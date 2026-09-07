"""SKILL 1b — read ONE section and work out what it teaches, before anything writes.

WHY THIS IS A SEPARATE CALL
Exactly the reason skills/strategy.py exists for the visuals, applied to the words.
write_script was doing two jobs in one call — comprehend the section, then draft an
interview about it — and a model asked for two things at once does the answerable
one. "Four JSON beats, each with a verbatim quote" is a shape it can fill.
"What is the single idea here, and what would a learner get wrong?" is not, so it
got answered as a side effect of drafting, or not at all. The symptom is a script
whose beats are the section's sentences in the section's own order: correctly
cited, individually true, and not an explanation of anything.

WHAT THIS STEP MUST NOT DO
Write. It produces no lines, no beats and no phrasing to be reused — it says what
is worth explaining and in what order, and the script step still has to say it. It
is also not allowed to become a second source of facts: everything it returns is
generated text, and the section stays the only thing a claim may be quoted from.
See SectionUnderstanding in schema.py, which says that to the reader of the data,
and the CONTENT UNDERSTANDING block in the script brief, which says it to the model.

WHAT IT COSTS
One extra call per SECTION, not per short — the result is keyed on the section, so
several topics filed under one section share one understanding, and so does every
retry of a script. See understanding_for().
"""
import threading

from ..schema import Section, SectionUnderstanding
from ..llm import ask_json
from ..checks import (check_teaching_sequence, check_example_plan,
                      check_confusion_plan, check_hook_plan)


UNDERSTANDING_SYSTEM = """You are reading ONE section of teaching material and
working out what it actually teaches. You write nothing for an audience. Another
step does the explaining; your job is to tell it what is worth explaining.

Answer eight questions about the section, and answer them from the section.

core_idea — the ONE thing this section teaches, in a single sentence.
  Not a summary of everything in it. If the section covers three things, name the
  one the other two exist to support. This is the thing a viewer should still have
  a week later.

key_points — what has to be said for that idea to LAND, in TEACHING order.
  Two to four of them. Teaching order is not document order: a document often
  states a rule, then defines the term the rule uses, then shows the example, and a
  learner needs the definition first. Put them in the order someone would have to
  hear them to follow along. Each point is a short phrase describing what must be
  got across, NOT a sentence to be spoken.
  If the section only supports two, give two. Padding here becomes padding later.

hook_plan — how the short should OPEN, and what the opening hands over to.
  Beat 1 is the first thing heard and the thing a viewer decides on. Choose one of
  four, from what the section actually contains:

    "question"  a question the section genuinely answers. The obvious choice, and
                right often — but not automatically, and not by default.
    "problem"   a difficulty the section establishes, which the idea then resolves.
                Strongest where the section is written that way: one that sets up
                external fragmentation before paging solves it wants this opening.
    "surprise"  a fact or relationship the section states that a learner would not
                predict. Only when the surprise is genuinely on the page.
    "direct"    no hook. Name the thing and start explaining.

  "direct" IS A NORMAL ANSWER. For a definition or a plain mechanism the concept
  itself is the clearest possible opening, and a hook bolted onto it costs seconds
  the explanation needed out of a short that has very few. Choose it whenever the
  section does not hand you a real question, problem or surprise. Do not rank the
  four — pick the one this section supports.

  NEVER MANUFACTURE INTEREST. No invented statistic, scenario, stake or comparison.
  No "you won't believe", "most people get this wrong", "nobody tells you", "the
  secret to" — that language promises something the material does not contain, and
  it is checked and thrown away. If the honest opening is undramatic, it is still
  the right one, and "direct" exists precisely for that case.

  When it is not "direct", also give:
    hook            what to open on, as an IDEA rather than as wording — the
                    writing step composes the sentence. A problem or a surprise is
                    a claim about the material and is checked against the section
                    as one; a question must at least be about this section.
    why_it_matters  what the hook makes the learner want to understand.
    leads_into      the concept it hands over to — normally core_idea or the first
                    teaching step. A hook that is interesting and goes somewhere
                    else is a hook for a different short, and this is checked.

  For "direct", leave the other fields empty.

teaching_sequence — the SMALLEST sequence of steps a beginner has to be walked
  through to end up understanding core_idea. THREE OR FOUR steps, and the number
  is not arbitrary: the short has four or five answer beats, one of which is spent
  landing the takeaway, so three or four steps is exactly what the beats can carry
  one-idea-each. Two is allowed only when the section genuinely supports no more —
  a two-step plan for a five-beat short is how the extra beats get filled with
  restatement, which is the failure the whole length window was reworked to avoid.
  Never more than four; a step that has to share a beat stops being a step.
  Each one is an object with three fields, and they are three different questions:

    concept           what is introduced at this step
    purpose           why this step has to exist — what the next step would be
                      unreadable without
    explanation_goal  what the learner understands once this step has landed

  THE ORDER IS THE ANSWER, so derive it from the concept and from nothing else.
  A process is taught by walking it. A comparison is taught by putting both sides
  up at once, not by explaining one and then the other. A definition is taught by
  naming the thing and then distinguishing it from what it is not. A cause is
  taught by showing the problem before the fix.
  Do NOT reach for a fixed shape. There is no house template here — not
  hook then problem then explanation then takeaway, not context then detail then
  summary, not any other slot list. A step that exists because a template has a
  slot for it is padding wearing a label, and it is obvious in the finished video.

  SMALLEST means what it says. Drop any step that a beginner could skip and still
  follow the next one. If two steps would be understood together, they are one
  step. Two well-chosen steps beat four that include a warm-up and a recap.

  It must stay on core_idea. Every step is either the objective itself or
  something the objective cannot be understood without — not a neighbouring idea,
  however interesting, and nothing from cannot_answer.

  Use the section's OWN concepts and the section's own words for them. A step
  naming something the section never mentions is the failure this field is most
  prone to, because a familiar topic has a familiar teaching order in your head and
  it will not be this section's. If the section does not build to something, do not
  invent the missing rung.

  Worked example, for a section on address translation:
    step 1  concept: "Page number and offset"
            purpose: "Establish the two parts of a virtual address"
            explanation_goal: "Learner understands which part identifies the page
                               and which part identifies the location within it"
    step 2  concept: "Page table lookup"
            purpose: "Show how the page number is translated"
            explanation_goal: "Learner understands that the page number maps to a
                               frame number"
    step 3  concept: "Frame plus offset"
            purpose: "Complete the address translation"
            explanation_goal: "Learner understands how the physical address is formed"
  Note what makes it work: three steps, each unusable without the one before,
  every concept named by the section, and it ends ON the objective rather than on a
  summary of it.

concrete_examples — the section's OWN concrete things, copied as it writes them.
  The selector, the property value, the number, the line of code, the worked case.
  font-family: "Roboto" and 1011 and 36px, not "a font name" and "a binary number"
  and "a size". This field decides whether the finished script is something a
  learner can use or something they nod along to, so look hard for them. If the
  section genuinely shows none, return an empty list rather than inventing a
  tidier example.

example_plan — whether THIS short should be built on a worked example, and which.
  concrete_examples above lists what the section HAS. This decides what to DO about
  it, and it is a real decision with three answers:

    "required"    the idea does not land without the worked case. The example IS
                  the explanation — a learner who hears only the general statement
                  cannot use it. Sections that show a translation, a calculation,
                  a piece of syntax or a before/after are usually this.
    "helpful"     the example makes it concrete and the short is better for it, but
                  the general statement stands on its own.
    "not_needed"  the section shows nothing concrete worth building on. A
                  definition, a contrast or a plain rule often shows nothing.

  ANSWER "not_needed" WHENEVER IT IS TRUE, and do not treat it as a worse answer.
  It is the whole reason this field is a decision instead of a list: the writing
  step is told to trust it, so "not_needed" is what stops it reaching for a
  familiar example from outside the section when the page offers none. Choosing
  "required" for a section that shows nothing forces exactly the invention this
  pipeline exists to prevent.

  When it is "required" or "helpful", also give:
    example            the thing itself, copied from the section EXACTLY as written
                       — normally one of your own concrete_examples. Not a tidied
                       version, not a generalisation ("a font name" instead of
                       font-family: "Roboto"), and never one you know from
                       elsewhere. It is checked against the section, and a plan
                       naming something the section does not contain is thrown away.
    supports_step      which teaching_sequence step it makes concrete, as a number.
    learner_takeaway   what the learner can see BECAUSE of it that they could not
                       see from the general statement. If you cannot say this, the
                       example is a mention and the answer is "not_needed".

  For "not_needed", leave example and learner_takeaway empty.

common_confusions — what a learner predicts WRONGLY here.
  What would someone assume, coming to this cold, that the section corrects? A
  question aimed at a confusion is worth watching; a question aimed at a definition
  usually is not. Zero to three. Only list one the section actually addresses — do
  not invent misconceptions the material never speaks to.

confusion_plan — whether THIS short should correct a wrong belief, and which one.
  common_confusions above lists what a learner tends to get wrong. This decides
  what to DO about it, and again there are three answers:

    "required"    the section exists partly to correct this. A viewer who finishes
                  still believing it has not understood the section.
    "helpful"     clearing it sharpens the explanation, but the short works without
                  spending a beat on it.
    "not_needed"  introduce no misconception at all.

  "not_needed" IS STILL THE ORDINARY ANSWER, though it is a closer call than it
  was. Choose it whenever the section is simply explaining something, which is
  most of the time.
  What has changed is only the price: the short now runs four or five beats rather
  than two or three, so a correction no longer costs a third of the explanation.
  What has NOT changed is the reason to be strict, and it was never mainly about
  cost — correcting a misconception plants the wrong belief in the viewer's head
  in order to knock it down. That is worth doing when the belief was already
  there, and never otherwise. A short that warns against a mistake nobody makes
  has spent a beat teaching an error, and a longer short does not make that
  better. So: pick "required" or "helpful" on the evidence in the section, never
  because there is room.

  When it is "required" or "helpful", also give:
    confusion             what the learner wrongly believes, in their words. It is
                          NOT in the section — that is what makes it a
                          misconception — but it must be ABOUT this section. A
                          misconception you know from the wider topic, about
                          something this page does not discuss, is exactly what
                          this field must not contain, and it is checked.
    correct_understanding what is actually true, SUPPORTED BY THIS SECTION. This is
                          a claim the short will teach, so it is checked against
                          the section like any other claim. If the section does not
                          establish the correction, you do not have a correction —
                          answer "not_needed".
    relates_to_step       which teaching_sequence step it belongs beside, as a
                          number, so the correction sharpens that step instead of
                          interrupting the explanation.
    learner_takeaway      what the learner holds once it is cleared.

  For "not_needed", leave the other fields empty.

cannot_answer — questions this section does NOT answer.
  Things a reader would reasonably want to know after reading it that the section
  itself does not establish: an adjacent mechanism it mentions but never explains,
  the "why" behind a rule it only states, a term it uses and never defines. Be
  specific, and phrase each as a question.
  This list is used to keep the writing step OUT of those places, so it is most
  useful when it names what the section is likely to be padded with — the
  neighbouring ideas that sound like they belong and are not on the page.

source_evidence — spans copied out of the section, VERBATIM, that ground the points
  above. Two to five. Copy character for character; do not tidy them, and do not
  join sentences that are not adjacent. These are for traceability only. Whatever
  you put here, the writing step still has to find its own sentences in the section.

STAY INSIDE THE SECTION
The section is the only thing you know about this subject. Never add a fact it does
not state, never correct it, and never fill a gap with what you know about the
topic. An empty list is a correct answer. A confident wrong one poisons everything
downstream, because the writing step trusts this as a reading of the page.

Output JSON:
{"section_id":"...","core_idea":"...","key_points":["..."],
 "hook_plan":{"kind":"question|problem|surprise|direct","hook":"...",
   "why_it_matters":"...","leads_into":"..."},
 "teaching_sequence":[{"concept":"...","purpose":"...","explanation_goal":"..."}],
 "concrete_examples":["..."],
 "example_plan":{"need":"required|helpful|not_needed","example":"copied from the section",
   "supports_step":1,"learner_takeaway":"..."},
 "common_confusions":["..."],
 "confusion_plan":{"need":"required|helpful|not_needed","confusion":"...",
   "relates_to_step":1,"correct_understanding":"supported by the section",
   "learner_takeaway":"..."},
 "cannot_answer":["..."],"source_evidence":["copied verbatim from the section"]}"""


def understand(section: Section, document: str | None = None,
               model_override: str | None = None) -> SectionUnderstanding:
    """Read one section. Raises if the model call fails — see understanding_for().

    `document` is CONTEXT ONLY and follows the rule it follows in write_script: it
    is there so a term the section inherits from an earlier section is understood
    rather than guessed at. Nothing may be read out of it as a fact about this
    section, because everything this step returns is presented downstream as a
    reading of THIS page.
    """
    user = ""
    if document:
        user += f"""THE FULL READING MATERIAL — CONTEXT ONLY, NOT PART OF THE SECTION
Here so you understand a term the section inherits from earlier. Do not describe
anything out of it. Everything you return must be about the section below.
=============================================================
{document}
=============================================================

"""

    user += f"""THE SECTION TO READ — [{section.section_id}] {section.title}
---
{section.text}
---

Work out what this section teaches. Use "{section.section_id}" as section_id."""

    understanding = ask_json(UNDERSTANDING_SYSTEM, user, SectionUnderstanding,
                             model=model_override,
                             max_tokens=2000, label="understanding")
    # The model is asked for the id and sometimes answers "" or the title. The
    # section it was handed is not in doubt, so this is set rather than trusted —
    # a brief labelled with the wrong section is worse than one labelled with none.
    understanding.section_id = section.section_id

    # THE TEACHING SEQUENCE IS GRADED, AND A BAD ONE IS DROPPED RATHER THAN RE-ASKED.
    #
    # Dropped, because of what the sequence is FOR. Every other field here is
    # consulted; this one is offered to the script step as the spine for its beats,
    # so a sequence that drifted onto a neighbouring idea does not merely fail to
    # help — it steers the script wrong, carrying the authority of a plan. The rest
    # of the reading is still good and is kept; as_brief() then renders exactly what
    # it rendered before this field existed.
    #
    # Not re-asked, because this step is one call and stays one call. The structural
    # faults — a missing field, a blank string — are already caught inside ask_json
    # by TeachingStep's validators, which show the model its own mistake on the
    # budget the call already has. What is left for this grader is judgement about
    # a sequence that is well-formed, and spending another call on it would buy a
    # second opinion at the price of the thing this step was supposed to be cheap
    # about.
    verdict = check_teaching_sequence(understanding, section_text=section.text)
    if not verdict.passed:
        print(f"    ~ teaching sequence [{section.section_id}] dropped — {verdict.reason}")
        understanding.teaching_sequence = []

    # THE EXAMPLE PLAN, on the same terms and for the same reason: dropped, not
    # re-asked. A plan naming something the section does not contain is the one
    # outcome that would be actively harmful downstream — the script step is told
    # to copy the named example verbatim, so an invented one would be laundered
    # into a beat with the authority of a plan. Setting it to None (rather than to
    # not_needed) is the honest state: no decision was made, so the script step
    # gets no example guidance at all and behaves as it did before this field.
    verdict = check_example_plan(understanding, section_text=section.text)
    if not verdict.passed:
        print(f"    ~ example plan [{section.section_id}] dropped — {verdict.reason}")
        understanding.example_plan = None

    # The confusion plan, on identical terms — dropped, not re-asked. The stakes
    # are the highest of the three: the script step is told to state the wrong
    # belief in order to correct it, so a plan built on a misconception from
    # outside the section, or on a correction the section does not make, would put
    # a fabricated error into a viewer's head and then "fix" it with a fabricated
    # fact. None means no decision, so the script writes as it did before this
    # field existed rather than being handed a bad one.
    verdict = check_confusion_plan(understanding, section_text=section.text)
    if not verdict.passed:
        print(f"    ~ confusion plan [{section.section_id}] dropped — {verdict.reason}")
        understanding.confusion_plan = None

    # And the opening, on the same terms. Dropping to None rather than falling back
    # to a `direct` plan is the point: `direct` is a positive decision that the
    # concept is its own best opening, and a hook that failed grounding is evidence
    # of nothing at all. None leaves beat 1 to the script brief, which has always
    # known how to write one.
    verdict = check_hook_plan(understanding, section_text=section.text)
    if not verdict.passed:
        print(f"    ~ hook plan [{section.section_id}] dropped — {verdict.reason}")
        understanding.hook_plan = None

    return understanding


#: Understandings already worked out, keyed on the section's CONTENT.
#:
#: Keyed on the text rather than on section_id, which matters in the server: the
#: same doc_id can be re-uploaded with different words under "3.2", and an
#: id-keyed cache would then hand the script step a reading of a page that no
#: longer exists. Hashing the text makes that impossible — different words are a
#: different key.
_CACHE: dict[tuple[int, int], SectionUnderstanding] = {}

#: A convenience cache for one batch of shorts, not a store. Sections are a few kB
#: each and a long-lived server is handed many documents, so the oldest entries are
#: dropped once it grows past roughly a document's worth of sections.
_CACHE_MAX = 64

#: The cache is read and written from THREADS — server.make_scripts drafts every
#: topic concurrently, one worker per topic. Two things need the lock and neither is
#: theoretical: evicting with `_CACHE.pop(next(iter(_CACHE)))` while another worker
#: is inserting raises "dictionary changed size during iteration", and a whole
#: batch filed under one section would otherwise miss the cache simultaneously and
#: pay for the same reading once per topic — which is the cost this cache exists to
#: avoid, absent on the only path where it matters.
_LOCK = threading.Lock()

#: One lock per section, so a worker that arrives while a reading is in flight waits
#: for it instead of starting a second one. Held across the model call, which is why
#: it must be per-key: a single global lock here would serialise every reading in a
#: batch and hand back the wall clock that drafting concurrently just bought.
_INFLIGHT: dict[tuple[int, int], threading.Lock] = {}


def understanding_for(section: Section, document: str | None = None,
                      quiet: bool = False) -> SectionUnderstanding | None:
    """The understanding for one section, cached, returning None instead of raising.

    TWO THINGS THIS BUYS, and both are why call sites use it rather than understand():

      1. ONE CALL PER SECTION. The script retry loop runs write_script up to three
         times and every attempt is given the SAME understanding — re-reading the
         section because a grader complained about beat 3 would be paying for a
         second opinion on a question that has not changed. Several topics filed
         under one section share it for the same reason.
      2. A FAILED READING MUST NOT LOSE A SHORT. This step improves the brief; it is
         not a dependency of it. write_script has always worked without one and
         still does, so a bad minute on this call returns None and the script is
         written exactly as it was before this step existed — rather than turning
         into a 500 on a path that used to succeed.
    """
    key = (hash(section.text), hash(document or ""))

    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        gate = _INFLIGHT.setdefault(key, threading.Lock())

    with gate:
        # Checked again inside the gate: whoever held it may have been reading this
        # very section, in which case the answer is now on the shelf.
        with _LOCK:
            if key in _CACHE:
                return _CACHE[key]

        try:
            understanding = understand(section, document=document)
        except Exception as e:
            # NOT cached. A failure is a bad minute on one call, not a fact about
            # this section — caching it would make every later short in the batch
            # skip the step for a reason that no longer applies.
            if not quiet:
                print(f"    ! understanding [{section.section_id}]: "
                      f"{type(e).__name__}: {e} — writing the script without it")
            return None

        with _LOCK:
            if len(_CACHE) >= _CACHE_MAX:
                oldest = next(iter(_CACHE))
                _CACHE.pop(oldest)
                # Its gate goes with it, or _INFLIGHT becomes the unbounded thing
                # the cache was bounded to avoid. Dropping the entry is safe while
                # a worker still holds that lock object: it holds a reference, and
                # a later arrival simply creates a fresh gate for a fresh reading.
                _INFLIGHT.pop(oldest, None)
            _CACHE[key] = understanding

    return understanding
