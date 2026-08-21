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
            return tts.synthesize(script, provider=provider)
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


def main():
    import argparse
    from .schema import ShortUnit

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("short_ids", nargs="*", help="which units to voice")
    ap.add_argument("--all", action="store_true", help="every unit in output/")
    ap.add_argument("--check", action="store_true", help="report every provider")
    ap.add_argument("--force", action="store_true", help="re-record even if cached")
    ap.add_argument("--provider", help="override TTS_PROVIDER for this run")
    args = ap.parse_args()

    if args.provider:
        config.TTS_PROVIDER = args.provider

    if args.check:
        _report()
        return

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
