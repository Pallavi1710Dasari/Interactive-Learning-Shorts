"""
Voice audition — RESTYLE_TO_STORY_REELS.md Step 7 Part 3.

    python -m shorts.voice_audition

For each cast member, synthesizes 3 short sample lines in different
emotions, writes output/voice_audition/<name>_<n>_<provider>.wav plus one
combined output/voice_audition/audition_<provider>.wav, and runs BOTH
Kokoro and Chatterbox if Chatterbox is actually usable (see
story_voices.list_chatterbox_status — it needs a reference clip configured
per character, not just the package installed; see that function's own note).

Free, local, no API key — run it directly, no flags needed.
"""
from pathlib import Path

from . import config, story_voices
from .tts import ffmpeg_exe

OUT_DIR = config.OUTPUT_DIR / "voice_audition"

#: One line per emotion, per character — Step 7 Part 3's own sample set,
#: verbatim. Each character gets 3 lines spanning 3 different emotions from
#: config.EMOTION_DELIVERY, so the audition actually exercises the
#: emotion->delivery table, not just 3 identical readings of one line.
SAMPLE_LINES: dict[str, list[tuple[str, str]]] = {
    "Rahul": [
        ("Five clicks. Still zero?!", "frustrated"),
        ("Wait… what?", "confused"),
        ("It actually changed!", "delighted"),
    ],
    "Riya": [
        ("Look closer.", "calm"),
        ("That's the trick.", "confident"),
        ("Not quite.", "gentle"),
    ],
    "System": [
        ("I'll keep that for you.", "steady"),
        ("Absolutely not.", "firm"),
        ("Here you go.", "friendly"),
    ],
    "Narrator": [
        ("Ever wondered why some things stay?", "curious"),
        ("So Rahul tried again…", "storytelling"),
        ("And here's the twist.", "dramatic"),
    ],
}


def _run(args: list[str]) -> None:
    import subprocess
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[-400:]}")


def audition_for_provider(provider: str) -> list[Path]:
    """Synthesize every SAMPLE_LINES entry with `provider`. Raises
    story_voices.VoiceError immediately (before making any real synthesis
    call) if that provider's cast voices aren't all valid/configured —
    Step 7 Part 1's own "fail clearly" rule applies to the audition tool
    exactly as much as to a real reel."""
    story_voices.validate_cast_voices(provider)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for character, lines in SAMPLE_LINES.items():
        for i, (text, emotion) in enumerate(lines, 1):
            raw = story_voices.synth_raw(character, text, emotion, provider)
            path = OUT_DIR / f"{character.lower()}_{i}_{provider}.wav"
            path.write_bytes(raw)
            written.append(path)
            print(f"  {character} ({emotion}): {text!r} -> {path}")
    return written


def build_combined(paths: list[Path], provider: str) -> Path | None:
    """One concatenated audition_<provider>.wav from every clip
    audition_for_provider() wrote, in order. None (no file, printed reason)
    if ffmpeg isn't available — the per-clip WAVs written above are still
    useful on their own even without this."""
    exe = ffmpeg_exe()
    if exe is None or not paths:
        return None
    listfile = OUT_DIR / f"_list_{provider}.txt"
    listfile.write_text("\n".join(f"file '{p.resolve()}'" for p in paths), encoding="utf-8")
    out = OUT_DIR / f"audition_{provider}.wav"
    _run([exe, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), str(out)])
    listfile.unlink(missing_ok=True)
    return out


def main(argv: list[str] | None = None) -> int:
    providers_run = []
    for provider in ("kokoro", "chatterbox"):
        print(f"=== {provider} ===")
        try:
            paths = audition_for_provider(provider)
        except story_voices.VoiceError as e:
            print(f"  skipped: {e}")
            continue
        combined = build_combined(paths, provider)
        if combined:
            print(f"  wrote combined {combined}")
        providers_run.append(provider)

    print(f"\nProviders auditioned: {providers_run or '(none — see skip reasons above)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
