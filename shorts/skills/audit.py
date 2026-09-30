"""SKILL 5 — eval-audit. Code graders run first (free), then the LLM judge (paid)."""
from ..schema import Script, ShortUnit, EvalReport, StoryScript, StoryEvalReport
from ..llm import ask_json
from .. import config, checks

JUDGE_SYSTEM = """You grade a teaching video script against its source material. You are the
last automated gate before a human reviewer, so be strict and specific.

Score 1-5 on each axis.

faithfulness
  5 Every claim is stated in or directly implied by the source section.
  4 Every claim traces to the source; one rewording is looser than ideal.
  3 One claim is plausible but not actually present in the section.
  2 Multiple claims are not in the section, OR a specific number, version, vendor
    name, date, or statistic appears that the source does not contain.
  1 Substantially about something the section does not cover.

  Most beats arrive with a `cites:` line — the sentence of the material the beat
  claims to be a restatement of. Its presence has already been verified; whether it
  SUPPORTS the beat has not, and that is your job. Read each beat against its own
  citation and ask: does this sentence actually establish this claim?

  A citation that merely shares vocabulary with the beat is the failure to catch.
  Example of the exact defect: the beat "that extension is what tells the browser
  this is a page to render" citing "It defines the structure of content and tells
  the browser how to display elements". Both say "tells the browser"; the source
  never says the extension causes rendering. That is an invented claim wearing a
  citation, and it scores 2 — the same as an uncited invention, because it is one.
  Name it in `problems` as "beat N's citation does not support its claim".

question_answered: true only if the answer delivers what the question asked. A
question that asks about two things and gets one explained, or asks "why" and gets
"what", is not answered — even when every individual claim is faithful.

clarity
  5 A learner who has not read the doc understands on first listen.
  4 Clear; one sentence could be tighter.
  3 Understandable but needs a re-listen.
  2 Jargon used before it is defined.
  1 Confusing or self-contradictory.

pace
  5 Beats evenly sized, none over ~12 seconds of speech (~30 words).
  4 Slightly uneven but watchable.
  3 One beat noticeably long.
  2 Wildly uneven.
  1 Effectively a monologue.

diagram_correct: judge the FRAMES section below, when it is present. False if any
frame contradicts the source, shows a value the material gives to a different
selector, labels something the narration never mentions, or repeats the spoken
sentence instead of drawing its subject. If no frames are given, true — but say so
in `problems` rather than implying you checked them.

In `problems`, list each specific defect as an actionable instruction, e.g.
"beat 3 states pages are 4KB; the source never gives a page size". Empty if clean.

Output JSON: {"faithfulness":n,"clarity":n,"pace":n,"diagram_correct":bool,
"question_answered":bool,"problems":["..."]}"""


def judge_script(script: Script, source_text: str,
                 unit: ShortUnit | None = None) -> EvalReport:
    """
    Grade one script, and its frames when they exist.

    `unit` IS WHY diagram_correct MEANT NOTHING. JUDGE_SYSTEM has always asked for
    it — "true only if every on_screen label matches what is being said" — and the
    judge was handed the dialogue and the source and no frames whatsoever. Asked a
    question it had no information to answer, with a schema default of True, it
    answered True every time, on every short, including the ones whose frames were a
    sentence of narration in a box. A field that cannot be false is not a check;
    it is a decoration that makes the report look more thorough than it is.

    So the frames go in when the caller has them. Cheap — a Frame is small
    structured JSON, far smaller than the section it is graded against — and it also
    lets the judge catch the class of error the code graders cannot: a frame that is
    well-formed, on-vocabulary, and about the wrong thing.
    """
    beats = "\n".join(
        f"{i}. {b.line}\n   on_screen: {b.on_screen}"
        + (f"\n   cites: {b.source_quote!r}" if b.source_quote else "")
        for i, b in enumerate(script.beats)
    )
    frames = ""
    if unit is not None and unit.visuals:
        import json
        drawn = {}
        for beat in script.beats:
            visual = unit.visuals.get(beat.visual_ref)
            if visual is not None and visual.frame is not None:
                drawn[beat.visual_ref] = visual.frame.model_dump(exclude_defaults=True)
        if drawn:
            frames = ("\n\nTHE FRAMES, one per visual_ref, in beat order. These are what "
                      "the viewer SEES while each line is spoken — judge diagram_correct "
                      "against them, and say in `problems` which frame is wrong and how.\n"
                      + json.dumps(drawn, indent=1))

    user = f"""SOURCE SECTION (the only permitted source of truth)
---
{source_text}
---

SCRIPT
Question: {script.question}
Estimated length: {script.estimated_seconds}s ({script.word_count} words)

{beats}{frames}

Grade it."""
    # The one call in the pipeline that keeps adaptive thinking on. Everything else
    # fills in a known JSON shape; this one has to weigh a claim against a source
    # and decide whether it holds, which is exactly what thinking is for. It is
    # started before the diagrams and collected after them, so its latency is
    # absorbed rather than added.
    return ask_json(JUDGE_SYSTEM, user, EvalReport, model=config.MODEL_JUDGE,
                    max_tokens=4000, think=True, label="judge")


def audit(script: Script, source_text: str, unit: ShortUnit | None = None, understanding=None):
    """Full audit: code graders, then the judge only if the cheap checks passed.

    `understanding` IS OPTIONAL AND ADDITIVE, same contract as everywhere else it is
    threaded through — but omitting it here is not free the way it is at drafting
    time. Without it, run_script_graders skips check_opening_follows_hook and
    check_hook_plan entirely (they are gated on `understanding is not None`), so a
    hook that generalises past what the section supports is not re-checked at the
    one point this module exists to be the last one. The retry loop that drafted
    this script already read the section once and has `understanding` in hand
    (see skills.understanding.understanding_for's own note on reading once); passing
    the same object here costs nothing extra and closes that gap.
    """
    results = checks.run_script_graders(script, source_text, understanding=understanding)
    if unit:
        # run_unit_graders rather than a loop over UNIT_GRADERS: the diagram check
        # needs the material to recognise a code frame's verbatim labels as grounded.
        results += checks.run_unit_graders(unit, source_text)

    if not checks.all_passed(results):
        return results, None                      # don't pay for a judge on known-bad output

    return results, judge_script(script, source_text, unit)


# --------------------------------------------------------------------- story mode
#
# RESTYLE_TO_STORY_REELS.md Phase 1's judge step. checks.check_mapping (free) is
# what run.py's story path calls first — this only runs once that has already
# passed, the same "don't pay for a judge on known-bad output" order audit()
# keeps above.

METAPHOR_JUDGE_SYSTEM = """You check ONE thing, for each mapping entry given to you: does
metaphor_event behave EXACTLY like concept_rule, with nothing extra implied?

faithful: false if the metaphor_event:
  - implies a behavior, cause, or consequence concept_rule does not state — a
    metaphor is allowed to dramatize a rule, never to add a second rule of its
    own that sounds plausible but was not in the material.
  - shows the OPPOSITE of concept_rule, or a weaker/stronger version of it than
    the material actually claims.
  - would teach a viewer something false about concept_rule if they treated the
    metaphor_event as a literal description of it.

faithful: true only if a viewer who accepted metaphor_event as "this is what
concept_rule means" would come away believing exactly what concept_rule says —
no more, no less.

When faithful is false, `problem` names EXACTLY what the metaphor implies that
concept_rule does not say, e.g. "the whiteboard being wiped implies the value is
lost forever, but concept_rule only says it is recreated with the SAME initial
value — the metaphor drops that it comes back, not that it's gone".

Output JSON: {"verdicts": [{"concept_rule": "...", "faithful": bool, "problem": "..."}, ...]},
one verdict per mapping entry given, in the same order."""


def judge_story_metaphors(mapping: list) -> StoryEvalReport:
    """
    RESTYLE_TO_STORY_REELS.md Phase 1: "for each mapping entry, ask the judge:
    Does metaphor_event behave exactly like concept_rule, with nothing extra
    implied? Any 'no' fails the reel." — StoryEvalReport.passed is that rule.

    TAKES THE MAPPING DIRECTLY (list[ConceptMapping]), NOT A StoryScript —
    Step 2's own "run judge_story_metaphors() on the mapping BEFORE shots are
    written" needs this gate reachable from skills.script.plan_story_mapping,
    which has a ConceptMappingSet in hand and no shots yet, hence no
    StoryScript to build. audit_story (below) still calls this the same way,
    passing `story.mapping`.

    Takes source_text implicitly through concept_rule/source_quote already
    being grounded by checks.check_mapping before this runs; the judge is
    asked to compare the METAPHOR against the RULE, not re-derive the rule
    from the material a second time — that grounding question is
    check_mapping's job, already paid for and already passed by the time this
    call happens.
    """
    entries = "\n\n".join(
        f"concept_rule: {m.concept_rule}\n"
        f"metaphor_event: {m.metaphor_event}\n"
        f"visible_proof: {m.visible_proof}"
        for m in mapping)
    user = f"MAPPING ENTRIES TO CHECK:\n\n{entries}\n\nGrade each one."
    return ask_json(METAPHOR_JUDGE_SYSTEM, user, StoryEvalReport,
                    model=config.MODEL_STORY_JUDGE, max_tokens=2000, think=True,
                    label="story_judge")


def audit_story(story: StoryScript, source_text: str, technical_term: str = ""):
    """Story mode's counterpart to audit() above: free checks first, judge only
    if they passed. See checks.run_story_graders for why this is a separate
    grader list rather than a branch inside run_script_graders.
    """
    results = checks.run_story_graders(story, source_text, technical_term=technical_term)
    if not checks.all_passed(results):
        return results, None
    return results, judge_story_metaphors(story.mapping)
