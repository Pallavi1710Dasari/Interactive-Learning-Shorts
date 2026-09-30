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
    # RESTYLE_TO_STORY_REELS.md Step 9 Fixes round 14: config.py's own note
    # on MODEL_STORY_VISION_JUDGE verified gemini-3.8-flash as "Free of
    # charge" against ai.google.dev's OWN pricing page — true for Google's
    # direct API, but every call in this project goes through OpenRouter
    # (this module's own docstring above), a paid reseller that does NOT
    # pass a model's own free tier through to callers. A real sample stage
    # showed $0.0000 estimated (this table had no entry, so text_cost_
    # per_call's fallback silently assumed free) but $0.0430 actual —
    # OpenRouter's own reported per-call cost (estimated=False rows in
    # output/usage.json), which is authoritative. Fitted here by least-
    # squares regression against 53 real, non-estimated logged calls
    # (input_tokens, output_tokens, cost) — not guessed, not copied from a
    # docs page: it reproduces every sampled real cost to 6 decimal places.
    "gemini-3.8-flash": (0.75e-6, 3.75e-6),
}


@dataclass
class Call:
    label: str                  # which pipeline step asked
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    estimated: bool             # True when the price table was used
    duration_seconds: float = 0.0   # wall clock around the request, see record()


@dataclass
class Totals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    estimated: bool = False
    duration_seconds: float = 0.0
    by_label: dict = field(default_factory=dict)


_lock = threading.Lock()
_calls: list[Call] = []
STORE = config.OUTPUT_DIR / "usage.json"

#: Has the on-disk ledger been read into _calls yet this process?
#:
#: THE LEDGER USED TO RESET DEPENDING ON WHICH COMMAND YOU RAN, which makes the one
#: number anyone checks — what this project has cost — quietly wrong. load() was
#: called in exactly one place, server.py at import. Every other entry point
#: (shorts.run, shorts.redraw, shorts.voice, any one-off script) started with an
#: empty _calls, and the first model call appended to that empty list and then
#: _save_locked() wrote it over usage.json. One CLI build therefore replaced the
#: whole history with its own handful of calls, silently, and the web UI went on
#: showing the pre-CLI total from memory until it was restarted.
#:
#: So loading is no longer something a caller has to remember. record() reads the
#: ledger before its first append, which no entry point can forget to do.
_loaded = False


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


def record(label: str, model: str, resp, duration_seconds: float = 0.0) -> Call | None:
    """Log one model call. Never raises — accounting must not break generation.

    duration_seconds is wall clock around the actual API request, timed at the
    call site in llm.py (perf_counter, not measured here — by the time resp
    exists the clock has already stopped). It defaults to 0.0 rather than being
    required so a caller that hasn't been updated yet — or a future call site
    someone adds without threading timing through — still records tokens and
    cost instead of raising, matching the "never raises" contract this whole
    function exists to keep.
    """
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

        call = Call(label, model, tin, tout, round(cost, 6), estimated,
                    round(float(duration_seconds), 3))
        with _lock:
            _load_locked()
            _calls.append(call)
            _save_locked()
        return call
    except Exception:
        return None


def record_image(label: str, model: str, cost: float, estimated: bool = True,
                 duration_seconds: float = 0.0) -> Call | None:
    """
    record()'s counterpart for shorts/imagegen.py — an image call has no
    token count, only a flat per-image price (or exactly $0.0 for a cache
    hit or the stub provider), so it cannot go through record()'s
    usage.input_tokens/output_tokens path at all. Same ledger (this function
    appends to the same _calls list record() does, so totals()/since()
    aggregate image and text calls together without either caller needing to
    know which kind the other was), same "never raises" contract.

    `estimated` mirrors record()'s own field: True for a real provider call
    (Gemini/Cloudflare report no per-call cost the way OpenRouter does for
    text — see config.IMAGE_COST_PER_CALL's own note), False for a cache hit
    or the stub provider, where $0.0 is not an estimate, it is the actual cost.
    """
    try:
        call = Call(label, model, 0, 0, round(float(cost), 6), estimated,
                    round(float(duration_seconds), 3))
        with _lock:
            _load_locked()
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
        t.duration_seconds += c.duration_seconds
        row = t.by_label.setdefault(
            c.label, {"calls": 0, "tokens": 0, "cost": 0.0, "duration_seconds": 0.0})
        row["calls"] += 1
        row["tokens"] += c.input_tokens + c.output_tokens
        row["cost"] = round(row["cost"] + c.cost, 6)
        row["duration_seconds"] = round(row["duration_seconds"] + c.duration_seconds, 3)
    t.cost = round(t.cost, 6)
    t.duration_seconds = round(t.duration_seconds, 3)
    return t


def totals() -> dict:
    with _lock:
        return asdict(_sum(list(_calls)))


def mark() -> int:
    """Cursor for measuring one request's spend.

    IT LOADS THE LEDGER FIRST, and that is not housekeeping. The cursor is an index
    into _calls, and record() fills _calls lazily — so marking before anything had
    been recorded returned 0, the first record() then loaded the whole history
    behind it, and since(0) reported EVERY call ever made as the cost of this one
    request. Measured: a two-token ping billed at $11.71.

    server.py happened to be immune because it calls load() at import. Nothing else
    was, and the ledger's own note ("record() loads lazily too, so every other entry
    point is covered") was wrong about exactly this one.
    """
    with _lock:
        _load_locked()
        return len(_calls)


def since(cursor: int) -> dict:
    """Totals for calls made after `cursor` — i.e. what this request cost."""
    with _lock:
        return asdict(_sum(_calls[cursor:]))


def calls_since(cursor: int) -> list[dict]:
    """RESTYLE_TO_STORY_REELS.md Step 9 — the RAW per-call records after
    `cursor`, each with its own `model` — since()'s own Totals.by_label
    aggregates by LABEL, not by model, and shorts/story_reel.py's report
    stage needs a genuine per-model breakdown (a story reel's "mapping"
    label and "shots" label can both use the same MODEL_GENERATOR, but a
    report reader wants to see total spend BY MODEL as its own axis)."""
    with _lock:
        return [asdict(c) for c in _calls[cursor:]]


def _save_locked() -> None:
    try:
        STORE.write_text(json.dumps(
            {"calls": [asdict(c) for c in _calls], "totals": asdict(_sum(_calls))},
            indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_locked() -> None:
    """Read the ledger once per process. Caller holds _lock."""
    global _loaded
    if _loaded:
        return
    _loaded = True                     # set first: a failed read must not retry per call
    if not STORE.exists():
        return
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        _calls.clear()
        _calls.extend(Call(**c) for c in data.get("calls", []))
    except Exception:
        pass


def load() -> None:
    """Carry totals across restarts so the figure on screen is cumulative.

    Kept for server.py, which wants the totals available before the first call is
    made so /api/usage is correct on a fresh boot. record() now loads lazily too, so
    every other entry point is covered without calling this.
    """
    with _lock:
        _load_locked()


def reset() -> None:
    global _loaded
    with _lock:
        _loaded = True                 # an explicit reset must not be re-hydrated
        _calls.clear()
        _save_locked()
