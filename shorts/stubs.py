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
from .checks import MAX_ANSWER_WORDS, MIN_ANSWERS, MIN_QUOTE_WORDS

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)      # 45
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)      # 112
# Derived, not a literal: the length window has moved once already, and a hardcoded
# target silently drifts outside it when it moves again.
TARGET_WORDS = (MIN_WORDS + MAX_WORDS) // 2
MAX_OVERLAY = 8

# Read off the graders rather than restated, so tightening a grader cannot leave
# the stub quietly generating output that grader now rejects — which is exactly
# how the free end-to-end run stops being a smoke test.
BEATS = MIN_ANSWERS + 1                              # 4
MAX_BEAT_WORDS = MAX_ANSWER_WORDS - 2                # stay clear of the cap


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
    if name == "VisualStrategy":
        return model_cls(**_strategy(user))
    if name == "VisionReport":
        return model_cls(**_vision(user))
    if name == "SectionUnderstanding":
        return model_cls(**_understanding(user))
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

    # Both labels, because this regex reaches into the real prompt and so it breaks
    # every time that prompt is reworded. When it broke, `body` silently fell back to
    # the topic string, the stub cited a sentence that exists nowhere in the doc, and
    # the free offline run started failing source_quotes — which is the stub earning
    # its keep, but only because the run is checked. Keep both spellings.
    body = (_find(r"THE SECTION THIS SHORT IS FILED UNDER.*?\n---\n(.*?)\n---", user, re.S)
            or _find(r"SOURCE SECTION.*?\n---\n(.*?)\n---", user, re.S)
            or topic)

    sentences = [s for s in re.split(r"(?<=\.)\s+", " ".join(body.split())) if s.strip()]
    if not sentences:
        sentences = [topic]

    # How many beats the section can actually support. check_source_quotes wants a
    # distinct citation per beat (bar one repeat), so a two-sentence section gets
    # three beats, not four — cycling two sentences across four beats is precisely
    # the padding that grader exists to reject, and the stub must not generate what
    # the graders reject.
    spans = _spans(sentences)
    n_beats = max(MIN_ANSWERS, min(BEATS, len(spans) + 1))

    # Fill each beat up to a per-beat word target, cycling the section's sentences
    # when it is short. Built per-beat rather than by dealing a flat list into
    # chunks, because check_dialogue_shape caps a single beat at MAX_ANSWER_WORDS
    # and dealing sentences out blindly produced 44-word beats.
    # PACK TO THE CAP, don't aim at the average.
    #
    # This used to be `budget // n_beats`, an even share of the target — and it
    # undershot the floor once the window moved to 35-50s. The packing below is
    # greedy over whole sentences and stops as soon as the NEXT sentence would
    # cross MAX_BEAT_WORDS, so a beat reliably lands under whatever figure it is
    # given. Handed 19 it produced 17, and five of those plus a short question is
    # 85 words against an 87-word floor: every stub run failed timing three times
    # and gave up, which takes the free end-to-end smoke test offline.
    #
    # Aiming at MAX_BEAT_WORDS instead lets each beat fill as far as whole
    # sentences allow, and the over-budget trim below already handles the other
    # side. `budget` is still computed because that trim reads the same window.
    budget = max(1, TARGET_WORDS - len(topic.split()))
    per_beat = MAX_BEAT_WORDS

    beats = [{"speaker": "interviewer", "line": topic,
              "on_screen": _overlay(topic), "visual_ref": "v_question"}]
    i = 0
    for n in range(1, n_beats + 1):
        chosen, words, first = [], 0, None
        # `tries` bounds the scan; `chosen` cannot, now that a sentence which does
        # not fit is skipped rather than ending the beat.
        tries = 0
        while words < per_beat and tries < len(sentences) * 2:
            s = sentences[i % len(sentences)]
            i += 1
            tries += 1
            if first is None:
                first = s
            if chosen and words + len(s.split()) > MAX_BEAT_WORDS:
                # SKIP, don't stop. Closing the beat here is what made a section's
                # one short sentence into a whole short beat: "Paging removes the
                # requirement for contiguity." is 6 words, the next sentence was 20,
                # 6 + 20 > 22 so the beat ended at 6. Five beats built that way came
                # to 83 words against an 87-word floor, so every stub run failed
                # timing three times and gave up. Trying the next sentence instead
                # lets a short one pair with another short one.
                continue
            chosen.append(s)
            words += len(s.split())

        line = " ".join(" ".join(chosen).split()[:MAX_BEAT_WORDS])
        beats.append({"speaker": "student", "line": line,
                      "on_screen": _overlay(line), "visual_ref": f"v_step_{n}",
                      # Verbatim by construction: the beat is assembled out of the
                      # section's own sentences, so citing one of them is a real
                      # citation and check_source_quotes passes honestly rather
                      # than by being switched off. Cycled through the distinct
                      # spans so no two beats lean on the same one.
                      "source_quote": spans[(n - 1) % len(spans)]})

    # TOP UP TO THE FLOOR — and read this before deciding it is a cheat.
    #
    # The 35-50s window needs 87-125 narration words. Every section in the sample
    # document is 47-78 words, and the beat cap is 22, so there is arithmetically
    # no way to build an honest 87-word script out of one of them: section 3.3 is
    # three sentences of 23, 28 and 12 words, which packs to 82 words at best.
    #
    # That is a TRUE statement about the material, not a bug in the packer, and in
    # the real pipeline it is the correct outcome — select.py's depth test now
    # rejects sections this thin, and a script step that hit the floor by repeating
    # itself would be caught by check_source_quotes' distinctness rule.
    #
    # The stub is the one place it is not the correct outcome, because the stub is
    # fake content whose entire job is to exercise plumbing — parse, grade, assemble,
    # write — for free, with the graders standing in as assertions. A stub that can
    # never clear the floor takes the free end-to-end run offline permanently, and
    # then nothing checks the plumbing at all. So it repeats a sentence to reach the
    # floor, and the repetition is confined to HERE: nothing a model produces gets
    # this treatment, and the distinctness rule still governs the citations.
    total = sum(len(b["line"].split()) for b in beats)
    if total < MIN_WORDS:
        students = [b for b in beats if b["speaker"] == "student"]
        while total < MIN_WORDS and students:
            grew = False
            for b in students:
                have = b["line"].split()
                if len(have) >= MAX_BEAT_WORDS:
                    continue
                extra = sentences[i % len(sentences)].split()
                i += 1
                room = MAX_BEAT_WORDS - len(have)
                if not extra[:room]:
                    continue
                b["line"] = " ".join(have + extra[:room])
                total = sum(len(x["line"].split()) for x in beats)
                grew = True
                if total >= MIN_WORDS:
                    break
            if not grew:
                break

    # Last resort: trim the final beat rather than hand the grader a script we
    # already know is over budget.
    total = sum(len(b["line"].split()) for b in beats)
    if total > MAX_WORDS:
        tail = beats[-1]["line"].split()
        keep = max(5, len(tail) - (total - MAX_WORDS) - 1)
        beats[-1]["line"] = " ".join(tail[:keep])

    return {"short_id": short_id, "question": topic, "beats": beats}


def _spans(sentences: list[str]) -> list[str]:
    """
    Distinct verbatim spans of the section, each long enough to cite.

    Sentences under MIN_QUOTE_WORDS are dropped — the grader rejects them as too
    thin to prove anything. A section that yields fewer than two usable spans has
    its longest one split in half at a word boundary: both halves are still exact
    substrings of the material, so both are real citations, and the stub can give
    two beats separate evidence without inventing any.
    """
    spans = [s for s in sentences if len(s.split()) >= MIN_QUOTE_WORDS]

    if len(spans) < 2:
        longest = max(sentences, key=lambda s: len(s.split()), default="")
        words = longest.split()
        if len(words) >= MIN_QUOTE_WORDS * 2:
            half = len(words) // 2
            return [" ".join(words[:half]), " ".join(words[half:])]

    return spans or [" ".join(sentences)]


def _refs(user: str) -> list[str]:
    """The visual_refs a prompt is asking about, in beat order."""
    listed = _find(r"(?:in this order|these refs)[^:]*:\s*(.+)$", user, re.M) or ""
    refs = (re.findall(r"'([^']+)'", listed)
            or re.findall(r"^\[([a-z0-9_]+)\]", user, re.M))
    return list(dict.fromkeys(refs))


def _strategy(user: str) -> dict:
    """A plan whose relationships MATCH what _visuals() goes on to draw.

    The two stubs have to agree or an offline run fails on itself:
    check_frames_match_strategy compares the relationship planned here against the
    template chosen there, and _visuals draws every frame as a "bar". "structure"
    is the relationship a bar can honestly carry, so that is what this claims —
    a stub that planned a "process" would have the smoke test reporting a
    contradiction the real pipeline does not have.
    """
    refs = _refs(user)
    lines = dict(re.findall(r"^\[([a-z0-9_]+)\]\s*\w+:\s*(.+)$", user, re.M))
    beats = []
    for i, ref in enumerate(refs):
        subject = lines.get(ref, ref.replace("_", " "))
        beats.append({
            "ref": ref,
            "concept": subject[:90],
            "relationship": "structure",
            "must_see": f"a row of cells with the {i + 1}th one accented",
            "changes_from_previous": "" if i == 0 else "one more cell joins the row",
            "focus": f"cell {i + 1}",
        })
    return {"subject": "a stub composition that grows one cell per beat",
            "beats": beats}


def _vision(user: str) -> dict:
    """Every frame passes, with no composition problems.

    A stub judge that FAILED frames would send the offline run round the redesign
    loop three times against a stub designer that returns the same answer every
    time — three identical attempts and a warning, on every short, for no signal.
    The plumbing is what the stub is for; the verdict is what the real judge is for.
    """
    refs = re.findall(r"^IMAGE \d+ — ref: (\S+)$", user, re.M)
    return {"frames": [{"ref": ref, "visual_correctness": 9,
                        "educational_clarity": 8, "text_dependency": 3,
                        "animation_relevance": 7, "concept_communication": 8,
                        "problems": []} for ref in refs],
            "composition_problems": []}


def _visuals(user: str) -> dict:
    """
    A real Frame per ref, so a stub run exercises the actual renderer.

    These used to come back type="text" with no frame at all, which meant the stub
    path skipped drawing entirely and a layout bug could not show up offline. Now
    every ref gets a legitimate template so `SHORTS_STUB=1` renders genuine SVG
    through skills/layout.render and the smoke test covers it for free.

    ONE "bar" COMPOSITION WITH THE HERO WALKING ALONG IT, not a card per beat. The
    stub used to emit a "stat" per beat and a "takeaway" at the end, carrying the
    spoken line as its caption and its note — which is precisely the shape
    check_frames_are_visual now fails, so an offline run failed its own smoke test
    on the stub rather than on anything real. It is also the shape the real brief
    now forbids, and a stub that models the banned output teaches the smoke test
    nothing. This models the wanted one: one composition, short noun labels, and the
    accent moving between beats.
    """
    refs = _refs(user)

    # Labels are taken from the NARRATION, not invented. check_diagram_matches_
    # narration compares a frame's label words against the beats and the source, and
    # it is right to: a label naming something the voice never says is the defect it
    # exists to catch. A stub that invented "stub frame, rendered locally" failed it
    # for exactly the correct reason, which is not a useful thing for a smoke test
    # to fail on.
    lines = dict(re.findall(r"^\[([a-z0-9_]+)\]\s*\w+:\s*(.+)$", user, re.M))

    # One cell per beat, labelled with the LONGEST word of that beat — a noun, not a
    # clause, and short enough that check_frames_are_visual sees a label rather than
    # a sentence and cannot read the frame as an echo of the line.
    def noun(ref: str) -> str:
        words = re.sub(r"[^\w\s-]", " ", lines.get(ref, ref.replace("_", " "))).split()
        return max(words, key=len)[:14] if words else "step"

    cells = [noun(ref) for ref in refs]

    out = []
    for i, ref in enumerate(refs):
        # THE BAR GROWS, one cell per beat, rather than holding all of them and
        # moving the accent. check_frames_develop fails a short whose every
        # transition is roles-only, and it is right to: that is one static slide
        # with a highlight sliding over it. The stub has to model the shape the
        # brief asks for, or an offline run fails on the stub instead of on the
        # thing being tested.
        #
        # No cells_title, and no word of its own anywhere on the frame.
        # check_diagram_matches_narration compares every drawn word against the
        # narration and the source, so a caption reading "Stub composition" made
        # every offline HTTP run report two shorts with 50% foreign labels — a stub
        # crying wolf, which trains you to ignore the one that means it.
        frame = {
            "template": "bar",
            "title": cells[i] or "Stub",
            "cells": [{"label": label, "role": "hero" if j == i else "plain"}
                      for j, label in enumerate(cells[: i + 1])],
        }
        out.append({"ref": ref, "spec": f"Stub frame {i + 1}: hero on {cells[i]!r}.",
                    "frame": frame})
    return {"visuals": out}


def _understanding(user: str) -> dict:
    """
    Understanding built out of the section's own sentences.

    Same principle as _script: read the real text back rather than emitting
    placeholders, so a stub run exercises understand.evidence_notes() for real
    instead of proving only that the dict has the right keys.
    """
    # Same both-spellings caution as _script: this reaches into a real prompt.
    section = (_find(r"THE SECTION — this is the authority.*?\n---\n(.*?)\n---", user, re.S)
               or _find(r"THE SECTION.*?\n---\n(.*?)\n---", user, re.S)
               or "")
    section = " ".join(section.split())
    topic = _find(r"TOPIC THIS SHORT WILL ANSWER:\s*(.+)", user) or "this topic"
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", section) if s.strip()]
    long_enough = [s for s in sentences if len(s.split()) >= MIN_QUOTE_WORDS]

    return {
        "core_concept": (sentences[0] if sentences else topic)[:200],
        "learning_objective": f"what {topic.rstrip('?')} comes down to"[:200],
        "key_concepts": [s.split(".")[0][:60] for s in sentences[:3]] or ["the concept"],
        "prerequisites": [],
        "how_it_works": " ".join(sentences[:2])[:400] or "the section describes it directly",
        "important_facts": [s[:180] for s in long_enough[:3]] or ["the section states it plainly"],
        # null, not a placeholder: an invented example is the exact failure the real
        # prompt forbids, and a stub that fakes one trains nobody's eye for it.
        "example": None,
        "misconceptions": [],
        "can_answer": [topic[:120]],
        "cannot_answer": [],
        # Verbatim, so evidence_notes() reports zero drift on a stub run. A stub
        # that trips its own diagnostics teaches you to ignore them.
        "source_evidence": long_enough[:3],
    }
