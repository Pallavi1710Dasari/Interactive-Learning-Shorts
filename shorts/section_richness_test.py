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


#: The real "## What is useEffect?" section that produced "only 2 distinct
#: citable sentence(s) ... need 3 for a 4-beat script" — two definition
#: sentences plus five bulleted examples, none of which ended in a full stop.
_BULLETED_EXAMPLES_SECTION = """\
`useEffect` is a React Hook that lets a component perform side effects.

A side effect is an operation that happens outside the normal process of calculating and displaying the UI.

For example:

- Fetching data from an API
- Updating the document title
- Starting a timer
- Subscribing to an event
- Updating something outside the React component
"""

#: A syllabus dressed as a bullet list rather than prose — must still fail,
#: for the same reason _HEADINGS_ONLY_SECTION above does.
_HEADING_BULLETS_SECTION = """\
## Overview

- Understanding useEffect
- Why hooks exist
- Difference between props and state
"""


def test_bulleted_examples_each_count_as_their_own_citable_span():
    # THE BUG THIS GUARDS AGAINST: check_section_richness's paragraph splitter
    # only breaks on blank lines and sentence-ending punctuation. A bullet
    # list has neither between its own items, so five distinct, individually
    # true examples glued into one unpunctuated run-on line and vanished from
    # the count entirely — not undercounted, LOST — failing a section that
    # was never thin, only unpunctuated.
    spans = checks._citable_spans(_BULLETED_EXAMPLES_SECTION)
    assert len(spans) == 7, f"expected 2 sentences + 5 bullet examples, got {len(spans)}: {spans}"
    for example in ("Fetching data from an API", "Updating the document title",
                    "Starting a timer", "Subscribing to an event",
                    "Updating something outside the React component"):
        assert example in spans, f"{example!r} should be its own citable span"

    result = checks.check_section_richness(_BULLETED_EXAMPLES_SECTION)
    assert result.passed, (
        f"a section with 2 definition sentences + 5 bulleted examples must "
        f"pass the richness gate for a 4-beat script: {result.reason}")


def test_heading_style_bullets_still_do_not_count():
    # The fix for the case above must not turn every bullet into free credit —
    # a bulleted OUTLINE is exactly as uncitable as a bulleted list of
    # headings written as prose, and must still be refused.
    spans = checks._citable_spans(_HEADING_BULLETS_SECTION)
    assert spans == [], f"heading-like bullets must not count as citable spans, got: {spans}"
    result = checks.check_section_richness(_HEADING_BULLETS_SECTION)
    assert not result.passed, "a bulleted outline must still fail the richness gate"


def test_short_bullet_fragment_does_not_count():
    # A one-or-two-word bullet ("- Yes", "- N/A") is not a citable claim
    # either — the same MIN_QUOTE_CHARS floor _table_rows already applies.
    section = "Some things to know:\n\n- Yes\n- No\n"
    spans = checks._citable_spans(section)
    assert spans == [], f"a bullet too short to cite anything should not count, got: {spans}"


def test_bulleted_example_is_still_a_valid_verbatim_citation():
    # check_section_richness counting a bullet as citable must agree with
    # check_source_quotes actually accepting it as a beat's source_quote —
    # otherwise the pre-gate would pass a section check_source_quotes still
    # rejects later, in the exact retry loop this pre-gate exists to save.
    from .schema import Script, Beat
    script = Script(short_id="t1", question="what is a side effect", beats=[
        Beat(line="Ever wondered what a side effect is?", on_screen="hook", visual_ref="v0"),
        Beat(line="A side effect can be fetching data.", on_screen="x", visual_ref="v1",
             source_quote="Fetching data from an API"),
    ])
    result = checks.check_source_quotes(script, _BULLETED_EXAMPLES_SECTION)
    assert result.passed, f"a bullet-sourced quote must pass check_source_quotes: {result.reason}"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} section-richness tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SECTION RICHNESS TESTS PASSED.")


if __name__ == "__main__":
    main()
