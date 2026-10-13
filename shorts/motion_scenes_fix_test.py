"""
The scenes stage after the first real motion reel failed
(output/what_state_means__motion, 2026-10-09; its script is the fixture
evals/fixtures/motion/what_state_means_script.json).

What happened: the first scenes call failed 8 of 11 shots, s01 (the hook)
failed both repairs and fell back to its default scene — whose pill read
"Same click. Why" — and the payoff (entity_card + trigger_chip from the
model) then no longer mirrored the default hook (kinetic_title +
status_pill), so the run gave up.

These tests replay it with a scripted fake model, in stub mode:
  - the prompt now carries what the graders check: the hook's language mark,
    every height and region, no side-by-side layout or phone mocks, cue words
    without tags, per-shot budgets;
  - a cue copied with its <b> tags still matches;
  - transitions are made legal for the fields in sequence, never a repair;
  - the hook falling back takes the payoff with it, and a fallback never
    leaves a grader failing;
  - the default hook names the question and the symptom, not a fragment;
  - every attempt is recorded (scenes_attempts.json).

    SHORTS_STUB=1 python -m shorts.motion_scenes_fix_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import json
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import checks, config, motion_scenes as ms
from shorts.schema import MotionScene, MotionScenesDraft, MotionScript
from shorts.skills import scenes as sk

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = MotionScript(**json.loads((ROOT / "evals/fixtures/motion/what_state_means_script.json").read_text()))


def _scene(**kw) -> dict:
    return {"field": kw.get("field", "paper"), "transition": kw.get("transition", "cut"), "label": "",
            "objects": kw["objects"], "actions": kw.get("actions", [])}


#: s01 as the real run's model kept writing it: two "phone mocks", which the library has no kind for.
BAD_HOOK = _scene(field="navy", objects=[
    {"id": "o1", "kind": "phone_mock", "props": {"label": "Plain variable", "value": "0"}},
    {"id": "o2", "kind": "phone_mock", "props": {"label": "State", "value": "3"}}],
    actions=[{"at": "start", "do": "enter", "target": "o1"}])
#: s09 as the real run's model wrote it: entity_card + trigger_chip.
MODEL_PAYOFF = _scene(field="navy", transition="iris", objects=[
    {"id": "o1", "kind": "entity_card", "props": {"label": "State", "value": "3", "tone": "ok"}},
    {"id": "o2", "kind": "trigger_chip", "props": {"label": "Same click"}}],
    actions=[{"at": "start", "do": "enter", "target": "o1"}, {"at": "side by side", "do": "enter", "target": "o2"},
             {"at": "plain variable", "do": "pulse", "target": "o2"},
             {"at": "stuck at zero", "do": "pulse", "target": "o1"},
             {"at": "state value climbs", "do": "state", "target": "o1", "value": "4", "tone": "ok"},
             {"at": "React remembers", "do": "pulse", "target": "o1"},
             {"at": "runs Counter again", "do": "pulse", "target": "o2"}])


@contextlib.contextmanager
def fake_model(answer):
    """Replace the scenes call: answer(label, user) -> {"shots": [...]}. Records the calls."""
    calls = []
    real = sk.ask_json

    def fake(system, user, cls, max_tokens=0, label=""):
        calls.append({"label": label, "system": system, "user": user})
        return cls(**answer(label, user))
    sk.ask_json = fake
    try:
        yield calls
    finally:
        sk.ask_json = real


def _defaults_except(overrides: dict[str, dict], only: list[str] | None = None) -> dict:
    scenes = ms.default_scenes(SCRIPT)
    shots = []
    for s, sc in zip(SCRIPT.shots, scenes):
        if only is not None and s.id not in only:
            continue
        shots.append({"id": s.id, "scene": overrides.get(s.id, sc.model_dump())})
    return {"shots": shots}


def _asked(user: str) -> list[str]:
    head = user.split("\nSHOTS:\n", 1)[1].split("\nSCRIPT (JSON", 1)[0]
    return [line.split()[1] for line in head.splitlines() if line.startswith("- s")]


# ================================================================= the prompt

def test_the_prompt_says_what_the_graders_check():
    p = sk.system_prompt()
    gap = sk.lib.library()["frame"]["gap"]           # the layout's own number, whatever it is
    for must in ("identity_title (no props", "ONLY the hook", "NO free layout", "ONE compare object",
                 "SHOW IT, DON'T WRITE IT", "app_screen", "memory_box", "ONLY on a shot whose script has code",
                 "1000 tall", "600 tall", f"gap between objects {gap}", "entity_card [placed] 330",
                 "kinetic_title [placed] 106 per line", "code_window [placed] 174 + 120 per line",
                 "without the <b> tags", "SAME object\n  kinds", "every 2.5 seconds"):
        assert must.replace("\n  ", " ") in p.replace("\n  ", " "), must
    assert "__" not in p
    block = sk._script_block(SCRIPT)
    assert "budget: ~" in block and "needs >= " in block and "act the problem out" in block
    assert "mirror the hook's kinds" in block
    assert "cue words: Why does one counter stay stuck at zero?" in block      # tags stripped
    assert "colours: coral (bad) allowed, no mint" in block


def test_the_prompts_example_is_a_valid_scene():
    p = sk.system_prompt()
    ex = p.split("has 600 of height):\n", 1)[1].split("\n(In the hook", 1)[0]
    draft = MotionScenesDraft(**json.loads(ex))
    for s in draft.shots:
        for o in s.scene.objects:
            assert not ms.object_problems(o), (s.id, o)
    # kinetic_title 2 lines (2 x 106.4) + gap 60 + app_screen 560 — the arithmetic the prompt states
    assert round(ms.stack_height(draft.shots[0].scene)) == 833, ms.stack_height(draft.shots[0].scene)
    assert {a.do for a in draft.shots[0].scene.actions} >= {"tap", "state"}


# ======================================================== cues and transitions

def test_a_cue_copied_with_its_tags_still_matches():
    s08 = SCRIPT.shots[7]
    for cue in ("<b>remember</b>", "<b>triggers the re-render</b>", "`setCount` changes"):
        sc = MotionScene(field="paper", transition="cut", objects=[{"id": "o1", "kind": "trigger_chip", "props": {"label": "x"}}],
                         actions=[{"at": cue, "do": "enter", "target": "o1"}])
        assert ms.resolve_cues(s08, sc)[0] is not None, cue


def test_transitions_are_fixed_not_repaired():
    script = ms.with_default_scenes(SCRIPT)
    broken = script.model_copy(update={"shots": [
        s.model_copy(update={"scene": s.scene.model_copy(update={"transition": "iris"})}) for s in script.shots]})
    assert not checks.check_motion_scene_valid(broken).passed
    fixed = ms.fix_transitions(broken)
    assert checks.check_motion_scene_valid(fixed).passed
    assert [s.scene.objects for s in fixed.shots] == [s.scene.objects for s in broken.shots]   # only transitions


# ================================================================ the fallback

def test_the_real_failure_now_falls_back_cleanly():
    """The model keeps writing s01 with phone mocks; s09 is its entity_card +
    trigger_chip. Before: s01 fell back alone and the mirror failed. Now: the
    payoff falls back with it and every grader passes."""
    def answer(label, user):
        if label == "motion_scenes":
            return _defaults_except({"s01": BAD_HOOK, "s09": MODEL_PAYOFF})
        return _defaults_except({"s01": BAD_HOOK}, only=_asked(user))
    attempts: list = []
    with fake_model(answer) as calls:
        out, results = sk.write_motion_scenes(SCRIPT, log=lambda *_: None, attempts=attempts)
    assert [c["label"] for c in calls] == ["motion_scenes"] + ["motion_scenes_repair"] * config.MAX_MOTION_SCENE_RETRIES
    assert checks.all_passed(results), [str(r) for r in results if not r.passed]
    hook, pay = out.shots[0], out.shots[8]
    assert {o.kind for o in hook.scene.objects} - {"identity_title"} <= {o.kind for o in pay.scene.objects}
    assert attempts[-1]["attempt"] == "fallback" and set(attempts[-1]["fallback"]) == {"s01", "s09"}
    assert "kind 'phone_mock' is not in the scene library" in json.dumps(attempts[0]["failing"]["s01"])
    # the model's payoff was drawable; it failed only because it could not mirror a broken hook
    assert all("motion_payoff_mirrors_hook" in why for why in attempts[0]["failing"]["s09"])


def test_the_old_fallback_would_have_failed_the_mirror():
    """The bug, reproduced: replacing only the hook by its default leaves a
    model payoff that does not mirror it."""
    mixed = SCRIPT.model_copy(update={"shots": [
        s.model_copy(update={"scene": MotionScene(**(MODEL_PAYOFF if s.id == "s09" else
                                                     ms.default_scenes(SCRIPT)[i].model_dump()))})
        for i, s in enumerate(SCRIPT.shots)]})
    mixed = ms.fix_transitions(mixed)
    r = checks.check_motion_payoff_mirrors_hook(mixed)
    assert not r.passed and "mirror the hook" in r.reason
    fixed, results, fell = sk.fall_back(mixed, ["s01"], log=lambda *_: None)
    assert checks.all_passed(results) and "s09" in fell


def test_a_fallback_never_leaves_a_failure():
    """Whatever mix the model leaves, fall_back ends with every grader passing."""
    defaults = ms.default_scenes(SCRIPT)
    for bad in (["s01"], ["s09"], ["s02", "s05"], ["s01", "s04", "s07", "s10"], [s.id for s in SCRIPT.shots]):
        mixed = SCRIPT.model_copy(update={"shots": [
            s.model_copy(update={"scene": MotionScene(**(BAD_HOOK if s.id in bad else defaults[i].model_dump()))})
            for i, s in enumerate(SCRIPT.shots)]})
        out, results, _ = sk.fall_back(mixed, bad, log=lambda *_: None)
        assert checks.all_passed(results), (bad, [str(r) for r in results if not r.passed])


def test_a_first_attempt_that_passes_makes_one_call():
    with fake_model(lambda label, user: _defaults_except({})) as calls:
        out, results = sk.write_motion_scenes(SCRIPT, log=lambda *_: None)
    assert len(calls) == 1 and checks.all_passed(results)


# ============================================================ the default hook

def test_the_default_hook_names_the_question_and_acts_out_the_symptom():
    """The hook: the question above, and the failure acted out below it (an
    app screen whose button is tapped and whose number stays put)."""
    hook = ms.default_scenes(SCRIPT)[0]
    kinds = [(o.kind, o.props) for o in hook.objects]
    title = next(p for k, p in kinds if k == "kinetic_title")["text"]
    assert title == "Why does one counter stay stuck at zero?"   # the player sets the case per design
    screen = next(o for o in hook.objects if o.kind in checks.MOTION_ACTION_KINDS)
    acts = [(a.do, a.tone) for a in hook.actions if a.target == screen.id]
    assert ("state", "bad") in acts, acts
    if screen.kind == "app_screen":
        assert ("tap", None) in acts, acts
    assert checks.all_passed(checks.run_motion_scene_graders(ms.with_default_scenes(SCRIPT)))


def test_the_runner_saves_every_attempt():
    from shorts import motion_reel
    sid = "what_state_means__motion"
    calls_left = {"n": 0}

    def answer(label, user):
        calls_left["n"] += 1
        if label == "motion_scenes":
            return _defaults_except({"s01": BAD_HOOK, "s09": MODEL_PAYOFF})
        return _defaults_except({"s01": BAD_HOOK}, only=_asked(user))
    with fake_model(answer):
        out = motion_reel.stage_scenes(sid, SCRIPT.model_copy(update={"short_id": sid}), yes=True, reel_cursor=0)
    assert out is not None
    saved = json.loads(motion_reel.scenes_attempts_path(sid).read_text())
    assert [a["attempt"] for a in saved["attempts"]] == ["first", "repair 1", "repair 2", "fallback"]
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")         # a temp folder, never output/


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} scenes-fix tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SCENES-FIX TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
