"""
What every step cost, in tokens and dollars.

Generation cost is invisible until it shows up on a bill, and the steps here are
wildly uneven — topic selection is one cheap call, while finalising a single short
is one call per diagram plus an Opus judge call. So every model call is recorded
and the totals are surfaced in the UI.

Cost comes from the provider when it reports one (OpenRouter returns a per-call
`cost` inside `usage`, which is authoritative because it accounts for the actual
model that served the request). When it does not, fall back to a price table.
Estimated rows are marked, so a number is never presented as measured when it
is not.
"""
import json, threading
from dataclasses import dataclass, asdict, field
from pathlib import Path

from . import config

# USD per token. Only used when the provider reports no cost.
PRICES = {
    "claude-opus-5":     (5.0e-6, 25.0e-6),
    "claude-sonnet-5":   (2.0e-6, 10.0e-6),
    "claude-haiku-4.5":  (1.0e-6,  5.0e-6),
    "claude-haiku-4-5":  (1.0e-6,  5.0e-6),
    "claude-opus-4.8":   (5.0e-6, 25.0e-6),
    "claude-fable-5":   (10.0e-6, 50.0e-6),
    # Longest key wins the lookup below, so "gpt-5-mini" is not shadowed by "gpt-5".
    "gpt-5-nano":        (0.05e-6, 0.40e-6),
    "gpt-5-mini":        (0.25e-6, 2.00e-6),
    "gpt-5":             (1.25e-6, 10.0e-6),
    "gemini-3.1-flash-lite": (0.25e-6, 1.50e-6),
    "gemini-3.5-flash-lite": (0.30e-6, 2.50e-6),
    "gemini-2.5-flash-lite": (0.10e-6, 0.40e-6),
}


@dataclass
class Call:
    label: str                  # which pipeline step asked
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    estimated: bool             # True when the price table was used


@dataclass
class Totals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    estimated: bool = False
    by_label: dict = field(default_factory=dict)


_lock = threading.Lock()
_calls: list[Call] = []
STORE = config.OUTPUT_DIR / "usage.json"


def _price(model: str, tin: int, tout: int) -> float:
    # Longest match, not first: "openai/gpt-5-mini" contains both "gpt-5-mini" and
    # "gpt-5", and taking whichever happened to be declared first would have priced
    # the mini model at the full model's rate — a silent 5x overstatement on the
    # only number anyone reads.
    matches = [k for k in PRICES if k in model]
    if not matches:
        return 0.0
    pin, pout = PRICES[max(matches, key=len)]
    return tin * pin + tout * pout


def record(label: str, model: str, resp) -> Call | None:
    """Log one model call. Never raises — accounting must not break generation."""
    try:
        u = getattr(resp, "usage", None)
        if u is None:
            return None
        tin = int(getattr(u, "input_tokens", 0) or 0)
        tout = int(getattr(u, "output_tokens", 0) or 0)

        # Providers can attach fields the SDK does not model; OpenRouter puts the
        # real cost here, which beats any table we keep.
        extra = getattr(u, "model_extra", None) or {}
        reported = extra.get("cost")
        if isinstance(reported, (int, float)) and reported > 0:
            cost, estimated = float(reported), False
        else:
            cost, estimated = _price(model, tin, tout), True

        call = Call(label, model, tin, tout, round(cost, 6), estimated)
        with _lock:
            _calls.append(call)
            _save_locked()
        return call
    except Exception:
        return None


def _sum(calls: list[Call]) -> Totals:
    t = Totals()
    for c in calls:
        t.calls += 1
        t.input_tokens += c.input_tokens
        t.output_tokens += c.output_tokens
        t.cost += c.cost
        t.estimated = t.estimated or c.estimated
        row = t.by_label.setdefault(c.label, {"calls": 0, "tokens": 0, "cost": 0.0})
        row["calls"] += 1
        row["tokens"] += c.input_tokens + c.output_tokens
        row["cost"] = round(row["cost"] + c.cost, 6)
    t.cost = round(t.cost, 6)
    return t


def totals() -> dict:
    with _lock:
        return asdict(_sum(list(_calls)))


def mark() -> int:
    """Cursor for measuring one request's spend."""
    with _lock:
        return len(_calls)


def since(cursor: int) -> dict:
    """Totals for calls made after `cursor` — i.e. what this request cost."""
    with _lock:
        return asdict(_sum(_calls[cursor:]))


def _save_locked() -> None:
    try:
        STORE.write_text(json.dumps(
            {"calls": [asdict(c) for c in _calls], "totals": asdict(_sum(_calls))},
            indent=2))
    except Exception:
        pass


def load() -> None:
    """Carry totals across restarts so the figure on screen is cumulative."""
    if not STORE.exists():
        return
    try:
        data = json.loads(STORE.read_text())
        with _lock:
            _calls.clear()
            _calls.extend(Call(**c) for c in data.get("calls", []))
    except Exception:
        pass


def reset() -> None:
    with _lock:
        _calls.clear()
        _save_locked()
