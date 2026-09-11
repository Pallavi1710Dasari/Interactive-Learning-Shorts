"""
Offline, deterministic tests for Step 2 of the question workflow: enriching
select.py's output into QuestionSelection objects, without touching the
existing selection policy.

No API key, no network — every LLM call this file exercises goes through
config.STUB / config.SCREEN_QUESTIONS=False instead. This is NOT testing
whether selection picks good topics (that is evals/cases.yaml's job, and it
costs real API calls); it is testing that:

  - QuestionSelection is built correctly from an already-selected TopicList
    (source_title resolution, reason generation)
  - the schema-level guarantees on QuestionSelection hold
  - drop_unanswerable / drop_unsupported / keep_most_important still filter
    exactly as they did before drop_unsupported grew a third return value
  - select_topics_with_notes / select_topics are byte-identical in signature
    and behavior to before this change
  - stub mode produces valid QuestionSelection objects end to end

    python -m shorts.select_workflow_test
"""
from pydantic import ValidationError

from . import config
from .schema import (Section, Topic, TopicList, QuestionSelection, SelectionReason,
                     SectionUnderstanding, TeachingStep, ConfusionPlan)
from .skills import select
from . import checks


def _section(section_id="3.1", title="Why Paging Exists", text=None) -> Section:
    text = text or (
        "Paging solves external fragmentation by dividing memory into equal "
        "fixed-size frames. Each process is divided into pages of the same size, "
        "and the operating system maintains a page table mapping pages to frames. "
        "Because every frame is the same size, a free frame always fits the next "
        "page, which is exactly what contiguous allocation could not guarantee."
    )
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=10)


def _topic(**overrides) -> Topic:
    data = dict(
        id="t_paging", topic="Why does paging remove external fragmentation?",
        why_it_matters="This is the central mechanism the rest of the session builds on.",
        source_section_id="3.1", difficulty="medium", importance=5,
        concept="paging and fragmentation",
        answer_quote="Paging solves external fragmentation by dividing memory into "
                     "equal fixed-size frames.",
    )
    data.update(overrides)
    return Topic(**data)


def _understanding(section_id="3.1", core_idea="", teaching_sequence=None,
                   confusion_plan=None) -> SectionUnderstanding:
    """A minimal SectionUnderstanding with only the fields a given test needs
    populated — everything else stays at its honest empty default, the same
    contract SectionUnderstanding itself documents."""
    return SectionUnderstanding(section_id=section_id, core_idea=core_idea,
                                teaching_sequence=teaching_sequence or [],
                                confusion_plan=confusion_plan)


# --------------------------------------------------------------------- A, B, C, D
# QuestionSelection construction: source_title resolution and the schema guarantees
# on `reasons`.

def test_source_title_resolved_from_actual_section():
    section = _section()
    topic = _topic()
    selections = select.build_question_selections(TopicList(topics=[topic]), [section])
    assert len(selections) == 1
    sel = selections[0]
    assert sel.source_title == "Why Paging Exists"

    result = checks.check_question_selection_source_title(sel, [section])
    assert result.passed, result.reason
    print("   ok — source_title resolves to the real Section.title, and the "
          "grader confirms it")


def test_source_title_grader_catches_a_mismatch():
    section = _section()
    topic = _topic()
    sel = QuestionSelection(topic=topic, source_title="Some Other Title",
                            reasons=[SelectionReason(category="other", explanation="x")])
    result = checks.check_question_selection_source_title(sel, [section])
    assert not result.passed
    print("   ok — the grader fails a selection whose source_title has drifted")


def test_source_title_grader_catches_an_unknown_section():
    topic = _topic(source_section_id="9.9")
    sel = QuestionSelection(topic=topic, source_title="Whatever",
                            reasons=[SelectionReason(category="other", explanation="x")])
    result = checks.check_question_selection_source_title(sel, [_section()])
    assert not result.passed
    print("   ok — the grader fails when source_section_id matches no parsed section")


def test_every_built_selection_has_at_least_one_reason():
    section = _section()
    topic = _topic()
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    assert len(sel.reasons) >= 1
    assert any(r.explanation.strip() for r in sel.reasons)
    print(f"   ok — built selection carries {len(sel.reasons)} reason(s), "
          f"none of them blank")


def test_reasons_without_understanding_cover_importance_grounding_and_distinctness():
    section = _section()
    topic = _topic(importance=5, concept="paging and fragmentation",
                   why_it_matters="the whole session depends on this")
    # No SectionUnderstanding supplied — the ordinary case today, since select.py's
    # own pipeline never computes one.
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    categories = [r.category for r in sel.reasons]

    assert "importance" in categories
    # answer_quote present and verified -> concrete_and_answerable.
    assert "concrete_and_answerable" in categories
    # concept present -> distinct_angle.
    assert "distinct_angle" in categories
    # NEITHER of these is claimed without SectionUnderstanding evidence, however
    # high the importance score is — see the importance/foundational/
    # commonly_confused decoupling tests below.
    assert "foundational" not in categories
    assert "commonly_confused" not in categories
    # why_it_matters text is folded into the importance reason verbatim, not
    # replaced by boilerplate, and not relabelled as a foundational claim.
    importance_reason = next(r for r in sel.reasons if r.category == "importance")
    assert "the whole session depends on this" in importance_reason.explanation
    print("   ok — without SectionUnderstanding, reasons cover importance/grounding/"
          "distinctness only — foundational and commonly_confused are absent")


# ------------------------------------------------- importance/foundational/confusion
# decoupling. These are the tests this step of the review specifically asked for:
# proving the importance score alone can never produce FOUNDATIONAL or
# COMMONLY_CONFUSED, and that real SectionUnderstanding evidence can produce them
# independently of the score.

def test_importance_alone_never_produces_foundational_or_commonly_confused():
    section = _section()
    for score in (5, 4, 3, 2):
        topic = _topic(id=f"t{score}", importance=score)
        [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
        categories = {r.category for r in sel.reasons}
        assert "foundational" not in categories, (score, categories)
        assert "commonly_confused" not in categories, (score, categories)
    print("   ok — importance scores 2-5 alone (no understanding) never produce "
          "foundational or commonly_confused")


def test_foundational_reason_requires_actual_understanding_evidence():
    section = _section()
    # LOW importance is the point here: foundational-ness must not be read off
    # the score, so this proves it can appear even when importance would not
    # have implied it under the old (incorrect) mapping.
    topic = _topic(importance=3, concept="paging and fragmentation")
    understanding = _understanding(
        core_idea="Paging removes external fragmentation using fixed-size frames.",
        teaching_sequence=[
            TeachingStep(concept="fixed-size frames", purpose="establish the unit "
                        "everything else maps onto", explanation_goal="learner can "
                        "name a frame"),
            TeachingStep(concept="the page table", purpose="builds on frames to "
                        "explain translation", explanation_goal="learner can "
                        "explain a lookup"),
        ])
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section],
        understanding_by_section={"3.1": understanding})
    categories = [r.category for r in sel.reasons]
    assert "foundational" in categories, categories
    reason = next(r for r in sel.reasons if r.category == "foundational")
    assert "fixed-size frames" in reason.explanation
    print("   ok — foundational appears when SectionUnderstanding shows this "
          "concept IS the core idea with steps built on it — at importance 3/5, "
          "not because of the score")


def test_commonly_confused_reason_requires_actual_confusion_plan_evidence():
    section = _section()
    # Again a LOW importance, on purpose.
    topic = _topic(importance=3, concept="paging and fragmentation")
    plan = ConfusionPlan(
        need="required",
        confusion="paging removes all fragmentation entirely",
        correct_understanding="paging removes external fragmentation but internal "
                              "fragmentation remains inside each frame",
        learner_takeaway="paging trades one kind of waste for another",
    )
    understanding = _understanding(confusion_plan=plan)
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section],
        understanding_by_section={"3.1": understanding})
    categories = [r.category for r in sel.reasons]
    assert "commonly_confused" in categories, categories
    reason = next(r for r in sel.reasons if r.category == "commonly_confused")
    assert "removes all fragmentation entirely" in reason.explanation
    assert "internal fragmentation remains" in reason.explanation
    print("   ok — commonly_confused appears when the section's own confusion_plan "
          "is decided AND overlaps this topic's concept — at importance 3/5")


def test_confusion_plan_not_needed_does_not_produce_commonly_confused():
    section = _section()
    topic = _topic(importance=5, concept="paging and fragmentation")
    plan = ConfusionPlan(need="not_needed")
    understanding = _understanding(confusion_plan=plan)
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section],
        understanding_by_section={"3.1": understanding})
    categories = {r.category for r in sel.reasons}
    assert "commonly_confused" not in categories
    print("   ok — a confusion_plan the section itself marked not_needed never "
          "produces commonly_confused, even at importance 5/5")


def test_unrelated_understanding_does_not_leak_onto_this_topic():
    section = _section()
    topic = _topic(importance=5, concept="paging and fragmentation")
    # A real understanding, but of a DIFFERENT concept (the TLB) from the same
    # section — this must not attach to a topic about paging/fragmentation.
    understanding = _understanding(
        core_idea="The TLB caches recent translations to avoid page table walks.",
        teaching_sequence=[
            TeachingStep(concept="tlb hit", purpose="p1", explanation_goal="g1"),
            TeachingStep(concept="tlb miss", purpose="p2", explanation_goal="g2"),
        ],
        confusion_plan=ConfusionPlan(
            need="required", confusion="the TLB always guarantees a hit",
            correct_understanding="a TLB miss still requires a page table walk",
            learner_takeaway="a TLB miss is not free"),
    )
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section],
        understanding_by_section={"3.1": understanding})
    categories = {r.category for r in sel.reasons}
    assert "foundational" not in categories
    assert "commonly_confused" not in categories
    print("   ok — an unrelated SectionUnderstanding (the TLB) does not leak "
          "foundational/commonly_confused onto a different topic (paging) in "
          "the same section")


def test_distinct_angle_wording_does_not_overclaim_educational_distinctness():
    section = _section()
    topic = _topic(concept="paging and fragmentation")
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    reason = next(r for r in sel.reasons if r.category == "distinct_angle")
    assert "deck coverage" in reason.explanation
    assert "more important" in reason.explanation or "more confusable" in reason.explanation
    print("   ok — distinct_angle's wording is scoped to deck coverage, not a "
          "claim of inherent pedagogical distinctness (requirement 5)")


def test_screen_reason_carries_the_screens_own_why():
    section = _section()
    topic = _topic()
    screen_reasons = {topic.id: "the section explicitly walks the fixed-size "
                                "frame mechanism and demonstrates it"}
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section], screen_reasons)
    matches = [r for r in sel.reasons
              if "fixed-size frame mechanism" in r.explanation]
    assert matches, sel.reasons
    print("   ok — the supportability screen's own `why` is surfaced as a reason "
          "instead of being discarded")


def test_question_selection_rejects_empty_reasons():
    try:
        QuestionSelection(topic=_topic(), source_title="x", reasons=[])
        raise AssertionError("QuestionSelection should require at least one reason")
    except ValidationError:
        pass
    print("   ok — QuestionSelection(reasons=[]) is rejected (requirement B)")


def test_question_selection_rejects_all_blank_reasons():
    try:
        QuestionSelection(topic=_topic(), source_title="x", reasons=[
            SelectionReason(category="other", explanation="   "),
            SelectionReason(category="importance", explanation=""),
        ])
        raise AssertionError("QuestionSelection should reject all-blank reasons")
    except ValidationError:
        pass
    print("   ok — reasons that are all blank/whitespace are rejected (requirement C)")


def test_selection_reason_rejects_invalid_category():
    try:
        SelectionReason(category="not_a_real_category", explanation="x")
        raise AssertionError("an invalid SelectionReasonCategory should be rejected")
    except ValidationError:
        pass
    print("   ok — an invalid reason category is rejected by schema validation "
          "(requirement D)")


# --------------------------------------------------------------------------- E
# The existing filters, unchanged in behavior.

def test_drop_unanswerable_still_drops_ungrounded_topics():
    section = _section()
    good = _topic(id="good", answer_quote="Paging solves external fragmentation by "
                                          "dividing memory into equal fixed-size frames.")
    bad = _topic(id="bad", answer_quote="This sentence appears nowhere in the section.")
    topics, notes = select.drop_unanswerable(TopicList(topics=[good, bad]), [section])
    ids = {t.id for t in topics.topics}
    assert ids == {"good"}
    assert any("bad" in n for n in notes)
    print("   ok — drop_unanswerable still drops a topic whose answer_quote is "
          "not in the material")


def test_drop_unsupported_returns_three_values_and_still_filters():
    old_screen = config.SCREEN_QUESTIONS
    config.SCREEN_QUESTIONS = False   # isolate pass 1; no LLM call either way
    try:
        section = _section()
        on_topic = _topic(id="on_topic",
                          topic="Why does paging remove external fragmentation?")
        off_topic = _topic(id="off_topic",
                           topic="Why does quantum entanglement enable teleportation?")
        result = select.drop_unsupported(TopicList(topics=[on_topic, off_topic]),
                                         [section])
        assert len(result) == 3, "drop_unsupported must return (topics, notes, reasons)"
        topics, notes, screen_reasons = result
        ids = {t.id for t in topics.topics}
        assert "on_topic" in ids
        assert "off_topic" not in ids
        assert screen_reasons == {}, "pass 2 was disabled; nothing should be recorded"
    finally:
        config.SCREEN_QUESTIONS = old_screen
    print("   ok — drop_unsupported still drops an off-topic question and now "
          "also returns a (possibly empty) screen_reasons dict")


def test_keep_most_important_still_enforces_importance_yesno_and_duplicates():
    weak = _topic(id="weak", topic="What does the operating system do?",
                  concept="os overview", importance=2)
    yesno = _topic(id="yesno", topic="Does paging remove all fragmentation?",
                   concept="paging fragmentation verdict", importance=5)
    good = _topic(id="good", topic="Why does paging remove external fragmentation?",
                 concept="paging and fragmentation", importance=5)
    duplicate = _topic(id="duplicate",
                       topic="Why does paging get rid of external fragmentation?",
                       concept="paging and fragmentation", importance=4)

    topics, notes = select.keep_most_important(
        TopicList(topics=[weak, yesno, good, duplicate]), target=5)
    ids = {t.id for t in topics.topics}

    assert "weak" not in ids, "importance 2 must still be dropped"
    assert "yesno" not in ids, "a yes/no question must still be dropped"
    assert "good" in ids
    assert "duplicate" not in ids, "a near-duplicate concept must still be dropped"
    print("   ok — keep_most_important still enforces the importance floor, the "
          "yes/no ban, and concept/duplicate dedup")


# --------------------------------------------------------------------------- F
# Existing TopicList/API consumers stay compatible.

def test_select_topics_with_notes_signature_is_unchanged():
    old_stub = config.STUB
    config.STUB = True
    try:
        section = _section()
        result = select.select_topics_with_notes([section], target=1)
        assert isinstance(result, tuple) and len(result) == 2, (
            "select_topics_with_notes must still return exactly (TopicList, notes)")
        topics, notes = result
        assert isinstance(topics, TopicList)
        assert isinstance(notes, list)

        topic_list = select.select_topics([section], target=1)
        assert isinstance(topic_list, TopicList)
    finally:
        config.STUB = old_stub
    print("   ok — select_topics_with_notes/select_topics keep their exact "
          "pre-existing return shape (requirement F)")


# --------------------------------------------------------------------------- G
# Stub mode.

def test_stub_mode_produces_valid_question_selections():
    old_stub = config.STUB
    config.STUB = True
    try:
        section = _section()
        topics, notes, selections = select.select_topics_with_selections(
            [section], target=1)
        assert isinstance(topics, TopicList)
        assert isinstance(notes, list)
        assert selections, "stub mode should still produce at least one selection"
        for sel in selections:
            assert isinstance(sel, QuestionSelection)   # validated by construction
            assert sel.reasons
            result = checks.check_question_selection_source_title(sel, [section])
            assert result.passed, result.reason
    finally:
        config.STUB = old_stub
    print(f"   ok — stub mode produced {len(selections)} valid QuestionSelection(s), "
          f"each with a correct source_title (requirement G)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} select-workflow tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SELECT WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
