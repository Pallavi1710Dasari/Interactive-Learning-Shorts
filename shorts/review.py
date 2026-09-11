"""
The human gate. A terminal reviewer — deliberately boring, deliberately fast.

    python -m shorts.review

Shows one short at a time as text. You never watch a video to approve it.
Sets status to approved or rejected in the unit JSON.

ALSO: Step 3's EARLIER, cheaper gate — on a candidate QUESTION, before a script
is ever written for it. See run_question_gate() below. Same module because it
is the same job (a human deciding whether something may proceed) one stage
earlier, not a second review framework — see approve_question / reject_question
/ regenerate, all reused as-is by run.py's CLI and server.py's API.
"""
import json, sys
from pathlib import Path
from .schema import (ShortUnit, QuestionWorkflow, RegenerationAttempt,
                     TeachingApproachRegenerationAttempt,
                     VisualStrategyRegenerationAttempt, Section)
from .parse import find_section
from .skills.select import regenerate_question
from .skills.teaching_approach import reconsider_teaching_approach
from .skills.strategy import reconsider_visual_strategy, as_brief
from . import config


#          output/ also holds sidecars that are not units. A stray file here used to
#          blow up on ShortUnit(**...) with a wall of pydantic errors.
SIDECARS = {"manifest.json", "topics.json", "smoke_unit.json"}


# --------------------------------------------------------- Step 3: question gate
#
# ONE STATE MACHINE, REUSED BY EVERY CALLER. run.py's --gate-topics loop below
# and server.py's /api/selections/* endpoints both call approve_question,
# reject_question and regenerate — never their own copy of "set status to X" —
# so a rule enforced here (a reason is required, the regeneration limit, landing
# back on pending) holds everywhere this workflow is decided, not just in
# whichever caller happened to implement it first.

def _require_reason(reason: str | None) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a regeneration reason is required — say what should "
                         "improve before requesting another attempt")
    return reason


def approve_question(workflow: QuestionWorkflow, note: str | None = None) -> QuestionWorkflow:
    """
    Approve `workflow` exactly as it currently stands.

    Never touches question text — only the gate. Whatever
    workflow.effective_question already resolves to (the original selection,
    or the latest regeneration) is what QuestionWorkflow.approved_topic hands
    downstream once this has run.
    """
    approval = workflow.question_approval.model_copy(update={
        "status": "approved",
        "note": note if note is not None else workflow.question_approval.note,
    })
    return workflow.model_copy(update={"question_approval": approval})


def reject_question(workflow: QuestionWorkflow, note: str | None = None) -> QuestionWorkflow:
    """Reject `workflow`. approved_topic returns None from here on — see
    schema.QuestionWorkflow.approved_topic — regardless of how many
    regenerations came before this."""
    approval = workflow.question_approval.model_copy(update={
        "status": "rejected",
        "note": note if note is not None else workflow.question_approval.note,
    })
    return workflow.model_copy(update={"question_approval": approval})


def regenerate(workflow: QuestionWorkflow, reason: str,
               sections: list[Section]) -> QuestionWorkflow:
    """
    The full Step 3 regeneration action: validate the reason, enforce the loop
    limit, call the LLM once, and land back on `pending` — NEVER `approved`.

    A human must call approve_question again after this, however many times it
    runs — see schema.QuestionApproval's "NO DIRECT EDITING" and
    QuestionWorkflow.approved_topic's own note that a freshly regenerated
    question is exactly as blocked as the one it replaced.

    STEP 7.1: ALSO INVALIDATES EVERY DOWNSTREAM DECISION, UNCONDITIONALLY —
    framing, teaching_approach and teaching_approach_approval are all reset
    via QuestionWorkflow.invalidate_downstream (see there for the full
    reasoning). Unconditional, not "only if the text actually changed":
    regenerate_question is asked, every time, to produce a DIFFERENT
    question addressing the reviewer's reason, so a regeneration that came
    back byte-identical would be the prompt failing its own instructions, not
    a case worth special-casing here — and treating "did the text change"
    as the trigger would mean comparing strings to decide whether a
    correctness rule applies, which is exactly the kind of caller-remembered
    bookkeeping this fix exists to remove. The question's OWN
    regeneration_history (right below) is unaffected; only decisions made
    FOR the question are cleared.

    Raises ValueError on a blank reason or a limit already reached — both are
    caller mistakes the state machine refuses rather than silently working
    around (an empty reason recorded in history would be indistinguishable
    from one that was lost; a limit that could be talked past would not be a
    limit). Whatever the LLM call itself raises (a provider error, a timeout)
    is left to propagate — this function does not decide how a caller should
    handle that, run_question_gate below and server.py each do.
    """
    reason = _require_reason(reason)
    approval = workflow.question_approval
    if approval.regeneration_attempts >= config.MAX_QUESTION_REGENERATIONS:
        raise ValueError(
            f"regeneration limit reached ({config.MAX_QUESTION_REGENERATIONS} "
            f"attempt(s)) for {workflow.selection.topic.id} — approve or reject "
            f"what you have")

    previous_question = workflow.effective_question
    section = find_section(sections, workflow.selection.topic.source_section_id)
    new_question = regenerate_question(workflow.selection, section, reason,
                                       previous_question)

    attempt = RegenerationAttempt(reason=reason, previous_question=previous_question,
                                  regenerated_question=new_question)
    approval = approval.model_copy(update={
        "status": "pending",
        "regenerated_question": new_question,
        "regeneration_history": approval.regeneration_history + [attempt],
    })
    return workflow.model_copy(
        update={"question_approval": approval}).invalidate_downstream()


def run_question_gate(workflows: list[QuestionWorkflow], sections: list[Section],
                      interactive: bool | None = None) -> list[QuestionWorkflow]:
    """
    Step 3's human gate: approve, reject, or request an LLM regeneration of
    each candidate QUESTION — the earlier, cheaper counterpart to main()'s gate
    on a finished ShortUnit below. No editing prompt exists here on purpose;
    see schema.QuestionApproval's "NO DIRECT EDITING".

    interactive=None (the default) checks sys.stdin.isatty(): a real terminal
    gets the loop below; anything else (a pipe, a cron job, a test harness)
    gets NONE of it, and every workflow comes back exactly as it went in —
    PENDING, never silently approved or rejected. See run.py's --gate-topics,
    which writes these to disk either way so a non-interactive run can still be
    decided by a later interactive pass, or by editing the written file's
    question_approval fields directly (not the question text — see above).
    """
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print(f"  {len(workflows)} candidate question(s) awaiting approval — not "
              f"an interactive terminal, so none are decided here.")
        return workflows

    decided = list(workflows)
    for i, wf in enumerate(workflows):
        while True:
            sel = wf.selection
            print("\n" + "=" * 78)
            print(f"[{sel.topic.source_section_id}] {sel.source_title}")
            print(f"Q: {wf.effective_question}")
            if wf.effective_question != sel.topic.topic:
                print(f"   (originally: {sel.topic.topic})")
            for r in sel.reasons:
                print(f"  - ({r.category}) {r.explanation}")
            if wf.question_approval.regeneration_history:
                print(f"  {wf.question_approval.regeneration_attempts} "
                      f"regeneration(s) so far "
                      f"(limit {config.MAX_QUESTION_REGENERATIONS})")

            choice = input("[a]pprove  [r]eject  [g]enerate again  [s]kip "
                           "(leave pending)  [q]uit > ").strip().lower()
            if choice == "q":
                decided[i] = wf
                return decided
            if choice == "a":
                wf = approve_question(wf)
                break
            if choice == "r":
                note = input("why (optional): ").strip()
                wf = reject_question(wf, note=note or None)
                break
            if choice == "g":
                reason = input("what should improve? (required) > ").strip()
                if not reason:
                    print("  ! a reason is required — nothing sent")
                    continue
                try:
                    wf = regenerate(wf, reason, sections)
                except ValueError as e:
                    print(f"  ! {e}")
                    continue
                except Exception as e:
                    print(f"  ! regeneration failed ({type(e).__name__}: {e})")
                    continue
                print(f"  regenerated -> {wf.effective_question}")
                continue           # still needs an explicit approve/reject
            if choice == "s":
                break              # leave as pending
            print("  ? choose a, r, g, s or q")
        decided[i] = wf
    return decided


# ------------------------------------------------- Step 6: teaching approach gate
#
# THE SAME SHAPE AS STEP 3, ONE STAGE LATER, AND DELIBERATELY KEPT SEPARATE. A
# reviewer unhappy with the TEACHING DEVICE ("code is not necessary for this
# concept") is not the same complaint as one unhappy with the QUESTION's own
# wording, so this has its own reason requirement, its own regeneration
# history, its own limit (config.MAX_TEACHING_APPROACH_REGENERATIONS, not
# MAX_QUESTION_REGENERATIONS) and its own gate — never folded into
# approve_question/regenerate above. See schema.TeachingApproachRegenerationAttempt.
#
# ONLY TWO HUMAN ACTIONS EXIST HERE: approve, or request regeneration. There is
# no reject — an approach a reviewer dislikes is not a reason to drop the
# QUESTION, only to ask for a different DEVICE, so the only paths out of
# "pending" are "approved" or "another regeneration".

def _require_teaching_approach_reviewable(workflow: QuestionWorkflow) -> None:
    """
    The precondition every function below shares: an approved question, with
    framing, with a teaching_approach already chosen. Checked BEFORE anything
    else — including before validating a regeneration reason — so a workflow
    that fails an earlier stage is refused for THAT reason, not a confusing
    one about the request it never got to.
    """
    if workflow.approved_topic is None:
        raise ValueError(
            f"cannot review teaching approach for {workflow.selection.topic.id}: "
            f"question_approval.status={workflow.question_approval.status!r}, "
            f"not 'approved'")
    if workflow.framing is None:
        raise ValueError(
            f"cannot review teaching approach for {workflow.selection.topic.id}: "
            f"this workflow has no framing")
    if workflow.teaching_approach is None:
        raise ValueError(
            f"cannot review teaching approach for {workflow.selection.topic.id}: "
            f"no teaching_approach has been chosen yet")


def approve_teaching_approach(workflow: QuestionWorkflow,
                              note: str | None = None) -> QuestionWorkflow:
    """
    Approve `workflow`'s teaching approach exactly as it currently stands —
    whatever effective_teaching_approach already resolves to (the LLM's
    original decision, or the latest regeneration) is what
    QuestionWorkflow.approved_teaching_approach hands downstream once this
    has run. Never touches the approach itself, only the gate.
    """
    _require_teaching_approach_reviewable(workflow)
    approval = workflow.teaching_approach_approval.model_copy(update={
        "status": "approved",
        "note": note if note is not None else workflow.teaching_approach_approval.note,
    })
    return workflow.model_copy(update={"teaching_approach_approval": approval})


def regenerate_teaching_approach(workflow: QuestionWorkflow, reason: str,
                                 sections: list[Section],
                                 understanding=None) -> QuestionWorkflow:
    """
    The full Step 6 regeneration action: validate the reason, enforce the loop
    limit, call the LLM once for a COMPLETE new decision, and land back on
    `pending` — NEVER `approved`.

    A human must call approve_teaching_approach again after this, however
    many times it runs — same contract as review.regenerate for questions,
    and see QuestionWorkflow.approved_teaching_approach's own note that a
    freshly regenerated approach is exactly as blocked as the one it replaced.

    DOES NOT TOUCH question_approval OR framing, UNLIKE review.regenerate's
    OWN invalidation of downstream stages (see there — Step 7.1). Those two
    are UPSTREAM of the teaching approach, not downstream of it: nothing
    about reconsidering the teaching DEVICE changes what question is being
    asked or how it is worded, so there is nothing above this stage for a
    teaching-approach regeneration to invalidate. teaching_approach_approval
    itself is replaced here — see the model_copy at the bottom of this
    function — and its own regeneration_history is exactly what grows, never
    reset, by this call.

    STEP 8.1: DOES CLEAR workflow.script, THOUGH. A script (Step 8) was
    written FOR the previous approved teaching approach — see
    skills.script.write_script_for_workflow, which reads
    approved_teaching_approach directly — so once the approach is being
    reconsidered, that script no longer describes an approved decision and
    must not survive to be read as current. See
    QuestionWorkflow.invalidate_script, called at the very end of this
    function, for the shared primitive both this and review.regenerate's own
    (broader) invalidate_downstream call use.

    `understanding`, WHEN SUPPLIED, is passed straight through to
    skills.teaching_approach.reconsider_teaching_approach — never fetched
    here, for the same reason skills/teaching_approach.py never fetches one
    itself: doing so would silently add a second, uncached call on top of
    this step's own one call.

    Raises ValueError on a blank reason, a limit already reached, or any of
    _require_teaching_approach_reviewable's preconditions failing — all
    caller mistakes the state machine refuses rather than works around.
    """
    _require_teaching_approach_reviewable(workflow)
    reason = _require_reason(reason)
    approval = workflow.teaching_approach_approval
    if approval.regeneration_attempts >= config.MAX_TEACHING_APPROACH_REGENERATIONS:
        raise ValueError(
            f"teaching-approach regeneration limit reached "
            f"({config.MAX_TEACHING_APPROACH_REGENERATIONS} attempt(s)) for "
            f"{workflow.selection.topic.id} — approve what you have")

    previous_approach = workflow.effective_teaching_approach
    section = find_section(sections, workflow.selection.topic.source_section_id)
    new_approach = reconsider_teaching_approach(workflow, section, reason,
                                                previous_approach,
                                                understanding=understanding)

    attempt = TeachingApproachRegenerationAttempt(
        reason=reason, previous_approach=previous_approach,
        regenerated_approach=new_approach)
    approval = approval.model_copy(update={
        "status": "pending",
        "regenerated_approach": new_approach,
        "regeneration_history": approval.regeneration_history + [attempt],
    })
    return workflow.model_copy(
        update={"teaching_approach_approval": approval}).invalidate_script()


def _describe_approach(approach) -> str:
    """One readable line for the CLI gate below — primary, plus combined_with
    when present, exactly what a reviewer needs to see at a glance."""
    line = approach.primary
    if approach.combined_with:
        line += f" (combined with {', '.join(approach.combined_with)})"
    return line


def run_teaching_approach_gate(workflows: list[QuestionWorkflow], sections: list[Section],
                               interactive: bool | None = None) -> list[QuestionWorkflow]:
    """
    Step 6's human gate: approve, or request an LLM regeneration of, each
    workflow's teaching approach. No editing prompt exists here on purpose —
    see schema.TeachingApproachApproval's "NO DIRECT OVERRIDES".

    ONLY WORKFLOWS THAT PASS _require_teaching_approach_reviewable ARE SHOWN.
    A workflow still pending question approval, or approved but not yet
    framed, or framed but with no teaching_approach chosen, is filtered out
    silently here rather than shown with nothing to review — this gate is for
    reviewing a DECISION that exists, not for surfacing that one is missing.

    interactive=None (the default) checks sys.stdin.isatty(): a real terminal
    gets the loop below; anything else (a pipe, a cron job, a test harness)
    gets NONE of it, and every reviewable workflow comes back exactly as it
    went in — PENDING, never silently approved. Same contract as
    run_question_gate, so this never makes a non-interactive run block on
    input() either.
    """
    reviewable = [wf for wf in workflows
                 if wf.approved_topic is not None and wf.framing is not None
                 and wf.teaching_approach is not None]

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print(f"  {len(reviewable)} teaching approach(es) awaiting approval — not "
              f"an interactive terminal, so none are decided here.")
        return workflows

    decided = {wf.selection.topic.id: wf for wf in workflows}
    for wf in reviewable:
        topic_id = wf.selection.topic.id
        while True:
            wf = decided[topic_id]
            approach = wf.effective_teaching_approach
            print("\n" + "=" * 78)
            print(f"[{wf.selection.topic.source_section_id}] {wf.selection.source_title}")
            print(f"Teaching question: {wf.framing.teaching_question}")
            print(f"Approach: {_describe_approach(approach)}")
            if approach.alternatives:
                print(f"  alternatives considered: {', '.join(approach.alternatives)}")
            if approach.rationale:
                print(f"  rationale: {approach.rationale}")
            history = wf.teaching_approach_approval.regeneration_history
            if history:
                print(f"  {len(history)} regeneration(s) so far "
                      f"(limit {config.MAX_TEACHING_APPROACH_REGENERATIONS})")

            choice = input("[a]pprove  [g]enerate again  [s]kip (leave pending)  "
                           "[q]uit > ").strip().lower()
            if choice == "q":
                return list(decided.values())
            if choice == "a":
                decided[topic_id] = approve_teaching_approach(wf)
                break
            if choice == "g":
                reason = input("what should improve? (required) > ").strip()
                if not reason:
                    print("  ! a reason is required — nothing sent")
                    continue
                try:
                    decided[topic_id] = regenerate_teaching_approach(wf, reason, sections)
                except ValueError as e:
                    print(f"  ! {e}")
                    continue
                except Exception as e:
                    print(f"  ! regeneration failed ({type(e).__name__}: {e})")
                    continue
                print(f"  regenerated -> {_describe_approach(decided[topic_id].effective_teaching_approach)}")
                continue           # still needs an explicit approve
            if choice == "s":
                break              # leave as pending
            print("  ? choose a, g, s or q")
    return list(decided.values())


# ------------------------------------------------------- Step 11: visual plan gate
#
# THE SAME SHAPE AS STEP 6, ONE STAGE LATER, AND DELIBERATELY KEPT SEPARATE. A
# reviewer unhappy with the VISUAL PLAN ("beat 2 is basically a code
# screenshot") is not the same complaint as one unhappy with the TEACHING
# DEVICE or the QUESTION's own wording, so this has its own reason
# requirement, its own regeneration history, its own limit
# (config.MAX_VISUAL_PLAN_REGENERATIONS, not MAX_TEACHING_APPROACH_REGENERATIONS
# or MAX_QUESTION_REGENERATIONS) and its own gate — never folded into the two
# gates above. See schema.VisualStrategyRegenerationAttempt.
#
# ONLY TWO HUMAN ACTIONS EXIST HERE: approve, or request regeneration. There is
# no reject and no field-level edit — see schema.VisualPlanApproval's own "NO
# DIRECT EDITING".

def _require_visual_plan_reviewable(workflow: QuestionWorkflow) -> None:
    """
    The precondition every function below shares: an approved question, with
    framing, with an approved teaching approach, with a script already
    generated, with a visual_strategy already planned. Checked BEFORE
    anything else — including before validating a regeneration reason — so a
    workflow that fails an earlier stage is refused for THAT reason, not a
    confusing one about the request it never got to.
    """
    if workflow.approved_topic is None:
        raise ValueError(
            f"cannot review the visual plan for {workflow.selection.topic.id}: "
            f"question_approval.status={workflow.question_approval.status!r}, "
            f"not 'approved'")
    if workflow.framing is None:
        raise ValueError(
            f"cannot review the visual plan for {workflow.selection.topic.id}: "
            f"this workflow has no framing")
    if workflow.approved_teaching_approach is None:
        raise ValueError(
            f"cannot review the visual plan for {workflow.selection.topic.id}: "
            f"teaching_approach_approval.status="
            f"{workflow.teaching_approach_approval.status!r}, not 'approved'")
    if workflow.script is None:
        raise ValueError(
            f"cannot review the visual plan for {workflow.selection.topic.id}: "
            f"no script has been generated yet")
    if workflow.visual_strategy is None:
        raise ValueError(
            f"cannot review the visual plan for {workflow.selection.topic.id}: "
            f"no visual plan has been generated yet")


def approve_visual_plan(workflow: QuestionWorkflow,
                        note: str | None = None) -> QuestionWorkflow:
    """
    Approve `workflow`'s visual plan exactly as it currently stands —
    whatever effective_visual_strategy already resolves to (Step 10's
    original plan, or the latest regeneration) is what
    QuestionWorkflow.approved_visual_strategy hands a future rendering stage
    once this has run. Never touches the plan itself, only the gate.
    """
    _require_visual_plan_reviewable(workflow)
    approval = workflow.visual_plan_approval.model_copy(update={
        "status": "approved",
        "note": note if note is not None else workflow.visual_plan_approval.note,
    })
    return workflow.model_copy(update={"visual_plan_approval": approval})


def regenerate_visual_plan(workflow: QuestionWorkflow, reason: str,
                           sections: list[Section],
                           understanding=None) -> QuestionWorkflow:
    """
    The full Step 11 regeneration action: validate the reason, enforce the
    loop limit, call the LLM once for a COMPLETE new visual plan, and land
    back on `pending` — NEVER `approved`.

    A human must call approve_visual_plan again after this, however many
    times it runs — same contract as regenerate_teaching_approach one stage
    earlier, and see QuestionWorkflow.approved_visual_strategy's own note
    that a freshly regenerated plan is exactly as blocked as the one it
    replaced.

    DOES NOT TOUCH question_approval, framing, teaching_approach,
    teaching_approach_approval OR script. All four are UPSTREAM of the
    visual plan, not downstream of it: nothing about reconsidering the
    PICTURE changes what question is being asked, how it was framed, which
    teaching device was approved, or what the script actually says, so
    there is nothing above this stage for a visual-plan regeneration to
    invalidate. visual_plan_approval itself is replaced here — see the
    model_copy at the bottom of this function — and its own
    regeneration_history is exactly what grows, never reset, by this call.

    `understanding`, WHEN SUPPLIED, is passed straight through to
    skills.strategy.reconsider_visual_strategy — never fetched here, for the
    same reason skills/strategy.py never fetches one itself: doing so would
    silently add a second, uncached call on top of this step's own one call.

    Raises ValueError on a blank reason, a limit already reached, or any of
    _require_visual_plan_reviewable's preconditions failing — all caller
    mistakes the state machine refuses rather than works around.
    """
    _require_visual_plan_reviewable(workflow)
    reason = _require_reason(reason)
    approval = workflow.visual_plan_approval
    if approval.regeneration_attempts >= config.MAX_VISUAL_PLAN_REGENERATIONS:
        raise ValueError(
            f"visual-plan regeneration limit reached "
            f"({config.MAX_VISUAL_PLAN_REGENERATIONS} attempt(s)) for "
            f"{workflow.selection.topic.id} — approve what you have")

    previous_strategy = workflow.effective_visual_strategy
    section = find_section(sections, workflow.selection.topic.source_section_id)
    new_strategy = reconsider_visual_strategy(workflow, section, reason,
                                              previous_strategy,
                                              understanding=understanding)

    attempt = VisualStrategyRegenerationAttempt(
        reason=reason, previous_strategy=previous_strategy,
        regenerated_strategy=new_strategy)
    approval = approval.model_copy(update={
        "status": "pending",
        "regenerated_strategy": new_strategy,
        "regeneration_history": approval.regeneration_history + [attempt],
    })
    return workflow.model_copy(update={"visual_plan_approval": approval})


def run_visual_plan_gate(workflows: list[QuestionWorkflow], sections: list[Section],
                         interactive: bool | None = None) -> list[QuestionWorkflow]:
    """
    Step 11's human gate: approve, or request an LLM regeneration of, each
    workflow's visual plan. No editing prompt exists here on purpose — see
    schema.VisualPlanApproval's "NO DIRECT EDITING".

    ONLY WORKFLOWS THAT PASS _require_visual_plan_reviewable ARE SHOWN. A
    workflow still missing an earlier stage is filtered out silently here
    rather than shown with nothing to review — this gate is for reviewing a
    PLAN that exists, not for surfacing that one is missing.

    interactive=None (the default) checks sys.stdin.isatty() — same contract
    as run_question_gate/run_teaching_approach_gate, so this never makes a
    non-interactive run block on input() either.
    """
    reviewable = []
    for wf in workflows:
        try:
            _require_visual_plan_reviewable(wf)
        except ValueError:
            continue
        reviewable.append(wf)

    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        print(f"  {len(reviewable)} visual plan(s) awaiting approval — not an "
              f"interactive terminal, so none are decided here.")
        return workflows

    decided = {wf.selection.topic.id: wf for wf in workflows}
    for wf in reviewable:
        topic_id = wf.selection.topic.id
        while True:
            wf = decided[topic_id]
            strategy = wf.effective_visual_strategy
            print("\n" + "=" * 78)
            print(f"[{wf.selection.topic.source_section_id}] {wf.selection.source_title}")
            print(f"Teaching question: {wf.framing.teaching_question}")
            print(f"Subject: {strategy.subject}")
            refs, seen = [], set()
            for b in wf.script.beats:
                if b.visual_ref not in seen:
                    seen.add(b.visual_ref)
                    refs.append(b.visual_ref)
            print(as_brief(strategy, refs))
            history = wf.visual_plan_approval.regeneration_history
            if history:
                print(f"  {len(history)} regeneration(s) so far "
                      f"(limit {config.MAX_VISUAL_PLAN_REGENERATIONS})")

            choice = input("[a]pprove  [g]enerate again  [s]kip (leave pending)  "
                           "[q]uit > ").strip().lower()
            if choice == "q":
                return list(decided.values())
            if choice == "a":
                decided[topic_id] = approve_visual_plan(wf)
                break
            if choice == "g":
                reason = input("what should improve? (required) > ").strip()
                if not reason:
                    print("  ! a reason is required — nothing sent")
                    continue
                try:
                    decided[topic_id] = regenerate_visual_plan(wf, reason, sections)
                except ValueError as e:
                    print(f"  ! {e}")
                    continue
                except Exception as e:
                    print(f"  ! regeneration failed ({type(e).__name__}: {e})")
                    continue
                print("  regenerated visual plan")
                continue           # still needs an explicit approve
            if choice == "s":
                break              # leave as pending
            print("  ? choose a, g, s or q")
    return list(decided.values())


def main():
    # NEWEST FIRST. This used to be `sorted(...)` — alphabetical by filename,
    # i.e. by short_id — so a unit built five minutes ago could sit anywhere
    # in the list depending on what its id happened to spell, with nothing
    # marking it as the one that just got built. mtime is what actually
    # tracks "when was this written".
    files = sorted((f for f in config.OUTPUT_DIR.glob("*.json") if f.name not in SIDECARS),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print("nothing to review — run `python -m shorts.run <doc>` first")
        return

    for f in files:
        unit = ShortUnit(**json.loads(f.read_text()))
        if unit.status in ("approved", "rendered"):
            continue

        print("\n" + "=" * 78)
        print(f"{unit.short_id}   section {unit.source_section_id}   {unit.estimated_seconds}s")
        print(f"Q: {unit.question}")
        print("-" * 78)
        for i, b in enumerate(unit.beats):
            who = "INT" if b.speaker == "interviewer" else "STU"
            print(f"{i}. [{who}] {b.line}")
            print(f"        screen: \"{b.on_screen}\"   visual: {b.visual_ref}")
        print("-" * 78)
        for ref, v in unit.visuals.items():
            has_svg = "svg ok" if v.svg else ("no svg" if v.type == "diagram" else "-")
            print(f"  {ref:26} {v.type:8} {has_svg:8} {v.spec[:60]}")
        if unit.eval:
            print(f"\n  judge: faithfulness={unit.eval.faithfulness} "
                  f"clarity={unit.eval.clarity} pace={unit.eval.pace} "
                  f"diagram_ok={unit.eval.diagram_correct}")
            for p in unit.eval.problems:
                print(f"    ! {p}")

        choice = input("\n[a]pprove  [r]eject  [s]kip  [q]uit > ").strip().lower()
        if choice == "q":
            break
        if choice == "a":
            unit.status = "approved"
        elif choice == "r":
            unit.status = "rejected"
        else:
            continue
        f.write_text(unit.model_dump_json(indent=2))
        print(f"  -> {unit.status}")


if __name__ == "__main__":
    main()
