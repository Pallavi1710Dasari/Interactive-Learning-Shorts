"""SKILL 1c — question framing. Approved question in, teaching question out.

WHERE THIS SITS. select.py picks WHICH question; review.py's human gate decides
WHETHER it ships, as written or after an LLM regeneration. Both of those are about
the question's CONTENT — is it important, is it answerable, is it worded well
enough to approve. This step is about something else: once a question is
approved, is it phrased the way it should actually be ASKED in a four-beat
interview? "How does a stack work?" is a perfectly good, approvable question and
a weak opening line — it invites a definition instead of a demonstration, and
"What happens when you push and pop?" teaches the same idea faster. Deciding that
is a different judgement from deciding the question is worth a reel at all, so it
is its own step rather than another responsibility bolted onto selection or onto
write_script's opening beat.

WHY A SEPARATE CALL, not folded into write_script. Exactly the same argument
skills/understanding.py's own docstring makes for splitting comprehension from
drafting: a model asked to frame the question AND write four grounded answer
beats in one call does the answerable half and lets the harder judgement ride
along for free, unexamined. Isolating it means "is this the right opening
question" gets asked and checked on its own, before a single beat is written.

WHAT THIS STEP MUST NOT DO. Change the subject. source_question is fixed
BEFORE the model ever sees the prompt — see frame_question below — and
teaching_question is graded against staying on the same concept, never against
being more interesting or more elaborate. See checks.check_framing_grounded.
"""
from pydantic import BaseModel

from ..schema import (QuestionWorkflow, QuestionFraming, QuestionRole, Section,
                      SectionUnderstanding)
from ..llm import ask_json
from ..parse import find_section


FRAMING_SYSTEM = """You decide how an ALREADY-APPROVED interview question should
actually be asked in a short teaching video, given the section it is about.

YOU DO NOT CHOOSE THE QUESTION. It has already been selected and approved by a
human. Your only job is to decide whether it should be asked WORD FOR WORD, or
reframed into a version that is easier to teach in three or four short beats —
and if the latter, to write that version and say why.

THE PURPOSE IS NOT TO MAKE THE QUESTION SOUND MORE IMPRESSIVE. A reframe is
worth making only when it produces a CLEARER TEACHING FLOW — a question whose
answer is naturally a sequence of beats, rather than one whose answer is a
single sentence gesturing at a definition. If the approved question already
does that, the right answer is to keep it exactly as it is.

  SOURCE: "How does a stack work?"
  WEAK ANSWER SHAPE: a definition, then more definition. Nothing to walk
    through in beats.
  BETTER TEACHING QUESTION: "What happens when you add and remove items from a
    stack?" — the answer is naturally a sequence: push, then pop, then what the
    order guarantees. Same concept, easier to teach in beats.

  SOURCE: "What is caching?"
  WEAK ANSWER SHAPE: a one-line definition with nowhere to go for three more
    beats.
  BETTER TEACHING QUESTION: "Why does keeping frequently used data readily
    available make an application faster?" — same concept (caching), but the
    answer is a mechanism and a consequence, which is what beats are for.

RULES FOR THE TEACHING QUESTION, ALL OF THEM HARD:
- It must be about the EXACT SAME CONCEPT as the approved question. Sharpening
  or reshaping how it is asked is allowed; asking about something else is not.
- It must not change what a correct answer would need to cover — the learning
  OBJECTIVE stays the one the approved question already set.
- It must not be BROADER than the approved question without a real teaching
  reason tied to this section. "How does a stack work?" reframed as "How do
  data structures manage memory?" is a different, bigger question, not a
  clearer version of the same one — reject that shape of change.
- It must be answerable FROM THE SECTION BELOW alone, the same rule every
  other question in this pipeline follows. Do not reframe toward something
  the section does not settle.
- If the approved question is already the clearest way to ask about this
  concept, TEACHING_QUESTION SHOULD BE IDENTICAL TO IT. Reframing every
  question whether or not it needs it is not the goal; a needless rewrite is
  a defect here, not a feature.
- One plain sentence, the same question-writing rules selection already used:
  starts with What/Why/How/Which/When/Where, never a yes/no opener, exactly
  one question mark.

ROLE — what job this question does in the reel it becomes. Almost always
"primary": one question drives one reel, and that is the default for a reason.
Choose anything else ONLY when the material you are given (the teaching
sequence, the hook plan, if present) gives a CLEAR, SPECIFIC reason this
question is not the central one — for example, it is offered as a warm-up hook
before the real question, or it exists to check a stated misconception rather
than to drive the explanation. Do not assign a role other than "primary" for
variety, or because one of the other four sounds more precise. When in doubt,
"primary" is correct.

  primary              the question the reel is built to answer. The default.
  hook                 opens the reel and hands over to a different core
                       question — only when the material clearly separates
                       the two.
  reinforcement        restates or checks an idea already taught, rather than
                       introducing the reel's main idea.
  misconception_check  specifically aimed at a stated misconception, per the
                       section's own confusion_plan, not at explaining the
                       mechanism generally.
  transition           bridges from one idea to a following one, rather than
                       driving the explanation itself.

Explain your choice in framing_rationale — one or two sentences, concrete about
WHY this framing (or the decision to keep it unchanged) serves the teaching
flow. "This wording is clearer" is not a reason; naming what the reframe makes
possible ("the answer becomes a sequence of two operations instead of a single
definition") is.

Return JSON:
{"teaching_question": "...", "framing_rationale": "...", "role": "primary"}"""


class _FramingOutput(BaseModel):
    """
    What the model actually decides. DELIBERATELY MISSING source_question —
    the model is never asked for it and has no field to put one in, so there
    is no JSON key for it to fill even if it tried. See frame_question, which
    sets QuestionFraming.source_question itself, from workflow.effective_question,
    after this call returns.
    """
    teaching_question: str
    framing_rationale: str = ""
    role: QuestionRole = "primary"


def frame_question(workflow: QuestionWorkflow, section: Section,
                   understanding: SectionUnderstanding | None = None) -> QuestionFraming:
    """
    One LLM call: decide how workflow's approved question should be asked.

    NO GATING HERE — that is frame_workflow's job, the same split select.py's
    regenerate_question (the raw call) and review.regenerate (the gated entry
    point) already use. A caller that reaches this function directly is
    assumed to have already checked workflow.approved_topic is not None.

    source_question IS SET HERE, DETERMINISTICALLY, FROM
    workflow.effective_question — NEVER FROM THE MODEL. This is what makes
    "the LLM cannot override source_question" true structurally rather than
    by convention: _FramingOutput has no field for it, so there is nothing
    for the model to override even if the prompt were silent about it.

    `understanding` is OPTIONAL and this function never computes one itself —
    supplying it is the caller's choice, exactly like write_script's own
    `understanding` parameter. That is what keeps this step's cost to AT MOST
    ONE call: fetching a fresh SectionUnderstanding here would silently add a
    second, uncached one on top of framing's own.
    """
    source_question = workflow.effective_question
    topic = workflow.selection.topic

    user = f"""APPROVED QUESTION — this is what the reel is about, and it is fixed:
{source_question}
"""
    if topic.topic != source_question:
        user += f"""
ORIGINALLY SELECTED AS: {topic.topic}
(The line above is already the human-approved version — a straight approval,
or an LLM regeneration a human then approved. Frame FROM the approved question,
not from this one; it is shown only so you understand what changed and why.)
"""

    user += f"""
CONCEPT: {topic.concept or topic.topic}

WHY THIS QUESTION WAS SELECTED:
""" + ("\n".join(f"- {r.explanation}" for r in workflow.selection.reasons)
       or "(none recorded)") + "\n"

    # SAME PLACEMENT RULE write_script USES: guidance before the section,
    # never after it — see write_script's own comment on this. `as_brief()`
    # returns "" when the reading came back empty, so an absent or quarantined
    # understanding changes nothing about the prompt below it.
    if understanding is not None:
        brief = understanding.as_brief()
        if brief:
            user += f"""
CONTENT UNDERSTANDING — GUIDANCE ONLY, NOT A SOURCE OF CLAIMS, NEVER QUOTE IT
An earlier step read the section below and worked out what it teaches and how.
Use it to judge which teaching question fits the section's own teaching order —
nothing here is itself something the reframed question may claim beyond what
the section states.
{brief}
"""

    user += f"""
SECTION {section.section_id} — {section.title}, THE ONLY SOURCE OF FACTS:
{section.text}

Decide the teaching question."""

    result = ask_json(FRAMING_SYSTEM, user, _FramingOutput, max_tokens=500,
                      label="framing")

    return QuestionFraming(
        source_question=source_question,
        teaching_question=result.teaching_question.strip(),
        framing_rationale=(result.framing_rationale or "").strip() or None,
        role=result.role,
    )


def frame_workflow(workflow: QuestionWorkflow, sections: list[Section],
                   understanding: SectionUnderstanding | None = None) -> QuestionWorkflow:
    """
    Step 4's entry point: frame an APPROVED workflow's question and attach the
    result to workflow.framing.

    THE ONE GATE. Mirrors QuestionWorkflow.approved_topic exactly — pending,
    rejected and regenerating all raise ValueError here, BEFORE find_section or
    any LLM call runs, so a workflow that is not approved never spends a call.
    This is deliberately the same check approved_topic performs, not a second,
    looser one: "may this workflow be framed" and "may this workflow proceed
    downstream" are the same question, asked at two different stages.

    A NEW ENTRY POINT, NOT A CHANGED PATH. Nothing in run.py, server.py or
    skills/script.py calls this yet — write_script still reads topic.topic
    exactly as it always has, and framing.py has no effect on it. This is the
    callable boundary a future step wires in, added ahead of that wiring so
    QuestionFraming's shape can be exercised end to end first.
    """
    if workflow.approved_topic is None:
        raise ValueError(
            f"cannot frame {workflow.selection.topic.id}: question_approval.status="
            f"{workflow.question_approval.status!r}, not 'approved'")

    section = find_section(sections, workflow.selection.topic.source_section_id)
    framing = frame_question(workflow, section, understanding=understanding)
    return workflow.model_copy(update={"framing": framing})
