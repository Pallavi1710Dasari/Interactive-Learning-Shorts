"""
Offline, deterministic tests for the Step 4 stage-aware validators:

    checks._resolve_beat_stage
    checks._stage_progression_problems (used by check_teaching_sequence)
    checks.check_teaching_sequence(..., script=...)
    checks.check_mechanism_stage_shows_change
    skills.visuals.design_visuals's retry loop wiring the check above in

No API key, no network — config.STUB is used only for the one end-to-end
retry-loop test, and even that never leaves the process (spec_visuals,
plan_strategy and render_diagrams are monkeypatched, not the real thing).

    python -m shorts.teaching_progression_validators_test
"""
import json

from . import checks
from .schema import (
    Script, Beat, Section, SectionUnderstanding, TeachingStep,
    Visual, Frame, Store, Slot, VisualStrategy, BeatStrategy, ShortUnit,
)


def _step(stage=None, concept="how the stack behaves", n=1) -> TeachingStep:
    # "stack" appears in every step's concept so check_teaching_sequence's
    # OWN pre-existing checks (on the objective, on the section's vocabulary)
    # pass regardless of stage — these tests are about the NEW stage checks,
    # not a regression test for the four that already existed.
    return TeachingStep(concept=f"{concept} {n}", purpose=f"needed before stack step {n + 1}",
                        explanation_goal=f"learner understands stack step {n}", stage=stage)


def _understanding(stages: list, core_idea="a stack is LIFO") -> SectionUnderstanding:
    steps = [_step(stage=s, n=i) for i, s in enumerate(stages, 1)]
    return SectionUnderstanding(section_id="1.1", core_idea=core_idea,
                                teaching_sequence=steps)


def _script(relates: list, question="why a stack is LIFO") -> Script:
    """beats[0] is the hook (relates_to_step always None); one body beat per
    entry in `relates`, each citing its own sentence so check_source_quotes-
    adjacent shape stays plausible (not graded here, just realistic)."""
    beats = [Beat(line="A stack only allows access at one end.", on_screen="Stack",
                  visual_ref="v0")]
    for i, r in enumerate(relates, 1):
        beats.append(Beat(line=f"Body sentence number {i}.", on_screen=f"B{i}",
                          visual_ref=f"v{i}", source_quote=f"Body sentence number {i}.",
                          relates_to_step=r))
    return Script(short_id="t1", question=question, beats=beats)


# ---------------------------------------------------------- 1 & 2: check_teaching_sequence

def test_1_valid_five_stage_progression_passes():
    understanding = _understanding(["concept", "mechanism", "example", "result"])
    script = _script([1, 2, 3, 4])
    result = checks.check_teaching_sequence(understanding, script=script)
    assert result.passed, result.reason
    print("   ok — hook -> concept -> mechanism -> example -> result passes cleanly")


def test_2_valid_shorter_progression_without_all_five_passes():
    # No mechanism, no example step in the PLAN at all — a genuinely simple
    # section. The script must not be forced to invent stages that were never
    # offered.
    understanding = _understanding(["concept", "result"])
    script = _script([1, 2])
    result = checks.check_teaching_sequence(understanding, script=script)
    assert result.passed, result.reason
    print("   ok — a valid hook -> concept -> result progression (no mechanism/example "
          "offered by the plan) passes without needing all five stages")


def test_3_out_of_range_relates_to_step_fails():
    understanding = _understanding(["concept", "result"])
    script = _script([1, 5])  # only 2 steps exist; beat 2 points at step 5
    result = checks.check_teaching_sequence(understanding, script=script)
    assert not result.passed
    assert "out of range" in result.reason
    print("   ok — an out-of-range relates_to_step (5, with only 2 steps) fails, "
          f"reason: {result.reason}")


def test_4_missing_stage_resolution_fails():
    # Step 1 has a stage; step 2 does not (present in range, but unresolvable).
    understanding = SectionUnderstanding(
        section_id="1.1", core_idea="a stack is LIFO",
        teaching_sequence=[_step(stage="concept", n=1), _step(stage=None, n=2)])
    script = _script([1, 2])
    result = checks.check_teaching_sequence(understanding, script=script)
    assert not result.passed
    assert "no stage set" in result.reason
    print("   ok — a beat referencing a real step that has no stage set fails, "
          f"reason: {result.reason}")


def test_5_definition_only_when_mechanism_expected_fails():
    # The plan offers a mechanism step; every resolvable beat stays at concept.
    understanding = _understanding(["concept", "mechanism", "result"])
    script = _script([1, 1, 1])  # every body beat relates to step 1 (concept) only
    result = checks.check_teaching_sequence(understanding, script=script)
    assert not result.passed
    assert "mechanism" in result.reason and "ever reaches one" in result.reason
    print("   ok — a script that only ever touches the concept-stage step, while the "
          f"plan offers a mechanism step, fails: {result.reason}")


def test_definition_only_check_is_inconclusive_without_stage_data():
    # No step carries a stage at all (pre-Step-3 data) — must be skipped, not failed.
    understanding = SectionUnderstanding(
        section_id="1.1", core_idea="how the stack behaves",
        teaching_sequence=[_step(stage=None, n=1), _step(stage=None, n=2)])
    script = _script([1, 2])
    result = checks.check_teaching_sequence(understanding, script=script)
    assert result.passed, result.reason
    print("   ok — a plan with no stage data at all is not judged on progression (inconclusive, not a failure)")


def test_definition_only_check_is_inconclusive_without_any_beat_reference():
    # Stage data exists on the plan, but no beat carries relates_to_step at all
    # (an older or not-yet-updated script) — must be skipped, not failed.
    understanding = _understanding(["concept", "mechanism", "result"])
    script = _script([None, None, None])
    result = checks.check_teaching_sequence(understanding, script=script)
    assert result.passed, result.reason
    print("   ok — a script with no relates_to_step anywhere is not judged on progression (inconclusive)")


def test_plan_only_call_without_script_is_unaffected():
    # understanding_for()'s own call site never passes `script` — confirm the
    # bare, original four-question behaviour is untouched.
    understanding = _understanding(["concept", "mechanism", "result"])
    result = checks.check_teaching_sequence(understanding)
    assert result.passed, result.reason
    print("   ok — calling check_teaching_sequence with no `script` (understanding_for()'s "
          "own call shape) behaves exactly as before Step 4")


# ------------------------------------------------- 6, 7, 8: check_mechanism_stage_shows_change

def _unit(beats, visuals) -> ShortUnit:
    return ShortUnit(short_id="t1", session_id="s", source_section_id="1.1",
                     question="q", estimated_seconds=30.0, beats=beats, visuals=visuals)


def _hook_visual() -> Visual:
    """A placeholder visual for the hook beat (v0) — every_ref_resolved requires
    one for every visual_ref a beat names, and these tests are not about the hook."""
    return Visual(ref="v0", type="diagram", spec="stub",
                  frame=Frame(template="stat", value="1", caption="a stack"))


def test_6_mechanism_beat_with_genuine_state_change_passes():
    understanding = _understanding(["concept", "mechanism", "result"])
    beats = [
        Beat(line="hook", on_screen="h", visual_ref="v0"),
        Beat(line="a stack is a container", on_screen="c", visual_ref="v1",
             source_quote="q", relates_to_step=1),
        Beat(line="pushing adds an item to the top", on_screen="push", visual_ref="v2",
             source_quote="q", relates_to_step=2),
        Beat(line="so the last one in comes out first", on_screen="lifo", visual_ref="v3",
             source_quote="q", relates_to_step=3),
    ]
    frame = Frame(template="state", store=Store(
        label="Stack", slots=[Slot(label="A", state="resting"),
                              Slot(label="B", state="arriving")],
        pointer="top", pointer_at=1))
    visuals = {
        "v0": _hook_visual(),
        "v1": Visual(ref="v1", type="diagram", spec="stub", frame=Frame(template="stat", value="1", caption="items"),
                    strategy=BeatStrategy(ref="v1", concept="c", relationship="structure",
                                         must_see="a container", focus="the container")),
        "v2": Visual(ref="v2", type="diagram", spec="stub", frame=frame,
                    strategy=BeatStrategy(ref="v2", concept="push", relationship="process",
                                         must_see="the item arriving", focus="the arriving item")),
        "v3": Visual(ref="v3", type="diagram", spec="stub", frame=Frame(template="stat", value="1", caption="order")),
    }
    unit = _unit(beats, visuals)
    result = checks.check_mechanism_stage_shows_change(unit, understanding)
    assert result.passed, result.reason
    print(f"   ok — a mechanism/process beat with a slot marked 'arriving' passes: {result.reason}")


def test_7_mechanism_beat_with_static_visual_fails():
    understanding = _understanding(["concept", "mechanism", "result"])
    beats = [
        Beat(line="hook", on_screen="h", visual_ref="v0"),
        Beat(line="pushing adds an item to the top", on_screen="push", visual_ref="v2",
             source_quote="q", relates_to_step=2),
    ]
    visuals = {
        "v0": _hook_visual(),
        "v2": Visual(ref="v2", type="diagram", spec="stub",
                    frame=Frame(template="bar", cells=[]),
                    strategy=BeatStrategy(ref="v2", concept="push", relationship="process",
                                         must_see="the item arriving", focus="the item")),
    }
    unit = _unit(beats, visuals)
    result = checks.check_mechanism_stage_shows_change(unit, understanding)
    assert not result.passed
    assert "bar" in result.reason
    print(f"   ok — a mechanism/process beat drawn as a static 'bar' fails: {result.reason}")


def test_7b_mechanism_beat_as_state_with_everything_resting_fails():
    understanding = _understanding(["concept", "mechanism", "result"])
    beats = [
        Beat(line="hook", on_screen="h", visual_ref="v0"),
        Beat(line="pushing adds an item to the top", on_screen="push", visual_ref="v2",
             source_quote="q", relates_to_step=2),
    ]
    frame = Frame(template="state", store=Store(
        label="Stack", slots=[Slot(label="A", state="resting"),
                              Slot(label="B", state="resting")],
        pointer="top", pointer_at=1))
    visuals = {
        "v0": _hook_visual(),
        "v2": Visual(ref="v2", type="diagram", spec="stub", frame=frame,
                    strategy=BeatStrategy(ref="v2", concept="push", relationship="process",
                                         must_see="the item arriving", focus="the item")),
    }
    unit = _unit(beats, visuals)
    result = checks.check_mechanism_stage_shows_change(unit, understanding)
    assert not result.passed
    assert "resting" in result.reason
    print(f"   ok — a mechanism/process beat drawn as 'state' with every slot resting fails: {result.reason}")


def test_8_genuinely_static_conceptual_mechanism_does_not_fail():
    # relationship=structure (NOT in _MOTION_RELATIONSHIPS) — a mechanism-stage
    # beat that is genuinely a still conceptual relationship, not a process.
    understanding = _understanding(["concept", "mechanism", "result"])
    beats = [
        Beat(line="hook", on_screen="h", visual_ref="v0"),
        Beat(line="the OS sits between hardware and applications", on_screen="layers",
             visual_ref="v2", source_quote="q", relates_to_step=2),
    ]
    visuals = {
        "v0": _hook_visual(),
        "v2": Visual(ref="v2", type="diagram", spec="stub",
                    frame=Frame(template="hierarchy"),
                    strategy=BeatStrategy(ref="v2", concept="layering", relationship="structure",
                                         must_see="the OS between two layers", focus="the OS")),
    }
    unit = _unit(beats, visuals)
    result = checks.check_mechanism_stage_shows_change(unit, understanding)
    assert result.passed, result.reason
    print(f"   ok — a mechanism-stage beat whose relationship is 'structure' (genuinely still) "
          f"is not required to show motion: {result.reason}")


def test_icons_with_arrows_false_fails_but_true_passes():
    understanding = _understanding(["concept", "mechanism", "result"])
    beats = [
        Beat(line="hook", on_screen="h", visual_ref="v0"),
        Beat(line="pushing adds an item to the top", on_screen="push", visual_ref="v2",
             source_quote="q", relates_to_step=2),
    ]
    for arrows, should_pass in ((False, False), (True, True)):
        visuals = {
            "v0": _hook_visual(),
            "v2": Visual(ref="v2", type="diagram", spec="stub",
                        frame=Frame(template="icons", arrows=arrows),
                        strategy=BeatStrategy(ref="v2", concept="push", relationship="process",
                                             must_see="items arriving in sequence", focus="the new item")),
        }
        unit = _unit(beats, visuals)
        result = checks.check_mechanism_stage_shows_change(unit, understanding)
        assert result.passed == should_pass, (arrows, result.reason)
    print("   ok — 'icons' with arrows=false fails, arrows=true passes, for a mechanism/process beat")


def test_no_teaching_sequence_skips_cleanly():
    result = checks.check_mechanism_stage_shows_change(
        _unit([Beat(line="x", on_screen="x", visual_ref="v0")], {"v0": _hook_visual()}), understanding=None)
    assert result.passed
    assert result.details.get("skipped")
    print("   ok — no teaching sequence at all skips cleanly (nothing to resolve a stage from)")


# --------------------------------------------------- 9: enters design_visuals's retry path

def test_9_stage_aware_visual_failure_enters_design_visuals_retry_path():
    """No LLM calls: spec_visuals/plan_strategy/render_diagrams are monkeypatched
    stand-ins, config.STUB is untouched (irrelevant here — nothing calls ask_json)."""
    import shorts.skills.visuals as visuals_mod

    understanding = _understanding(["concept", "mechanism", "result"])
    section = Section(section_id="1.1", title="Stacks", start_line=1, end_line=5,
                      text="A stack only allows access at one end.")
    script = Script(short_id="t9", question="why a stack is LIFO", beats=[
        Beat(line="A stack only allows access at one end.", on_screen="Stack", visual_ref="v1"),
        Beat(line="pushing adds an item to the top", on_screen="Push", visual_ref="v2",
             source_quote="pushing adds an item to the top", relates_to_step=2),
    ])
    strategy = VisualStrategy(subject="a stack", beats=[
        BeatStrategy(ref="v1", concept="a stack", relationship="structure",
                     must_see="a container", focus="the container"),
        BeatStrategy(ref="v2", concept="push", relationship="process",
                     must_see="the item arriving", focus="the item"),
    ])

    spec_calls = []

    def fake_spec_visuals(script, section=None, feedback=None, model_override=None, strategy=None):
        spec_calls.append(feedback)
        by_ref = strategy.by_ref() if strategy else {}
        return {
            "v1": Visual(ref="v1", type="diagram", spec="stub",
                        frame=Frame(template="stat", value="1", caption="items"),
                        strategy=by_ref.get("v1")),
            # ALWAYS static, on purpose: this attempt never gets to satisfy
            # check_mechanism_stage_shows_change, so we can see it stay in
            # `problems` across retries without needing a smarter fake.
            # strategy=by_ref.get("v2") mirrors the REAL spec_visuals, which
            # attaches each Visual's strategy from the plan it was given —
            # without this, check_mechanism_stage_shows_change has no
            # relationship to read and skips every beat, silently.
            "v2": Visual(ref="v2", type="diagram", spec="stub",
                        frame=Frame(template="bar", cells=[]),
                        strategy=by_ref.get("v2")),
        }

    original_spec_visuals = visuals_mod.spec_visuals
    visuals_mod.spec_visuals = fake_spec_visuals
    try:
        visuals, problems = visuals_mod.design_visuals(
            script, section, draw=False, vision=False, attempts=2,
            strategy=strategy, understanding=understanding)
    finally:
        visuals_mod.spec_visuals = original_spec_visuals

    assert len(spec_calls) == 2, f"expected 2 attempts (both fail identically), got {len(spec_calls)}"
    assert any("mechanism_stage_shows_change" in p for p in problems), problems
    print(f"   ok — the stage-aware mechanism check's failure appears in design_visuals's "
          f"returned problems after retrying: {problems}")
    print(f"   ok — the retry loop ran {len(spec_calls)} attempt(s), same as any other "
          f"design-graders failure (no parallel pipeline)")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} teaching-progression-validator tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL TEACHING PROGRESSION VALIDATOR TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
