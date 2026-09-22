"""
Offline, deterministic tests for check_section_richness's heading-vs-statement
filter (shorts/checks.py's _is_heading_like / _heading_like_spans).

THE BUG THIS GUARDS AGAINST: a section that is a bullet list of chapter
headings and FAQ-style questions — "What are props in React?", "Understanding
the relationship between parent and child components." — passed
check_section_richness, because every bullet is a punctuated, multi-word
"sentence" by _is_whole_sentence's letter even though none of them asserts a
fact. The frozen fixture below is the real "### Introduction" section under
"## 2. Understanding Props in React" from a document actually pasted into the
app; write_script was handed it, produced a script the LLM judge scored
faithfulness 2/5 on ("The source section is a list of topic headings/questions
only... nearly every substantive claim in the script is therefore invented and
wearing a citation"), and it should never have reached write_script at all.

THE PAIRING RULE: for every case asserting a failure, a case asserting a
success — see ARCHITECTURE_OVERVIEW.md's eval doctrine. E069 in
evals/cases.yaml already covers "real prose passes"; this file adds the
heading-only failure case plus one prose section with a "When..." opening
sentence, which is the false positive an earlier version of this filter had
(a lead word list that also excluded "when"/"where" rejected the real
page-fault section of content/session_18_paging.md).

No API key, no network, no cost — pure string processing.

    python -m shorts.section_richness_test
"""
from . import checks

#: The exact "### Introduction" bullets under "## 2. Understanding Props in
#: React" from the pasted material that produced the low-faithfulness reel.
_HEADINGS_ONLY_SECTION = """\
* What are props in React?

* Why are props used in React applications?

* How props help in passing data between components.

* Understanding the relationship between parent and child components.

* Difference between props and regular JavaScript function parameters.
"""

#: A real explanatory paragraph, same shape (one topic, several sentences) but
#: actually saying something — content/session_18_paging.md's section 3.3.
#: Deliberately starts with "When...", the exact phrasing that must NOT be
#: treated as heading-like.
_REAL_PROSE_SECTION = """\
When the MMU reads a page table entry whose valid bit is clear, it raises a page
fault trap to the operating system. The OS locates the page on the backing
store, selects a free frame, issues the disk read, updates the page table entry,
and restarts the instruction that faulted. The faulting process is blocked for
the duration of the disk I/O.
"""


def test_headings_only_section_is_rejected():
    result = checks.check_section_richness(_HEADINGS_ONLY_SECTION)
    assert not result.passed, "a bullet list of headings/questions must fail the gate"
    assert "heading" in result.reason.lower() or "question" in result.reason.lower(), (
        f"failure reason should name the actual defect, got: {result.reason!r}")


def test_real_prose_section_still_passes():
    result = checks.check_section_richness(_REAL_PROSE_SECTION)
    assert result.passed, f"real explanatory prose must not be rejected: {result.reason}"


def test_when_opening_sentence_is_not_heading_like():
    # The regression this file exists to pin: "when"/"where" must not be
    # lead-word signals, because ordinary declarative sentences open with them
    # far more often than headings do.
    sentence = ("When the MMU reads a page table entry whose valid bit is "
               "clear, it raises a page fault trap to the operating system.")
    assert not checks._is_heading_like(sentence), (
        "a real subordinate-clause sentence must not be flagged heading-like")


def test_bare_question_is_heading_like():
    assert checks._is_heading_like("What are props in React?")


def test_gerund_heading_is_heading_like():
    assert checks._is_heading_like(
        "Understanding the relationship between parent and child components.")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} section-richness tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SECTION RICHNESS TESTS PASSED.")


if __name__ == "__main__":
    main()
