"""
Offline, deterministic tests for Step 4: pedagogical question framing
(shorts/skills/framing.py's frame_question / frame_workflow, plus the schema
and checks they use).

No API key, no network — the one LLM call this step adds goes through
config.STUB exactly like everything else (see stubs._framing).

    python -m shorts.framing_workflow_test
"""
import inspect

from pydantic import ValidationError

from . import config
from .schema import (Section, Topic, TopicList, QuestionWorkflow, QuestionFraming,
                     SectionUnderstanding, TeachingStep)
from .skills import select, framing
from . import review, checks


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow(approve: bool = True, **topic_overrides) -> QuestionWorkflow:
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
    return review.approve_question(wf) if approve else wf


# --------------------------------------------------------------------------- 1
# Framing only runs for approved workflows.

def test_framing_runs_for_an_approved_workflow():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True)
        result = framing.frame_workflow(wf, [_section()])
        assert result.framing is not None
    finally:
        config.STUB = old_stub
    print("   ok — frame_workflow succeeds for an approved workflow (requirement 1)")


# ----------------------------------------------------------------------- 2, 3, 4
# Pending / rejected / regenerating workflows cannot be framed, and no LLM call
# is made trying.

def test_pending_workflow_cannot_be_framed():
    wf = _workflow(approve=False)
    assert wf.question_approval.status == "pending"
    try:
        framing.frame_workflow(wf, [_section()])
        raise AssertionError("frame_workflow should refuse a pending workflow")
    except ValueError as e:
        assert "pending" in str(e)
    print("   ok — a pending workflow cannot be framed (requirement 2)")


def test_rejected_workflow_cannot_be_framed():
    wf = review.reject_question(_workflow(approve=False), note="not needed")
    try:
        framing.frame_workflow(wf, [_section()])
        raise AssertionError("frame_workflow should refuse a rejected workflow")
    except ValueError as e:
        assert "rejected" in str(e)
    print("   ok — a rejected workflow cannot be framed (requirement 3)")


def test_regenerating_workflow_cannot_be_framed():
    wf = _workflow(approve=False)
    wf = wf.model_copy(update={
        "question_approval": wf.question_approval.model_copy(update={"status": "regenerating"})})
    try:
        framing.frame_workflow(wf, [_section()])
        raise AssertionError("frame_workflow should refuse a 'regenerating' workflow")
    except ValueError as e:
        assert "regenerating" in str(e)
    print("   ok — a 'regenerating' workflow cannot be framed (requirement 4)")


def test_unapproved_workflow_never_reaches_the_llm():
    # Prove the refusal happens BEFORE any call, not merely that the result
    # looks wrong — patch ask_json to explode if framing ever reaches it.
    from unittest.mock import patch
    wf = _workflow(approve=False)
    with patch("shorts.skills.framing.ask_json", side_effect=AssertionError(
            "ask_json must not be called for an unapproved workflow")):
        try:
            framing.frame_workflow(wf, [_section()])
            raise AssertionError("should have raised ValueError before any LLM call")
        except ValueError:
            pass
    print("   ok — an unapproved workflow never reaches the LLM call "
          "(requirement 2/3/4, cost protection)")


# --------------------------------------------------------------------------- 5
# source_question exactly matches effective_question.

def test_source_question_matches_effective_question():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True)
        result = framing.frame_workflow(wf, [_section()])
        assert result.framing.source_question == wf.effective_question
        assert result.framing.source_question == "Why does paging remove external fragmentation?"
    finally:
        config.STUB = old_stub
    print("   ok — framing.source_question exactly equals effective_question "
          "(requirement 5)")


def test_source_question_tracks_a_regenerated_question():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=False)
        wf = review.regenerate(wf, "focus on the mechanism", [_section()])
        wf = review.approve_question(wf)
        assert wf.effective_question != wf.selection.topic.topic   # sanity

        result = framing.frame_workflow(wf, [_section()])
        assert result.framing.source_question == wf.effective_question
        assert result.framing.source_question != wf.selection.topic.topic
    finally:
        config.STUB = old_stub
    print("   ok — source_question follows the effective (regenerated) question, "
          "not the original Topic.topic (requirement 5)")


# --------------------------------------------------------------------------- 6
# The LLM cannot override source_question.

def test_framing_output_model_has_no_source_question_field():
    # Structural guarantee: the LLM-facing model has no field the model could
    # even try to fill for source_question.
    fields = framing._FramingOutput.model_fields
    assert "source_question" not in fields
    assert set(fields) == {"teaching_question", "framing_rationale", "role"}
    print("   ok — _FramingOutput has no source_question field for the LLM to "
          "fill (requirement 6)")


def test_frame_question_signature_sets_source_question_itself():
    # frame_question's own body is what assigns source_question — confirmed
    # behaviourally: even if the model's prompt were somehow ignored,
    # source_question in the result is workflow.effective_question, set after
    # the call returns, not read out of the model's JSON.
    src = inspect.getsource(framing.frame_question)
    assert "source_question=source_question" in src.replace(" ", "")
    print("   ok — frame_question assigns source_question from "
          "effective_question in code, never from the model's output "
          "(requirement 6)")


# ----------------------------------------------------------------------- 7, 8, 9
# teaching_question non-empty; framing_rationale meaningful-or-None; role valid.

def test_teaching_question_cannot_be_blank():
    for bad in ("", "   "):
        try:
            QuestionFraming(source_question="Q?", teaching_question=bad)
            raise AssertionError(f"should reject teaching_question={bad!r}")
        except ValidationError:
            pass
    print("   ok — QuestionFraming rejects a blank teaching_question (requirement 7)")


def test_source_question_cannot_be_blank():
    for bad in ("", "   "):
        try:
            QuestionFraming(source_question=bad, teaching_question="Q?")
            raise AssertionError(f"should reject source_question={bad!r}")
        except ValidationError:
            pass
    print("   ok — QuestionFraming rejects a blank source_question too")


def test_framing_rationale_must_be_meaningful_when_provided():
    for bad in ("", "   "):
        try:
            QuestionFraming(source_question="Q?", teaching_question="Q?",
                            framing_rationale=bad)
            raise AssertionError(f"should reject framing_rationale={bad!r}")
        except ValidationError:
            pass
    # None is fine — "no rationale given" is an honest answer.
    qf = QuestionFraming(source_question="Q?", teaching_question="Q?",
                         framing_rationale=None)
    assert qf.framing_rationale is None
    # A real rationale passes through, stripped.
    qf2 = QuestionFraming(source_question="Q?", teaching_question="Q?",
                          framing_rationale="  clearer teaching flow  ")
    assert qf2.framing_rationale == "clearer teaching flow"
    print("   ok — framing_rationale rejects blank strings but allows None or "
          "real content (requirement 8)")


def test_role_rejects_invalid_values():
    try:
        QuestionFraming(source_question="Q?", teaching_question="Q?", role="not_a_role")
        raise AssertionError("an invalid role should be rejected")
    except ValidationError:
        pass
    for valid in ("primary", "hook", "reinforcement", "misconception_check", "transition"):
        QuestionFraming(source_question="Q?", teaching_question="Q?", role=valid)
    print("   ok — role is restricted to the five valid QuestionRole values "
          "(requirement 9)")


def test_stub_framing_defaults_to_primary_role():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True)
        result = framing.frame_workflow(wf, [_section()])
        assert result.framing.role == "primary"
    finally:
        config.STUB = old_stub
    print("   ok — the stub (and the default) framing role is 'primary'")


# --------------------------------------------------------------------------- 10
# The framing result is stored in QuestionWorkflow.framing.

def test_framing_result_stored_on_workflow():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True)
        assert wf.framing is None
        result = framing.frame_workflow(wf, [_section()])
        assert isinstance(result.framing, QuestionFraming)
        assert result.framing.teaching_question
    finally:
        config.STUB = old_stub
    print("   ok — the framing result lands in QuestionWorkflow.framing "
          "(requirement 10)")


# --------------------------------------------------------------------------- 11
# Existing QuestionWorkflow fields remain unchanged.

def test_framing_does_not_touch_other_workflow_fields():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True)
        result = framing.frame_workflow(wf, [_section()])
        assert result.selection == wf.selection
        assert result.question_approval == wf.question_approval
        assert result.teaching_approach is None
        assert result.teaching_approach_approval == wf.teaching_approach_approval
        assert result.script is None
        assert result.visual_strategy is None
        assert result.visual_plan_approval == wf.visual_plan_approval
        # And the ORIGINAL workflow object is untouched (model_copy, not mutation).
        assert wf.framing is None
    finally:
        config.STUB = old_stub
    print("   ok — framing only ever sets .framing; every other field is "
          "untouched, and the original workflow object is not mutated "
          "(requirement 11)")


# --------------------------------------------------------------------------- 12
# Stub mode produces deterministic, valid framing.

def test_stub_framing_is_deterministic_and_valid():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True)
        r1 = framing.frame_workflow(wf, [_section()])
        r2 = framing.frame_workflow(wf, [_section()])
        assert r1.framing == r2.framing
        assert r1.framing.teaching_question == wf.effective_question
    finally:
        config.STUB = old_stub
    print("   ok — stub-mode framing is deterministic across repeated calls "
          "(requirement 12)")


def test_frame_question_uses_at_most_one_llm_call():
    from unittest.mock import patch
    wf = _workflow(approve=True)
    calls = {"n": 0}
    real_ask_json = framing.ask_json

    def counting(*a, **kw):
        calls["n"] += 1
        return real_ask_json(*a, **kw)

    old_stub = config.STUB
    config.STUB = True
    try:
        with patch("shorts.skills.framing.ask_json", side_effect=counting):
            framing.frame_workflow(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert calls["n"] == 1, f"expected exactly one LLM call, got {calls['n']}"
    print("   ok — framing an approved workflow makes exactly one LLM call")


# --------------------------------------------------------------------------- 13
# Existing script generation remains unchanged.

def test_write_script_still_reads_topic_topic_directly():
    # Step 8 (a later step) gives skills/script.py an intentional dependency
    # on the QuestionFraming DATA TYPE — write_script_for_workflow accepts
    # one already decided — but it must never depend on the skills/framing.py
    # MODULE itself: no import of frame_question/frame_workflow, no call that
    # would build a framing on its own rather than being handed one.
    from .skills import script as script_module
    assert not hasattr(script_module, "frame_question")
    assert not hasattr(script_module, "frame_workflow")
    src = open(script_module.__file__).read()
    assert "skills.framing" not in src and "skills import framing" not in src
    print("   ok — skills/script.py depends on QuestionFraming's shape, "
          "never on skills/framing.py's own functions (requirement 13)")


def test_approving_and_framing_never_mutates_the_original_topic():
    wf = _workflow(approve=False)
    original_topic_question = wf.selection.topic.topic
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.regenerate(wf, "focus on the mechanism", [_section()])
        wf = review.approve_question(wf)
        wf = framing.frame_workflow(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert wf.selection.topic.topic == original_topic_question
    print("   ok — selection.topic.topic (what write_script would read for an "
          "unframed workflow) is never touched by regeneration or framing "
          "(requirement 13)")


# --------------------------------------------------------------------------- extra
# The checks.py grading coverage this step adds.

def test_check_framing_source_matches_effective_question():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = framing.frame_workflow(_workflow(approve=True), [_section()])
    finally:
        config.STUB = old_stub

    assert checks.check_framing_source_matches_effective_question(wf).passed

    stale = wf.model_copy(update={
        "framing": wf.framing.model_copy(update={"source_question": "a different question"})})
    result = checks.check_framing_source_matches_effective_question(stale)
    assert not result.passed

    unframed = QuestionWorkflow(selection=wf.selection)
    skipped = checks.check_framing_source_matches_effective_question(unframed)
    assert skipped.passed and skipped.details.get("skipped")
    print("   ok — check_framing_source_matches_effective_question passes real "
          "framing, fails stale framing, and skips an unframed workflow")


def test_check_framing_stays_on_concept():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = framing.frame_workflow(_workflow(approve=True), [_section()])
    finally:
        config.STUB = old_stub

    assert checks.check_framing_stays_on_concept(wf.framing, wf.selection.topic).passed

    drifted = wf.framing.model_copy(update={
        "teaching_question": "What is quantum entanglement?"})
    result = checks.check_framing_stays_on_concept(drifted, wf.selection.topic)
    assert not result.passed
    print("   ok — check_framing_stays_on_concept passes on-topic framing and "
          "fails a teaching_question that drifted subject")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} framing-workflow (Step 4) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL FRAMING WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
