"""
Offline, deterministic tests for Step 3: the human question-approval and
regeneration gate (shorts/review.py's approve_question / reject_question /
regenerate / run_question_gate, plus the schema they operate on).

No API key, no network — every LLM call here goes through config.STUB, which
review.regenerate routes through exactly like everything else in this
pipeline (see skills.select.regenerate_question -> llm.ask_json -> stubs.fake).

    python -m shorts.review_workflow_test
"""
import io
from contextlib import redirect_stdout

from pydantic import ValidationError

from . import config
from .schema import (Section, Topic, TopicList, QuestionWorkflow, QuestionApproval,
                     RegenerationAttempt)
from .skills import select
from . import review


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow(**topic_overrides) -> QuestionWorkflow:
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
    return QuestionWorkflow(selection=selection)


# ------------------------------------------------------------------------- 1, 2
# Approved proceeds; pending/rejected/regenerating never do.

def test_approved_question_proceeds():
    wf = review.approve_question(_workflow())
    approved = wf.approved_topic
    assert approved is not None
    assert approved.topic == wf.selection.topic.topic
    print("   ok — an approved workflow's approved_topic is a real Topic (requirement 1)")


def test_pending_question_cannot_proceed():
    wf = _workflow()
    assert wf.question_approval.status == "pending"
    assert wf.approved_topic is None
    print("   ok — a pending workflow's approved_topic is None (requirement 2)")


def test_rejected_question_cannot_proceed():
    wf = review.reject_question(_workflow(), note="not needed")
    assert wf.question_approval.status == "rejected"
    assert wf.approved_topic is None
    print("   ok — a rejected workflow's approved_topic is None (requirement 2)")


def test_regenerating_status_cannot_proceed():
    # "regenerating" is a caller-set, transient status (see QuestionApproval's
    # docstring) — review.regenerate never persists it, but a workflow a caller
    # marked this way must still be blocked if something reads it mid-flight.
    wf = _workflow()
    wf = wf.model_copy(update={
        "question_approval": wf.question_approval.model_copy(update={"status": "regenerating"})})
    assert wf.approved_topic is None
    print("   ok — a workflow marked 'regenerating' cannot proceed either")


# ---------------------------------------------------------------------------- 3
# No direct editing anywhere in this step's surface.

def test_approve_and_reject_take_no_question_text_argument():
    import inspect
    for fn in (review.approve_question, review.reject_question):
        params = list(inspect.signature(fn).parameters)
        assert "question" not in params and "edited_question" not in params, (
            f"{fn.__name__} must not accept replacement question text: {params}")
    print("   ok — approve_question/reject_question accept no question-text "
          "argument (requirement 3)")


def test_interactive_gate_offers_no_edit_action():
    # The gate's own prompt string is the product surface a human sees — assert
    # it offers approve/reject/regenerate/skip/quit and nothing that edits text.
    import builtins
    wf = _workflow()
    prompts = []
    responses = iter(["q"])

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(responses)

    old_input = builtins.input
    builtins.input = fake_input
    try:
        review.run_question_gate([wf], [_section()], interactive=True)
    finally:
        builtins.input = old_input

    assert prompts, "the gate should have prompted at least once"
    assert "edit" not in prompts[0].lower()
    assert "[g]enerate again" in prompts[0]
    print("   ok — the interactive gate's own prompt offers no editing action "
          "(requirement 3)")


# ---------------------------------------------------------------------------- 4
# Regeneration requires a reason.

def test_regeneration_attempt_rejects_blank_reason():
    for bad in ("", "   "):
        try:
            RegenerationAttempt(reason=bad, previous_question="Q?",
                                regenerated_question="Q, revised?")
            raise AssertionError(f"RegenerationAttempt should reject reason={bad!r}")
        except ValidationError:
            pass
    print("   ok — RegenerationAttempt rejects a blank/whitespace reason (requirement 4)")


def test_regenerate_raises_without_a_reason():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        for bad in (None, "", "   "):
            try:
                review.regenerate(wf, bad, [_section()])
                raise AssertionError(f"regenerate() should reject reason={bad!r}")
            except ValueError:
                pass
    finally:
        config.STUB = old_stub
    print("   ok — review.regenerate refuses a missing/blank reason before "
          "calling the LLM (requirement 4)")


# ---------------------------------------------------------------------------- 5
# Traceability: original question + regeneration history preserved.

def test_original_question_and_history_preserved_across_regenerations():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow()
        original = wf.selection.topic.topic

        wf = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        wf = review.regenerate(wf, "make it more concrete", [_section()])

        # The ORIGINAL Topic is untouched, however many regenerations ran.
        assert wf.selection.topic.topic == original

        history = wf.question_approval.regeneration_history
        assert len(history) == 2
        assert history[0].reason == "too broad, focus on the mechanism"
        assert history[0].previous_question == original
        assert history[1].reason == "make it more concrete"
        # The second attempt started from what the FIRST one produced, not from
        # the original again — a real history, not two independent edits.
        assert history[1].previous_question == history[0].regenerated_question
        assert wf.question_approval.regenerated_question == history[-1].regenerated_question
    finally:
        config.STUB = old_stub
    print("   ok — the original question and the full regeneration history "
          "(in order) survive multiple regenerations (requirement 5)")


# ---------------------------------------------------------------------------- 6
# Regenerated question stays grounded in the same source/concept.

def test_regenerate_question_prompt_includes_source_and_concept():
    # regenerate_question builds its prompt from the SAME section and the
    # SAME concept/reasons selection already committed to — captured here by
    # intercepting the prompt actually sent to ask_json, rather than trusting
    # a real model's output (which a stub cannot honestly stand in for).
    captured = {}
    real_ask_json = select.ask_json

    def spy(system, user, model_cls, **kw):
        captured["user"] = user
        return real_ask_json(system, user, model_cls, **kw)

    old_stub = config.STUB
    config.STUB = True
    select.ask_json = spy
    try:
        section = _section()
        wf = _workflow(concept="paging and fragmentation")
        review.regenerate(wf, "focus on the mechanism", [section])
    finally:
        select.ask_json = real_ask_json
        config.STUB = old_stub

    user = captured["user"]
    assert "paging and fragmentation" in user      # the concept
    assert section.text in user                     # the actual section text
    assert "focus on the mechanism" in user          # the human's reason
    print("   ok — regenerate_question's prompt carries the same section text "
          "and concept the original selection used (requirement 6)")


def test_regenerated_question_does_not_change_source_section():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.regenerate(_workflow(), "sharpen it", [_section()])
    finally:
        config.STUB = old_stub
    # source_section_id lives on selection.topic and regeneration never
    # touches selection at all — only question_approval.
    assert wf.selection.topic.source_section_id == "3.1"
    print("   ok — regeneration never changes source_section_id (requirement 6)")


# ------------------------------------------------------------------------- 7, 8
# Regeneration always lands back on pending and needs explicit approval.

def test_regeneration_returns_to_pending_not_approved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(_workflow())          # start APPROVED
        assert wf.question_approval.status == "approved"
        wf = review.regenerate(wf, "make it sharper", [_section()])
        assert wf.question_approval.status == "pending", (
            "a regeneration must never leave (or land on) 'approved'")
        assert wf.approved_topic is None
    finally:
        config.STUB = old_stub
    print("   ok — regenerating an already-approved question drops it back to "
          "pending, never auto-approved (requirements 7, 8)")


def test_regenerated_question_requires_a_fresh_explicit_approve():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.regenerate(_workflow(), "focus on the mechanism", [_section()])
        assert wf.approved_topic is None
        wf = review.approve_question(wf)
        assert wf.approved_topic is not None
        assert wf.approved_topic.topic == wf.question_approval.regenerated_question
    finally:
        config.STUB = old_stub
    print("   ok — a regenerated question proceeds only after a fresh, explicit "
          "approve_question call (requirement 8)")


# ---------------------------------------------------------------------------- 9
# Regeneration loop protection, and it is configurable.

def test_regeneration_limit_is_enforced_and_configurable():
    old_stub, old_limit = config.STUB, config.MAX_QUESTION_REGENERATIONS
    config.STUB = True
    config.MAX_QUESTION_REGENERATIONS = 2
    try:
        wf = _workflow()
        wf = review.regenerate(wf, "reason one", [_section()])
        wf = review.regenerate(wf, "reason two", [_section()])
        assert wf.question_approval.regeneration_attempts == 2
        try:
            review.regenerate(wf, "reason three", [_section()])
            raise AssertionError("a third regeneration should be refused at limit=2")
        except ValueError as e:
            assert "limit" in str(e).lower()
    finally:
        config.STUB, config.MAX_QUESTION_REGENERATIONS = old_stub, old_limit
    print("   ok — MAX_QUESTION_REGENERATIONS caps regeneration and is a "
          "configurable value, not a hardcoded constant (requirement 9)")


# --------------------------------------------------------------------------- 10
# Interactive gate displays question, source title, and reasons.

def test_interactive_gate_displays_required_information():
    import builtins
    wf = _workflow()
    responses = iter(["s"])   # leave pending — just checking what got printed
    old_input = builtins.input
    builtins.input = lambda prompt="": next(responses)
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            review.run_question_gate([wf], [_section()], interactive=True)
    finally:
        builtins.input = old_input

    out = buf.getvalue()
    assert wf.selection.topic.topic in out
    assert wf.selection.source_title in out
    for r in wf.selection.reasons:
        assert r.explanation in out
    print("   ok — the interactive gate prints the question, source title, and "
          "every selection reason (requirement 10)")


# --------------------------------------------------------------------------- 12
# Non-interactive flow never blocks on input().

def test_non_interactive_gate_never_calls_input():
    import builtins

    def poison(prompt=""):
        raise AssertionError("run_question_gate must not call input() when "
                             "interactive=False")

    old_input = builtins.input
    builtins.input = poison
    try:
        workflows = [_workflow(), _workflow(id="t2")]
        result = review.run_question_gate(workflows, [_section()], interactive=False)
    finally:
        builtins.input = old_input

    assert len(result) == 2
    assert all(wf.question_approval.status == "pending" for wf in result), (
        "a non-interactive pass must leave every workflow exactly as it went in")
    print("   ok — interactive=False returns immediately without calling "
          "input() (requirement 12)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} review-workflow (Step 3) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL REVIEW WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
