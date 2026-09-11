"""SKILL 1d — teaching approach. Framed question in, a pedagogical device out.

WHERE THIS SITS. select.py picked WHICH question; review.py's human gate decided
WHETHER it ships; framing.py decided HOW it is WORDED. None of those say HOW THE
ANSWER SHOULD BE TAUGHT — whether the beats that follow should walk a process,
draw an analogy, show real code, or hold two things up for comparison. That is a
different judgement again, and folding it into script-writing is exactly the
mistake skills/understanding.py's own docstring warns against: a model asked to
choose a teaching device AND draft four grounded beats in one call does the
answerable half (produce beats) and lets the harder judgement (which DEVICE) ride
along unexamined, which is how a pipeline with seven documented teaching devices
ends up drawing every short as icons-in-a-row.

WHY THIS IS A REAL RISK, NAMED PLAINLY. The most likely way this call fails is
not "wrong device" in general, it is one SPECIFIC device chosen for the wrong
reason: `code`, picked because the section happens to contain some and the course
is about programming, rather than because the CONCEPT is a piece of syntax. See
TEACHING_APPROACH_SYSTEM's own CODE IS NOT THE DEFAULT section, and
checks.check_teaching_approach_not_code_by_default, which catches the laziest
version of that mistake deterministically.

WHAT THIS STEP MUST NOT DO. Decide anything about VISUALS — that is
skills/strategy.py's BeatStrategy, a later, per-BEAT decision about relationship
and physical_form once a script exists. TeachingApproach is coarser and earlier:
one decision, for the whole reel, about the pedagogical DEVICE — analogy, code,
comparison, and so on — before a single beat is written.
"""
from ..schema import (QuestionWorkflow, TeachingApproach, Section, SectionUnderstanding)
from ..llm import ask_json
from ..parse import find_section


#: THE KIND DEFINITIONS AND THE RULES GOVERNING THEM, SHARED BY BOTH PROMPTS
#: BELOW. The initial decision and a reconsideration must be held to the
#: EXACT SAME rules — CODE IS NOT THE DEFAULT applies just as hard to a
#: regeneration as to a first decision, so this is written once and included
#: in both rather than risking the two prompts drifting apart over time.
_APPROACH_KINDS_AND_RULES = """Choose exactly one PRIMARY approach from:

  analogy                the concept is explained by comparison to something
                         familiar from outside the material. Fits ABSTRACT
                         mechanisms that are hard to picture directly — what a
                         stack IS, what caching IS, what a lock IS.
  real_world_example      a concrete case from everyday use illustrates the
                         concept. Fits a mechanism whose VALUE is best seen in
                         a situation a learner already recognises.
  code                    the answer is taught by showing and reading actual
                         code or syntax. Fits ONLY when the concept itself is
                         a syntax rule, a language feature, or something whose
                         correct teaching genuinely requires the viewer to see
                         the written form — see CODE IS NOT THE DEFAULT below.
  conceptual_visual       the idea is taught by a diagram or a picture of its
                         structure or state — containers, pointers, levels,
                         a state changing. Fits a MECHANISM defined by
                         structure or by something changing over time.
  process_demonstration   the answer is taught by walking a sequence of steps
                         in order. Fits an OPERATION or an algorithm — what
                         happens, in order, when you do X.
  comparison               two things are held up side by side because the
                         concept IS the difference between them. Fits a
                         question that is fundamentally "how does A differ
                         from B", not one where a comparison would just be
                         decoration.
  direct_explanation       the concept is explained plainly, with no device
                         beyond stating and reasoning about it. Fits a
                         definition or a plain rule that does not need a
                         demonstration, an analogy or a picture to be clear.

THE DECISION IS ABOUT THE CONCEPT AND THE TEACHING QUESTION, NOT ABOUT WHAT
WOULD LOOK GOOD. Ask what a learner actually needs to SEE or FOLLOW to
understand THIS concept, never which device is the most visually interesting
one available. A device chosen because it would make a striking picture, with
no teaching reason tied to the concept, is the wrong choice however good it
would look.

CODE IS NOT THE DEFAULT, AND THIS IS THE RULE MOST LIKELY TO BE GOTTEN WRONG.
Do not choose `code` because:
  - the section happens to contain a code snippet
  - the material is from a programming course
  - a line of code is available as an example
Any of those makes `code` merely POSSIBLE, never RIGHT. Choose `code` only when
the concept ITSELF is a piece of syntax, a language feature, or a rule about
written code — something that cannot be taught correctly without showing the
written form. "What does the `static` keyword do?" is a code concept. "How
does a stack work?" is NOT, even if the section that explains it happens to
show a stack implemented in code — that section's own code is evidence for
`process_demonstration` or `conceptual_visual` about the STACK, not a reason to
teach the stack AS code.

  WRONG   primary: code — rationale: "the section shows a code example"
          ^ Availability, not necessity. Reject this reasoning.
  RIGHT   primary: code — rationale: "the question is specifically about what
          the `static` keyword changes about a method's syntax and behaviour,
          which cannot be shown without the written form"

COMBINED_WITH — almost always empty, occasionally exactly one more approach,
when a SECOND device genuinely improves teaching THIS concept. Not for
variety. A real example: primary process_demonstration, combined_with
conceptual_visual, for a mechanism that is a sequence of steps where a picture
of the state changing at each step makes the sequence land. Leave it empty
whenever the primary approach is sufficient on its own — an empty list is the
ordinary, correct answer far more often than a populated one.

ALTERNATIVES — one or two OTHER approaches that were genuinely plausible for
this same concept, not a device you have already ruled out for an unrelated
reason. Never list every remaining kind; that is not a comparison, it is
padding. If nothing else was genuinely close, return an empty list.

RATIONALE, and this is the field most likely to be filled with nothing: it
must say, specifically —
  (a) why the primary approach fits THIS concept, in this concept's own terms
  (b) why it supports answering the teaching question asked, specifically
  (c) why the source material actually SUPPORTS teaching it this way (a
      process needs steps to walk, a comparison needs two things stated, an
      analogy needs the concept to be genuinely abstract, and so on)
NEVER write a generic justification that would apply to any concept — "this
approach is engaging", "this makes it more interesting", "this is a popular
way to explain things" are all rejected. If you cannot say something specific
to THIS concept, you have not finished deciding."""

_APPROACH_JSON_INSTRUCTION = """Return JSON:
{"primary":"analogy|real_world_example|code|conceptual_visual|process_demonstration|comparison|direct_explanation",
 "combined_with":["..."],"alternatives":["..."],"rationale":"..."}"""


TEACHING_APPROACH_SYSTEM = f"""You decide HOW an already-framed teaching question
should be taught in a short interview-style video — not what the question is,
not how it is worded, but which pedagogical DEVICE the answer beats should use.

{_APPROACH_KINDS_AND_RULES}

{_APPROACH_JSON_INSTRUCTION}"""


TEACHING_APPROACH_REGENERATE_SYSTEM = f"""You are RECONSIDERING a teaching
approach that was already decided, because a human reviewer wants something
about it to change. You are given the PREVIOUS decision and the reviewer's
specific reason, and your job is a fresh, COMPLETE decision that addresses it
— not a patch to one field of the old one.

{_APPROACH_KINDS_AND_RULES}

RECONSIDERING, SPECIFICALLY:
- Read the reviewer's reason and address it directly. "Code is not necessary
  for this concept" means `primary` should very likely move away from code;
  "a real-world example would explain this better" points specifically at
  real_world_example; "this should be a process" points at
  process_demonstration. Do not produce a decision that ignores what was
  actually asked for.
- You MAY end up at the same `primary` you started with, if, having genuinely
  weighed the reviewer's reason against the concept, it still fits best. If
  so, say so plainly in the rationale — explain why the reason does not
  change the decision — rather than silently repeating the old answer.
- Produce the COMPLETE decision again: primary, combined_with, alternatives
  and rationale together. The previous decision below is shown for CONTEXT
  ONLY, not as a baseline you are patching or mostly keeping.

{_APPROACH_JSON_INSTRUCTION}"""


def choose_teaching_approach(workflow: QuestionWorkflow, section: Section,
                             understanding: SectionUnderstanding | None = None,
                             ) -> TeachingApproach:
    """
    One LLM call: decide the pedagogical device for an already-framed question.

    NO GATING HERE — that is choose_teaching_approach_for_workflow's job, the
    same split framing.frame_question/frame_workflow already uses. A caller
    reaching this directly is assumed to have already checked
    workflow.approved_topic is not None and workflow.framing is not None.

    workflow.framing MUST ALREADY BE SET, and this reads it rather than
    re-deriving anything: teaching_question (what the beats will actually
    answer), role, and framing_rationale all inform which device fits. This
    function never builds a QuestionFraming itself — see the module docstring
    on orchestration providing framing explicitly.

    `understanding` is OPTIONAL and this function never computes one — exactly
    framing.frame_question's own contract, and for the same reason: fetching
    one here would silently add a second, uncached call on top of this step's
    own, and the brief only promises ONE.
    """
    framing = workflow.framing
    if framing is None:
        raise ValueError(
            f"cannot choose a teaching approach for {workflow.selection.topic.id}: "
            f"no framing on this workflow")

    topic = workflow.selection.topic
    reasons_block = ("\n".join(f"- {r.explanation}" for r in workflow.selection.reasons)
                     or "(none recorded)")

    user = f"""TEACHING QUESTION — this is what the answer beats will teach:
{framing.teaching_question}
ROLE OF THIS QUESTION IN THE REEL: {framing.role}
"""
    if framing.framing_rationale:
        user += f"WHY IT WAS FRAMED THIS WAY: {framing.framing_rationale}\n"

    user += f"""
CONCEPT: {topic.concept or topic.topic}

WHY THIS QUESTION WAS SELECTED:
{reasons_block}
"""

    # SAME PLACEMENT RULE write_script AND framing.py BOTH USE: guidance
    # before the section, never after it. `as_brief()` returns "" for an
    # empty/quarantined reading, so an absent understanding changes nothing.
    if understanding is not None:
        brief = understanding.as_brief()
        if brief:
            user += f"""
CONTENT UNDERSTANDING — GUIDANCE ONLY, NOT A SOURCE OF CLAIMS
An earlier step read the section below and worked out what it teaches and how.
Use it to judge what kind of thing this concept IS — a process to walk, a
structure to picture, a piece of syntax, a comparison — not as a source of
facts about the approach itself.
{brief}
"""

    user += f"""
SECTION {section.section_id} — {section.title}, THE ONLY SOURCE OF FACTS:
{section.text}

Decide the teaching approach."""

    return ask_json(TEACHING_APPROACH_SYSTEM, user, TeachingApproach,
                    max_tokens=600, label="teaching_approach")


def reconsider_teaching_approach(workflow: QuestionWorkflow, section: Section,
                                 reason: str, previous_approach: TeachingApproach,
                                 understanding: SectionUnderstanding | None = None,
                                 ) -> TeachingApproach:
    """
    One LLM call: reconsider workflow's teaching approach given a human's
    stated reason and the PREVIOUS complete decision — Step 6's counterpart to
    skills.select.regenerate_question.

    `reason` IS ASSUMED NON-BLANK — schema.TeachingApproachRegenerationAttempt's
    own validator is what actually enforces that; review.regenerate_teaching_approach
    builds the attempt (which raises first) rather than this function
    re-checking a rule it does not own.

    ALWAYS RETURNS A COMPLETE TeachingApproach, never a patch — see
    TEACHING_APPROACH_REGENERATE_SYSTEM's own "RECONSIDERING, SPECIFICALLY".
    The previous decision is shown to the model for context, not as a
    baseline it edits in place.
    """
    if workflow.framing is None:
        raise ValueError(
            f"cannot reconsider a teaching approach for {workflow.selection.topic.id}: "
            f"this workflow has no framing")

    framing = workflow.framing
    topic = workflow.selection.topic
    reasons_block = ("\n".join(f"- {r.explanation}" for r in workflow.selection.reasons)
                     or "(none recorded)")
    combined = (", combined with " + ", ".join(previous_approach.combined_with)
               if previous_approach.combined_with else "")

    user = f"""TEACHING QUESTION — this is what the answer beats will teach:
{framing.teaching_question}
ROLE OF THIS QUESTION IN THE REEL: {framing.role}

CONCEPT: {topic.concept or topic.topic}

WHY THIS QUESTION WAS SELECTED:
{reasons_block}

THE PREVIOUS DECISION:
primary: {previous_approach.primary}{combined}
alternatives considered: {', '.join(previous_approach.alternatives) or '(none)'}
rationale given: {previous_approach.rationale or '(none)'}

THE REVIEWER'S REQUESTED CHANGE — address this directly:
{reason}
"""

    if understanding is not None:
        brief = understanding.as_brief()
        if brief:
            user += f"""
CONTENT UNDERSTANDING — GUIDANCE ONLY, NOT A SOURCE OF CLAIMS
{brief}
"""

    user += f"""
SECTION {section.section_id} — {section.title}, THE ONLY SOURCE OF FACTS:
{section.text}

Reconsider the teaching approach."""

    return ask_json(TEACHING_APPROACH_REGENERATE_SYSTEM, user, TeachingApproach,
                    max_tokens=600, label="teaching_approach_regenerate")


def choose_teaching_approach_for_workflow(workflow: QuestionWorkflow,
                                          sections: list[Section],
                                          understanding: SectionUnderstanding | None = None,
                                          ) -> QuestionWorkflow:
    """
    Step 5's entry point: choose a teaching approach for an APPROVED, FRAMED
    workflow and attach the result to workflow.teaching_approach.

    THE ONE GATE, TWICE. pending, rejected and regenerating all raise
    ValueError, exactly like framing.frame_workflow — see
    QuestionWorkflow.approved_topic. UNFRAMED ALSO RAISES: this step decides
    how to teach the QUESTION AS FRAMED (teaching_question, role), so a
    workflow with no framing has nothing yet for this decision to be about.
    Both checks run BEFORE find_section or any LLM call, so neither case
    spends a call.

    FRAMING IS NEVER BUILT HERE. This function takes workflow.framing exactly
    as it finds it — if it is None, this raises rather than silently calling
    skills.framing.frame_workflow to produce one. The orchestration that
    chains framing then teaching-approach is a caller's job, not this
    function's; see the module docstring's "orchestration should provide
    framing explicitly".

    ONLY workflow.teaching_approach IS WRITTEN. selection, question_approval,
    framing, script and visual_strategy all pass through model_copy
    untouched — see test_teaching_approach_does_not_touch_other_workflow_fields.
    """
    if workflow.approved_topic is None:
        raise ValueError(
            f"cannot choose a teaching approach for {workflow.selection.topic.id}: "
            f"question_approval.status={workflow.question_approval.status!r}, "
            f"not 'approved'")
    if workflow.framing is None:
        raise ValueError(
            f"cannot choose a teaching approach for {workflow.selection.topic.id}: "
            f"this workflow has no framing yet — run skills.framing.frame_workflow "
            f"first")

    section = find_section(sections, workflow.selection.topic.source_section_id)
    approach = choose_teaching_approach(workflow, section, understanding=understanding)
    return workflow.model_copy(update={"teaching_approach": approach})
