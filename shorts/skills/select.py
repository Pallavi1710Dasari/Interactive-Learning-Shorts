"""SKILL 1 — short-selection. Doc in, 8-10 topics out."""
from ..schema import TopicList, Section
from ..parse import sections_as_prompt_block
from ..llm import ask_json

SYSTEM = """You select which concepts from a software-engineering course session deserve a
30-60 second interview-style video short.

A concept qualifies ONLY if all of these are true:
- It can be fully answered in about 45 seconds of speech (roughly 110 words).
- It is self-contained: a learner needs no other short to understand it.
- It has a definite answer, not an open discussion.
- It maps to exactly one section of the source document.

Reject: concepts needing multi-step derivation, anything requiring more than one
diagram to explain, and pure definitions with no mechanism behind them.

Prefer concepts where a learner commonly holds a misconception, because the
interview format is strongest when it corrects a wrong prediction.

Output JSON:
{"topics":[{"id":"snake_case_id","topic":"the question this short answers",
"why_it_matters":"one sentence","source_section_id":"exact id from the doc",
"difficulty":"easy|medium|hard"}]}

source_section_id MUST be copied exactly from a [section_id: X] marker in the input."""


def select_topics(sections: list[Section], target: int = 5) -> TopicList:
    user = (
        f"Select up to {target} topics for shorts from this session.\n\n"
        f"{sections_as_prompt_block(sections)}"
    )
    return ask_json(SYSTEM, user, TopicList, max_tokens=2000, label="select")
