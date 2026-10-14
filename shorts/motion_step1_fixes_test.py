"""
Step 1 of the first-real-reel review of variable_points_to_value__motion
(job f64077e78448, 2026-10-13): caption layout, the CTA timing failure and
its cause, and the bugs and removals the review found. The fixture is that
reel's approved scenes (evals/fixtures/motion/variable_points_to_value_scenes.json)
and its old plan with the real word timings (…_plan_rev1.json).

  - the CTA held still 2.6 s (motion_change_cadence): the end card is now cued
    on its words, and on the real clock any still stretch in ANY template
    gets a word-cued action (motion_tidy.fill_cadence);
  - "# cart: the variable" (a comment used as a label) is removed;
  - the memory slot "tag | cart" is turned round to cart -> ["milk", "bread"];
  - the payoff that only relabelled the hook's box now shows cart pointing to
    its list (a low-value shot with no such picture is dropped);
  - the new plan checks: caption layout, redundant overlays, decoration.

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

def test_comment_labels_are_removed_and_real_comments_kept():
    assert motion_tidy.comment_label("# cart: the variable", ['cart = ["milk"]'])
    assert motion_tidy.comment_label("// count - the state", ["let count = 0"])
    assert not motion_tidy.comment_label("# make the list first", ['cart = ["milk"]'])
    assert not motion_tidy.comment_label('cart = ["milk"]', ['cart = ["milk"]'])
    tidied, notes = motion_tidy.strip_comment_labels(SCRIPT)
    lines = _shot(tidied, "s07").scene.objects[0].props["lines"]
    assert lines == ['cart = ["milk", "bread"]'], lines
    assert any("s07" in n for n in notes)


def test_the_memory_slot_is_turned_round():
    tidied, notes = motion_tidy.fix_panel_slots(SCRIPT)
    p = _shot(tidied, "s04").scene.objects[1].props
    assert (p["slot_name"], p["slot_value"]) == ("cart", '["milk", "bread"]'), p
    # a slot that already names a value is left alone
    ok = SCRIPT.model_copy(update={"shots": [s.model_copy(update={"scene": s.scene.model_copy(update={
        "objects": [MotionSceneObject(id="o1", kind="system_panel",
                                      props={"title": "Memory", "status": "x", "slot_name": "cart", "slot_value": "list"})],
        "actions": [MotionSceneAction(at="start", do="enter", target="o1")]})}) if s.id == "s04" else s
        for s in SCRIPT.shots]})
    assert motion_tidy.fix_panel_slots(ok)[1] == []


def test_the_relabelled_payoff_is_dropped_and_a_real_one_kept():
    assert motion_tidy.low_value_shots(SCRIPT) == [("s08", "repeats s01's memory_box and only relabels it")]
    # the same box, but the payoff TAPS it (the hook's failure now works): kept
    shots = []
    for s in SCRIPT.shots:
        if s.id == "s08":
            acts = list(s.scene.actions) + [MotionSceneAction(at="points", do="reset", target="o1")]
            s = s.model_copy(update={"scene": s.scene.model_copy(update={"actions": acts})})
        shots.append(s)
    assert motion_tidy.low_value_shots(SCRIPT.model_copy(update={"shots": shots})) == []


def test_the_relabelled_payoff_now_points_at_its_value():
    """The student's "Now I get it" line stays: its box is drawn as cart
    pointing to ["milk", "bread"] (from the reel's own code), no relabel text."""
    tidied, notes = motion_tidy.drop_low_value(SCRIPT)
    pay = _shot(tidied, "s08")
    box = pay.scene.objects[0]
    assert box.props["points_to"] == '["milk", "bread"]', box.props
    assert all(a.value is None for a in pay.scene.actions if a.do == "state"), pay.scene.actions
    assert motion_tidy.low_value_shots(tidied) == []
    assert any("s08" in n and "pointing" in n for n in notes), notes


def test_a_low_value_shot_with_no_better_picture_is_dropped():
    # the same relabel, but the reel's code never assigns the box's name
    shots = [s.model_copy(update={"code": []}) for s in SCRIPT.shots]
    tidied, notes = motion_tidy.drop_low_value(SCRIPT.model_copy(update={"shots": shots}))
    assert "s08" not in [s.id for s in tidied.shots]
    assert any("s08: dropped" in n for n in notes), notes


def test_tidy_keeps_the_scenes_valid():
    from shorts import checks
    tidied, _ = motion_tidy.tidy(SCRIPT, n_tags=4)
    assert [s.id for s in tidied.shots] == ["s01", "s02", "s03", "s04", "s05", "s06", "s07", "s08", "s09", "s10"]
    r = checks.check_motion_scene_valid(tidied)
    assert r.passed, r.reason
    assert checks.check_motion_payoff_mirrors_hook(tidied).passed
    # a payoff dropped as low value does not fail the mirror check; a missing one does
    gone = tidied.model_copy(update={"shots": [s for s in tidied.shots if s.id != "s08"]})
    assert checks.check_motion_payoff_mirrors_hook(gone, dropped=["s08"]).passed
    assert not checks.check_motion_payoff_mirrors_hook(gone).passed


# ===================================================================== plan checks

def _plan(script=None, characters=True) -> MotionPlan:
    script = script or motion_tidy.tidy(SCRIPT, n_tags=4)[0]
    from shorts.motion_reel import _cast
    return build_plan(script, _real_clocks(script), cast=_cast(script), tags=["#python", "#mentor"],
                      characters=characters, character="cs", host_character="host", design="midnight_lab")


def test_a_new_plan_is_rev_2_and_an_old_one_is_not_checked():
    plan = _plan()
    assert plan.rev == PLAN_REV >= 2
    old = MotionPlan(**OLD_PLAN)
    assert old.rev == 1
    for r in motion_plan_checks.run(old):
        assert r.passed and "not checked" in r.reason, r


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


def test_redundant_overlays_flag_a_caption_that_repeats_a_card():
    plan = _plan()
    assert motion_plan_checks.check_redundant_overlays(plan).passed
    # a pill whose words are the caption's
    shots = []
    for s in plan.shots:
        if s.id == "s05":
            objs = [o.model_copy(update={"props": {**o.props, "text": "tells Python where the box is"}})
                    if o.kind == "status_pill" else o for o in s.objects]
            s = s.model_copy(update={"objects": objs})
        shots.append(s)
    bad = motion_plan_checks.check_redundant_overlays(plan.model_copy(update={"shots": shots}))
    assert not bad.passed and "s05" in bad.reason, bad.reason


def test_decoration_is_flagged():
    plan = _plan()
    assert motion_plan_checks.check_decorative_elements(plan).passed
    shots = []
    for s in plan.shots:
        if s.id == "s05":
            objs = [o.model_copy(update={"props": {"text": "", "icon": "box"}}) if o.kind == "status_pill" else o
                    for o in s.objects]
            s = s.model_copy(update={"objects": objs, "actions": [a for a in s.actions if a.target != "o2" or a.do == "enter"]})
        shots.append(s)
    bad = motion_plan_checks.check_decorative_elements(plan.model_copy(update={"shots": shots}))
    assert not bad.passed and "s05.o2" in bad.reason, bad.reason


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
