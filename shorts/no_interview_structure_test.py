"""
Deterministic tests for checks.check_no_interview_structure — the workflow-wide
guard against Q&A/interviewer-shaped narration: the selected question restated
as beat 1, an interviewer-style opening question, speaker/role labels, or a
mid-script question-then-answer exchange. See its own docstring in checks.py
for the full design (this is checked, not just prompted for, because the
prompt-only version of this rule kept recurring in real generated reels).

No API key, no network, no cost — pure string/structure checks.

    python -m shorts.no_interview_structure_test
"""
from . import checks
from .schema import Script, Beat


def _script(lines: list[str], question: str = "q") -> Script:
    beats = [Beat(line=line, on_screen="x", visual_ref=f"v{i}")
            for i, line in enumerate(lines)]
    return Script(short_id="t", question=question, beats=beats)


# --------------------------------------------------------------------------- 1
# The selected question must never simply become beat 1 — the exact real
# question from the report that triggered this whole step.

def test_selected_question_converted_into_beat_1_fails():
    question = ("What are props and how do they let a parent component pass "
               "data to a child component?")
    # A "light rewording" of the question, not even a verbatim copy — the
    # defect this whole step is about is the SHAPE (open by asking the
    # objective), not merely byte-identical text.
    script = _script([
        "So how do props let a parent component pass data down to its child?",
        "Props are values passed from a parent component to a child component, "
        "so the child can use that data when it needs it.",
    ], question=question)
    result = checks.check_no_interview_structure(script, selected_question=question)
    assert not result.passed
    assert "selected question" in result.reason
    print(f"   ok — a beat 1 that converts the selected question into the "
          f"opening line fails, naming the exact defect: {result.reason} "
          f"(requirement: selected question is not spoken)")


def test_run_script_graders_catches_the_same_defect_via_write_and_grade_path_shape():
    # Same check, invoked the way write_and_grade_script_for_workflow actually
    # invokes it — through run_script_graders, with selected_question passed
    # positionally the same way that call site does.
    question = "What are props and how do they let a parent component pass data to a child component?"
    script = _script([
        "What are props and how do parents pass data to a child component?",
        "Props are values passed from a parent component to a child component.",
    ], question=question)
    results = checks.run_script_graders(script, selected_question=question)
    hit = next(r for r in results if r.name == "no_interview_structure")
    assert not hit.passed, hit.reason
    print("   ok — run_script_graders (the shared entry point every real "
          "script-generation path calls) surfaces the same failure")


# --------------------------------------------------------------------------- 2
# A literal interviewer-style opening question, regardless of wording overlap
# with any particular selected question, must fail on its own shape alone.

def test_interviewer_style_opening_question_fails():
    script = _script([
        "How does a parent component actually hand data down to its child?",
        "Props are values passed from a parent component to a child component, "
        "so the child can use that data when it needs it.",
    ])
    result = checks.check_no_interview_structure(script)
    assert not result.passed
    assert "interviewer-style" in result.reason or "opens by asking" in result.reason
    print(f"   ok — an interviewer-style opening question fails even with no "
          f"selected_question given: {result.reason} "
          f"(requirement: interviewer question fails)")


def test_role_labels_fail():
    script = _script([
        "Interviewer: How does a parent pass data to a child?",
        "Narrator: Props let a parent send data to a child.",
    ])
    result = checks.check_no_interview_structure(script)
    assert not result.passed
    assert "interviewer-style narration" in result.reason
    print(f"   ok — Interviewer:/Narrator: role labels fail: {result.reason}")


def test_mid_script_question_answer_exchange_fails():
    script = _script([
        "Props let a parent pass data to a child component.",
        "But how does the child actually receive that value?",
        "It receives it as a function argument, the same way any parameter works.",
    ])
    result = checks.check_no_interview_structure(script)
    assert not result.passed
    assert "question-answer exchange" in result.reason
    print(f"   ok — a mid-script interviewer-style question fails, not only "
          f"beat 1: {result.reason} (requirement: question beat immediately "
          f"followed by an answer beat)")


def test_multiple_question_answer_exchanges_are_reported_as_a_pattern():
    script = _script([
        "Props let a parent pass data to a child component.",
        "But how does the child actually receive that value?",
        "It receives it as a function argument.",
        "So why does React re-render when a prop changes?",
        "Because React compares the new props to the old ones.",
    ])
    result = checks.check_no_interview_structure(script)
    assert not result.passed
    assert "2 question-answer exchanges" in result.reason
    print(f"   ok — multiple question-answer exchanges are reported together, "
          f"not just the first: {result.reason} "
          f"(requirement: multiple question-answer patterns)")


# --------------------------------------------------------------------------- 3
# Continuous single-narrator teaching must pass — including a hook that shares
# the selected question's own vocabulary (grounding requires that) without
# restating it, and a genuine curiosity hook that is not a closed-form quiz
# question.

def test_continuous_narration_opening_passes():
    question = ("What are props and how do they let a parent component pass "
               "data to a child component?")
    script = _script([
        "A parent component can have information that a child component needs.",
        "React provides a simple way to pass that information down: props.",
        "They let a parent pass data to a child component, so the child can "
        "use that data when it needs it.",
    ], question=question)
    result = checks.check_no_interview_structure(script, selected_question=question)
    assert result.passed, result.reason
    print("   ok — a continuous, single-narrator opening passes even though it "
          "shares the selected question's own concept vocabulary (parent, "
          "child, data, props) — grounding is not confused with restatement "
          "(requirement: continuous narration passes)")


def test_genuine_curiosity_hook_is_not_falsely_rejected():
    # A real rhetorical question that is NOT a closed-form "how does/what is/
    # why does" quiz lead must still be allowed — see the check's own
    # docstring: this is not a blanket ban on "?".
    script = _script([
        "A small change in one value can affect what a component displays.",
        "That value is called state, and updating it tells React to redraw "
        "the screen.",
    ])
    result = checks.check_no_interview_structure(script)
    assert result.passed, result.reason
    print("   ok — a genuine curiosity/statement hook with no closed-form "
          "quiz-question lead is not falsely rejected")


def test_direct_teaching_approach_style_opening_passes():
    # "Direct" hooks (script.py's own fourth THE OPENING shape) are a plain
    # statement of the concept — must never be mistaken for an interviewer
    # question just because it is short and declarative.
    script = _script([
        "Props are values passed from a parent component to a child component.",
        "The child reads them the same way it would read any function argument.",
    ])
    result = checks.check_no_interview_structure(script)
    assert result.passed, result.reason
    print("   ok — a plain DIRECT-style opening (no hook at all) passes")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} no-interview-structure tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL NO-INTERVIEW-STRUCTURE TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
