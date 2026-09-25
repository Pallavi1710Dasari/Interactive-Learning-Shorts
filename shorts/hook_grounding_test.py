"""
Step 2 hardening: hook grounding.

check_hook_plan and check_opening_follows_hook already existed before this step
— this file is not introducing a new grounding mechanism, it is proving the
existing one does what Step 2 asks (grounded/fabricated/unrelated/curiosity
hooks are told apart, without requiring a literal quote), and closing the one
real gap found while auditing it: `understanding` (and therefore the hook
checks, which are gated on `understanding is not None` — see
checks.run_script_graders's own docstring) was computed but never passed at
the FINAL gate — shorts.skills.audit.audit(), and its two callers, run.py's
build_one and server.py's finalize (both the main gate and the repair-path
gate in _rejudge_after_fix). A hook that generalised past what the section
supports was checked while drafting and never checked again at the point that
actually decides whether the short ships.

No API key, no network, no real LLM calls — every test here exercises the
deterministic checks directly, and the one test that reaches audit() does so
on a script that fails the FREE graders, so audit() returns before it would
ever call the (real) judge.

    SHORTS_STUB=1 python -m shorts.hook_grounding_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks
from shorts.schema import Beat, HookPlan, Script, SectionUnderstanding
from shorts.skills.audit import audit


SOURCE = (
    "A queue only allows items to be added at the back and removed from the "
    "front. This ordering is called FIFO, first in first out. A print spooler "
    "uses a queue so that print jobs run in the order they were submitted, "
    "instead of finishing out of order."
)

CORE_IDEA = "a queue processes items in the order they were added, FIFO"


def _understanding(hook_plan: HookPlan | None) -> SectionUnderstanding:
    return SectionUnderstanding(section_id="1.1", core_idea=CORE_IDEA,
                                hook_plan=hook_plan)


# ============================================================ 1. check_hook_plan

def test_grounded_hook_passes():
    plan = HookPlan(kind="problem",
                    hook="a print spooler has to run print jobs in the order "
                         "they were submitted, instead of finishing out of "
                         "order",
                    why_it_matters="a printer that runs jobs out of order is "
                                   "useless",
                    leads_into=CORE_IDEA)
    result = checks.check_hook_plan(_understanding(plan), SOURCE)
    assert result.passed, result.reason
    print("   ok — a problem hook whose claim is actually in the section "
          "passes check_hook_plan")


def test_fabricated_hook_fails():
    plan = HookPlan(kind="problem",
                    hook="a queue can process one million print jobs every "
                         "second on modern hardware",
                    why_it_matters="speed matters",
                    leads_into=CORE_IDEA)
    result = checks.check_hook_plan(_understanding(plan), SOURCE)
    assert not result.passed
    print(f"   ok — a fabricated statistic the section never states fails "
          f"check_hook_plan: {result.reason}")


def test_unrelated_hook_fails():
    plan = HookPlan(kind="question",
                    hook="why does a car engine need regular oil changes",
                    why_it_matters="engines are important",
                    leads_into=CORE_IDEA)
    result = checks.check_hook_plan(_understanding(plan), SOURCE)
    assert not result.passed
    print(f"   ok — a hook about a completely different topic fails "
          f"check_hook_plan on topicality: {result.reason}")


def test_natural_curiosity_hook_grounded_passes():
    """The exact shape the audit asked to keep possible: a natural "have you
    ever wondered" phrasing, accepted specifically because the underlying
    idea is grounded — not because of the phrasing."""
    plan = HookPlan(kind="question",
                    hook="have you ever wondered why your print jobs always "
                         "come out in the order you sent them, even when a "
                         "printer is busy",
                    why_it_matters="it is not obvious a queue is what "
                                   "guarantees that",
                    leads_into=CORE_IDEA)
    result = checks.check_hook_plan(_understanding(plan), SOURCE)
    assert result.passed, result.reason
    print("   ok — a naturally-phrased curiosity hook passes when its "
          "underlying idea is grounded in the section (phrasing is not the "
          "bar — groundedness is)")


# ================================================== 2. check_opening_follows_hook

def _script(opening_line: str, question: str = CORE_IDEA) -> Script:
    beats = [
        Beat(line=opening_line, on_screen="Queue", visual_ref="v0"),
        Beat(line="A queue only allows items in at the back and out at the "
                  "front.", on_screen="FIFO", visual_ref="v1",
             source_quote="A queue only allows items to be added at the back "
                          "and removed from the front."),
        Beat(line="That ordering is called first in, first out.",
             on_screen="FIFO", visual_ref="v2",
             source_quote="This ordering is called FIFO, first in first "
                          "out."),
    ]
    return Script(short_id="t_queue", question=question, beats=beats)


def test_opening_follows_grounded_hook_passes():
    plan = HookPlan(kind="question",
                    hook="have you ever wondered why print jobs come out in "
                         "the order you sent them",
                    why_it_matters="it is not obvious", leads_into=CORE_IDEA)
    understanding = _understanding(plan)
    script = _script("Have you ever wondered why print jobs always come out "
                     "in the order you send them?")
    result = checks.check_opening_follows_hook(script, understanding, SOURCE)
    assert result.passed, result.reason
    print("   ok — an opening beat that stays on the grounded, planned hook "
          "passes check_opening_follows_hook")


def test_opening_that_fabricates_a_detail_fails():
    plan = HookPlan(kind="direct", hook="", why_it_matters="", leads_into="")
    understanding = _understanding(plan)
    script = _script("A queue can reorder ten thousand print jobs a second.")
    result = checks.check_opening_follows_hook(script, understanding, SOURCE)
    assert not result.passed
    print(f"   ok — an opening that invents a number/detail the section "
          f"never states fails check_opening_follows_hook: {result.reason}")


# ================================================== 3. selected question -> Q&A

def test_selected_question_spoken_verbatim_is_still_rejected():
    """The exact failure mode Step 2's brief names: the selected question
    simply converted into a spoken question. check_no_interview_structure
    already exists to catch this and runs unconditionally (see
    run_script_graders's own docstring) — this proves it still does."""
    question = "How does a queue process items in order?"
    script = _script(question, question=question)
    result = checks.check_no_interview_structure(script, selected_question=question)
    assert not result.passed
    print(f"   ok — beat 1 restating the selected question as a spoken "
          f"question is rejected by the existing no-interview validator: "
          f"{result.reason}")


def test_curiosity_hook_is_not_penalized_as_interview_structure():
    """A curiosity question that is NOT the selected question restated, AND
    was planned as a grounded 'question' hook (check_hook_plan already
    verified it — see understanding_for's own drop-on-failure behavior),
    must not be caught by the same rule — Step 2 explicitly says not to ban
    rhetorical/curiosity questions outright."""
    question = CORE_IDEA
    plan = HookPlan(kind="question",
                    hook="have you ever wondered why print jobs come out in "
                         "the order you sent them",
                    why_it_matters="it is not obvious", leads_into=CORE_IDEA)
    understanding = _understanding(plan)
    script = _script("Have you ever wondered why print jobs always come out "
                     "in the order you send them?", question=question)
    result = checks.check_no_interview_structure(script, selected_question=question,
                                                  understanding=understanding)
    assert result.passed, result.reason
    print("   ok — a curiosity question that is not the selected question "
          "restated, and was planned+grounded as a question hook, is not "
          "flagged as interview structure")


def test_unplanned_curiosity_question_is_still_rejected_by_default():
    """The default (no hook_plan, or omitted entirely) must NOT change —
    every existing caller without a plan keeps exactly the old behaviour."""
    question = CORE_IDEA
    script = _script("Have you ever wondered why print jobs always come out "
                     "in the order you send them?", question=question)
    result = checks.check_no_interview_structure(script, selected_question=question)
    assert not result.passed
    print(f"   ok — the same curiosity question with no hook_plan behind it "
          f"is still rejected — the relaxation only applies to a "
          f"deliberately planned and grounded 'question' hook: "
          f"{result.reason}")


# ================================================== 4. the wiring gap itself

def test_hook_check_is_skipped_without_understanding():
    """Documents the exact shape of the bug this step closes: omit
    `understanding` (as the pre-Step-2 finalize gate did) and the hook is not
    checked at all — not because it passed, but because the check never
    ran."""
    plan = HookPlan(kind="direct", hook="", why_it_matters="", leads_into="")
    script = _script("A queue can reorder ten thousand print jobs a second.")
    results = checks.run_script_graders(script, SOURCE, understanding=None)
    names = [r.name for r in results]
    assert "opening_hook" not in names, names
    print("   ok — without understanding, check_opening_follows_hook is not "
          "even in the grader list (confirms the pre-fix blind spot)")


def test_hook_check_runs_and_catches_the_same_script_with_understanding():
    plan = HookPlan(kind="direct", hook="", why_it_matters="", leads_into="")
    understanding = _understanding(plan)
    script = _script("A queue can reorder ten thousand print jobs a second.")
    results = checks.run_script_graders(script, SOURCE, understanding=understanding)
    by_name = {r.name: r for r in results}
    assert "opening_hook" in by_name, [r.name for r in results]
    assert not by_name["opening_hook"].passed, by_name["opening_hook"].reason
    print("   ok — with understanding passed (as every drafting call already "
          "did), the SAME fabricated hook is caught: "
          f"{by_name['opening_hook'].reason}")


def test_audit_now_blocks_on_a_bad_hook_when_understanding_is_supplied():
    """The actual fix: shorts.skills.audit.audit() — the function run.py's
    build_one and server.py's finalize both call at the final gate — now
    accepts and uses `understanding`. This script fails several free graders
    at once (it is a 1-beat-short fragment, not a full script) precisely so
    audit() returns before it would ever call the real judge — see this
    file's own module docstring."""
    plan = HookPlan(kind="direct", hook="", why_it_matters="", leads_into="")
    understanding = _understanding(plan)
    script = _script("A queue can reorder ten thousand print jobs a second.")
    results, report = audit(script, SOURCE, unit=None, understanding=understanding)
    assert report is None, (
        "audit() should not have reached the judge — the free graders, "
        "including the newly-wired opening_hook check, already fail")
    by_name = {r.name: r for r in results}
    assert "opening_hook" in by_name and not by_name["opening_hook"].passed
    print("   ok — audit(), called with understanding as run.py and "
          "server.py's finalize both now do, blocks a script on its "
          "fabricated hook before it would reach the judge")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} hook-grounding hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL HOOK-GROUNDING HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
