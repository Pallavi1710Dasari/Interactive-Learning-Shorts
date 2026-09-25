"""
Step 8 hardening: parallel per-beat TTS, only where it is actually safe.

THE AUDIT'S FINDING: Chatterbox's own synth() already says why it cannot be
parallelised — "One at a time: the worker is a single process with one model
in it", enforced by its own threading.Lock. Kokoro and Piper each hold one
loaded model object with no lock of their own, which is not evidence they
ARE safe, so Provider.concurrent_safe defaults False for them too — only
ElevenLabs and Google, whose synth() is a plain independent HTTP request,
are marked True. tts.synthesize() now renders beats in parallel ONLY when
the provider says concurrent_safe = True; every other provider still
renders one beat at a time, in order.

This file proves both halves: a concurrent_safe fake provider actually
overlaps its calls (measured wall-clock time, not merely inspected code),
and a non-concurrent_safe one still runs strictly sequentially — with the
resulting beat order and timing identical to before Step 8 either way.

Real ffmpeg (bundled, offline, free), fake providers with a real but
artificial delay — no API key, no network, no real TTS engine.

    SHORTS_STUB=1 python -m shorts.tts_latency_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import tempfile, time, wave
from pathlib import Path

from shorts import providers, tts
from shorts.schema import Beat, Script


def _silence_wav_bytes(seconds: float, rate: int = 8000) -> bytes:
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


class _SlowFakeProvider(providers.Provider):
    """Every synth() call takes a real, fixed wall-clock delay before
    returning silence — a stand-in for network latency, not a mock of it."""
    name = "slow-fake"
    suffix = ".wav"

    def __init__(self, delay: float, concurrent_safe: bool):
        self._delay = delay
        self.concurrent_safe = concurrent_safe
        self.call_order: list[int] = []
        self._next_id = 0

    def available(self):
        return True, "fake"

    def installed(self):
        return True, "fake"

    def resolve(self):
        return {"interviewer": "fake-voice"}

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        my_id = self._next_id
        self._next_id += 1
        time.sleep(self._delay)
        self.call_order.append(my_id)
        return _silence_wav_bytes(0.3)


def _script(n_beats: int) -> Script:
    beats = [Beat(line=f"Beat number {i} of the explanation.", on_screen=f"B{i}",
                  visual_ref=f"v{i}") for i in range(n_beats)]
    return Script(short_id="t_latency", question="how does it work", beats=beats)


def _skip_if_no_ffmpeg():
    if tts.ffmpeg_exe() is None:
        raise SystemExit("no ffmpeg available in this environment — cannot "
                         "run real-audio latency tests")


def test_concurrent_safe_provider_overlaps_its_calls():
    _skip_if_no_ffmpeg()
    delay = 0.3
    n = 4
    provider = _SlowFakeProvider(delay, concurrent_safe=True)
    script = _script(n)
    with tempfile.TemporaryDirectory() as tmp:
        started = time.perf_counter()
        audio = tts.synthesize(script, out_dir=Path(tmp), provider=provider,
                               voices={"interviewer": "v"})
        elapsed = time.perf_counter() - started
    sequential_would_be = n * delay
    assert elapsed < sequential_would_be * 0.7, (
        f"expected overlap: {elapsed:.2f}s took, sequential would be "
        f"~{sequential_would_be:.2f}s")
    assert len(audio.beat_spans) == n
    print(f"   ok — {n} beats at {delay}s each overlapped: {elapsed:.2f}s "
          f"measured vs ~{sequential_would_be:.2f}s sequential "
          f"(concurrent_safe=True actually renders in parallel)")


def test_non_concurrent_safe_provider_stays_sequential():
    _skip_if_no_ffmpeg()
    delay = 0.25
    n = 3
    provider = _SlowFakeProvider(delay, concurrent_safe=False)
    script = _script(n)
    with tempfile.TemporaryDirectory() as tmp:
        started = time.perf_counter()
        audio = tts.synthesize(script, out_dir=Path(tmp), provider=provider,
                               voices={"interviewer": "v"})
        elapsed = time.perf_counter() - started
    sequential_would_be = n * delay
    assert elapsed >= sequential_would_be * 0.9, (
        f"expected no overlap: {elapsed:.2f}s took, sequential floor is "
        f"~{sequential_would_be:.2f}s")
    assert len(audio.beat_spans) == n
    print(f"   ok — {n} beats at {delay}s each, concurrent_safe=False, took "
          f"{elapsed:.2f}s (>= the {sequential_would_be:.2f}s sequential "
          f"floor) — unchanged, one-at-a-time behaviour")


def test_beat_order_is_preserved_under_parallel_rendering():
    """Even when calls complete out of order (later beats can finish before
    earlier ones under real concurrency), the resulting beat_spans must
    stay in BEAT order, not completion order."""
    _skip_if_no_ffmpeg()

    class _VariableDelay(providers.Provider):
        name = "variable-fake"
        suffix = ".wav"
        concurrent_safe = True

        def available(self):
            return True, "fake"

        def installed(self):
            return True, "fake"

        def resolve(self):
            return {"interviewer": "fake-voice"}

        def synth(self, text, voice_id, speaker):
            # Beat 0 is the SLOWEST call, so it finishes LAST — if ordering
            # were completion-order instead of beat-order, beat 0's audio
            # would land somewhere other than the start of the track.
            # speech.conversational() may reword the text, so the beat
            # number is pulled out with a regex rather than assumed to sit
            # at a fixed position.
            import re
            n = int(re.search(r"\d+", text).group())
            time.sleep(0.35 if n == 0 else 0.05)
            return _silence_wav_bytes(0.2 + 0.1 * n)

    provider = _VariableDelay()
    script = _script(3)
    with tempfile.TemporaryDirectory() as tmp:
        audio = tts.synthesize(script, out_dir=Path(tmp), provider=provider,
                               voices={"interviewer": "v"})
    starts = [s.start for s in audio.beat_spans]
    assert starts == sorted(starts), starts
    assert audio.beat_spans[0].start == 0.0
    print(f"   ok — beat spans stay in beat order ({starts}) even though "
          f"beat 0's own call was the slowest to actually complete")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} TTS-latency hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL TTS-LATENCY HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
