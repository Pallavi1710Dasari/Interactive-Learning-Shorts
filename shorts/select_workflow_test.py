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
                     SectionUnderstanding, TeachingStep, ConfusionPlan,
                     QuestionWorkflow, QuestionApproval)
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
    # why_it_matters is NEVER folded into the importance reason — it is
    # shown separately, verbatim, as the card's own "Learning outcome" field
    # (web/src/StepApprove.tsx). Repeating it here used to mean a reviewer
    # read the same sentence twice; this reason now explains the RUBRIC TIER
    # on its own terms instead.
    importance_reason = next(r for r in sel.reasons if r.category == "importance")
    assert "the whole session depends on this" not in importance_reason.explanation
    assert "5/5" in importance_reason.explanation
    print("   ok — without SectionUnderstanding, reasons cover importance/grounding/"
          "distinctness only — foundational and commonly_confused are absent, and "
          "importance never repeats why_it_matters")


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
    # UPDATED FOR ROUND 3: the screen's own verdict is surfaced only when
    # there is no grounded answer_quote to prefer instead — see
    # _concrete_and_answerable_reason. A topic WITHOUT an answer_quote is
    # what exercises that fallback now; a topic with both used to surface
    # BOTH as two separate concrete_and_answerable reasons, which was
    # exactly the duplicate-category bug this round fixes.
    section = _section()
    topic = _topic(answer_quote=None)
    screen_reasons = {topic.id: "the section explicitly walks the fixed-size "
                                "frame mechanism and demonstrates it"}
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section], screen_reasons)
    matches = [r for r in sel.reasons
              if "fixed-size frame mechanism" in r.explanation]
    assert matches, sel.reasons
    print("   ok — the supportability screen's own `why` is surfaced as a reason "
          "when there is no grounded quote to prefer instead")


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


# ------------------------------------------------------- E2. foundational tie-break
#
# THE ACTUAL BUG. keep_most_important used to sort purely by importance, and
# `sorted` is stable — so two candidates tied at the same score kept whatever
# order the model happened to list them in. Confirmed against a real React
# useState document (content/react_usestate_basics.md, 4 sections, the
# foundational "what state is" placed LAST): across five real selection
# calls, that section and a later consequence of it ("what happens when you
# call a setter") tied at 5/5 importance every time, and the consequence won
# every time — not because it was more foundational, but because the model
# listed it first, which correlated with document order. These tests prove
# the fix deterministically, without spending an API call: is_foundational
# now breaks the tie, and its absence (older data, or a model that skipped
# the field) falls back to exactly the old, list-order behavior rather than
# crashing or changing shape.

def test_foundational_flag_breaks_a_tie_the_old_sort_got_wrong():
    # Same importance, same shape as the real failure: the definition
    # (foundational) is listed SECOND, the consequence FIRST — reproducing
    # the exact input order that used to win.
    consequence = _topic(id="consequence", importance=5, is_foundational=False,
                        concept="state update triggers re-render",
                        topic="What happens when you call a state setter?")
    definition = _topic(id="definition", importance=5, is_foundational=True,
                        foundational_note="the re-render topic assumes the "
                                          "learner already knows what state is",
                        concept="what state means",
                        topic="What does it mean for a value to be React state?")
    topics, notes = select.keep_most_important(
        TopicList(topics=[consequence, definition]), target=2)
    ids = [t.id for t in topics.topics]
    assert ids == ["definition", "consequence"], ids
    print("   ok — a foundational candidate tied on importance is promoted "
          "ahead of a non-foundational one, regardless of list order")


def test_tie_with_no_foundational_signal_keeps_old_list_order_behavior():
    # Neither topic sets is_foundational (None, the ordinary case for a model
    # that skipped the new field, or older cached data) — must fall back to
    # exactly the prior behavior (stable sort on input order), not raise and
    # not silently reorder something the model never judged either way.
    first = _topic(id="first", importance=4, concept="concept a",
                  topic="Why does the first mechanism matter here?")
    second = _topic(id="second", importance=4, concept="concept b",
                   topic="Why does the second mechanism matter here?")
    topics, notes = select.keep_most_important(
        TopicList(topics=[first, second]), target=2)
    assert [t.id for t in topics.topics] == ["first", "second"]
    print("   ok — with no is_foundational signal on either side, a tie "
          "still falls back to input order exactly as before this change")


def test_foundational_does_not_bypass_the_duplicate_or_yesno_filters():
    # is_foundational is a tie-break among SURVIVORS, not a bypass of the
    # existing gates. A foundational-flagged near-duplicate must still be
    # dropped, and a foundational-flagged yes/no question must still be
    # dropped — otherwise the fix would open a new hole in exactly the
    # filters this file already guards.
    kept_one = _topic(id="kept_one", importance=5, is_foundational=True,
                     concept="paging and fragmentation",
                     topic="Why does paging remove external fragmentation?")
    dup = _topic(id="dup", importance=5, is_foundational=True,
               concept="paging and fragmentation",
               topic="Why does paging get rid of external fragmentation?")
    yesno = _topic(id="yesno", importance=5, is_foundational=True,
                  concept="paging verdict",
                  topic="Does paging remove all fragmentation?")
    topics, notes = select.keep_most_important(
        TopicList(topics=[kept_one, dup, yesno]), target=3)
    ids = {t.id for t in topics.topics}
    assert ids == {"kept_one"}, ids
    print("   ok — is_foundational=True does not exempt a topic from the "
          "duplicate-concept or yes/no filters")


def test_several_distinct_concepts_rank_foundational_first_among_ties():
    # The full React useState shape, built by hand instead of via a live
    # selection call: 4 distinct concepts, 2 tied at the top, only one of
    # which is genuinely foundational to the other.
    rerender = _topic(id="rerender", importance=5, is_foundational=False,
                     concept="state update triggers re-render",
                     topic="What happens when you call a state setter?")
    definition = _topic(id="definition", importance=5, is_foundational=True,
                       foundational_note="both the re-render and persistence "
                                        "topics assume state is already understood",
                       concept="what state means",
                       topic="What does it mean for a value to be React state?")
    var_fails = _topic(id="var_fails", importance=4, is_foundational=False,
                      concept="plain variable vs state",
                      topic="Why doesn't reassigning a plain variable update the screen?")
    persistence = _topic(id="persistence", importance=4, is_foundational=False,
                        concept="useState persistence mechanism",
                        topic="How does useState remember a value across renders?")
    topics, notes = select.keep_most_important(
        TopicList(topics=[rerender, definition, var_fails, persistence]), target=4)
    ids = [t.id for t in topics.topics]
    assert ids[0] == "definition", ids
    assert set(ids) == {"rerender", "definition", "var_fails", "persistence"}
    print(f"   ok — all 4 distinct concepts kept, foundational one ranked "
          f"first despite tying on importance: {ids}")


def test_single_meaningful_concept_survives_unpadded():
    # A short reading may genuinely contain only one thing worth a short.
    # keep_most_important (and TopicList's own validator) must not force
    # padding or reject a list of exactly one.
    only = _topic(id="only", importance=5)
    topics, notes = select.keep_most_important(TopicList(topics=[only]), target=5)
    assert [t.id for t in topics.topics] == ["only"]
    print("   ok — a single-concept candidate list is kept as-is, not padded "
          "or rejected for being short of the target")


def test_foundational_reason_surfaces_before_any_section_understanding_exists():
    # THE OTHER HALF OF THE FIX. A human reviewing Step 1's output (the
    # /api/material response) sees QuestionSelection.reasons before any
    # SectionUnderstanding has ever been computed for this document — see
    # server.py's /api/material, which calls select_topics_with_selections
    # with no understanding_by_section at all. Before this change,
    # "foundational" could therefore never appear on the FIRST screen a human
    # actually reviews; it only ever appeared after a script's own section had
    # already been read, i.e. after the human had already approved something.
    section = _section()
    topic = _topic(importance=5, is_foundational=True,
                  foundational_note="the re-render topic in this material "
                                    "assumes this one is already understood")
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    categories = [r.category for r in sel.reasons]
    assert "foundational" in categories, categories
    reason = next(r for r in sel.reasons if r.category == "foundational")
    assert "re-render topic" in reason.explanation
    assert "selection" in reason.explanation.lower()
    print("   ok — is_foundational produces a foundational reason with NO "
          "SectionUnderstanding supplied, i.e. it is visible on the very "
          "first screen a human reviews")


def test_foundational_reason_absent_when_flag_is_false_or_unset():
    section = _section()
    for flag in (False, None):
        topic = _topic(id=f"t_{flag}", importance=5, is_foundational=flag)
        [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
        categories = {r.category for r in sel.reasons}
        assert "foundational" not in categories, (flag, categories)
    print("   ok — is_foundational=False or unset never produces a "
          "foundational reason (no false claims from an unset signal)")


def test_section_understanding_evidence_still_wins_over_select_time_signal():
    # When BOTH sources exist, the validated per-section reading is used, not
    # the earlier, weaker cross-candidate comparison — they must not blend
    # into one claim, per _foundational_reason's own docstring.
    section = _section()
    topic = _topic(importance=3, concept="paging and fragmentation",
                  is_foundational=True, foundational_note="a select-time guess")
    understanding = _understanding(
        core_idea="Paging removes external fragmentation using fixed-size frames.",
        teaching_sequence=[
            TeachingStep(concept="fixed-size frames", purpose="p1", explanation_goal="g1"),
            TeachingStep(concept="the page table", purpose="p2", explanation_goal="g2"),
        ])
    [sel] = select.build_question_selections(
        TopicList(topics=[topic]), [section],
        understanding_by_section={"3.1": understanding})
    reason = next(r for r in sel.reasons if r.category == "foundational")
    assert "fixed-size frames" in reason.explanation
    assert "select-time guess" not in reason.explanation
    print("   ok — when SectionUnderstanding evidence is available it is used "
          "verbatim, not blended with the earlier select-time signal")


# ------------------------------------------------------- E3. Step 2 propagation
#
# Requirement 4: the concept Step 1 selected must reach Step 2 (framing/script)
# unchanged and traceably. QuestionWorkflow.approved_topic is the one gate
# everything past selection reads (see schema.py) — it is built by
# model_copy(update={"topic": effective_question}), which means every OTHER
# field, including the new is_foundational/foundational_note, carries through
# automatically. This test locks that behavior in rather than assuming it.

def test_selected_concept_propagates_unchanged_into_step_2():
    section = _section()
    topic = _topic(importance=5, is_foundational=True,
                  foundational_note="everything else in this material builds on it",
                  concept="what state means", source_section_id="3.1")
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    workflow = QuestionWorkflow(
        selection=sel,
        question_approval=QuestionApproval(status="approved"))

    approved = workflow.approved_topic
    assert approved is not None, "an approved workflow must expose approved_topic"
    assert approved.id == topic.id
    assert approved.concept == "what state means"
    assert approved.source_section_id == "3.1"
    assert approved.is_foundational is True
    assert approved.foundational_note == "everything else in this material builds on it"
    # effective_question is substituted in; everything else is the original topic.
    assert approved.topic == workflow.effective_question == topic.topic
    print("   ok — the concept (id, concept, source_section_id, foundational "
          "evidence) reaches Step 2 unchanged once the question is approved")


def test_unapproved_selection_never_exposes_a_topic_to_step_2():
    section = _section()
    topic = _topic()
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    workflow = QuestionWorkflow(selection=sel)   # default status: "pending"
    assert workflow.approved_topic is None
    print("   ok — a pending (unapproved) selection is not silently handed to "
          "Step 2 — approved_topic stays None until a human approves it")


# ------------------------------------------------- E5. round 2: a real reported bug
#
# A live user report against a React useState document: the app selected the
# state-CHANGE mechanism ("what sequence of events happens after you call a
# state setter") at 5/5 over the foundational "what is state in React?"
# concept, AND the "why this question was selected" panel showed empty
# bullets. Traced to two independent defects:
#
#   1. is_foundational only ever broke a TIE (equal importance) — when the
#      base rubric scored the foundational concept a point BELOW the
#      mechanism (the rubric's own "a definition... NOT WORTH A SHORT" tier
#      language structurally punished a foundational concept that happened
#      to be phrased as "what is X"), no tie ever occurred and the
#      foundational signal never got a chance to matter. Fixed in SYSTEM's
#      rubric text, not testable offline (it is prompt wording); these tests
#      instead lock in that when scores GENUINELY differ, the higher score
#      still wins — foundational-ness is not supposed to override that, and
#      never did; the bug was that it also never got a fair shot upstream.
#   2. QuestionSelection.reasons could carry an individual blank-explanation
#      entry, which the UI renders as a bullet with nothing in it. Fixed by
#      making the schema validator FILTER blanks, not just check "at least
#      one is real". Testable offline — see below.

def test_higher_importance_still_wins_over_a_lower_scored_foundational_topic():
    # THE "NOT A BLIND OVERRIDE" REQUIREMENT. A foundational flag must never
    # promote a topic over one that scored GENUINELY higher on the rubric —
    # only over one that TIED it. This is deliberate design, not a gap: see
    # keep_most_important's own docstring on the sort key.
    weaker_foundational = _topic(id="foundational_but_weaker", importance=3,
                                is_foundational=True,
                                foundational_note="the mechanism below assumes this",
                                concept="what state is",
                                topic="What is state in a React component?")
    stronger_mechanism = _topic(id="mechanism", importance=5, is_foundational=False,
                               concept="state change mechanism",
                               topic="What sequence of events happens after you "
                                    "call a state setter function?")
    topics, notes = select.keep_most_important(
        TopicList(topics=[weaker_foundational, stronger_mechanism]), target=2)
    ids = [t.id for t in topics.topics]
    assert ids == ["mechanism", "foundational_but_weaker"], ids
    print("   ok — a genuinely higher importance score still wins over a lower-"
          "scored foundational topic; is_foundational only breaks real ties")


def test_foundational_status_survives_ranking_and_the_step_2_handoff():
    section = _section()
    winner = _topic(id="winner", importance=5, is_foundational=True,
                   foundational_note="everything else in this material assumes it",
                   concept="what state is", source_section_id="3.1",
                   topic="What is state in a React component?")
    runner_up = _topic(id="runner_up", importance=5, is_foundational=False,
                      concept="state change mechanism",
                      topic="What happens after you call a state setter?")
    ranked, _notes = select.keep_most_important(
        TopicList(topics=[runner_up, winner]), target=2)
    assert ranked.topics[0].id == "winner", [t.id for t in ranked.topics]
    assert ranked.topics[0].is_foundational is True

    [sel] = [s for s in select.build_question_selections(ranked, [section])
            if s.topic.id == "winner"]
    workflow = QuestionWorkflow(selection=sel,
                               question_approval=QuestionApproval(status="approved"))
    approved = workflow.approved_topic
    assert approved.is_foundational is True
    assert approved.foundational_note == "everything else in this material assumes it"
    print("   ok — foundational status survives being re-ranked ahead of a tied "
          "competitor AND the Step 2 handoff (approved_topic) unchanged")


def test_blank_reason_never_reaches_the_reviewer():
    # THE EMPTY-BULLETS BUG. A SelectionReason with a blank explanation must
    # never survive into QuestionSelection.reasons — regardless of which
    # code path produced it, since the UI renders every surviving entry as
    # its own bullet with no blank-check of its own.
    topic = _topic()
    real = SelectionReason(category="importance", explanation="Scored 5/5.")
    blank = SelectionReason(category="other", explanation="   ")
    also_blank = SelectionReason(category="distinct_angle", explanation="")
    sel = QuestionSelection(topic=topic, source_title="x",
                           reasons=[real, blank, also_blank])
    assert len(sel.reasons) == 1
    assert all(r.explanation.strip() for r in sel.reasons)
    print("   ok — blank-explanation reasons are filtered out at construction, "
          "never reaching a reviewer as an empty bullet")


def test_selection_with_only_blank_reasons_still_raises():
    # The filter must not silently turn "no real explanation at all" into a
    # quietly empty (but schema-valid) reasons list — that would trade an
    # empty-bullet bug for an empty-panel bug. This must still fail loud.
    topic = _topic()
    try:
        QuestionSelection(topic=topic, source_title="x", reasons=[
            SelectionReason(category="other", explanation=""),
            SelectionReason(category="importance", explanation="   "),
        ])
        raise AssertionError("all-blank reasons must still be rejected")
    except ValidationError:
        pass
    print("   ok — a selection with NO real reason anywhere still raises, "
          "rather than silently validating with an empty reasons list")


def test_candidate_comparison_reason_states_facts_not_invented_narrative():
    section = _section()
    winner = _topic(id="winner", importance=5, is_foundational=True,
                   foundational_note="the mechanism assumes this",
                   concept="what state is",
                   topic="What is state in a React component?")
    runner_up = _topic(id="runner_up", importance=4, is_foundational=False,
                      concept="state change mechanism",
                      topic="What happens after you call a state setter?")
    ranked = TopicList(topics=[winner, runner_up])   # already in final rank order
    [top_sel, _] = select.build_question_selections(ranked, [section])
    comparisons = [r for r in top_sel.reasons if r.category == "candidate_comparison"]
    assert len(comparisons) == 1, top_sel.reasons
    text = comparisons[0].explanation
    assert "state change mechanism" in text
    assert "5/5" in text and "4/5" in text
    print(f"   ok — the top pick's reasons name the actual runner-up and both "
          f"scores instead of just '5/5, highest tier': {text!r}")


def test_candidate_comparison_reason_absent_for_a_single_candidate():
    # No runner-up exists — nothing to compare against, so nothing invented.
    section = _section()
    topic = _topic()
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section])
    assert not any(r.category == "candidate_comparison" for r in sel.reasons)
    print("   ok — candidate_comparison is absent when there is no runner-up "
          "to compare against, rather than fabricating a comparison")


def test_candidate_comparison_only_attaches_to_the_top_ranked_topic():
    section = _section()
    winner = _topic(id="winner", importance=5, concept="a", topic="Why does A matter?")
    second = _topic(id="second", importance=4, concept="b", topic="Why does B matter?")
    ranked = TopicList(topics=[winner, second])
    selections = select.build_question_selections(ranked, [section])
    winner_sel = next(s for s in selections if s.topic.id == "winner")
    second_sel = next(s for s in selections if s.topic.id == "second")
    assert any(r.category == "candidate_comparison" for r in winner_sel.reasons)
    assert not any(r.category == "candidate_comparison" for r in second_sel.reasons)
    print("   ok — candidate_comparison only appears on the #1 topic, not on "
          "every runner-up down the list")


# ------------------------------------------------- E6. round 3: dedup + truthful
# target=1 comparison
#
# The live bug this round fixes: (1) concrete_and_answerable shown twice with
# overlapping text, (2) importance repeating the "Learning outcome" field
# verbatim, (3) the top reason repeated again inside the expanded list
# (frontend-only, not testable here), (4) candidate_comparison silently a
# no-op at target=1 because the runner-up had already been cut before
# build_question_selections ever saw it.

def test_no_duplicate_reason_categories_are_ever_produced():
    # A topic with BOTH a verified answer_quote AND a distinct screen verdict
    # — the exact condition that used to produce two concrete_and_answerable
    # bullets.
    section = _section()
    topic = _topic()
    screen_reasons = {topic.id: "the section explicitly walks the fixed-size "
                                "frame mechanism and demonstrates it"}
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section],
                                             screen_reasons)
    categories = [r.category for r in sel.reasons]
    assert len(categories) == len(set(categories)), categories
    print(f"   ok — no category appears twice, even when both grounding and "
          f"screen evidence exist for the same topic: {categories}")


def test_concrete_and_answerable_prefers_grounded_quote_over_screen_verdict():
    section = _section()
    topic = _topic()   # has a real answer_quote from _topic()'s own defaults
    screen_reasons = {topic.id: "a completely different sentence about the screen"}
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section],
                                             screen_reasons)
    ca_reasons = [r for r in sel.reasons if r.category == "concrete_and_answerable"]
    assert len(ca_reasons) == 1, ca_reasons
    assert "states the answer directly" in ca_reasons[0].explanation
    assert "a completely different sentence" not in ca_reasons[0].explanation
    print("   ok — concrete_and_answerable prefers the grounded answer_quote "
          "over the screen's own verdict when both are available")


def test_concrete_and_answerable_falls_back_to_screen_when_no_quote():
    section = _section()
    topic = _topic(answer_quote=None)
    screen_reasons = {topic.id: "the section settles this through worked examples"}
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section],
                                             screen_reasons)
    ca_reasons = [r for r in sel.reasons if r.category == "concrete_and_answerable"]
    assert len(ca_reasons) == 1
    assert "worked examples" in ca_reasons[0].explanation
    print("   ok — the screen's own verdict is used when there is no quote to "
          "show — a real, distinct detail, not a redundant second voice")


def test_dedupe_by_category_keeps_first_occurrence():
    a = SelectionReason(category="concrete_and_answerable", explanation="first")
    b = SelectionReason(category="importance", explanation="second")
    c = SelectionReason(category="concrete_and_answerable", explanation="third")
    deduped = select._dedupe_by_category([a, b, c])
    assert [r.explanation for r in deduped] == ["first", "second"]
    print("   ok — _dedupe_by_category keeps the first reason per category "
          "and drops later ones with the same category")


def test_comparison_uses_the_pre_cut_scored_pool_at_target_1():
    # THE ACTUAL BUG. A foundational competitor scores 4/5, a mechanism
    # scores 5/5 and wins outright (not a tie — see round 2). With target=1,
    # ONLY the mechanism is kept in `topics` — but `scored_pool` still
    # carries both, so the comparison must still name the real runner-up.
    winner = _topic(id="mechanism", importance=5, is_foundational=False,
                   concept="state change mechanism",
                   topic="What happens after you call a state setter?")
    runner_up = _topic(id="foundational", importance=4, is_foundational=True,
                      foundational_note="the mechanism above assumes this",
                      concept="what state is",
                      topic="What is state in a React component?")
    section = _section()

    # Simulate _select_pipeline: rank_candidates sees BOTH candidates;
    # keep_most_important then cuts to target=1.
    scored_pool, _pool_notes = select.rank_candidates(TopicList(topics=[winner, runner_up]))
    assert len(scored_pool.topics) == 2, "both candidates must survive the pool"
    cut_to_one, _cut_notes = select.keep_most_important(
        TopicList(topics=[winner, runner_up]), target=1)
    assert len(cut_to_one.topics) == 1, "keep_most_important must still honor target=1"

    selections = select.build_question_selections(
        cut_to_one, [section], scored_pool=scored_pool)
    assert len(selections) == 1
    comparisons = [r for r in selections[0].reasons if r.category == "candidate_comparison"]
    assert len(comparisons) == 1, selections[0].reasons
    text = comparisons[0].explanation
    assert "what state is" in text
    assert "5/5" in text and "4/5" in text
    print(f"   ok — at target=1, the comparison still names the real runner-up "
          f"from the pre-cut pool instead of being a silent no-op: {text!r}")


def test_no_comparison_fabricated_when_scored_pool_has_no_runner_up():
    # A caller that legitimately only ever scored ONE candidate (the model
    # returned a single topic) — scored_pool has one entry, so there is no
    # runner-up to name, and nothing must be invented.
    section = _section()
    topic = _topic()
    scored_pool = TopicList(topics=[topic])
    [sel] = select.build_question_selections(TopicList(topics=[topic]), [section],
                                             scored_pool=scored_pool)
    assert not any(r.category == "candidate_comparison" for r in sel.reasons)
    print("   ok — no candidate_comparison reason is fabricated when the "
          "scored pool itself has no runner-up")


def test_comparison_omitted_when_selected_topic_is_not_the_pools_own_top():
    # A defensive case: if the caller ever hands build_question_selections a
    # `topics` list whose own #1 is NOT scored_pool's #1 (should not happen
    # in the real pipeline, but nothing should invent a comparison for it).
    section = _section()
    pool_winner = _topic(id="pool_winner", importance=5, concept="a",
                        topic="Why does A matter here?")
    other = _topic(id="other", importance=4, concept="b",
                  topic="Why does B matter here?")
    scored_pool = TopicList(topics=[pool_winner, other])
    # `topics` here only contains `other` — e.g. pool_winner was rejected by
    # a later step this test does not model.
    [sel] = select.build_question_selections(TopicList(topics=[other]), [section],
                                             scored_pool=scored_pool)
    assert not any(r.category == "candidate_comparison" for r in sel.reasons)
    print("   ok — no comparison is fabricated for a topic that is not "
          "actually the scored pool's own #1")


def test_requested_selected_count_is_unaffected_by_the_scored_pool_change():
    # target-count behavior must be untouched by any of this round's changes.
    topics5 = [_topic(id=f"t{i}", importance=5, concept=f"concept {i}",
                     topic=f"Why does concept {i} matter?") for i in range(5)]
    for target in (1, 2, 3):
        cut, _notes = select.keep_most_important(TopicList(topics=topics5), target=target)
        assert len(cut.topics) == target, (target, len(cut.topics))
    print("   ok — keep_most_important still returns exactly `target` topics, "
          "for target 1, 2 and 3 — unaffected by rank_candidates/scored_pool")


def test_rank_candidates_returns_every_survivor_not_just_the_top_one():
    good = _topic(id="good", importance=5, concept="a", topic="Why does A matter here?")
    also_good = _topic(id="also_good", importance=4, concept="b",
                      topic="Why does B matter here?")
    weak = _topic(id="weak", importance=2, concept="c", topic="Why does C matter here?")
    pool, notes = select.rank_candidates(TopicList(topics=[good, also_good, weak]))
    ids = [t.id for t in pool.topics]
    assert ids == ["good", "also_good"], ids
    assert any("weak" in n for n in notes)
    print("   ok — rank_candidates keeps every filter-surviving candidate "
          "(not cut to any target) and still reports what the importance "
          "floor dropped")


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
