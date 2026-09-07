"""
SKILL 1b — read the section properly, before anybody writes a word of script.

WHERE THIS SITS
    select -> screen -> HUMAN GATE -> find_section -> [ understand ] -> script

WHY IT IS ITS OWN STEP
write_script was doing two jobs in one call. It got a topic and a section and had
to work out what the section teaches AND turn that into interview beats inside a
12-28 second budget. A model asked for two things at once does the answerable one,
and the answerable one is "emit four beats that quote this text": comprehension
happened as a side effect of drafting, was never written down, and could not be
inspected, graded, or reused.

That last word is the cost. The script step retries up to three times against its
graders, and each attempt re-derived its understanding of the section from scratch
— three private, invisible, mutually inconsistent readings of the same fixed text,
paid for three times. Understanding a section is not what the graders are failing,
so it should not be inside the loop that reacts to them.

WHAT IT DELIBERATELY DOES NOT DO
  - It does not write beats. Wording, pacing and the interview shape stay in
    skills/script.py.
  - It does not choose visuals. That is skills/strategy.py, downstream of the
    script, and it needs the beats this step must not invent.
  - It does not re-run the supportability screen. select.drop_unsupported decides
    whether a topic SHIPS; this describes the limits of one that already did.
    Those are different questions and both are worth asking.
  - It does not produce quotable text. See the note on SOURCE_EVIDENCE below.

SOURCE_EVIDENCE IS NOT A QUOTE SUPPLY
checks.check_source_quotes matches a beat's source_quote against the SECTION and
nothing else, on purpose: accepting quotes from anywhere in the document put four
of fifteen shipped shorts at faithfulness 2/5, each teaching a fact its own cited
section did not contain. Every field here is comprehension for a reader, never
citation for a grader. evidence_notes() below reports which evidence lines are
literal so that drift is visible, but it reports — it does not gate.

THE SECTION IS THE ONLY AUTHORITY, AND `document` DEFAULTS TO OFF
write_script takes the whole reading material as vocabulary context, and the
temptation was to mirror that here. It is left off by default because the two
fields that matter most — can_answer and cannot_answer — get WORSE with it. Asked
"does this section settle X" while holding the whole document, a model answers for
the document: it reads X three sections earlier and reports the section can settle
it. That is precisely the cross-section contamination check_source_quotes was
tightened to stop, arriving one step earlier and wearing a label that says
"understood". The parameter exists for a caller that wants vocabulary help and can
live with that trade; the pipeline does not pass it.
"""
from ..schema import Section, SectionUnderstanding, Topic
from ..llm import ask_json


SYSTEM = """You are a curriculum analyst. You read ONE section of software-engineering
course material and write down what it actually teaches, so that a scriptwriter
working after you never has to guess.

You are NOT writing the video. Do not produce dialogue, beats, narration, timings or
visual ideas. Produce understanding.

THE SECTION IS THE ONLY AUTHORITY.
Everything you write must be supported by the section text you are given. You know a
great deal about this subject from elsewhere; none of it belongs here. If the section
is thin, say so in cannot_answer rather than filling the gap from memory. A confident
addition is the one failure mode that makes this whole step worse than not existing,
because the scriptwriter downstream cannot tell your knowledge from the section's.

FIELD BY FIELD

core_concept
  One sentence: what is this topic teaching? Name the thing, not the activity.
  good: "A page table maps virtual page numbers to physical frame numbers."
  bad:  "This section discusses page tables and how they are used."

learning_objective
  One sentence from the LEARNER's side — what they should understand after watching.
  good: "Why a process can use contiguous addresses while its memory is scattered."
  bad:  "Explain the page table." (that is a task, not an understanding)

key_concepts
  The ideas needed to explain core_concept. 2-5 short noun phrases. Not definitions.

prerequisites
  What the student must already know for this to land. Take these from the
  section's own vocabulary — a term it uses without defining is a prerequisite.
  RETURN AN EMPTY LIST if the section is self-contained. Do not invent a syllabus.

how_it_works
  The mechanism, process or relationship — the part that makes this a concept and
  not a definition. 1-3 sentences. If the section only defines a thing and never
  says how it behaves, say that plainly here.

important_facts
  Facts the section supports, in your own words. 2-6 items. Paraphrase is expected;
  the scriptwriter is going to read these to understand, not to copy.

example
  An example the SECTION ITSELF provides — a number, a code line, a walked-through
  case. Use null if it provides none. NEVER invent one. An invented example is the
  most damaging thing you can put in this document, because it looks like evidence.

misconceptions
  Confusions this reel should avoid — but ONLY where the section gives grounds for
  them, e.g. it contrasts two things learners conflate, or corrects an assumption.
  AN EMPTY LIST IS THE RIGHT ANSWER FOR MOST SECTIONS. A padded list makes the reel
  argue with a mistake the learner was never going to make.

can_answer
  What this section clearly settles. Short phrases.

cannot_answer
  What it does NOT establish — adjacent questions a reader might expect it to cover
  and it does not. This is the most useful field you write: it is the honest
  boundary the scriptwriter has to respect. Be specific ("does not say how the
  table is stored"), never generic ("does not cover everything").

source_evidence
  2-5 sentences or clauses FROM THE SECTION that carry the answer, copied as
  closely as you can. These are for grounding and traceability only. They are NOT
  quotes for the script to reuse, and nothing downstream will treat them as such.

Return raw JSON with exactly these keys:
{"core_concept":"...","learning_objective":"...","key_concepts":["..."],
"prerequisites":["..."],"how_it_works":"...","important_facts":["..."],
"example":null,"misconceptions":["..."],"can_answer":["..."],
"cannot_answer":["..."],"source_evidence":["..."]}"""


def understand(topic: Topic, section: Section, document: str | None = None,
               model_override: str | None = None) -> SectionUnderstanding:
    """
    Read one section against one topic and return what it teaches.

    ONE CALL PER TOPIC, NOT PER SCRIPT ATTEMPT. The caller must hold this across
    the script step's retry loop — see the module docstring. Nothing in here
    depends on a draft, so re-running it per attempt buys three identical readings.

    `document` is off by default and the pipeline does not pass it; the module
    docstring explains why the section alone produces better can_answer /
    cannot_answer than the section plus its document.

    Uses MODEL_GENERATOR (ask_json's default) rather than a role of its own. This
    is comprehension of supplied text at a fixed JSON shape, which is the same
    class of work select and script already do on that model; a MODEL_UNDERSTAND
    knob can be split out later if the judge's scores ever argue for it.
    """
    user = f"""TOPIC THIS SHORT WILL ANSWER: {topic.topic}
WHY IT MATTERS: {topic.why_it_matters}
DIFFICULTY AS SELECTED: {topic.difficulty}
"""

    # The evidence sentence selection already verified against this section. It is
    # passed as a POINTER, not as an answer: it tells this step which sentence
    # convinced the selector the question was answerable, which is a strong hint
    # about where the core concept lives. Topic.answer_quote is not modified and
    # stays available to every later step exactly as before.
    if topic.answer_quote:
        user += (f"\nTHE SENTENCE THAT MADE THIS TOPIC ANSWERABLE (already verified\n"
                 f"against the section by the selection step — treat it as a pointer\n"
                 f"to where the answer lives, not as the whole answer):\n"
                 f"  {topic.answer_quote}\n")

    if document:
        user += f"""
THE FULL READING MATERIAL — VOCABULARY ONLY, NEVER A SOURCE OF FACTS
Here so you recognise terms the section inherits from earlier material. You may NOT
take a fact, a number, an example or a code line from it, and you must NOT let it
influence can_answer or cannot_answer — those describe THE SECTION BELOW alone.
=============================================================
{document}
=============================================================
"""

    user += f"""
THE SECTION — this is the authority [{section.section_id}] {section.title}
---
{section.text}
---

Write the understanding. Support everything from the section above. Use null for
example if the section gives no example, and an empty list for misconceptions if the
section gives no grounds for one. Do not write dialogue and do not suggest visuals."""

    return ask_json(SYSTEM, user, SectionUnderstanding,
                    model=model_override,
                    max_tokens=2500, label="understand")


def as_brief(u: SectionUnderstanding) -> str:
    """
    The understanding formatted as a prompt block, for whoever consumes it next.

    Lives here rather than at the call site for the same reason strategy.as_brief
    does: the shape of this document is this module's business, and a consumer that
    formats it itself will drift the moment a field is added.

    NOT WIRED INTO write_script YET. The script step's prompt is unchanged in this
    change set, on purpose — the brain is built and inspectable first, and teaching
    behaviour moves in a separate step where the judge's scores can attribute the
    difference. This function is what that step will call.
    """
    def block(title: str, items: list[str]) -> str:
        if not items:
            return ""
        body = "\n".join(f"  - {i}" for i in items)
        return f"\n{title}\n{body}\n"

    out = (f"CORE CONCEPT: {u.core_concept}\n"
           f"LEARNING OBJECTIVE: {u.learning_objective}\n"
           f"\nHOW IT WORKS\n  {u.how_it_works}\n")
    out += block("KEY CONCEPTS", u.key_concepts)
    out += block("ASSUMED KNOWLEDGE", u.prerequisites)
    out += block("FACTS THE SECTION SUPPORTS", u.important_facts)
    if u.example:
        out += f"\nEXAMPLE FROM THE SECTION\n  {u.example}\n"
    out += block("CONFUSIONS TO AVOID", u.misconceptions)
    out += block("THE SECTION SETTLES", u.can_answer)
    out += block("THE SECTION DOES NOT ESTABLISH — do not claim these", u.cannot_answer)
    if u.source_evidence:
        out += ("\nWHERE THE ANSWER LIVES (orientation only — quote the section "
                "itself, never these lines)\n")
        out += "\n".join(f"  - {e}" for e in u.source_evidence) + "\n"
    return out


#: Evidence shorter than this is a fragment, and a fragment matches by accident.
#: Same threshold and same reasoning as select.MIN_ANSWER_QUOTE_WORDS.
MIN_EVIDENCE_WORDS = 4


def evidence_notes(u: SectionUnderstanding, section: Section) -> list[str]:
    """
    Which source_evidence lines are NOT literally in the section.

    REPORTS, DOES NOT GATE. The temptation is to validate these the way
    check_source_quotes validates a beat and fail the call when they drift, and
    that would be wrong twice over. These lines are explicitly not citations, so a
    paraphrase is legal; and this step is non-fatal by design, so a hard failure
    here would cost a short its script over a formatting preference.

    What it is for: a run that quietly paraphrases everything is a run whose
    understanding has floated off the text, and that is worth seeing in the log
    before it reaches a reviewer as a bad reel. Uses checks._flatten so the
    comparison matches what check_source_quotes would accept.
    """
    from ..checks import _flatten

    haystack = _flatten(section.text)
    notes = []
    for line in u.source_evidence:
        if len(line.split()) < MIN_EVIDENCE_WORDS:
            notes.append(f"evidence too short to verify: {line!r}")
        elif _flatten(line) not in haystack:
            notes.append(f"evidence is paraphrased, not literal: {line[:80]!r}")
    return notes
