"""
Model routing for motion reels (RESTYLE_TO_MOTION_REELS.md, phase 3 review).

shorts/motion_models.yaml names, for every LLM call a motion reel makes (by
its llm.ask_json label), the model to use, plus the numbers behind the
cost estimate printed before a reel starts. The motion runner switches the
routing on for its own run with `use()`; nothing else does, so explainer and
story runs keep config.py's MODEL_* settings untouched.
"""
import contextlib
import re
from functools import lru_cache
from pathlib import Path

import yaml

from . import llm, preflight

PATH = Path(__file__).resolve().parent / "motion_models.yaml"


@lru_cache(maxsize=1)
def load() -> dict:
    data = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    tiers = data.get("models") or {}
    steps = data.get("steps") or {}
    for label, step in steps.items():
        tier = step.get("tier", "")
        if tier not in tiers and "/" not in tier:
            raise ValueError(f"motion_models.yaml: step {label!r} has tier {tier!r}, which is "
                             f"neither one of {sorted(tiers)} nor a model id")
    return data


def model_for(label: str) -> str | None:
    """The model a motion call with this label uses (None: not routed)."""
    data = load()
    step = (data.get("steps") or {}).get(label)
    if step is None:
        return None
    tier = step["tier"]
    return (data.get("models") or {}).get(tier, tier)


def routes() -> dict[str, str]:
    return {label: model_for(label) for label in (load().get("steps") or {})}


@contextlib.contextmanager
def use():
    """Route every routed label to its model for the duration."""
    llm.set_label_models(routes())
    try:
        yield
    finally:
        llm.set_label_models({})


def _tokens(value, doc_tokens: int) -> int:
    if isinstance(value, int):
        return value
    total = 0
    for part in str(value).split("+"):
        part = part.strip()
        total += doc_tokens if part == "doc" else int(part)
    return total


def estimate(doc_text: str = "") -> list[dict]:
    """Per step: model, worst-case and typical calls and dollars, for a whole
    reel. Token counts are the YAML's rough sizes; `doc` is the document's
    length in tokens (~4 characters each)."""
    doc_tokens = len(doc_text) // 4
    rows = []
    for label, step in (load().get("steps") or {}).items():
        model = model_for(label)
        per_call = preflight.text_cost_per_call(model, _tokens(step.get("input", 0), doc_tokens),
                                                _tokens(step.get("output", 0), doc_tokens))
        rows.append({"label": label, "model": model, "worst_calls": step.get("worst", 0),
                     "typical_calls": step.get("typical", 0), "per_call": round(per_call, 4),
                     "worst": round(per_call * step.get("worst", 0), 4),
                     "typical": round(per_call * step.get("typical", 0), 4)})
    return rows


def print_estimate(rows: list[dict]) -> tuple[float, float]:
    print("\n=== Estimated cost of this motion reel (setup -> playable plan) ===")
    print(f"  {'step':<30} {'model':<30} {'calls':>11} {'$/call':>8} {'typical':>9} {'worst':>9}")
    for r in rows:
        if not r["worst_calls"] and not r["typical_calls"]:
            continue
        print(f"  {r['label']:<30} {r['model']:<30} {r['typical_calls']:>4} - {r['worst_calls']:<4}"
              f" {r['per_call']:>8.4f} {r['typical']:>9.4f} {r['worst']:>9.4f}")
    typical = round(sum(r["typical"] for r in rows), 4)
    worst = round(sum(r["worst"] for r in rows), 4)
    print(f"  {'total':<30} {'':<30} {'':>11} {'':>8} {typical:>9.4f} {worst:>9.4f}")
    print("  voice (Chatterbox) and timing (forced alignment) run locally: $0.")
    print("  Token sizes are estimates; OpenRouter's billed cost per call is logged as it happens.")
    return typical, worst
