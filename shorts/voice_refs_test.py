"""
RESTYLE_TO_STORY_REELS.md Step 8 Part 1: unit tests for shorts/voice_refs.py —
the --from-kokoro reference-clip seeder.

    SHORTS_STUB=1 python -m shorts.voice_refs_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import shutil
import tempfile
from pathlib import Path

from shorts import config, story_voices, voice_refs

# NEVER point this at the real config.CAST_VOICE_DIR (assets/voices/) —
# under SHORTS_STUB=1, voice_refs.run() writes SILENT stub placeholder
# wavs (story_voices.synth_raw's own STUB branch), and this file's own
# tests deliberately corrupt/overwrite clips to prove --force behavior.
# Running against the real directory would destroy the REAL Kokoro-
# synthesized reference clips voice_refs.py wrote there for real (see this
# step's own reply) the moment this test file runs. Every test below
# monkeypatches config.CAST_VOICE_DIR to a fresh temp directory instead,
# via _isolated_voice_dir(), and restores the real value afterward.
_ORIGINAL_CAST_VOICE_DIR = config.CAST_VOICE_DIR


class _isolated_voice_dir:
    """Context manager: config.CAST_VOICE_DIR -> a fresh temp dir for the
    duration of one test, restored (never deleted — it's a real, valuable
    directory) afterward."""
    def __enter__(self):
        self._tmp = tempfile.mkdtemp(prefix="voice_refs_test_")
        config.CAST_VOICE_DIR = Path(self._tmp)
        return config.CAST_VOICE_DIR

    def __exit__(self, *exc):
        config.CAST_VOICE_DIR = _ORIGINAL_CAST_VOICE_DIR
        shutil.rmtree(self._tmp, ignore_errors=True)


def test_run_writes_one_wav_per_cast_role():
    with _isolated_voice_dir():
        code = voice_refs.run(force=False)
        assert code == 0
        for name in story_voices.CAST_ROLES:
            path = voice_refs._out_path(name)
            assert path.exists(), path
            assert path.stat().st_size > 0
        names = [voice_refs._out_path(n).name for n in story_voices.CAST_ROLES]
    print(f"   ok — --from-kokoro writes a non-empty wav for all "
         f"{len(story_voices.CAST_ROLES)} cast roles: {names}")


def test_run_never_overwrites_without_force():
    with _isolated_voice_dir():
        voice_refs.run(force=False)
        path = voice_refs._out_path("Rahul")
        original_bytes = path.read_bytes()
        original_mtime = path.stat().st_mtime_ns
        path.write_bytes(b"a human-recorded clip would go here")   # simulate a real recording

        voice_refs.run(force=False)
        assert path.read_bytes() == b"a human-recorded clip would go here", (
            "a re-run without --force must never touch an existing clip")
        assert path.stat().st_mtime_ns >= original_mtime
        assert path.read_bytes() != original_bytes
    print("   ok — re-running without --force leaves an existing clip "
         "(simulating a human recording) completely untouched")


def test_force_overwrites_an_existing_clip():
    with _isolated_voice_dir():
        voice_refs.run(force=False)
        path = voice_refs._out_path("Rahul")
        path.write_bytes(b"stale content")

        code = voice_refs.run(force=True)
        assert code == 0
        assert path.read_bytes() != b"stale content"
    print("   ok — --force does overwrite an existing clip")


def test_seeded_clips_are_wired_into_cast_chatterbox_voice_by_default():
    """config.py's own _default_chatterbox_voice discovers CAST_VOICE_DIR
    (whatever it is set to AT CALL TIME, since it re-reads config.
    CAST_VOICE_DIR fresh — matching how it's actually used at real import
    time) — proving the same discovery a fresh process performs, without
    needing to spawn one."""
    with _isolated_voice_dir():
        voice_refs.run(force=False)
        for name in story_voices.CAST_ROLES:
            discovered = config._default_chatterbox_voice(name)
            assert discovered == str(voice_refs._out_path(name)), (name, discovered)
    print("   ok — config._default_chatterbox_voice discovers every clip "
         "voice_refs.py just wrote, by the same path convention")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} voice_refs tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL VOICE_REFS TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
