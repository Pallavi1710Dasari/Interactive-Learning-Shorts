"""
Chatterbox reference-clip seeding — RESTYLE_TO_STORY_REELS.md Step 8 Part 1.

    python -m shorts.voice_refs --from-kokoro
    python -m shorts.voice_refs --from-kokoro --force

For each of config.CAST's 4 roles, synthesizes a ~10s neutral sentence with
that character's own mapped Kokoro voice (config.CAST_KOKORO_VOICE) and
writes it to assets/voices/<name>.wav — a real starting reference clip for
Chatterbox to clone from, so a fresh checkout has SOMETHING before a human
ever records a real line. config.CAST_CHATTERBOX_VOICE auto-discovers these
files on the next process start (see config.py's own
_default_chatterbox_voice) — nothing else needs to change to "wire them in".

NEVER OVERWRITES an existing clip without --force — a human-recorded
reference clip that already replaced a Kokoro-seeded one must not be
silently clobbered by re-running this.

Free, local, no API key.
"""
import argparse
from pathlib import Path

from . import config, story_voices

#: One neutral(ish) ~10s sentence per character — long enough for a usable
#: Chatterbox reference clip (short clips clone poorly), short enough this
#: stays a quick, free, local step. Synthesized at "neutral" emotion
#: (config.EMOTION_DELIVERY_DEFAULT's 1.0x speed) — a REFERENCE clip should
#: capture the voice itself, not a specific emotional delivery.
SEED_LINES: dict[str, str] = {
    "Rahul": ("I keep trying the same thing over and over, expecting a "
             "different result, and every single time it comes back exactly "
             "the way it did before."),
    "Riya": ("If you slow down and look at what's actually happening step "
            "by step, the answer is usually sitting right there in front "
            "of you the whole time."),
    "System": ("I hold onto whatever you give me for as long as you need "
              "it, and I hand it back exactly the way you left it, every "
              "single time you ask."),
    "Narrator": ("Every story about a system starts the same way: "
                "something small goes wrong, somebody notices, and the "
                "rest of us finally understand why it mattered all along."),
}


def _out_path(name: str) -> Path:
    return config.CAST_VOICE_DIR / f"{name.lower()}.wav"


def run(force: bool) -> int:
    config.CAST_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []
    for name in story_voices.CAST_ROLES:
        out = _out_path(name)
        if out.exists() and not force:
            skipped.append(name)
            print(f"  {name}: {out} already exists — skipped (use --force to overwrite)")
            continue
        raw = story_voices.synth_raw(name, SEED_LINES[name], "neutral", "kokoro")
        out.write_bytes(raw)
        seconds = story_voices.wav_duration(raw)
        written.append(name)
        print(f"  {name}: wrote {out} ({seconds:.1f}s, voice={config.CAST_KOKORO_VOICE[name]})")

    print(f"\n{len(written)} written, {len(skipped)} skipped (already existed): "
         f"written={written} skipped={skipped}")
    if written:
        print("CAST_CHATTERBOX_VOICE auto-discovers these on the next process "
             "start (config.py's own _default_chatterbox_voice) — no .env "
             "edit needed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.voice_refs",
        description="Seed assets/voices/<name>.wav from each character's mapped Kokoro voice.")
    p.add_argument("--from-kokoro", action="store_true", required=True,
                   help="the only supported source today — explicit so a future "
                       "--from-recording flag has an unambiguous opposite")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing clip (never the default — a "
                       "human-recorded clip must not be silently clobbered)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.force)


if __name__ == "__main__":
    raise SystemExit(main())
