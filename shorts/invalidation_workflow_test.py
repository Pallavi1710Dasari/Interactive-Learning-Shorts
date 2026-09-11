"""
Offline, deterministic tests for Step 7.1 AND Step 8.1: downstream workflow
invalidation.

Step 7.1 confirms: regenerating the QUESTION invalidates every decision
derived from it (framing, teaching_approach, teaching_approach_approval) —
see schema.QuestionWorkflow.invalidate_downstream, called from
review.regenerate — while regenerating the TEACHING APPROACH invalidates
nothing above its own stage.

Step 8.1 extends both paths to `script` (Step 8's artifact, added after 7.1's
original fix): question regeneration clears it via invalidate_downstream
(now itself extended); teaching-approach regeneration clears it via the new
QuestionWorkflow.invalidate_script, WITHOUT touching framing or
question_approval.

No API key, no network — every LLM call here goes through config.STUB exactly
like Steps 3-8.

    python -m shorts.invalidation_workflow_test
"""
from unittest.mock import patch

from . import config
from .schema import Section, Topic, TopicList, QuestionWorkflow
from .skills import select, framing as framing_mod, teaching_approach as ta_mod, script as script_mod
from . import review, workflow


def _section(section_id="3.1", title="Why Paging Exists") -> Section:
    text = ("Paging solves external fragmentation by dividing memory into equal "
            "fixed-size frames. Each process is divided into pages of the same "
            "size, and the operating system maintains a page table mapping pages "
            "to frames.")
    return Section(section_id=section_id, title=title, text=text, start_line=1,
                   end_line=5)


def _workflow_ready_for_next_stage(topic_id="t_paging") -> QuestionWorkflow:
    """An approved, framed workflow with an APPROVED teaching approach — the
    fullest state a workflow reaches before Step 7.1 is exercised, so every
    test here starts from something genuinely worth invalidating."""
    data = dict(
        id=topic_id, topic="Why does paging remove external fragmentation?",
        why_it_matters="central mechanism", source_section_id="3.1",
        difficulty="medium", importance=5, concept="paging and fragmentation",
        answer_quote="Paging solves external fragmentation by dividing memory "
                     "into equal fixed-size frames.",
    )
    topic = Topic(**data)
    [selection] = select.build_question_selections(TopicList(topics=[topic]), [_section()])
    wf = QuestionWorkflow(selection=selection)

    old_stub = config.STUB
    config.STUB = True
    try:
        wf = review.approve_question(wf)
        wf = workflow.advance(wf, [_section()]).workflow
        wf = review.approve_teaching_approach(wf)
    finally:
        config.STUB = old_stub
    assert wf.framing is not None
    assert wf.teaching_approach is not None
    assert wf.teaching_approach_approval.status == "approved"
    return wf


def _workflow_with_script(topic_id="t_paging") -> QuestionWorkflow:
    """Everything _workflow_ready_for_next_stage gives, PLUS a generated
    script — the fullest state a workflow reaches after Step 8, so Step
    8.1's tests start from something genuinely worth invalidating."""
    wf = _workflow_ready_for_next_stage(topic_id)
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = script_mod.write_script_for_workflow(wf, _section())
    finally:
        config.STUB = old_stub
    assert wf.script is not None
    return wf


# --------------------------------------------------------------------------- 1
def test_regenerating_question_after_framing_clears_framing():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf.framing is not None            # sanity: it really existed before
    assert wf2.framing is None
    print("   ok — regenerating the question after framing exists clears "
          "framing (requirement 1)")


# --------------------------------------------------------------------------- 2
def test_regenerating_question_after_teaching_approach_clears_it():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf.teaching_approach is not None
    assert wf2.teaching_approach is None
    print("   ok — regenerating the question after a teaching_approach exists "
          "clears it (requirement 2)")


# --------------------------------------------------------------------------- 3
def test_regenerating_question_clears_teaching_approach_approval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        assert wf.teaching_approach_approval.status == "approved"
        assert wf.teaching_approach_approval.regeneration_history == []  # sanity
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.teaching_approach_approval.status == "pending"
    assert wf2.teaching_approach_approval.override is None
    assert wf2.teaching_approach_approval.regenerated_approach is None
    assert wf2.teaching_approach_approval.regeneration_history == []
    print("   ok — regenerating the question resets teaching_approach_approval "
          "to a fresh, pending state — including its own history "
          "(requirement 3)")


def test_regenerating_question_clears_teaching_approach_approval_with_its_own_history():
    # A workflow whose teaching approach was ITSELF regenerated before the
    # question was — that history belongs to a now-invalid teaching_approach
    # and must not survive either.
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf = review.regenerate_teaching_approach(wf, "code is not necessary", [_section()])
        assert wf.teaching_approach_approval.regeneration_history != []
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.teaching_approach_approval.regeneration_history == []
    print("   ok — a teaching-approach regeneration history is also cleared "
          "when the question underneath it regenerates (requirement 3)")


# --------------------------------------------------------------------------- 4
def test_question_regeneration_history_preserved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert len(wf2.question_approval.regeneration_history) == 1
    assert wf2.question_approval.regeneration_history[0].reason == (
        "too broad, focus on the mechanism")
    assert wf2.question_approval.regeneration_history[0].previous_question == (
        wf.effective_question)
    print("   ok — the question's own regeneration_history survives "
          "invalidation, unaffected (requirement 4)")


# --------------------------------------------------------------------------- 5
def test_selection_and_reasons_unchanged():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.selection == wf.selection
    assert wf2.selection.reasons == wf.selection.reasons
    assert wf2.selection.topic.topic == wf.selection.topic.topic   # the ORIGINAL question
    print("   ok — selection (and its reasons, and the original question) "
          "are completely unchanged by invalidation (requirement 5)")


# --------------------------------------------------------------------------- 6
def test_regenerated_question_returns_to_pending():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.question_approval.status == "pending"
    assert wf2.approved_topic is None
    print("   ok — the regenerated question returns to pending, not approved "
          "(requirement 6)")


# --------------------------------------------------------------------------- 7
def test_orchestrator_makes_no_downstream_calls_before_reapproval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        with patch.object(framing_mod, "ask_json", side_effect=AssertionError(
                "must not frame before the regenerated question is approved")), \
            patch.object(ta_mod, "ask_json", side_effect=AssertionError(
                "must not choose a teaching approach before re-approval")):
            result = workflow.advance(wf2, [_section()])
    finally:
        config.STUB = old_stub
    assert result.status == "awaiting_question_approval"
    assert result.workflow.framing is None
    assert result.workflow.teaching_approach is None
    print("   ok — the orchestrator makes no framing or teaching-approach "
          "call for a regenerated-but-unapproved question (requirement 7)")


# --------------------------------------------------------------------------- 8
def test_orchestrator_generates_fresh_framing_after_reapproval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        wf3 = review.approve_question(wf2)
        result = workflow.advance(wf3, [_section()])
    finally:
        config.STUB = old_stub
    assert result.workflow.framing is not None
    print("   ok — after the regenerated question is approved, the "
          "orchestrator generates fresh framing (requirement 8)")


# --------------------------------------------------------------------------- 9
def test_orchestrator_generates_fresh_teaching_approach_after_reapproval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        wf3 = review.approve_question(wf2)
        result = workflow.advance(wf3, [_section()])
    finally:
        config.STUB = old_stub
    assert result.workflow.teaching_approach is not None
    assert result.status == "awaiting_teaching_approach_approval"
    print("   ok — after the regenerated question is approved, the "
          "orchestrator generates a fresh teaching approach too "
          "(requirement 9)")


# -------------------------------------------------------------------------- 10
def test_new_downstream_decisions_are_based_on_the_regenerated_question():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        old_effective = wf.effective_question
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        wf3 = review.approve_question(wf2)
        result = workflow.advance(wf3, [_section()])
    finally:
        config.STUB = old_stub
    new_effective = wf3.effective_question
    assert new_effective != old_effective
    assert result.workflow.framing.source_question == new_effective
    assert result.workflow.framing.source_question != old_effective
    print("   ok — the fresh framing is built from the REGENERATED question, "
          "not the old one (requirement 10)")


# -------------------------------------------------------------------------- 11
def test_teaching_approach_regeneration_does_not_clear_question_approval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        original_question_approval = wf.question_approval
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.question_approval == original_question_approval
    assert wf2.approved_topic is not None
    print("   ok — regenerating the teaching approach leaves question_approval "
          "(and approved_topic) completely untouched (requirement 11)")


# -------------------------------------------------------------------------- 12
def test_teaching_approach_regeneration_does_not_clear_framing():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        original_framing = wf.framing
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.framing == original_framing
    print("   ok — regenerating the teaching approach leaves framing "
          "completely untouched (requirement 12)")


# -------------------------------------------------------------------------- 13
def test_teaching_approach_regeneration_resets_only_its_own_approval():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        original_teaching_approach = wf.teaching_approach   # the LLM's ORIGINAL decision
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    # Only the APPROVAL state resets; the original decision field itself is
    # untouched — the new one lives in regenerated_approach, same contract
    # Step 6 already established.
    assert wf2.teaching_approach == original_teaching_approach
    assert wf2.teaching_approach_approval.status == "pending"
    assert wf2.teaching_approach_approval.regenerated_approach is not None
    assert len(wf2.teaching_approach_approval.regeneration_history) == 1
    print("   ok — regenerating the teaching approach resets only "
          "teaching_approach_approval's own state, and preserves its "
          "regeneration history (requirement 13)")


# -------------------------------------------------------------------------- 14
def test_repeated_orchestration_after_invalidation_is_idempotent():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        wf3 = review.approve_question(wf2)
        first = workflow.advance(wf3, [_section()]).workflow

        with patch.object(framing_mod, "ask_json", side_effect=AssertionError(
                "framing must not be regenerated on a second advance() call")), \
            patch.object(ta_mod, "ask_json", side_effect=AssertionError(
                "teaching approach must not be regenerated on a second "
                "advance() call")):
            again = workflow.advance(first, [_section()])
    finally:
        config.STUB = old_stub
    assert again.status == "awaiting_teaching_approach_approval"
    assert again.workflow.framing == first.framing
    assert again.workflow.teaching_approach == first.teaching_approach
    print("   ok — advancing again after invalidation and regeneration is "
          "idempotent — no further calls, same result (requirement 14)")


# =========================================================================
# STEP 8.1 — script invalidation after upstream changes.

# --------------------------------------------------------------------------- 1
def test_question_regeneration_clears_an_existing_script():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf.script is not None            # sanity: it really existed before
    assert wf2.script is None
    print("   ok — regenerating the question clears an existing script "
          "(requirement 1)")


# --------------------------------------------------------------------------- 2
def test_question_regeneration_preserves_question_regeneration_history():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert len(wf2.question_approval.regeneration_history) == 1
    assert wf2.question_approval.regeneration_history[0].reason == (
        "too broad, focus on the mechanism")
    print("   ok — question regeneration history is preserved alongside "
          "script invalidation (requirement 2)")


# --------------------------------------------------------------------------- 3
def test_question_regeneration_preserves_selection():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.selection == wf.selection
    assert wf2.selection.topic.topic == wf.selection.topic.topic   # original question
    print("   ok — selection (the original topic and its reasons) is "
          "preserved alongside script invalidation (requirement 3)")


# --------------------------------------------------------------------------- 4
def test_teaching_approach_regeneration_clears_an_existing_script():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    assert wf.script is not None
    assert wf2.script is None
    print("   ok — regenerating the teaching approach clears an existing "
          "script (requirement 4)")


# --------------------------------------------------------------------------- 5
def test_teaching_approach_regeneration_does_not_clear_framing_with_script():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        original_framing = wf.framing
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.framing == original_framing
    print("   ok — teaching-approach regeneration clears script but leaves "
          "framing untouched (requirement 5)")


# --------------------------------------------------------------------------- 6
def test_teaching_approach_regeneration_does_not_clear_question_approval_with_script():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        original_question_approval = wf.question_approval
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.question_approval == original_question_approval
    assert wf2.approved_topic is not None
    print("   ok — teaching-approach regeneration clears script but leaves "
          "question_approval untouched (requirement 6)")


# --------------------------------------------------------------------------- 7
def test_no_script_before_regenerated_question_is_reapproved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        assert wf2.question_approval.status == "pending"
        with patch.object(script_mod, "ask_json", side_effect=AssertionError(
                "must not write a script before the regenerated question is "
                "approved")):
            try:
                script_mod.write_script_for_workflow(wf2, _section())
                raise AssertionError("should have refused")
            except ValueError:
                pass
    finally:
        config.STUB = old_stub
    print("   ok — no new script can be generated before a regenerated "
          "question is re-approved (requirement 7)")


# --------------------------------------------------------------------------- 8
def test_no_workflow_aware_script_before_regenerated_approach_is_reapproved():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
        assert wf2.teaching_approach_approval.status == "pending"
        with patch.object(script_mod, "ask_json", side_effect=AssertionError(
                "must not write a script before the regenerated approach is "
                "approved")):
            try:
                script_mod.write_script_for_workflow(wf2, _section())
                raise AssertionError("should have refused")
            except ValueError:
                pass
    finally:
        config.STUB = old_stub
    print("   ok — no new workflow-aware script can be generated before a "
          "regenerated teaching approach is re-approved (requirement 8)")


# --------------------------------------------------------------------------- 9
def test_fresh_script_after_full_reapproval_cycle():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        original_script = wf.script

        # Regenerate the question, re-approve, let the orchestrator rebuild
        # framing/teaching_approach, approve the (fresh) teaching approach,
        # and confirm a genuinely NEW script can be written.
        wf = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
        wf = review.approve_question(wf)
        wf = workflow.advance(wf, [_section()]).workflow
        wf = review.approve_teaching_approach(wf)
        assert wf.script is None   # still cleared — nothing writes it automatically
        wf = script_mod.write_script_for_workflow(wf, _section())
    finally:
        config.STUB = old_stub
    assert wf.script is not None
    assert wf.script.question == wf.framing.teaching_question
    assert wf.framing.teaching_question != original_script.question
    print("   ok — after a full re-approval cycle, a fresh script can be "
          "generated, built from the regenerated question (requirement 9)")


# -------------------------------------------------------------------------- 10
def test_existing_invalidation_behavior_unchanged_when_no_script_exists():
    # The exact Step 7.1 scenario, unmodified: a workflow with NO script yet
    # regenerates its question, and framing/teaching_approach/
    # teaching_approach_approval invalidate exactly as they always did.
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_ready_for_next_stage()   # no script generated
        assert wf.script is None
        wf2 = review.regenerate(wf, "too broad, focus on the mechanism", [_section()])
    finally:
        config.STUB = old_stub
    assert wf2.framing is None
    assert wf2.teaching_approach is None
    assert wf2.teaching_approach_approval.status == "pending"
    assert wf2.teaching_approach_approval.regeneration_history == []
    assert wf2.script is None   # already None; still None, not an error
    print("   ok — Step 7.1's original invalidation behavior is unchanged "
          "when there was no script to begin with (requirement 10)")


# -------------------------------------------------------------------------- 11
def test_existing_topic_based_write_script_behavior_unchanged():
    # write_script (no workflow, no framing, no approach) is not part of the
    # invalidation machinery at all — confirm it is untouched by Step 8.1.
    from .skills.script import write_script
    section = _section()
    topic = Topic(id="t1", topic="Why does paging remove external fragmentation?",
                 why_it_matters="m", source_section_id="3.1", difficulty="medium")
    old_stub = config.STUB
    config.STUB = True
    try:
        sc = write_script(topic, section)
    finally:
        config.STUB = old_stub
    assert sc.question == topic.topic
    print("   ok — plain Topic-based write_script is unaffected by Step 8.1 "
          "(requirement 11)")


# -------------------------------------------------------------------------- 12
def test_repeated_generation_does_not_reuse_a_stale_script():
    old_stub = config.STUB
    config.STUB = True
    try:
        wf = _workflow_with_script()
        stale_script = wf.script

        wf2 = review.regenerate_teaching_approach(wf, "code is not necessary",
                                                   [_section()])
        wf2 = review.approve_teaching_approach(wf2)
        assert wf2.script is None
        rebuilt = script_mod.write_script_for_workflow(wf2, _section())
    finally:
        config.STUB = old_stub
    # A fresh script was genuinely written, not the old object reused as-is
    # for a workflow whose approved approach has since changed identity.
    assert rebuilt.script is not None
    assert rebuilt.teaching_approach_approval.status == "approved"
    assert rebuilt.teaching_approach_approval.regenerated_approach is not None
    print("   ok — regenerating downstream stages and re-approving always "
          "produces a freshly written script, never a stale reused one "
          "(requirement 12)")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} invalidation (Step 7.1) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL INVALIDATION WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
