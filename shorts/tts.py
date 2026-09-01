"""
Assembling a short's narration, whoever speaks it.

    beat text -> conversational phrasing -> provider -> normalised wav
              -> measured duration -> beat span -> joined mp3

Providers live in providers.py; this file owns everything that is the same
regardless of who makes the audio.

TWO DESIGN NOTES WORTH READING

Beat timings are MEASURED, not requested. The first version asked ElevenLabs for
character-level alignments and folded them into word timings, which tied the whole
pipeline to one vendor's optional response field — Google returns nothing of the
kind, and Piper has no concept of it. Since each beat is synthesised separately, its
duration is simply the length of its own audio file, which every provider gives you
for free. Word timings are still kept when a provider offers them, but nothing
depends on them any more.

Every chunk is normalised to 44.1kHz mono WAV before joining. Providers return
different formats and sample rates — Piper 22kHz WAV, the cloud two 44.1kHz MP3 —
and concatenating those without normalising produces a file whose later beats play
at the wrong speed.
"""
import json, subprocess, tempfile, wave
from pathlib import Path

from .schema import Script, Audio, WordTiming, BeatSpan
from . import config, providers, speech

# Re-exported so callers can keep catching tts.AccountBlocked.
AccountBlocked = providers.AccountBlocked

SAMPLE_RATE = 44100


def ffmpeg_exe() -> str | None:
    """
    Path to an ffmpeg binary, or None.

    A system ffmpeg is preferred, but requiring one means requiring sudo on a fresh
    box just to hear a voice. imageio-ffmpeg ships a static build inside the venv and
    is in requirements.txt, so the normal install already has one.
    """
    import shutil
    if found := shutil.which("ffmpeg"):
        return found
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return None


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[-400:]}")


def _to_wav(raw: bytes, suffix: str, dest: Path, exe: str) -> float:
    """Write provider audio out as normalised WAV, and return its duration."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        src = f.name
    _run([exe, "-y", "-i", src, "-ar", str(SAMPLE_RATE), "-ac", "1", str(dest)])
    Path(src).unlink(missing_ok=True)
    with wave.open(str(dest)) as w:
        return w.getnframes() / float(w.getframerate())


def synthesize(script: Script, out_dir: Path | None = None,
               gap: float | None = None,
               provider: providers.Provider | None = None,
               voices: dict[str, str] | None = None) -> Audio:
    """
    Render every beat with the right voice, join them, and report exact beat spans.

    `voices` OVERRIDES provider.resolve() FOR THIS CALL, and it exists because of a
    bug that was invisible until someone tried the obvious thing twice.

    The voice studio previews a clip you have just uploaded. It used to do that by
    assigning config.CHATTERBOX_VOICE_* and letting resolve() pick them up — which
    worked exactly once. After the first adoption, voices/settings.json exists, and
    Chatterbox.resolve() reads that store BEFORE the environment (deliberately: a
    choice made in the UI has to outrank a stale .env). So every later preview
    silently used the ADOPTED voices instead of the uploaded ones: upload a
    different voice, press play, hear the old one, conclude the upload did nothing.

    Passing the voices in removes the ambiguity — a caller that knows which clips it
    means says so, rather than mutating global configuration and hoping the
    precedence rules fall its way. It is also the thread-safe shape: two previews at
    once were writing the same module-level globals.
    """
    provider = provider or providers.get()
    # With explicit voices the question is whether the ENGINE runs, not whether a
    # voice has been configured — the caller is holding the clips. available()
    # would fail here for a Chatterbox that simply has not been adopted yet, which
    # is the normal state while auditioning one.
    ok, why = provider.installed() if voices else provider.available()
    if not ok:
        raise RuntimeError(f"{provider.name}: {why}")

    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("no ffmpeg available to join the beats — "
                           "pip install imageio-ffmpeg, or install ffmpeg")

    out_dir = out_dir or config.OUTPUT_DIR / script.short_id
    out_dir.mkdir(parents=True, exist_ok=True)
    gap = config.VOICE_BEAT_GAP if gap is None else gap

    voices = voices or provider.resolve()
    missing = [k for k, v in voices.items() if not v]
    if missing:
        raise RuntimeError(f"{provider.name}: no voice configured for "
                           f"{', '.join(missing)}")

    parts, spans, all_words, cursor = [], [], [], 0.0

    for i, beat in enumerate(script.beats):
        spoken = speech.conversational(beat.line)
        raw = provider.synth(spoken, voices[beat.speaker], beat.speaker)

        chunk = out_dir / f"beat_{i:02d}.wav"
        duration = _to_wav(raw, provider.suffix, chunk, exe)

        spans.append(BeatSpan(start=round(cursor, 3), end=round(cursor + duration, 3)))
        all_words += _even_words(spoken, cursor, duration)
        parts.append(str(chunk))
        cursor += duration + gap

    combined = out_dir / "audio.mp3"
    _join(parts, combined, gap, exe)

    (out_dir / "spans.json").write_text(
        json.dumps([s.model_dump() for s in spans], indent=2))
    (out_dir / "timings.json").write_text(
        json.dumps([w.model_dump() for w in all_words], indent=2))

    # The trailing gap is silence after the last word; the track ends with the words.
    duration = round(max(cursor - gap, 0.0), 2)
    return Audio(file=str(combined), duration_seconds=duration,
                 word_timings=all_words, beat_spans=spans)


def _even_words(text: str, offset: float, duration: float) -> list[WordTiming]:
    """
    Word timings spread evenly across a beat.

    An approximation, and labelled as one. Beat changes — the thing the video
    actually needs — come from the measured beat spans and are exact; these exist so
    a future word-level effect has something to work with, and so the field is
    populated the same way whoever spoke. Do not build anything load-bearing on them
    without checking whether the provider can give real ones.
    """
    words = text.split()
    if not words or duration <= 0:
        return []
    step = duration / len(words)
    return [WordTiming(word=w, start=round(offset + i * step, 3),
                       end=round(offset + (i + 1) * step, 3))
            for i, w in enumerate(words)]


def _join(parts: list[str], out: Path, gap: float, exe: str) -> None:
    """Concatenate the beat wavs with silence between them, encode one mp3."""
    silence = out.parent / "_gap.wav"
    _run([exe, "-y", "-f", "lavfi", "-i",
          f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", str(gap), str(silence)])

    seq: list[str] = []
    for p in parts:
        seq += [p, str(silence)]
    seq = seq[:-1]                      # no trailing silence

    # ABSOLUTE PATHS IN THE LIST. ffmpeg's concat demuxer resolves each entry
    # relative to the LIST FILE, and the list file is in the system temp dir — so a
    # relative beat path became /tmp/output/.../beat_00.wav and the join failed with
    # "No such file or directory" on files that were sitting right there. It never
    # bit in production because out_dir defaults to config.OUTPUT_DIR, which is
    # absolute; it bit the moment anything passed a relative directory in.
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in seq:
            f.write(f"file '{Path(p).resolve()}'\n")
        listfile = f.name

    _run([exe, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
          "-ar", str(SAMPLE_RATE), "-ac", "1", "-b:a", "128k", str(out)])
    Path(listfile).unlink(missing_ok=True)
    silence.unlink(missing_ok=True)


def probe(provider: providers.Provider | None = None) -> tuple[bool, str]:
    """
    Can this provider actually synthesise? Costs about a dozen characters.

    Credentials that parse, list voices, and report a subscription still do not prove
    audio can be produced — ElevenLabs reported "configured" right up until the first
    real beat failed. The only way to know is to synthesise something.
    """
    provider = provider or providers.get()
    ok, why = provider.available()
    if not ok:
        return False, why
    try:
        voices = provider.resolve()
        raw = provider.synth("Hello there.", voices["student"], "student")
    except AccountBlocked as e:
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if not raw:
        return False, "the provider returned no audio"
    return True, f"synthesis works ({len(raw)} bytes via {provider.name})"
