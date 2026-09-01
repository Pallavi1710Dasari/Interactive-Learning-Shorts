"""
Recorded neural narration: an approved short gets a real voice track.

    python -m shorts.voice --check          # is it configured? which voices?
    python -m shorts.voice --all            # backfill every unit in output/
    python -m shorts.voice <short_id> ...   # just these

Generated once at build time and cached next to the unit JSON, never at watch time.
Two things follow from that: watching is instant and a re-watch costs nothing, and
the beats are cut to the provider's own word timings so the diagram changes on the
word instead of on a words-per-minute estimate.

Voice ids do not have to be configured. A mistyped id is a 404 on every beat and was
the most common way this step failed, so with VOICE_INTERVIEWER / VOICE_STUDENT
blank this resolves two contrasting voices from the account's own library once and
caches the choice for the process.

Still best-effort at build time: a missing key, an expired key, no ffmpeg, or a
provider outage must not cost anyone a reel they have already approved. The short is
written either way and the browser voice narrates it.
"""
import json
from pathlib import Path

from .schema import Script, Audio, WordTiming, BeatSpan
from . import config, providers, tts


def audio_dir(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id


def existing(short_id: str) -> Path | None:
    """The cached track for a short, if it has one. Never regenerate over this."""
    path = audio_dir(short_id) / "audio.mp3"
    return path if path.exists() and path.stat().st_size > 0 else None


# ------------------------------------------------------------------ configuration

def configured() -> tuple[bool, str]:
    """Whether a recorded track can be produced, and why not when it cannot."""
    if not tts.ffmpeg_exe():
        return False, ("no ffmpeg to join the beats — pip install imageio-ffmpeg, "
                       "or install ffmpeg")
    provider = providers.get()
    ok, why = provider.available()
    return ok, f"{provider.name}: {why}"


# ---------------------------------------------------------------- synthesis

def synthesize(script: Script) -> Audio | None:
    """
    Render one short to a cached mp3. Returns None if it cannot be done.

    Never raises: every caller is in the middle of building something the user has
    already approved, and a voice failure is not a reason to lose it.
    """
    ok, _ = configured()
    if not ok:
        return None

    cached = _from_cache(script)
    if cached:
        print(f"    voice {script.short_id}: reusing cached audio.mp3")
        return cached

    # Down the chain until one speaks. With TTS_PROVIDER set that chain is one entry
    # long and a failure is final; on "auto" a provider that cannot synthesise is
    # remembered and the next one gets a turn, which is what makes a blocked
    # ElevenLabs account degrade to Google or Piper instead of to silence.
    blocked: Exception | None = None
    for provider in providers.chain():
        try:
            audio = tts.synthesize(script, provider=provider)
            # Record WHO spoke, so _from_cache can tell a re-record after a voice
            # change from a genuine cache hit.
            try:
                (audio_dir(script.short_id) / "voice.json").write_text(
                    _stamp_for(provider))
            except OSError:
                pass          # a missing stamp only costs a re-record
            return audio
        except tts.AccountBlocked as e:
            providers.mark_blocked(provider.name)
            blocked = e
            continue
        except Exception as e:
            print(f"    ! voice {script.short_id} via {provider.name}: "
                  f"{type(e).__name__}: {e}")
            return None

    if blocked is not None:
        raise blocked          # every candidate refused; the caller decides
    return None


def _voice_stamp(directory: Path) -> str:
    """What voice made the track in `directory`, or "" if it predates stamping."""
    try:
        return (directory / "voice.json").read_text().strip()
    except OSError:
        return ""


def _stamp_for(provider) -> str:
    """The identity of one provider's current voice configuration."""
    import hashlib
    h = hashlib.sha256()
    h.update(provider.name.encode())
    for who, ref in sorted(provider.resolve().items()):
        h.update(who.encode())
        h.update(str(ref).encode())
        clip = Path(str(ref))
        if clip.exists() and clip.is_file():
            st = clip.stat()
            h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def _current_voice_stamp() -> str:
    """
    An identity for the voice that would speak right now.

    Hashes the reference clips' CONTENT, not their paths: replacing
    voices/student.wav with a different recording at the same name is a different
    voice and has to invalidate, and a path comparison would miss that entirely.
    """
    from . import providers
    try:
        return _stamp_for(providers.get())
    except Exception:
        return ""


def _from_cache(script: Script) -> Audio | None:
    """
    Rebuild an Audio from a track already on disk.

    Keyed on the spoken words, not on the short id: regenerating a short after a
    reviewer's edit reuses the id, and serving the old recording against new beats
    would put the wrong words under the diagram. A changed script means a changed
    word list means a cache miss.
    """
    directory = audio_dir(script.short_id)
    track, timings = existing(script.short_id), directory / "timings.json"
    if not track or not timings.exists():
        return None

    # THE VOICE IS PART OF THE KEY, and leaving it out broke the one workflow the
    # voice studio exists for. The docstring above is right that a changed SCRIPT
    # must miss — but a changed VOICE must miss too, and it did not: the test was
    # the word list and the beat count, both of which are identical when the only
    # thing that changed is who is speaking.
    #
    # So adopting a new voice and re-recording returned every existing track
    # unchanged, from the previous voice, reporting success. The person hears no
    # difference and reasonably concludes the new voice did not take.
    if _voice_stamp(directory) != _current_voice_stamp():
        return None
    try:
        words = [WordTiming(**w) for w in json.loads(timings.read_text())]
        spans_file = directory / "spans.json"
        spans = ([BeatSpan(**s) for s in json.loads(spans_file.read_text())]
                 if spans_file.exists() else [])
    except Exception:
        return None

    if len(spans) != len(script.beats):
        return None          # written before spans existed, or the script changed
    return Audio(file=str(track), duration_seconds=spans[-1].end if spans else 0.0,
                 word_timings=words, beat_spans=spans)


# --------------------------------------------------------------------- cli

def _units() -> list[Path]:
    from . import feed
    return [p for p in sorted(config.OUTPUT_DIR.glob("*.json"))
            if p.name not in feed.SIDECARS]


def _report() -> None:
    """
    Every provider, whether it works, and what it would use.

    Reports on all of them rather than only the selected one, because the useful
    question when the voice is wrong is "what are my options" — and because a
    provider that merely holds credentials is not the same as one that can speak.
    Each row is a real synthesis attempt of about a dozen characters.
    """
    if not tts.ffmpeg_exe():
        print("! no ffmpeg — pip install imageio-ffmpeg. Nothing can be joined.")

    active = providers.get()
    print(f"TTS_PROVIDER={config.TTS_PROVIDER or 'auto'} -> using {active.name!r}\n")

    for provider in providers.all_providers():
        mark = "*" if provider.name == active.name else " "
        ok, why = provider.available()
        print(f"{mark} {provider.name:11} {'configured' if ok else 'not configured'} — {why}")
        if not ok:
            continue
        works, detail = tts.probe(provider)
        print(f"{'':13} synthesis: {'OK' if works else 'BLOCKED'} — {detail[:180]}")
        if works:
            print(f"{'':13} voices: {provider.resolve()}")


#: What an auditioned clip is made to say. Two sentences, because one is not enough
#: to hear whether a cloned voice holds together across a sentence boundary, and
#: because this is roughly the length of one real beat.
_AUDITION_LINE = (
    "So everything a computer processes gets represented using only two values "
    "— ones and zeros. That is why we call it binary.")


def _audition(clip: str) -> int:
    """
    Speak one line in the voice of `clip`, so a candidate can be judged in a minute.

    THE POINT IS THE LOOP. Choosing a reference clip is a taste decision made by
    listening, and before this the only way to hear one was to edit .env, re-record
    a whole short and play that — a five-minute round trip per candidate, with the
    project's real configuration changed on every attempt. This changes nothing:
    it takes a path, writes one mp3 next to it, and prints where.
    """
    from pathlib import Path as _P
    from . import providers, tts
    from .schema import Script, Beat

    src = _P(clip)
    if not src.exists():
        print(f"! no such clip: {src}")
        return 1

    cb = providers._REGISTRY["chatterbox"]
    exe = _P(config.CHATTERBOX_PYTHON)
    if not exe.exists():
        print(f"! Chatterbox is not installed at {exe}\n"
              f"  python3 -m venv venv-chatterbox && "
              f"venv-chatterbox/bin/pip install chatterbox-tts")
        return 1

    out_dir = config.OUTPUT_DIR / "voice-auditions" / src.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    # The first beat must be the interviewer — Script validates that, and it is the
    # right shape anyway: both refs point at the clip being auditioned, so this
    # speaks the sample line in that one voice regardless of who is nominally
    # talking.
    script = Script(short_id=f"audition_{src.stem}",
                    question=_AUDITION_LINE,
                    beats=[Beat(speaker="interviewer", line=_AUDITION_LINE,
                                on_screen="audition", visual_ref="v")])
    print(f"auditioning {src} — the model loads once, this takes a couple of minutes")
    # The clip is BOTH voices: an audition is about one speaker at a time. Passed
    # explicitly rather than assigned to config, which an adopted voice overrides.
    try:
        audio = tts.synthesize(script, out_dir=out_dir.resolve(), provider=cb,
                               voices={"interviewer": str(src), "student": str(src)})
    except Exception as e:
        print(f"! {type(e).__name__}: {e}")
        return 1
    print(f"\n  reference : {src}")
    print(f"  spoken    : {audio.file}   ({audio.duration_seconds:.1f}s)")
    print(f"\nplay them back to back:\n"
          f"  ffplay -nodisp -autoexit {src}\n"
          f"  ffplay -nodisp -autoexit {audio.file}\n"
          f"\nhappy with it? put it in .env:\n"
          f"  TTS_PROVIDER=chatterbox\n"
          f"  CHATTERBOX_VOICE_STUDENT={src}")
    return 0


def main():
    import argparse
    from .schema import ShortUnit

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("short_ids", nargs="*", help="which units to voice")
    ap.add_argument("--all", action="store_true", help="every unit in output/")
    ap.add_argument("--check", action="store_true", help="report every provider")
    ap.add_argument("--force", action="store_true", help="re-record even if cached")
    ap.add_argument("--provider", help="override TTS_PROVIDER for this run")
    ap.add_argument("--try", dest="try_clip", metavar="CLIP",
                    help="audition one reference clip through Chatterbox and exit — "
                         "speaks a sample line in that voice, changes nothing")
    args = ap.parse_args()

    if args.provider:
        config.TTS_PROVIDER = args.provider

    if args.check:
        _report()
        return

    if args.try_clip:
        raise SystemExit(_audition(args.try_clip))

    ok, why = configured()
    print(f"provider: {why}")
    if not ok:
        raise SystemExit("cannot record narration — fix the above first")

    targets = _units() if args.all else [
        config.OUTPUT_DIR / f"{s}.json" for s in args.short_ids]
    if not targets:
        raise SystemExit("name some short_ids, or pass --all")

    done = failed = skipped = 0
    for path in targets:
        if not path.exists():
            print(f"  ! {path.name}: no such unit")
            failed += 1
            continue
        unit = ShortUnit(**json.loads(path.read_text()))
        script = Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)

        if args.force:
            for stale in ("audio.mp3", "timings.json", "spans.json"):
                (audio_dir(unit.short_id) / stale).unlink(missing_ok=True)
        elif existing(unit.short_id):
            print(f"  = {unit.short_id}: already recorded")
            skipped += 1
            continue

        print(f"  voicing {unit.short_id} ({len(unit.beats)} beats)…")
        try:
            audio = synthesize(script)
        except tts.AccountBlocked as e:
            raise SystemExit(f"\n{e}\n\nNothing will record until that is resolved. "
                             f"The reels still play with the browser voice.")
        if not audio:
            failed += 1
            continue
        unit.audio = audio
        path.write_text(unit.model_dump_json(indent=2))
        print(f"    -> {audio.duration_seconds}s, {len(audio.word_timings)} word timings")
        done += 1

    print(f"\n{done} recorded, {skipped} already done, {failed} failed")


if __name__ == "__main__":
    main()
