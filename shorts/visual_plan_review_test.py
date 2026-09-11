"""
Offline, deterministic tests for Step 11: human review of the workflow-aware
VisualStrategy (shorts/review.py's approve_visual_plan /
regenerate_visual_plan / run_visual_plan_gate, plus the schema they operate
on).

No API key, no network — every LLM call here goes through config.STUB exactly
like Steps 3-10 (see stubs._workflow_aware_strategy, reused for both the
initial plan and a regeneration since both target the same VisualStrategy
model).

    python -m shorts.visual_plan_review_test
"""
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from pydantic import ValidationError

from . import config
from .schema import (Section, Topic, TopicList, QuestionWorkflow, VisualStrategy,
                     VisualStrategyRegenerationAttempt)
from .skills import select, framing, teaching_approach
from .skills.script import write_script_for_workflow
from .skills.strategy import plan_strategy_for_workflow, VISUAL_STRATEGY_REGENERATE_SYSTEM
from .skills import strategy as strategy_mod
from . import review


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow(stage: str = "planned", **topic_overrides) -> QuestionWorkflow:
    """
    Build a workflow at a given stage:
      "pending"           just selected, question still pending
      "approved"           question approved, no framing
      "framed"              question approved and framed, no teaching_approach
      "approach"            framed, and a teaching_approach chosen (not approved)
      "approach_approved"   teaching approach approved, no script
      "scripted"            approach approved and scripted, no visual_strategy
      "planned"             (default) scripted AND a visual plan generated —
                            the ordinary starting point for these tests
    """
    data = dict(
        id="t_paging", topic="Why does paging remove external fragmentation?",
        why_it_matters="central mechanism", source_section_id="3.1",
        difficulty="medium", importance=5, concept="paging and fragmentation",
        answer_quote="Paging solves external fragmentation by dividing memory "
                     "into equal fixed-size frames.",
    )
    data.update(topic_overrides)
    topic = Topic(**data)
    [selection] = select.build_question_selections(TopicList(topics=[topic]), [_section()])
    wf = QuestionWorkflow(selection=selection)
    if stage == "pending":
        return wf

    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(wf)
        if stage == "approved":
            return wf
        wf = framing.frame_workflow(wf, [_section()])
        if stage == "framed":
            return wf
        wf = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        if stage == "approach":
            return wf
        wf = review.approve_teaching_approach(wf)
        if stage == "approach_approved":
            return wf
        wf = write_script_for_workflow(wf, _section())
        if stage == "scripted":
            return wf
        wf = plan_strategy_for_workflow(wf, _section())
        return wf
    finally:
        config.STUB = old_stub


# --------------------------------------------------------------------------- 1
# Visual plan can be approved.

def test_visual_plan_can_be_approved():
    wf = review.approve_visual_plan(_workflow())
    assert wf.visual_plan_approval.status == "approved"
    assert wf.approved_visual_strategy is not None
    print("   ok — a visual plan can be approved (requirement 1)")


# --------------------------------------------------------------------------- 2
# Pending plan cannot proceed.

def test_pending_plan_cannot_proceed():
    wf = _workflow()
    assert wf.visual_plan_approval.status == "pending"
    assert wf.approved_visual_strategy is None
    print("   ok — a pending visual_plan_approval blocks approved_visual_strategy "
          "(requirement 2)")


def test_legacy_modified_status_does_not_proceed_either():
    wf = _workflow()
    legacy = wf.visual_plan_approval.model_copy(update={
        "status": "modified", "override": wf.visual_strategy})
    wf = wf.model_copy(update={"visual_plan_approval": legacy})
    assert wf.approved_visual_strategy is None
    print("   ok — legacy 'modified' status does not satisfy the gate either")


def test_regenerating_status_cannot_proceed():
    wf = _workflow()
    wf = wf.model_copy(update={"visual_plan_approval":
        wf.visual_plan_approval.model_copy(update={"status": "regenerating"})})
    assert wf.approved_visual_strategy is None
    print("   ok — a workflow marked 'regenerating' cannot proceed")


# --------------------------------------------------------------------------- 3
# Regeneration requires a non-blank reason.

def test_regeneration_requires_non_blank_reason():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        for bad in (None, "", "   "):
            try:
                review.regenerate_visual_plan(wf, bad, [_section()])
                raise AssertionError(f"should reject reason={bad!r}")
            except ValueError:
                pass
    finally:
        config.STUB = old_stub
    print("   ok — regenerate_visual_plan refuses a missing/blank reason "
          "before calling the LLM (requirement 3)")


def test_regeneration_attempt_schema_rejects_blank_reason():
    strategy = VisualStrategy(subject="s", beats=[])
    for bad in ("", "   "):
        try:
            VisualStrategyRegenerationAttempt(
                reason=bad, previous_strategy=strategy, regenerated_strategy=strategy)
            raise AssertionError(f"should reject reason={bad!r}")
        except ValidationError:
            pass
    print("   ok — VisualStrategyRegenerationAttempt rejects a blank reason "
          "at the schema level too (requirement 3)")


# --------------------------------------------------------------------------- 4
# No direct editing / field-level modification.

def test_approve_takes_no_field_override_arguments():
    import inspect
    params = list(inspect.signature(review.approve_visual_plan).parameters)
    assert params == ["workflow", "note"]
    print("   ok — approve_visual_plan accepts no subject/beats override "
          "arguments (requirement 4/9)")


def test_regenerate_takes_no_field_override_arguments():
    import inspect
    params = list(inspect.signature(review.regenerate_visual_plan).parameters)
    assert "subject" not in params and "beats" not in params
    assert params == ["workflow", "reason", "sections", "understanding"]
    print("   ok — regenerate_visual_plan accepts only `reason`, never "
          "individual field overrides (requirement 4/9)")


def test_interactive_gate_offers_no_field_editing():
    wf = _workflow()
    prompts = []
    responses = iter(["q"])

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(responses)

    import builtins
    old_input = builtins.input
    builtins.input = fake_input
    try:
        review.run_visual_plan_gate([wf], [_section()], interactive=True)
    finally:
        builtins.input = old_input

    assert prompts
    lowered = prompts[0].lower()
    assert "edit" not in lowered and "override" not in lowered
    assert "[g]enerate again" in prompts[0]
    print("   ok — the interactive gate's prompt offers approve/regenerate/"
          "skip/quit only, never field editing (requirement 4/9)")


# --------------------------------------------------------------------------- 5
# Regeneration history.

def test_previous_strategy_preserved_in_history():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        original = wf.visual_strategy
        wf2 = review.regenerate_visual_plan(wf, "beat 2 shows code, that's not the approach",
                                            [_section()])
        history = wf2.visual_plan_approval.regeneration_history
        assert len(history) == 1
        assert history[0].previous_strategy == original
        # And the ORIGINAL visual_strategy field itself is untouched.
        assert wf2.visual_strategy == original
    finally:
        config.STUB = old_stub
    print("   ok — the previous VisualStrategy is preserved in "
          "regeneration_history, and workflow.visual_strategy is never "
          "overwritten (requirement 5)")


def test_previous_strategy_chains_across_multiple_regenerations():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf = review.regenerate_visual_plan(wf, "reason one", [_section()])
        first_regen = wf.visual_plan_approval.regenerated_strategy
        wf = review.regenerate_visual_plan(wf, "reason two", [_section()])
        history = wf.visual_plan_approval.regeneration_history
        assert len(history) == 2
        assert history[1].previous_strategy == first_regen
    finally:
        config.STUB = old_stub
    print("   ok — each regeneration's previous_strategy is the prior "
          "regeneration's result, forming a real chain (requirement 5)")


# --------------------------------------------------------------------------- 6
# Regeneration reason preserved.

def test_regeneration_reason_preserved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf = review.regenerate_visual_plan(
            wf, "I can't tell the two things apart", [_section()])
        history = wf.visual_plan_approval.regeneration_history
        assert history[0].reason == "I can't tell the two things apart"
    finally:
        config.STUB = old_stub
    print("   ok — the human's regeneration reason is preserved verbatim in "
          "history (requirement 6)")


# --------------------------------------------------------------------------- 7
# Complete regeneration, never a patch.

def test_regeneration_produces_a_complete_independent_plan():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf2 = review.regenerate_visual_plan(wf, "show a state change", [_section()])
        regenerated = wf2.visual_plan_approval.regenerated_strategy
        assert isinstance(regenerated, VisualStrategy)
        assert regenerated.subject
        assert isinstance(regenerated.beats, list) and regenerated.beats
        # EVERY ref from the original plan is decided again, not only the
        # beat(s) a reason happens to name.
        original_refs = {b.ref for b in wf.visual_strategy.beats}
        regenerated_refs = {b.ref for b in regenerated.beats}
        assert original_refs == regenerated_refs
    finally:
        config.STUB = old_stub
    print("   ok — regeneration returns a complete VisualStrategy (subject + "
          "every beat, same refs as before), never a partial patch "
          "(requirement 7/10)")


def test_reconsider_visual_strategy_prompt_shows_the_previous_plan():
    captured = {}
    real_ask_json = strategy_mod.ask_json

    def spy(system, user, model_cls, **kw):
        if model_cls.__name__ == "VisualStrategy":
            captured["user"] = user
            captured["system"] = system
        return real_ask_json(system, user, model_cls, **kw)

    old_stub = config.STUB
    config.STUB = True
    strategy_mod.ask_json = spy
    try:
        wf = _workflow()
        review.regenerate_visual_plan(wf, "beat 2 shows code, that's not the approach",
                                      [_section()])
    finally:
        strategy_mod.ask_json = real_ask_json
        config.STUB = old_stub

    assert "THE PREVIOUS PLAN, WHICH A HUMAN REVIEWED" in captured["user"]
    assert "beat 2 shows code, that's not the approach" in captured["user"]
    assert captured["system"] == VISUAL_STRATEGY_REGENERATE_SYSTEM
    print("   ok — regeneration's prompt includes the previous plan and the "
          "human's reason, using the dedicated reconsideration system prompt "
          "(requirement 7/10)")


# --------------------------------------------------------------------------- 8
# Regenerated plan returns to pending.

def test_regeneration_returns_to_pending_never_approved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_visual_plan(_workflow())    # start APPROVED
        assert wf.visual_plan_approval.status == "approved"
        wf = review.regenerate_visual_plan(wf, "show a state change", [_section()])
        assert wf.visual_plan_approval.status == "pending", (
            "regenerating an approved plan must drop it back to pending")
        assert wf.approved_visual_strategy is None
    finally:
        config.STUB = old_stub
    print("   ok — regenerating (even an already-approved plan) always lands "
          "on pending, never approved (requirement 8)")


# --------------------------------------------------------------------------- 9
# Regenerated plan requires explicit approval; regenerated strategy replaces
# the effective strategy.

def test_regenerated_plan_requires_a_fresh_explicit_approve():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.regenerate_visual_plan(_workflow(), "show a state change", [_section()])
        assert wf.approved_visual_strategy is None
        wf = review.approve_visual_plan(wf)
        assert wf.approved_visual_strategy is not None
        assert wf.approved_visual_strategy == wf.visual_plan_approval.regenerated_strategy
    finally:
        config.STUB = old_stub
    print("   ok — a regenerated plan proceeds only after a fresh, explicit "
          "approve_visual_plan call (requirement 9)")


def test_regenerated_strategy_replaces_the_effective_strategy():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        original = wf.effective_visual_strategy
        assert original == wf.visual_strategy
        wf2 = review.regenerate_visual_plan(wf, "show a state change", [_section()])
        # effective_visual_strategy now prefers the regeneration, but the
        # ORIGINAL visual_strategy field is still there, untouched.
        assert wf2.effective_visual_strategy == wf2.visual_plan_approval.regenerated_strategy
        assert wf2.visual_strategy == original
    finally:
        config.STUB = old_stub
    print("   ok — effective_visual_strategy prefers the latest regeneration "
          "over the original plan, without overwriting it")


def test_approved_strategy_unavailable_until_approval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        assert wf.approved_visual_strategy is None
        wf2 = review.regenerate_visual_plan(wf, "show a state change", [_section()])
        assert wf2.approved_visual_strategy is None
        approved = review.approve_visual_plan(wf2)
        assert approved.approved_visual_strategy is not None
        assert approved.approved_visual_strategy == approved.effective_visual_strategy
    finally:
        config.STUB = old_stub
    print("   ok — approved_visual_strategy is None until an explicit approve, "
          "before AND after a regeneration")


# -------------------------------------------------------------------------- 10
# Regeneration attempt count is tracked.

def test_regeneration_attempt_count_tracked():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        assert wf.visual_plan_approval.regeneration_attempts == 0
        wf = review.regenerate_visual_plan(wf, "reason one", [_section()])
        assert wf.visual_plan_approval.regeneration_attempts == 1
        wf = review.regenerate_visual_plan(wf, "reason two", [_section()])
        assert wf.visual_plan_approval.regeneration_attempts == 2
    finally:
        config.STUB = old_stub
    print("   ok — regeneration_attempts tracks the count exactly "
          "(requirement 10)")


# -------------------------------------------------------------------------- 11
# Regeneration limit works, is configurable, and is independent of the other
# two regeneration budgets.

def test_regeneration_limit_enforced_and_configurable():
    old_stub, old_limit = config.STUB, config.MAX_VISUAL_PLAN_REGENERATIONS
    config.STUB = True
    config.MAX_VISUAL_PLAN_REGENERATIONS = 2
    try:
        wf = _workflow()
        wf = review.regenerate_visual_plan(wf, "reason one", [_section()])
        wf = review.regenerate_visual_plan(wf, "reason two", [_section()])
        assert wf.visual_plan_approval.regeneration_attempts == 2
        try:
            review.regenerate_visual_plan(wf, "reason three", [_section()])
            raise AssertionError("a third regeneration should be refused at limit=2")
        except ValueError as e:
            assert "limit" in str(e).lower()
        assert wf.visual_plan_approval.status == "pending"
        assert wf.approved_visual_strategy is None
    finally:
        config.STUB, config.MAX_VISUAL_PLAN_REGENERATIONS = old_stub, old_limit
    print("   ok — MAX_VISUAL_PLAN_REGENERATIONS caps regeneration, is "
          "configurable, and never silently auto-approves at the limit "
          "(requirement 11)")


def test_all_three_regeneration_limits_are_independent():
    # The visual-plan counter must not share a budget with the question or
    # teaching-approach counters — see schema.VisualStrategyRegenerationAttempt's
    # "KEPT LOGICALLY SEPARATE".
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(stage="approach_approved")
        wf = review.regenerate_teaching_approach(wf, "teaching-approach reason", [_section()])
        assert wf.teaching_approach_approval.regeneration_attempts == 1
        assert wf.script is None    # invalidated by the teaching-approach regen
        wf = review.approve_teaching_approach(wf)
        wf = write_script_for_workflow(wf, _section())
        wf = plan_strategy_for_workflow(wf, _section())
        assert wf.visual_plan_approval.regeneration_attempts == 0
        wf = review.regenerate_visual_plan(wf, "visual-plan reason", [_section()])
        assert wf.visual_plan_approval.regeneration_attempts == 1
        # The teaching-approach counter is UNCHANGED by the visual-plan regen.
        assert wf.teaching_approach_approval.regeneration_attempts == 1
    finally:
        config.STUB = old_stub
    print("   ok — question, teaching-approach, and visual-plan regeneration "
          "attempts are all tracked independently (requirement 11)")


# -------------------------------------------------------------------------- 12
# Only approved plans pass the future rendering gate.

def test_only_approved_status_satisfies_the_gate():
    old_stub = config.STUB
    config.STUB = True
    try:
        for status in ("pending", "modified", "regenerating"):
            wf = _workflow()
            approval = wf.visual_plan_approval.model_copy(update={"status": status})
            wf = wf.model_copy(update={"visual_plan_approval": approval})
            assert wf.approved_visual_strategy is None, status
        approved = review.approve_visual_plan(_workflow())
        assert approved.approved_visual_strategy is not None
    finally:
        config.STUB = old_stub
    print("   ok — approved_visual_strategy is non-None ONLY for status="
          "'approved' (requirement 12)")


# -------------------------------------------------------------------------- 13
# Review cannot occur before all required upstream stages are complete.

def test_review_refused_before_question_approved():
    wf = _workflow(stage="pending")
    for fn, args in ((review.approve_visual_plan, ()),
                    (review.regenerate_visual_plan, ("a reason", [_section()]))):
        try:
            fn(wf, *args)
            raise AssertionError(f"{fn.__name__} should refuse a pending question")
        except ValueError as e:
            assert "question_approval" in str(e) or "approved" in str(e)
    print("   ok — visual-plan review is refused before the question itself "
          "is approved (requirement 13)")


def test_review_refused_before_framing_exists():
    wf = _workflow(stage="approved")
    assert wf.framing is None
    try:
        review.approve_visual_plan(wf)
        raise AssertionError("should refuse a workflow with no framing")
    except ValueError as e:
        assert "framing" in str(e).lower()
    print("   ok — visual-plan review is refused before framing exists "
          "(requirement 13)")


def test_review_refused_before_teaching_approach_approved():
    wf = _workflow(stage="approach")
    assert wf.approved_teaching_approach is None
    try:
        review.approve_visual_plan(wf)
        raise AssertionError("should refuse a workflow with no approved teaching approach")
    except ValueError as e:
        assert "teaching_approach_approval" in str(e) or "approved" in str(e)
    print("   ok — visual-plan review is refused before the teaching approach "
          "is approved (requirement 13)")


def test_review_refused_before_script_exists():
    wf = _workflow(stage="approach_approved")
    assert wf.script is None
    try:
        review.approve_visual_plan(wf)
        raise AssertionError("should refuse a workflow with no script")
    except ValueError as e:
        assert "script" in str(e).lower()
    print("   ok — visual-plan review is refused before a script has been "
          "generated (requirement 13)")


def test_review_refused_before_visual_strategy_exists():
    wf = _workflow(stage="scripted")
    assert wf.visual_strategy is None
    try:
        review.approve_visual_plan(wf)
        raise AssertionError("should refuse a workflow with no visual plan")
    except ValueError as e:
        assert "visual plan" in str(e).lower() or "visual_strategy" in str(e).lower()
    print("   ok — visual-plan review is refused before a visual plan has "
          "been generated (requirement 13)")


def test_gate_reachable_only_once_all_preconditions_hold():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(stage="planned")
        result = review.approve_visual_plan(wf)
        assert result.approved_visual_strategy is not None
    finally:
        config.STUB = old_stub
    print("   ok — review succeeds once question approval, framing, approved "
          "teaching approach, script and visual_strategy all hold "
          "(requirement 13)")


# -------------------------------------------------------------------------- 14
# CLI displays the plan.

def test_cli_displays_plan_information():
    wf = _workflow()
    import builtins
    responses = iter(["s"])   # leave pending, just check what was printed
    old_input = builtins.input
    builtins.input = lambda prompt="": next(responses)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            review.run_visual_plan_gate([wf], [_section()], interactive=True)
    finally:
        builtins.input = old_input

    out = buf.getvalue()
    assert wf.framing.teaching_question in out
    assert wf.visual_strategy.subject in out
    for b in wf.visual_strategy.beats:
        assert b.must_see in out
    print("   ok — the interactive gate prints the teaching question, subject, "
          "and every beat's must_see (requirement 14)")


# -------------------------------------------------------------------------- 15
# Non-interactive flow never blocks on input().

def test_non_interactive_gate_never_calls_input():
    import builtins

    def poison(prompt=""):
        raise AssertionError("run_visual_plan_gate must not call input() "
                             "when interactive=False")

    old_input = builtins.input
    builtins.input = poison
    try:
        workflows = [_workflow(), _workflow(id="t2")]
        result = review.run_visual_plan_gate(workflows, [_section()], interactive=False)
    finally:
        builtins.input = old_input

    assert len(result) == 2
    assert all(wf.visual_plan_approval.status == "pending" for wf in result), (
        "a non-interactive pass must leave every workflow exactly as it went in")
    print("   ok — interactive=False returns immediately without calling "
          "input() (requirement 15)")


def test_non_interactive_gate_handles_workflows_that_are_not_yet_reviewable():
    import builtins

    def poison(prompt=""):
        raise AssertionError("must not call input()")

    old_input = builtins.input
    builtins.input = poison
    try:
        workflows = [_workflow(stage="pending"), _workflow(stage="approved", id="t2"),
                    _workflow(stage="framed", id="t3"), _workflow(stage="approach", id="t4"),
                    _workflow(stage="approach_approved", id="t5"),
                    _workflow(stage="scripted", id="t6"), _workflow(stage="planned", id="t7")]
        result = review.run_visual_plan_gate(workflows, [_section()], interactive=False)
    finally:
        builtins.input = old_input
    assert len(result) == 7
    print("   ok — a mix of not-yet-reviewable and reviewable workflows is "
          "handled without blocking or crashing in non-interactive mode "
          "(requirement 15)")


# -------------------------------------------------------------------------- 16
# LLM call discipline.

def test_no_llm_call_for_approve_or_for_refused_regeneration():
    wf = _workflow()
    with patch("shorts.skills.strategy.ask_json", side_effect=AssertionError(
            "approving must not call the LLM")):
        review.approve_visual_plan(wf)
    pending_question_wf = _workflow(stage="pending")
    with patch("shorts.skills.strategy.ask_json", side_effect=AssertionError(
            "a refused regeneration must not call the LLM")):
        try:
            review.regenerate_visual_plan(pending_question_wf, "a reason", [_section()])
        except ValueError:
            pass
    print("   ok — approving spends no call, and a refused regeneration "
          "request never reaches the LLM (requirement 16)")


def test_exactly_one_llm_call_per_accepted_regeneration():
    wf = _workflow()
    calls = {"n": 0}
    real_ask_json = strategy_mod.ask_json

    def counting(*a, **kw):
        calls["n"] += 1
        return real_ask_json(*a, **kw)

    old_stub = config.STUB
    config.STUB = True
    try:
        with patch("shorts.skills.strategy.ask_json", side_effect=counting):
            review.regenerate_visual_plan(wf, "show a state change", [_section()])
    finally:
        config.STUB = old_stub
    assert calls["n"] == 1, f"expected exactly one LLM call, got {calls['n']}"
    print("   ok — one accepted regeneration spends exactly one LLM call "
          "(requirement 16)")


def test_idempotent_approve_repeated_call():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_visual_plan(_workflow())
        with patch("shorts.skills.strategy.ask_json", side_effect=AssertionError(
                "re-approving must not call the LLM")):
            wf2 = review.approve_visual_plan(wf)
    finally:
        config.STUB = old_stub
    assert wf2.approved_visual_strategy == wf.approved_visual_strategy
    print("   ok — approving an already-approved plan again spends no LLM "
          "call and leaves the plan unchanged (idempotency)")


# -------------------------------------------------------------------------- 17
# Preservation: regenerating the visual plan touches ONLY the visual-plan
# decision and approval state — nothing upstream.

def test_visual_plan_regeneration_preserves_every_upstream_field():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        before = dict(
            selection=wf.selection, question_approval=wf.question_approval,
            framing=wf.framing, teaching_approach=wf.teaching_approach,
            teaching_approach_approval=wf.teaching_approach_approval,
            script=wf.script,
        )
        wf2 = review.regenerate_visual_plan(wf, "show a state change", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.selection == before["selection"]
    assert wf2.question_approval == before["question_approval"]
    assert wf2.framing == before["framing"]
    assert wf2.teaching_approach == before["teaching_approach"]
    assert wf2.teaching_approach_approval == before["teaching_approach_approval"]
    assert wf2.script == before["script"]
    print("   ok — regenerating the visual plan leaves question selection, "
          "question approval, framing, teaching approach, teaching-approach "
          "approval, and script completely unchanged (requirement 17)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} visual-plan review (Step 11) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL VISUAL PLAN REVIEW TESTS PASSED.")


if __name__ == "__main__":
    main()
