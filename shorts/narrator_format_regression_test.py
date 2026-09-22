"""
Cross-topic regression tests for the single-narrator script format.

This is the fix that removed the scripted interviewer/student DIALOGUE — see
schema.py's Script/Beat docstrings, checks.py's check_narration_shape /
check_narration_sentence_form, and skills/script.py's SYSTEM prompt. Every
other test file that touches a Script was written (or updated) against ONE
document; this file's whole point is to prove the format holds the same shape
across SEVERAL, unrelated topics and documents — paging, CSS specificity,
stacks, linked lists, hash tables, React state — rather than against a single
fixture that might happen to work by accident.

No API key, no network — config.STUB is set for the whole run, the same way
script_workflow_test.py and smoke_test.py already run offline.

    python -m shorts.narrator_format_regression_test
"""
from pathlib import Path

from . import config, checks
from .schema import Script, Beat, Topic
from .parse import parse_markdown
from .skills.script import write_script

ROOT = Path(__file__).resolve().parent.parent

#: Five real documents, none of them the paging file most other tests already
#: use — a different subject, a different author's prose, a different section
#: length each time. Each entry is (filename, a topic to draft). All five have
#: enough distinct sentences in their first section to fill a full-length
#: short, so every SCRIPT_GRADER is expected to pass, not just the two this
#: file is really about.
DOCS = [
    ("session_18_paging.md", "Why does paging remove external fragmentation?"),
    ("css_specificity.md", "How does the browser score a CSS selector?"),
    ("stack_data_structure.md", "How do push and pop work on a stack?"),
    ("hash_table_basics.md", "How does a hash table find a value without searching?"),
    ("react_usestate_basics.md", "How does a state update trigger a re-render?"),
]

#: linked_list_basics.md's first section is only 3 sentences — genuinely too
#: thin to fill MIN_ANSWERS beats, the same "the stub stays honest" case
#: stubs.py's own module docstring describes. Kept SEPARATE from DOCS, on
#: purpose: this is the case that proves check_narration_shape's rejection is
#: about CONTENT RICHNESS, not a leftover need for a second speaker — a thin
#: section fails it today for exactly the reason it always did, before this
#: format existed at all.
THIN_DOC = ("linked_list_basics.md", "How does a linked list find the next item without an index?")


def _first_section_and_topic(filename: str, question: str):
    sections = parse_markdown(ROOT / "content" / filename)
    section = sections[0]
    topic = Topic(id=f"t_{filename}", topic=question, why_it_matters="m",
                  source_section_id=section.section_id, difficulty="medium")
    return section, topic


def _with_stub(fn):
    """Run `fn()` with config.STUB forced on, restoring it afterwards —
    the same pattern script_workflow_test.py uses throughout."""
    old_stub = config.STUB
    config.STUB = True
    try:
        return fn()
    finally:
        config.STUB = old_stub


def test_every_document_produces_a_single_narrator_script():
    # DOCS plus THIN_DOC — the structural shape below has to hold whether or
    # not the section is rich enough to fill every beat (see THIN_DOC's own
    # comment); only test_every_document_passes_the_narration_graders cares
    # about richness.
    for filename, question in DOCS + [THIN_DOC]:
        section, topic = _first_section_and_topic(filename, question)
        script = _with_stub(lambda: write_script(topic, section))

        # ONE VOICE, EVERY BEAT — no beat requires a second speaker to exist,
        # and every beat this pipeline writes carries the same one.
        assert all(b.speaker == "narrator" for b in script.beats), \
            f"{filename}: not every beat is the same narrator: " \
            f"{[b.speaker for b in script.beats]}"

        # THE OPENING/BODY SPLIT IS POSITIONAL, NOT A ROLE. Beat 0 is the
        # opening (no citation, by design — see checks.check_question_grounded);
        # everything after it is the answer, and every one of THOSE beats is
        # grounded, exactly as strictly as it always was under the old
        # "student beats carry source_quote" rule.
        assert script.opening_beat is script.beats[0]
        assert script.body_beats == script.beats[1:]
        assert all(b.source_quote for b in script.body_beats), \
            f"{filename}: an answer beat has no source_quote"

        print(f"   ok — {filename}: {len(script.beats)} beats, one narrator, "
              f"opening beat 0 + {len(script.body_beats)} grounded answer beat(s)")
    print("   ok — every one of {} unrelated documents produces the same "
          "single-narrator shape, richly-sourced and thin alike".format(len(DOCS) + 1))


def test_a_too_thin_document_is_rejected_for_content_not_for_missing_a_second_speaker():
    # THE CONTROL CASE. linked_list_basics.md's first section only supports 3
    # distinct sentences — one short of MIN_ANSWERS. check_narration_shape
    # still rejects it, exactly as check_dialogue_shape always would have —
    # but the reason has to be about the BEAT COUNT, never about a speaker or
    # role, because there is no second role left to be missing.
    filename, question = THIN_DOC
    section, topic = _first_section_and_topic(filename, question)
    script = _with_stub(lambda: write_script(topic, section))
    result = checks.check_narration_shape(script)

    assert not result.passed, (
        f"{filename} was expected to be too thin for a full-length short — "
        f"if it now passes, either the content changed or this fixture "
        f"needs a different document")
    assert "at least" in result.reason and "answer beat" in result.reason
    for word in ("speaker", "interviewer", "student", "role"):
        assert word not in result.reason.lower(), \
            f"check_narration_shape's rejection mentions {word!r}: {result.reason!r}"
    print(f"   ok — {filename} is rejected for having too few answer beats "
          f"({result.reason!r}), never for a missing second speaker")


def test_every_document_passes_the_narration_graders():
    for filename, question in DOCS:
        section, topic = _first_section_and_topic(filename, question)
        script = _with_stub(lambda: write_script(topic, section))

        results = checks.run_script_graders(script, source_text=section.text)
        by_name = {r.name: r for r in results}

        # THE TWO RENAMED STRUCTURAL GRADERS ARE THERE (formerly
        # check_dialogue_shape / check_qa_sentence_form) — a document that
        # never wired them in would fail silently, not loudly.
        assert "narration_shape" in by_name, (filename, by_name.keys())
        assert "narration_sentence_form" in by_name, (filename, by_name.keys())

        # AND NEITHER READS SPEAKER TO DECIDE ANYTHING — a stub script whose
        # beats are ALL the same speaker still gets graded on beat COUNT and
        # WORD COUNT, exactly as a real two-role script used to.
        assert by_name["narration_shape"].passed, \
            f"{filename}: {by_name['narration_shape'].reason}"
        assert by_name["narration_sentence_form"].passed, \
            f"{filename}: {by_name['narration_sentence_form'].reason}"

        print(f"   ok — {filename}: narration_shape and "
              f"narration_sentence_form both pass a single-narrator script")
    print("   ok — the renamed structural graders run, and pass, across "
          "every document, not just the one they were written against")


def test_schema_no_longer_requires_a_second_speaker():
    # THE STRUCTURAL CLAIM AT THE CENTER OF THIS CHANGE: a Script is valid
    # with every beat carrying the SAME speaker, in ANY order of content —
    # schema.py no longer has a validator (the old starts_with_interviewer)
    # that requires beat 0 to be a particular role. This is what "the
    # mandatory interviewer/student structure is removed" means, made
    # concrete rather than argued for.
    script = Script(short_id="s", question="What happens here?", beats=[
        Beat(speaker="narrator", line="It starts like this.", on_screen="a",
            visual_ref="v1"),
        Beat(speaker="narrator", line="Then this happens.", on_screen="b",
            visual_ref="v2", source_quote="Then this happens."),
    ])
    assert script.beats[0].speaker == script.beats[1].speaker == "narrator"
    print("   ok — a Script with every beat carrying the same speaker "
          "validates cleanly (requirement: no mandatory two-role structure)")

    # AND OLD SAVED DATA STILL LOADS. A unit recorded before this change has
    # "interviewer"/"student" literally in its JSON — Beat.speaker accepts any
    # string precisely so that JSON still parses (see Beat's own docstring).
    legacy = Script(short_id="s2", question="What happens here?", beats=[
        Beat(speaker="interviewer", line="What happens here?", on_screen="a",
            visual_ref="v1"),
        Beat(speaker="student", line="This happens.", on_screen="b",
            visual_ref="v2", source_quote="This happens."),
    ])
    assert legacy.beats[0].speaker == "interviewer"
    print("   ok — a legacy Script with the old interviewer/student values "
          "still loads (backward compatibility with saved units)")

    # A SCRIPT WITH NO BEATS IS STILL REJECTED — has_beats replaced
    # starts_with_interviewer, it did not remove schema validation entirely.
    try:
        Script(short_id="s3", question="What happens here?", beats=[])
        raise AssertionError("Script should reject an empty beats list")
    except Exception as e:
        assert "no beats" in str(e)
    print("   ok — a Script still needs at least one beat (has_beats)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} narrator-format regression tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL NARRATOR FORMAT REGRESSION TESTS PASSED.")


if __name__ == "__main__":
    main()
