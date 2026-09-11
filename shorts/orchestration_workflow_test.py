"""
Offline, deterministic tests for Step 7: the orchestration boundary
(shorts/workflow.py's advance / advance_many).

No API key, no network — every LLM call reachable from here goes through
config.STUB exactly like Steps 3-6 (select, framing, teaching_approach all
already have stub handlers; this step adds no new LLM call of its own).

    python -m shorts.orchestration_workflow_test
"""
from unittest.mock import patch

from . import config
from .schema import Section, Topic, TopicList, QuestionWorkflow
from .skills import select, framing as framing_mod, teaching_approach as ta_mod
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


# --------------------------------------------------------------------------- 1
def test_pending_question_stops_before_framing():
    wf = _workflow()
    result = workflow.advance(wf, [_section()])
    assert result.status == "awaiting_question_approval"
    assert result.workflow.framing is None
    assert result.workflow.teaching_approach is None
    print("   ok — a pending question stops before any framing is generated "
          "(requirement 1)")


def test_pending_question_makes_no_llm_call():
    wf = _workflow()
    with patch.object(framing_mod, "ask_json", side_effect=AssertionError("no call expected")), \
        patch.object(ta_mod, "ask_json", side_effect=AssertionError("no call expected")):
        workflow.advance(wf, [_section()])
    print("   ok — a pending workflow triggers no generation call at all "
          "(requirement 1, cost protection)")


# --------------------------------------------------------------------------- 2
def test_rejected_question_stops_permanently():
    wf = review.reject_question(_workflow(), note="not needed")
    result = workflow.advance(wf, [_section()])
    assert result.status == "rejected"
    assert result.workflow.framing is None
    # Advancing again changes nothing — still rejected, still no framing.
    result2 = workflow.advance(result.workflow, [_section()])
    assert result2.status == "rejected"
    print("   ok — a rejected question stops, permanently, across repeated "
          "advance() calls (requirement 2)")


# --------------------------------------------------------------------------- 3
def test_approved_question_gets_framing_generated():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        assert wf.framing is None
        result = workflow.advance(wf, [_section()])
        assert result.workflow.framing is not None
        assert result.workflow.framing.source_question == wf.effective_question
    finally:
        config.STUB = old_stub
    print("   ok — an approved question gets framing generated automatically "
          "(requirement 3)")


# --------------------------------------------------------------------------- 4
def test_framed_approved_question_gets_teaching_approach_generated():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        wf = framing_mod.frame_workflow(wf, [_section()])
        assert wf.teaching_approach is None
        result = workflow.advance(wf, [_section()])
        assert result.workflow.teaching_approach is not None
    finally:
        config.STUB = old_stub
    print("   ok — a framed, approved question gets a teaching approach "
          "generated automatically (requirement 4)")


def test_one_advance_call_does_both_framing_and_teaching_approach():
    # The task's own expected behavior: approval -> framing -> teaching
    # approach -> stop, all in ONE advance() call, not one per stage.
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.workflow.framing is not None
    assert result.workflow.teaching_approach is not None
    assert result.status == "awaiting_teaching_approach_approval"
    print("   ok — one advance() call on a freshly-approved question produces "
          "both framing and a teaching approach, stopping at the next gate")


# --------------------------------------------------------------------------- 5
def test_teaching_approach_pending_approval_stops():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_teaching_approach_approval"
    assert result.workflow.approved_teaching_approach is None
    print("   ok — a chosen-but-unapproved teaching approach stops the "
          "workflow (requirement 5)")


# --------------------------------------------------------------------------- 6
def test_approved_teaching_approach_is_ready_for_visual_planning():
    # Step 9: reaching this status now also means a script was generated,
    # in the SAME advance() call — see shorts/script_workflow_test.py for
    # the dedicated script-generation-orchestration test suite.
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        wf = workflow.advance(wf, [_section()]).workflow
        wf = review.approve_teaching_approach(wf)
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_visual_plan_approval"
    assert result.workflow.approved_topic is not None
    assert result.workflow.approved_teaching_approach is not None
    assert result.workflow.script is not None
    print("   ok — question approved + framed + teaching approach approved "
          "-> ready_for_visual_planning, with a script generated "
          "(requirement 6)")


# --------------------------------------------------------------------------- 7
def test_repeated_advance_does_not_duplicate_framing_calls():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        first = workflow.advance(wf, [_section()]).workflow
        with patch.object(framing_mod, "ask_json",
                          side_effect=AssertionError("framing must not be called again")):
            again = workflow.advance(first, [_section()]).workflow
    finally:
        config.STUB = old_stub
    assert again.framing == first.framing
    print("   ok — a second advance() call never re-generates framing "
          "(requirement 7)")


# --------------------------------------------------------------------------- 8
def test_repeated_advance_does_not_duplicate_teaching_approach_calls():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        first = workflow.advance(wf, [_section()]).workflow
        with patch.object(ta_mod, "ask_json",
                          side_effect=AssertionError("teaching_approach must not be called again")):
            again = workflow.advance(first, [_section()]).workflow
    finally:
        config.STUB = old_stub
    assert again.teaching_approach == first.teaching_approach
    print("   ok — a second advance() call never re-chooses a teaching "
          "approach (requirement 8)")


# --------------------------------------------------------------------------- 9
def test_understanding_object_reused_for_framing_and_teaching_approach():
    captured = {"framing": None, "teaching_approach": None}
    real_frame_question = framing_mod.frame_question
    real_choose = ta_mod.choose_teaching_approach

    def spy_frame(wf, section, understanding=None):
        captured["framing"] = understanding
        return real_frame_question(wf, section, understanding=understanding)

    def spy_choose(wf, section, understanding=None):
        captured["teaching_approach"] = understanding
        return real_choose(wf, section, understanding=understanding)

    old_stub = config.STUB
    config.STUB = True
    framing_mod.frame_question = spy_frame
    ta_mod.choose_teaching_approach = spy_choose
    try:
        wf = review.approve_question(_workflow())
        section = _section()
        from shorts.schema import SectionUnderstanding
        u = SectionUnderstanding(section_id="3.1", core_idea="paging removes external fragmentation")
        workflow.advance(wf, [section], understanding=u)
    finally:
        framing_mod.frame_question = real_frame_question
        ta_mod.choose_teaching_approach = real_choose
        config.STUB = old_stub

    assert captured["framing"] is u
    assert captured["teaching_approach"] is u
    print("   ok — advance() passes the SAME SectionUnderstanding object to "
          "both framing and teaching-approach generation (requirement 9)")


def test_advance_many_fetches_understanding_once_per_section():
    # A section text UNIQUE TO THIS TEST — understanding_for caches by the
    # section's own text (see skills/understanding.py's _CACHE), and this
    # process runs many tests against the ordinary _section() fixture, so
    # reusing that text here would make this test pass on a warm cache
    # instead of actually proving the sharing.
    section = Section(section_id="9.9", title="A section only this test uses",
                      text="A cache-isolation fixture, unique to this test, so "
                           "understanding_for cannot have already cached it.",
                      start_line=1, end_line=1)

    calls = {"n": 0}
    from shorts.skills import understanding as u_mod
    real_understand = u_mod.understand

    def counting(*a, **kw):
        calls["n"] += 1
        return real_understand(*a, **kw)

    old_stub = config.STUB
    config.STUB = True
    u_mod.understand = counting
    try:
        wf_a = review.approve_question(_workflow(topic_id="t_a", source_section_id="9.9"))
        wf_b = review.approve_question(_workflow(topic_id="t_b", source_section_id="9.9"))
        workflow.advance_many([wf_a, wf_b], [section])
    finally:
        u_mod.understand = real_understand
        config.STUB = old_stub
    assert calls["n"] == 1, (
        f"expected exactly one understanding call shared by both workflows, "
        f"got {calls['n']}")
    print("   ok — advance_many fetches ONE understanding per section, shared "
          "across every workflow filed under it (requirement 9)")


def test_advance_many_never_fetches_understanding_for_workflows_that_do_not_need_it():
    calls = {"n": 0}
    from shorts.skills import understanding as u_mod
    real_understand = u_mod.understand

    def counting(*a, **kw):
        calls["n"] += 1
        return real_understand(*a, **kw)

    old_stub = config.STUB
    config.STUB = True
    u_mod.understand = counting
    try:
        section = _section()
        pending = _workflow(topic_id="t_pending")
        rejected = review.reject_question(_workflow(topic_id="t_rejected"))
        already_ready = review.approve_question(_workflow(topic_id="t_ready"))
        already_ready = workflow.advance(already_ready, [section]).workflow
        already_ready = review.approve_teaching_approach(already_ready)
        calls["n"] = 0   # reset after the setup call above
        workflow.advance_many([pending, rejected, already_ready], [section])
    finally:
        u_mod.understand = real_understand
        config.STUB = old_stub
    assert calls["n"] == 0, (
        f"none of these workflows need generation; expected 0 understanding "
        f"calls, got {calls['n']}")
    print("   ok — advance_many fetches no understanding at all for pending, "
          "rejected, or already-complete workflows (cost protection)")


# -------------------------------------------------------------------------- 10
def test_one_workflow_does_not_block_another():
    old_stub = config.STUB
    config.STUB = True
    try:
        section = _section()
        pending = _workflow(topic_id="t_pending")
        approved = review.approve_question(_workflow(topic_id="t_approved"))
        results = workflow.advance_many([pending, approved], [section])
    finally:
        config.STUB = old_stub
    by_id = {r.workflow.selection.topic.id: r for r in results}
    assert by_id["t_pending"].status == "awaiting_question_approval"
    assert by_id["t_approved"].status == "awaiting_teaching_approach_approval"
    print("   ok — a pending workflow does not prevent another workflow from "
          "advancing all the way to its own gate (requirement 10)")


def test_a_failed_workflow_does_not_block_the_rest_of_the_batch():
    old_stub = config.STUB
    config.STUB = True
    try:
        section = _section()
        wf_fail = review.approve_question(_workflow(topic_id="t_fail"))
        wf_ok = review.approve_question(_workflow(topic_id="t_ok"))

        real_frame_question = framing_mod.frame_question

        def flaky(wf, sec, understanding=None):
            if wf.selection.topic.id == "t_fail":
                raise RuntimeError("simulated provider error")
            return real_frame_question(wf, sec, understanding=understanding)

        framing_mod.frame_question = flaky
        try:
            results = workflow.advance_many([wf_fail, wf_ok], [section])
        finally:
            framing_mod.frame_question = real_frame_question
    finally:
        config.STUB = old_stub

    by_id = {r.workflow.selection.topic.id: r for r in results}
    assert by_id["t_fail"].status == "framing_failed"
    assert "simulated provider error" in by_id["t_fail"].detail
    assert by_id["t_ok"].status == "awaiting_teaching_approach_approval"
    print("   ok — one workflow's generation failure does not block another "
          "workflow in the same batch (requirement 10)")


# -------------------------------------------------------------------------- 11
def test_regenerated_question_follows_the_same_flow_after_approval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        wf = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        assert wf.question_approval.status == "pending"   # regeneration always returns here
        # Before approval, advance() still stops at the question gate.
        mid = workflow.advance(wf, [_section()])
        assert mid.status == "awaiting_question_approval"

        wf = review.approve_question(wf)
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_teaching_approach_approval"
    assert result.workflow.framing.source_question == wf.effective_question
    assert result.workflow.framing.source_question != wf.selection.topic.topic
    print("   ok — a regenerated-then-approved question proceeds through "
          "framing and teaching-approach selection exactly like a directly-"
          "approved one (requirement 11)")


# -------------------------------------------------------------------------- 12
def test_regenerated_teaching_approach_requires_approval_before_ready():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        wf = workflow.advance(wf, [_section()]).workflow
        wf = review.approve_teaching_approach(wf)
        assert workflow.advance(wf, [_section()]).status == "awaiting_visual_plan_approval"

        wf = review.regenerate_teaching_approach(wf, "code is not necessary", [_section()])
        assert wf.teaching_approach_approval.status == "pending"
        mid = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert mid.status == "awaiting_teaching_approach_approval"
    assert mid.workflow.approved_teaching_approach is None
    print("   ok — regenerating an already-approved teaching approach drops "
          "the workflow back to awaiting approval, not ready "
          "(requirement 12)")


# -------------------------------------------------------------------------- 13
def test_stub_mode_executes_the_complete_available_chain():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())
        wf = workflow.advance(wf, [_section()]).workflow
        assert wf.framing is not None and wf.teaching_approach is not None
        wf = review.approve_teaching_approach(wf)
        result = workflow.advance(wf, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_visual_plan_approval"
    assert result.workflow.script is not None
    print("   ok — stub mode can execute the complete available chain, "
          "selection through ready_for_visual_planning, script included "
          "(requirement 13)")


# -------------------------------------------------------------------------- 14
def test_workflow_module_never_calls_input():
    import inspect
    src = inspect.getsource(workflow)
    assert "input(" not in src
    print("   ok — shorts/workflow.py contains no input() call of its own — "
          "it cannot be the reason a non-interactive run blocks "
          "(requirement 14)")


# -------------------------------------------------------------------------- 15
def test_write_script_has_no_dependency_on_the_orchestrator():
    # Step 8 (a later step) gives skills/script.py an intentional dependency
    # on the QuestionWorkflow DATA TYPE — write_script_for_workflow reads one
    # already advanced past both gates — but it must never depend on
    # shorts/workflow.py's own advance()/advance_many(): script generation is
    # not itself an orchestration decision, only a consumer of one already
    # made.
    from .skills import script as script_module
    assert not hasattr(script_module, "advance")
    assert not hasattr(script_module, "advance_many")
    src = open(script_module.__file__).read()
    assert "from .. import workflow" not in src and \
        "from shorts import workflow" not in src and \
        "workflow.advance" not in src
    print("   ok — skills/script.py depends on QuestionWorkflow's shape, "
          "never on shorts/workflow.py's own advance()/advance_many() "
          "(requirement 15)")


def test_advancing_never_mutates_the_original_topic_or_selection():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        original_question = wf.selection.topic.topic
        original_selection = wf.selection
        wf = review.approve_question(wf)
        wf = workflow.advance(wf, [_section()]).workflow
        wf = review.approve_teaching_approach(wf)
        wf = workflow.advance(wf, [_section()]).workflow
    finally:
        config.STUB = old_stub
    assert wf.selection.topic.topic == original_question
    assert wf.selection == original_selection
    print("   ok — orchestration never touches selection.topic (what "
          "write_script would read) (requirement 15)")


# -------------------------------------------------------------------------- 16
def test_legacy_workflow_missing_new_fields_still_advances():
    # A workflow built the way Step 1's tests originally built one — nothing
    # about framing, teaching_approach or their approvals set explicitly,
    # relying entirely on the schema's own defaults.
    old_stub = config.STUB
    config.STUB = True
    try:
        raw_topic = dict(
            id="legacy1", topic="Why does paging remove external fragmentation?",
            why_it_matters="m", source_section_id="3.1", difficulty="medium",
        )
        legacy = QuestionWorkflow(**{
            "selection": {
                "topic": raw_topic,
                "source_title": "Why Paging Exists",
                "reasons": [{"category": "other", "explanation": "x"}],
            },
            # question_approval, framing, teaching_approach, etc. all omitted
            # entirely — exactly like data written before Steps 4-6 existed.
        })
        assert legacy.framing is None
        assert legacy.teaching_approach is None
        result = workflow.advance(legacy, [_section()])
        assert result.status == "awaiting_question_approval"

        approved_legacy = review.approve_question(legacy)
        result2 = workflow.advance(approved_legacy, [_section()])
    finally:
        config.STUB = old_stub
    assert result2.status == "awaiting_teaching_approach_approval"
    assert result2.workflow.framing is not None
    print("   ok — a legacy QuestionWorkflow missing every Step 4-6 field "
          "still loads and advances normally (requirement 16)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} orchestration (Step 7) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL ORCHESTRATION WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
