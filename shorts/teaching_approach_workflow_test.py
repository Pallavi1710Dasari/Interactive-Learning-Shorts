"""
Offline, deterministic tests for Step 5: LLM-selected teaching approach
(shorts/skills/teaching_approach.py's choose_teaching_approach /
choose_teaching_approach_for_workflow, plus the checks they lean on).

No API key, no network — the one LLM call this step adds goes through
config.STUB exactly like Steps 3 and 4 (see stubs._teaching_approach).

    python -m shorts.teaching_approach_workflow_test
"""
from unittest.mock import patch

from pydantic import ValidationError

from . import config
from .schema import (Section, Topic, TopicList, QuestionWorkflow, TeachingApproach,
                     TeachingApproachKind)
from .skills import select, framing, teaching_approach
from . import review, checks


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow(approve: bool = True, frame: bool = True, **topic_overrides) -> QuestionWorkflow:
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
    if not approve:
        return wf
    wf = review.approve_question(wf)
    if frame:
        old_stub = config.STUB
        config.STUB = True
        try:
            wf = framing.frame_workflow(wf, [_section()])
        finally:
            config.STUB = old_stub
    return wf


# --------------------------------------------------------------------------- 1
# Teaching approach only runs for approved (and framed) workflows.

def test_teaching_approach_runs_for_an_approved_framed_workflow():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True, frame=True)
        result = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        assert result.teaching_approach is not None
    finally:
        config.STUB = old_stub
    print("   ok — an approved, framed workflow gets a teaching approach (requirement 1)")


# ------------------------------------------------------------------------ 2, 3, 4
# Pending / rejected / regenerating workflows are refused, before any LLM call.

def test_pending_workflow_refused():
    wf = _workflow(approve=False)
    try:
        teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        raise AssertionError("should refuse a pending workflow")
    except ValueError as e:
        assert "pending" in str(e)
    print("   ok — a pending workflow cannot receive a teaching approach (requirement 2)")


def test_rejected_workflow_refused():
    wf = review.reject_question(_workflow(approve=False), note="not needed")
    try:
        teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        raise AssertionError("should refuse a rejected workflow")
    except ValueError as e:
        assert "rejected" in str(e)
    print("   ok — a rejected workflow cannot receive a teaching approach (requirement 3)")


def test_regenerating_workflow_refused():
    wf = _workflow(approve=False)
    wf = wf.model_copy(update={
        "question_approval": wf.question_approval.model_copy(update={"status": "regenerating"})})
    try:
        teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        raise AssertionError("should refuse a 'regenerating' workflow")
    except ValueError as e:
        assert "regenerating" in str(e)
    print("   ok — a 'regenerating' workflow cannot receive a teaching approach (requirement 4)")


def test_unapproved_workflow_never_reaches_the_llm():
    wf = _workflow(approve=False)
    with patch("shorts.skills.teaching_approach.ask_json", side_effect=AssertionError(
            "ask_json must not be called for an unapproved workflow")):
        try:
            teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
            raise AssertionError("should have raised before any LLM call")
        except ValueError:
            pass
    print("   ok — an unapproved workflow never reaches the LLM call "
          "(requirements 2/3/4, cost protection)")


# --------------------------------------------------------------------------- 5
# Workflows without valid framing cannot receive an approach, and framing is
# never silently created.

def test_unframed_approved_workflow_refused():
    wf = _workflow(approve=True, frame=False)
    assert wf.question_approval.status == "approved"
    assert wf.framing is None
    try:
        teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        raise AssertionError("should refuse an approved-but-unframed workflow")
    except ValueError as e:
        assert "framing" in str(e).lower()
    print("   ok — an approved workflow with no framing cannot receive a "
          "teaching approach (requirement 5)")


def test_unframed_workflow_never_calls_frame_workflow_or_the_llm():
    # Prove framing is genuinely never built on the caller's behalf — patch
    # BOTH the framing entry point and the LLM call to explode if reached.
    wf = _workflow(approve=True, frame=False)
    with patch("shorts.skills.framing.frame_workflow",
              side_effect=AssertionError("framing must not be created implicitly")), \
        patch("shorts.skills.teaching_approach.ask_json",
              side_effect=AssertionError("ask_json must not be called without framing")):
        try:
            teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
            raise AssertionError("should have raised before building framing or calling the LLM")
        except ValueError:
            pass
    print("   ok — an unframed workflow never triggers framing internally, and "
          "never reaches the LLM (requirement 5, 'do not silently create framing')")


# --------------------------------------------------------------------------- 6
# Exactly one primary approach is required — the schema's own contract.

def test_primary_is_required_with_no_default():
    try:
        TeachingApproach()
        raise AssertionError("TeachingApproach() should require `primary`")
    except ValidationError:
        pass
    ta = TeachingApproach(primary="analogy")
    assert ta.primary == "analogy"
    print("   ok — TeachingApproach requires an explicit primary, no default "
          "(requirement 6)")


def test_primary_must_be_a_valid_kind():
    try:
        TeachingApproach(primary="not_a_real_kind")
        raise AssertionError("an invalid primary kind should be rejected")
    except ValidationError:
        pass
    print("   ok — primary is restricted to the seven valid "
          "TeachingApproachKind values (requirement 6)")


# --------------------------------------------------------------------------- 7
# The approach is stored in workflow.teaching_approach.

def test_result_stored_on_workflow():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True, frame=True)
        assert wf.teaching_approach is None
        result = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        assert isinstance(result.teaching_approach, TeachingApproach)
        assert result.teaching_approach.primary
    finally:
        config.STUB = old_stub
    print("   ok — the approach lands in QuestionWorkflow.teaching_approach "
          "(requirement 7)")


# --------------------------------------------------------------------------- 8
# Existing workflow fields remain unchanged; selection/question_approval/
# framing/script/visual_strategy are never modified by this step.

def test_other_workflow_fields_untouched():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True, frame=True)
        result = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        assert result.selection == wf.selection
        assert result.question_approval == wf.question_approval
        assert result.framing == wf.framing
        assert result.script is None
        assert result.visual_strategy is None
        assert result.visual_plan_approval == wf.visual_plan_approval
        assert result.teaching_approach_approval == wf.teaching_approach_approval
        # And the original object passed in is not mutated.
        assert wf.teaching_approach is None
    finally:
        config.STUB = old_stub
    print("   ok — only .teaching_approach is written; every other field, and "
          "the original workflow object, is untouched (requirement 8)")


# --------------------------------------------------------------------------- 9
# Stub mode produces a valid, deterministic approach.

def test_stub_mode_is_deterministic_and_valid():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(approve=True, frame=True)
        r1 = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        r2 = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
        assert r1.teaching_approach == r2.teaching_approach
        assert r1.teaching_approach.primary in TeachingApproachKind.__args__
    finally:
        config.STUB = old_stub
    print("   ok — stub-mode teaching approach is deterministic and a valid "
          "TeachingApproachKind (requirement 9)")


# -------------------------------------------------------------------------- 10
# Code is not automatically selected simply because source material contains
# code.

def test_stub_never_selects_code_even_with_code_in_the_section():
    old_stub = config.STUB
    config.STUB = True
    try:
        code_section = Section(
            section_id="4.1", title="The static keyword",
            text=("A static method belongs to the class rather than an instance. "
                 "```java\nclass Counter {\n  static int count = 0;\n}\n```\n"
                 "Calling Counter.count does not require creating an instance."),
            start_line=1, end_line=10,
        )
        wf = _workflow(approve=True, frame=False, source_section_id="4.1",
                       concept="the static keyword")
        wf = framing.frame_workflow(wf, [code_section])
        result = teaching_approach.choose_teaching_approach_for_workflow(
            wf, [code_section])
        # The STUB never reaches for code — see stubs._teaching_approach's own
        # docstring: the mechanical path always returns direct_explanation, so
        # a section containing a fenced code block proves nothing was
        # hardcoded to notice and prefer it.
        assert result.teaching_approach.primary != "code"
    finally:
        config.STUB = old_stub
    print("   ok — a section containing code does not make the mechanical path "
          "select `code` (requirement 10)")


def test_code_by_default_check_catches_an_availability_excuse():
    lazy = TeachingApproach(primary="code",
                            rationale="The section contains code, so we use code.")
    result = checks.check_teaching_approach_not_code_by_default(lazy)
    assert not result.passed
    print("   ok — check_teaching_approach_not_code_by_default fails a "
          "rationale that justifies code by availability (requirement 10)")


def test_code_by_default_check_passes_a_necessity_rationale():
    justified = TeachingApproach(
        primary="code",
        rationale="The question asks specifically what the static keyword "
                  "changes about method syntax, which cannot be shown without "
                  "the written form.")
    result = checks.check_teaching_approach_not_code_by_default(justified)
    assert result.passed
    print("   ok — check_teaching_approach_not_code_by_default passes a "
          "rationale grounded in necessity, not availability")


def test_code_by_default_check_skips_non_code_approaches():
    other = TeachingApproach(primary="process_demonstration", rationale="x")
    result = checks.check_teaching_approach_not_code_by_default(other)
    assert result.passed and result.details.get("skipped")
    print("   ok — the code-by-default check skips approaches that did not "
          "select code at all")


# -------------------------------------------------------------------------- 11
# combined_with is not required.

def test_combined_with_is_not_required():
    ta = TeachingApproach(primary="direct_explanation")
    assert ta.combined_with == []
    print("   ok — combined_with defaults to an empty list; it is never "
          "required (requirement 11)")


# -------------------------------------------------------------------------- 12
# alternatives are valid TeachingApproachKind values.

def test_alternatives_must_be_valid_kinds():
    TeachingApproach(primary="analogy", alternatives=["comparison", "conceptual_visual"])
    try:
        TeachingApproach(primary="analogy", alternatives=["not_a_real_kind"])
        raise AssertionError("an invalid alternative kind should be rejected")
    except ValidationError:
        pass
    print("   ok — alternatives are restricted to valid TeachingApproachKind "
          "values (requirement 12)")


# -------------------------------------------------------------------------- 13
# The workflow-level function performs at most one LLM call.

def test_workflow_level_function_makes_exactly_one_llm_call():
    wf = _workflow(approve=True, frame=True)
    calls = {"n": 0}
    real_ask_json = teaching_approach.ask_json

    def counting(*a, **kw):
        calls["n"] += 1
        return real_ask_json(*a, **kw)

    old_stub = config.STUB
    config.STUB = True
    try:
        with patch("shorts.skills.teaching_approach.ask_json", side_effect=counting):
            teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert calls["n"] == 1, f"expected exactly one LLM call, got {calls['n']}"
    print("   ok — choosing a teaching approach makes exactly one LLM call "
          "(requirement 13)")


def test_understanding_is_never_fetched_internally():
    # If this step ever starts calling understanding_for itself, that is a
    # SECOND call riding along on top of its own — patch it to explode.
    wf = _workflow(approve=True, frame=True)
    old_stub = config.STUB
    config.STUB = True
    try:
        with patch("shorts.skills.understanding.understanding_for",
                  side_effect=AssertionError(
                      "teaching_approach must not fetch its own understanding")):
            teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
    finally:
        config.STUB = old_stub
    print("   ok — choose_teaching_approach never calls understanding_for "
          "itself (requirement 13, 'reuse when supplied')")


# -------------------------------------------------------------------------- 14
# Existing script generation remains unchanged.

def test_write_script_has_no_dependency_on_teaching_approach():
    # Step 8 (a later step) gives skills/script.py an intentional dependency
    # on the TeachingApproach DATA TYPE — write_script_for_workflow accepts
    # one already approved — but it must never depend on the
    # skills/teaching_approach.py MODULE itself: no import of
    # choose_teaching_approach/choose_teaching_approach_for_workflow, no call
    # that would decide an approach on its own rather than being handed one.
    from .skills import script as script_module
    assert not hasattr(script_module, "choose_teaching_approach")
    assert not hasattr(script_module, "choose_teaching_approach_for_workflow")
    src = open(script_module.__file__).read()
    assert "skills.teaching_approach" not in src and \
        "skills import teaching_approach" not in src
    print("   ok — skills/script.py depends on TeachingApproach's shape, "
          "never on skills/teaching_approach.py's own functions "
          "(requirement 14)")


def test_approval_framing_and_teaching_approach_never_mutate_the_original_topic():
    wf = _workflow(approve=False)
    original_question = wf.selection.topic.topic
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.regenerate(wf, "focus on the mechanism", [_section()])
        wf = review.approve_question(wf)
        wf = framing.frame_workflow(wf, [_section()])
        wf = teaching_approach.choose_teaching_approach_for_workflow(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert wf.selection.topic.topic == original_question
    print("   ok — the original Topic.topic (what write_script would read) "
          "survives regeneration, framing and teaching-approach selection "
          "untouched (requirement 14)")


# ------------------------------------------------------------------------ extra
# The rationale-specificity check this step adds.

def test_rationale_specific_check_catches_generic_praise():
    generic = TeachingApproach(primary="analogy", rationale="This approach is engaging.")
    result = checks.check_teaching_approach_rationale_specific(generic)
    assert not result.passed
    print("   ok — check_teaching_approach_rationale_specific fails a generic "
          "'this is engaging' rationale")


def test_rationale_specific_check_passes_concrete_reasoning():
    concrete = TeachingApproach(
        primary="process_demonstration",
        rationale="Pushing and popping are ordered operations, and the section "
                  "only makes sense walked in sequence.")
    result = checks.check_teaching_approach_rationale_specific(concrete)
    assert result.passed
    print("   ok — check_teaching_approach_rationale_specific passes concrete, "
          "concept-specific reasoning")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} teaching-approach workflow (Step 5) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL TEACHING APPROACH WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
