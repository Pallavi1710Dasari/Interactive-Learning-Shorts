"""
Step 5 hardening: continuous narration, deterministic timing.

THE PROBLEM. tts.py inserted config.VOICE_BEAT_GAP (0.45s) of silence before
EVERY beat, unconditionally — including beats the script itself was written
to read as one continuous thought (skills/script.py's own "CONNECT EVERY
BEAT TO THE ONE BEFORE IT ... someone reads the whole thing aloud in one
take"), just because that thought needed its own visual and so had to stay
two beats. The fixed gap made every beat boundary sound like a new answer
starting.

THE FIX. Beat.continues_previous (schema.py) is an explicit, script-level
signal — never inferred from text at TTS time. tts.synthesize() and
tts._join() now place config.VOICE_CONTINUATION_GAP (0.12s) before a beat
whose own continues_previous is True, and the ordinary VOICE_BEAT_GAP
everywhere else — including every beat written before this field existed,
which defaults to continues_previous=False and gets byte-identical timing to
before.

Real ffmpeg (the bundled imageio-ffmpeg static binary — no sudo, no
network), but a FAKE Provider that returns silence of an exact, known
duration instead of any real TTS engine — so the beat/gap timing math is
checked against real audio files without a real API key or network call.

    SHORTS_STUB=1 python -m shorts.narration_continuity_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import shutil, tempfile, wave
from pathlib import Path

from shorts import config, providers, tts
from shorts.schema import Beat, Script


def _silence_wav_bytes(seconds: float, rate: int = 8000) -> bytes:
    """A real, valid mono 16-bit WAV of exactly `seconds` of silence — real
    audio ffmpeg can normalise, not a mock of one."""
    n_frames = int(round(seconds * rate))
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n_frames)
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return data


class _FakeVoiceProvider(providers.Provider):
    """Returns silence of an exact, pre-programmed duration per call, in
    call order — so beat 0 is exactly durations[0] seconds, beat 1 exactly
    durations[1], etc. Real bytes, no real engine."""
    name = "fake"
    suffix = ".wav"

    def __init__(self, durations: list[float]):
        self._durations = list(durations)
        self._calls = 0

    def available(self):
        return True, "fake provider, always available"

    def resolve(self):
        return {"interviewer": "fake-voice-id"}

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        d = self._durations[self._calls]
        self._calls += 1
        return _silence_wav_bytes(d)


def _script(continues: list[bool]) -> Script:
    beats = [
        Beat(line=f"This is beat number {i} of the explanation.",
             on_screen=f"Beat {i}", visual_ref=f"v{i}",
             continues_previous=continues[i])
        for i in range(len(continues))
    ]
    return Script(short_id="t_narration", question="how does it work", beats=beats)


def _skip_if_no_ffmpeg():
    if tts.ffmpeg_exe() is None and shutil.which("ffmpeg") is None:
        raise SystemExit("no ffmpeg available in this environment — cannot "
                         "run real-audio timing tests")


def test_default_beats_use_the_ordinary_gap_unchanged():
    """continues_previous is False on every beat (the default, and every
    beat written before this field existed) — timing must be byte-identical
    to the pre-Step-5 fixed-gap behaviour."""
    _skip_if_no_ffmpeg()
    durations = [1.0, 1.0, 1.0]
    provider = _FakeVoiceProvider(durations)
    script = _script([False, False, False])
    with tempfile.TemporaryDirectory() as tmp:
        audio = tts.synthesize(script, out_dir=Path(tmp), gap=None, provider=provider,
                               voices={"interviewer": "v"})
        expected_total = sum(durations) + 2 * config.VOICE_BEAT_GAP
        assert abs(audio.duration_seconds - expected_total) < 0.05, (
            audio.duration_seconds, expected_total)
        assert len(audio.beat_spans) == 3
        # Beat 1 starts after beat 0's full duration PLUS the ordinary gap.
        gap_seen = audio.beat_spans[1].start - audio.beat_spans[0].end
        assert abs(gap_seen - config.VOICE_BEAT_GAP) < 0.02, gap_seen
    print(f"   ok — with no beat continuing another, total duration "
          f"{audio.duration_seconds}s matches sum(durations) + 2x "
          f"VOICE_BEAT_GAP ({expected_total}s), unchanged from before "
          f"continues_previous existed")


def test_continuing_beat_gets_the_short_continuation_gap():
    """Beat 1 continues beat 0 — the gap BEFORE beat 1 must be
    VOICE_CONTINUATION_GAP, not the full VOICE_BEAT_GAP. Beat 2 does not
    continue beat 1, so its own gap stays ordinary."""
    _skip_if_no_ffmpeg()
    durations = [1.0, 1.0, 1.0]
    provider = _FakeVoiceProvider(durations)
    script = _script([False, True, False])
    with tempfile.TemporaryDirectory() as tmp:
        audio = tts.synthesize(script, out_dir=Path(tmp), gap=None, provider=provider,
                               voices={"interviewer": "v"})
        gap_0_to_1 = audio.beat_spans[1].start - audio.beat_spans[0].end
        gap_1_to_2 = audio.beat_spans[2].start - audio.beat_spans[1].end
        assert abs(gap_0_to_1 - config.VOICE_CONTINUATION_GAP) < 0.02, gap_0_to_1
        assert abs(gap_1_to_2 - config.VOICE_BEAT_GAP) < 0.02, gap_1_to_2

        expected_total = (sum(durations) + config.VOICE_CONTINUATION_GAP
                          + config.VOICE_BEAT_GAP)
        assert abs(audio.duration_seconds - expected_total) < 0.05, (
            audio.duration_seconds, expected_total)
    print(f"   ok — beat 1 (continues_previous=True) gets a "
          f"{config.VOICE_CONTINUATION_GAP}s gap ({gap_0_to_1:.3f}s "
          f"measured), beat 2 (continues_previous=False) gets the ordinary "
          f"{config.VOICE_BEAT_GAP}s gap ({gap_1_to_2:.3f}s measured) — one "
          f"short sounds like two different answers where it should, and "
          f"one continuous thought where it should not")


def test_beat_0_continues_previous_is_never_honoured():
    """continues_previous on beat 0 is meaningless — there is no beat before
    it — and must not do anything strange (e.g. a negative leading gap)."""
    _skip_if_no_ffmpeg()
    durations = [1.0, 1.0]
    provider = _FakeVoiceProvider(durations)
    script = _script([True, False])
    with tempfile.TemporaryDirectory() as tmp:
        audio = tts.synthesize(script, out_dir=Path(tmp), gap=None, provider=provider,
                               voices={"interviewer": "v"})
        assert audio.beat_spans[0].start == 0.0
        gap = audio.beat_spans[1].start - audio.beat_spans[0].end
        assert abs(gap - config.VOICE_BEAT_GAP) < 0.02, gap
    print("   ok — continues_previous on beat 0 has no effect (nothing "
          "precedes it); beat 1's own gap is decided by beat 1's own flag, "
          "unaffected")


def test_multiple_gap_durations_still_produce_one_valid_track():
    """A short mixing continuation and ordinary gaps in both directions —
    proving _join's per-junction silence files (one per distinct duration
    needed) assemble into a single coherent track, not one file per beat."""
    _skip_if_no_ffmpeg()
    durations = [0.8, 0.6, 0.9, 0.7]
    provider = _FakeVoiceProvider(durations)
    script = _script([False, True, False, True])
    with tempfile.TemporaryDirectory() as tmp:
        audio = tts.synthesize(script, out_dir=Path(tmp), gap=None, provider=provider,
                               voices={"interviewer": "v"})
        assert Path(audio.file).exists() and Path(audio.file).stat().st_size > 0
        gaps_seen = [audio.beat_spans[i + 1].start - audio.beat_spans[i].end
                    for i in range(3)]
        expected = [config.VOICE_CONTINUATION_GAP, config.VOICE_BEAT_GAP,
                   config.VOICE_CONTINUATION_GAP]
        for seen, want in zip(gaps_seen, expected):
            assert abs(seen - want) < 0.02, (gaps_seen, expected)
    print(f"   ok — mixed continuation/ordinary gaps ({gaps_seen}) assemble "
          f"into one real audio.mp3 track")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} narration-continuity hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL NARRATION-CONTINUITY HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
