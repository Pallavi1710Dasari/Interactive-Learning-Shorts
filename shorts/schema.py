"""
The data contract for the whole pipeline.

Every step reads one of these models and returns another. If a step's output
does not validate, the pipeline stops there instead of pushing a broken object
further downstream. Design this file first and change it rarely.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Speech pacing. 150 words/min is a conservative average for clear narration.
WORDS_PER_MINUTE = 150
WORDS_PER_SECOND = WORDS_PER_MINUTE / 60.0

# The length window, in seconds of speech.
#
# 25-50 -> ... -> 35-50 -> 25-45, and this is the FOURTH setting. Read the history
# before moving it a fifth time, because the previous four each had a reason and
# only the last one has evidence.
#
#   30-60   The floor forced padding. A question whose honest answer is three
#           sentences had to be inflated, and the extra beat was always the
#           weakest — a restatement, or a claim propped up by a citation that did
#           not really support it.
#   18-45   Cut for the same defect, one level down.
#   12-28   Cut again on memorability: at 45s a short was five points long, and
#           five points is what made these unmemorable.
#   35-50   Raised on the theory that length was never the problem — that a
#           45-second short is only padded when the TOPIC could not fill it, and
#           that a real depth gate in select plus an understanding-driven plan
#           would make the length honest.
#   25-45   THE THEORY WAS HALF RIGHT AND THE FLOOR WAS STILL WRONG.
#
# What settled it was measurement, not argument. Four real runs against
# content/css_specificity.md — a document written specifically to be rich enough
# for 45 seconds — produced scripts of 67, 77 and 71 words: mean 71.7 words, 28.7
# seconds, against an 87-word floor. Most attempts passed every other grader. One
# of them opened by correcting the misconception, scored both of the section's real
# selectors verbatim, and landed the consequence. It was a good short and the only
# thing wrong with it was that it was 28 seconds.
#
# So the natural length of a source-grounded, one-idea-per-beat explanation of a
# single concept is around 28-30 seconds, and three separate settings of this
# window have now produced that number. The floor is 25s to admit it.
#
# WHAT THE WINDOW IS NOT: a target. 25-45 is wide because the concept decides,
# and skills/script.py states the bands rather than a figure to hit —
#   25-30s  concise but complete
#   30-38s  a normal mechanism-and-consequence explanation
#   38-45s  a richer concept, with a grounded example and/or a misconception
# A short at the bottom of that range is not a short that fell short.
#
# The two things holding quality in place are NOT the floor, and both stay: every
# beat is still one idea (checks.MAX_ANSWER_WORDS = 24) and no beat may restate an
# earlier one (checks.check_beats_develop). Those reject a padded 40-second short,
# which is what the floor was being asked to do and could not.
#
# 25s is ~62 words, 45s is ~112.
MIN_SECONDS = 25
MAX_SECONDS = 45

# checks.MAX_ANSWERS (5) and checks.MAX_ANSWER_WORDS (24) are hard, independently
# tuned caps on beat count and beat length — see their docstrings for why each was
# tried larger and rejected (a script that "becomes a list again" past five beats;
# a wall of text past 24 words). Those caps were not chosen with MAX_SECONDS in
# mind, and they can produce more speech than 45s admits: 1 question beat plus 5
# answer beats at 24 words is already ~135 words, ~54s — over the 45s ceiling
# using structure this file already allows.
#
# HARD_MAX_SECONDS is that reachable structural maximum, rounded up a little for
# a question beat's own words, NOT a new, larger target. checks.duration_budget
# only unlocks it for a section whose reading genuinely supports a 5th beat — see
# checks.plan_material — so a thin section still gets the 45s ceiling. Nothing
# about MAX_ANSWERS or MAX_ANSWER_WORDS changes: this only stops check_timing from
# rejecting a script that used the beats and words those caps already allow.
HARD_MAX_SECONDS = 58

MAX_OVERLAY_WORDS = 8


class Section(BaseModel):
    """One chunk of the source reading material."""
    section_id: str          # e.g. "3.2"
    title: str
    text: str
    start_line: int
    end_line: int

    @property
    def span(self) -> str:
        return f"{self.section_id} (lines {self.start_line}-{self.end_line})"


class Topic(BaseModel):
    """Output of Skill 1. One topic becomes one short."""
    id: str
    topic: str
    why_it_matters: str
    source_section_id: str
    difficulty: Literal["easy", "medium", "hard"]

    # The sentence from the section that ANSWERS this question, copied verbatim.
    #
    # This is the fix for questions that cannot be answered from the reading
    # material. Selection used to be asked, in prose, to only pick answerable
    # topics; nothing checked that it had, so a plausible-sounding question whose
    # answer was not in the document survived all the way to a reviewer, and the
    # script step then either refused or invented. Making the model produce the
    # evidence turns that from a request into something select.py can verify by
    # string match, the same way check_source_quotes already does for beats.
    #
    # Optional because topics.json files written before this field existed must
    # still load. Newly selected topics without one are dropped by select.py.
    answer_quote: Optional[str] = None

    # THERE IS DELIBERATELY NO `depth` FIELD HERE, and it was removed rather than
    # never written — the reasoning is worth keeping because it is easy to re-add.
    #
    # It held which of mechanism / consequence / example / misconception the topic's
    # section was judged to hold, filled by select as a side-task of ranking. Three
    # of those four are what skills/understanding.py reads off the SAME section a
    # step later — and it does so per section rather than per topic, validated
    # against the section text, and quarantined when the reading does not hold up.
    #
    # So the field was a second, weaker record of facts the understanding already
    # owns: unvalidated, duplicated across topics sharing a section, and — the part
    # that settled it — read by nothing. select filled it and no step consumed it.
    #
    # The division that replaced it: select's prompt keeps the depth CRITERIA as a
    # gate (it is the only step that sees every section at once and can compare
    # them), and that gate stays a prompt instruction rather than a stored claim.
    # The understanding is the single record of what a section holds, and
    # checks.check_plan_depth is the one place that asks whether it is enough for a
    # 35-50s short.

    # How much this question matters, 1-5, against the rubric in select.py.
    #
    # This exists because selection was returning correct, answerable, forgettable
    # questions — the definition of one CSS property, a yes/no about whether HTML
    # styles a page — alongside the ones a learner is actually asked. Everything
    # about those topics validated, so nothing downstream could tell them apart
    # from the good ones. Scoring them makes "the most important questions in this
    # material" something select.py can sort by and cut, instead of a hope.
    #
    # Optional for the same reason answer_quote is: older topics.json must load.
    importance: Optional[int] = Field(default=None, ge=1, le=5)

    # The one concept this question is about, as a short noun phrase. Used to keep
    # three shorts asking the same thing three ways out of one deck.
    concept: Optional[str] = None


class TopicList(BaseModel):
    topics: list[Topic]

    @field_validator("topics")
    @classmethod
    def check_count(cls, v):
        # 1 is legitimate: a short reading may only contain one thing worth a
        # short, and asking for one reel should not be rejected as malformed.
        if not 1 <= len(v) <= 12:
            raise ValueError(f"expected 1-12 topics, got {len(v)}")
        return v


#: ============================================================================
#: HUMAN-IN-THE-LOOP PLANNING WORKFLOW (future).
#:
#: Reading Material -> Top Questions -> QuestionSelection (source + why) ->
#: QuestionApproval (human) -> QuestionFraming -> TeachingApproach (LLM) ->
#: TeachingApproachApproval (human) -> Script -> VisualStrategy ->
#: VisualPlanApproval (human) -> final reel.
#:
#: These models are data contracts only. Nothing in select.py, script.py,
#: strategy.py or server.py reads or writes them yet — see QuestionWorkflow at
#: the bottom of this file, which stitches all of them together and explains
#: why the container itself is optional-by-stage.
#: ============================================================================

SelectionReasonCategory = Literal[
    "importance",              # scores high on Topic.importance's existing rubric
    "foundational",            # later understanding depends on this being clear
    "commonly_confused",       # learners often get this wrong
    "concrete_and_answerable", # the section gives a clean, checkable answer
    "distinct_angle",          # asks about the concept from an angle its
                               # siblings in the same TopicList do not
    "other",
]


class SelectionReason(BaseModel):
    """One structured reason a question was surfaced, for a human to read
    alongside it. category is the axis a reviewer scans down a list of
    candidates on; explanation is the specific claim for THIS question."""
    category: SelectionReasonCategory
    explanation: str = ""


class QuestionSelection(BaseModel):
    """Why one candidate question was surfaced for human approval, before any
    teaching decision has been made about it.

    WRAPS A TOPIC RATHER THAN COPYING IT. Topic already carries the source
    section/topic identity (id, source_section_id), the existing importance
    signal (1-5, against select.py's rubric) and a why_it_matters sentence —
    exactly the "importance/relevance signals already available" requirement 1
    asks to be reused. Restating them as new fields here would be a second,
    driftable record of facts Topic already owns.

    What this model adds is what Topic does not have: the section's own
    human-readable title (Topic only carries source_section_id, an id like
    "3.2"), and a STRUCTURED breakdown of why this question in particular was
    picked — which why_it_matters, one free-text sentence, cannot represent.
    """
    topic: Topic
    #: Copied from Section.title, so an approval screen can show "from: <title>"
    #: without joining back against sections.json.
    source_title: str
    reasons: list[SelectionReason] = Field(default_factory=list)

    @field_validator("reasons")
    @classmethod
    def at_least_one_real_reason(cls, v):
        # THE SCHEMA'S OWN JOB — "can this be represented" — same as
        # TeachingStep.not_blank above. A QuestionSelection with no reasons, or
        # with reasons that are all blank, is not a weaker explanation: it is
        # no explanation, and a human approval screen has nothing to show.
        if not v:
            raise ValueError("a QuestionSelection needs at least one SelectionReason "
                             "— a question surfaced with no explanation cannot be "
                             "reviewed")
        if not any((r.explanation or "").strip() for r in v):
            raise ValueError("every SelectionReason here has a blank explanation — "
                             "at least one must say something a human can read")
        return v


class RegenerationAttempt(BaseModel):
    """One completed LLM regeneration of a candidate question — see
    QuestionApproval's "NO DIRECT EDITING" note for why this exists instead of
    a human simply retyping the question.

    THE HUMAN SUPPLIES ONLY `reason`. `previous_question` and
    `regenerated_question` are both machine text: the question this attempt
    started from, and what skills.select.regenerate_question produced from it
    — grounded in the same section and concept, never invented by the human
    or by this model. Kept as a growing list on QuestionApproval, oldest
    first, so the full history survives every round; the attempt COUNT that
    review.MAX_QUESTION_REGENERATIONS caps is just this list's length, not a
    separate field to keep in sync.
    """
    reason: str
    previous_question: str
    regenerated_question: str

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v):
        # THE ONE HARD RULE OF THIS STEP: a human requesting a regeneration must
        # say what should change. Rejected rather than defaulted to "" — an
        # empty reason recorded in history would be indistinguishable from a
        # reason that was simply lost, and regenerate_question has nothing
        # useful to hand the model without it.
        if not v or not v.strip():
            raise ValueError("a regeneration reason is required — see "
                             "QuestionApproval's docstring: this is the one "
                             "thing a human actually supplies in this flow")
        return v.strip()


class QuestionApproval(BaseModel):
    """The human gate immediately after a question is surfaced, before any
    teaching work is spent on it.

    A SEPARATE MODEL FROM ShortUnit.status, deliberately. ShortUnit.status
    (draft/audited/approved/rendered/rejected/needs_review) gates a REEL that
    has already been fully built — "should this finished thing reach a
    learner". This gates something much earlier and much cheaper: "is this
    even the right question to spend a reel on". Reusing ShortUnit's states
    would either add reel-shaped states (rendered, needs_review) that make no
    sense for a bare question, or overload "approved" to mean two different
    moments in the pipeline — so this stays its own small model instead.

    NO DIRECT EDITING. edited_question (below) predates regeneration and is
    kept so anything already relying on it still loads, but Step 3's own CLI
    and API never write to it — a human who wants different wording requests
    a REGENERATION instead. That is a deliberate product decision, not a
    missing feature: a human typing a question directly can ask about
    something the section never settles, with nothing downstream positioned
    to catch it before a script gets written for it — exactly what select.py's
    own answer_quote and supportability screen exist to prevent one step
    earlier. Routing every change through review.regenerate (which calls
    skills.select.regenerate_question, the same kind of grounded LLM call
    selection itself used) keeps every question that reaches "approved"
    subject to the same grounding rules as the ones selection produced.
    """
    #: "regenerating" is a TRANSIENT, CALLER-SET state, never itself written by
    #: review.regenerate — that function goes straight from whatever status it
    #: is handed to "pending" once the LLM call returns, because it is
    #: synchronous and there is nothing in between for anyone to observe. It
    #: exists for a caller that reflects an in-flight request before awaiting
    #: it — the web UI, optimistically, while its regenerate call is in
    #: flight — so a viewer sees "regenerating…" rather than the stale prior
    #: state for the duration of one request.
    status: Literal["pending", "approved", "rejected", "regenerating"] = "pending"
    note: Optional[str] = None

    #: LEGACY. The human's rewording of the question, from before regeneration
    #: existed. None means nothing here; Step 3 never sets this field — see
    #: "NO DIRECT EDITING" above.
    edited_question: Optional[str] = None

    #: The most recent LLM-regenerated question, once at least one regeneration
    #: has completed. None until then. This is what
    #: QuestionWorkflow.effective_question prefers over edited_question — see
    #: there for the full priority order.
    regenerated_question: Optional[str] = None

    #: Every completed regeneration, oldest first. See RegenerationAttempt.
    regeneration_history: list[RegenerationAttempt] = Field(default_factory=list)

    @property
    def regeneration_attempts(self) -> int:
        """How many regenerations this question has already been through —
        what review.regenerate checks against config.MAX_QUESTION_REGENERATIONS
        before spending another call."""
        return len(self.regeneration_history)


#: What job a framed question does in the reel it becomes. "primary" is the
#: ordinary case: one question drives one reel, matching Script's existing
#: one-question-per-short shape (Script.starts_with_interviewer).
QuestionRole = Literal[
    "primary", "hook", "reinforcement", "misconception_check", "transition",
]


class QuestionFraming(BaseModel):
    """How an APPROVED question (see QuestionWorkflow.approved_topic) is turned
    into the question the reel actually asks a student.

    source_question AND teaching_question ARE BOTH KEPT because they can
    differ: source_question is QuestionWorkflow.effective_question at the
    moment of framing — the human-approved question, whether that is the
    original selection or the latest LLM regeneration — set DETERMINISTICALLY
    by skills.framing.frame_question, never by the framing model itself (see
    that module's _FramingOutput, which has no field for it). teaching_question
    is how it would actually be put to a student on screen — the same idea,
    sometimes reworded for a clearer teaching flow, never a different one. A
    future script step reads teaching_question, never source_question, for
    Script.question.
    """
    source_question: str
    teaching_question: str
    framing_rationale: Optional[str] = None
    role: QuestionRole = "primary"

    @field_validator("source_question", "teaching_question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        # THE SCHEMA'S OWN JOB, same as TeachingStep.not_blank above: a framing
        # with a blank question — source or teaching — is not weaker framing,
        # it is not framing. source_question in particular should never reach
        # here blank (effective_question always falls back to the original
        # Topic.topic, itself required and non-blank), but this is the
        # boundary that makes that a guarantee rather than an assumption.
        if not v or not v.strip():
            raise ValueError("must not be empty — both source_question and "
                             "teaching_question are required")
        return v.strip()

    @field_validator("framing_rationale")
    @classmethod
    def rationale_meaningful_if_present(cls, v: Optional[str]) -> Optional[str]:
        # None ("no rationale was given") is a valid, honest answer. An empty
        # or whitespace-only STRING is not — that is a rationale that claims to
        # exist and says nothing, which is worse than admitting there is none.
        if v is not None and not v.strip():
            raise ValueError("framing_rationale must be meaningful when provided "
                             "— use None instead of a blank string")
        return v.strip() if v is not None else v


#: Deliberately not exhaustive of every possible teaching device, but wide
#: enough to combine: an analogy plus a code example, a process demonstration
#: set against a comparison, or a plain direct_explanation on its own.
TeachingApproachKind = Literal[
    "analogy", "real_world_example", "code", "conceptual_visual",
    "process_demonstration", "comparison", "direct_explanation",
]


class TeachingApproach(BaseModel):
    """The pedagogical strategy chosen for teaching one question.

    `primary` IS REQUIRED AND HAS NO DEFAULT, on purpose. A field that
    defaults to one Kind is a system that quietly reaches for that Kind
    whenever a caller forgets to set it — exactly the "always choose one
    specific style" failure requirement 4 asks this schema to avoid. Nothing
    here favours direct_explanation, or any other kind, over the rest.
    """
    primary: TeachingApproachKind
    #: Other devices used ALONGSIDE primary in the same reel, not instead of it.
    combined_with: list[TeachingApproachKind] = Field(default_factory=list)
    #: Approaches that were considered and not chosen, so a human reviewing the
    #: choice can see the road not taken rather than only the winner.
    alternatives: list[TeachingApproachKind] = Field(default_factory=list)
    rationale: str = ""


class TeachingApproachRegenerationAttempt(BaseModel):
    """One completed LLM regeneration of a TeachingApproach — Step 6's
    counterpart to RegenerationAttempt (question regeneration), and
    DELIBERATELY A SEPARATE MODEL rather than a reused or generic one.

    WHAT MAKES IT DIFFERENT. RegenerationAttempt's previous/regenerated
    fields are question STRINGS; here they are COMPLETE TeachingApproach
    objects — primary, combined_with, alternatives and rationale together.
    That is not incidental: a human's reason ("code is not necessary for this
    concept") can invalidate more than primary alone, since alternatives that
    made sense against a code-centric decision may not make sense against
    whatever replaces it. See TeachingApproachApproval's own "COMPLETE
    DECISIONS ONLY, NEVER A FIELD PATCH".

    KEPT LOGICALLY SEPARATE FROM QUESTION REGENERATION ON PURPOSE — two
    different regeneration histories, two different limits
    (config.MAX_QUESTION_REGENERATIONS vs
    config.MAX_TEACHING_APPROACH_REGENERATIONS), because a reviewer disliking
    the TEACHING DEVICE has nothing to do with how many times the QUESTION
    itself was regenerated, and conflating the two counters would let one
    kind of regeneration silently eat the other's budget.
    """
    reason: str
    previous_approach: TeachingApproach
    regenerated_approach: TeachingApproach

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v):
        # Same rule, same reasoning as RegenerationAttempt.reason_required:
        # a blank reason recorded in history is indistinguishable from one
        # that was lost, and there is nothing useful to hand the model
        # without it.
        if not v or not v.strip():
            raise ValueError("a regeneration reason is required — see "
                             "TeachingApproachApproval's docstring: this is "
                             "the one thing a human actually supplies here")
        return v.strip()


class TeachingApproachApproval(BaseModel):
    """The human gate on the LLM-selected TeachingApproach.

    NO DIRECT OVERRIDES. `override` (below) predates regeneration — it let a
    human hand-write a replacement TeachingApproach, the same shape of
    shortcut QuestionApproval.edited_question once was for questions. Step 6's
    own CLI and API never write it: a human who wants a different approach
    requests a REGENERATION instead (see TeachingApproachRegenerationAttempt),
    which asks the LLM to reconsider the COMPLETE decision — primary,
    combined_with, alternatives and rationale together — grounded in the same
    framing and section, never a field the human fills in by hand. This is
    the exact same product decision QuestionApproval's "NO DIRECT EDITING"
    makes for questions, and for the same reason: a hand-picked `primary` with
    nothing checking it against the concept or the section is precisely the
    unguided choice this whole step exists to replace.

    COMPLETE DECISIONS ONLY, NEVER A FIELD PATCH. There is no way to ask this
    model — or a human — to change just `primary` while leaving
    `combined_with`/`alternatives`/`rationale` as they were, because those
    fields are not independent facts, they are one pedagogical judgement
    expressed in four parts. Regenerating always replaces all four together.
    """
    #: "regenerating" is TRANSIENT AND CALLER-SET, exactly like
    #: QuestionApproval.status's own "regenerating" — review.py's
    #: regenerate_teaching_approach goes straight from whatever status it is
    #: handed to "pending" once the LLM call returns, so nothing in this
    #: file's own code ever leaves a workflow sitting in this state. It exists
    #: for a caller (a UI) that wants to reflect an in-flight request.
    #:
    #: "modified" IS LEGACY, from before regeneration existed, kept only so
    #: data written under the old override-based flow still loads. Step 6's
    #: own code never sets it, and — unlike "approved" — it does NOT satisfy
    #: QuestionWorkflow.approved_teaching_approach's gate; see there.
    status: Literal["pending", "approved", "modified", "regenerating"] = "pending"
    note: Optional[str] = None

    #: LEGACY. A hand-written replacement TeachingApproach, from before
    #: regeneration existed. None means nothing here; Step 6 never sets this
    #: field — see "NO DIRECT OVERRIDES" above.
    override: Optional[TeachingApproach] = None

    #: The most recent LLM regeneration, once at least one has completed.
    #: None until then. This is what
    #: QuestionWorkflow.effective_teaching_approach prefers over `override` —
    #: see there for the full priority order.
    regenerated_approach: Optional[TeachingApproach] = None

    #: Every completed regeneration, oldest first. See
    #: TeachingApproachRegenerationAttempt.
    regeneration_history: list[TeachingApproachRegenerationAttempt] = Field(default_factory=list)

    @property
    def regeneration_attempts(self) -> int:
        """How many regenerations this approach has already been through —
        what review.regenerate_teaching_approach checks against
        config.MAX_TEACHING_APPROACH_REGENERATIONS before spending another
        call."""
        return len(self.regeneration_history)


class TeachingStep(BaseModel):
    """One step of the order a beginner has to meet the idea in.

    THE THREE FIELDS ARE THREE DIFFERENT QUESTIONS and collapsing any two of them
    is what makes a "teaching order" decorative:

        concept           WHAT is introduced here
        purpose           WHY this step has to exist at all
        explanation_goal  WHAT THE LEARNER CAN DO once it has landed

    `purpose` is the one that does the work. A list of concepts in an order is just
    a list — it does not say whether step 2 could be dropped, or why step 1 has to
    come first. "Establish the two parts of a virtual address" says the later steps
    are unreadable without it, and that is a claim a human can disagree with, which
    is the whole point (the same reason skills/strategy.py asks for `must_see`
    rather than a template name).

    All three are REQUIRED and none may be blank. This is the schema's own job —
    "can this be represented" — unlike the quality bar in checks.py, which asks
    whether the sequence is any good. A step missing its purpose is not a weak
    step, it is not a step, and a blank string sails past a plain `str` annotation.
    """
    concept: str
    purpose: str
    explanation_goal: str

    @field_validator("concept", "purpose", "explanation_goal")
    @classmethod
    def not_blank(cls, v: str) -> str:
        # Rejected rather than defaulted, so ask_json's retry shows the model the
        # field it left empty instead of the pipeline carrying a hollow step
        # forward into the script brief.
        if not v or not v.strip():
            raise ValueError("must not be empty — every teaching step needs all "
                             "three of concept, purpose and explanation_goal")
        return v.strip()


class ExamplePlan(BaseModel):
    """Whether this short needs a concrete example, and which one.

    WHY A DECISION AND NOT A LIST. concrete_examples already carried the section's
    own concrete things, and the script brief already asked for one to be named —
    and both are advisory, so the example was the first thing dropped whenever the
    beats got tight. It reads as optional information because that is exactly what
    it was: a bag of nouns with nothing saying whether this particular short is one
    where a worked case IS the explanation, or one where naming a value would be
    decoration. Those are different shorts and nothing in the pipeline told them
    apart.

    So this field makes it a decision with a reason attached, in the same shape as
    everything else the understanding produces: what to use, which step it belongs
    to, and what the learner is supposed to see in it.

    NOT NEEDED IS A FIRST-CLASS ANSWER, and it is the one that keeps this honest.
    Plenty of sections state a relationship and show nothing — a definition, a
    contrast, a rule. Forcing an example there produces an invented one, which is
    the worst failure mode this project has. `not_needed` is how the reading says
    "there is nothing concrete here" without lying, and the script brief is told to
    take it at its word rather than reach for something plausible.
    """

    #: required   the idea does not land without the worked case; the example IS
    #:            the explanation, not an illustration of it
    #: helpful    the example makes it concrete and should be used if the beats
    #:            have room — its absence is not a defect
    #: not_needed the section shows nothing concrete worth naming. DO NOT INVENT ONE.
    need: Literal["required", "helpful", "not_needed"] = "not_needed"

    #: The example itself, copied from the section — normally one of
    #: concrete_examples. Never a tidied-up or generalised version of it, and never
    #: one the reading brought from outside: checks.check_example_plan verifies this
    #: string really occurs in the section, and the plan is dropped when it does not.
    example: str = ""

    #: Which teaching_sequence step this example belongs to, 1-based, so the script
    #: puts it where it does its work. An example landing three beats away from the
    #: idea it makes concrete is a decoration.
    supports_step: Optional[int] = None

    #: What the learner should be able to see BECAUSE of the example. The test of a
    #: real example rather than a mention: if this is empty, nobody decided what it
    #: was for.
    learner_takeaway: str = ""


class ConfusionPlan(BaseModel):
    """Whether this short should correct a learner's wrong belief, and which one.

    WHY A DECISION AND NOT A LIST, the same argument as ExamplePlan and for a worse
    symptom. common_confusions listed what a learner tends to get wrong, and the
    script brief says a question aimed at a misconception is the best kind — so the
    list read as an instruction to find one. That is how a short acquires a "common
    mistake" beat about a mistake nobody makes: the misconception is generated to
    satisfy the shape, and a viewer is warned off an error they were never going to
    commit, using a beat that could have explained the thing.

    Correcting a misconception is powerful and it is not free. It costs a beat out
    of two or three, and it plants the wrong belief in the viewer's head in order
    to knock it down — which is a bad trade unless the belief was already there.
    So this decides whether this particular short is one of those, and `not_needed`
    is the ordinary answer rather than the disappointing one.

    THE CORRECTION IS THE PART THAT MUST BE ON THE PAGE. A misconception is by
    definition something the section does NOT say, so `confusion` cannot be
    required to appear in it — only to be about it. `correct_understanding` is the
    opposite: it is a claim being taught, so it is checked against the section like
    any other claim, and a plan whose correction is not supported there is dropped.
    """

    #: required   the section exists partly to correct this, and a viewer who keeps
    #:            believing it has not understood the section
    #: helpful    clarifying it sharpens the explanation, but the short works
    #:            without spending a beat on it
    #: not_needed introduce no misconception. The ordinary answer.
    need: Literal["required", "helpful", "not_needed"] = "not_needed"

    #: What the learner wrongly believes, in their terms. NOT quoted from the
    #: section — it is the thing the section contradicts — but it must be ABOUT the
    #: section: checks.check_confusion_plan requires its vocabulary to be the
    #: section's, which is what stops a misconception arriving from outside.
    confusion: str = ""

    #: Which teaching_sequence step the clarification belongs beside, 1-based. A
    #: correction dropped in somewhere else interrupts the explanation instead of
    #: sharpening it.
    relates_to_step: Optional[int] = None

    #: What is actually true, supported by THIS section. Verified against the
    #: section text, because this is a claim the short will teach.
    correct_understanding: str = ""

    #: What the learner should hold once the confusion is cleared. Empty means
    #: nobody decided what correcting it was for, and the plan is dropped.
    learner_takeaway: str = ""


class HookPlan(BaseModel):
    """How this short should OPEN, decided from the section rather than from habit.

    WHY THIS IS A DECISION TOO. Beat 1 is the interviewer's question and it is the
    thing a viewer decides on, so it attracts every bad instinct in short-form
    video: the manufactured stake, the invented statistic, the "most people get
    this wrong" that nothing supports. The brief already forbids that in prose, and
    prose is not a constraint — the fix is to decide the opening where the section
    is in view, and to have a `direct` option so "just say what it is" is a
    choice on the list rather than a failure to think of something better.

    THE FOUR OPENINGS, and the section decides which:

      question   a question the section genuinely answers. The default instinct,
                 and right often enough, but not automatically.
      problem    a difficulty the section establishes, which the idea then
                 resolves. Strongest when the section is structured that way —
                 3.1 sets up external fragmentation before paging solves it.
      surprise   a fact or relationship the section states that a learner would not
                 predict. Only when the surprise is genuinely on the page; a
                 surprise the reading manufactured is a lie in the first sentence.
      direct     no hook. Name the thing and start explaining. This is a NORMAL
                 answer, not a shrug — for a definition or a plain mechanism the
                 concept itself is the clearest possible opening, and a hook bolted
                 onto it costs seconds the explanation needed.

    EVERY FORM IS GROUNDED. A hook is the first thing said, in the student's own
    voice, and an ungrounded one poisons the short before it starts — see
    checks.check_hook_plan, which verifies problem and surprise against the section
    as claims, and requires a question's subject to be the section's.
    """

    #: Which of the four openings this short takes.
    kind: Literal["question", "problem", "surprise", "direct"] = "direct"

    #: The hook itself, as an idea rather than as wording — the script writes the
    #: sentence. Empty for `direct`.
    hook: str = ""

    #: Why a learner should care: what the hook makes them want to understand. The
    #: test of a hook that works rather than one that merely opens.
    why_it_matters: str = ""

    #: The concept the hook hands over to — normally core_idea, or the first
    #: teaching step. This is what stops a hook being interesting and irrelevant:
    #: it has to arrive somewhere, and checks.check_hook_plan verifies that
    #: somewhere is the objective rather than a neighbouring topic.
    leads_into: str = ""


class SectionUnderstanding(BaseModel):
    """What one section actually teaches, worked out before anything writes.

    WHY THIS IS ITS OWN STEP
    write_script was handed a topic and a wall of prose and asked to do two jobs in
    one call: work out what the section is really teaching, and write a three-beat
    interview about it. A model asked for two things at once does the answerable
    one — "produce four JSON beats each with a verbatim quote" is a shape it can
    fill, and "what is the single idea here, and what would a learner predict
    wrongly" is not. So the comprehension happened as a side effect of drafting,
    and the beats came out as sentences lifted in document order.

    THIS IS GUIDANCE, NOT EVIDENCE. Every field here is GENERATED TEXT, including
    source_evidence. It says what to explain and how to explain it. It is never a
    citation: the section remains the only legal source of a claim, and every
    source_quote is still matched against the section alone by
    checks.check_source_quotes.

    Every field defaults, so a partial answer from the model still validates and a
    unit written before this existed still loads.
    """

    #: Which section this is a reading of. Carried so a cached understanding can
    #: never be shown against the wrong section.
    section_id: str = ""

    #: The one thing this section teaches, in a sentence.
    core_idea: str = ""

    #: How the short opens, and what the opening hands over to.
    #:
    #: None means no decision was made (older data, or a plan dropped by
    #: checks.check_hook_plan) and the script writes beat 1 the way it always did.
    #: A `direct` plan is a decision — it says the concept IS the opening. See
    #: HookPlan.
    hook_plan: Optional[HookPlan] = None

    #: What has to be said for that idea to land, in TEACHING order — not in the
    #: order the document happens to present it in.
    key_points: list[str] = Field(default_factory=list)

    #: The smallest sequence of steps a beginner has to be walked through to reach
    #: core_idea, each one saying what it introduces, why it is needed, and what
    #: the learner understands afterwards.
    #:
    #: HOW THIS DIFFERS FROM key_points, since they overlap and the difference is
    #: the reason both exist. key_points is a checklist: the things that have to get
    #: said. It has an order, and nothing in it explains the order — so a script
    #: could cover every point and still open on step 3, which is exactly the defect
    #: the script brief spends two pages on. A teaching sequence carries the REASON
    #: for the order in `purpose`, which is what makes it usable as a spine for the
    #: beats rather than as a tick-list.
    #:
    #: NO FIXED TEMPLATE. This is deliberately not hook -> problem -> explanation ->
    #: takeaway, or any other house shape. A comparison is taught by putting both
    #: sides up at once, a process by walking it, a definition by naming the thing
    #: and then distinguishing it — and a step that exists because the template has
    #: a slot for it is padding with a label on. The model picks the order the
    #: concept demands; checks.check_teaching_sequence then verifies it is short,
    #: complete, on the objective, and built from concepts the section supports.
    #:
    #: Defaults empty, like every field here: understandings cached or written
    #: before this field existed must still load, and as_brief() renders exactly
    #: what it rendered before when the list is empty.
    teaching_sequence: list[TeachingStep] = Field(default_factory=list)

    #: The section's own concrete things, named: a selector, a value, a number, a
    #: line of code. This is what stops a script being all generalities.
    concrete_examples: list[str] = Field(default_factory=list)

    #: Which of those examples this short should actually use, and how badly.
    #:
    #: concrete_examples says what is AVAILABLE; this says what to DO about it. The
    #: split matters because a section can show three values of which one is the
    #: explanation and two are incidental, and a list cannot say which. See
    #: ExamplePlan.
    #:
    #: Optional, and None is not the same as not_needed: None means no decision was
    #: made (an older understanding, or a plan dropped by
    #: checks.check_example_plan), and the script step is then given no example
    #: guidance at all — exactly the behaviour it had before this field existed.
    #: not_needed is a decision, and it actively tells the script not to invent one.
    example_plan: Optional[ExamplePlan] = None

    #: What a learner predicts wrongly here. A question aimed at one of these is
    #: worth watching; a question aimed at a definition usually is not.
    common_confusions: list[str] = Field(default_factory=list)

    #: Which of those, if any, this short should actually take on.
    #:
    #: Same relationship as concrete_examples to example_plan: the list is what
    #: EXISTS, this is the decision. None means no decision was made (older data, or
    #: a plan dropped by checks.check_confusion_plan) and the script step gets no
    #: confusion guidance at all; not_needed is a decision, and it tells the script
    #: not to manufacture one. See ConfusionPlan.
    confusion_plan: Optional[ConfusionPlan] = None

    #: Questions this section does NOT answer. The script step is told to stay off
    #: them, because they are exactly where a thin section gets padded from — a
    #: beat that drifts here is one the section was never going to support.
    cannot_answer: list[str] = Field(default_factory=list)

    #: Spans copied out of the section, as grounding for the points above.
    #:
    #: GROUNDING INFORMATION ONLY, and this is the field most likely to be misused.
    #: It is not a pre-approved quote list. The model that copied these may have
    #: tidied or mistyped one, so a beat still has to find its own sentence in the
    #: section and still gets checked against the section. Read it as "here is
    #: where this point came from", never as "here is your citation".
    source_evidence: list[str] = Field(default_factory=list)

    def as_brief(self) -> str:
        """The understanding as the block of text the script step is given.

        Sections with nothing in them are omitted rather than printed empty: a
        heading followed by no bullets reads to a model as "there are none of
        these", which is a claim this step has not made.

        Returns "" when the model gave back nothing usable, which is the signal
        write_script uses to leave its prompt exactly as it was.
        """
        lines: list[str] = []
        if self.core_idea:
            lines += [f"THE ONE IDEA: {self.core_idea}", ""]

        # THE OPENING, before the sequence, because the brief is read in the order
        # the short is delivered: beat 1 is the hook and the answer beats are the
        # sequence. A hook printed after the plan it introduces reads as an
        # afterthought, which is how it gets treated.
        hook = self.hook_plan
        if hook is not None:
            if hook.kind == "direct":
                lines += [
                    "THE OPENING — DIRECT. No hook.",
                    "  The concept is its own best opening here. Beat 1 asks plainly about",
                    "  the thing and the answer starts explaining immediately. Do not",
                    "  manufacture a stake, a scenario, or a surprise to warm the viewer up",
                    "  — there are seconds in this short and the explanation needs them.",
                    "",
                ]
            elif hook.hook:
                lines.append(f"THE OPENING — {hook.kind.upper()}:")
                lines.append(f"  open on:          {hook.hook}")
                if hook.why_it_matters:
                    lines.append(f"  why they care:    {hook.why_it_matters}")
                if hook.leads_into:
                    lines.append(f"  hands over to:    {hook.leads_into}")
                lines.append("  This is the SUBSTANCE of beat 1, not its wording — write the")
                lines.append("  question yourself. It comes from the section, so it may not be")
                lines.append("  sharpened with anything the section does not say.")
                lines.append("")

        # THE SEQUENCE COMES NEXT, directly under the idea it builds to, because it
        # is the spine the beats are meant to follow. Everything below it —
        # examples, confusions, evidence — is material to hang on that spine.
        if self.teaching_sequence:
            lines.append("HOW TO BUILD THE EXPLANATION — the order a beginner needs:")
            for i, step in enumerate(self.teaching_sequence, 1):
                lines.append(f"  step {i}: {step.concept}")
                lines.append(f"    why it is needed:   {step.purpose}")
                lines.append(f"    learner ends up:    {step.explanation_goal}")
            lines.append("")

        if self.key_points:
            # TWO HEADINGS FOR ONE FIELD, chosen by whether a sequence is present.
            #
            # key_points is itself "in teaching order", so printing it under that
            # name directly beneath a teaching sequence hands the model two
            # orderings and no way to tell which one governs — and the one with the
            # reasons attached is the one that should. When there is no sequence
            # (older data, or a reading whose sequence was quarantined) the heading
            # is the original, so those briefs render exactly as they always did.
            lines.append("SUPPORTING POINTS FROM THE SECTION:" if self.teaching_sequence
                         else "WHAT HAS TO BE EXPLAINED, in teaching order:")
            lines += [f"  {i}. {p}" for i, p in enumerate(self.key_points, 1)]
            lines.append("")
        if self.concrete_examples:
            lines.append("THE SECTION'S OWN CONCRETE THINGS — name one of these:")
            lines += [f"  - {e}" for e in self.concrete_examples]
            lines.append("")

        # THE DECISION, printed after the list it is a decision about. A verdict
        # above its own evidence reads as a heading; below it, it reads as the
        # conclusion — and this block is meant to override the "name one of these"
        # invitation directly above it, including by saying not to.
        plan = self.example_plan
        if plan is not None:
            if plan.need == "not_needed":
                lines += [
                    "THE EXAMPLE — NOT NEEDED.",
                    "  This section shows nothing concrete worth building the answer on.",
                    "  Explain it without a worked case. DO NOT INVENT AN EXAMPLE, do not",
                    "  reach for a familiar one from outside, and do not make up a value to",
                    "  look specific. A clear general answer is correct here.",
                    "",
                ]
            elif plan.example:
                label = ("REQUIRED — the idea does not land without it"
                         if plan.need == "required"
                         else "HELPFUL — use it if the beats have room")
                lines.append(f"THE EXAMPLE — {label}:")
                lines.append(f"  use exactly:      {plan.example}")
                if plan.supports_step:
                    step = None
                    if 1 <= plan.supports_step <= len(self.teaching_sequence):
                        step = self.teaching_sequence[plan.supports_step - 1]
                    lines.append(f"  belongs to:       step {plan.supports_step}"
                                 + (f" ({step.concept})" if step else ""))
                if plan.learner_takeaway:
                    lines.append(f"  so the learner sees: {plan.learner_takeaway}")
                lines.append("  Copy it from the section exactly as written. Do not tidy it,")
                lines.append("  generalise it, or swap in one you find neater.")
                lines.append("")
        if self.common_confusions:
            lines.append("WHAT A LEARNER GETS WRONG HERE:")
            lines += [f"  - {c}" for c in self.common_confusions]
            lines.append("")

        # The verdict under its own evidence, exactly as with the example plan, and
        # for the sharper reason: the list above reads as an invitation, and this
        # block is usually there to decline it.
        cplan = self.confusion_plan
        if cplan is not None:
            if cplan.need == "not_needed":
                lines += [
                    "THE MISCONCEPTION — NONE TO CORRECT.",
                    "  Do not introduce one. Do not open with what people get wrong, do not",
                    "  add a 'common mistake' beat, and do not invent a belief in order to",
                    "  knock it down — that plants an error the viewer did not have and",
                    "  spends a beat doing it. Just explain the idea.",
                    "",
                ]
            elif cplan.confusion:
                label = ("REQUIRED — the section exists partly to correct this"
                         if cplan.need == "required"
                         else "HELPFUL — clarify it only if it costs you nothing")
                lines.append(f"THE MISCONCEPTION — {label}:")
                lines.append(f"  learners believe:  {cplan.confusion}")
                if cplan.correct_understanding:
                    lines.append(f"  the section says:  {cplan.correct_understanding}")
                if cplan.relates_to_step:
                    step = None
                    if 1 <= cplan.relates_to_step <= len(self.teaching_sequence):
                        step = self.teaching_sequence[cplan.relates_to_step - 1]
                    lines.append(f"  clarify at:        step {cplan.relates_to_step}"
                                 + (f" ({step.concept})" if step else ""))
                if cplan.learner_takeaway:
                    lines.append(f"  so the learner:    {cplan.learner_takeaway}")
                lines.append("  Correct it inside the explanation, not as an aside. NEVER state")
                lines.append("  the wrong belief on its own — it is only ever said in the same")
                lines.append("  breath as what is actually true.")
                lines.append("")
        if self.cannot_answer:
            lines.append("WHAT THIS SECTION DOES NOT ANSWER — stay out of these:")
            lines += [f"  - {c}" for c in self.cannot_answer]
            lines.append("")
        if self.source_evidence:
            lines.append("WHERE THAT CAME FROM — grounding only, NOT a citation list:")
            lines += [f"  - {q}" for q in self.source_evidence]
            lines.append("")
        return "\n".join(lines).rstrip()


class Beat(BaseModel):
    """One spoken line plus what the viewer sees while it plays.

    NOTE: on_screen length is deliberately NOT validated here. The schema's job is
    "can this be represented", the grader's job is "is this good". If the schema
    rejects an over-long overlay, you get an exception instead of a diagnosis, and
    you can no longer write an eval case for the failure. Enforcement lives in
    checks.check_overlays().
    """
    speaker: Literal["interviewer", "student"]
    line: str
    on_screen: str
    visual_ref: str

    # The span of the source section this beat is a restatement of, copied out
    # character for character. checks.check_source_quotes() then verifies it really
    # occurs in the section, which turns "is this grounded?" from a judgement call
    # into a substring test that costs nothing and cannot be argued with.
    #
    # Optional because the 20 units already in output/ predate the field and must
    # still load. Enforcement lives in the grader, per the note above.
    source_quote: Optional[str] = None


class Script(BaseModel):
    """Output of Skill 2."""
    short_id: str
    question: str
    beats: list[Beat]

    @property
    def word_count(self) -> int:
        return sum(len(b.line.split()) for b in self.beats)

    @property
    def estimated_seconds(self) -> float:
        return round(self.word_count / WORDS_PER_SECOND, 1)

    @field_validator("beats")
    @classmethod
    def starts_with_interviewer(cls, v):
        if not v:
            raise ValueError("script has no beats")
        if v[0].speaker != "interviewer":
            raise ValueError("first beat must be the interviewer asking the question")
        return v


#: How a cell, box or row is being treated by the narration right now.
#:
#: The narration decides emphasis, not the drawing, so a frame names ROLES and the
#: renderer owns the colours. That is what keeps the palette consistent across every
#: short and stops "amber" being spent on three things at once.
Role = Literal["plain", "hero", "lost", "quiet"]


class Cell(BaseModel):
    """One box in a bar, column, split or flow."""
    label: str = ""
    role: Role = "plain"


class Node(BaseModel):
    """One box in a Graph: a service, a step, an idea — anything with connections."""
    label: str = ""
    role: Role = "plain"


class Branch(BaseModel):
    """One direct connection from the root to one other node.

    THE EDGE HAS ITS OWN LABEL, and this is the field the shape exists for: "calls",
    "depends on", "BOOK", "owns" — the CONNECTION is frequently the fact being
    taught ("A depends on B" is a claim about the arrow, not about A or B alone),
    and every existing template draws boxes without ever letting an edge speak.
    """
    node: Node = Field(default_factory=Node)
    #: What the connection MEANS, read at its midpoint. Empty is a valid answer —
    #: not every connection needs naming, and a label invented to fill the field
    #: is worse than none.
    edge_label: str = ""


class Graph(BaseModel):
    """One root and up to a handful of direct connections — dependencies, a
    service calling several others, a concept related to several things at once.

    DELIBERATELY NOT A GENERAL GRAPH. One level deep, one root, no cycles, no
    edges between two branches. General graph layout — arbitrary nodes, arbitrary
    edges, a real layout algorithm to avoid crossings — is a much bigger, open-
    ended problem, and most real explanations do not need it: "the OS depends on
    the driver and the scheduler", "this function calls three others", "a class
    implements two interfaces" are all ONE thing and what it connects to, which is
    exactly what this draws. A concept that genuinely has edges between its
    children, or two levels of depth, does not fit this template — say so rather
    than forcing it in.
    """
    root: Node = Field(default_factory=Node)
    branches: list[Branch] = Field(default_factory=list)


class Slot(BaseModel):
    """One position in a Store — occupied or empty, and possibly in motion.

    A SLOT IS A PLACE, NOT A LABEL, and that distinction is the whole reason this
    model exists. Every other container in this schema is a list of Cells, which
    are labels in boxes, so the only way to draw a stack was three boxes reading
    "Push 1", "Push 2", "Push 3" — the words doing the work a picture should do.
    A slot is a place that may hold something, so an EMPTY one is drawable and a
    full one is drawable and the difference between two frames can be that
    something moved between them.
    """
    #: What occupies this slot. EMPTY STRING MEANS EMPTY, and it is drawn — an
    #: empty slot is how a viewer sees there is room, which is half of what a
    #: stack, a queue or a page table is about.
    label: str = ""
    role: Role = "plain"

    #: Where this slot's contents are in the movement the beat describes.
    #:
    #: "resting"  sitting in the container.
    #: "arriving" entering it on this beat — drawn OUTSIDE the container's open end
    #:            with an arrow in, and animated travelling along that arrow.
    #: "leaving"  being removed on this beat — drawn outside with the arrow out.
    #:
    #: This is the field that makes a concept HAPPEN rather than be labelled. A
    #: push is a slot marked arriving; a pop is the top slot marked leaving.
    state: Literal["resting", "arriving", "leaving"] = "resting"


class Store(BaseModel):
    """A container of slots, with an optional index pointing into it.

    ONE SHAPE FOR EVERY CONCEPT THAT HOLDS THINGS: a stack (vertical, open at the
    top, pointer at the top slot), a queue (horizontal, pointers at both ends), an
    array or page table (horizontal, closed, indexed), a set of memory frames (a
    page arriving into a free one). Adding a template per data structure would be
    ten templates that differ by their labels; this is the one they have in common.
    """
    #: The container's own name — "Stack", "Frames", "Queue". Not a sentence.
    label: str = ""

    #: Vertical grows upward from the base, which is what a stack does. Horizontal
    #: runs left to right from index 0, which is what an array or a queue does.
    orientation: Literal["vertical", "horizontal"] = "vertical"

    slots: list[Slot] = Field(default_factory=list)

    #: The index marker: what it is called, and which slot it points at.
    #:
    #: `pointer_at` may be -1, and that is not an error — it is how an empty stack
    #: is drawn, with `top = -1` marking the space below the base. A pointer that
    #: names a position outside the slots is drawn at the nearest edge rather than
    #: dropped, because "past the end" is a real state a viewer needs to see.
    pointer: Optional[str] = None
    pointer_at: Optional[int] = None

    #: Where this SAME pointer was pointing on the PREVIOUS beat, so a beat
    #: about a pointer CHANGING can draw it disconnecting from its old target
    #: and reconnecting to its new one, instead of only ever appearing already
    #: arrived.
    #:
    #: None means "was not pointing anywhere before this beat, or this is the
    #: first beat" — no retargeting to draw, and pointer_at renders exactly as
    #: it always has. Filled only when it differs from pointer_at: `top`
    #: advancing after a push, `head` moving after an insertion, a node's
    #: `next` being handed from the node before it to the one just inserted
    #: after it. THIS IS THE FIELD THAT MAKES A POINTER CHANGE VISIBLE RATHER
    #: THAN JUST DIFFERENT — the literal "a pointer disconnecting and
    #: reconnecting" the product brief asked for, and layout._state reuses
    #: web/src/AnimatedSvg.tsx's existing slide() to animate it: no new
    #: primitive, because sliding an element from an offset into its drawn
    #: position is already exactly what a retargeting pointer needs.
    pointer_at_previous: Optional[int] = None

    #: Draw the container open at the end things enter by — three sides, not four.
    #: True for a stack or a queue, False for a fixed array whose ends are its own.
    open_end: bool = True


class TableRow(BaseModel):
    cells: list[str] = Field(default_factory=list)
    role: Role = "plain"


class Sample(BaseModel):
    """One line of sample text, DRAWN WITH the style being taught.

    The picture for a typography lesson is the type. A frame that says
    "font-family sets the typeface" in a box is a sentence; a frame showing the word
    "Tourism" set in Lobster next to the same word in Roboto is the thing itself,
    and the difference is visible before a single label is read.

    Only styles a browser can actually render are here — no invented ones — because
    this is drawn as real SVG text and the viewer is looking at the genuine effect.
    """
    text: str = ""
    #: What this sample demonstrates, e.g. 'Roboto' or '36px'. Small, under it.
    label: str = ""
    #: A font-family value. Generic families (serif, sans-serif, monospace, cursive)
    #: always render; named ones need loading — see web/index.html.
    font: Optional[str] = None
    #: Relative size, 1-5. NOT pixels: the renderer owns the canvas and scales these
    #: so the largest fits, which is what makes a size comparison honest at any
    #: number of samples.
    scale: Optional[int] = Field(default=None, ge=1, le=5)
    weight: Optional[int] = Field(default=None, ge=100, le=900)
    italic: bool = False
    decoration: Optional[Literal["underline", "line-through", "overline"]] = None

    #: The text colour, as a CSS keyword or hex — the material's own value.
    #:
    #: THIS FIELD WAS MISSING AND THE FRAME LIED WITHOUT IT. Asked to illustrate
    #: `color: blue` / `color: grey`, the model produced two samples labelled "blue"
    #: and "grey" and, with nowhere to put the colour, both rendered in the default
    #: ink — a picture claiming a difference it did not show. A `preview` frame
    #: exists to display an effect, so every effect it is asked to display needs
    #: somewhere to live; see checks.check_samples_differ, which now fails a frame
    #: whose samples claim to differ and render identically.
    color: Optional[str] = None

    #: The background colour behind this sample, same format. For background-color.
    background: Optional[str] = None

    role: Role = "plain"


class Glyph(BaseModel):
    """One pictogram in an `icons` frame: a drawn thing, with a name under it."""
    #: Which pictogram. See layout.PICTOGRAMS for the list; an unknown name falls
    #: back to a plain box rather than failing the build.
    icon: str = "box"
    label: str = ""
    role: Role = "plain"


class Panel(BaseModel):
    """One side of a `compare` frame: a titled card with a small stack inside.

    Two worlds side by side is a shape these shorts need constantly — contiguous
    versus paged, internal versus external, normal versus italic — and it was being
    forced through `table`, which draws a lookup grid and claims a
    row-for-row correspondence that a comparison does not have.
    """
    title: str = ""
    items: list[Cell] = Field(default_factory=list)
    role: Role = "plain"


#: What KIND of claim a beat makes. This is the axis the visual is chosen on, and
#: naming it explicitly is the whole point of the strategist step.
#:
#: The educational visual rules the reviewer wrote are mostly rules about THIS
#: field — "if the concept describes a process, animate the process"; "if it
#: describes a comparison, show both states simultaneously"; "if it describes data
#: movement, animate the data movement". None of them can be followed by a step
#: that never decides which one it is looking at, and the old pipeline never did:
#: spec_visuals went straight from a sentence to a template name, so the
#: relationship was implicit in a choice rather than a thing that could be checked.
#:
#: Made explicit, it becomes checkable. A beat that says "process" and renders a
#: static "bar" is a detectable mismatch; the same frame with no declared
#: relationship is just a frame.
Relationship = Literal[
    "process",        # a sequence of events -> rule 6, animate it
    "comparison",     # two states weighed against each other -> rule 7, both at once
    "data_movement",  # something travels from A to B -> rule 8, animate the travel
    "hierarchy",      # containment or levels -> rule 9, spatial hierarchy
    "cause_effect",   # this makes that happen -> rule 10, animate cause then effect
    "structure",      # one thing divided into named parts, held still
    "effect",         # how something LOOKS; the picture IS the answer
    "quantity",       # a figure is the whole point
]

#: THE AXIS `relationship` DOES NOT COVER: not what KIND of claim a beat makes,
#: but what PHYSICAL SHAPE the thing being shown actually has. Two beats can
#: both be `relationship: process` — a stack filling up, a linked list growing
#: — and still need opposite drawings, because one is slots inside one
#: container and the other is separate objects joined only by a pointer. Before
#: this field existed that distinction lived entirely in visuals.py's prose
#: ("state vs flow are not interchangeable...", "hierarchy vs graph...") with no
#: structured fact to check it against — a real difference the model was asked
#: to get right from a paragraph, every time, with nothing downstream able to
#: tell whether it had.
#:
#: Decided here, at the SAME step that decides `relationship`, and for the same
#: reason: it is a fact about the concept, not a drawing choice, and answering
#: it after a template is already picked is answering it too late to matter.
PhysicalForm = Literal[
    "single_container",  # one physical container, contiguous positions — a
                          # stack, a queue, an array, a fixed set of memory
                          # frames. Slots inside ONE bordered thing.
    "linked_nodes",       # separate objects that only a reference/pointer
                          # relates — a linked list, a graph's edges, a promise
                          # chain. Each one really is somewhere else.
    "nested_levels",      # one thing physically inside or resting on another,
                          # two or more levels — containment or a layered
                          # system (OS above hardware, a folder inside a
                          # folder).
    "flat_parts",         # a root or a whole divided into several NAMED,
                          # NON-NESTED parts, or several distinct things
                          # depending on one shared source — a kernel and the
                          # things that depend on it, an address split into
                          # fields.
    "two_sides",          # exactly two things held up at once to be weighed
                          # against each other.
    "single_object",      # one thing, not a container of several positions —
                          # its own state, its own look, a value changing.
    "not_applicable",     # the claim is a figure, a rendered effect, or
                          # something else this axis does not describe. The
                          # default, and the honest answer when none of the
                          # above is really what is being shown.
]


class BeatStrategy(BaseModel):
    """What ONE beat's frame has to make a viewer see, decided before any template.

    THE STEP THAT WAS MISSING. spec_visuals was asked to do two different jobs in
    one call: decide what the viewer should see, and pick the shape that shows it.
    Asked for both at once it did the second one — a template name is a concrete,
    answerable thing and "what should someone SEE to understand this" is not — so
    the frames came out well-formed and educationally empty. That is the reviewer's
    scoring exactly: visual correctness 9, educational clarity 4.

    Separating them forces the question to be answered in words, in its own field,
    before a template is on the table. The template is then chosen to serve an
    answer that already exists rather than standing in for one.
    """
    ref: str

    #: The ONE idea this beat teaches, in a learner's words. Not the beat's
    #: sentence — the idea under it.
    concept: str

    #: What kind of claim it is. Decides which visual rules apply.
    relationship: Relationship

    #: THE PHYSICAL SHAPE of what must be seen. See PhysicalForm above. Optional
    #: with a safe default so a strategy written before this field existed, or a
    #: caller that has not been updated, still loads and simply is not checked
    #: against it — the same contract every other optional field on this class
    #: already has.
    physical_form: PhysicalForm = "not_applicable"

    #: WHY THIS BEAT NEEDS A PICTURE AT ALL, in one sentence: the specific thing
    #: about this idea that narration alone leaves the viewer guessing at — a
    #: spatial relationship, a simultaneous comparison, a structure words have
    #: to describe serially but a picture shows at once. Not a repeat of
    #: `concept`; the ANSWER to "what would be lost with the sound off and the
    #: screen blank". Optional and empty by default, for the same reason
    #: `physical_form` is: strategies from before this field existed still load.
    why_visual: str = ""

    #: WHAT THE VIEWER MUST SEE — objects, relationships, states. Written as
    #: things on a screen, never as a sentence to print.
    #:
    #: Rule 3 is the test this field exists to pass: the scene must communicate
    #: the concept even if all text is removed. If what is written here stops
    #: making sense once you delete the labels, the strategy is a caption.
    must_see: str

    #: What a viewer would notice changing since the previous beat, with the sound
    #: off. Empty on the first beat.
    changes_from_previous: str = ""

    #: The single object that carries the accent. Exactly one, always.
    focus: str


class VisualStrategy(BaseModel):
    """The composition plan for one short, before any of it is drawn."""

    #: What the whole short is a picture OF — the one subject every frame develops.
    subject: str
    beats: list[BeatStrategy] = Field(default_factory=list)

    def by_ref(self) -> dict[str, BeatStrategy]:
        return {b.ref: b for b in self.beats}


class VisualStrategyRegenerationAttempt(BaseModel):
    """One completed LLM regeneration of a VisualStrategy — Step 11's
    counterpart to TeachingApproachRegenerationAttempt, one stage later, and
    DELIBERATELY A SEPARATE MODEL for the same reason that one is: the
    previous/regenerated fields here are COMPLETE VisualStrategy objects —
    `subject` and every beat's full BeatStrategy — not a patch to one beat,
    because a human's reason ("beat 2 shows code, this approach was not
    code") can call the WHOLE composition's shape into question, not only
    the beat it names.

    KEPT LOGICALLY SEPARATE FROM QUESTION AND TEACHING-APPROACH REGENERATION
    ON PURPOSE — its own history, its own limit
    (config.MAX_VISUAL_PLAN_REGENERATIONS), because a reviewer unhappy with
    the VISUAL PLAN has nothing to do with how many times the QUESTION or the
    TEACHING DEVICE were regenerated, and conflating the counters would let
    one kind of regeneration silently eat another's budget.
    """
    reason: str
    previous_strategy: VisualStrategy
    regenerated_strategy: VisualStrategy

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v):
        # Same rule, same reasoning as TeachingApproachRegenerationAttempt's
        # own validator: a blank reason recorded in history is
        # indistinguishable from one that was lost, and there is nothing
        # useful to hand the model without it.
        if not v or not v.strip():
            raise ValueError("a regeneration reason is required — see "
                             "VisualPlanApproval's docstring: this is the "
                             "one thing a human actually supplies here")
        return v.strip()


class VisualPlanApproval(BaseModel):
    """The human gate on the visual plan (VisualStrategy) for one reel —
    Step 11's counterpart to TeachingApproachApproval, one stage later, and
    the SAME SHAPE: approve what stands, or request a complete LLM
    regeneration with a reason. There is no third action.

    NO DIRECT EDITING. `override` (below) predates regeneration in this
    file's other approval models and follows the identical convention: Step
    11's own CLI and API never write it. A human who wants a different
    visual plan requests a REGENERATION instead (see
    VisualStrategyRegenerationAttempt), which asks the LLM to reconsider the
    COMPLETE plan — `subject` and every beat together — grounded in the
    approved script, the approved teaching approach and the section, never a
    beat a human fills in by hand. Same product decision as
    QuestionApproval's "NO DIRECT EDITING" and
    TeachingApproachApproval's "NO DIRECT OVERRIDES", for the same reason: a
    hand-edited `must_see` with nothing checking it against the concept is
    precisely the unguided change this whole pipeline exists to replace.

    COMPLETE PLANS ONLY, NEVER A BEAT PATCH. There is no way to ask this
    model — or a human — to change just one beat while leaving the rest of
    the composition as it was, because the beats are one continuous
    development (see skills/strategy.py's "BUILD, DO NOT REPEAT") and
    changing one can change what the ones after it are even allowed to show.
    Regenerating always replaces the whole plan.
    """
    #: "regenerating" is TRANSIENT AND CALLER-SET, exactly like
    #: TeachingApproachApproval.status's own "regenerating" — review.py's
    #: regenerate_visual_plan goes straight from whatever status it is
    #: handed to "pending" once the LLM call returns, so nothing in this
    #: file's own code ever leaves a workflow sitting in this state.
    #:
    #: "modified" IS LEGACY, from before regeneration existed, kept only so
    #: data written under the old override-based flow still loads. Step 11's
    #: own code never sets it, and — unlike "approved" — it does NOT satisfy
    #: QuestionWorkflow.approved_visual_strategy's gate; see there.
    status: Literal["pending", "approved", "modified", "regenerating"] = "pending"
    note: Optional[str] = None

    #: LEGACY. A hand-written replacement VisualStrategy, from before
    #: regeneration existed. None means nothing here; Step 11 never sets
    #: this field — see "NO DIRECT EDITING" above.
    override: Optional[VisualStrategy] = None

    #: The most recent LLM regeneration, once at least one has completed.
    #: None until then. This is what
    #: QuestionWorkflow.effective_visual_strategy prefers over `override` —
    #: see there for the full priority order.
    regenerated_strategy: Optional[VisualStrategy] = None

    #: Every completed regeneration, oldest first. See
    #: VisualStrategyRegenerationAttempt.
    regeneration_history: list[VisualStrategyRegenerationAttempt] = Field(default_factory=list)

    @property
    def regeneration_attempts(self) -> int:
        """How many regenerations this plan has already been through — what
        review.regenerate_visual_plan checks against
        config.MAX_VISUAL_PLAN_REGENERATIONS before spending another call."""
        return len(self.regeneration_history)


class Frame(BaseModel):
    """
    One diagram, described as STRUCTURE rather than as coordinates.

    WHY THIS EXISTS
    The model used to emit raw SVG, and the labels overlapped — persistently, on
    every model tried, however the brief was worded. That is not a prompting
    problem: drawing an SVG by hand means doing layout arithmetic in your head
    (does this 27-character label fit inside this 200px box, is there clear space
    between these two <text> elements) with no way to see the result. Three redraw
    attempts guided by checks.svg_problems reduced it and never fixed it, and
    _draw_one kept the frame either way, so broken frames shipped.

    So the model no longer places anything. It chooses a template and supplies the
    words; skills/layout.py computes every coordinate, fits every label to the box
    it belongs to, and reserves a band for anything that cannot fit inside. Labels
    cannot overlap because nothing is ever placed where something else already is.

    The templates are deliberately few. Each one is a shape these shorts actually
    need, and a frame that cannot be said in one of them is a frame that was trying
    to say too much for four seconds of phone screen.
    """
    #: "takeaway" is LEGACY and must not be chosen for new frames — see the
    #: renderer and SPEC_SYSTEM. It stays in the union only so the units already in
    #: output/ still load and can be re-rendered.
    template: Literal["bar", "mapping", "split", "flow", "table", "stat",
                      "code", "compare", "preview", "icons",
                      "hierarchy", "cause_effect", "state", "graph", "analogy",
                      "takeaway"]
    title: str = ""
    #: LEGACY, and no longer drawn. This was "the one supporting line under the
    #: diagram", and what the model actually put in it was the sentence being
    #: spoken — so every frame carried a caption of its own narration, under a
    #: player that already flows that same line word by word. Two copies of the
    #: voice and no picture is the "visuals are just text" complaint in one field.
    #: Kept so old units load; layout.render ignores it.
    note: Optional[str] = None

    #: bar — a row of equal cells, e.g. memory frames.
    cells: list[Cell] = Field(default_factory=list)
    #: bar / mapping — a quiet caption naming the whole row or column.
    cells_title: Optional[str] = None

    #: mapping — two columns with arrows between them, e.g. pages to frames.
    left: list[Cell] = Field(default_factory=list)
    right: list[Cell] = Field(default_factory=list)
    left_title: Optional[str] = None
    right_title: Optional[str] = None

    #: split — one wide bar cut into named parts, e.g. an address.
    parts: list[Cell] = Field(default_factory=list)

    #: flow — steps top to bottom with arrows, e.g. a page fault path.
    steps: list[Cell] = Field(default_factory=list)

    #: flow — which way the steps run. Named to sit next to Store.orientation
    #: rather than for brevity: the two fields mean the same thing on two
    #: different templates, and giving them different names would suggest a
    #: difference in the concept that is not there.
    #:
    #: "vertical" is the original, unbroken behaviour — a column of boxes, one
    #: arrow between each pair, e.g. a page fault path. "horizontal" is the
    #: SAME shape transposed: separate, distinct boxes with a visible gap and a
    #: real drawn arrow between them, left to right. This is what a linked list
    #: needs and a `state` container is the wrong shape for — see
    #: flow_terminator below and skills/visuals.py's `state` vs `flow` contrast.
    #: A stack or a queue is ONE physical container with contiguous slots
    #: (`state`); a linked list is SEPARATE nodes that only a pointer relates,
    #: which this draws as separate boxes rather than one bordered row.
    flow_orientation: Literal["vertical", "horizontal"] = "vertical"

    #: flow — a drawn mark AFTER THE LAST STEP saying the chain stops here, e.g.
    #: "null", "None", "∅". The model's own word — whatever the material or the
    #: narration would call it — never invented by the renderer.
    #:
    #: WHY THIS EXISTS. Before this field, a `flow` chain simply had no more
    #: boxes after the last one — which is indistinguishable from "the artist
    #: stopped drawing" and is exactly how an array's last cell and a linked
    #: list's last node rendered identically once nothing referenced a pointer.
    #: A linked list's last node genuinely POINTS AT NOTHING, and that is a real
    #: state a viewer needs to see, the same argument Store.pointer_at = -1
    #: already makes for an empty stack: "no more" has to be drawn, not implied
    #: by an edge of the canvas.
    #:
    #: None (the default) draws nothing extra, so a plain sequence — "what
    #: happens on a page fault" — still ends on its last box exactly as before.
    flow_terminator: Optional[str] = None

    #: table — a header row and rows, one of them the hero.
    columns: list[str] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)

    #: stat — one number or term, large.
    value: Optional[str] = None
    caption: Optional[str] = None

    #: code — the material's OWN snippet, one line per Cell, verbatim including its
    #: leading indentation, with the line under discussion as the hero.
    #:
    #: This is the template that was missing, and its absence is most of why the
    #: frames came out as text. Roughly every web-development document in this
    #: project teaches through a code block — `.main-heading { font-family:
    #: "Roboto"; }` — and there was no shape that could show one. With nothing
    #: pictorial to choose, the model laid the narration out as boxes instead, which
    #: is a slide of the voiceover rather than a diagram of the idea.
    code_lines: list[Cell] = Field(default_factory=list)
    #: code — the file or selector the snippet lives in, e.g. "style.css".
    code_caption: Optional[str] = None

    #: compare — two titled cards side by side, each holding its own small stack.
    panels: list[Panel] = Field(default_factory=list)

    #: analogy — which curated real-world noun to fetch a photo for. THE LEFT PANEL.
    #:
    #: Tallied across every frame this pipeline had ever drawn, icons+compare+bar
    #: were 48.5% of all of them — three shapes standing in for a TCP handshake, a
    #: TLS handshake, a CSS cascade and a cache alike, because a stack and a queue
    #: have no template of their own and land on whichever of those three is
    #: nearest. A real-world analogy is the other half of how this pipeline was
    #: asked to teach a container mechanism, and it needs a photo of the real
    #: thing rather than an invented one — see skills/photos.py's hardware set for
    #: why a curated, verified filename beats a runtime search.
    #:
    #: MUST MATCH A KEY IN skills/photos.py's CURATED ANALOGY SET — currently
    #: "stack", "queue", "cache", "recursion", "linked_list", "tree",
    #: "hash_table", "graph" — for the same reason a hardware
    #: `Glyph.icon` is drawn from a fixed list rather than free text: an
    #: unreviewed subject fetched at render time might return whatever Commons
    #: ranks first for the search term, with nobody standing behind the choice.
    #: A subject outside the curated set (or no network right now) renders as a
    #: plain labelled box instead of a photo — see layout._analogy — the same
    #: degrade-gracefully contract `photo_for` already has for the hardware five.
    analogy_subject: Optional[str] = None

    #: analogy — the human sentence STATING the comparison, e.g. "Like a stack of
    #: plates — you can only take from the top."
    #:
    #: MUST READ AS A STATED ANALOGY, NEVER AS A CLAIM THE MATERIAL TEACHES. A
    #: real photo of a physical object needs no citation to depict that object
    #: correctly — the same principle already covers the five hardware photos —
    #: but the WORDS beside it are a different kind of claim than every other
    #: label in this schema: "a spring-loaded plate dispenser" is not something
    #: any section says, and stating it as a fact ("a stack IS a plate
    #: dispenser") would put someone else's metaphor in the material's voice.
    #: "Like X" / "similar to X" keeps it legible as scaffolding brought TO the
    #: lesson rather than a fact taken FROM it.
    analogy_caption: Optional[str] = None

    #: analogy — the RIGHT panel: the section's own mechanism, reusing Panel
    #: rather than inventing a second titled-card shape this file would have to
    #: keep in step with the first one.
    #:
    #: UNLIKE analogy_caption, every label in here is still held to the ordinary
    #: rule — SPEC_SYSTEM's "EVERY FRAME IS A CLAIM ABOUT THE MATERIAL" — because
    #: this side is not illustrative, it is the thing being taught. The photo and
    #: its caption may borrow a plate dispenser from nowhere in the section; this
    #: panel's title and items may not.
    analogy_technical: Optional[Panel] = None

    #: preview — sample text rendered IN the style being taught, so the viewer sees
    #: the effect rather than reading a description of it.
    samples: list[Sample] = Field(default_factory=list)

    #: icons — drawn pictograms with names under them. Pictures, not boxes of words.
    glyphs: list[Glyph] = Field(default_factory=list)
    #: icons — draw arrows between the pictograms, for a sequence rather than a set.
    arrows: bool = True

    #: hierarchy — levels stacked top to bottom, each resting on the one below.
    #:
    #: RULE 9 ("if the concept describes hierarchy, use spatial hierarchy") had no
    #: shape to be expressed in. The nearest pictorial template was `icons`, which
    #: lays its glyphs out IN A ROW — so the layered-system frame the brief quotes
    #: as its worst example, "Users / Applications / Operating System / Hardware",
    #: was drawn as four peers side by side. The arrangement said the opposite of
    #: the concept, and only the reading order of the labels carried the truth.
    levels: list[Cell] = Field(default_factory=list)

    #: The `state` template's container. See Store and Slot: this is the only field
    #: in the Frame that can express a thing HAPPENING rather than a thing being
    #: named, so it is what a process or a state change should be drawn with.
    store: Optional[Store] = None

    #: The `graph` template's root and its direct connections. See Graph: one
    #: root, up to a handful of children, no cycles, one level deep.
    graph: Optional[Graph] = None

    #: cause_effect — the thing that makes something happen, and what happens.
    #:
    #: Rule 10. These went to `flow` before, which draws equal boxes descending a
    #: column and therefore says "a process with two stages" — a different claim
    #: from "this makes that true", and the beat is always about the second one.
    cause: Optional[Cell] = None
    effect: Optional[Cell] = None
    #: cause_effect — the mechanism, written ON the arrow. The one place in this
    #: renderer where the RELATIONSHIP gets named rather than the things it joins.
    mechanism: Optional[str] = None

    #: CROSS-TEMPLATE, FOR HIERARCHY / STATE / FLOW ONLY: the exact label that
    #: belongs in this frame's semantically PRIMARY position, checked against
    #: what actually ended up there.
    #:
    #: layout.py's positioning is deterministic — levels[0] always renders at
    #: the top, steps[0] always renders first, the slot at store.pointer_at
    #: always renders wherever the pointer points — but "always" is a promise
    #: about the RENDERER, not about the DATA. If `levels` is handed
    #: [child, parent] instead of [parent, child], the renderer faithfully
    #: draws the child above the parent, because index 0 IS "the top" by
    #: definition — there was nothing wrong with the drawing, the wrong thing
    #: went into position 0. Nothing before this field could catch that: a
    #: hierarchy frame with two real levels, correctly nested, passes every
    #: existing check, whichever one is on top.
    #:
    #: So this names the intended answer, in the model's own words, for
    #: checks.check_anchor_matches_structure to compare against what is
    #: actually first — the one place a claim about ORDER can be checked
    #: rather than assumed:
    #:   hierarchy  the PARENT's label — must equal levels[0].label, the top.
    #:   flow       the SOURCE/first node's label — must equal steps[0].label,
    #:              where the chain starts.
    #:   state      the label the POINTER should be indicating — must equal
    #:              whatever store.slots[store.pointer_at] actually holds,
    #:              catching a pointer aimed at the wrong slot even though the
    #:              slot it names is a perfectly valid one.
    #: Empty for every other template, and empty here too when the frame's own
    #: order has only one sensible reading (a single level, a single step) —
    #: there being nothing to get backwards is a fine reason to leave it blank.
    anchor_label: str = ""


class VisualScore(BaseModel):
    """What the educational vision judge saw when it LOOKED at one rendered frame.

    Every other score in this file is a judgement about text. This one is a
    judgement about a picture, and the axes are the reviewer's own, kept on their
    0-10 scale rather than squeezed onto EvalReport's 1-5 so the numbers in the
    brief and the numbers in the report are the same numbers.

    TEXT_DEPENDENCY RUNS BACKWARDS AND THAT IS DELIBERATE. It is the only field
    here where high is bad, because it measures a defect rather than a quality:
    how much of this frame's meaning is carried by reading rather than by seeing.
    The reviewer scored the old frames 8/10 on it and marked it BAD. Flipping it to
    a "visual independence" score would have made every axis point the same way and
    made the field stop meaning what it was named for, so it keeps its direction
    and every comparison against it is spelled out at the point of use.
    """
    #: Is the SVG sound — valid, positioned, nothing clipped or overlapping?
    #: The templates make this true by construction, so a low score here is a
    #: renderer bug worth knowing about rather than a redesign to ask for.
    visual_correctness: int = Field(ge=0, le=10)

    #: Could a learner understand the concept from this picture? The gate.
    educational_clarity: int = Field(ge=0, le=10)

    #: HIGH IS BAD. How much of the frame's meaning needs reading. 10 means it is
    #: a slide of words; 0 means the picture would teach with every label erased.
    text_dependency: int = Field(ge=0, le=10)

    #: Does the motion carry the concept, or is it decoration? Scored from the
    #: still plus the motion plan the judge is given in text — see skills/vision.py.
    animation_relevance: int = Field(ge=0, le=10)

    #: Does the visual show the RELATIONSHIP the beat is about?
    concept_communication: int = Field(ge=0, le=10)

    #: Specific, actionable defects. These are what a redesign is shown.
    problems: list[str] = Field(default_factory=list)

    #: Which ref this scored, so a report can be read without its dict key.
    ref: str = ""

    def failures(self) -> list[str]:
        """Every threshold this frame is under, as sentences a redesign can act on.

        Imported late so schema stays importable without config — the thresholds
        are configuration, and this module is what config-free tools parse.
        """
        from . import config
        out = []
        if self.educational_clarity < config.VISION_MIN_CLARITY:
            out.append(
                f"educational_clarity {self.educational_clarity}/10 is below "
                f"{config.VISION_MIN_CLARITY}: a learner could not understand the "
                f"concept from this picture")
        if self.text_dependency > config.VISION_MAX_TEXT_DEPENDENCY:
            out.append(
                f"text_dependency {self.text_dependency}/10 is above "
                f"{config.VISION_MAX_TEXT_DEPENDENCY}: the frame's meaning is carried "
                f"by reading it, not by seeing it")
        return out

    @property
    def passed(self) -> bool:
        return not self.failures()


class Visual(BaseModel):
    """Output of Skills 3 and 4."""
    ref: str
    type: Literal["diagram", "image", "text"]
    spec: str                       # what it should show, in words
    svg: Optional[str] = None       # filled in for type == "diagram"
    image_path: Optional[str] = None

    #: The structured frame this diagram was rendered from, when it was rendered
    #: from one. Optional so units written before templates existed still load, and
    #: kept on the unit so a frame can be re-rendered after a layout fix without
    #: spending another LLM call.
    frame: Optional[Frame] = None

    #: What the strategist decided this frame had to make a viewer see, kept so a
    #: later redesign or a human reviewer can read the intent rather than
    #: reverse-engineering it from the template that was chosen.
    strategy: Optional[BeatStrategy] = None

    #: The vision judge's verdict on the rendered pixels, when one was taken.
    #: None means it was not run (no browser, or turned off), which is
    #: deliberately distinct from a zero — see skills/vision.py.
    score: Optional[VisualScore] = None


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class BeatSpan(BaseModel):
    """When one beat starts and stops in the rendered track."""
    start: float
    end: float


class Audio(BaseModel):
    file: str
    duration_seconds: float
    word_timings: list[WordTiming]

    # Recorded per beat by whoever synthesised the track, rather than re-derived
    # downstream from word counts.
    #
    # feed.py used to cut beats by consuming len(beat.line.split()) word timings in
    # order, which silently assumed the spoken text has exactly as many
    # whitespace tokens as the written line. Speaking the text conversationally
    # breaks that assumption the moment it rewrites "a — b" as "a, b", and the
    # penalty is every later beat drifting by one word. The synthesiser knows each
    # beat's real boundaries because it renders them one at a time, so it says so
    # here. Optional: tracks made before this field existed fall back to the
    # word-count estimate.
    beat_spans: list[BeatSpan] = []


class EvalReport(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    pace: int = Field(ge=1, le=5)
    diagram_correct: bool
    # Whether the answer delivers what the question asked. Defaults True so the 20
    # units judged before this field existed still load.
    question_answered: bool = True
    problems: list[str] = []

    @property
    def passed(self) -> bool:
        return (
            self.faithfulness >= 4
            and self.clarity >= 4
            and self.pace >= 3
            and self.diagram_correct
            and self.question_answered
        )


class ShortUnit(BaseModel):
    """The complete artifact. This is what Remotion renders."""
    short_id: str
    session_id: str
    source_section_id: str
    question: str
    estimated_seconds: float
    beats: list[Beat]
    visuals: dict[str, Visual]
    audio: Optional[Audio] = None
    eval: Optional[EvalReport] = None

    #: What SKILL 1b understood about the source section before the script existed.
    #:
    #: RECORDED SO IT CAN BE READ, on the same terms as vision_scores below. The
    #: understanding is computed once per short and was otherwise a thing that
    #: happened inside one process and vanished — which makes "was this reel weak
    #: because the section is thin, or because the writer wandered?" a question you
    #: could only answer by paying for the reading again.
    #:
    #: Nothing downstream consumes it yet. skills/script.py's prompt is unchanged;
    #: wiring it in is a separate change so the judge's scores can attribute the
    #: difference. Optional and None by default, so all 37 units written before this
    #: field existed still load.
    understanding: Optional[SectionUnderstanding] = None
    #: What the vision judge scored each frame, kept instead of thrown away.
    #:
    #: RECORDED, NEVER READ BACK. judge_frames already rasterises every frame and
    #: scores it, the design loop uses those scores to decide on a redesign, and then
    #: they were discarded — so "which of my frames are weak" could only be answered
    #: by paying for the judgement again, one short at a time. Storing it makes that
    #: a question about output/ rather than about the API.
    #:
    #: Nothing downstream consumes this. It is not sent to any model (spec_visuals is
    #: handed `previous` visuals, not the unit), it is not in the feed payload
    #: (feed.collect builds its keys explicitly), and it is not rendered. Optional and
    #: empty by default so every unit written before it still loads.
    vision_scores: dict[str, dict] = Field(default_factory=dict)

    #: "needs_review" is the quarantine state: the short was built and paid for, and
    #: the judge scored it below the bar (see EvalReport.passed). It stays on disk
    #: with its verdict attached so a human can read what was wrong and decide, but
    #: feed.collect keeps it out of the student-facing reel by default. Before this
    #: existed a faithfulness-2 short — one teaching a fact its own section does not
    #: contain — was written as "audited" and appeared in the feed indistinguishable
    #: from a 5.
    status: Literal["draft", "audited", "approved", "rendered", "rejected",
                    "needs_review"] = "draft"
    video_path: Optional[str] = None

    @field_validator("visuals")
    @classmethod
    def every_ref_resolved(cls, v, info):
        beats = info.data.get("beats") or []
        missing = {b.visual_ref for b in beats} - set(v.keys())
        if missing:
            raise ValueError(f"beats reference visuals that don't exist: {sorted(missing)}")
        return v


class QuestionWorkflow(BaseModel):
    """The full human-in-the-loop record for one candidate question, from
    selection through to the final reel:

        QuestionSelection (why this question, shown with its source)
          -> QuestionApproval (human)
          -> QuestionFraming
          -> TeachingApproach (LLM)
          -> TeachingApproachApproval (human)
          -> Script (question-driven)
          -> VisualStrategy
          -> VisualPlanApproval (human)
          -> the ShortUnit that finally gets rendered

    EVERY STAGE PAST SELECTION IS OPTIONAL — the same progressive-fill
    contract SectionUnderstanding's plan fields already use. A workflow
    paused waiting on a human, or one that never advances past selection, is
    a valid, loadable object rather than one carrying placeholder values for
    "not decided yet".

    STEP 3 WIRES IN question_approval: review.py's CLI gate and server.py's
    selection endpoints read and write it (approve / reject / regenerate),
    and run.py's build step reads approved_topic below to decide what may
    proceed. STEP 4 adds framing (skills/framing.py — not yet wired into any
    orchestration path). STEP 5 adds teaching_approach (skills/
    teaching_approach.py — likewise not yet wired in). STEP 6 WIRES IN
    teaching_approach_approval the same way Step 3 wired in question_approval:
    review.py's approve_teaching_approach/regenerate_teaching_approach and
    server.py's /api/teaching-approach/* endpoints read and write it, and
    approved_teaching_approach below is the one gate anything past it should
    read. STEP 8/9/10 add script and visual_strategy (orchestrated by
    shorts/workflow.py's advance()/advance_many()). STEP 11 WIRES IN
    visual_plan_approval THE SAME WAY: review.py's
    approve_visual_plan/regenerate_visual_plan and server.py's
    /api/visual-plan/* endpoints read and write it, and
    approved_visual_strategy below is the one gate a future rendering stage
    should read.
    """
    selection: QuestionSelection
    question_approval: QuestionApproval = Field(default_factory=QuestionApproval)
    framing: Optional[QuestionFraming] = None
    teaching_approach: Optional[TeachingApproach] = None
    teaching_approach_approval: TeachingApproachApproval = Field(
        default_factory=TeachingApproachApproval)
    script: Optional[Script] = None
    visual_strategy: Optional[VisualStrategy] = None
    visual_plan_approval: VisualPlanApproval = Field(default_factory=VisualPlanApproval)

    @property
    def effective_question(self) -> str:
        """
        The question downstream stages should actually use.

        FIXED PRIORITY ORDER, checked in this exact sequence:
          1. question_approval.regenerated_question — the latest LLM
             regeneration, when at least one has completed. This is the ONLY
             way Step 3's own CLI and API ever change the question in use.
          2. question_approval.edited_question — LEGACY COMPATIBILITY ONLY.
             This field predates regeneration; Step 3's own CLI and API never
             write it (see QuestionApproval's "NO DIRECT EDITING"), so it is
             only ever non-empty on a workflow built or loaded from data
             written before regeneration existed. It is read here so that old
             data still resolves to something sensible — never as a second,
             still-live way to edit a question going forward.
          3. selection.topic.topic — the original question selection
             produced, when neither of the above is set.

        selection.topic.topic ITSELF IS NEVER TOUCHED by any of this: it stays
        the traceable record of what was originally selected, however many
        times this property's answer changes underneath it, and however this
        priority is exercised.
        """
        approval = self.question_approval
        if (regenerated := (approval.regenerated_question or "").strip()):
            return regenerated
        if (edited := (approval.edited_question or "").strip()):
            return edited
        return self.selection.topic.topic

    @property
    def approved_topic(self) -> Topic | None:
        """
        The Topic downstream stages (build_one, write_script, ...) should
        receive, with effective_question substituted in — or None if this
        workflow is not currently approved.

        THE ONE GATE. pending, rejected and regenerating all return None here
        — nothing downstream may proceed on any of them, including a question
        that was JUST regenerated: regeneration always lands back on pending
        (see review.regenerate), so a fresh regenerated_question is exactly as
        blocked as the original one was until a human calls review.approve
        again.
        """
        if self.question_approval.status != "approved":
            return None
        return self.selection.topic.model_copy(update={"topic": self.effective_question})

    @property
    def effective_teaching_approach(self) -> Optional[TeachingApproach]:
        """
        The TeachingApproach downstream stages should actually use.

        SAME PRIORITY SHAPE AS effective_question, one stage later:
          1. teaching_approach_approval.regenerated_approach — the latest LLM
             regeneration, when at least one has completed.
          2. teaching_approach_approval.override — LEGACY COMPATIBILITY ONLY,
             from before regeneration existed (see TeachingApproachApproval's
             "NO DIRECT OVERRIDES"). Step 6's own CLI and API never write it.
          3. self.teaching_approach — the LLM's original decision, when
             neither of the above is set.

        UNLIKE effective_question, this can be None: there is no
        schema-guaranteed original to fall back to before
        skills.teaching_approach has ever run on this workflow.
        """
        approval = self.teaching_approach_approval
        if approval.regenerated_approach is not None:
            return approval.regenerated_approach
        if approval.override is not None:
            return approval.override
        return self.teaching_approach

    @property
    def approved_teaching_approach(self) -> Optional[TeachingApproach]:
        """
        THE ONE GATE for the teaching approach, the exact same shape as
        approved_topic one stage earlier. pending, "modified" (legacy),
        regenerating — none of them proceed. Only an explicit "approved"
        status does, and what it hands downstream is
        effective_teaching_approach: the latest regeneration if there was
        one, otherwise the original LLM decision.
        """
        if self.teaching_approach_approval.status != "approved":
            return None
        return self.effective_teaching_approach

    @property
    def effective_visual_strategy(self) -> Optional[VisualStrategy]:
        """
        The VisualStrategy downstream stages (rendering, a future step)
        should actually use.

        SAME PRIORITY SHAPE AS effective_teaching_approach, two stages
        earlier:
          1. visual_plan_approval.regenerated_strategy — the latest LLM
             regeneration, when at least one has completed.
          2. visual_plan_approval.override — LEGACY COMPATIBILITY ONLY, from
             before regeneration existed (see VisualPlanApproval's "NO
             DIRECT EDITING"). Step 11's own CLI and API never write it.
          3. self.visual_strategy — Step 10's own plan_strategy_for_workflow
             output, when neither of the above is set.

        Can be None: there is no schema-guaranteed original to fall back to
        before skills.strategy.plan_strategy_for_workflow has ever run on
        this workflow.
        """
        approval = self.visual_plan_approval
        if approval.regenerated_strategy is not None:
            return approval.regenerated_strategy
        if approval.override is not None:
            return approval.override
        return self.visual_strategy

    @property
    def approved_visual_strategy(self) -> Optional[VisualStrategy]:
        """
        THE ONE GATE for the visual plan, the exact same shape as
        approved_teaching_approach one stage earlier. pending, "modified"
        (legacy), regenerating — none of them proceed. Only an explicit
        "approved" status does, and what it hands downstream (a future
        rendering stage) is effective_visual_strategy: the latest
        regeneration if there was one, otherwise plan_strategy_for_workflow's
        original output.
        """
        if self.visual_plan_approval.status != "approved":
            return None
        return self.effective_visual_strategy

    def invalidate_script(self) -> "QuestionWorkflow":
        """
        A copy of this workflow with `script`, `visual_strategy` and
        `visual_plan_approval` all cleared — everything DERIVED FROM the
        script, reset to its own honest "nothing decided yet" state.

        STEP 8.1's PRIMITIVE, EXTENDED IN STEP 10. `script` (Step 8) is
        derived from THREE things at once — effective_question,
        framing.teaching_question, and approved_teaching_approach, all read
        directly by skills.script.write_script_for_workflow — so it goes
        stale whenever ANY of them changes, not only when the question does.
        `visual_strategy` (Step 10) is ONE LAYER FURTHER DOWN STILL: it is
        built directly from workflow.script itself (see
        skills.strategy.plan_strategy_for_workflow, which reads the approved
        script as its teaching sequence) plus the same approved_teaching_approach
        the script used. So a script going stale makes the visual plan built
        FROM it stale too, by construction — there is no path where `script`
        is cleared and a visual strategy planned from the old one remains
        valid. `visual_plan_approval` goes with it for the same reason
        teaching_approach_approval is reset (not merely left pointing at
        nothing) whenever teaching_approach is cleared: a "pending" or
        "approved" verdict on a plan that no longer exists is not an honest
        state for that field to be in.

        Factored out as its own method because it is shared by two different
        callers with two different SCOPES of invalidation:

          invalidate_downstream (below)          question regenerated: also
                                                  clears framing and
                                                  teaching_approach, because
                                                  BOTH are now decisions about
                                                  a question that no longer
                                                  exists.
          review.regenerate_teaching_approach    only the teaching DEVICE
                                                  regenerated: framing and
                                                  question_approval are still
                                                  valid — only the script (and
                                                  everything built from it) is
                                                  stale.

        A script or visual plan surviving either case would be read by
        anything checking "is workflow.script/.visual_strategy set" as still
        current, and it would not be — exactly the failure invalidate_downstream
        was built to prevent for framing/teaching_approach in Step 7.1, two
        fields later here.
        """
        return self.model_copy(update={
            "script": None,
            "visual_strategy": None,
            "visual_plan_approval": VisualPlanApproval(),
        })

    def invalidate_downstream(self) -> "QuestionWorkflow":
        """
        A copy of this workflow with every decision derived from the question
        cleared — framing, teaching_approach, teaching_approach_approval, and
        script, each reset to its own honest "nothing decided yet" state.

        STEP 7.1's FIX, EXTENDED IN STEP 8.1. framing.teaching_question,
        teaching_approach, and script are all decided FOR one specific
        effective_question — see skills/framing.py, skills/teaching_approach.py
        and skills/script.py's write_script_for_workflow, which all read it
        (or something built from it) directly. Once a question REGENERATION
        changes what effective_question resolves to, every one of them
        becomes a decision about a question that no longer exists, and
        workflow.advance's idempotency contract ("None means not yet
        decided") would otherwise read the OLD ones as still current and
        never regenerate them. script's own clearing is delegated to
        invalidate_script — see there for why it is its own method rather
        than one more key in the update dict below.

        CALLED BY review.regenerate() ALONE, immediately after a question
        regeneration succeeds — see it for why every regeneration invalidates
        unconditionally rather than only when the text happens to differ.
        review.regenerate_teaching_approach calls invalidate_script directly
        instead of this method — see its own docstring for why its
        invalidation is narrower: it never touches the question or framing,
        so it has nothing above its own stage to invalidate here.

        WHAT THIS DOES NOT TOUCH, ON PURPOSE: selection (the original
        QuestionSelection, and its reasons) and question_approval (including
        its own regeneration_history — the record of how the question got
        here). Only what was DERIVED from the question is cleared — which,
        via invalidate_script, now reaches all the way to visual_strategy and
        visual_plan_approval (Step 10) — the question's own record is not.
        """
        return self.invalidate_script().model_copy(update={
            "framing": None,
            "teaching_approach": None,
            "teaching_approach_approval": TeachingApproachApproval(),
        })
