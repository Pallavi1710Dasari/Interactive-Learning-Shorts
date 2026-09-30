"""
Pre-flight cost summary — RESTYLE_TO_STORY_REELS.md Step 8 Part 0 #4.

Before any REAL (cost-incurring, non-dry-run) run of a story-mode job — the
"story" job (skills.script.plan_story_mapping / write_story_shots / the
metaphor judge, run.py's build_one_story), the "frames" job
(shorts/story_frames.py's image generation + vision judge), or the
"cast_sheets" job (shorts/cast_sheets.py's candidate character art) — print
every model that job will use, the WORST-CASE planned call count per model
(the same "worst case, not the usually-lower real number" framing
story_frames.py's own pre-Step-8 cost print already used), and the
estimated cost per model and in total; then require --yes, the same gate
every one of those three CLIs already had its own copy of before this
module existed.

Also persist the plan to output/<short_id>/preflight.json, MERGED by job
name (not overwritten) — a reel commonly runs "story" today and "frames"
tomorrow, and the second run's pre-flight record must not erase the first's.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from . import config
from . import usage as usage_mod


@dataclass
class ModelPlan:
    """One model's worst-case usage within a single job."""
    label: str            # e.g. "story_mapping", "story_judge", "image:gemini"
    model: str
    planned_calls: int
    cost_per_call: float

    @property
    def cost(self) -> float:
        return round(self.planned_calls * self.cost_per_call, 4)

    def to_dict(self) -> dict:
        return {"label": self.label, "model": self.model,
               "planned_calls": self.planned_calls,
               "cost_per_call": round(self.cost_per_call, 4), "cost": self.cost}


def text_cost_per_call(model: str, est_input_tokens: int, est_output_tokens: int) -> float:
    """
    A worst-case $/call estimate for one text/vision LLM call, BEFORE the
    call happens — the same price table usage.py's own _price() falls back
    to when a provider reports no per-call cost (see usage.PRICES), applied
    here as a planning number instead of an after-the-fact one.

    A model with NO price-table entry estimates $0.0 here — that used to be
    treated as "the truth for a genuinely free model" for MODEL_STORY_
    VISION_JUDGE's gemini-3.8-flash specifically, which is WRONG (STEP 9
    FIXES ROUND 14): Google's own pricing page lists it free, but every
    call here goes through OpenRouter (usage.py's own module docstring),
    which bills its own real rate regardless of a model's direct-API free
    tier — confirmed by a real sample stage showing $0.0000 estimated but
    $0.0430 actual. gemini-3.8-flash now has a real (regression-fitted from
    actual billed calls) entry in usage.PRICES, so this no longer applies
    to it — but the lesson generalizes: a $0.0 estimate here means "no
    price-table entry", never "confirmed free", for ANY model reached
    through a paid gateway. Add a real entry rather than trusting the
    silence.
    """
    return usage_mod._price(model, est_input_tokens, est_output_tokens)


def build_plan(job: str, short_id: str, usages: list[ModelPlan]) -> dict:
    total = round(sum(u.cost for u in usages), 4)
    return {"job": job, "short_id": short_id,
           "models": [u.to_dict() for u in usages], "total_cost": total}


def print_plan(plan: dict) -> None:
    print(f"\n=== Pre-flight: {plan['job']} ({plan['short_id']}) ===")
    for m in plan["models"]:
        print(f"  {m['label']}: {m['model']} x {m['planned_calls']} call(s) "
             f"@ ${m['cost_per_call']:.4f} = ${m['cost']:.4f}")
    print(f"  Total estimated cost: ${plan['total_cost']:.4f}")


def _preflight_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "preflight.json"


def write_preflight_json(short_id: str, plan: dict, path: Path | None = None) -> Path:
    """Merge `plan` into output/<short_id>/preflight.json under its own job
    name, keeping any other job's plan already recorded there.

    `path` overrides the reel-scoped default — cast_sheets.py's job has no
    single short_id to scope to (a cast sheet is shared across every reel,
    not built per-reel), so it points this at its own shared
    output/cast_candidates/preflight.json instead.
    """
    path = _preflight_path(short_id) if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing[plan["job"]] = plan
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return path


def run_preflight(job: str, short_id: str, usages: list[ModelPlan], yes: bool,
                  path: Path | None = None) -> bool:
    """Print + persist the plan, then gate on --yes — the one call site every
    job's CLI makes. Returns True iff the caller should proceed."""
    plan = build_plan(job, short_id, usages)
    print_plan(plan)
    written = write_preflight_json(short_id, plan, path=path)
    print(f"  wrote {written}")
    if not yes:
        print("Re-run with --yes to proceed.")
        return False
    return True
