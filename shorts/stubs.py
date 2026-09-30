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
import ast
import json
import re
from pathlib import Path

from .schema import MIN_SECONDS, MAX_SECONDS, WORDS_PER_SECOND
from .checks import MAX_ANSWER_WORDS, MIN_ANSWERS, MIN_QUOTE_WORDS

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)      # 62
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
        # STEP 10's own path is DETECTED, NOT PASSED AS A FLAG — the marker
        # plan_strategy only writes when it was given an `approach` (see
        # skills/strategy.py's own prompt block). Routes to a DIFFERENT stub
        # that actually varies by approach — see _workflow_aware_strategy's
        # own note on why the ORIGINAL _strategy below must stay fixed at
        # "structure" (it has to keep agreeing with _visuals()'s
        # always-"bar" stub; the workflow-aware path is never carried that
        # far by anything in this codebase yet).
        if "THE APPROVED TEACHING APPROACH FOR THIS SHORT" in user:
            return model_cls(**_workflow_aware_strategy(user))
        return model_cls(**_strategy(user))
    if name == "VisionReport":
        return model_cls(**_vision(user))
    if name == "SectionUnderstanding":
        return model_cls(**_understanding(user))
    if name == "_RegeneratedQuestion":
        return model_cls(**_regenerated_question(user))
    if name == "_FramingOutput":
        return model_cls(**_framing(user))
    if name == "TeachingApproach":
        return model_cls(**_teaching_approach(user))
    if name == "ConceptMappingSet":
        return model_cls(**_story_mapping(user))
    if name == "HookLineOnly":
        return model_cls(**_story_hook_fix(user))
    if name == "StoryShotsSet":
        return model_cls(**_story_shots(user))
    if name == "StoryEvalReport":
        return model_cls(**_story_eval(user))
    if name == "StoryFrameJudge":
        return model_cls(**_story_frame_judge(user))
    if name == "MotionScriptDraft":
        return model_cls(**_motion_script(user))
    if name == "MotionHookFix":
        return model_cls(**_motion_hook_fix(user))
    raise NotImplementedError(
        f"no stub for {name}. Add one in shorts/stubs.py, or unset SHORTS_STUB.")


def _find(pattern: str, text: str, flags=0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _overlay(text: str) -> str:
    """on_screen must stay under the 8-word limit check_overlays() enforces."""
    words = re.sub(r"[^\w\s-]", "", text).split()
    return " ".join(words[:MAX_OVERLAY]) or "detail"


def _terminate(line: str) -> str:
    """
    `line`, guaranteed to end in real terminal punctuation.

    checks.check_narration_sentence_form checks EVERY beat for one, opening
    beat included (it used to skip beat 0 because that was always the
    interviewer's own, separately-worded question; see that check's own
    docstring). Any word-count trim in this file — cutting a long section
    sentence to MAX_BEAT_WORDS, or the total-length last resort further down
    — can land mid-clause, leaving a beat like "...the number of id
    selectors, and the", which is exactly the fragment that check exists to
    catch. Every trim in this file goes through this before it becomes a
    beat's `line`.
    """
    return line if line.endswith((".", "!", "?")) else line + "."


def _truncate(text: str, max_words: int) -> str:
    """The first `max_words` words of `text`, terminated — see _terminate."""
    return _terminate(" ".join(text.split()[:max_words]))


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


def _regenerated_question(user: str) -> dict:
    """
    A deterministic, honest tweak of the original question — never a fabricated
    rewrite — so SHORTS_STUB=1 can exercise review.regenerate end to end with no
    network call.

    Appends the reviewer's own words rather than inventing new phrasing, the
    same "never claim more than the input supports" contract every other stub
    in this file follows: a stub that produced a plausible-sounding rewrite
    would be exercising an LLM's judgement, which is exactly what a stub
    cannot honestly stand in for.
    """
    original = _find(r"^ORIGINAL QUESTION:\s*(.+)$", user, re.M) or "What does this section explain?"
    reason = _find(r"^REVIEWER'S REQUESTED CHANGE:\s*(.+)$", user, re.M) or ""
    base = original.rstrip("?").strip()
    question = f"{base}, specifically regarding {reason}?" if reason else f"{base}?"
    return {"question": question}


def _framing(user: str) -> dict:
    """
    The stub keeps the teaching question IDENTICAL to the approved one — the
    only honest default a rule-based stand-in can produce. Deciding whether a
    reframe would teach better is exactly the pedagogical judgement a stub
    cannot make; copying the approved question verbatim can never violate
    "stay on the same concept" or "answerable from the section", which an
    invented reframe risks doing.
    """
    approved = _find(r"^APPROVED QUESTION.*?:\s*\n(.+)$", user, re.M) or "What does this section explain?"
    return {"teaching_question": approved.strip(),
           "framing_rationale": "Stub: kept the approved question as written.",
           "role": "primary"}


def _teaching_approach(user: str) -> dict:
    """
    Always direct_explanation, with nothing combined and no alternatives — the
    one device that is a defensible, honest default for ANY concept, the same
    reason _understanding defaults its plans to not_needed rather than
    guessing at a required one.

    A stub that picked code, or any other specific device, would be
    pretending to make the pedagogical judgement this step exists to make for
    real — exactly what a stub must not do. It also means a stub run can never
    exhibit the code-by-default failure this step is guarded against: the
    mechanical path never reaches for code at all, so if that bias ever shows
    up it can only be in what the real model chooses, not in the plumbing.
    """
    concept = _find(r"^CONCEPT:\s*(.+)$", user, re.M) or "this concept"
    return {
        "primary": "direct_explanation",
        "combined_with": [],
        "alternatives": [],
        "rationale": f"Stub: explaining {concept} plainly, with no device chosen.",
    }


def _script(user: str) -> dict:
    """
    Build a single narrator's script out of the section's own sentences.

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
    # Capped by the sentences available, NOT floored at MIN_ANSWERS. Forcing four
    # beats out of a three-sentence section is what the cycling did, and it is the
    # padding check_beats_develop rejects — better to emit three and fail
    # narration_shape honestly than to emit four that repeat.
    n_beats = min(BEATS, len(spans), len(sentences))

    # ONE DISTINCT SENTENCE PER BEAT, IN DOCUMENT ORDER. No cycling.
    #
    # Three shapes were tried here and the first two are instructive. Packing
    # several sentences per beat and STOPPING when the next did not fit turned a
    # section's one short sentence into a whole short beat. Packing and SKIPPING
    # instead fixed that and broke something worse: skipping advances the sentence
    # cursor, so the cursor wrapped and later beats were served sentences earlier
    # beats had already used — check_beats_develop then found beats 3 and 4 were
    # 100% words already heard, which is exactly right, because they were.
    #
    # Taking one sentence per beat cannot produce either fault. Every beat is a
    # different span of the section, so novelty is structural rather than hoped
    # for, and the citation is the span the beat was built from rather than one
    # cycled independently of it.
    #
    # It also means the stub can no longer manufacture length. A section without
    # enough distinct sentences produces a short script and fails timing, and that
    # failure is the honest report: 4-5 beats that each say something new need a
    # section with 4-5 things to say. content/css_specificity.md is sized for it;
    # the thinner sample documents are not, and should fail here.
    # MIRRORS _understanding's OWN STEP COUNT, without calling it — see that
    # function's docstring on why the two stay independent. _understanding
    # builds a 1-step sequence ("concept") when there is only one span, or a
    # 2-step sequence ("concept" then "result") otherwise; the same condition,
    # applied here, is what lets relates_to_step point at a step that will
    # actually exist once _understanding runs on this same section.
    step_count = 1 if len(spans) <= 1 else 2

    # STEP: continuous-narration opening, NOT the raw topic/selected-question
    # echoed verbatim. The topic is very often phrased as a WH-question
    # ("Why does...", "What are...") — this pipeline's own selected question
    # is an internal teaching objective, never beat 1 itself (see script.py's
    # SYSTEM: "NEVER JUST CONVERT THE SELECTED QUESTION INTO A SENTENCE") — so
    # a stub that spoke it verbatim, as a question, modelled exactly the
    # interviewer/Q&A defect checks.check_no_interview_structure now exists to
    # reject, and every stub-mode test exercising the full grader list would
    # fail on the stub's OWN shape rather than on anything real being tested.
    # Stripping the trailing "?" is the minimal fix: check_no_interview_structure's
    # interrogative-lead detection requires a beat to actually END in "?" to be
    # read as a posed question (see its own docstring on why this is not a
    # blanket ban on the word "why"/"how") — a declarative sentence that
    # happens to start with one of those words is not itself an interview.
    opening = topic.strip()
    if opening.endswith("?"):
        opening = opening[:-1] + "."
    beats = [{"speaker": "narrator", "line": opening,
              "on_screen": _overlay(topic), "visual_ref": "v_question"}]
    for n in range(1, n_beats + 1):
        source = sentences[(n - 1) % len(sentences)]
        line = _truncate(source, MAX_BEAT_WORDS)
        beats.append({"speaker": "narrator", "line": line,
                      "on_screen": _overlay(line), "visual_ref": f"v_step_{n}",
                      # Verbatim by construction, and now the span the beat was
                      # actually built from rather than one cycled separately — so
                      # the citation cannot drift away from the line it supports.
                      "source_quote": spans[(n - 1) % len(spans)],
                      # Every beat but the last relates to step 1 ("concept");
                      # the last beat is about to be overwritten to land on the
                      # SAME span step 2 ("result") describes, below — see that
                      # block's own comment.
                      "relates_to_step": step_count if n == n_beats and step_count > 1 else 1})

    # THE LAST BEAT LANDS THE OBJECTIVE, because _understanding reports one and
    # check_reaches_objective asks whether the short ENDS on it. Without this the
    # final beat landed on whatever the sentence cycle reached — section 3.2 ended
    # on the valid bit while its stated objective was the page-number split,
    # scoring 17% on the objective. The grader was right; the stub was modelling a
    # short that stops somewhere other than its own idea.
    #
    # THE LAST SPAN, NOT THE FIRST, and that correction matters. The first cut used
    # sentences[0] — which is also where beat 1 starts, so every stub short shipped
    # with beats 1 and 3 IDENTICAL. check_beats_develop now fails exactly that, as
    # it should, and a stub that models the defect a grader exists to catch fails
    # the offline run on the stub instead of on the thing being tested.
    #
    # _understanding computes the same `spans` from the same section text, so both
    # halves agree on which sentence the objective is without sharing state.
    #
    # The source_quote is left as the cycled span: still a verbatim span of the
    # section, still distinct per beat, and never coupled to the assembled lines.
    if len(beats) > 1 and spans:
        landing = _truncate(spans[-1], MAX_BEAT_WORDS)
        # Guard for a section so thin that its last span IS its first sentence:
        # duplicating a beat to satisfy one grader while failing another is not a
        # trade worth making, so the cycled line stays.
        if landing not in [b["line"] for b in beats[:-1]]:
            beats[-1]["line"] = landing
            beats[-1]["on_screen"] = _overlay(landing)

    # THERE IS NO TOP-UP TO THE LENGTH FLOOR, and there was one — briefly — so
    # here is why it came out.
    #
    # The 35-50s window needs 87-125 spoken words. Every section of
    # session_18_paging.md is 47-78 words, so the first attempt at this made the
    # floor by appending cycled sentences to the earlier beats. It worked, in the
    # sense that timing passed. Then check_beats_develop read the result and found
    # beats 2, 3 and 4 were 100% words already heard — because that is precisely
    # what cycling a short section is.
    #
    # Both graders were right, and together they say something true: a section with
    # 66 words of content cannot produce five beats that each add something. No
    # amount of arranging fixes that, and a stub that pads to satisfy one grader
    # while tripping another models the defect the graders exist to catch — the
    # offline run then fails on the stub instead of on the thing being tested.
    #
    # So the stub stays honest and the MATERIAL got richer: content/css_specificity.md
    # has sections written to carry a 35-50s short, and that is what the free
    # offline run points at. A thin document now fails the length gate here, which
    # is the correct report — see check_plan_depth, which says the same thing about
    # the reading before a word is written.
    # Last resort: trim the final beat rather than hand the grader a script we
    # already know is over budget.
    total = sum(len(b["line"].split()) for b in beats)
    if total > MAX_WORDS:
        tail = beats[-1]["line"].split()
        keep = max(5, len(tail) - (total - MAX_WORDS) - 1)
        beats[-1]["line"] = _terminate(" ".join(tail[:keep]))
        beats[-1]["on_screen"] = _overlay(beats[-1]["line"])

    return {"short_id": short_id, "question": topic, "beats": beats}


def _understanding(user: str) -> dict:
    """A reading of the section built out of the section's own sentences.

    THE POINT OF DOING IT HONESTLY. This block ends up inside the script prompt, so
    a stub returning invented prose would be feeding the script stub words that
    appear nowhere in the document — and the one thing an offline run exists to
    prove is that grounding works for real rather than by being switched off. Every
    string here is either a verbatim span of the section or a fixed phrase carrying
    no claim about it.

    cannot_answer is deliberately EMPTY. It is the field the script step is told to
    steer away from, so a stub guessing at it would push the offline run off topics
    the section does cover — a stub inventing a constraint the real pipeline never
    had, which is the failure mode the module docstring warns about.
    """
    body = _find(r"THE SECTION TO READ.*?\n---\n(.*?)\n---", user, re.S) or ""
    section_id = _find(r"THE SECTION TO READ — \[([^\]]+)\]", user) or ""

    sentences = [s for s in re.split(r"(?<=\.)\s+", " ".join(body.split())) if s.strip()]
    spans = _spans(sentences) if sentences else []

    # THE SPAN THE SCRIPT ENDS ON — see the matching note in _script, which lands
    # its final beat on the same one. Both halves derive `spans` from the same
    # section text, so they agree without sharing state.
    core_idea = spans[-1] if spans else "what this section explains"

    # A sequence that PASSES check_teaching_sequence, honestly.
    #
    # Every `concept` is a span of the section, so the vocabulary check clears on
    # the section's real words rather than on a grader being lenient. Two steps,
    # not four, because the grader caps the sequence and a stub that modelled the
    # rejected shape would fail the offline run on the stub.
    #
    # FIRST SPAN THEN LAST, in document order, which is also the order _script
    # walks: beat 1 is assembled from the opening sentences and the final beat
    # lands spans[-1]. Building the sequence from core_idea first — as this did
    # while core_idea was a sentence — put step 1 wherever that sentence happened
    # to be and produced a plan the stub's own script ran out of order.
    #
    # `purpose` and `explanation_goal` are fixed phrases carrying no claim about
    # the material — the stub is proving the plumbing, and inventing a reason a
    # step is needed would put words in the document's mouth.
    # `stage` FOLLOWS THE SAME STRUCTURAL HONESTY AS THE REST OF THIS FUNCTION.
    # Step 0 is spans[0] — the section's own opening idea, so "concept" is the
    # only stage a stub can claim without inventing a judgement. Step 1, when
    # present, is spans[-1] — the SAME span the final beat lands on (see the
    # docstring above and _script's matching note) — so "result" is likewise
    # structural, not guessed. Neither "mechanism" nor "example" nor "hook" is
    # ever claimed here: a stub cannot tell a mechanism from a definition
    # without reading the section, and check_teaching_sequence does not ask it
    # to — this two-step sequence is honest about being the shape it actually is.
    stages = ["concept", "result"]
    sequence = []
    for i, concept in enumerate(spans[:1] + spans[-1:] if len(spans) > 1 else spans[:1]):
        sequence.append({
            "concept": " ".join(concept.split()[:6]),
            "purpose": f"stub step {i + 1}: establish what the section states here",
            "explanation_goal": "learner can follow the next step",
            "stage": stages[i],
        })

    return {
        "section_id": section_id,
        # A span of the section, not a description of it. See the docstring.
        "core_idea": core_idea,
        "key_points": spans[:3],
        # NO HOOK PLAN AT ALL, which is a different claim from "direct" and the
        # honest one here. `direct` asserts that the concept is this section's best
        # opening — a judgement a stub is not entitled to make. None says no
        # decision was reached, which is exactly true, and check_opening_follows_hook
        # then skips cleanly.
        #
        # It also resolves a contradiction the stub cannot write its way out of.
        # With a plan present, the leads-in rule wants the objective within the
        # first two beats and check_reaches_objective wants it in the last one; a
        # real script satisfies both by developing the same idea in new words,
        # while a stub that only copies whole sentences would have to repeat one —
        # which check_beats_develop now rejects, correctly. The hook path keeps its
        # coverage from the frozen eval cases (E037 and friends), which test it far
        # more precisely than a stub ever did.
        "hook_plan": None,
        "teaching_sequence": sequence,
        "concrete_examples": [],
        # not_needed, and honestly so: concrete_examples is empty above, because a
        # stub cannot tell which of a section's nouns is a worked example without
        # reading it. Claiming "required" would make the stub name something, and
        # anything it named would be a fabrication — which check_example_plan would
        # then correctly throw away, so the offline run would be exercising the
        # quarantine path on every short instead of the normal one.
        "example_plan": {"need": "not_needed", "example": "",
                         "supports_step": None, "learner_takeaway": ""},
        # not_needed for the same reason, and here it is the only honest answer
        # available: common_confusions is empty above because a stub cannot know
        # what a learner gets wrong, and a stub that claimed "required" would have
        # to invent both a misconception and a correction. That is the one thing
        # this whole field exists to prevent, and check_confusion_plan would throw
        # it away — so the offline run would exercise the quarantine path on every
        # short instead of the normal one.
        "confusion_plan": {"need": "not_needed", "confusion": "",
                           "relates_to_step": None, "correct_understanding": "",
                           "learner_takeaway": ""},
        "common_confusions": [],
        "cannot_answer": [],
        "source_evidence": spans[:2],
    }


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


#: STEP 10 — deterministic per-approach shape, so a stub run through
#: plan_strategy_for_workflow exercises a genuinely different, concept-first
#: path per approach rather than always the same "structure" answer
#: _strategy above gives. Never "code": the whole point of this table is that
#: nothing here reaches for code or text by default — see
#: _workflow_aware_strategy's own docstring for why this is never carried
#: into _visuals()'s stub, which is the one that has to keep agreeing with
#: _strategy's fixed answer.
_STUB_APPROACH_SHAPE = {
    "process_demonstration": ("process", "single_container"),
    "comparison": ("comparison", "two_sides"),
    "analogy": ("structure", "single_object"),
    "real_world_example": ("structure", "single_object"),
    "conceptual_visual": ("hierarchy", "nested_levels"),
    "code": ("structure", "not_applicable"),
    "direct_explanation": ("structure", "single_object"),
}


def _workflow_aware_strategy(user: str) -> dict:
    """
    A deterministic, APPROACH-VARYING stub for plan_strategy_for_workflow —
    Step 10's own path.

    KEPT SEPARATE FROM _strategy ABOVE ON PURPOSE. That one always answers
    "structure" because it has to agree with _visuals()'s own stub, which
    always draws every frame as "bar" — see its own comment. Nothing in this
    codebase carries a workflow-aware strategy into _visuals() yet (visual
    RENDERING is explicitly future work — see shorts/skills/strategy.py's
    own module docstring on what this step must not do), so this stub is
    free to vary by approach without breaking that agreement, and doing so
    is the whole point: a stub that always said "structure" regardless of
    the approved approach would prove nothing about whether the approach
    actually reached the strategist.
    """
    refs = _refs(user)
    lines = dict(re.findall(r"^\[([a-z0-9_]+)\]\s*\w+:\s*(.+)$", user, re.M))
    primary = _find(r"^THE APPROVED TEACHING APPROACH FOR THIS SHORT:\s*(.+)$",
                    user, re.M) or ""
    primary = primary.split(",")[0].strip()   # drop ", combined with ..." if present
    relationship, physical_form = _STUB_APPROACH_SHAPE.get(primary, ("structure", "single_object"))

    # STEP 11 — reconsider_visual_strategy sends the SAME "THE APPROVED
    # TEACHING APPROACH..." marker this stub already dispatches on, plus its
    # own "THE PREVIOUS PLAN..." marker. Detected here so a REGENERATION
    # produces a deterministic but genuinely DIFFERENT dict than a fresh
    # plan — subject and why_visual both reference the reviewer's own
    # reason — rather than silently returning byte-identical output for two
    # calls that are supposed to represent two different decisions.
    reason = ""
    if "THE PREVIOUS PLAN, WHICH A HUMAN REVIEWED" in user:
        m = re.search(
            r"THE REVIEWER'S REQUESTED CHANGE — address this directly:\n(.*?)\n\n",
            user, re.S)
        if m:
            reason = m.group(1).strip()

    beats = []
    for i, ref in enumerate(refs):
        subject = lines.get(ref, ref.replace("_", " ")) or ref
        if relationship == "process":
            must_see = f"{subject} arriving, then settling into place"
            changes = "" if i == 0 else "the next step's state is now visible"
        elif relationship == "comparison":
            must_see = f"both sides held up at once, {subject} on one of them"
            changes = "" if i == 0 else "the second side's own detail now sits alongside the first"
        elif relationship == "hierarchy":
            must_see = f"{subject} shown as one level resting on another"
            changes = "" if i == 0 else "one more level is now visible in the stack"
        else:
            must_see = f"{subject} shown as a single, concrete object"
            changes = "" if i == 0 else "the object's own state has changed"
        why_visual = f"the narration alone does not show {subject} directly"
        if reason:
            why_visual += f"; revised per reviewer note: {reason[:60]}"
        beats.append({
            "ref": ref,
            "concept": subject[:90],
            "relationship": relationship,
            "physical_form": physical_form,
            "why_visual": why_visual,
            "must_see": must_see,
            "changes_from_previous": changes,
            "focus": subject,
        })
    subject_line = (f"a stub composition revised for the approved "
                    f"{primary or 'direct_explanation'} approach per: {reason[:60]}"
                    if reason else
                    f"a stub composition built for the approved "
                    f"{primary or 'direct_explanation'} approach")
    return {"subject": subject_line, "beats": beats}


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


# --------------------------------------------------------------------- story mode
#
# RESTYLE_TO_STORY_REELS.md Phase 1. Same honesty rule as _understanding/_script
# above: every source_quote is a REAL verbatim span of the material, because that
# is the one thing checks.check_mapping actually checks against the source, and a
# stub that faked it would let a broken quote-matcher pass a stub run clean. Every
# other field (concept_rule, metaphor_event, visible_proof, lesson_line) is a
# fixed, deterministic phrase — check_mapping never asks whether those are TRUE,
# only that they are internally consistent (same concept_rule string used as
# concept_ref, same lesson_line used as a shot's line and in `lessons`), so
# inventing prose for them is not the honesty gap the module docstring warns
# about.

#: Rotates through checks.STORY_ACTORS so a stub mapping's actor field is
#: always a valid one without importing checks (stubs.py stays a leaf module).
_STUB_ACTORS = ("Rahul", "System", "Riya")


def _story_mapping(user: str) -> dict:
    body = _find(r"MATERIAL:\n(.*?)\n\nILLUSTRATION STYLE", user, re.S) or ""
    sentences = [s for s in re.split(r"(?<=\.)\s+", " ".join(body.split())) if s.strip()]
    spans = _spans(sentences) if sentences else []
    if not spans:
        spans = [body.strip() or "this material"]
    # 3 entries — check_mapping's own preferred default (2-4 allowed; Step 2
    # Part B's ~26-30 shot budget needs 3 mini-scenes' worth of material to
    # land in range without stretching each one artificially thin).
    picks = spans[:3] if len(spans) >= 3 else (spans + [spans[-1]] * (3 - len(spans)))
    mapping = [
        {
            # entry 0 must read as THE PROBLEM (check_mapping's first-entry
            # rule) — "does not" is one of _FAILURE_WORDS.
            "concept_rule": (f"rule {i + 1} does not work without the fix: {quote[:40]}"
                             if i == 0 else f"rule {i + 1}: {quote[:40]}"),
            "source_quote": quote,
            "actor": _STUB_ACTORS[i % len(_STUB_ACTORS)],
            "metaphor_event": f"stub event {i + 1} happens when the stub notebook is opened",
            "visible_proof": f"stub visible proof {i + 1}, no words needed",
            "lesson_line": f"Stub lesson {i + 1}.",
        }
        for i, quote in enumerate(picks)
    ]
    # `chosen` is intentionally absent here — skills.script._assign_chosen_candidate
    # sets it in code from these scores, the same as it would for a real
    # model response that omits the field (see MetaphorCandidate.chosen).
    candidates = [
        {"name": "stub desk", "pitch": "a stub scene at a stub desk",
         "familiarity": 5, "faithfulness": 5, "drawability": 5, "drama": 5},
        {"name": "stub runner-up A", "pitch": "a weaker stub candidate",
         "familiarity": 3, "faithfulness": 3, "drawability": 3, "drama": 3},
        {"name": "stub runner-up B", "pitch": "another weaker stub candidate",
         "familiarity": 2, "faithfulness": 3, "drawability": 3, "drama": 2},
    ]
    return {
        "mapping": mapping,
        "system_name": "Stub System",
        "setting": "a quiet stub desk",
        "props": ["stub notebook"],
        "candidates": candidates,
        "hook_line": "Ever noticed how the stub desk always resets?",
        # STEP 9 FIX 2: required, non-blank — see ConceptMappingSet.
        # technical_term's own field validator.
        "technical_term": "stub state",
        "card_facts": ["Stub notation fact about a return shape.",
                      "Stub complexity fact, written as O(1)."],
    }


def _story_hook_fix(user: str) -> dict:
    """
    skills.script.regenerate_hook_line's stub path — a NARROW repair call
    (HookLineOnly, one field), separate from _story_mapping above. Always
    returns a line that passes checks.check_hook (a real opener from
    HOOK_OPENERS, short, no technical term named) so the happy path —
    story_reel.py's _fix_stale_hook_line regenerating a stale, pre-4-opener
    hook_line on a resumed mapping — exercises end to end under
    SHORTS_STUB=1 with no real model call. A test that wants the RETRY path
    (a candidate that keeps failing check_hook) monkeypatches
    skills.script.ask_json directly, the same pattern every other retry-path
    test in this project already uses (see e.g. judge_story_metaphors
    rejection tests) — this stub only needs to model the common case.
    """
    return {"hook_line": "Ever noticed how the stub scene always resets?"}


#: RESTYLE_TO_STORY_REELS.md Step 2 Part B — the shape every stub (and every
#: real) shot list must follow. Kept here, not folded inline into
#: _story_shots, so shorts/story_mode_test.py can import it directly and
#: build "break exactly one rule" variants by mutating a COPY of a known-good
#: script, rather than stubs.py needing one hand-written variant per rule.
def build_stub_shots(entries: list[dict], hook_line: str, props: list[str],
                     card_facts: list[str], brand_handle: str, topic_label: str,
                     technical_term: str | None = None) -> list[dict]:
    """
    Build a compliant ~26-30 shot list from an approved mapping's entries.

    `entries` is a list of dicts with concept_rule/source_quote/actor/lesson_line
    — the same shape _story_shots below parses out of the approved-mapping
    text block. Deterministic and dumb on purpose, same philosophy as every
    other stub in this module: it follows the RULES (rhythm, structure,
    per-shot fields) exactly, using the real mapping's own words, so
    checks.run_story_graders passes for real rather than by being switched off.
    """
    props = list(props) or ["stub prop"]
    technical_term = technical_term or "the concept"
    shots: list[dict] = []

    def add(shot_id, characters, action, **kw):
        shots.append({
            "shot_id": shot_id, "characters": characters, "action": action,
            "line": kw.get("line"), "concept_ref": kw.get("concept_ref"),
            "story_beat": kw.get("story_beat"), "kind": kw.get("kind", "scene"),
            "emotion": kw.get("emotion", ""), "key_prop": kw.get("key_prop"),
            "camera": kw.get("camera", "static"), "framing": kw.get("framing", "medium"),
            "source_quote": kw.get("source_quote"), "overlay_text": kw.get("overlay_text"),
            "card_lines": kw.get("card_lines") or [],
        })

    add("s_hook", [], "the scene opens on the empty setting", line=hook_line,
       framing="wide")

    for ei, e in enumerate(entries):
        actor, rule, quote, lesson = e["actor"], e["rule"], e["quote"], e["lesson"]
        prop = props[ei % len(props)]
        common = dict(concept_ref=rule, key_prop=prop, source_quote=quote)

        # 4 "problem" shots — the difficulty this entry's metaphor resolves.
        # STEP 9 FIXES ROUND 6: bumped from 3 to 4 (7 -> 8 shots/entry
        # overall) to match SYSTEM_STORY_SHOTS's own retuned "aim for 8
        # shots PER MINI-SCENE" arithmetic — real runs had been landing at
        # 22-23 total shots (below the 24 floor) even with the prompt's
        # prior "aim for 7" target, so the prompt now targets ~29, and
        # this fixture is kept in step with it so the stub sits clearly
        # above the floor too, not just barely over it.
        add(f"s{ei}_problem0", [actor], f"{actor} tries the old way with the {prop}",
           line=f"{actor} tries again with the {prop}.", story_beat="problem",
           emotion="determined", camera="static", framing="medium", **common)
        add(f"s{ei}_problem1", [actor], f"{actor} keeps trying, nothing changes",
           story_beat="problem", emotion="frustrated", camera="static",
           framing="medium", **common)
        add(f"s{ei}_problem2", [actor], f"{actor} stares at the {prop}, stuck",
           story_beat="problem", emotion="frustrated", camera="push_left",
           framing="medium", **common)
        add(f"s{ei}_problem3", [actor], f"{actor} tries one more thing with the {prop}, still stuck",
           story_beat="problem", emotion="frustrated", camera="zoom_out",
           framing="medium", **common)

        # THE REVEAL — one "reaction" shot, wide, then close_up right after it
        # (checks.check_shot_rhythm's own rule).
        add(f"s{ei}_reaction", [actor], f"the {prop} does what the rule says it does",
           story_beat="reaction", emotion="surprised", camera="shake",
           framing="wide", **common)
        add(f"s{ei}_reveal_close", [actor], f"a close view of the {prop} settles",
           story_beat="payoff", emotion="surprised", camera="zoom_in",
           framing="close_up", **common)

        # 2 more "payoff" shots. The first is a `two_shot` — the actor and a
        # companion sharing the moment together, waist up — Step 5's own
        # framing, and what guarantees every mapping entry contributes both
        # a second cast member on screen and a two_shot for story_frames.py's
        # --sample selection to actually find.
        companion = "Rahul" if actor != "Rahul" else "System"
        add(f"s{ei}_payoff0", [actor, companion],
           f"{actor} and {companion} both look at the {prop} together",
           story_beat="payoff", emotion="relieved", camera="static",
           framing="two_shot", **common)
        add(f"s{ei}_payoff1", [actor], f"{actor} nods at the {prop}",
           line=lesson, story_beat="payoff", emotion="relieved", camera="static",
           framing="medium", **common)

        if ei == 0:
            add("s_concept_named", [], f"the camera lingers on the {prop} a moment longer",
               line=f"And that {prop}? That's {technical_term}.")

    for i, fact in enumerate(card_facts[:2]):
        add(f"s_card{i}", [], "a plain fact card appears over the scene",
           kind="text_card", overlay_text=fact)

    recap_lines = [" ".join(e["lesson"].split()[:min(5, max(2, len(e["lesson"].split())))])
                  for e in entries]
    add("s_recap", [], "a short recap card appears", kind="recap", card_lines=recap_lines)

    add("s_cta", [], "a follow card appears", kind="cta",
       overlay_text=f"Follow {brand_handle} to learn {topic_label} the simple way.")

    return shots


_STORY_SHOTS_ENTRY_RE = re.compile(
    r"concept_rule:\s*(?P<rule>.+?)\n\s*source_quote:\s*(?P<quote>.+?)\n"
    r"\s*actor:\s*(?P<actor>.+?)\n\s*metaphor_event:.*?\n\s*visible_proof:.*?\n"
    r"\s*lesson_line:\s*(?P<lesson>.+?)(?:\n|$)", re.S)


def _story_shots(user: str) -> dict:
    entries = [{k: v.strip() for k, v in m.groupdict().items()}
              for m in _STORY_SHOTS_ENTRY_RE.finditer(user)]
    if not entries:
        entries = [{"rule": "stub rule", "quote": "stub quote", "actor": "Rahul",
                   "lesson": "Stub lesson."}]

    hook_line = _find(r"OPENING HOOK LINE[^:]*:\s*(.+)", user) or "Ever noticed the stub reset?"
    technical_term = _find(r"TECHNICAL TERM[^:]*:\s*(.+)", user) or "the concept"
    props_text = _find(r"PROPS:\s*(\[.*?\])", user)
    try:
        props = ast.literal_eval(props_text) if props_text else []
    except (ValueError, SyntaxError):
        props = []
    brand_handle = _find(r"BRAND HANDLE FOR THE CTA:\s*(.+)", user) or "@learnthesimpleway"
    topic_label = _find(r"TOPIC FOR THE CTA[^:]*:\s*(.+)", user) or "this"
    card_block = _find(r"CARD FACTS[^\n]*:\n(.*?)\nBRAND HANDLE", user, re.S) or ""
    card_facts = [ln.strip("- ").strip() for ln in card_block.splitlines()
                 if ln.strip().startswith("-")]

    shots = build_stub_shots(entries, hook_line, props, card_facts, brand_handle, topic_label,
                             technical_term=technical_term)
    return {
        "cast": [],
        "shots": shots,
        "lessons": [e["lesson"] for e in entries],
        "estimated_seconds": 30.0,
    }


def _story_eval(user: str) -> dict:
    rules = re.findall(r"concept_rule:\s*(.+)", user)
    return {"verdicts": [{"concept_rule": r.strip(), "faithful": True, "problem": ""}
                         for r in rules]}


def _story_frame_judge(user: str) -> dict:
    """
    A clean pass, every axis 5 — the honesty rule other stubs in this module
    follow (see the module docstring) does not apply the same way here:
    there is no real frame for this stub to look at and report on
    truthfully, only the same canned "this looks fine" opinion every
    SHORTS_STUB=1 judge call in this project already gives (see EvalReport's
    own stub above). Tests exercising a FAILING verdict monkeypatch
    skills.vision.judge_story_frame directly instead of trying to make this
    stub text-sniff its way to a bad score.
    """
    result = {
        "character_match": 5, "no_text": 5, "action_visible": 5,
        "emotion_readable": 5, "style_match": 5, "reasons": [],
    }
    if "score setting_match" in user:
        result["setting_match"] = 5
    return result


# =========================================================================== motion
#
# A motion script is eleven shots of hand-fitted captions, hook, code and icons —
# not something a dumb string-splitter can make pass every motion grader from
# arbitrary text. So the motion stubs are the golden fixtures themselves,
# evals/fixtures/motion/*_golden.json: the one whose concept_name the material
# actually teaches. Material no fixture covers raises, naming the fix, rather
# than handing back a script about a different topic that then fails grounding
# in a way that looks like a pipeline bug.

_MOTION_FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "fixtures" / "motion"
_MOTION_DRAFT_FIELDS = ("hook_question", "concept_name", "promise",
                        "icon_vocabulary", "takeaways", "shots")


def _motion_fixture_for(user: str) -> dict:
    material = (_find(r"MATERIAL:\n(.*?)(?:\n(?:CORE IDEA|THE APPROVED|SERIES)|\Z)",
                      user, re.S) or user)
    flat = re.sub(r"[`*]", "", material).lower()
    for path in sorted(_MOTION_FIXTURES.glob("*_golden.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["concept_name"].lower() in flat:
            return data
    raise NotImplementedError(
        "no motion stub fixture teaches this material — add an "
        "evals/fixtures/motion/<name>_golden.json whose concept_name appears in it, "
        "or unset SHORTS_STUB.")


def _motion_script(user: str) -> dict:
    data = _motion_fixture_for(user)
    return {k: data[k] for k in _MOTION_DRAFT_FIELDS}


def _motion_hook_fix(user: str) -> dict:
    data = _motion_fixture_for(user)
    hook = data["shots"][0]
    return {"hook_question": data["hook_question"],
            "speech": hook["speech"], "captions": hook["captions"],
            "visual": hook["visual"]}
