"""
Offline stand-ins for every LLM call. Enable with SHORTS_STUB=1.

Why this exists: without it there is no way to run the pipeline at all, because
llm.client() raises when ANTHROPIC_API_KEY is missing. So you cannot prove that
parse -> select -> script -> graders -> unit -> JSON -> Remotion -> MP4 works
before you start spending money on it.

Every stub is built out of the source doc's own words, on purpose:
  - the fake Script reuses sentences from the section it was given, so
    check_grounding passes for real rather than by being switched off
  - word counts are trimmed to sit inside the timing budget
  - visuals all come back type="text", which is the V1 cut anyway

A stub run should therefore go green end to end. If it doesn't, the bug is in
your code, not in a prompt — which is exactly what you want a smoke test to tell
you. These are deliberately dumb. Do not tune them; tune the real prompts.
"""
import re

from .schema import MIN_SECONDS, MAX_SECONDS, WORDS_PER_SECOND

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)      # 75
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)      # 150
TARGET_WORDS = 110
MAX_OVERLAY = 8


def fake(model_cls, system: str, user: str):
    """Dispatch on the pydantic class ask_json() was asked to return."""
    name = model_cls.__name__
    if name == "TopicList":
        return model_cls(**_topics(user))
    if name == "Script":
        return model_cls(**_script(user))
    if name == "VisualPlan":
        return model_cls(**_visuals(user))
    if name == "EvalReport":
        return model_cls(faithfulness=5, clarity=5, pace=4,
                         diagram_correct=True, problems=[])
    raise NotImplementedError(
        f"no stub for {name}. Add one in shorts/stubs.py, or unset SHORTS_STUB.")


def _find(pattern: str, text: str, flags=0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _overlay(text: str) -> str:
    """on_screen must stay under the 8-word limit check_overlays() enforces."""
    words = re.sub(r"[^\w\s-]", "", text).split()
    return " ".join(words[:MAX_OVERLAY]) or "detail"


def _topics(user: str) -> dict:
    """One topic per section, read straight out of the prompt block."""
    found = re.findall(r"\[section_id: ([^\]]+)\]\s*(.*)", user)
    topics = []
    for section_id, title in found:
        title = title.strip() or f"section {section_id}"
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]
        topics.append({
            "id": f"stub_{slug}" if slug else f"stub_{section_id.replace('.', '_')}",
            "topic": f"How does {title[0].lower() + title[1:]} work?",
            "why_it_matters": f"Stub topic generated from section {section_id}.",
            "source_section_id": section_id.strip(),
            "difficulty": "medium",
        })
    return {"topics": topics}


def _script(user: str) -> dict:
    """
    Build an interview out of the section's own sentences.

    Sentences are cycled if the section is short, because a real section is often
    under the 75-word floor and we want the timing grader to pass honestly.
    """
    short_id = _find(r"^SHORT_ID:\s*(.+)$", user, re.M) or "stub_short"
    topic = _find(r"^TOPIC:\s*(.+)$", user, re.M) or "How does this work?"
    body = _find(r"SOURCE SECTION.*?\n---\n(.*?)\n---", user, re.S) or topic

    sentences = [s for s in re.split(r"(?<=\.)\s+", " ".join(body.split())) if s.strip()]
    if not sentences:
        sentences = [topic]

    budget = TARGET_WORDS - len(topic.split())
    picked, words, i = [], 0, 0
    while words < budget and len(picked) < 12:
        s = sentences[i % len(sentences)]
        picked.append(s)
        words += len(s.split())
        i += 1

    # Deal the sentences into at most 4 student beats. check_dialogue_shape wants
    # between 2 and 6, so a single-sentence section gets split down the middle.
    if len(picked) < 2:
        half = max(1, len(picked[0].split()) // 2)
        w = picked[0].split()
        chunks = [[" ".join(w[:half])], [" ".join(w[half:])]]
    else:
        per = -(-len(picked) // 4)
        chunks = [picked[j:j + per] for j in range(0, len(picked), per)][:4]

    beats = [{"speaker": "interviewer", "line": topic,
              "on_screen": _overlay(topic), "visual_ref": "v_question"}]
    for n, chunk in enumerate(chunks, start=1):
        line = " ".join(chunk)
        beats.append({"speaker": "student", "line": line,
                      "on_screen": _overlay(line), "visual_ref": f"v_step_{n}"})

    # Last resort: trim the final beat rather than hand the grader a script we
    # already know is over budget.
    total = sum(len(b["line"].split()) for b in beats)
    if total > MAX_WORDS:
        tail = beats[-1]["line"].split()
        keep = max(5, len(tail) - (total - MAX_WORDS) - 1)
        beats[-1]["line"] = " ".join(tail[:keep])

    return {"short_id": short_id, "question": topic, "beats": beats}


def _visuals(user: str) -> dict:
    """Everything comes back as a text card — V1 ships no diagrams."""
    listed = _find(r"Assign a visual to each of:\s*(.+)$", user, re.M) or ""
    refs = re.findall(r"'([^']+)'", listed) or re.findall(r"^\[([a-z0-9_]+)\]", user, re.M)
    return {"visuals": [
        {"ref": ref, "type": "text", "spec": f"Large text card for {ref}."}
        for ref in dict.fromkeys(refs)
    ]}
