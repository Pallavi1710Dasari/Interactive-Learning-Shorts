"""
Word timestamps for motion captions (RESTYLE_TO_MOTION_REELS.md phase 3).

Karaoke captions light each word as it is spoken (addendum 4.4), so every
caption word needs its real time in the audio. Three sources, best first,
all free and local:

  1. forced_alignment — wav2vec2 + torchaudio.functional.forced_align on the
     clip, against the words we KNOW were said (shorts/motion_align_worker.py,
     a resident process in venv-chatterbox);
  2. whisper — faster-whisper's word boundaries paired with the known words,
     when the counts match (story_audio's method);
  3. even — the caption's measured length split evenly. Stub mode always
     uses this (the audio is silence), and it is the last resort otherwise.

Each caption records which one it got (MotionCaptionTiming.source), and the
plan records the weakest, so a reel timed by guesswork says so.
"""
import json
import subprocess
import threading
import time
from pathlib import Path

from . import config


class _Worker:
    """The resident aligner, started once on first use (loading wav2vec2
    takes seconds, not minutes, but there is no reason to pay it per clip)."""

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self.error: str | None = None

    def _ensure(self):
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if self.error:
            return None
        python = config.CHATTERBOX_PYTHON
        if not Path(python).exists():
            self.error = f"{python} not found (the aligner runs in venv-chatterbox)"
            return None
        proc = subprocess.Popen([python, "-m", "shorts.motion_align_worker"], cwd=str(config.ROOT),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, bufsize=1)
        ready = self._read(proc, 600.0)
        if not ready.get("ok"):
            proc.kill()
            self.error = ready.get("error", "no reply")
            return None
        self._proc = proc
        return proc

    @staticmethod
    def _read(proc, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                return {"ok": False, "error": "aligner exited"}
            try:
                return json.loads(line)
            except ValueError:
                continue
        return {"ok": False, "error": f"no reply within {timeout:.0f}s"}

    def align(self, wav: Path, words: list[str]) -> list | None:
        with self._lock:
            proc = self._ensure()
            if proc is None:
                return None
            proc.stdin.write(json.dumps({"wav": str(wav), "words": words}) + "\n")
            proc.stdin.flush()
            reply = self._read(proc, 120.0)
        if not reply.get("ok"):
            self.error = reply.get("error")
            return None
        return reply["times"]

    def close(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None


_WORKER = _Worker()


def _fill(times: list, duration: float) -> list[tuple[float, float]] | None:
    """Interpolate the words the aligner could not place (no letters: "—")
    between their neighbours; None when it placed none at all."""
    if not any(times):
        return None
    out: list = list(times)
    n = len(out)
    for i in range(n):
        if out[i] is None:
            prev_end = next((out[j][1] for j in range(i - 1, -1, -1) if out[j]), 0.0)
            nxt = next((out[j][0] for j in range(i + 1, n) if out[j]), duration)
            out[i] = [prev_end, max(prev_end, nxt)]
    return [(float(a), float(b)) for a, b in out]


def _whisper(wav: Path, text: str) -> list[tuple[float, float]] | None:
    from .story_audio import _whisper_words
    words = _whisper_words(wav, text)
    return [(w.start, w.end) for w in words] if words else None


def align_clip(wav: Path, spoken: str, duration: float) -> tuple[list[tuple[float, float]] | None, str]:
    """Each SPOKEN word's (start, end) in `wav`, and the source. None times
    (and "even") under SHORTS_STUB=1 or when both aligners fail."""
    words = spoken.split()
    if config.STUB or not words:
        return None, "even"
    times = _WORKER.align(wav, words)
    if times is not None and len(times) == len(words):
        filled = _fill(times, duration)
        if filled:
            return filled, "forced_alignment"
    w = _whisper(wav, spoken)
    if w is not None and len(w) == len(words):
        return w, "whisper"
    return None, "even"


def shown_times(spoken_times: list[tuple[float, float]] | None,
                ranges: list[tuple[int, int]]) -> list[tuple[float, float]] | None:
    """Caption (shown) word times from spoken word times: a shown word that
    stands for several spoken words (`useState` <- "use State") spans them."""
    if spoken_times is None:
        return None
    out = []
    for a, b in ranges:
        if a >= len(spoken_times):
            last = spoken_times[-1][1]
            out.append((last, last))
            continue
        out.append((spoken_times[a][0], spoken_times[max(a, b - 1)][1]))
    return out


def close() -> None:
    _WORKER.close()
