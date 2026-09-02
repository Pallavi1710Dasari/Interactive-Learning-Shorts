"""SKILL 1 — short-selection. Doc in, topics out."""
import re

from pydantic import BaseModel

from .. import config
from ..schema import TopicList, Section
from ..parse import sections_as_prompt_block
from ..llm import ask_json

SYSTEM = """You select which questions from a software-engineering course session deserve a
30-60 second interview-style video short.

YOUR JOB IS TO RANK, NOT TO COLLECT
There are always more answerable questions in a document than there are questions
worth a short. Selecting the answerable ones is easy and it is not the task. The
task is to find THE MOST IMPORTANT ONES — the handful a learner has to be able to
answer out loud, in the order that matters.

So score every topic you return with `importance`, 1 to 5, against this rubric,
and be strict. Inflating the scores defeats the whole step.

  5  The central idea of the material. If a learner understood only one thing from
     this document, this is it. An interviewer asks it directly and often. Missing
     it means not knowing the topic at all.
     "What happens on a page fault?"  "Why does paging need a page table?"
  4  A mechanism, cause, or distinction that is genuinely asked and routinely got
     wrong. Answering it proves understanding rather than recall.
     "How is internal fragmentation different from external?"
     "Why can't the CPU just walk the page table on every access?"
  3  Real but secondary: a consequence, a trade-off, a supporting detail. Worth
     knowing, rarely the question anybody opens with.
  2  A definition of one term or property, looked up in seconds and forgotten just
     as fast. NOT WORTH A SHORT.
  1  Incidental: an example's numbers, an aside, a naming convention. Never.

RETURN 4s AND 5s. A 3 only when there is nothing better left in the material, and
never a 1 or a 2 — drop those instead, even if it means returning fewer topics
than asked for. Three questions a learner will really be asked beat eight
forgettable ones, and a deck padded with 2s is exactly the complaint this step
exists to prevent.

Order the list by importance, highest first.

BANNED: THE YES/NO QUESTION
The question must NOT be answerable with "yes" or "no". This is the most common
way a weak topic gets through, because a yes/no question sounds conversational
and provocative while asking almost nothing:

  BAD   "So does HTML decide how pretty a webpage looks?"
  BAD   "Isn't the <head> element just another heading tag?"
  BAD   "If you have 4 bits, can they only represent 4 possible values?"
  BAD   "Does paging get rid of fragmentation completely?"

Every one of those is really a misconception worth correcting, asked the lazy way.
Ask the real question underneath it instead — the one whose answer is the
explanation, not a verdict:

  GOOD  "What does HTML define on a page, and what does CSS define?"
  GOOD  "What is the <head> element for, and how does it differ from <h1>?"
  GOOD  "How many values can 4 bits represent, and why?"
  GOOD  "Which kind of fragmentation does paging remove, and which does it leave?"

So: start the question with What, Why, How, Which, When or Where. Never with
Is/Are/Do/Does/Can/Will/Would/Should, and never with a conversational lead-in
("So...", "Wait...", "If I..."). No trick framing, no "which of the following", no
question that needs the answer before it can be understood.

ONE QUESTION PER CONCEPT
Give every topic a `concept`: the one idea it is about, as a short noun phrase
("MSB and LSB positions", "page fault handling"). Two topics may not share a
concept. Asking the same thing three ways — "which bit is the MSB", "which end is
the MSB", "in 1010 is the important bit on the left" — produces three shorts a
learner watches once and cannot tell apart, and it crowds out the concepts that
got no short at all. Prefer covering five concepts once to covering two five ways.

THE ANSWER MUST BE IN THE READING MATERIAL — THIS IS THE HARD RULE
The single worst failure of this step is a good-sounding question whose answer is
not in the document. A later step is forbidden from using outside knowledge, so
such a topic becomes a short that either refuses to answer or invents something.

So for EVERY topic you must supply `answer_quote`: the sentence from the section
that answers the question, copied CHARACTER FOR CHARACTER out of the material.

- Copy it, do not retype it from memory, and do not tidy it up. It is checked by
  exact string match and a topic whose quote is not found is DELETED.
- It must be a sentence that STATES the answer. A heading or a question the
  material itself asks is not an answer — "What is a TLB?" is not evidence, the
  sentence explaining what a TLB does is.
- If you cannot find such a sentence, the question is not answerable from this
  material. DROP IT. Do not reach for a sentence that merely shares vocabulary
  with your question; sharing words is not answering.

Ask only what this document answers. A question that is important in the field but
unanswered here is still the wrong question for this deck.

ALSO REJECT:
- Incidental detail: an example's specific numbers, an aside, a units convention.
- Anything needing multi-step derivation, or more than one diagram.
- Anything not answerable in about 45 seconds of speech (roughly 110 words).
- Anything needing another short to make sense.

Pick the section that CONTAINS the answer, not the one whose title sounds closest.

Return FEWER topics rather than padding with weak ones. Three questions a learner
will really be asked beat eight forgettable ones.

Output JSON, ordered by importance, highest first:
{"topics":[{"id":"snake_case_id","topic":"the question this short answers",
"concept":"the one idea it is about, a short noun phrase",
"importance":5,
"why_it_matters":"one sentence",
"source_section_id":"exact id from the doc",
"answer_quote":"the sentence from that section that answers it, copied verbatim",
"difficulty":"easy|medium|hard"}]}

source_section_id MUST be one of the ids listed under ALLOWED SECTION IDS in the
input, character for character. Do NOT invent finer-grained ids: if a section is
"1.3" then "1.3.2" and "1.3.11" do not exist, even when the prose inside that
section happens to contain a numbered list. Pick the section that contains the
concept."""


#: How many more candidates to ask for than will be kept.
#
#: Asking for exactly `target` gets exactly `target` back — a model asked for five
#: returns five whether or not the fifth is any good, because returning four feels
#: like failing the instruction however the prompt is worded. Asking for a few more
#: and then cutting to the best turns "the five best" into a real comparison, and it
#: costs a handful of output tokens on one call, not another call.
OVERSHOOT = 4

#: The schema's upper bound. Asking past it just fails validation.
MAX_CANDIDATES = 12


def select_topics_with_notes(sections: list[Section],
                             target: int = 5) -> tuple[TopicList, list[str]]:
    """
    Select the most important topics, and report everything that was corrected.

    Three passes over one LLM call: the ids have to resolve, the answers have to be
    in the material, and what is left is cut to the most important non-duplicate
    questions. The cutting is deliberately deterministic — a model that has just
    told you a topic is a 2 out of 5 should not also be the thing deciding whether
    a 2 ships.
    """
    allowed = [s.section_id for s in sections]
    candidates = min(target + OVERSHOOT, MAX_CANDIDATES)
    user = (
        f"Find the most important question(s) in this session and return AT MOST "
        f"{candidates} of them, ordered by importance, highest first. Only the top "
        f"{target} will be made into shorts, so this is a ranking task: include a "
        f"topic only if you would defend it as one of the {target} most important "
        f"things in this material. If only one concept here truly qualifies, return "
        f"just that one — do not pad the list to reach a count.\n\n"
        f"ALLOWED SECTION IDS (source_section_id must be exactly one of these):\n"
        f"{', '.join(allowed)}\n\n"
        f"{sections_as_prompt_block(sections)}"
    )
    topics = ask_json(SYSTEM, user, TopicList, max_tokens=3000, label="select")
    topics, id_notes = repair_section_ids(topics, sections)
    topics, quote_notes = drop_unanswerable(topics, sections)
    # Before the cut to `target`, so a dropped topic promotes the next-ranked one
    # rather than leaving the batch short — the overshoot IS the replacement bench.
    topics, screen_notes = drop_unsupported(topics, sections)
    topics, rank_notes = keep_most_important(topics, target)
    return topics, id_notes + quote_notes + screen_notes + rank_notes


#: Below this, a question is not worth a short. See the rubric in SYSTEM.
MIN_IMPORTANCE = 3

#: An unscored topic (an older topics.json, or a model that skipped the field) is
#: treated as ordinary rather than dropped — the field is new and its absence is
#: not evidence of a weak question.
ASSUMED_IMPORTANCE = 3

#: A question opening with one of these is answerable "yes" or "no".
#: Apostrophes are stripped before the lookup, so "isn't" arrives as "isnt".
_YES_NO_OPENERS = {
    "is", "isnt", "are", "arent", "was", "wasnt", "were", "werent",
    "do", "dont", "does", "doesnt", "did", "didnt",
    "can", "cant", "could", "couldnt", "will", "wont", "would", "wouldnt",
    "should", "shouldnt", "has", "hasnt", "have", "havent", "had",
    "am", "must", "shall",
}

#: A question opening with one of these is asking for an explanation, not a
#: verdict, and is never flagged however many auxiliaries appear later in it.
_INTERROGATIVES = {"what", "whats", "why", "how", "which", "when", "where",
                   "who", "whose", "whom"}

#: Conversational lead-ins to look past before judging the opener. "So does HTML
#: decide..." is the same defect as "Does HTML decide...".
_LEAD_INS = {"so", "wait", "but", "and", "ok", "okay", "hmm", "then", "now", "if"}

#: Above this token overlap, two questions are asking the same thing twice.
_DUPLICATE_OVERLAP = 0.7

#: Words that two unrelated questions share anyway, so they must not be what makes
#: a pair look like duplicates.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did", "of", "to",
    "in", "on", "for", "and", "or", "but", "it", "its", "this", "that", "what",
    "why", "how", "which", "when", "where", "you", "your", "i", "if", "so", "just",
    "actually", "really", "with", "at", "by", "from", "as", "be", "been", "can",
    "not", "no", "get", "gets", "make", "makes", "than", "then", "there", "here",
}


def keep_most_important(topics: TopicList, target: int) -> tuple[TopicList, list[str]]:
    """
    Cut a candidate list down to the most important, distinct, properly-asked ones.

    Three defects, all of which validated cleanly before this existed and all of
    which reached the reviewer as finished shorts:

      the forgettable one   "What does the CSS color property specify?" — correct,
                            answerable, cited, and a two-second lookup. Cut by
                            importance.
      the yes/no one        "So does HTML decide how pretty a webpage looks?" — a
                            real misconception asked the lazy way, which produces a
                            short whose answer is "no, and here is the actual
                            thing", wasting the first beat on a verdict.
      the triplet           three shorts asking which end of a binary number the
                            MSB is on. Each is fine; together they are one concept
                            occupying three slots that other concepts needed.

    Nothing is dropped when EVERY candidate fails, for the same reason
    drop_unanswerable keeps its rejects in that case: leaving the user with "no
    topics" and no way to see why is worse than letting them judge a weak list.
    """
    ranked = sorted(
        topics.topics,
        key=lambda t: -(t.importance if t.importance is not None else ASSUMED_IMPORTANCE),
    )

    kept, notes, seen_concepts, seen_questions = [], [], set(), []

    for topic in ranked:
        score = topic.importance if topic.importance is not None else ASSUMED_IMPORTANCE
        question = (topic.topic or "").strip()

        if score < MIN_IMPORTANCE:
            notes.append(f"{topic.id}: dropped, importance {score}/5 — not worth a short")
        elif _is_yes_no(question):
            notes.append(f"{topic.id}: dropped, asks a yes/no question — {question[:60]!r}")
        elif (concept := _norm_concept(topic.concept)) and concept in seen_concepts:
            notes.append(f"{topic.id}: dropped, another topic already covers "
                         f"{topic.concept!r}")
        elif (twin := _near_duplicate(question, seen_questions)) is not None:
            notes.append(f"{topic.id}: dropped, asks the same thing as {twin!r}")
        else:
            kept.append(topic)
            if concept:
                seen_concepts.add(concept)
            seen_questions.append(question)

    if not kept:
        print(f"  ! every candidate failed the importance/duplicate checks "
              f"({len(notes)}) — keeping them all rather than returning nothing")
        for note in notes:
            print(f"    ~ {note}")
        return TopicList(topics=ranked[:target]), notes

    cut = kept[target:]
    for topic in cut:
        score = topic.importance if topic.importance is not None else ASSUMED_IMPORTANCE
        notes.append(f"{topic.id}: not selected, ranked below the top {target} "
                     f"(importance {score}/5)")

    for note in notes:
        print(f"  ! {note}")
    if kept[:target]:
        print(f"  selected {len(kept[:target])} topic(s), most important first:")
        for topic in kept[:target]:
            score = topic.importance if topic.importance is not None else ASSUMED_IMPORTANCE
            print(f"    {score}/5  {topic.topic}")
    return TopicList(topics=kept[:target]), notes


def _is_yes_no(question: str) -> bool:
    """
    Would "yes" answer this?

    Judged on the word that opens the asking clause, and only against closed lists,
    because the cost of a false positive is a good question silently deleted. A
    question that opens with an interrogative — What/Why/How/Which — is never
    flagged, however many auxiliaries appear later in it ("Why does adding one more
    bit double the values?" is a fine question).

    Two shapes, both of which showed up in real output:

      "Does paging get rid of fragmentation?"        the auxiliary opens it
      "If you have 4 bits, can they only hold 4?"    a condition opens it and the
                                                     auxiliary opens the clause
                                                     after the comma

    The second rule only applies when nothing interrogative opens the sentence, so
    "How is this stored, and does the TLB help?" is left alone.
    """
    def words(text: str) -> list[str]:
        return [w.replace("'", "") for w in re.findall(r"[\w']+", text.lower())]

    head = words(question)
    while head and head[0] in _LEAD_INS:
        head.pop(0)
    if not head:
        return False
    if head[0] in _YES_NO_OPENERS:
        return True
    if head[0] in _INTERROGATIVES:
        return False

    _, _, rest = question.partition(",")
    tail = words(rest)
    return bool(tail) and tail[0] in _YES_NO_OPENERS


def _norm_concept(concept: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (concept or "").lower()))


def _near_duplicate(question: str, against: list[str]) -> str | None:
    """The first earlier question asking substantially the same thing, if any."""
    mine = _content_words(question)
    if len(mine) < 3:
        return None                 # too short to judge; let it through
    for other in against:
        theirs = _content_words(other)
        if not theirs:
            continue
        overlap = len(mine & theirs) / min(len(mine), len(theirs))
        if overlap >= _DUPLICATE_OVERLAP:
            return other
    return None


def _content_words(question: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", question.lower())
            if w not in _STOPWORDS and len(w) > 1}


def select_topics(sections: list[Section], target: int = 5) -> TopicList:
    return select_topics_with_notes(sections, target)[0]


#: Below this many words, an "answer" is a fragment rather than a statement.
MIN_ANSWER_QUOTE_WORDS = 4


def drop_unanswerable(topics: TopicList,
                      sections: list[Section]) -> tuple[TopicList, list[str]]:
    """
    Delete topics whose answer is not actually in the reading material.

    The prompt asks for a verbatim answer_quote; this is what makes that a rule
    rather than a suggestion. A question the document does not answer is the most
    expensive kind of defect here — it survives selection, costs a script call and
    four diagram calls, and reaches a reviewer as a short that either refuses or
    quietly invents. Killing it here costs nothing.

    Matched against the WHOLE document, not just the cited section. The material is
    not tidy and an answer often lives in a summary or an FAQ elsewhere, which
    script.py already relies on; requiring the quote to sit in the cited section
    would throw away good topics for a filing mistake. The section id still has to
    resolve — repair_section_ids has run by now — so the topic remains traceable.

    Nothing is dropped when EVERY topic fails. A model that quoted with smart quotes
    or normalised whitespace throughout would otherwise wipe the whole batch and
    leave the user with "no topics" and no way to see why, which is worse than
    letting the downstream graders judge them one at a time.
    """
    from ..checks import _flatten

    document = _flatten(" ".join(s.text for s in sections))
    kept, dropped, notes = [], [], []

    for topic in topics.topics:
        quote = (topic.answer_quote or "").strip()
        if not quote:
            dropped.append((topic, "no answer_quote — cannot show the material answers it"))
        elif len(quote.split()) < MIN_ANSWER_QUOTE_WORDS:
            dropped.append((topic, f"answer_quote is only {len(quote.split())} words"))
        elif _flatten(quote) not in document:
            dropped.append((topic, f"answer_quote is not in the material: {quote[:70]!r}"))
        else:
            kept.append(topic)

    if not kept and dropped:
        print(f"  ! every topic failed the answer_quote check ({len(dropped)}) — "
              f"keeping them all rather than returning nothing. The script graders "
              f"will catch any that really are unanswerable.")
        for topic, why in dropped:
            print(f"    ~ {topic.id}: {why}")
        return topics, [f"{t.id}: unverified answer ({w})" for t, w in dropped]

    for topic, why in dropped:
        notes.append(f"{topic.id}: dropped, {why}")
        print(f"  ! {notes[-1]}")
    return TopicList(topics=kept), notes



# ------------------------------------------------------- the supportability screen
#
# WHY A SECOND SCREEN, WHEN drop_unanswerable ALREADY RUNS
# That one asks "is the answer_quote really in the document" — a PRESENCE check. It
# cannot see the failure that costs the most: a question the material mentions but
# does not SETTLE. The case that prompted this was "When must you use bracket
# notation instead of dot?", whose answer_quote ("Use Dot notation when the key is a
# valid Identifier.") is in the source, verbatim, and whose real answer is not. The
# section never demonstrates dot notation failing on a key with a space, never
# defines "valid identifier", and shows only `undefined` as an outcome. So the script
# had to infer the interesting half, the judge caught it as unfaithful, and the short
# was quarantined AFTER a script call, six diagram calls and a judge call.
#
# Screening here is the cheapest place it can possibly be caught, and it needs no
# replacement machinery: OVERSHOOT already asks for more candidates than are kept, so
# dropping a bad one simply promotes the next-ranked topic. That IS the swap.

#: A question whose topical words are mostly absent from the material is asking about
#: something the material does not discuss. Deliberately loose — this half is the free
#: pass and only has to catch the blunt cases; the model catches the subtle ones.
MAX_FOREIGN_QUESTION_SHARE = 0.5


class _Verdict(BaseModel):
    id: str
    supported: bool
    why: str = ""


class _ScreenReport(BaseModel):
    findings: list[_Verdict]


SCREEN_SYSTEM = """You decide whether a section of reading material actually SETTLES a
question, using only what the section says.

You are not being asked whether the question is a good one, nor whether you know the
answer. You know this subject and that knowledge is exactly what must not be used
here: the video built from this question may state only what the material states, so
a question you can answer from expertise but the section does not settle is the
failure this step exists to catch.

Mark supported = false when answering well would need ANY of:
  * a fact, term or definition the section never gives
  * a demonstration the section never shows — a question about when something FAILS
    needs the section to show it failing, not merely a rule implying it would
  * an example the section does not contain
  * a distinction the section never draws

Mark supported = true when the section states or demonstrates the answer outright,
so a careful writer could answer using only sentences from it.

IT MUST ALSO SUPPORT MORE THAN ONE SENTENCE OF ANSWER, and this half is missed most
often. The format is one question and then TWO OR THREE answer beats, each resting
on a DIFFERENT sentence from the section — so a question the section settles in a
single line is unsupported here even though it is answered. It cannot be split, the
writer pads or repeats to fill the second beat, and the graders reject it. Ask
whether the section gives at least two distinct things to say in answer. If the
honest answer is "one sentence covers it", mark it false.

A WORKED EXAMPLE, from a short this screen was built after. The section states
"Use Dot notation when the key is a valid Identifier." and shows person.firstName,
person["firstName"], person.gender // undefined, and person[a]. It never defines
"valid identifier", never accesses a key containing a space, and never shows dot
notation failing on one.

  QUESTION: "When must you use bracket notation instead of dot?"   -> false

The rule IS stated, so the question looks settled — and it is not. Answering it
usefully means naming which keys force brackets, and that is precisely what the
section leaves to inference. THE SHALLOW HALF BEING STATED IS NOT ENOUGH: judge a
question by whether the material settles the part that makes it worth asking, not
by whether some sentence in it gestures at the topic. A question whose interesting
half is an inference is unsupported however plainly its dull half is written down.

Be strict. Dropping a weak question costs nothing — another candidate takes its
place — while keeping one costs a script, several diagram calls and a judge call
before anybody finds out. When genuinely unsure, mark it false.

Return JSON:
{"findings":[{"id":"<topic id>","supported":true,"why":"<one clause>"}]}
Every id you were given must appear exactly once."""


def drop_unsupported(topics: TopicList,
                     sections: list[Section]) -> tuple[TopicList, list[str]]:
    """
    Drop topics whose cited section cannot settle them without inference.

    Two passes, cheap first. A word-overlap heuristic removes questions about things
    the material never discusses, for free; whatever survives goes to one batched
    model call — one call for the whole candidate list, not one per topic, because
    the judgement is the same shape for each and the section text is shared.

    Nothing is dropped when every topic fails, for the same reason drop_unanswerable
    does the same: a screen that empties the list leaves the user with no topics and
    no way to see why, which is worse than letting the downstream graders decide.
    """
    from ..checks import _flatten, _stems, _is_topical, _grounded

    by_id = {s.section_id: s for s in sections}
    document = " ".join(s.text for s in sections)
    doc_stems = set(_stems(document))

    kept, dropped, notes = [], [], []

    # --- pass 1: free -------------------------------------------------------
    for topic in topics.topics:
        asked = {stem: word for stem, word in _stems(topic.topic or "").items()
                 if _is_topical(word)}
        if not asked:
            kept.append(topic)
            continue
        foreign = [w for stem, w in asked.items() if not _grounded(stem, doc_stems)]
        if len(foreign) / len(asked) > MAX_FOREIGN_QUESTION_SHARE:
            dropped.append((topic, f"asks about {', '.join(sorted(foreign)[:4])}, "
                                   f"which the material never discusses"))
        else:
            kept.append(topic)

    # --- pass 2: one model call over the survivors --------------------------
    if kept and not config.STUB and config.SCREEN_QUESTIONS:
        blocks = []
        for topic in kept:
            section = by_id.get(topic.source_section_id)
            body = (section.text if section else document)[:6000]
            blocks.append(f"### topic id: {topic.id}\n"
                          f"QUESTION: {topic.topic}\n"
                          f"SECTION {topic.source_section_id}:\n{body}")
        user = ("Decide, for each topic below, whether its section settles its "
                "question using only what that section says.\n\n"
                + "\n\n".join(blocks))
        try:
            report = ask_json(SCREEN_SYSTEM, user, _ScreenReport,
                              max_tokens=1500, label="screen")
        except Exception as e:
            print(f"  ! question screen skipped ({type(e).__name__}: {e}) — "
                  f"the downstream graders still apply")
        else:
            verdicts = {v.id: v for v in report.findings}
            survivors = []
            for topic in kept:
                v = verdicts.get(topic.id)
                if v is not None and not v.supported:
                    dropped.append((topic, f"the section does not settle it — {v.why}"))
                else:
                    survivors.append(topic)
            kept = survivors

    if not kept and dropped:
        print(f"  ! every topic failed the supportability screen ({len(dropped)}) — "
              f"keeping them all rather than returning nothing.")
        for topic, why in dropped:
            print(f"    ~ {topic.id}: {why}")
        return topics, [f"{t.id}: unscreened ({w})" for t, w in dropped]

    for topic, why in dropped:
        notes.append(f"{topic.id}: dropped, {why}")
        print(f"  ! {notes[-1]}")
    return TopicList(topics=kept), notes


def repair_section_ids(topics: TopicList, sections: list[Section]) -> tuple[TopicList, list[str]]:
    """
    Snap invented section ids onto real ones, and drop what cannot be saved.

    The model reliably invents sub-section ids: given a doc containing "1.3" it
    returns "1.3.11", because the prose inside that section is itself numbered.
    Every downstream step then fails with "no section with id '1.3.11'", which
    reaches the reviewer as a dead card they can only retry.

    An invented id is not random — it is a real id with extra components on the
    end — so trimming from the right recovers the section the model meant.
    Anything that still does not resolve is dropped rather than shipped: a short
    that cannot cite its source is the one thing this pipeline must not produce.
    """
    valid = {s.section_id for s in sections}
    kept, notes = [], []

    for topic in topics.topics:
        sid = topic.source_section_id.strip()
        if sid in valid:
            kept.append(topic)
            continue

        candidate, trimmed = None, sid
        while "." in trimmed:
            trimmed = trimmed.rsplit(".", 1)[0]
            if trimmed in valid:
                candidate = trimmed
                break

        if candidate:
            notes.append(f"{topic.id}: section {sid} does not exist — using {candidate}")
            kept.append(topic.model_copy(update={"source_section_id": candidate}))
        else:
            notes.append(f"{topic.id}: dropped, nothing matches section {sid!r}")

    if not kept:
        raise ValueError(
            "topic selection cited only sections that do not exist ("
            + ", ".join(t.source_section_id for t in topics.topics)
            + f"). Real sections are: {', '.join(sorted(valid))}. "
            "Retry, or give the material clearer numbered headings."
        )
    for note in notes:
        print(f"  ! {note}")
    return TopicList(topics=kept), notes
