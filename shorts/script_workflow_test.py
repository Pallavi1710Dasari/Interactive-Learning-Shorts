"""
Offline, deterministic tests for Step 8: workflow-aware script generation
(shorts/skills/script.py's write_script_for_workflow, and write_script's new
optional `framing`/`approach` parameters).

No API key, no network — every LLM call here goes through config.STUB exactly
like Steps 3-7 (write_script already had a stub handler; write_script_for_workflow
reuses it unchanged since it targets the same Script model).

    python -m shorts.script_workflow_test
"""
from pathlib import Path
from unittest.mock import patch

from . import config
from .schema import Section, Topic, TopicList, QuestionWorkflow, Script, Beat, TeachingApproach
from .parse import parse_markdown, find_section
from .skills import select, script as script_mod
from . import review, workflow, checks

ROOT = Path(__file__).resolve().parent.parent


def _thin_section(section_id="3.1", title="Why Paging Exists") -> Section:
    """A short, hand-written section — enough for gating/wiring tests, not
    rich enough to pass every length/beat-count grader (see _rich_section
    for that)."""
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _rich_sections() -> list[Section]:
    """The real content file smoke_test.py already relies on for a script
    that passes every grader — reused here rather than hand-rolling a second
    fixture that would need the same care to get right."""
    return parse_markdown(ROOT / "content" / "session_18_paging.md")


def _workflow(section: Section, stage: str = "approach", **topic_overrides) -> QuestionWorkflow:
    """
    Build a workflow at a given stage:
      "pending"   just selected, question still pending
      "approved"  question approved, no framing
      "framed"    question approved and framed, no teaching_approach
      "approach"  framed, with a teaching_approach chosen but NOT approved
      "ready"     teaching_approach chosen AND approved — fully gate-cleared
    """
    data = dict(
        id="t_paging", topic="Why does paging remove external fragmentation?",
        why_it_matters="central mechanism", source_section_id=section.section_id,
        difficulty="medium", importance=5, concept="paging and fragmentation",
        answer_quote="Paging solves external fragmentation by dividing memory "
                     "into equal fixed-size frames.",
    )
    data.update(topic_overrides)
    topic = Topic(**data)
    [selection] = select.build_question_selections(TopicList(topics=[topic]), [section])
    wf = QuestionWorkflow(selection=selection)
    if stage == "pending":
        return wf

    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(wf)
        if stage == "approved":
            return wf
        wf = workflow.advance(wf, [section]).workflow   # frames + chooses approach
        if stage == "framed":
            return wf.model_copy(update={"teaching_approach": None})
        if stage == "approach":
            return wf
        wf = review.approve_teaching_approach(wf)
        return wf
    finally:
        config.STUB = old_stub


# --------------------------------------------------------------------------- 1
def test_only_fully_approved_workflow_generates_a_script():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        result = script_mod.write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub
    assert result.script is not None
    print("   ok — a fully approved workflow generates a script (requirement 1)")


# --------------------------------------------------------------------------- 2
def test_pending_question_cannot_generate_script():
    section = _thin_section()
    wf = _workflow(section, stage="pending")
    try:
        script_mod.write_script_for_workflow(wf, section)
        raise AssertionError("should refuse a pending question")
    except ValueError as e:
        assert "pending" in str(e)
    print("   ok — a pending question cannot generate a script (requirement 2)")


# --------------------------------------------------------------------------- 3
def test_rejected_question_cannot_generate_script():
    section = _thin_section()
    wf = review.reject_question(_workflow(section, stage="pending"), note="not needed")
    try:
        script_mod.write_script_for_workflow(wf, section)
        raise AssertionError("should refuse a rejected question")
    except ValueError as e:
        assert "rejected" in str(e)
    print("   ok — a rejected question cannot generate a script (requirement 3)")


def test_regenerating_question_cannot_generate_script():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="pending")
        wf = wf.model_copy(update={
            "question_approval": wf.question_approval.model_copy(update={"status": "regenerating"})})
    finally:
        config.STUB = old_stub
    try:
        script_mod.write_script_for_workflow(wf, section)
        raise AssertionError("should refuse a 'regenerating' question")
    except ValueError as e:
        assert "regenerating" in str(e)
    print("   ok — a regenerating question cannot generate a script (requirement 2)")


# --------------------------------------------------------------------------- 4
def test_missing_framing_cannot_generate_script():
    section = _thin_section()
    wf = _workflow(section, stage="approved")
    assert wf.framing is None
    try:
        script_mod.write_script_for_workflow(wf, section)
        raise AssertionError("should refuse a workflow with no framing")
    except ValueError as e:
        assert "framing" in str(e).lower()
    print("   ok — missing framing cannot generate a script (requirement 4)")


# --------------------------------------------------------------------------- 5
def test_pending_teaching_approach_approval_cannot_generate_script():
    section = _thin_section()
    wf = _workflow(section, stage="approach")
    assert wf.teaching_approach_approval.status == "pending"
    try:
        script_mod.write_script_for_workflow(wf, section)
        raise AssertionError("should refuse a pending teaching_approach_approval")
    except ValueError as e:
        assert "pending" in str(e)
    print("   ok — a pending teaching-approach approval cannot generate a "
          "script (requirement 5)")


def test_regenerated_teaching_approach_not_yet_approved_cannot_generate_script():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        wf = review.regenerate_teaching_approach(wf, "code is not necessary", [section])
    finally:
        config.STUB = old_stub
    assert wf.teaching_approach_approval.status == "pending"
    try:
        script_mod.write_script_for_workflow(wf, section)
        raise AssertionError("should refuse an unapproved regenerated approach")
    except ValueError as e:
        assert "pending" in str(e)
    print("   ok — a regenerated-but-unapproved teaching approach cannot "
          "generate a script (requirement 5)")


def test_unapproved_workflow_never_reaches_the_llm():
    section = _thin_section()
    wf = _workflow(section, stage="approach")   # not yet approved
    with patch.object(script_mod, "ask_json", side_effect=AssertionError(
            "must not call the LLM for an unapproved workflow")):
        try:
            script_mod.write_script_for_workflow(wf, section)
            raise AssertionError("should have raised before any LLM call")
        except ValueError:
            pass
    print("   ok — an unapproved workflow never reaches the LLM (cost protection)")


# --------------------------------------------------------------------------- 6
def test_approved_teaching_approach_allows_generation():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        assert wf.approved_teaching_approach is not None
        result = script_mod.write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub
    assert result.script is not None
    print("   ok — an approved teaching approach allows generation (requirement 6)")


# --------------------------------------------------------------------------- 7
def test_effective_approved_question_is_passed_as_source_question():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="pending")
        wf = review.regenerate(wf, "too broad, focus on the mechanism", [section])
        wf = review.approve_question(wf)
        wf = workflow.advance(wf, [section]).workflow
        wf = review.approve_teaching_approach(wf)

        captured = {}
        real_ask_json = script_mod.ask_json

        def spy(system, user, model_cls, **kw):
            captured["user"] = user
            return real_ask_json(system, user, model_cls, **kw)

        script_mod.ask_json = spy
        try:
            result = script_mod.write_script_for_workflow(wf, section)
        finally:
            script_mod.ask_json = real_ask_json
    finally:
        config.STUB = old_stub

    assert wf.effective_question != wf.selection.topic.topic   # sanity: really regenerated
    assert "ORIGINALLY APPROVED QUESTION" in captured["user"] or \
        wf.framing.source_question in captured["user"]
    assert wf.framing.source_question == wf.effective_question
    print("   ok — the effective (regenerated, approved) question is what "
          "the script generator is told was approved (requirement 7)")


# --------------------------------------------------------------------------- 8
def test_teaching_question_is_passed_to_the_generator():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        captured = {}
        real_ask_json = script_mod.ask_json

        def spy(system, user, model_cls, **kw):
            captured["user"] = user
            return real_ask_json(system, user, model_cls, **kw)

        script_mod.ask_json = spy
        try:
            result = script_mod.write_script_for_workflow(wf, section)
        finally:
            script_mod.ask_json = real_ask_json
    finally:
        config.STUB = old_stub

    assert f"TOPIC: {wf.framing.teaching_question}" in captured["user"]
    # And it is what the generated question actually IS, in stub mode.
    assert result.script.question == wf.framing.teaching_question
    print("   ok — framing.teaching_question drives the script's own "
          "question (requirement 8)")


# --------------------------------------------------------------------------- 9
def test_approved_teaching_approach_is_passed_to_the_generator():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        captured = {}
        real_ask_json = script_mod.ask_json

        def spy(system, user, model_cls, **kw):
            captured["user"] = user
            return real_ask_json(system, user, model_cls, **kw)

        script_mod.ask_json = spy
        try:
            script_mod.write_script_for_workflow(wf, section)
        finally:
            script_mod.ask_json = real_ask_json
    finally:
        config.STUB = old_stub

    assert "THE APPROVED TEACHING APPROACH" in captured["user"]
    assert wf.approved_teaching_approach.primary in captured["user"]
    if wf.approved_teaching_approach.rationale:
        assert wf.approved_teaching_approach.rationale in captured["user"]
    print("   ok — the approved teaching approach (primary + rationale) is "
          "passed to the script generator (requirement 9)")


# -------------------------------------------------------------------------- 10
def test_script_generation_does_not_replace_the_approved_approach():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        original_approach = wf.teaching_approach
        original_approval = wf.teaching_approach_approval
        result = script_mod.write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub
    assert result.teaching_approach == original_approach
    assert result.teaching_approach_approval == original_approval
    assert result.selection == wf.selection
    assert result.framing == wf.framing
    print("   ok — generating a script never touches teaching_approach, its "
          "approval, selection, or framing (requirement 10)")


# -------------------------------------------------------------------------- 11
def test_non_code_approach_does_not_inject_code_instruction():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        # Force a NON-code approach regardless of what the stub chose, so
        # this test is not at the mercy of the stub's own default.
        forced = TeachingApproach(primary="process_demonstration",
                                  rationale="walks push then pop in order")
        wf = wf.model_copy(update={
            "teaching_approach": forced,
            "teaching_approach_approval": wf.teaching_approach_approval.model_copy(
                update={"regenerated_approach": None})})
        assert wf.approved_teaching_approach.primary == "process_demonstration"

        captured = {}
        real_ask_json = script_mod.ask_json

        def spy(system, user, model_cls, **kw):
            captured["user"] = user
            return real_ask_json(system, user, model_cls, **kw)

        script_mod.ask_json = spy
        try:
            script_mod.write_script_for_workflow(wf, section)
        finally:
            script_mod.ask_json = real_ask_json
    finally:
        config.STUB = old_stub

    assert script_mod._APPROACH_GUIDANCE["code"] not in captured["user"]
    assert script_mod._APPROACH_GUIDANCE["process_demonstration"] in captured["user"]
    print("   ok — a non-code approach never injects the code-specific "
          "guidance block (requirement 11)")


def test_bare_write_script_never_gets_approach_guidance():
    # The ORDINARY, pre-Step-8 call path — no framing, no approach — must
    # never see ANY approach-specific text; this is the strongest form of
    # "code is not the default" there is: the guidance block simply does not
    # exist unless a workflow explicitly supplied an approved approach.
    section = _thin_section()
    topic = Topic(id="t1", topic="Why does paging remove external fragmentation?",
                 why_it_matters="m", source_section_id=section.section_id,
                 difficulty="medium")
    captured = {}
    real_ask_json = script_mod.ask_json

    def spy(system, user, model_cls, **kw):
        captured["user"] = user
        return real_ask_json(system, user, model_cls, **kw)

    old_stub = config.STUB
    config.STUB = True
    script_mod.ask_json = spy
    try:
        script_mod.write_script(topic, section)
    finally:
        script_mod.ask_json = real_ask_json
        config.STUB = old_stub

    assert "THE APPROVED TEACHING PLAN" not in captured["user"]
    assert "THE APPROVED TEACHING APPROACH" not in captured["user"]
    print("   ok — write_script with no framing/approach injects no teaching-"
          "plan or approach guidance at all (requirement 11)")


# -------------------------------------------------------------------------- 12
def test_existing_topic_based_write_script_unchanged():
    # The exact fixture-driven check smoke_test.py performs — reused here so
    # this file also proves Step 8 did not disturb it.
    sections = _rich_sections()
    section = find_section(sections, "3.1")
    import json
    data = json.loads((ROOT / "evals/fixtures/concise_but_complete.json").read_text())
    sc = Script(**data)
    results = checks.run_script_graders(sc, section.text)
    assert checks.all_passed(results), [r for r in results if not r.passed]
    print("   ok — the existing known-good script fixture still passes every "
          "grader unchanged (requirement 12)")


def test_write_script_signature_backward_compatible():
    import inspect
    params = inspect.signature(script_mod.write_script).parameters
    names = list(params)
    assert names[:6] == ["topic", "section", "feedback", "current", "document",
                        "understanding"]
    assert params["framing"].default is None
    assert params["approach"].default is None
    print("   ok — write_script's existing positional/keyword parameters are "
          "unchanged; framing/approach are new, trailing, and optional "
          "(requirement 12)")


# -------------------------------------------------------------------------- 13
def test_workflow_aware_script_passes_existing_beat_constraints():
    sections = _rich_sections()
    # Section 3.1 — the same one smoke_test.py's "concise_but_complete" fixture
    # uses, and the one _workflow()'s hardcoded topic ("...external
    # fragmentation") is actually ABOUT. 3.3 covers page faults instead, which
    # is a different concept the hardcoded topic would score 0% grounded
    # against — a mismatch in this fixture, not in write_script_for_workflow.
    section = find_section(sections, "3.1")
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        result = script_mod.write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub

    script = result.script
    assert isinstance(script, Script)
    results = checks.run_script_graders(script, section.text)
    for r in results:
        print(f"      {r}")
    assert checks.all_passed(results), [r for r in results if not r.passed]
    print("   ok — a workflow-aware script (stub mode, rich section) passes "
          "every existing script grader (requirement 13)")


# -------------------------------------------------------------------------- 14
# (run separately: `python -m shorts.smoke_test` — see the run instructions
# at the bottom of this file's own module docstring / the report.)


# -------------------------------------------------------------------------- 15
def test_stub_mode_generates_deterministically():
    sections = _rich_sections()
    section = find_section(sections, "3.1")
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        r1 = script_mod.write_script_for_workflow(wf, section)
        r2 = script_mod.write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub
    assert r1.script == r2.script
    print("   ok — stub-mode workflow-aware generation is deterministic "
          "(requirement 15)")


# -------------------------------------------------------------------------- 16
def test_repeated_generation_makes_exactly_one_call_each_time():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        calls = {"n": 0}
        real_ask_json = script_mod.ask_json

        def counting(*a, **kw):
            calls["n"] += 1
            return real_ask_json(*a, **kw)

        script_mod.ask_json = counting
        try:
            script_mod.write_script_for_workflow(wf, section)
            script_mod.write_script_for_workflow(wf, section)
        finally:
            script_mod.ask_json = real_ask_json
    finally:
        config.STUB = old_stub
    assert calls["n"] == 2, (
        f"expected exactly one call per generation (2 total), got {calls['n']}")
    print("   ok — each write_script_for_workflow call spends exactly one "
          "LLM call — no extra planning calls (requirement 16)")


def test_result_stored_on_workflow_script_field():
    section = _thin_section()
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow(section, stage="ready")
        assert wf.script is None
        result = script_mod.write_script_for_workflow(wf, section)
    finally:
        config.STUB = old_stub
    assert result.script is not None
    assert isinstance(result.script, Script)
    print("   ok — the generated script is stored in the existing "
          "QuestionWorkflow.script field — no new schema needed")


# ------------------------------------------------------------------ new check

def _beat(quote: str):
    return Beat(speaker="student", line="explains it", on_screen="x",
               visual_ref="v1", source_quote=quote)


def test_check_script_matches_approach_passes_code_shown_for_code_approach():
    sc = Script(short_id="s1", question="Q?", beats=[
        Beat(speaker="interviewer", line="Q?", on_screen="Q", visual_ref="v0"),
        _beat("static int count = 0;"),
    ])
    result = checks.check_script_matches_teaching_approach(sc, TeachingApproach(primary="code"))
    assert result.passed
    print("   ok — check_script_matches_teaching_approach passes when code is "
          "shown for an approved code approach")


def test_check_script_matches_approach_fails_code_approved_but_not_shown():
    sc = Script(short_id="s1", question="Q?", beats=[
        Beat(speaker="interviewer", line="Q?", on_screen="Q", visual_ref="v0"),
        _beat("Paging solves external fragmentation by dividing memory into "
             "equal fixed-size frames."),
    ])
    result = checks.check_script_matches_teaching_approach(sc, TeachingApproach(primary="code"))
    assert not result.passed
    print("   ok — check_script_matches_teaching_approach fails when code was "
          "approved but never shown")


def test_check_script_matches_approach_fails_when_code_dominates_non_code_approach():
    sc = Script(short_id="s1", question="Q?", beats=[
        Beat(speaker="interviewer", line="Q?", on_screen="Q", visual_ref="v0"),
        _beat("const s = 2;"),
        _beat("let x = 3;"),
        _beat("Paging solves external fragmentation by dividing memory into "
             "equal fixed-size frames."),
    ])
    result = checks.check_script_matches_teaching_approach(
        sc, TeachingApproach(primary="conceptual_visual"))
    assert not result.passed
    print("   ok — check_script_matches_teaching_approach fails when code "
          "dominates a non-code approach")


def test_check_script_matches_approach_passes_one_supporting_code_citation():
    # ONE code citation alongside prose ones is tolerated — the section may
    # only offer code as its concrete evidence even under a non-code approach.
    sc = Script(short_id="s1", question="Q?", beats=[
        Beat(speaker="interviewer", line="Q?", on_screen="Q", visual_ref="v0"),
        _beat("Paging solves external fragmentation by dividing memory into "
             "equal fixed-size frames."),
        _beat("Each process is divided into pages of the same size."),
        _beat("static int count = 0;"),
    ])
    result = checks.check_script_matches_teaching_approach(
        sc, TeachingApproach(primary="process_demonstration"))
    assert result.passed
    print("   ok — a single supporting code citation does not fail a "
          "non-code approach")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} script-workflow (Step 8) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SCRIPT WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
