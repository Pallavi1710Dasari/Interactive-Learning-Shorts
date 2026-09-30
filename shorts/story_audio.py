"""
Story-mode audio — RESTYLE_TO_STORY_REELS.md Step 7 Part 2.

    python -m shorts.story_audio <short_id>

Per shot (including the Narrator's text_card/recap/cta lines — see
spoken_text() below): synthesize with the speaker's voice + emotion
delivery (shorts/story_voices.py), cache by hash(provider, voice, text,
params), measure real duration, and derive word timings the same way
tts.py's own _even_words does — evenly split across the MEASURED duration,
an approximation labelled as one, never forced-aligned.

Then: pad every shot's audio to its own final_duration, concatenate with
STORY_SHOT_AUDIO_GAP silence between shots, normalize the whole mix to
STORY_AUDIO_TARGET_LUFS (ffmpeg's loudnorm filter — free, no pyloudnorm
dependency needed since imageio_ffmpeg is already a project dependency),
and duck in an optional MUSIC_PATH bed underneath.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path

from . import config, story_voices
from .checks import shot_speaker
from .schema import Shot, StoryScript, WordTiming
from .story_frames import load_story
from .tts import ffmpeg_exe

AUDIO_CACHE_DIR = config.OUTPUT_DIR / ".story_audio_cache"
#: Kokoro's own native output rate (and story_voices.silent_wav_bytes's
#: default) — everything in this module's mix pipeline stays at this rate
#: so no step silently resamples.
MIX_SAMPLE_RATE = 24000


def spoken_text(shot: Shot) -> str | None:
    """
    What the Narrator (or an acting character) actually SAYS for this shot —
    Step 7's own "including text_card/recap/cta Narrator lines" rule. An
    ordinary scene shot speaks `line` verbatim; a text_card/cta shot has no
    `line` (its words live in `overlay_text` — see Shot's own docstring)
    but the Narrator still reads that text aloud; a recap shot reads its
    condensed `card_lines` out, joined. Returns None only for a shot with
    genuinely nothing to say (a pure establishing beat).
    """
    if shot.line:
        return shot.line
    if shot.kind in ("text_card", "cta") and shot.overlay_text:
        return shot.overlay_text
    if shot.kind == "recap" and shot.card_lines:
        # STEP 9 FIX 1: each card_line already carries its OWN terminal
        # punctuation ("Stub lesson 1.", "Some things need a better place
        # to live!") — joining them with ". " unchanged produced "..",
        # ". .", "!." etc. at every seam. Strip each line's own trailing
        # punctuation first, then join with a single ". ", then end with
        # exactly one ".".
        cleaned = [line.strip().rstrip(".!?").strip() for line in shot.card_lines]
        cleaned = [line for line in cleaned if line]
        return ". ".join(cleaned) + "." if cleaned else None
    return None


def _params_for(tts_provider: str, emotion: str) -> dict:
    delivery = config.emotion_delivery(emotion)
    if tts_provider == "kokoro":
        return {"speed": delivery["kokoro_speed"]}
    return {"exaggeration": delivery["chatterbox_exaggeration"],
           "cfg_weight": delivery["chatterbox_cfg_weight"]}


def _cache_key(tts_provider: str, voice: str, text: str, params: dict) -> str:
    """sha256(provider + voice + text + params) — Step 7 Part 2's own cache
    spec, verbatim, same pattern as shorts/imagegen.py's image cache key."""
    h = hashlib.sha256()
    h.update(tts_provider.encode())
    h.update(voice.encode())
    h.update(text.encode("utf-8"))
    h.update(json.dumps(params, sort_keys=True).encode())
    return h.hexdigest()


def _resolved_cache_key(character: str, text: str, emotion: str,
                        tts_provider: str | None = None) -> str:
    """The SAME cache key synth_cached uses, keyed by the ACTUALLY RESOLVED
    provider (story_voices.resolve_provider), not the raw requested one —
    Step 8 Part 1's own fallback means a "chatterbox" request can really be
    synthesized by Kokoro, and a cache namespaced under "chatterbox" for
    audio that is actually Kokoro's would be wrong: it would keep serving
    stale Kokoro-fallback bytes under a "chatterbox" key even after
    Chatterbox becomes available and would otherwise produce a different
    clip. Exposed separately (not just inlined into synth_cached) so
    render_shot_audio's word-timing cache (below) can key off the exact
    same resolved identity without resynthesizing anything."""
    tts_provider = (tts_provider or config.TTS_PROVIDER_STORY).strip().lower()
    resolved = story_voices.resolve_provider(character, tts_provider)
    voice = story_voices.voice_for(character, resolved)
    params = _params_for(resolved, emotion)
    return _cache_key(resolved, voice, text, params)


def synth_cached(character: str, text: str, emotion: str,
                 tts_provider: str | None = None) -> bytes:
    """story_voices.synth_raw(), wrapped in a real content-addressed cache —
    a cache hit never calls the underlying engine again, real OR stub."""
    key = _resolved_cache_key(character, text, emotion, tts_provider)
    cache_path = AUDIO_CACHE_DIR / f"{key}.wav"
    if cache_path.exists():
        return cache_path.read_bytes()

    raw = story_voices.synth_raw(character, text, emotion, tts_provider)
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(raw)
    return raw


def _even_words(text: str, offset: float, duration: float) -> list[WordTiming]:
    """Word timings spread evenly across a shot's MEASURED duration — the
    same approximation tts.py's own _even_words uses (see that function's
    docstring: real beat/shot boundaries are exact, per-word ones inside a
    beat are not, and nothing downstream should treat them as forced-aligned).
    THE FALLBACK, not the default any more — see _word_timings below."""
    words = text.split()
    if not words or duration <= 0:
        return []
    step = duration / len(words)
    return [WordTiming(word=w, start=round(offset + i * step, 3),
                       end=round(offset + (i + 1) * step, 3))
           for i, w in enumerate(words)]


_whisper_model = None


def _load_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE,
                                      compute_type=config.WHISPER_COMPUTE_TYPE)
    return _whisper_model


def _whisper_words(wav_path: Path, text: str) -> list[WordTiming] | None:
    """
    REAL per-word timings from the actual synthesized audio at `wav_path` —
    RESTYLE_TO_STORY_REELS.md Step 8 Part 1's own rule: word timestamps must
    come from real audio, not an even split.

    Neither of this project's TTS engines returns native word-level
    timestamps today (Kokoro's model.create() returns raw samples only;
    Chatterbox's worker protocol returns only a clip's total `seconds` — see
    shorts/story_voices.py and shorts/chatterbox_worker.py) — the "or the
    TTS engine's own timestamps" leg of the rule has nothing to try against
    either provider as they exist in this codebase, so faster-whisper is the
    one real source this function attempts, not a first choice among two.

    faster-whisper (this project's local ASR) does not do true phoneme-level
    FORCED alignment to a known transcript out of the box — that needs a
    separate aligner (e.g. wav2vec2-based, as whisperx bundles), which is
    not a dependency here. What this does instead, and what "forced to the
    known line text" means in this implementation: run word_timestamps=True
    transcription with `initial_prompt=text` (biases decoding toward the
    known line), then take whisper's own detected word BOUNDARIES
    (start/end, from the real audio) and pair them POSITIONALLY with our
    OWN known words — the text we synthesized is already ground truth, so
    trusting whisper's occasionally-misheard transcribed text over it would
    be a downgrade, not an improvement.

    Returns None (never raises) when whisper is unavailable, errors, or its
    own detected word count doesn't match our known text's word count
    closely enough to pair positionally with confidence — the caller logs a
    warning and falls back to _even_words in every one of those cases.
    """
    known = text.split()
    if not known:
        return None
    try:
        model = _load_whisper_model()
        segments, _ = model.transcribe(str(wav_path), word_timestamps=True,
                                       initial_prompt=text, language="en", beam_size=1)
        detected = [w for seg in segments for w in (seg.words or [])]
    except Exception as e:
        print(f"  timing: faster-whisper failed ({type(e).__name__}: {e}) for "
             f"{text[:50]!r} — falling back to an even split")
        return None
    if len(detected) != len(known):
        print(f"  timing: faster-whisper detected {len(detected)} word(s) but "
             f"the known line has {len(known)} — counts don't line up closely "
             f"enough to pair positionally, falling back to an even split "
             f"for {text[:50]!r}")
        return None
    return [WordTiming(word=known[i], start=round(detected[i].start, 3),
                       end=round(detected[i].end, 3)) for i in range(len(known))]


def _word_timings(wav_path: Path, text: str, fallback_duration: float,
                  cache_key: str | None = None) -> list[WordTiming]:
    """The one call site render_shot_audio uses: real timing when possible,
    the even-split approximation (with a printed warning) otherwise. Never
    attempted under SHORTS_STUB=1 — the "audio" there is a silent WAV of an
    estimated length (see story_voices.synth_raw's own STUB branch), so
    whisper would only ever detect 0 words against it; loading a real ASR
    model to prove that on every single stub test run would be pure waste,
    for a warning that is never actionable under stub.

    `cache_key`, when given (the SAME key synth_cached's own audio cache
    used for this exact (character, text, params)), caches the whisper
    result as a sidecar JSON next to that audio's cache entry — a cache
    HIT on the audio (recap/cta lines and repeated dialogue reuse the same
    clip often) would otherwise still pay to re-transcribe identical audio
    on every shot that reuses it.
    """
    if not text:
        return []
    cache_path = (AUDIO_CACHE_DIR / f"{cache_key}.words.json") if cache_key else None
    if cache_path is not None and cache_path.exists():
        return [WordTiming(**w) for w in json.loads(cache_path.read_text(encoding="utf-8"))]

    if not config.STUB:
        words = _whisper_words(wav_path, text)
        if words is not None:
            if cache_path is not None:
                cache_path.write_text(json.dumps([w.model_dump() for w in words]),
                                      encoding="utf-8")
            return words
    return _even_words(text, 0.0, fallback_duration)


def _audio_dir(short_id: str) -> Path:
    d = config.OUTPUT_DIR / short_id / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _shot_wav_path(short_id: str, shot_id: str) -> Path:
    return _audio_dir(short_id) / f"shot_{shot_id}.wav"


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[-400:]}")


def _pad_to(src: Path, dest: Path, target_seconds: float, exe: str) -> None:
    """Pad (never trim) `src` with trailing silence up to `target_seconds` —
    a shot's audio slot in the final mix is always exactly final_duration
    wide, even when the spoken line itself is shorter."""
    _run([exe, "-y", "-i", str(src), "-af",
         f"apad=whole_dur={target_seconds}", "-t", str(target_seconds), str(dest)])


def render_shot_audio(short_id: str, shot: Shot,
                      tts_provider: str | None = None) -> dict:
    """
    Synthesize (cached), measure, and pad ONE shot's audio to its own
    final_duration — Step 7's own rule: final_duration = max(planned
    duration, audio_len + 0.25s), EXCEPT recap/cta, which "keep their
    planned minimum" (their own Shot.duration_seconds is never stretched to
    fit a longer voice-over — the overlay's own pacing, from Step 2 Part B,
    already governs those two).

    Returns {"final_duration": float, "words": [...]} — story_audio.py's
    per-shot record; the padded WAV is written to
    output/<short_id>/audio/shot_<id>.wav as a side effect.
    """
    text = spoken_text(shot)
    speaker = shot_speaker(shot)
    exe = ffmpeg_exe()
    if exe is None:
        raise RuntimeError("no ffmpeg available (system or imageio_ffmpeg) — "
                           "cannot pad/measure story audio")

    cache_key = None
    if not text:
        # Nothing spoken — silence for the shot's own planned duration.
        final_duration = shot.duration_seconds
        raw = story_voices.silent_wav_bytes(final_duration)
    else:
        cache_key = _resolved_cache_key(speaker, text, shot.emotion, tts_provider)
        raw = synth_cached(speaker, text, shot.emotion, tts_provider)
        audio_len = story_voices.wav_duration(raw)
        if shot.kind in ("recap", "cta"):
            # "Keep their planned minimum" — shot.duration_seconds is a
            # FLOOR for these two, not the +0.25s-buffered target ordinary
            # shots get, but it is still a MINIMUM: if the actual audio
            # (reading overlay_text/card_lines aloud) runs longer than the
            # planned floor, final_duration still has to cover all of it —
            # otherwise _pad_to's own `-t final_duration` truncation below
            # would silently CUT THE AUDIO OFF mid-sentence, which is a much
            # worse defect than a recap/cta running a little long.
            final_duration = max(shot.duration_seconds, audio_len)
        else:
            final_duration = max(shot.duration_seconds, audio_len + 0.25)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(raw)
        raw_path = Path(f.name)
    try:
        words = (_word_timings(raw_path, text, final_duration, cache_key=cache_key)
                if text else [])
        _pad_to(raw_path, _shot_wav_path(short_id, shot.shot_id), final_duration, exe)
    finally:
        raw_path.unlink(missing_ok=True)

    return {"final_duration": round(final_duration, 3),
           "words": [w.model_dump() for w in words]}


def _mix(short_id: str, shots: list[Shot], exe: str) -> Path:
    """Concatenate every shot's padded WAV with STORY_SHOT_AUDIO_GAP silence
    between them, then normalize the whole thing to STORY_AUDIO_TARGET_LUFS
    — ffmpeg's own `loudnorm` filter, no pyloudnorm dependency needed."""
    audio_dir = _audio_dir(short_id)
    gap = config.STORY_SHOT_AUDIO_GAP

    listfile_lines = []
    silence_path = audio_dir / "_gap.wav"
    if gap > 0:
        _run([exe, "-y", "-f", "lavfi", "-i", f"anullsrc=r={MIX_SAMPLE_RATE}:cl=mono",
             "-t", str(gap), str(silence_path)])

    for i, shot in enumerate(shots):
        if i > 0 and gap > 0:
            listfile_lines.append(f"file '{silence_path.resolve()}'")
        listfile_lines.append(f"file '{_shot_wav_path(short_id, shot.shot_id).resolve()}'")

    listfile = audio_dir / "_concat_list.txt"
    listfile.write_text("\n".join(listfile_lines), encoding="utf-8")

    raw_mix = audio_dir / "_mix_raw.wav"
    _run([exe, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), str(raw_mix)])

    mix_path = audio_dir / "mix.wav"
    # `-ar` EXPLICIT ON PURPOSE: ffmpeg's loudnorm filter silently upsamples
    # its output (observed: 24kHz mono in -> 192kHz out) when no output
    # sample rate is given, bloating the file ~8x for no audible benefit at
    # this content's actual bandwidth. Pin it back to MIX_SAMPLE_RATE.
    _run([exe, "-y", "-i", str(raw_mix), "-af",
         f"loudnorm=I={config.STORY_AUDIO_TARGET_LUFS}:TP=-1.5:LRA=11",
         "-ar", str(MIX_SAMPLE_RATE), str(mix_path)])

    if config.MUSIC_PATH and Path(config.MUSIC_PATH).exists():
        mix_path = _duck_music(mix_path, audio_dir, exe)

    for p in (silence_path, listfile, raw_mix):
        p.unlink(missing_ok=True)
    return mix_path


def _duck_music(speech_path: Path, audio_dir: Path, exe: str) -> Path:
    """
    Mix `speech_path` with config.MUSIC_PATH, the music bed held at
    MUSIC_DUCK_DB relative to the speech track.

    A FIXED reduction for the whole track, not a dynamic per-word
    sidechain duck — "duck it to -18 dB under speech" is implemented as
    "the music bed sits at a fixed level under the mix", the simplest
    honest reading that needs no extra dependency beyond ffmpeg's own
    `amix`/`volume` filters (a real sidechain-compressor duck that
    tightens only where speech is actually present is a real refinement
    or later, not attempted here).
    """
    out = audio_dir / "mix_with_music.wav"
    duck_gain = f"{config.MUSIC_DUCK_DB}dB"
    _run([exe, "-y", "-i", str(speech_path), "-i", config.MUSIC_PATH,
         "-filter_complex",
         f"[1:a]volume={duck_gain}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]",
         "-map", "[out]", str(out)])
    return out


def run(short_id: str, tts_provider: str | None = None) -> int:
    tts_provider = (tts_provider or config.TTS_PROVIDER_STORY).strip().lower()
    # RESTYLE_TO_STORY_REELS.md Step 8 Part 1: TTS_PROVIDER_STORY=chatterbox
    # missing a clip is no longer a hard failure — story_voices.synth_raw
    # falls back to Kokoro automatically, per character, logging it as it
    # happens. Kokoro (the guaranteed fallback target) is still validated
    # strictly here: if THAT is broken there is nowhere left to fall back
    # to, and failing clearly before any synthesis is better than failing
    # midway through a 27-shot reel.
    story_voices.validate_cast_voices("kokoro")
    summary = story_voices.resolution_summary(tts_provider)
    print("Voice provider resolution (per character):")
    for name, using in summary.items():
        print(f"  {name}: requested={tts_provider} -> using={using}")

    story = load_story(short_id)
    exe = ffmpeg_exe()
    if exe is None:
        raise RuntimeError("no ffmpeg available — cannot render story audio")

    timings: dict[str, dict] = {}
    cursor = 0.0
    for shot in story.shots:
        record = render_shot_audio(short_id, shot, tts_provider)
        start = cursor
        end = round(start + record["final_duration"], 3)
        timings[shot.shot_id] = {
            "start": start, "end": end,
            "final_duration": record["final_duration"],
            "words": [{"word": w["word"], "start": round(start + w["start"], 3),
                      "end": round(start + w["end"], 3)} for w in record["words"]],
        }
        cursor = end + (config.STORY_SHOT_AUDIO_GAP if shot is not story.shots[-1] else 0.0)
        shot.final_duration_seconds = record["final_duration"]
        print(f"  {shot.shot_id}: {record['final_duration']:.2f}s "
             f"[{timings[shot.shot_id]['start']:.2f}-{timings[shot.shot_id]['end']:.2f}]")

    timings_path = config.OUTPUT_DIR / short_id / "timings.json"
    timings_path.write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"wrote {timings_path}")

    mix_path = _mix(short_id, story.shots, exe)
    print(f"wrote {mix_path}")

    story_path = config.OUTPUT_DIR / f"{short_id}.story.json"
    story_path.write_text(story.model_dump_json(indent=2), encoding="utf-8")
    print(f"updated {story_path} with final_duration_seconds per shot")

    total = cursor
    needs_review = total > config.STORY_MAX_TOTAL_SECONDS
    status_path = config.OUTPUT_DIR / short_id / "audio" / "status.json"
    status = {"status": "NEEDS_REVIEW" if needs_review else "OK",
             "total_seconds": round(total, 2),
             "max_seconds": config.STORY_MAX_TOTAL_SECONDS}
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

    print(f"\nTotal: {total:.2f}s (max {config.STORY_MAX_TOTAL_SECONDS}s)")
    if needs_review:
        over = [(sid, t["final_duration"]) for sid, t in timings.items()
               if t["final_duration"] > 3.0]
        over.sort(key=lambda x: -x[1])
        print(f"NEEDS_REVIEW — reel runs {total - config.STORY_MAX_TOTAL_SECONDS:.2f}s "
             f"over. Longest shots: {over[:5]}")
        print("(not auto-rewriting the script — that would cost LLM calls)")
    else:
        print("status: OK")

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m shorts.story_audio",
                                description="Synthesize and mix one story reel's audio.")
    p.add_argument("short_id")
    p.add_argument("--provider", choices=["kokoro", "chatterbox"], default=None,
                   help="override TTS_PROVIDER_STORY")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.short_id, args.provider)


if __name__ == "__main__":
    raise SystemExit(main())
