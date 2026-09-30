"""
Per-character voice resolution and synthesis — RESTYLE_TO_STORY_REELS.md
Step 7 Part 1.

WHY THIS IS A SEPARATE MODULE FROM shorts/providers.py's Provider classes,
NOT A NEW Provider SUBCLASS. tts.py's synthesize()/Provider.resolve() are
built around a FIXED 2-SLOT shape (interviewer/student — see
Provider.resolve's own docstring, "speaker -> voice id", always exactly two
keys). Story mode has FOUR roles (Rahul/Riya/System/Narrator, config.CAST),
and per-shot EMOTION has to reach all the way down to the delivery
parameters (Kokoro's `speed`, Chatterbox's `exaggeration`/`cfg_weight`) —
neither fits the interviewer/student shape without distorting it. So this
module talks to the underlying engines directly: kokoro_onnx.Kokoro.create()
for Kokoro (bypassing providers.Kokoro.synth()'s own fixed asking/explaining
speed skew), and providers.Chatterbox.synth()'s new per-call
exaggeration/cfg_weight kwargs (Step 7's own small addition to that class)
for Chatterbox.
"""
import io
import wave
from pathlib import Path

import numpy as np

from . import config, providers

#: config.CAST's four roles, in the fixed order everything else in story
#: mode uses (config.CAST itself, CAST_LOOK, MASCOT_POSE's own cast).
CAST_ROLES = ("Rahul", "Riya", "System", "Narrator")


class VoiceError(RuntimeError):
    """A configured voice (id or clip) does not exist, or a required TTS
    engine isn't usable at all — always raised with enough detail to fix it
    (which character, which provider, what was tried)."""


def list_kokoro_voices() -> list[str]:
    """Every voice id in THIS MACHINE'S installed Kokoro catalogue —
    kokoro_onnx has no fixed/hardcoded voice list (see providers.Kokoro.
    voices()'s own note); this is the only authoritative source."""
    kokoro = providers._REGISTRY["kokoro"]
    return kokoro.voices()


def list_chatterbox_status() -> dict:
    """Whether Chatterbox itself is installed/runnable, and which of the 4
    characters currently have a reference clip configured — does NOT start
    the (slow, ~158s-to-load) worker process; this only checks paths."""
    cb = providers._REGISTRY["chatterbox"]
    installed, reason = cb.installed()
    clips = {name: config.CAST_CHATTERBOX_VOICE.get(name, "") for name in CAST_ROLES}
    return {
        "installed": installed,
        "reason": reason,
        "clips": clips,
        "configured": {name: bool(clip) and Path(clip).exists()
                      for name, clip in clips.items()},
    }


def resolve_provider(character: str, tts_provider: str | None = None) -> str:
    """
    The provider that will ACTUALLY be used to voice `character` —
    RESTYLE_TO_STORY_REELS.md Step 8 Part 1's own carry-over rule:
    TTS_PROVIDER_STORY defaults to "chatterbox", but falls back to Kokoro
    AUTOMATICALLY, per character, whenever Chatterbox is not installed or
    has no reference clip configured for that specific character — logging
    which provider is actually about to run either way, never silently.

    A request for "kokoro" (or any provider other than "chatterbox") passes
    through unchanged — there is nothing to fall back FROM. The "chatterbox
    call fails at synth time" leg of the carry-over rule is handled by
    synth_raw itself (this function only answers "would it even be worth
    trying"), not here — a worker crash is only discoverable by attempting
    the call.
    """
    tts_provider = (tts_provider or config.TTS_PROVIDER_STORY).strip().lower()
    if tts_provider != "chatterbox":
        return tts_provider

    status = list_chatterbox_status()
    if not status["installed"]:
        print(f"  voice: chatterbox not installed ({status['reason']}) — "
             f"falling back to kokoro for {character}")
        return "kokoro"
    if not status["configured"].get(character):
        print(f"  voice: no chatterbox reference clip configured for "
             f"{character} — falling back to kokoro")
        return "kokoro"
    return "chatterbox"


def resolution_summary(tts_provider: str | None = None) -> dict[str, str]:
    """{character: actual_provider} for every CAST role — the SAME decision
    resolve_provider() makes, but read-only (no per-call fallback log line),
    for a caller that wants to print the whole cast's resolution ONCE,
    upfront, before any synthesis happens (see story_audio.run())."""
    tts_provider = (tts_provider or config.TTS_PROVIDER_STORY).strip().lower()
    if tts_provider != "chatterbox":
        return {name: tts_provider for name in CAST_ROLES}
    status = list_chatterbox_status()
    if not status["installed"]:
        return {name: "kokoro" for name in CAST_ROLES}
    return {name: ("chatterbox" if status["configured"].get(name) else "kokoro")
           for name in CAST_ROLES}


def voice_for(character: str, tts_provider: str | None = None) -> str:
    """The configured voice id (Kokoro) or reference clip path (Chatterbox)
    for `character` — never validated here (see validate_cast_voices);
    just the lookup."""
    tts_provider = (tts_provider or config.TTS_PROVIDER_STORY).strip().lower()
    if tts_provider == "kokoro":
        return config.CAST_KOKORO_VOICE.get(character, "")
    if tts_provider == "chatterbox":
        return config.CAST_CHATTERBOX_VOICE.get(character, "")
    raise VoiceError(f"unknown TTS_PROVIDER_STORY {tts_provider!r} — "
                     f"must be 'kokoro' or 'chatterbox'")


def validate_cast_voices(tts_provider: str | None = None) -> None:
    """
    Verify every one of the 4 cast roles maps to a voice that ACTUALLY
    EXISTS — Step 7 Part 1's own "verify every mapped id exists; fail
    clearly if not" rule. Raises VoiceError naming every problem at once,
    not just the first.

    Kokoro: checked against list_kokoro_voices() — this machine's real
    installed catalogue, not a guessed/hardcoded list.
    Chatterbox: checked as a real, existing, non-empty file path (a
    cloning provider has no catalogue to check an id against — see
    providers.Chatterbox's own docstring).
    """
    tts_provider = (tts_provider or config.TTS_PROVIDER_STORY).strip().lower()
    problems = []

    if tts_provider == "kokoro":
        catalogue = set(list_kokoro_voices())
        for name in CAST_ROLES:
            vid = config.CAST_KOKORO_VOICE.get(name, "")
            if not vid:
                problems.append(f"{name}: no Kokoro voice id configured (CAST_KOKORO_VOICE)")
            elif vid not in catalogue:
                problems.append(f"{name}: {vid!r} is not in the installed Kokoro "
                                f"catalogue ({len(catalogue)} voices)")
    elif tts_provider == "chatterbox":
        cb_status = list_chatterbox_status()
        if not cb_status["installed"]:
            raise VoiceError(f"chatterbox is not usable at all: {cb_status['reason']}")
        for name in CAST_ROLES:
            clip = config.CAST_CHATTERBOX_VOICE.get(name, "")
            if not clip:
                problems.append(f"{name}: no Chatterbox reference clip configured "
                                f"(CAST_CHATTERBOX_VOICE)")
            elif not Path(clip).exists():
                problems.append(f"{name}: reference clip {clip!r} does not exist")
    else:
        raise VoiceError(f"unknown TTS_PROVIDER_STORY {tts_provider!r} — "
                         f"must be 'kokoro' or 'chatterbox'")

    if problems:
        raise VoiceError(f"invalid story-mode voice configuration ({tts_provider}): "
                         + "; ".join(problems))


def _pcm16_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """float32 [-1, 1] samples -> a 16-bit mono PCM WAV, as bytes."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16.tobytes())
    return buf.getvalue()


def silent_wav_bytes(duration: float, sample_rate: int = 24000) -> bytes:
    """A silent WAV of exactly `duration` seconds — SHORTS_STUB=1's stand-in
    for real synthesis (Step 7's own "stub TTS writes a silent WAV of the
    estimated length" rule)."""
    n = max(1, round(duration * sample_rate))
    return _pcm16_wav_bytes(np.zeros(n, dtype=np.float32), sample_rate)


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getnframes() / w.getframerate()


def _synth_with(tts_provider: str, character: str, text: str, emotion: str) -> bytes:
    """One real synthesis call against a KNOWN provider — no fallback logic,
    no STUB check; synth_raw (below) is the only caller."""
    delivery = config.emotion_delivery(emotion)
    voice = voice_for(character, tts_provider)

    if tts_provider == "kokoro":
        kokoro_provider = providers._REGISTRY["kokoro"]
        model = kokoro_provider._load()
        samples, sample_rate = model.create(text, voice=voice,
                                            speed=delivery["kokoro_speed"],
                                            lang=config.KOKORO_LANG)
        return _pcm16_wav_bytes(np.asarray(samples), sample_rate)

    if tts_provider == "chatterbox":
        cb = providers._REGISTRY["chatterbox"]
        return cb.synth(text, voice, character,
                        exaggeration=delivery["chatterbox_exaggeration"],
                        cfg_weight=delivery["chatterbox_cfg_weight"])

    raise VoiceError(f"unknown TTS_PROVIDER_STORY {tts_provider!r}")


def synth_raw(character: str, text: str, emotion: str,
             tts_provider: str | None = None) -> bytes:
    """
    Real synthesis (or, under SHORTS_STUB=1, a silent WAV of the estimated
    length) for ONE line, in `character`'s voice, delivered per `emotion` —
    NO CACHING here (see story_audio.py's own cache, which wraps this).

    Talks to the underlying engine directly rather than through
    providers.Kokoro.synth()/Chatterbox.synth()'s fixed 2-slot shape — see
    this module's own top docstring for why.

    RESTYLE_TO_STORY_REELS.md Step 8 Part 1's fallback carry-over, all three
    legs: resolve_provider() already falls back to Kokoro when Chatterbox
    isn't installed or has no clip for this character (logged there); this
    function additionally catches a Chatterbox call that IS attempted but
    actually FAILS (worker crash, timeout, bad clip at synth time) and
    retries once with Kokoro, logging the failure — a real-audio call site
    must never simply raise and abort the whole reel over one flaky call
    when a free, local, always-available fallback exists.
    """
    if config.STUB:
        from .schema import WORDS_PER_SECOND
        words = len(text.split())
        duration = max(0.6, words / WORDS_PER_SECOND + 0.3)
        return silent_wav_bytes(duration)

    tts_provider = resolve_provider(character, tts_provider)
    try:
        return _synth_with(tts_provider, character, text, emotion)
    except VoiceError:
        raise
    except Exception as e:
        if tts_provider != "chatterbox":
            raise
        print(f"  voice: chatterbox synth failed for {character} ({e}) — "
             f"falling back to kokoro")
        return _synth_with("kokoro", character, text, emotion)
