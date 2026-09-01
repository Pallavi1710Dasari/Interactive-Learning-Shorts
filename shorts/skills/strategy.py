"""
SKILL 3a — decide what the viewer must SEE, before anything decides how to draw it.

WHY THIS IS ITS OWN STEP
spec_visuals used to do two jobs in one call. It read the beats and returned a
template name plus the words to put in it, which means the question

    what should someone SEE in order to understand this?

was never actually asked. It was answered as a side effect of picking a shape, and
a model asked for two things at once does the answerable one: "bar" is a concrete
choice with a fixed vocabulary, and "what would make this land" is not. So the
shape got chosen carefully and the seeing got chosen by accident.

That is measurable in the frames, and it was measured — visual correctness 9/10,
educational clarity 4/10, text dependency 8/10. The templates were doing their job
perfectly. They were being pointed at the wrong pictures.

WHAT SEPARATING IT BUYS
Three things, and none of them are available while the two decisions are fused:

  1. The educational rules become enforceable. Almost every rule in the brief is a
     rule about the KIND of claim being made — animate a process, show both sides
     of a comparison at once, use spatial hierarchy for a hierarchy. A step that
     never names the kind cannot follow them. This step names it, in
     `relationship`, and the name is then checked against what got drawn.
  2. The strategy can be wrong in a way you can read. "Focus: the arrow from
     browser to server" is a sentence a human can disagree with. A template name
     is not.
  3. The redesign loop gets something to hold onto. When the vision judge rejects
     a frame, the strategy says what that frame was FOR, so the next attempt can
     change the drawing without losing the intent — which is what happened before,
     when a rejected frame was redesigned from the beats again and came back as a
     different arrangement of the same misunderstanding.

WHAT THIS STEP MUST NOT DO
Pick a template. It is not shown the list, on purpose. Handed the eight shapes it
starts reasoning backwards from what is drawable, which reintroduces exactly the
fusion this file exists to undo — and the shapes are chosen in visuals.py by a
model that IS shown them, against a strategy that already exists.
"""
from ..schema import Script, Section, VisualStrategy
from ..llm import ask_json
from .. import config


#: The reviewer's rules, in the form the models are actually given them.
#:
#: ONE COPY, TWO READERS. The strategist below is judged against these and so is
#: the vision judge in skills/vision.py, and they have to be the same rules or the
#: loop oscillates: a designer working to one list and a grader marking against a
#: different one produces a frame that is rejected, redesigned toward the rejection,
#: and rejected again for the thing the first version had right. It is imported
#: rather than restated for that reason and no other.
#:
#: Rules 6 to 10 are the ones with no home before this file existed. They are all
#: conditioned on the KIND of concept — "if the concept describes a process..." —
#: and nothing in the pipeline had ever decided what kind a concept was.
EDUCATIONAL_VISUAL_RULES = """EDUCATIONAL VISUAL RULES

1.  Never visualise a concept primarily by displaying its name. A word set large is
    not a picture of the thing the word refers to.
2.  Prefer objects, relationships, processes and state changes.
3.  EVERY SCENE MUST COMMUNICATE THE CONCEPT EVEN IF ALL TEXT IS REMOVED. This is
    the test the others serve. Imagine the frame with every label deleted: if what
    is left is a set of empty rectangles, the picture was carrying nothing and the
    labels were carrying everything.
4.  Use text only for essential labels, numbers, and short annotations.
5.  Never use a large heading as the main visual explanation.
6.  If the concept describes a PROCESS, the frame must show the process happening —
    ordered stages, with the movement between them drawn.
7.  If the concept describes a COMPARISON, show both states SIMULTANEOUSLY, side by
    side. Never one after the other: a difference the viewer has to remember across
    a cut is a difference they did not see.
8.  If the concept describes DATA MOVEMENT, draw the thing that moves, the place it
    starts and the place it arrives — and the path between them.
9.  If the concept describes HIERARCHY, use SPATIAL hierarchy: containment or
    levels, so the structure is in the arrangement rather than in the words.
10. If the concept describes CAUSE -> EFFECT, both the cause and the effect are on
    screen, with the direction between them drawn.
11. Avoid generic computer and laptop icons unless the computer itself is the
    subject.
12. Avoid decorative illustration that does not contribute to understanding."""


STRATEGY_SYSTEM = """You are the VISUAL STRATEGIST for a short teaching video.

You decide WHAT A VIEWER MUST SEE. You do not decide how it is drawn, you are not
choosing from a menu of shapes, and you must not describe a layout. Another step
owns that, and it is better at it than you because it can see the renderer.

Your entire job is the question that step cannot answer for itself:

    what should a learner SEE in order to understand this concept?

__RULES__

HOW TO ANSWER IT
For each beat, in order, you write down five things.

`concept` — the ONE idea this beat teaches, in a learner's words.
    Not the beat's sentence. The idea underneath the sentence. If the line is
    "so the browser has to fetch it separately", the concept is "the stylesheet is
    a second file the browser goes and gets", not the clause.

`relationship` — what KIND of claim it is. Exactly one of:
    process        a sequence of events, in order
    comparison     two states or approaches weighed against each other
    data_movement  something travels from one place to another
    hierarchy      containment, nesting, or levels
    cause_effect   this makes that happen
    structure      one thing divided into named parts, standing still
    effect         how something LOOKS; seeing it IS understanding it
    quantity       a figure is the whole point

    THIS FIELD DECIDES WHICH RULES APPLY, so choosing it lazily costs more than
    getting it slightly wrong. "structure" is the default that means "I did not
    look", and it is the one to be suspicious of: most beats that got labelled
    structure were really a process with its steps flattened into a row, or a
    cause_effect with the arrow left out. Read the beat again and ask whether
    anything HAPPENS in it. If something happens, it is not structure.

`must_see` — the objects on the screen and what is true between them.
    Written as things, not as sentences to print. This is the field the whole step
    exists for, and there is one test for it:

        DELETE EVERY LABEL. DOES THE PICTURE STILL TEACH?

    If what you have described becomes a row of empty boxes once the words are
    gone, you have written a caption and not a scene. Write what is actually drawn:
    a page with a hole in it, two columns of the same paragraph at different
    weights, an arrow leaving one box and arriving inside another.

      BAD   "three boxes labelled Users, Applications, Hardware"
            ^ delete the labels and it is three boxes. The picture claims nothing;
              the words claimed everything.
      GOOD  "a small figure at the top, a stack of app windows below it, and a
            slab underneath both that the stack physically rests on — the layering
            is the claim, so it survives losing the words"

`changes_from_previous` — what a viewer would notice changing, WITH THE SOUND OFF.
    Empty for the first beat. For every other beat this must name something that
    ADDS, REMOVES or REPLACES a visible thing. Moving the highlight is not a
    change. Adding a parenthetical to a label is not a change. If you cannot name
    one, say so in this field in those words — "nothing changes; hold the previous
    scene" — and the drawing step will honestly hold one picture rather than
    faking two.

`focus` — the ONE object carrying the accent. Exactly one, every time. Name the
    object, not the idea: "the arrow into the frame table", not "the lookup".

AND ONE THING FOR THE WHOLE SHORT
`subject` — what this short is a picture OF. Every beat develops this one thing.
A short whose beats are pictures of four different subjects is four unrelated
diagrams, and a viewer remembers none of them.

BUILD, DO NOT REPEAT
The beats are one continuous explanation, so the scenes are one continuous scene
that develops. Two constraints follow and both are checked downstream:
  * Never describe a scene you have already described. Not just the previous beat
    — ANY earlier beat. A short that goes A, B, A ends where it started.
  * The first beat is the interviewer's QUESTION, and its scene draws the SUBJECT
    as an object — the thing being asked about. It is not a title card, it is not
    "what is being asked", and it is not the answer's code shown early.

DRAW FROM THE MATERIAL, NOT FROM THE PROSE
You are given the section this short came from. What you take from it are the
things it SHOWS: its code, its values, its tables, its numbers. Not its sentences.
A noun from a paragraph nobody in this short mentions is drift.

Use the narration's own words for anything that will end up as a label. If the
beats say "most significant bit", the object is the most significant bit.

Output JSON:
{"subject":"...",
 "beats":[{"ref":"...","concept":"...","relationship":"process|comparison|
   data_movement|hierarchy|cause_effect|structure|effect|quantity",
   "must_see":"...","changes_from_previous":"...","focus":"..."}]}"""

STRATEGY_SYSTEM = STRATEGY_SYSTEM.replace("__RULES__", EDUCATIONAL_VISUAL_RULES)


def plan_strategy(script: Script, section: Section | None = None,
                  feedback: str | None = None,
                  model_override: str | None = None) -> VisualStrategy:
    """
    One call: what every beat of this short has to make the viewer see.

    Cheap relative to what it changes. It is one extra model call per short, on a
    prompt far shorter than the visual brief, and it runs once — the redesign loop
    re-runs the DESIGN step against a strategy that is usually still correct, so a
    short that needs three attempts still pays for one strategy.

    `feedback` carries the vision judge's verdict back in. That path only matters
    when the judge rejected the IDEA rather than the drawing — see
    visuals.design_visuals, which re-plans only when the same frame keeps failing
    on concept_communication, because redrawing a scene that was never going to
    teach is what the old loop did three times in a row.
    """
    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = f"QUESTION: {script.question}\n\nBEATS, in order:\n{beats}\n"

    if section is not None:
        user += f"""
THE READING MATERIAL THIS SHORT CAME FROM — section [{section.section_id}] {section.title}
---
{section.text}
---
"""

    user += (f"\nPlan the composition. Return one entry for each of these refs, in "
             f"this order, using these exact strings: {refs}")

    if feedback:
        user += f"""

YOUR PREVIOUS PLAN PRODUCED FRAMES THAT A JUDGE LOOKED AT AND REJECTED. What it
saw:

{feedback}

These are verdicts on PICTURES, not on wording. If a scene was called text-heavy or
unclear, the fix is a different scene — different objects, a different relationship
made visible — not the same scene described more carefully."""

    return ask_json(STRATEGY_SYSTEM, user, VisualStrategy,
                    model=model_override or config.MODEL_STRATEGIST,
                    max_tokens=3000, label="visual_strategy")


def as_brief(strategy: VisualStrategy, refs: list[str]) -> str:
    """The strategy as the block of text the design step is given.

    Ordered by the beats rather than by the strategy's own list, because a plan
    that came back shuffled would otherwise hand the designer the composition out
    of sequence — which is the bug that made spec_visuals sort refs alphabetically
    and design a build for beats in the wrong order.
    """
    by_ref = strategy.by_ref()
    lines = [f"THE SUBJECT OF THIS SHORT: {strategy.subject}", ""]
    for ref in refs:
        plan = by_ref.get(ref)
        if plan is None:
            lines.append(f"[{ref}] no strategy — design this beat from the dialogue.")
            continue
        lines.append(f"[{ref}]")
        lines.append(f"  concept:      {plan.concept}")
        lines.append(f"  relationship: {plan.relationship}")
        lines.append(f"  must see:     {plan.must_see}")
        if plan.changes_from_previous:
            lines.append(f"  changes:      {plan.changes_from_previous}")
        lines.append(f"  focus:        {plan.focus}")
        lines.append("")
    return "\n".join(lines).rstrip()
