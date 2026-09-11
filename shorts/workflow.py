"""
Steps 7 and 9 — the orchestration boundary.

Advances a QuestionWorkflow as far as it can go WITHOUT a human, and stops
cleanly at the two human gates Steps 3 and 6 put in place. Nothing here
decides pedagogy, writes a line of narration, or generates content itself —
every generation step is exactly the call skills/framing.py,
skills/teaching_approach.py or skills/script.py already makes; this module's
entire job is deciding WHETHER to make that call, and reporting WHY it
stopped when it did.

WHY A SEPARATE MODULE, NOT review.py, run.py OR server.py. review.py owns the
state machine AT each human gate (approve / reject / regenerate) and stays
deliberately narrow — one gate, one decision, reused as-is by every caller.
run.py and server.py are two DIFFERENT callers (a terminal, an HTTP API) that
would otherwise each have to reimplement "check question approval, then
framing, then teaching approach, then its approval, then the script, in that
order" in their own words — exactly the duplication Steps 3-6 avoided by
keeping each gate's own state machine in one place. This module applies that
same discipline ACROSS stages instead of within one, and is the one place
that decision lives.

WHAT THIS MODULE OWNS: which stage is next, whether reaching it needs an LLM
call, and when to stop. WHAT IT DOES NOT OWN: any prompt, any pedagogical
judgement, any state transition INSIDE one stage, or the gate DECISIONS
themselves (approve/reject/regenerate) — all of those stay in
skills/framing.py, skills/teaching_approach.py, skills/script.py and
review.py, called here exactly as any other caller would call them.

STEP 9 ADDS SCRIPT GENERATION, one stage past teaching-approach approval,
using the EXISTING skills.script.write_script_for_workflow — no new
generation logic, no rebuilt inputs: that function is still the one place
that validates the three gates and assembles effective_question,
teaching_question and the approved approach into a prompt. This module still
only decides WHEN to call it.

STEP 10 ADDS VISUAL PLANNING, one stage past a script existing, using the
EXISTING skills.strategy.plan_strategy_for_workflow — again no new generation
logic: that function validates its own four gates and hands plan_strategy the
approved script (as the teaching sequence), section and approach. STOPS AT
"awaiting_visual_plan_approval" AND GOES NO FURTHER — Step 10 does not build
the approve/reject/regenerate state machine for the visual plan (that is
review.py's job, the same way Steps 3 and 6 own the question and
teaching-approach gates), so this module never reads
visual_plan_approval.status or reports anything past a plan existing.
"""
from typing import Literal

from pydantic import BaseModel

from .schema import QuestionWorkflow, Section, SectionUnderstanding
from .parse import find_section
from .skills.framing import frame_workflow
from .skills.teaching_approach import choose_teaching_approach_for_workflow
from .skills.script import write_script_for_workflow
from .skills.strategy import plan_strategy_for_workflow
from .skills.understanding import understanding_for


#: Why advance() stopped, in a form a human or a caller can act on directly.
#:
#: "awaiting_question_approval"           question_approval.status is pending
#:                                        (or the transient "regenerating") —
#:                                        approve, reject, or regenerate it.
#: "rejected"                             question_approval.status is
#:                                        "rejected" — PERMANENT. Nothing
#:                                        past this stage will ever run for
#:                                        this workflow again.
#: "awaiting_teaching_approach_approval"  framing and a teaching_approach both
#:                                        exist; teaching_approach_approval is
#:                                        not yet "approved" — approve it or
#:                                        request a regeneration.
#: "awaiting_visual_plan_approval"        question approved, framed, taught,
#:                                        SCRIPTED, AND a visual plan has been
#:                                        drafted. Nothing more for THIS
#:                                        module to do — approved_topic,
#:                                        approved_teaching_approach, script
#:                                        and visual_strategy are all set.
#:                                        Named for what comes next, the same
#:                                        reason "ready_for_next_stage" (Step
#:                                        7's placeholder) was retired for
#:                                        "ready_for_visual_planning" (Step 9's
#:                                        placeholder, before visual planning
#:                                        itself existed) — and THAT name is
#:                                        retired here in turn, now that
#:                                        reaching this point means planning
#:                                        already happened rather than being
#:                                        the next thing to do. review.py does
#:                                        NOT yet own an approve/regenerate
#:                                        state machine for this gate — see
#:                                        this module's own docstring — so
#:                                        nothing can move a workflow past
#:                                        this status yet, the same way
#:                                        nothing could move one past
#:                                        "awaiting_teaching_approach_approval"
#:                                        before Step 6 existed.
#: "framing_failed" / "teaching_approach_failed" / "script_failed" /
#: "visual_plan_failed"
#:                                        the workflow was eligible for that
#:                                        stage but the generation call itself
#:                                        raised (a provider error, a
#:                                        timeout, a precondition this
#:                                        module's own checks should have
#:                                        already prevented). See advance()'s
#:                                        own note on why this is caught here
#:                                        rather than left to propagate.
#:
#: THERE IS NO "generating_framing" / "generating_teaching_approach" /
#: "generating_script" / "generating_visual_plan" STATUS. advance() is
#: synchronous and runs straight through to a stopping point or a failure in
#: one call — there is no in-between moment for a caller to observe, so a
#: status implying one would be fiction. (Contrast QuestionApproval.status's
#: "regenerating", which is real precisely because it is CALLER-set, for a
#: caller reflecting its OWN in-flight request — see that field's docstring.
#: Nothing analogous exists here.)
OrchestrationStatus = Literal[
    "awaiting_question_approval",
    "rejected",
    "awaiting_teaching_approach_approval",
    "awaiting_visual_plan_approval",
    "framing_failed",
    "teaching_approach_failed",
    "script_failed",
    "visual_plan_failed",
]


class WorkflowProgress(BaseModel):
    """One workflow's result from advance(): where it ended up, and why."""
    workflow: QuestionWorkflow
    status: OrchestrationStatus
    #: A human-readable reason, always non-empty — see advance()'s own status
    #: assignments for exactly what each one says.
    detail: str = ""

    @property
    def needs_human(self) -> bool:
        """Stopped at a gate — pending isn't over, but it isn't stuck either."""
        return self.status in ("awaiting_question_approval",
                              "awaiting_teaching_approach_approval",
                              "awaiting_visual_plan_approval")


def advance(workflow: QuestionWorkflow, sections: list[Section], *,
           understanding: SectionUnderstanding | None = None,
           document: str | None = None) -> WorkflowProgress:
    """
    Move `workflow` forward exactly as far as it can go without a human, and
    report where it stopped.

    IDEMPOTENT, BY CONSTRUCTION. Every generation step below is gated on the
    corresponding field already being None:
      - framing is only generated when workflow.framing is None
      - a teaching approach is only generated when workflow.teaching_approach
        is None
      - a script is only generated when workflow.script is None (Step 9),
        and only once teaching_approach_approval is actually "approved" —
        see approved_teaching_approach below
      - a visual plan is only generated when workflow.visual_strategy is
        None (Step 10), and only once a script actually exists
    So calling this again on a workflow that already reached a stopping point
    does EXACTLY the same work as the first call past that point: none. A
    workflow a human has since regenerated (question or teaching approach)
    picks up cleanly wherever that regeneration left its status — regeneration
    is the ONLY thing that ever clears these fields for a re-decision, and it
    only ever happens through review.py's explicit, human-triggered functions
    (which also clear `script` at the correct scope — see
    QuestionWorkflow.invalidate_downstream / invalidate_script, Steps 7.1 and
    8.1), never through this one.

    NEVER APPROVES ANYTHING. This function can only move a workflow as far as
    a human already has — it reads question_approval.status and
    teaching_approach_approval.status, it never writes either. The
    "awaiting_*" statuses below are this function refusing to guess what a
    human would decide, exactly as QuestionWorkflow.approved_topic and
    .approved_teaching_approach already refuse to, one field at a time.
    Script generation is NOT a third human gate — Step 8 never added a
    script-approval concept — so once teaching_approach_approval is
    "approved", a missing script is generated automatically, the same way
    framing and the teaching approach already are once the question is
    approved.

    `understanding`, WHEN SUPPLIED, is passed to framing, teaching-approach
    AND script generation, UNCHANGED — this function never calls
    understanding_for itself, so it can never fetch two different readings of
    the same section for the calls it might make. See advance_many, which is
    where a caller gets one FOR this workflow's section — once, shared with
    everything else filed under it — before calling this.

    `document`, WHEN SUPPLIED, is passed only to script generation (the one
    stage that reads it — see skills.script.write_script's own `document`
    parameter); framing and teaching-approach generation have no use for it.

    NO SCRIPT-GENERATION LOGIC LIVES HERE. `section` is looked up (a plain
    dict-style lookup by id, not a decision) and handed straight to
    skills.script.write_script_for_workflow, which remains the one place that
    validates the three gates itself and assembles effective_question,
    teaching_question and the approved approach into a prompt — see that
    function's own docstring.

    EXCEPTIONS FROM GENERATION ARE CAUGHT, DELIBERATELY, the same choice
    skills.understanding.understanding_for already makes for the reading one
    stage earlier: a provider error or a timeout on ONE workflow must not
    raise out of a batch and take four good ones down with it (see
    advance_many, and requirement 10 — one workflow must never block
    another). Everything else — question and teaching-approach state — is
    read, never awaited, so there is nothing to catch on those paths.
    """
    if workflow.approved_topic is None:
        if workflow.question_approval.status == "rejected":
            return WorkflowProgress(
                workflow=workflow, status="rejected",
                detail="the question was rejected — this workflow goes no further")
        return WorkflowProgress(
            workflow=workflow, status="awaiting_question_approval",
            detail=f"question_approval.status={workflow.question_approval.status!r} "
                   f"— approve, reject, or request a regeneration")

    if workflow.framing is None:
        try:
            workflow = frame_workflow(workflow, sections, understanding=understanding)
        except Exception as e:
            return WorkflowProgress(
                workflow=workflow, status="framing_failed",
                detail=f"{type(e).__name__}: {e}")

    if workflow.teaching_approach is None:
        try:
            workflow = choose_teaching_approach_for_workflow(
                workflow, sections, understanding=understanding)
        except Exception as e:
            return WorkflowProgress(
                workflow=workflow, status="teaching_approach_failed",
                detail=f"{type(e).__name__}: {e}")

    if workflow.approved_teaching_approach is None:
        return WorkflowProgress(
            workflow=workflow, status="awaiting_teaching_approach_approval",
            detail=f"teaching_approach_approval.status="
                   f"{workflow.teaching_approach_approval.status!r} — approve it "
                   f"or request a regeneration")

    if workflow.script is None:
        try:
            section = find_section(sections, workflow.selection.topic.source_section_id)
            workflow = write_script_for_workflow(
                workflow, section, document=document, understanding=understanding)
        except Exception as e:
            return WorkflowProgress(
                workflow=workflow, status="script_failed",
                detail=f"{type(e).__name__}: {e}")

    if workflow.visual_strategy is None:
        try:
            section = find_section(sections, workflow.selection.topic.source_section_id)
            workflow = plan_strategy_for_workflow(
                workflow, section, understanding=understanding)
        except Exception as e:
            return WorkflowProgress(
                workflow=workflow, status="visual_plan_failed",
                detail=f"{type(e).__name__}: {e}")

    return WorkflowProgress(
        workflow=workflow, status="awaiting_visual_plan_approval",
        detail="question approved, framed, taught, scripted, and a visual "
               "plan has been drafted — approve it (a future step) before "
               "rendering")


def advance_many(workflows: list[QuestionWorkflow], sections: list[Section], *,
                 document: str | None = None,
                 understanding_by_section: dict[str, SectionUnderstanding | None] | None = None,
                 ) -> list[WorkflowProgress]:
    """
    advance() for every workflow in `workflows`, each entirely independently.

    ONE UNDERSTANDING PER SECTION, computed AT MOST ONCE per section PER
    CALL, and shared across every workflow filed under it — the same sharing
    run.build_one and server.make_scripts already do for the script step
    itself. Computed LAZILY: a section is only read at all if some workflow
    filed under it actually needs generation this call — missing framing,
    missing teaching_approach, an APPROVED teaching approach with no script
    yet (Step 9), OR (Step 10) a script with no visual_strategy yet. A
    workflow still pending question approval, still waiting on
    teaching-approach approval (chosen but not yet approved — nothing past
    that gate may run), or already fully "awaiting_visual_plan_approval",
    triggers no understanding call and therefore no cost, matching this
    step's own cost-protection requirement. THE SAME understanding object
    this fetches is what advance() then hands to framing, teaching-approach,
    script AND visual-plan generation for that workflow — never a second,
    separate fetch for any later stage.

    `understanding_by_section` lets a caller that already has readings short-
    circuit the lookup entirely — an entry present in the dict (even one
    mapped to None, meaning "the reading failed or was skipped") is used
    as-is and never re-fetched.

    `document` IS THREADED THROUGH TO advance() TOO (Step 9), not only used
    for the understanding fetch here — script generation is the one stage
    that reads it, via skills.script.write_script's own `document` parameter.

    NO WORKFLOW CAN BLOCK ANOTHER. Each advance() call is independent — one
    stopping at a human gate, one failing, and one reaching
    awaiting_visual_plan_approval all happen in the same pass with no
    ordering dependency between them (requirement 10).
    """
    by_id = {s.section_id: s for s in sections}
    resolved: dict[str, SectionUnderstanding | None] = dict(understanding_by_section or {})

    results = []
    for wf in workflows:
        section_id = wf.selection.topic.source_section_id
        needs_generation = (
            wf.approved_topic is not None and (
                wf.framing is None
                or wf.teaching_approach is None
                or (wf.approved_teaching_approach is not None and wf.script is None)
                or (wf.script is not None and wf.visual_strategy is None)
            )
        )
        understanding = None
        if needs_generation:
            if section_id not in resolved:
                section = by_id.get(section_id)
                resolved[section_id] = (
                    understanding_for(section, document=document, quiet=True)
                    if section is not None else None)
            understanding = resolved[section_id]
        results.append(advance(wf, sections, understanding=understanding, document=document))
    return results
