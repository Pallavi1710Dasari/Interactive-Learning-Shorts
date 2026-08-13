"""SKILL 1 — short-selection. Doc in, topics out."""
from ..schema import TopicList, Section
from ..parse import sections_as_prompt_block
from ..llm import ask_json

SYSTEM = """You select which concepts from a software-engineering course session deserve a
30-60 second interview-style video short.

PICK WHAT MATTERS. This is the part people get wrong. A section usually contains
one load-bearing idea plus supporting detail. Choose the load-bearing idea. Ask
yourself: if a learner understood only this, would they understand the section?
If the answer is no, it is not a topic.

A concept qualifies ONLY if all of these are true:
- It can be fully answered in about 45 seconds of speech (roughly 110 words).
- It is self-contained: a learner needs no other short to understand it.
- It has a definite answer, not an open discussion.
- It maps to exactly one section of the source document.
- It explains a MECHANISM or a CONSEQUENCE — why something works, or what follows
  from it. Not what something is called.

REJECT, even when the text supports them:
- Terminology and naming ("what does MSB stand for") — that is a flashcard.
- Restating a definition the section already gives in one line.
- Incidental detail: an example's specific numbers, an aside, a units convention.
- Anything answerable by reading one sentence aloud. If the section answers it
  directly in a single clause, it is too thin for 45 seconds.
- Concepts needing multi-step derivation, or more than one diagram.

Strongly prefer concepts where a learner holds a MISCONCEPTION, because the
interview format is strongest when it corrects a wrong prediction. The best topic
is one where a learner would confidently give the wrong answer.

Return FEWER topics rather than padding with weak ones. Three strong questions
beat eight forgettable ones.

Output JSON:
{"topics":[{"id":"snake_case_id","topic":"the question this short answers",
"why_it_matters":"one sentence","source_section_id":"exact id from the doc",
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
    return repair_section_ids(topics, sections)


def select_topics(sections: list[Section], target: int = 5) -> TopicList:
    return select_topics_with_notes(sections, target)[0]


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
