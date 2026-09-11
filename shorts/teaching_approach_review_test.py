"""
Offline, deterministic tests for Step 6: human review of the LLM-selected
TeachingApproach (shorts/review.py's approve_teaching_approach /
regenerate_teaching_approach / run_teaching_approach_gate, plus the schema
they operate on).

No API key, no network — every LLM call here goes through config.STUB exactly
like Steps 3-5 (see stubs._teaching_approach, reused for both the initial
decision and a regeneration since both target the same TeachingApproach model).

    python -m shorts.teaching_approach_review_test
"""
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from pydantic import ValidationError

from . import config
from .schema import (Section, Topic, TopicList, QuestionWorkflow, TeachingApproach,
                     TeachingApproachApproval, TeachingApproachRegenerationAttempt)
from .skills import select, framing, teaching_approach
from . import review


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow(stage: str = "approach", **topic_overrides) -> QuestionWorkflow:
    """
    Build a workflow at a given stage:
      "pending"   just selected, question still pending
      "approved"  question approved, no framing
      "framed"    question approved and framed, no teaching_approach
      "approach"  question approved, framed, and a teaching_approach chosen
                  (the ordinary starting point for these tests)
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
        return wf
    finally:
        config.STUB = old_stub


# --------------------------------------------------------------------------- 1
# Teaching approach can be approved.

def test_teaching_approach_can_be_approved():
    wf = review.approve_teaching_approach(_workflow())
    assert wf.teaching_approach_approval.status == "approved"
    assert wf.approved_teaching_approach is not None
    print("   ok — a teaching approach can be approved (requirement 1)")


# --------------------------------------------------------------------------- 2
# Pending approach cannot proceed.

def test_pending_approach_cannot_proceed():
    wf = _workflow()
    assert wf.teaching_approach_approval.status == "pending"
    assert wf.approved_teaching_approach is None
    print("   ok — a pending teaching_approach_approval blocks "
          "approved_teaching_approach (requirement 2)")


def test_legacy_modified_status_does_not_proceed_either():
    # "modified" is kept ONLY for legacy data (the old override-based flow).
    # It must not satisfy the new gate, same as "pending".
    wf = _workflow()
    legacy = wf.teaching_approach_approval.model_copy(update={
        "status": "modified", "override": wf.teaching_approach})
    wf = wf.model_copy(update={"teaching_approach_approval": legacy})
    assert wf.approved_teaching_approach is None
    print("   ok — legacy 'modified' status does not satisfy the gate either")


def test_regenerating_status_cannot_proceed():
    wf = _workflow()
    wf = wf.model_copy(update={"teaching_approach_approval":
        wf.teaching_approach_approval.model_copy(update={"status": "regenerating"})})
    assert wf.approved_teaching_approach is None
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
                review.regenerate_teaching_approach(wf, bad, [_section()])
                raise AssertionError(f"should reject reason={bad!r}")
            except ValueError:
                pass
    finally:
        config.STUB = old_stub
    print("   ok — regenerate_teaching_approach refuses a missing/blank reason "
          "before calling the LLM (requirement 3)")


def test_regeneration_attempt_schema_rejects_blank_reason():
    for bad in ("", "   "):
        try:
            TeachingApproachRegenerationAttempt(
                reason=bad, previous_approach=TeachingApproach(primary="analogy"),
                regenerated_approach=TeachingApproach(primary="comparison"))
            raise AssertionError(f"should reject reason={bad!r}")
        except ValidationError:
            pass
    print("   ok — TeachingApproachRegenerationAttempt rejects a blank reason "
          "at the schema level too (requirement 3)")


# --------------------------------------------------------------------------- 4
# The human cannot directly override individual approach fields.

def test_approve_takes_no_field_override_arguments():
    import inspect
    params = list(inspect.signature(review.approve_teaching_approach).parameters)
    assert params == ["workflow", "note"]
    print("   ok — approve_teaching_approach accepts no primary/combined_with/"
          "alternatives/rationale arguments (requirement 4)")


def test_regenerate_takes_no_field_override_arguments():
    import inspect
    params = list(inspect.signature(review.regenerate_teaching_approach).parameters)
    assert "primary" not in params and "rationale" not in params
    assert params == ["workflow", "reason", "sections", "understanding"]
    print("   ok — regenerate_teaching_approach accepts only `reason`, never "
          "individual field overrides (requirement 4)")


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
        review.run_teaching_approach_gate([wf], [_section()], interactive=True)
    finally:
        builtins.input = old_input

    assert prompts
    lowered = prompts[0].lower()
    assert "edit" not in lowered and "override" not in lowered
    assert "[g]enerate again" in prompts[0]
    print("   ok — the interactive gate's prompt offers approve/regenerate/"
          "skip/quit only, never field editing (requirement 4)")


# --------------------------------------------------------------------------- 5
# Previous approach is preserved.

def test_previous_approach_preserved_in_history():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        original = wf.teaching_approach
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary", [_section()])
        history = wf2.teaching_approach_approval.regeneration_history
        assert len(history) == 1
        assert history[0].previous_approach == original
        # And the ORIGINAL teaching_approach field itself is untouched.
        assert wf2.teaching_approach == original
    finally:
        config.STUB = old_stub
    print("   ok — the previous TeachingApproach is preserved in "
          "regeneration_history, and workflow.teaching_approach is never "
          "overwritten (requirement 5)")


def test_previous_approach_chains_across_multiple_regenerations():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf = review.regenerate_teaching_approach(wf, "code is not necessary", [_section()])
        first_regen = wf.teaching_approach_approval.regenerated_approach
        wf = review.regenerate_teaching_approach(wf, "make it a comparison instead", [_section()])
        history = wf.teaching_approach_approval.regeneration_history
        assert len(history) == 2
        # The SECOND attempt starts from what the FIRST one produced.
        assert history[1].previous_approach == first_regen
    finally:
        config.STUB = old_stub
    print("   ok — each regeneration's previous_approach is the prior "
          "regeneration's result, forming a real chain (requirement 5)")


# --------------------------------------------------------------------------- 6
# Regeneration reason is preserved.

def test_regeneration_reason_preserved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf = review.regenerate_teaching_approach(
            wf, "a real-world example would explain this better", [_section()])
        history = wf.teaching_approach_approval.regeneration_history
        assert history[0].reason == "a real-world example would explain this better"
    finally:
        config.STUB = old_stub
    print("   ok — the human's regeneration reason is preserved verbatim in "
          "history (requirement 6)")


# --------------------------------------------------------------------------- 7
# Regeneration calls the approach decision as a complete decision, never a
# partial patch.

def test_regeneration_produces_a_complete_independent_decision():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf2 = review.regenerate_teaching_approach(wf, "make it a comparison", [_section()])
        regenerated = wf2.teaching_approach_approval.regenerated_approach
        # The regenerated approach is a fully-formed, independently valid
        # TeachingApproach — not a dict with only `primary` set.
        assert isinstance(regenerated, TeachingApproach)
        assert regenerated.primary
        assert isinstance(regenerated.combined_with, list)
        assert isinstance(regenerated.alternatives, list)
        assert isinstance(regenerated.rationale, str)
    finally:
        config.STUB = old_stub
    print("   ok — regeneration returns a complete TeachingApproach "
          "(primary + combined_with + alternatives + rationale together), "
          "never a partial patch (requirement 7)")


def test_reconsider_teaching_approach_prompt_shows_the_previous_decision():
    # Confirm the LLM call is actually GIVEN the previous decision and the
    # reason — not silently starting over with no context.
    captured = {}
    real_ask_json = teaching_approach.ask_json

    def spy(system, user, model_cls, **kw):
        captured["user"] = user
        captured["system"] = system
        return real_ask_json(system, user, model_cls, **kw)

    old_stub = config.STUB
    config.STUB = True
    teaching_approach.ask_json = spy
    try:
        wf = _workflow()
        review.regenerate_teaching_approach(wf, "code is not necessary for this concept",
                                            [_section()])
    finally:
        teaching_approach.ask_json = real_ask_json
        config.STUB = old_stub

    assert "THE PREVIOUS DECISION" in captured["user"]
    assert "direct_explanation" in captured["user"]   # the stub's initial primary
    assert "code is not necessary for this concept" in captured["user"]
    assert captured["system"] == teaching_approach.TEACHING_APPROACH_REGENERATE_SYSTEM
    print("   ok — regeneration's prompt includes the previous decision and "
          "the human's reason, using the dedicated reconsideration system "
          "prompt (requirement 7)")


# --------------------------------------------------------------------------- 8
# Regenerated approach returns to pending.

def test_regeneration_returns_to_pending_never_approved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_teaching_approach(_workflow())     # start APPROVED
        assert wf.teaching_approach_approval.status == "approved"
        wf = review.regenerate_teaching_approach(wf, "make it a comparison", [_section()])
        assert wf.teaching_approach_approval.status == "pending", (
            "regenerating an approved approach must drop it back to pending")
        assert wf.approved_teaching_approach is None
    finally:
        config.STUB = old_stub
    print("   ok — regenerating (even an already-approved approach) always "
          "lands on pending, never approved (requirement 8)")


# --------------------------------------------------------------------------- 9
# Regenerated approach requires explicit approval.

def test_regenerated_approach_requires_a_fresh_explicit_approve():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.regenerate_teaching_approach(_workflow(), "make it a comparison",
                                                  [_section()])
        assert wf.approved_teaching_approach is None
        wf = review.approve_teaching_approach(wf)
        assert wf.approved_teaching_approach is not None
        assert wf.approved_teaching_approach == wf.teaching_approach_approval.regenerated_approach
    finally:
        config.STUB = old_stub
    print("   ok — a regenerated approach proceeds only after a fresh, "
          "explicit approve_teaching_approach call (requirement 9)")


# -------------------------------------------------------------------------- 10
# Regeneration attempt count is tracked.

def test_regeneration_attempt_count_tracked():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        assert wf.teaching_approach_approval.regeneration_attempts == 0
        wf = review.regenerate_teaching_approach(wf, "reason one", [_section()])
        assert wf.teaching_approach_approval.regeneration_attempts == 1
        wf = review.regenerate_teaching_approach(wf, "reason two", [_section()])
        assert wf.teaching_approach_approval.regeneration_attempts == 2
    finally:
        config.STUB = old_stub
    print("   ok — regeneration_attempts tracks the count exactly "
          "(requirement 10)")


# -------------------------------------------------------------------------- 11
# Regeneration limit works, and does not silently auto-approve.

def test_regeneration_limit_enforced_and_configurable():
    old_stub, old_limit = config.STUB, config.MAX_TEACHING_APPROACH_REGENERATIONS
    config.STUB = True
    config.MAX_TEACHING_APPROACH_REGENERATIONS = 2
    try:
        wf = _workflow()
        wf = review.regenerate_teaching_approach(wf, "reason one", [_section()])
        wf = review.regenerate_teaching_approach(wf, "reason two", [_section()])
        assert wf.teaching_approach_approval.regeneration_attempts == 2
        try:
            review.regenerate_teaching_approach(wf, "reason three", [_section()])
            raise AssertionError("a third regeneration should be refused at limit=2")
        except ValueError as e:
            assert "limit" in str(e).lower()
        # AND IT IS NOT SILENTLY APPROVED — hitting the limit leaves the
        # workflow exactly where it was: pending, not proceedable.
        assert wf.teaching_approach_approval.status == "pending"
        assert wf.approved_teaching_approach is None
    finally:
        config.STUB, config.MAX_TEACHING_APPROACH_REGENERATIONS = old_stub, old_limit
    print("   ok — MAX_TEACHING_APPROACH_REGENERATIONS caps regeneration, is "
          "configurable, and never silently auto-approves at the limit "
          "(requirement 11)")


def test_question_and_teaching_approach_regeneration_limits_are_independent():
    # The two counters must not share a budget — see schema.
    # TeachingApproachRegenerationAttempt's "KEPT LOGICALLY SEPARATE".
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(stage="framed")
        wf = review.regenerate(wf, "question wording reason", [_section()])
        assert wf.question_approval.regeneration_attempts == 1
        # Regenerating the QUESTION always lands back on pending (Step 3) —
        # re-approve so the teaching-approach gate below can even run. Step
        # 7.1 ALSO clears framing (it was decided for the OLD question), so
        # re-framing before choosing a teaching approach is now required,
        # not optional — see schema.QuestionWorkflow.invalidate_downstream.
        assert wf.question_approval.status == "pending"
        assert wf.framing is None
        wf = review.approve_question(wf)
        wf = framing.frame_workflow(wf, [_section()])
        wf = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        assert wf.teaching_approach_approval.regeneration_attempts == 0
    finally:
        config.STUB = old_stub
    print("   ok — question regeneration attempts and teaching-approach "
          "regeneration attempts are tracked independently (requirement 11)")


# -------------------------------------------------------------------------- 12
# Only approved approaches pass the future-stage gate.

def test_only_approved_status_satisfies_the_gate():
    old_stub = config.STUB
    config.STUB = True
    try:
        for status in ("pending", "modified", "regenerating"):
            wf = _workflow()
            approval = wf.teaching_approach_approval.model_copy(update={"status": status})
            wf = wf.model_copy(update={"teaching_approach_approval": approval})
            assert wf.approved_teaching_approach is None, status
        approved = review.approve_teaching_approach(_workflow())
        assert approved.approved_teaching_approach is not None
    finally:
        config.STUB = old_stub
    print("   ok — approved_teaching_approach is non-None ONLY for status="
          "'approved' (requirement 12)")


# -------------------------------------------------------------------------- 13
# Review cannot occur before approved question + framing + approach.

def test_review_refused_before_question_approved():
    wf = _workflow(stage="pending")
    for fn, args in ((review.approve_teaching_approach, ()),
                    (review.regenerate_teaching_approach, ("a reason", [_section()]))):
        try:
            fn(wf, *args)
            raise AssertionError(f"{fn.__name__} should refuse a pending question")
        except ValueError as e:
            assert "question_approval" in str(e) or "not \'approved\'" in str(e) or "approved" in str(e)
    print("   ok — teaching-approach review is refused before the question "
          "itself is approved (requirement 13)")


def test_review_refused_before_framing_exists():
    wf = _workflow(stage="approved")
    assert wf.framing is None
    try:
        review.approve_teaching_approach(wf)
        raise AssertionError("should refuse a workflow with no framing")
    except ValueError as e:
        assert "framing" in str(e).lower()
    print("   ok — teaching-approach review is refused before framing exists "
          "(requirement 13)")


def test_review_refused_before_teaching_approach_exists():
    wf = _workflow(stage="framed")
    assert wf.teaching_approach is None
    try:
        review.approve_teaching_approach(wf)
        raise AssertionError("should refuse a workflow with no teaching_approach")
    except ValueError as e:
        assert "teaching_approach" in str(e).lower() or "chosen" in str(e).lower()
    print("   ok — teaching-approach review is refused before a "
          "teaching_approach has been chosen (requirement 13)")


def test_gate_reachable_only_once_all_preconditions_hold():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(stage="approach")
        result = review.approve_teaching_approach(wf)
        assert result.approved_teaching_approach is not None
    finally:
        config.STUB = old_stub
    print("   ok — review succeeds once question approval, framing and "
          "teaching_approach all hold (requirement 13)")


# -------------------------------------------------------------------------- 14
# CLI displays the complete approach information.

def test_cli_displays_complete_approach_information():
    old_stub = config.STUB
    config.STUB = True
    try:
        base = _workflow(stage="approach")
        approach = TeachingApproach(primary="comparison", combined_with=["conceptual_visual"],
                                    alternatives=["process_demonstration"],
                                    rationale="Contiguous allocation and paging are best taught side by side.")
        wf = base.model_copy(update={"teaching_approach": approach})
    finally:
        config.STUB = old_stub

    import builtins
    responses = iter(["s"])   # leave pending, just check what was printed
    old_input = builtins.input
    builtins.input = lambda prompt="": next(responses)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            review.run_teaching_approach_gate([wf], [_section()], interactive=True)
    finally:
        builtins.input = old_input

    out = buf.getvalue()
    assert wf.framing.teaching_question in out
    assert "comparison" in out
    assert "conceptual_visual" in out
    assert "process_demonstration" in out
    assert "Contiguous allocation and paging are best taught side by side." in out
    print("   ok — the interactive gate prints the teaching question, primary, "
          "combined_with, alternatives, and rationale (requirement 14)")


# -------------------------------------------------------------------------- 16
# Non-interactive flow never blocks on input().

def test_non_interactive_gate_never_calls_input():
    import builtins

    def poison(prompt=""):
        raise AssertionError("run_teaching_approach_gate must not call input() "
                             "when interactive=False")

    old_input = builtins.input
    builtins.input = poison
    try:
        workflows = [_workflow(), _workflow(id="t2")]
        result = review.run_teaching_approach_gate(workflows, [_section()],
                                                    interactive=False)
    finally:
        builtins.input = old_input

    assert len(result) == 2
    assert all(wf.teaching_approach_approval.status == "pending" for wf in result), (
        "a non-interactive pass must leave every workflow exactly as it went in")
    print("   ok — interactive=False returns immediately without calling "
          "input() (requirement 16)")


def test_non_interactive_gate_handles_workflows_that_are_not_yet_reviewable():
    # A mix of stages — the gate must not crash or block on a workflow that
    # is not yet reviewable, and must still report all of them back unchanged.
    import builtins

    def poison(prompt=""):
        raise AssertionError("must not call input()")

    old_input = builtins.input
    builtins.input = poison
    try:
        workflows = [_workflow(stage="pending"), _workflow(stage="approved", id="t2"),
                    _workflow(stage="framed", id="t3"), _workflow(stage="approach", id="t4")]
        result = review.run_teaching_approach_gate(workflows, [_section()],
                                                    interactive=False)
    finally:
        builtins.input = old_input
    assert len(result) == 4
    print("   ok — a mix of not-yet-reviewable and reviewable workflows is "
          "handled without blocking or crashing in non-interactive mode "
          "(requirement 16)")


# -------------------------------------------------------------------------- 17
# No downstream expensive work starts before approach approval.

def test_no_llm_call_for_approve_or_for_refused_regeneration():
    wf = _workflow()
    with patch("shorts.skills.teaching_approach.ask_json", side_effect=AssertionError(
            "approving must not call the LLM")):
        review.approve_teaching_approach(wf)
    # A regeneration refused for a bad precondition/reason must not reach the
    # LLM either.
    pending_question_wf = _workflow(stage="pending")
    with patch("shorts.skills.teaching_approach.ask_json", side_effect=AssertionError(
            "a refused regeneration must not call the LLM")):
        try:
            review.regenerate_teaching_approach(pending_question_wf, "a reason", [_section()])
        except ValueError:
            pass
    print("   ok — approving spends no call, and a refused regeneration "
          "request never reaches the LLM (requirement 17)")


def test_exactly_one_llm_call_per_accepted_regeneration():
    wf = _workflow()
    calls = {"n": 0}
    real_ask_json = teaching_approach.ask_json

    def counting(*a, **kw):
        calls["n"] += 1
        return real_ask_json(*a, **kw)

    old_stub = config.STUB
    config.STUB = True
    try:
        with patch("shorts.skills.teaching_approach.ask_json", side_effect=counting):
            review.regenerate_teaching_approach(wf, "make it a comparison", [_section()])
    finally:
        config.STUB = old_stub
    assert calls["n"] == 1, f"expected exactly one LLM call, got {calls['n']}"
    print("   ok — one accepted regeneration spends exactly one LLM call "
          "(requirement 17)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} teaching-approach review (Step 6) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL TEACHING APPROACH REVIEW TESTS PASSED.")


if __name__ == "__main__":
    main()
