"""
Step 5 hardening: an adopted voice must not be silently bypassed.

THE BUG THIS CLOSES. providers.get() already honoured a voice adopted in the
Voice Lab UI (voices/settings.json) over the static _PREFERENCE order — but
voice.synthesize(), the function that actually narrates a real short,
iterates providers.chain(), not get(). chain()'s own "auto" branch never
consulted the adopted provider at all; it walked _PREFERENCE
("elevenlabs", "chatterbox", ...) and returned the first one whose
available() was True. An adopted Chatterbox voice was silently skipped in
favour of ElevenLabs the moment ElevenLabs credentials existed for any
reason (leftover from testing another feature, a key added for something
else) — with no warning, because ElevenLabs succeeding was never treated as
a fallback. providers._adopted() is now the one check both get() and chain()
make first.

No API key, no network, no real LLM or TTS calls — every test here
monkeypatches shorts.providers._REGISTRY with fake in-process Provider stubs
and shorts.config.voice_settings, and restores both afterward.

    SHORTS_STUB=1 python -m shorts.voice_provider_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import config, providers


class _Fake(providers.Provider):
    def __init__(self, name, available=True, why="ok"):
        self.name = name
        self._available = available
        self._why = why

    def available(self):
        return self._available, self._why

    def resolve(self):
        return {"interviewer": f"{self.name}-voice"}

    def synth(self, text, voice_id, speaker):
        return b""


def _swap_registry(**providers_by_name):
    """Replace providers._REGISTRY for the duration of one test, and hand
    back a restore function — same pattern judge_gate_test.py and
    step8_hardening_test.py use for monkeypatching module-level state.

    Fills in every name chain()'s fallback loop walks (_PREFERENCE) that the
    caller did not specify with an unavailable stub, so that loop's
    unconditional `_REGISTRY[n]` lookups never KeyError on a name this test
    was not trying to exercise."""
    real_registry = providers._REGISTRY
    real_settings = config.voice_settings
    real_tts_provider = config.TTS_PROVIDER
    real_warned = set(providers._adopted_unavailable_warned)
    fake = dict(providers_by_name)
    for name in providers._PREFERENCE:
        fake.setdefault(name, _Fake(name, available=False, why="not configured in this test"))
    providers._REGISTRY = fake
    providers._adopted_unavailable_warned.clear()

    def restore():
        providers._REGISTRY = real_registry
        config.voice_settings = real_settings
        config.TTS_PROVIDER = real_tts_provider
        providers._adopted_unavailable_warned.clear()
        providers._adopted_unavailable_warned.update(real_warned)

    return restore


def test_chain_prefers_adopted_provider_over_preference_order():
    """The exact bug: elevenlabs is FIRST in _PREFERENCE and available, but
    chatterbox was adopted in the UI. chain() must return chatterbox, not
    fall through to elevenlabs."""
    elevenlabs = _Fake("elevenlabs", available=True)
    chatterbox = _Fake("chatterbox", available=True)
    restore = _swap_registry(elevenlabs=elevenlabs, chatterbox=chatterbox)
    config.voice_settings = lambda: {"provider": "chatterbox"}
    config.TTS_PROVIDER = ""
    try:
        result = providers.chain()
        assert result == [chatterbox], [p.name for p in result]
        print("   ok — chain() returns the adopted chatterbox voice, not "
              "elevenlabs, even though elevenlabs is first in _PREFERENCE "
              "and available")
    finally:
        restore()


def test_get_and_chain_agree_on_the_adopted_provider():
    """Regression guard for the inconsistency itself: get() and chain()
    must never disagree about who the adopted voice is."""
    elevenlabs = _Fake("elevenlabs", available=True)
    chatterbox = _Fake("chatterbox", available=True)
    restore = _swap_registry(elevenlabs=elevenlabs, chatterbox=chatterbox)
    config.voice_settings = lambda: {"provider": "chatterbox"}
    config.TTS_PROVIDER = ""
    try:
        assert providers.get() is chatterbox
        assert providers.chain()[0] is chatterbox
        print("   ok — providers.get() and providers.chain()[0] agree on "
              "the adopted provider")
    finally:
        restore()


def test_chain_falls_back_and_warns_when_adopted_provider_is_unavailable():
    import contextlib, io

    chatterbox = _Fake("chatterbox", available=False, why="worker crashed")
    piper = _Fake("piper", available=True)
    restore = _swap_registry(chatterbox=chatterbox, piper=piper)
    config.voice_settings = lambda: {"provider": "chatterbox"}
    config.TTS_PROVIDER = ""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = providers.chain()
        assert result == [piper], [p.name for p in result]
        printed = buf.getvalue()
        assert "adopted voice provider" in printed and "chatterbox" in printed, printed
        print("   ok — an unavailable adopted provider falls back to the "
              "preference order AND prints why, never silently: "
              f"{printed.strip()[:100]}")
    finally:
        restore()


def test_no_adopted_provider_keeps_preference_order():
    """No adoption at all (fresh install, .env-only) must behave exactly as
    before — the static _PREFERENCE order, untouched."""
    elevenlabs = _Fake("elevenlabs", available=True)
    chatterbox = _Fake("chatterbox", available=True)
    restore = _swap_registry(elevenlabs=elevenlabs, chatterbox=chatterbox)
    config.voice_settings = lambda: {}
    config.TTS_PROVIDER = ""
    try:
        result = providers.chain()
        assert result and result[0] is elevenlabs, [p.name for p in result]
        print("   ok — with nothing adopted, chain() still follows the "
              "ordinary _PREFERENCE order (no behaviour change for the "
              "unconfigured case)")
    finally:
        restore()


def test_explicit_env_provider_still_resolves_through_get():
    """TTS_PROVIDER set explicitly still goes through chain()'s is_explicit
    branch, which calls get() — and get() itself still lets an adopted UI
    voice outrank .env, exactly as its own docstring always promised. This
    only proves chain()'s dispatch did not change for the explicit case."""
    piper = _Fake("piper", available=True)
    restore = _swap_registry(piper=piper)
    config.voice_settings = lambda: {}
    config.TTS_PROVIDER = "piper"
    try:
        result = providers.chain()
        assert result == [piper], [p.name for p in result]
        print("   ok — an explicit TTS_PROVIDER still resolves via "
              "chain()'s is_explicit() branch, unchanged")
    finally:
        restore()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} voice-provider hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL VOICE-PROVIDER HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
