"""
Step 1 of the first-real-reel review of variable_points_to_value__motion
(job f64077e78448, 2026-10-13): the caption layout, and the CTA timing
failure and its cause. The CTA held still 2.6 s (motion_change_cadence): the
end card is now cued on its words, and on the real clock any still stretch in
ANY template gets a word-cued action (motion_tidy.fill_cadence). The fixture
is that reel's approved scenes and its old plan with the real word times
(evals/fixtures/motion/variable_points_to_value_*).

    SHORTS_STUB=1 python -m shorts.motion_step1_fixes_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_library as lib, motion_plan_checks, motion_tidy
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

def test_the_real_cta_held_still_and_now_does_not():
    """The real run's failure, reproduced on its own word times: s10 held
    still 2.6 s from 1.5 s in. Cued on its words, it moves at least every 2.5 s."""
    clocks = {c.id: c for c in _real_clocks(SCRIPT)}
    cta = _shot(SCRIPT, "s10")
    gap, at = longest_still(cta, clocks["s10"])
    assert gap > MAX_STILL_SECONDS and round(at - clocks["s10"].start, 1) == 1.5, (gap, at)
    tidied, _ = motion_tidy.cue_cta(SCRIPT, n_tags=4)
    gap, _ = longest_still(_shot(tidied, "s10"), clocks["s10"])
    assert gap <= MAX_STILL_SECONDS, gap


def test_cta_steps_land_on_their_words():
    acts = motion_tidy.cta_actions(_shot(SCRIPT, "s10"), n_tags=4)
    got = [(a.do, a.at) for a in acts]
    assert got[0] == ("enter", "start")
    assert ("tap", "Follow") in got and ("reveal", "Next") in got, got
    assert got[-1][0] == "pulse"
    # every cue resolves, in order
    from shorts.motion_scenes import resolve_cues
    shot = _shot(SCRIPT, "s10")
    shot = shot.model_copy(update={"scene": shot.scene.model_copy(update={"actions": acts})})
    idx = resolve_cues(shot)
    assert None not in idx and idx == sorted(idx), idx


def test_every_full_frame_template_keeps_moving_on_a_long_shot():
    """The cause, not just this scene: every full-frame card, stretched to
    half again as long as estimated (a slow speaker), still changes at least every 2.5 s once the
    timing stage's cadence repair runs on its clock."""
    from shorts.motion_scenes import with_default_scenes
    scripts = []
    for f in sorted(FIX.glob("*_golden.json")) + [FIX / "variable_points_to_value_scenes.json"]:
        sc = MotionScript.model_validate_json(f.read_text())
        scripts.append(with_default_scenes(sc))
        if all(s.scene for s in sc.shots):
            scripts.append(sc)
    slow = []
    kinds_seen = set()
    for script in scripts:
        slow += _stretched_slow(script, kinds_seen)
    full = {k for k, spec in lib.object_kinds().items() if spec["layout"] == "full"}
    assert full <= kinds_seen, full - kinds_seen
    assert not slow, slow


K = 1.5


def _stretched_slow(script, kinds_seen):
    clocks = shot_timings(script)
    slow = []
    for sh, c in zip(script.shots, clocks):
        # stretch the clock: every word half again as long
        caps = [cap.model_copy(update={
            "start": c.start + (cap.start - c.start) * K, "end": c.start + (cap.end - c.start) * K,
            "words": [w.model_copy(update={"start": c.start + (w.start - c.start) * K,
                                           "end": c.start + (w.end - c.start) * K}) for w in cap.words]})
            for cap in c.captions]
        long = ShotClock(id=c.id, start=c.start, end=c.start + (c.end - c.start) * K, captions=caps)
        fixed = motion_tidy.fill_cadence(script.model_copy(update={"shots": [sh]}), [long])[0].shots[0]
        gap, _ = longest_still(fixed, long)
        kinds = [o.kind for o in sh.scene.objects]
        kinds_seen.update(kinds)
        if gap > MAX_STILL_SECONDS + 1e-6:
            slow.append((script.short_id, sh.id, sh.beat, kinds, round(gap, 1)))
    return slow


# ===================================================================== scenes

def _plan(script=None, characters=True) -> MotionPlan:
    script = script or motion_tidy.tidy(SCRIPT, n_tags=4)[0]
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
