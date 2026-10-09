"""
Model routing for motion reels (RESTYLE_TO_MOTION_REELS.md, phase 3 review).

shorts/motion_models.yaml names, for every LLM call a motion reel makes (by
its llm.ask_json label), the model to use, plus the numbers behind the
cost estimate printed before a reel starts. The motion runner switches the
routing on for its own run with `use()`; nothing else does, so explainer and
story runs keep config.py's MODEL_* settings untouched.

It also sets each model's REASONING for the run (`reasoning` in the YAML):
thinking on with a budget (required by models that refuse to disable it,
like Opus 5.5 on OpenRouter) or off. The estimate counts thinking tokens, and
`check_models()` (motion_reel --check-models) makes one tiny call per model
to prove the settings are accepted before a reel spends anything.
"""
import contextlib
import re
from functools import lru_cache
from pathlib import Path

import yaml

from . import llm, preflight

PATH = Path(__file__).resolve().parent / "motion_models.yaml"


def _switch(value) -> str:
    """thinking: on / off — YAML reads a bare on/off as a boolean, so accept both."""
    if value is True:
        return "on"
    if value is False:
        return "off"
    return str(value).strip().lower()


@lru_cache(maxsize=1)
def load() -> dict:
    data = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    for r in (data.get("reasoning") or {}).values():
        r["thinking"] = _switch(r.get("thinking"))
    tiers = data.get("models") or {}
    steps = data.get("steps") or {}
    for label, step in steps.items():
        tier = step.get("tier", "")
        if tier not in tiers and "/" not in tier:
            raise ValueError(f"motion_models.yaml: step {label!r} has tier {tier!r}, which is "
                             f"neither one of {sorted(tiers)} nor a model id")
    efforts = data.get("effort_budgets") or {}
    used = {tiers.get(s.get("tier"), s.get("tier")) for s in steps.values()}
    for model in sorted(used):
        r = (data.get("reasoning") or {}).get(model)
        if r is None:
            raise ValueError(f"motion_models.yaml: model {model!r} has no `reasoning` entry "
                             f"(thinking: on with an effort or budget, or thinking: off)")
        if r.get("thinking") not in ("on", "off"):
            raise ValueError(f"motion_models.yaml: {model}: thinking must be on or off, not {r.get('thinking')!r}")
        if r["thinking"] == "on":
            budget = r.get("budget", efforts.get(r.get("effort")))
            if not isinstance(budget, int) or budget < 1024:
                raise ValueError(f"motion_models.yaml: {model}: thinking on needs an effort in "
                                 f"{sorted(efforts)} or a budget of at least 1024 tokens")
    return data


def reasoning_for(model: str) -> dict:
    """{"thinking": "on", "budget": N} or {"thinking": "off", "budget": 0}."""
    data = load()
    r = (data.get("reasoning") or {}).get(model) or {"thinking": "off"}
    if r.get("thinking") != "on":
        return {"thinking": "off", "budget": 0}
    budget = r.get("budget", (data.get("effort_budgets") or {}).get(r.get("effort")))
    return {"thinking": "on", "budget": int(budget)}


def models() -> list[str]:
    """Every distinct model a motion run uses."""
    return sorted({m for m in routes().values() if m})


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
    """Route every routed label to its model, with its reasoning setting, for
    the duration."""
    llm.set_label_models(routes())
    llm.set_model_reasoning({m: reasoning_for(m) for m in models()})
    try:
        yield
    finally:
        llm.set_label_models({})
        llm.set_model_reasoning({})


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
    share = float(load().get("typical_share", 0.6))
    rows = []
    for label, step in (load().get("steps") or {}).items():
        model = model_for(label)
        tin = _tokens(step.get("input", 0), doc_tokens)
        tout = _tokens(step.get("output", 0), doc_tokens)
        think = reasoning_for(model)["budget"]
        # thinking is billed as output: a typical call uses part of its budget,
        # the worst case all of it
        typical_call = preflight.text_cost_per_call(model, tin, tout + round(think * share))
        worst_call = preflight.text_cost_per_call(model, tin, tout + think)
        rows.append({"label": label, "model": model, "thinking": think,
                     "worst_calls": step.get("worst", 0), "typical_calls": step.get("typical", 0),
                     "per_call": round(typical_call, 4), "per_call_worst": round(worst_call, 4),
                     "worst": round(worst_call * step.get("worst", 0), 4),
                     "typical": round(typical_call * step.get("typical", 0), 4)})
    return rows


def print_estimate(rows: list[dict]) -> tuple[float, float]:
    print("\n=== Estimated cost of this motion reel (setup -> playable plan) ===")
    print(f"  {'step':<30} {'model':<30} {'thinking':>8} {'calls':>11} {'$/call':>8} {'typical':>9} {'worst':>9}")
    for r in rows:
        if not r["worst_calls"] and not r["typical_calls"]:
            continue
        think = f"{r['thinking']}" if r["thinking"] else "off"
        print(f"  {r['label']:<30} {r['model']:<30} {think:>8} {r['typical_calls']:>4} - {r['worst_calls']:<4}"
              f" {r['per_call']:>8.4f} {r['typical']:>9.4f} {r['worst']:>9.4f}")
    typical = round(sum(r["typical"] for r in rows), 4)
    worst = round(sum(r["worst"] for r in rows), 4)
    print(f"  {'total':<30} {'':<30} {'':>8} {'':>11} {'':>8} {typical:>9.4f} {worst:>9.4f}")
    print("  thinking = the per-call reasoning budget in tokens (billed as output): typical counts "
          f"{float(load().get('typical_share', 0.6)):.0%} of it, worst all of it.")
    print("  voice (Chatterbox) and timing (forced alignment) run locally: $0.")
    print("  Token sizes are estimates; OpenRouter's billed cost per call is logged as it happens.")
    return typical, worst


# ================================================================ preflight

CHECK_PROMPT = 'Return exactly this JSON and nothing else: {"ok": true}'
CHECK_MAX_TOKENS = 16


def check_models(dry_run: bool = False) -> list[dict]:
    """ONE tiny call per model a motion run uses, with that model's reasoning
    setting, to prove the endpoint accepts the request before a reel spends
    anything. Per model: OK, or the exact error; its cost (OpenRouter's billed
    cost when it reports one). The answer is read as a reel's would be —
    visible text only, thinking skipped — and must parse as {"ok": true}.

    dry_run (stub mode) makes no call: it shows what would be sent and the
    most it could cost."""
    import json as _json
    import time as _time
    from . import usage
    out = []
    with use():
        for model in models():
            r = reasoning_for(model)
            kwargs = llm._reasoning(model, False)
            max_tokens = CHECK_MAX_TOKENS + llm.thinking_budget(model)
            worst = preflight.text_cost_per_call(model, 60, max_tokens)
            row = {"model": model, "thinking": r["thinking"], "budget": r["budget"],
                   "request": kwargs, "max_tokens": max_tokens, "max_cost": round(worst, 4)}
            if dry_run:
                out.append({**row, "status": "DRY RUN", "detail": "no call made (SHORTS_STUB=1)", "cost": 0.0})
                continue
            started = _time.perf_counter()
            try:
                resp = llm.client().messages.create(
                    model=model, max_tokens=max_tokens, system="Reply with raw JSON only.",
                    messages=[{"role": "user", "content": CHECK_PROMPT}], **kwargs)
                call = usage.record("check_models", model, resp, duration_seconds=_time.perf_counter() - started)
                text = llm.visible_text(resp)
                kinds = sorted({getattr(b, "type", "?") for b in resp.content or []})
                try:
                    ok = _json.loads(llm._extract_json(text)) == {"ok": True}
                except ValueError:
                    ok = False
                out.append({**row, "status": "OK" if ok else "UNEXPECTED ANSWER",
                            "detail": f"answer {text.strip()[:80]!r}; blocks {kinds}; "
                                      f"{resp.usage.input_tokens} in / {resp.usage.output_tokens} out",
                            "cost": call.cost if call else 0.0, "estimated": bool(call and call.estimated)})
            except Exception as e:          # noqa: BLE001 — the exact error is the point
                out.append({**row, "status": "ERROR", "detail": f"{type(e).__name__}: {e}", "cost": 0.0})
    return out


def print_check(rows: list[dict]) -> bool:
    print("\n=== Motion model check: one tiny call per model ===")
    for r in rows:
        think = f"thinking on, budget {r['budget']}" if r["thinking"] == "on" else "thinking off"
        cost = f"${r['cost']:.4f}" + (" (estimated)" if r.get("estimated") else "")
        print(f"  {r['status']:<17} {r['model']:<30} {think:<28} {cost}")
        print(f"      sent: max_tokens={r['max_tokens']} {r['request']}")
        print(f"      {r['detail']}")
    total = sum(r["cost"] for r in rows)
    most = sum(r["max_cost"] for r in rows)
    if all(r["status"] == "DRY RUN" for r in rows):
        print(f"  dry run: no call made. Run without SHORTS_STUB=1 to check for real — at most ${most:.4f} in all.")
        return True
    ok = all(r["status"] == "OK" for r in rows)
    print(f"  total ${total:.4f} — {'all models accept their settings' if ok else 'FIX the failing model(s) in shorts/motion_models.yaml'}")
    return ok
