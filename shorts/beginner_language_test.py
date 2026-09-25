"""
Step 9 hardening: a deterministic, narrow check for unnecessary jargon.

checks.check_beginner_friendly_language is new. It is deliberately a SMALL,
named word list (facilitate, leverage, abstraction, orchestration,
invocation, paradigm, utilize, instantiate and their close forms) — not a
general reading-level score, which cannot be computed deterministically
without real false-positive risk on legitimate technical vocabulary. Each
hit is excused the moment the source material itself uses the same word,
mirroring skills/script.py's own existing prose rule ("jargon the material
itself introduces stays").

No API key, no network, no real LLM calls — every test calls the grader
directly on a hand-built Script.

    SHORTS_STUB=1 python -m shorts.beginner_language_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks
from shorts.schema import Beat, Script


def _script(*lines: str) -> Script:
    beats = [Beat(line=line, on_screen=f"B{i}", visual_ref=f"v{i}")
            for i, line in enumerate(lines)]
    return Script(short_id="t_lang", question="q", beats=beats)


def test_jargon_word_is_flagged():
    script = _script("A cache can leverage memory to speed up lookups.")
    result = checks.check_beginner_friendly_language(script, source_text="a cache stores values")
    assert not result.passed
    assert "leverage" in result.reason
    print(f"   ok — 'leverage', not in the source, is flagged: {result.reason}")


def test_jargon_word_used_by_the_source_is_allowed():
    script = _script("The abstraction hides the disk's real layout from the program.")
    source = "An abstraction hides the disk's real layout from the program."
    result = checks.check_beginner_friendly_language(script, source_text=source)
    assert result.passed, result.reason
    print("   ok — 'abstraction' is allowed because the source itself uses it")


def test_clean_script_passes():
    script = _script("A cache stores values so a lookup does not repeat the work.")
    result = checks.check_beginner_friendly_language(script, source_text="anything")
    assert result.passed, result.reason
    print("   ok — a script with none of the listed jargon words passes cleanly")


def test_multiple_jargon_words_are_all_reported():
    script = _script("This will facilitate faster access.",
                     "The orchestration layer coordinates the calls.")
    result = checks.check_beginner_friendly_language(script, source_text="nothing relevant")
    assert not result.passed
    assert "facilitate" in result.reason and "orchestration" in result.reason
    print(f"   ok — multiple jargon words across beats are all reported: {result.reason}")


def test_legitimate_technical_terms_not_on_the_list_are_untouched():
    """Not a general jargon detector — recursion, polymorphism, asynchronous
    etc. are real technical vocabulary this check must never touch."""
    script = _script("Recursion means a function calls itself.",
                     "Polymorphism lets one interface have many forms.",
                     "An asynchronous call does not block the caller.")
    result = checks.check_beginner_friendly_language(script, source_text="")
    assert result.passed, result.reason
    print("   ok — legitimate technical terms outside the small named list "
          "are never flagged (this is not a general reading-level score)")


def test_no_source_text_still_reports_every_hit():
    """Without material to check the exception against, every hit is
    reported — the caller has no way to tell 'the source uses it too' from
    'this is a lazy word choice', so it is not asked to."""
    script = _script("We can leverage the existing index.")
    result = checks.check_beginner_friendly_language(script, source_text=None)
    assert not result.passed
    print(f"   ok — with no source_text, a jargon hit is still reported: {result.reason}")


def test_wired_into_run_script_graders_unconditionally():
    script = _script("We can leverage the existing index.")
    results = checks.run_script_graders(script, source_text=None)
    names = [r.name for r in results]
    assert "beginner_friendly_language" in names, names
    print("   ok — check_beginner_friendly_language runs even when no "
          "source_text is passed at all (same unconditional contract as "
          "check_no_interview_structure)")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} beginner-language hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL BEGINNER-LANGUAGE HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
