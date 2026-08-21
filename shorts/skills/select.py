"""SKILL 1 — short-selection. Doc in, topics out."""
from ..schema import TopicList, Section
from ..parse import sections_as_prompt_block
from ..llm import ask_json

SYSTEM = """You select which questions from a software-engineering course session deserve a
30-60 second interview-style video short.

PICK THE QUESTIONS AN INTERVIEWER ACTUALLY ASKS
These shorts are interview preparation. The test for every topic is: would this
question be asked in a technical interview on this subject, or is it the kind of
thing an examiner marks you down for not knowing? Pick the standard, important,
frequently-asked questions on the material — the ones a learner must be able to
answer out loud.

Prefer, in this order:
1. The question an interviewer opens with on this topic — the direct one.
   "What happens on a page fault?" "Why does paging need a page table?"
2. The comparison or distinction that is routinely asked and routinely confused.
   "How is internal fragmentation different from external?"
3. The mechanism or consequence question — why something works, what follows.
4. The misconception a learner would confidently get wrong.

ASK IT DIRECTLY. A short is not a riddle. The question must be phrased the plain
way an interviewer would say it, and the answer must be the plain, complete answer
to exactly that question. No trick framing, no "which of the following", no
question that needs the answer before you can understand what is being asked.

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

Output JSON:
{"topics":[{"id":"snake_case_id","topic":"the question this short answers",
"why_it_matters":"one sentence","source_section_id":"exact id from the doc",
"answer_quote":"the sentence from that section that answers it, copied verbatim",
"difficulty":"easy|medium|hard"}]}

source_section_id MUST be one of the ids listed under ALLOWED SECTION IDS in the
input, character for character. Do NOT invent finer-grained ids: if a section is
"1.3" then "1.3.2" and "1.3.11" do not exist, even when the prose inside that
section happens to contain a numbered list. Pick the section that contains the
concept."""


def select_topics_with_notes(sections: list[Section],
                             target: int = 5) -> tuple[TopicList, list[str]]:
    """Select topics, and report any section id that had to be corrected."""
    allowed = [s.section_id for s in sections]
    user = (
        f"Select the {target} best topic(s) for shorts from this session. "
        f"Return AT MOST {target}. If only one concept here truly qualifies, "
        f"return just that one — do not pad the list to reach a count.\n\n"
        f"ALLOWED SECTION IDS (source_section_id must be exactly one of these):\n"
        f"{', '.join(allowed)}\n\n"
        f"{sections_as_prompt_block(sections)}"
    )
    topics = ask_json(SYSTEM, user, TopicList, max_tokens=2000, label="select")
    topics, id_notes = repair_section_ids(topics, sections)
    topics, quote_notes = drop_unanswerable(topics, sections)
    return topics, id_notes + quote_notes


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
