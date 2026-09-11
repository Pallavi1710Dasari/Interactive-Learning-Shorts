"""
Offline, deterministic tests for the human-in-the-loop planning workflow's
data contracts (schema.py: SelectionReason, QuestionSelection,
QuestionApproval, QuestionFraming, TeachingApproach, TeachingApproachApproval,
VisualPlanApproval, QuestionWorkflow).

No API key, no network. These check that the new models serialize, default,
and reuse the existing schema (Topic, VisualStrategy) the way the models'
docstrings claim — not that any future pipeline step behaves correctly, since
none consumes these yet.

    python -m shorts.workflow_schema_test
"""
import json
from pydantic import ValidationError

from .schema import (
    Topic, Script, Beat, BeatStrategy, VisualStrategy,
    SelectionReason, QuestionSelection, QuestionApproval, QuestionFraming,
    TeachingApproach, TeachingApproachApproval, VisualPlanApproval,
    QuestionWorkflow,
)


def _topic(**overrides) -> Topic:
    data = dict(id="t1", topic="Why does X happen?", why_it_matters="it matters",
                source_section_id="3.2", difficulty="medium", importance=4,
                concept="X")
    data.update(overrides)
    return Topic(**data)


def test_question_selection_reuses_topic_signals():
    topic = _topic()
    qs = QuestionSelection(
        topic=topic,
        source_title="Section 3.2: Paging",
        reasons=[
            SelectionReason(category="importance", explanation="scores 4/5"),
            SelectionReason(category="foundational", explanation="later sections assume this"),
        ],
    )
    # Round-trips through JSON exactly, and nothing here re-derives what Topic
    # already carries — importance and why_it_matters come along on .topic.
    restored = QuestionSelection(**json.loads(qs.model_dump_json()))
    assert restored.topic.importance == 4
    assert restored.topic.why_it_matters == "it matters"
    assert restored.source_title == "Section 3.2: Paging"
    assert [r.category for r in restored.reasons] == ["importance", "foundational"]
    print("   ok — QuestionSelection wraps Topic and round-trips")


def test_question_selection_reasons_default_empty():
    qs = QuestionSelection(topic=_topic(), source_title="Section 3.2")
    assert qs.reasons == []
    print("   ok — QuestionSelection.reasons defaults to []")


def test_question_approval_defaults_and_states():
    qa = QuestionApproval()
    assert qa.status == "pending"
    assert qa.note is None
    assert qa.edited_question is None

    qa2 = QuestionApproval(status="approved", note="good one",
                            edited_question="Why does X happen when Y?")
    restored = QuestionApproval(**json.loads(qa2.model_dump_json()))
    assert restored.status == "approved"
    assert restored.edited_question == "Why does X happen when Y?"

    try:
        QuestionApproval(status="modified")  # not a valid state for this gate
        raise AssertionError("QuestionApproval should reject 'modified'")
    except ValidationError:
        pass
    print("   ok — QuestionApproval defaults to pending, rejects foreign states")


def test_question_framing_role_default_and_round_trip():
    qf = QuestionFraming(source_question="Why does X happen?",
                          teaching_question="What causes X?")
    assert qf.role == "primary"
    qf2 = QuestionFraming(source_question="Why does X happen?",
                           teaching_question="What causes X?",
                           framing_rationale="sharper and concrete",
                           role="hook")
    restored = QuestionFraming(**json.loads(qf2.model_dump_json()))
    assert restored.role == "hook"
    assert restored.framing_rationale == "sharper and concrete"
    print("   ok — QuestionFraming defaults role to primary, carries rationale")


def test_teaching_approach_requires_primary_no_hidden_default():
    try:
        TeachingApproach()
        raise AssertionError("TeachingApproach should require `primary`")
    except ValidationError:
        pass

    ta = TeachingApproach(primary="analogy")
    assert ta.combined_with == []
    assert ta.alternatives == []
    assert ta.rationale == ""

    ta2 = TeachingApproach(primary="code", combined_with=["real_world_example"],
                            alternatives=["comparison", "direct_explanation"],
                            rationale="the section IS a code snippet")
    restored = TeachingApproach(**json.loads(ta2.model_dump_json()))
    assert restored.primary == "code"
    assert restored.combined_with == ["real_world_example"]
    assert restored.alternatives == ["comparison", "direct_explanation"]
    print("   ok — TeachingApproach requires primary, defaults combined/alternatives empty")


def test_teaching_approach_approval_override_reuses_teaching_approach():
    approval = TeachingApproachApproval()
    assert approval.status == "pending"
    assert approval.override is None

    approval2 = TeachingApproachApproval(
        status="modified",
        override=TeachingApproach(primary="conceptual_visual", rationale="clearer as a picture"),
        note="swapped from code to a diagram",
    )
    restored = TeachingApproachApproval(**json.loads(approval2.model_dump_json()))
    assert restored.status == "modified"
    assert restored.override.primary == "conceptual_visual"
    assert restored.note == "swapped from code to a diagram"
    print("   ok — TeachingApproachApproval.override is a real TeachingApproach")


def test_visual_plan_approval_override_reuses_visual_strategy():
    approval = VisualPlanApproval()
    assert approval.status == "pending"
    assert approval.override is None

    strategy = VisualStrategy(
        subject="a stack",
        beats=[BeatStrategy(ref="b1", concept="pushing an item", relationship="process",
                             must_see="a slot arriving at the top", focus="the new slot")],
    )
    approval2 = VisualPlanApproval(status="modified", override=strategy,
                                    note="was a bar, should be a state container")
    restored = VisualPlanApproval(**json.loads(approval2.model_dump_json()))
    assert restored.status == "modified"
    assert restored.override.subject == "a stack"
    assert restored.override.beats[0].relationship == "process"
    print("   ok — VisualPlanApproval.override is a real VisualStrategy")


def test_question_workflow_minimal_construction_defaults_every_later_stage():
    topic = _topic()
    selection = QuestionSelection(topic=topic, source_title="Section 3.2")
    wf = QuestionWorkflow(selection=selection)

    # Only `selection` is required; everything after it in the pipeline is
    # either a fresh default-status approval or None ("not decided yet").
    assert wf.question_approval.status == "pending"
    assert wf.teaching_approach_approval.status == "pending"
    assert wf.visual_plan_approval.status == "pending"
    assert wf.framing is None
    assert wf.teaching_approach is None
    assert wf.script is None
    assert wf.visual_strategy is None
    print("   ok — QuestionWorkflow needs only `selection`; later stages default/None")


def test_question_workflow_full_round_trip():
    topic = _topic()
    script = Script(short_id="s1", question="What causes X?",
                     beats=[Beat(speaker="interviewer", line="What causes X?",
                                 on_screen="X?", visual_ref="b1")])
    strategy = VisualStrategy(
        subject="X",
        beats=[BeatStrategy(ref="b1", concept="X", relationship="cause_effect",
                             must_see="the cause and the effect", focus="the arrow")],
    )
    wf = QuestionWorkflow(
        selection=QuestionSelection(
            topic=topic, source_title="Section 3.2",
            reasons=[SelectionReason(category="foundational", explanation="x")],
        ),
        question_approval=QuestionApproval(status="approved"),
        framing=QuestionFraming(source_question="Why does X happen?",
                                 teaching_question="What causes X?"),
        teaching_approach=TeachingApproach(primary="direct_explanation"),
        teaching_approach_approval=TeachingApproachApproval(status="approved"),
        script=script,
        visual_strategy=strategy,
        visual_plan_approval=VisualPlanApproval(status="approved"),
    )

    restored = QuestionWorkflow(**json.loads(wf.model_dump_json()))
    assert restored.selection.topic.id == "t1"
    assert restored.question_approval.status == "approved"
    assert restored.framing.teaching_question == "What causes X?"
    assert restored.teaching_approach.primary == "direct_explanation"
    assert restored.script.question == "What causes X?"
    assert restored.visual_strategy.subject == "X"
    assert restored.visual_plan_approval.status == "approved"
    print("   ok — QuestionWorkflow round-trips every stage through JSON")


# --------------------------------------------------------------------------
# Step 3.1: QuestionWorkflow.effective_question / .approved_topic priority.
#
# regenerated_question > edited_question (legacy compatibility only) > the
# original selected Topic.topic. Step 3's own CLI and API never write
# edited_question — these tests fix that priority in place, including the
# legacy-data case where an older workflow somehow carries BOTH fields.

def _selection(topic_question="Why does X happen?") -> QuestionSelection:
    return QuestionSelection(
        topic=_topic(topic=topic_question),
        source_title="Section 3.2",
        reasons=[SelectionReason(category="importance", explanation="x")],
    )


def test_effective_question_uses_regenerated_question_only():
    wf = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(regenerated_question="What causes X?"),
    )
    assert wf.effective_question == "What causes X?"
    # The original selected question is untouched underneath the regeneration.
    assert wf.selection.topic.topic == "Why does X happen?"
    print("   ok — regenerated_question alone drives effective_question (case 1)")


def test_effective_question_uses_edited_question_for_legacy_compatibility_only():
    wf = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(edited_question="Why does X happen when Y?"),
    )
    assert wf.effective_question == "Why does X happen when Y?"
    assert wf.selection.topic.topic == "Why does X happen?"
    print("   ok — edited_question alone still resolves, for legacy data only (case 2)")


def test_effective_question_prefers_regenerated_over_edited_when_both_present():
    # THE LEGACY-COMPATIBILITY CASE THIS STEP EXISTS TO PIN DOWN: a workflow
    # that somehow carries both fields (old edited_question data, plus a
    # regeneration recorded later) must resolve to the regeneration — never a
    # silent fallback to the legacy field, and never an error.
    wf = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(
            edited_question="a stale, pre-regeneration edit",
            regenerated_question="a fresh, grounded regeneration",
        ),
    )
    assert wf.effective_question == "a fresh, grounded regeneration"
    print("   ok — regenerated_question wins over edited_question when both are "
          "set (case 3)")


def test_effective_question_falls_back_to_original_when_neither_present():
    wf = QuestionWorkflow(selection=_selection())
    assert wf.question_approval.regenerated_question is None
    assert wf.question_approval.edited_question is None
    assert wf.effective_question == "Why does X happen?"
    print("   ok — neither field set falls back to the original selected "
          "question (case 4)")


def test_approved_topic_uses_the_same_effective_question_priority():
    # Same three scenarios as above, but through approved_topic — the actual
    # gate downstream stages read. status must be "approved" for any of these
    # to return non-None at all (see the pending/rejected test below).
    only_regenerated = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(status="approved",
                                           regenerated_question="What causes X?"),
    )
    assert only_regenerated.approved_topic.topic == "What causes X?"

    only_edited = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(status="approved",
                                           edited_question="Why does X happen when Y?"),
    )
    assert only_edited.approved_topic.topic == "Why does X happen when Y?"

    both = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(
            status="approved",
            edited_question="a stale, pre-regeneration edit",
            regenerated_question="a fresh, grounded regeneration",
        ),
    )
    assert both.approved_topic.topic == "a fresh, grounded regeneration"

    neither = QuestionWorkflow(
        selection=_selection(),
        question_approval=QuestionApproval(status="approved"),
    )
    assert neither.approved_topic.topic == "Why does X happen?"

    # And in every case, the ORIGINAL Topic underneath selection is untouched —
    # approved_topic is always a COPY with only `.topic` substituted.
    for wf in (only_regenerated, only_edited, both, neither):
        assert wf.selection.topic.topic == "Why does X happen?"
        assert wf.approved_topic is not wf.selection.topic
    print("   ok — approved_topic resolves through the exact same "
          "regenerated > edited > original priority as effective_question "
          "(case 5)")


def test_approved_topic_none_for_pending_and_rejected_regardless_of_fields():
    # A workflow carrying a regenerated_question (or an edited_question) is
    # NOT thereby approved — approved_topic must stay None until status is
    # explicitly "approved", whatever text is sitting in either field.
    for status in ("pending", "rejected", "regenerating"):
        wf = QuestionWorkflow(
            selection=_selection(),
            question_approval=QuestionApproval(
                status=status,
                edited_question="a stale, pre-regeneration edit",
                regenerated_question="a fresh, grounded regeneration",
            ),
        )
        assert wf.approved_topic is None, (
            f"status={status!r} must never produce an approved_topic")
    print("   ok — pending/rejected/regenerating never produce an approved_topic, "
          "even with both question fields populated (case 6)")


def test_new_models_do_not_disturb_backward_compatibility():
    # A ShortUnit dict shaped like the ones already on disk (no knowledge of
    # anything added in this change) must still load unchanged.
    from .schema import ShortUnit, Visual
    old_style = dict(
        short_id="s1", session_id="sess", source_section_id="3.2",
        question="What causes X?", estimated_seconds=30.0,
        beats=[Beat(speaker="interviewer", line="What causes X?",
                    on_screen="X?", visual_ref="b1").model_dump()],
        visuals={"b1": Visual(ref="b1", type="text", spec="placeholder").model_dump()},
    )
    unit = ShortUnit(**old_style)
    assert unit.status == "draft"
    assert unit.understanding is None
    print("   ok — pre-existing ShortUnit shape still loads unchanged")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} workflow-schema tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL WORKFLOW SCHEMA TESTS PASSED.")


if __name__ == "__main__":
    main()
