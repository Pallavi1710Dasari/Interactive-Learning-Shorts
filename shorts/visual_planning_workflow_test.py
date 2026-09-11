"""
Offline, deterministic tests for Step 10: workflow-aware visual planning
(shorts/skills/strategy.py's plan_strategy_for_workflow, and
shorts/workflow.py's advance()/advance_many(), extended to call it one stage
past script generation).

No API key, no network — every LLM call here goes through config.STUB exactly
like Steps 3-9 (plan_strategy already has a stub path via VisualStrategy's
existing stub handler; Step 10 adds a second, approach-varying stub path
alongside it — see shorts.stubs._workflow_aware_strategy).

    python -m shorts.visual_planning_workflow_test
"""
from unittest.mock import patch

from . import config
from .schema import Section, Topic, TopicList, QuestionWorkflow, TeachingApproach
from .skills import select, strategy as strategy_mod
from .skills.script import write_script_for_workflow
from .skills.strategy import plan_strategy_for_workflow, plan_strategy
from .checks import (
    check_visual_strategy_matches_teaching_approach,
    _mentions_code,
)
from . import review, workflow


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow(topic_id="t_paging", **overrides) -> QuestionWorkflow:
    data = dict(
        id=topic_id, topic="Why does paging remove external fragmentation?",
        why_it_matters="central mechanism", source_section_id="3.1",
        difficulty="medium", importance=5, concept="paging and fragmentation",
        answer_quote="Paging solves external fragmentation by dividing memory "
                     "into equal fixed-size frames.",
    )
    data.update(overrides)
    topic = Topic(**data)
    [selection] = select.build_question_selections(TopicList(topics=[topic]), [_section()])
    return QuestionWorkflow(selection=selection)


def _scripted_workflow(topic_id="t_paging", section: Section | None = None) -> QuestionWorkflow:
    """Question approved, framed, teaching approach chosen AND approved, script
    generated — no visual plan yet. Built WITHOUT going through advance() for
    the script step: a single advance() call now runs script generation AND
    visual planning back to back (Step 10's own wiring, verified separately
    by test_approved_scripted_workflow_can_plan_visuals), so reaching
    "scripted but not yet planned" needs write_script_for_workflow called
    directly, the same way script_orchestration_test.py's own
    _approved_teaching_approach_workflow avoids advance() for its final step.
    The stub's own TeachingApproach is always `direct_explanation` (see
    stubs._teaching_approach) — tests that need a DIFFERENT approved approach
    use _forced_approach below rather than depending on stub wording, so they
    are not flaky against that stub's own fixed output."""
    section = section or _section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(
            _workflow(topic_id, source_section_id=section.section_id))
        wf = workflow.advance(wf, [section]).workflow   # framed + approach chosen
        wf = review.approve_teaching_approach(wf)
        wf = write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub
    assert wf.script is not None
    assert wf.visual_strategy is None
    return wf


def _forced_approach(wf: QuestionWorkflow, primary: str,
                     combined_with: list[str] | None = None) -> QuestionWorkflow:
    """Replace wf's APPROVED teaching approach with a specific, hand-built
    one — bypassing the stub's fixed direct_explanation output — so tests can
    exercise every _STUB_APPROACH_SHAPE entry deterministically. Mirrors how
    a real regeneration would land: teaching_approach set, approval status
    'approved', no stale regenerated_approach/override pointing elsewhere.
    Does not touch script — plan_strategy_for_workflow's gate only requires
    approved_teaching_approach to be set, never that the existing script was
    written for this exact approach."""
    approach = TeachingApproach(primary=primary, combined_with=combined_with or [],
                                alternatives=[], rationale=f"forced for test: {primary}")
    return wf.model_copy(update={
        "teaching_approach": approach,
        "teaching_approach_approval": wf.teaching_approach_approval.model_copy(
            update={"status": "approved", "regenerated_approach": None, "override": None}),
    })


# --------------------------------------------------------------------------- 1
def test_visual_planning_refuses_before_script_exists():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        wf = workflow.advance(wf, [_section()]).workflow   # framed + approach chosen
        wf = review.approve_teaching_approach(wf)
        assert wf.script is None
        raised = None
        try:
            plan_strategy_for_workflow(wf, _section())
        except ValueError as e:
            raised = e
    finally:
        config.STUB = old_stub
    assert raised is not None
    assert "no script" in str(raised)
    print("   ok — plan_strategy_for_workflow refuses to run before a script "
          "exists (requirement 1)")


# --------------------------------------------------------------------------- 2
def test_pending_question_approval_blocks_visual_plan():
    wf = _workflow()
    with patch.object(strategy_mod, "ask_json", side_effect=AssertionError(
            "must not plan visuals for a pending question")):
        result = workflow.advance(wf, [_section()])
    assert result.status == "awaiting_question_approval"
    assert result.workflow.visual_strategy is None
    print("   ok — a pending question approval blocks visual-plan creation "
          "(requirement 2)")


# --------------------------------------------------------------------------- 3
def test_pending_teaching_approach_approval_blocks_visual_plan():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        wf = workflow.advance(wf, [_section()]).workflow   # framed + chosen, not approved
        assert wf.teaching_approach_approval.status == "pending"
        with patch.object(strategy_mod, "ask_json", side_effect=AssertionError(
                "must not plan visuals before teaching-approach approval")):
            result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_teaching_approach_approval"
    assert result.workflow.visual_strategy is None
    print("   ok — a pending teaching-approach approval blocks visual-plan "
          "creation (requirement 3)")


# --------------------------------------------------------------------------- 4
def test_approved_scripted_workflow_can_plan_visuals():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_visual_plan_approval"
    assert result.workflow.visual_strategy is not None
    assert result.workflow.visual_strategy.beats
    print("   ok — a fully approved, scripted workflow can create a visual "
          "plan through advance() (requirement 4)")


# --------------------------------------------------------------------------- 5
def test_approved_teaching_approach_reaches_the_prompt():
    captured = {}
    real_ask_json = strategy_mod.ask_json

    def spy(system, user, model_cls, **kw):
        if model_cls.__name__ == "VisualStrategy":
            captured["user"] = user
        return real_ask_json(system, user, model_cls, **kw)

    old_stub = config.STUB
    config.STUB = True
    strategy_mod.ask_json = spy
    try:
        wf = _scripted_workflow()
        wf = _forced_approach(wf, "comparison")
        workflow.advance(wf, [_section()])
    finally:
        strategy_mod.ask_json = real_ask_json
        config.STUB = old_stub
    assert "user" in captured, "plan_strategy was never called"
    assert "THE APPROVED TEACHING APPROACH FOR THIS SHORT: comparison" in captured["user"]
    print("   ok — the approved teaching approach reaches the visual-planning "
          "prompt (requirement 5)")


# --------------------------------------------------------------------------- 6
def test_script_beats_reach_the_input():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    script_refs, seen = [], set()
    for b in result.workflow.script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            script_refs.append(b.visual_ref)
    strategy_refs = [b.ref for b in result.workflow.visual_strategy.beats]
    assert script_refs == strategy_refs, (script_refs, strategy_refs)
    print("   ok — the approved script's own beats/refs reach the visual "
          "strategy's input, one decision per ref, no re-derivation "
          "(requirement 6)")


# --------------------------------------------------------------------------- 7
def test_non_code_approaches_do_not_inject_code_first_instructions():
    old_stub = config.STUB
    config.STUB = True
    try:
        results = {}
        for primary in ["analogy", "comparison", "process_demonstration",
                        "conceptual_visual", "direct_explanation"]:
            wf = _scripted_workflow(topic_id=f"t_{primary}")
            wf = _forced_approach(wf, primary)
            result = workflow.advance(wf, [_section()])
            results[primary] = result.workflow.visual_strategy
    finally:
        config.STUB = old_stub
    for primary, strategy in results.items():
        approach = TeachingApproach(primary=primary, combined_with=[],
                                    alternatives=[], rationale="x")
        check = check_visual_strategy_matches_teaching_approach(strategy, approach)
        assert check.passed, f"{primary}: {check.reason}"
        for b in strategy.beats:
            assert not _mentions_code(b.must_see), (primary, b.must_see)
    print("   ok — non-code approved approaches never produce a code-first "
          "visual plan (requirement 7)")


# --------------------------------------------------------------------------- 8
def test_code_approach_can_legitimately_select_code():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow(topic_id="t_code_approach")
        wf = _forced_approach(wf, "code")
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    strategy = result.workflow.visual_strategy
    assert strategy is not None
    approach = TeachingApproach(primary="code", combined_with=[], alternatives=[],
                                rationale="x")
    check = check_visual_strategy_matches_teaching_approach(strategy, approach)
    assert check.passed, check.reason
    print("   ok — a code-approved approach is permitted to select a "
          "code-centred visual, and the alignment check accepts it "
          "(requirement 8)")


# --------------------------------------------------------------------------- 9
def test_existing_visual_strategy_architecture_still_works():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    strategy = result.workflow.visual_strategy
    # by_ref(), as_brief(), and every field BeatStrategy already had before
    # Step 10 still work unmodified against a workflow-generated strategy.
    by_ref = strategy.by_ref()
    assert set(by_ref) == {b.ref for b in strategy.beats}
    brief = strategy_mod.as_brief(strategy, set(by_ref))
    assert isinstance(brief, str) and brief
    for b in strategy.beats:
        assert b.relationship in (
            "process", "comparison", "data_movement", "hierarchy",
            "cause_effect", "structure", "effect", "quantity")
    print("   ok — the pre-existing VisualStrategy/BeatStrategy architecture "
          "(by_ref, as_brief, Relationship values) is unchanged and works "
          "against a workflow-generated strategy (requirement 9)")


# -------------------------------------------------------------------------- 10
def test_repeated_advance_after_visual_plan_does_not_call_llm_again():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        first = workflow.advance(wf, [_section()]).workflow
        with patch.object(strategy_mod, "ask_json", side_effect=AssertionError(
                "visual plan must not be regenerated on a second advance() "
                "call")):
            again = workflow.advance(first, [_section()])
    finally:
        config.STUB = old_stub
    assert again.status == "awaiting_visual_plan_approval"
    assert again.workflow.visual_strategy == first.visual_strategy
    print("   ok — a second advance() call after visual planning makes no "
          "further LLM call (requirement 10)")


# -------------------------------------------------------------------------- 11
def test_question_regeneration_invalidates_visual_plan():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        wf = workflow.advance(wf, [_section()]).workflow
        assert wf.visual_strategy is not None

        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.visual_strategy is None
    assert wf2.script is None
    print("   ok — question regeneration invalidates the visual plan (and the "
          "script it was built from) (requirement 11)")


# -------------------------------------------------------------------------- 12
def test_teaching_approach_regeneration_invalidates_visual_plan():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        wf = workflow.advance(wf, [_section()]).workflow
        assert wf.visual_strategy is not None

        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.visual_strategy is None
    assert wf2.script is None
    print("   ok — teaching-approach regeneration invalidates the visual plan "
          "(requirement 12)")


# -------------------------------------------------------------------------- 13
def test_script_invalidation_clears_visual_plan_directly():
    # A direct, schema-level check of the invalidation primitive itself,
    # independent of which review.py caller triggers it: whenever `script`
    # goes stale, `visual_strategy` and `visual_plan_approval` must go with
    # it — see QuestionWorkflow.invalidate_script.
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _scripted_workflow()
        wf = workflow.advance(wf, [_section()]).workflow
        assert wf.script is not None
        assert wf.visual_strategy is not None
    finally:
        config.STUB = old_stub
    cleared = wf.invalidate_script()
    assert cleared.script is None
    assert cleared.visual_strategy is None
    assert cleared.visual_plan_approval.status == "pending"
    print("   ok — invalidate_script clears script, visual_strategy and "
          "visual_plan_approval together (requirement 13)")


# -------------------------------------------------------------------------- 14
def test_existing_rendering_pipeline_not_broken():
    # The OLD, non-workflow-aware plan_strategy() call path — no `approach`
    # argument — must stay byte-identical to before Step 10: same stub
    # function (_strategy, fixed at relationship="structure"), same prompt
    # shape, no new required argument.
    from .skills.script import write_script
    section = _section()
    topic = Topic(id="t1", topic="Why does paging remove external fragmentation?",
                 why_it_matters="m", source_section_id="3.1", difficulty="medium")
    old_stub = config.STUB
    config.STUB = True
    try:
        sc = write_script(topic, section)
        strategy = plan_strategy(sc, section)
    finally:
        config.STUB = old_stub
    assert strategy.beats
    assert all(b.relationship == "structure" for b in strategy.beats), (
        "the OLD stub path must stay fixed at 'structure' — it has to keep "
        "agreeing with _visuals()'s own always-'bar' stub")
    print("   ok — the existing (non-workflow) visual-strategy path and "
          "rendering-facing stub contract are unchanged (requirement 14)")


# -------------------------------------------------------------------------- 15
def test_stub_mode_exercises_concept_first_planning():
    # Across several approved teaching approaches, the workflow-aware stub
    # must not always fall back to the same relationship/text — some of it
    # has to actually vary with the approach, the deterministic proxy for
    # "concept-first, not always text/code".
    old_stub = config.STUB
    config.STUB = True
    try:
        seen_relationships = set()
        for primary in ["process_demonstration", "comparison", "analogy",
                        "conceptual_visual", "direct_explanation"]:
            wf = _scripted_workflow(topic_id=f"t_stub_{primary}")
            wf = _forced_approach(wf, primary)
            result = workflow.advance(wf, [_section()])
            assert result.workflow.visual_strategy is not None
            for b in result.workflow.visual_strategy.beats:
                seen_relationships.add(b.relationship)
                assert not _mentions_code(b.must_see)
    finally:
        config.STUB = old_stub
    assert len(seen_relationships) > 1, (
        f"expected the workflow-aware stub to vary by approach, only ever "
        f"saw {seen_relationships}")
    print("   ok — stub mode exercises multiple concept-first visual shapes, "
          "not a single fixed text/code default (requirement 15)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} visual-planning (Step 10) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL VISUAL PLANNING WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
