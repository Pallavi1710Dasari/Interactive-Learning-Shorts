"""
RESTYLE_TO_STORY_REELS.md Step 8 Part 1: unit tests for shorts/story_voices.py's
Chatterbox -> Kokoro fallback (resolve_provider / resolution_summary / synth_raw's
runtime-failure leg).

No API key. Most of this runs under SHORTS_STUB=1; the two tests that need to
see synth_raw's REAL (non-stub) code path monkeypatch story_voices._synth_with
itself, so no real Kokoro/Chatterbox call ever happens here either — that real
coverage already exists in story_audio_test.py and the Step 7 voice_audition
run (see this step's own reply).

    SHORTS_STUB=1 python -m shorts.story_voices_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import io
import contextlib

from shorts import config, story_voices


def test_resolve_provider_passes_kokoro_through_unchanged():
    assert story_voices.resolve_provider("Rahul", "kokoro") == "kokoro"
    print("   ok — a kokoro request resolves to kokoro (nothing to fall back from)")


def test_resolve_provider_falls_back_when_chatterbox_not_installed():
    original = config.CHATTERBOX_PYTHON
    config.CHATTERBOX_PYTHON = "/no/such/interpreter"
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            resolved = story_voices.resolve_provider("Rahul", "chatterbox")
    finally:
        config.CHATTERBOX_PYTHON = original

    assert resolved == "kokoro"
    assert "not installed" in buf.getvalue() and "Rahul" in buf.getvalue()
    print(f"   ok — chatterbox not installed -> resolves to kokoro, logged: "
         f"{buf.getvalue().strip()!r}")


def test_resolve_provider_falls_back_when_no_clip_for_this_character():
    original = dict(config.CAST_CHATTERBOX_VOICE)
    config.CAST_CHATTERBOX_VOICE["Riya"] = ""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            resolved = story_voices.resolve_provider("Riya", "chatterbox")
    finally:
        config.CAST_CHATTERBOX_VOICE.clear()
        config.CAST_CHATTERBOX_VOICE.update(original)

    assert resolved == "kokoro"
    assert "no chatterbox reference clip" in buf.getvalue() and "Riya" in buf.getvalue()
    print(f"   ok — chatterbox installed but no clip for THIS character -> "
         f"resolves to kokoro, logged: {buf.getvalue().strip()!r}")


def test_resolve_provider_uses_chatterbox_when_actually_configured():
    """A REAL check against this machine's own state — voice_refs.py has
    seeded assets/voices/<name>.wav for all 4 characters this step (see the
    reply), so config.CAST_CHATTERBOX_VOICE's own auto-discovered default
    should have a real, existing clip for every role right now. Skips
    cleanly (rather than failing) if that seeding hasn't happened in
    whatever environment this runs in."""
    status = story_voices.list_chatterbox_status()
    if not status["installed"]:
        print(f"   skipped — chatterbox not installed here: {status['reason']}")
        return
    if not status["configured"].get("Rahul"):
        print("   skipped — no chatterbox clip configured for Rahul here "
             "(run `python -m shorts.voice_refs --from-kokoro` first)")
        return
    resolved = story_voices.resolve_provider("Rahul", "chatterbox")
    assert resolved == "chatterbox"
    print("   ok — chatterbox installed AND a real clip is configured -> "
         "resolves to chatterbox (no fallback)")


def test_resolution_summary_matches_resolve_provider_per_character():
    original = dict(config.CAST_CHATTERBOX_VOICE)
    config.CAST_CHATTERBOX_VOICE["Rahul"] = ""   # force Rahul to fall back
    try:
        summary = story_voices.resolution_summary("chatterbox")
        for name in story_voices.CAST_ROLES:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                expected = story_voices.resolve_provider(name, "chatterbox")
            assert summary[name] == expected, (name, summary[name], expected)
    finally:
        config.CAST_CHATTERBOX_VOICE.clear()
        config.CAST_CHATTERBOX_VOICE.update(original)
    print(f"   ok — resolution_summary agrees with resolve_provider for every "
         f"role, including a forced fallback (Rahul): {summary}")


def test_resolution_summary_prints_nothing():
    """resolution_summary is the READ-ONLY, upfront-print-once variant —
    calling it must never itself print a fallback line (story_audio.run()
    prints its own summary from the returned dict instead)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        story_voices.resolution_summary("chatterbox")
    assert buf.getvalue() == ""
    print("   ok — resolution_summary makes zero prints of its own")


def test_synth_raw_falls_back_to_kokoro_when_chatterbox_synth_raises():
    """The THIRD fallback leg — resolve_provider said 'try chatterbox' (it
    IS installed and configured), but the real call itself fails (worker
    crash / timeout) — synth_raw must catch that and retry with kokoro
    rather than raising and aborting the whole reel."""
    original_stub = config.STUB
    original_synth_with = story_voices._synth_with
    original_resolve = story_voices.resolve_provider
    config.STUB = False
    story_voices.resolve_provider = lambda character, tts_provider=None: "chatterbox"

    calls = []

    def fake_synth_with(tts_provider, character, text, emotion):
        calls.append(tts_provider)
        if tts_provider == "chatterbox":
            raise RuntimeError("worker crashed")
        return b"fake-kokoro-wav-bytes"

    story_voices._synth_with = fake_synth_with
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = story_voices.synth_raw("Rahul", "hello", "neutral", "chatterbox")
    finally:
        config.STUB = original_stub
        story_voices._synth_with = original_synth_with
        story_voices.resolve_provider = original_resolve

    assert calls == ["chatterbox", "kokoro"], calls
    assert result == b"fake-kokoro-wav-bytes"
    assert "falling back to kokoro" in buf.getvalue()
    print(f"   ok — a chatterbox call that raises at synth time is caught and "
         f"retried with kokoro, never propagated: calls={calls}")


def test_synth_raw_does_not_swallow_a_kokoro_failure():
    """The fallback is Chatterbox -> Kokoro ONLY — a kokoro call itself
    failing has nowhere further to fall back to and must raise normally."""
    original_stub = config.STUB
    original_synth_with = story_voices._synth_with
    original_resolve = story_voices.resolve_provider
    config.STUB = False
    story_voices.resolve_provider = lambda character, tts_provider=None: "kokoro"

    def raising(tts_provider, character, text, emotion):
        raise RuntimeError("kokoro model exploded")

    story_voices._synth_with = raising
    try:
        try:
            story_voices.synth_raw("Rahul", "hello", "neutral", "kokoro")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "kokoro model exploded" in str(e)
    finally:
        config.STUB = original_stub
        story_voices._synth_with = original_synth_with
        story_voices.resolve_provider = original_resolve
    print("   ok — a kokoro failure propagates normally (no further fallback exists)")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} story_voices tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL STORY_VOICES TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
