"""
Step 1 of the first-real-reel review of variable_points_to_value__motion
(job f64077e78448, 2026-10-13), part 1: the caption layout. With characters
on screen the chat has its own zone below them; bubbles sit on their
speaker's side, at most 70 % of the frame wide; motion_caption_layout checks
it on the plan. The fixture is that reel's approved scenes and its old plan
with the real word times (evals/fixtures/motion/variable_points_to_value_*).

    SHORTS_STUB=1 python -m shorts.motion_step1_fixes_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_library as lib, motion_plan_checks
from shorts.motion_scenes import MAX_STILL_SECONDS, longest_still
from shorts.motion_timeline import PLAN_REV, ShotClock, build_plan, shot_timings
from shorts.schema import (MotionCaptionTiming, MotionPlan, MotionScene, MotionSceneAction,
                           MotionSceneObject, MotionScript)

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "evals/fixtures/motion"
SCRIPT = MotionScript.model_validate_json((FIX / "variable_points_to_value_scenes.json").read_text())
OLD_PLAN = json.loads((FIX / "variable_points_to_value_plan_rev1.json").read_text())


def _real_clocks(script: MotionScript) -> list[ShotClock]:
    """The recorded reel's clocks (forced-alignment word times)."""
    by_id = {s["id"]: s for s in OLD_PLAN["shots"]}
    return [ShotClock(id=s.id, start=by_id[s.id]["start"], end=by_id[s.id]["end"],
                      captions=[MotionCaptionTiming(**c) for c in by_id[s.id]["captions"]])
            for s in script.shots]


def _shot(script, sid):
    return next(s for s in script.shots if s.id == sid)


# ===================================================================== CTA

def _plan(script=None, characters=True) -> MotionPlan:
    script = script or SCRIPT
    from shorts.motion_reel import _cast
    return build_plan(script, _real_clocks(script), cast=_cast(script), tags=["#python", "#mentor"],
                      characters=characters, character="cs", host_character="host", design="midnight_lab")


def test_a_new_plan_is_rev_2_and_an_old_one_is_not_checked():
    plan = _plan()
    assert plan.rev == PLAN_REV == 2
    old = MotionPlan(**OLD_PLAN)
    assert old.rev == 1
    for r in motion_plan_checks.run(old):
        assert r.passed and "rev 1" in r.reason, r


def test_caption_layout_passes_the_real_reel_and_catches_breakage():
    plan = _plan()
    r = motion_plan_checks.check_caption_layout(plan)
    assert r.passed, r.reason
    # an object pushed down into the caption zone
    shots = [s.model_copy(update={"objects": [o.model_copy(update={"box": o.box.model_copy(update={"y": 1320.0})})
                                              if o.box else o for o in s.objects]}) if s.id == "s05" else s
             for s in plan.shots]
    bad = motion_plan_checks.check_caption_layout(plan.model_copy(update={"shots": shots}))
    assert not bad.passed and "s05" in bad.reason and "overlaps o2" in bad.reason, bad.reason
    # a caption too long for the chat zone
    long = "word " * 120
    shots = [s.model_copy(update={"captions": [s.captions[0].model_copy(update={"text": long})]}) if s.id == "s03" else s
             for s in plan.shots]
    bad = motion_plan_checks.check_caption_layout(plan.model_copy(update={"shots": shots}))
    assert not bad.passed and "s03" in bad.reason and "needs" in bad.reason, bad.reason


def test_the_bubble_is_at_most_70_percent_wide_and_clear_of_the_characters():
    b = lib.library()["frame"]["chat"]["bubble"]
    ch = lib.library()["frame"]["characters"]
    assert b["max_w"] <= 0.7 * 1080
    assert b["side"] >= round(1080 * 0.06)
    assert b["avatar_gap"] >= 40 and ch["bottom"] + b["avatar_gap"] < b["safe_bottom"]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} step-1 fix tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL STEP-1 FIX TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
