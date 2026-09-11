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
from ..schema import (Script, Section, SectionUnderstanding, VisualStrategy,
                      QuestionWorkflow, TeachingApproach)
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
12. Avoid decorative illustration that does not contribute to understanding.
13. If the concept is a container or mechanism with a well-known real-world
    equivalent (a stack, a queue, a cache, recursion, a linked list, a tree,
    a hash table, a graph), prefer a real-world analogy alongside the actual
    structure over a generic icon or a bare box."""


STRATEGY_SYSTEM = """You are the VISUAL STRATEGIST for a short teaching video.

You decide WHAT A VIEWER MUST SEE. You do not decide how it is drawn, you are not
choosing from a menu of shapes, and you must not describe a layout. Another step
owns that, and it is better at it than you because it can see the renderer.

Your entire job is the question that step cannot answer for itself:

    what should a learner SEE in order to understand this concept?

__RULES__

HOW TO ANSWER IT
For each beat, in order, you write down seven things.

`why_visual` — answer this BEFORE anything else: what, specifically, would a
    viewer NOT get from the narration alone? Not "it helps to see it" — the
    exact thing words leave the viewer guessing at: a spatial relationship
    ("which one sits inside which"), a simultaneous comparison ("both scores at
    once, not one after the other"), a structure that is serial in speech but
    should be instant in a picture ("four fields in one address, seen together
    rather than named in a list"). If you cannot say what would be lost with
    the sound off and the screen blank, you have not found the picture yet —
    keep looking at the beat, do not fall back to "the concept, illustrated".

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

    COUNT THE SUBJECTS BEFORE YOU PICK "process". The warning above pushes away
    from structure and it must not push you into process by default, which is the
    mistake it has actually caused:

      BEAT  "So `#nav .item a` counts to 1,1,1, while `.item .link a` counts to
             0,2,1."
      BAD   process — because "counts" is a verb, so something happens
      GOOD  comparison — there are TWO subjects and neither goes first

    process needs ONE subject moving through steps that have an ORDER, where step 2
    cannot happen before step 1. If you cannot say what would break by running the
    steps backwards, it is not a process.

    comparison is TWO subjects held side by side and weighed. Each side may well
    contain a verb — scoring, counting, waiting, growing — and that does not make
    it a process; it makes it two things doing the same thing differently. The tell
    is the word "while", "whereas", "but", or "and the other", and the fact that
    swapping which side you describe first changes nothing.

    So: one subject with an order -> process. Two subjects weighed -> comparison,
    however much happens inside each of them.

`physical_form` — the PHYSICAL SHAPE of the thing must_see is about to
    describe. `relationship` says what KIND of claim this is; this says what it
    would look like if you built it out of blocks. Exactly one of:

      single_container   one physical container, contiguous positions — a
                          stack, a queue, an array, a fixed set of frames.
                          Slots inside ONE bordered thing.
      linked_nodes        separate objects related only by a pointer or a
                          reference — a linked list, a graph's edges, a chain
                          of promises. Each one genuinely lives somewhere else.
      nested_levels        one thing physically inside or resting on another,
                          two or more levels — an OS above hardware, a folder
                          inside a folder, a page inside a process's space.
      flat_parts           a root or a whole divided into several NAMED,
                          NON-NESTED parts, or several distinct things that
                          depend on one shared source — a kernel and what
                          depends on it, an address split into fields.
      two_sides             exactly two things held up at once to be weighed.
      single_object         one thing, not a container of several positions —
                          its own state, its own look, a value changing.
      not_applicable        the claim is a rendered effect or a figure, and
                          none of the above is really what is being shown.

    ASK THIS BEFORE YOU ANSWER: if I built this out of blocks on a table, what
    would be sitting next to what? A stack and a linked list can BOTH be
    `relationship: process` — both fill up over time — and still need the
    opposite shape, because a stack is slots inside one box
    (single_container) and a linked list is separate boxes joined by string
    (linked_nodes). Getting `relationship` right and `physical_form` wrong
    still sends the drawing to the wrong picture.

    nested_levels is NOT the same as flat_parts, and the two are confused
    constantly: "the OS sits between applications and hardware" is
    nested_levels — one is layered on the one below it, an arrangement, not a
    list. "The kernel depends on the scheduler and the driver" is flat_parts —
    two named, separate things related to one root, neither resting on the
    other. If nothing is INSIDE or UNDER anything else, it is not
    nested_levels, however hierarchical the idea sounds when spoken.

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
 "beats":[{"ref":"...","why_visual":"...","concept":"...","relationship":"process|comparison|
   data_movement|hierarchy|cause_effect|structure|effect|quantity",
   "physical_form":"single_container|linked_nodes|nested_levels|flat_parts|two_sides|single_object|not_applicable",
   "must_see":"...","changes_from_previous":"...","focus":"..."}]}"""

STRATEGY_SYSTEM = STRATEGY_SYSTEM.replace("__RULES__", EDUCATIONAL_VISUAL_RULES)


#: STEP 11 — the human-review counterpart to STRATEGY_SYSTEM, the same shape
#: as TEACHING_APPROACH_REGENERATE_SYSTEM one stage earlier: the FULL
#: strategist brief above (every rule, the field-by-field instructions, the
#: output shape) PLUS one more block that turns "plan it" into "reconsider
#: what you planned, given this specific complaint". Built by extension
#: rather than restated, for the same reason STRATEGY_SYSTEM's own rules are
#: imported rather than copied: a rule changed in one place must not drift
#: out of sync with the other.
VISUAL_STRATEGY_REGENERATE_SYSTEM = STRATEGY_SYSTEM + """

YOU ARE NOW RECONSIDERING A VISUAL PLAN THAT WAS ALREADY DECIDED, because a
human reviewer read it, beat by beat, and wants something about it to change.
You are given the PREVIOUS complete plan and the reviewer's specific reason,
and your job is a fresh, COMPLETE plan that addresses it — not a patch to
the one beat the reason happens to name.

RECONSIDERING, SPECIFICALLY:
- Read the reviewer's reason and address it directly. "Beat 3 is basically a
  code screenshot" means that beat's relationship/physical_form/must_see
  should very likely move away from code; "I can't tell the two sides apart"
  points at relationship=comparison with physical_form=two_sides and a
  must_see that puts both on screen at once; "this doesn't show anything
  changing" points at relationship=process with a real state change in
  changes_from_previous. Do not produce a plan that ignores what was
  actually asked for.
- Beats the reviewer's reason does not touch MAY end up close to where they
  started, if, having genuinely weighed the reason against the concept, the
  original scene still teaches it best. Even so, decide each one again —
  copying a beat forward unexamined is not reconsidering it.
- Produce the COMPLETE plan again: `subject` and one full beat entry for
  EVERY ref listed in the previous plan below, in the same order — never
  only the beat(s) the reason points at.
- THE APPROVED TEACHING APPROACH AND THE CODE RULE STILL APPLY, UNCHANGED BY
  THIS REQUEST. A reviewer asking for a clearer picture is not asking to
  override the approved approach or default to code/text — the same
  DO NOT DEFAULT TO CODE OR TEXT instruction above still governs every beat
  here."""


#: STEP 10 — one paragraph of visual-specific guidance per TeachingApproachKind,
#: added to the prompt ONLY when plan_strategy is given an `approach` (see
#: plan_strategy_for_workflow below). The counterpart to
#: skills.script._APPROACH_GUIDANCE one stage earlier — same seven kinds, same
#: "translate the teaching decision into an actual visual explanation" job,
#: but pointed at BeatStrategy's own fields (relationship, physical_form,
#: must_see) rather than at spoken narration.
_VISUAL_APPROACH_GUIDANCE: dict[str, str] = {
    "process_demonstration": (
        "Prefer relationship=process, with physical_form matching the actual "
        "mechanism (single_container for a stack/queue/array, linked_nodes for "
        "a linked structure). must_see should show a STATE CHANGING — "
        "something arriving, leaving, or moving between beats — not a static "
        "description of what the steps are."
    ),
    "comparison": (
        "Prefer relationship=comparison and physical_form=two_sides. must_see "
        "must put BOTH things being compared on screen AT ONCE — the "
        "simultaneous contrast is the picture; showing one side per beat is "
        "not this approach."
    ),
    "analogy": (
        "The scene may draw the analogy itself, but at least one beat's "
        "must_see should connect it back to the real concept — name what the "
        "analogy's parts correspond to in the actual mechanism, not only "
        "depict the analogy in isolation."
    ),
    "real_world_example": (
        "Show the real-world scenario, but must_see should make the link to "
        "the technical concept explicit — both the scenario and the concept "
        "it stands for need to be visible, not the scenario alone."
    ),
    "conceptual_visual": (
        "Prioritise relationship values of hierarchy, structure, cause_effect "
        "or process, and a physical_form that commits to an actual shape "
        "(never not_applicable) — this approach exists specifically for "
        "relationships, movement, state and structure. A beat that comes back "
        "as plain text or a name displayed large is a failure of this "
        "approach, not a legitimate answer for it."
    ),
    "code": (
        "must_see may legitimately describe the actual code being shown and "
        "explained — this is the one approach where that is the right call, "
        "because the code itself is the learning objective, not a "
        "convenience."
    ),
    "direct_explanation": (
        "Still find the clearest CONCEPT visual available — a structure, a "
        "state, a relationship — rather than defaulting to a block of text or "
        "a code snippet because nothing else seems necessary. 'Direct' "
        "describes the NARRATION style; it is not a licence for the picture "
        "to stop being a picture."
    ),
}


def plan_strategy(script: Script, section: Section | None = None,
                  feedback: str | None = None,
                  model_override: str | None = None,
                  understanding: SectionUnderstanding | None = None,
                  approach: TeachingApproach | None = None) -> VisualStrategy:
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

    `understanding` IS NEW, AND IT CLOSES A REAL GAP. write_script has read
    understanding_for(section) since that step existed — the section's own
    core_idea, teaching_sequence and confusion_plan — and this step never has,
    despite being the one that decides "what should a learner SEE in order to
    understand this concept?", the exact question understand() already answered
    once for the words. Handed only the beats, this step had to re-derive "what
    is this short really about" from four lines of dialogue with no access to
    the deeper reading that produced them — so `subject` came out grounded in
    the SCRIPT's phrasing rather than the SECTION's actual central idea, and a
    beat aimed at a misconception had no way to know one had been identified.
    Optional and additive: understanding can be None (a quarantined reading, or
    a caller that has not been updated), and the prompt below degrades to
    exactly its previous behaviour when it is.

    `approach` IS STEP 10's ADDITION, and OPTIONAL — every existing call site
    omits it and gets BYTE-IDENTICAL behaviour to before, the same contract
    `understanding` already has. Passed (see plan_strategy_for_workflow, the
    gated entry point that always supplies one from an approved
    QuestionWorkflow), it adds ONE more guidance block to the SAME prompt and
    the SAME call — never a second call to translate it first. It does NOT
    change WHAT THIS STEP OWNS: no template is chosen here either way (see
    this module's own "WHAT THIS STEP MUST NOT DO"); `approach` only steers
    which RELATIONSHIP, PHYSICAL FORM and SCENE the strategist reaches for.
    """
    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = f"QUESTION: {script.question}\n\nBEATS, in order:\n{beats}\n"

    if understanding is not None:
        brief = understanding.as_brief()
        if brief:
            user += f"""
WHAT THIS SECTION ACTUALLY TEACHES — read this before deciding `subject`.
This is the same reading write_script used to write the beats above, not a
second opinion: ground `subject` in its core_idea rather than re-deriving the
short's subject from the dialogue alone, and if a confusion_plan is present
below, treat correcting it as something the COMPOSITION should show (the
wrong state next to the right one, or the corrected state replacing it) —
not only something the narration says.

THE COMPOSITION BUILDS IN THE SAME ORDER teaching_sequence lays out below, and
that order is a decision about DIFFICULTY, not just about topic — it exists
because a beginner cannot meet the hardest version of the idea first. So the
EARLY beats' scenes are the simple, concrete, recognisable state (what a
learner already has some purchase on — an empty container, a plain everyday
version of the object, the "before" of a change) and only the LATER beats'
scenes introduce the mechanism's own vocabulary and precision (the named
fields, the index arithmetic, the specific rule). A short whose FIRST frame is
already the most technically dense picture it ever shows has skipped the
climb teaching_sequence describes and asked the viewer to arrive at the top
cold. This is not about simplifying what gets said — the words can be exact
from beat one — it is about which PICTURE earns the right to be shown first.
---
{brief}
---
"""

    if section is not None:
        user += f"""
THE READING MATERIAL THIS SHORT CAME FROM — section [{section.section_id}] {section.title}
---
{section.text}
---
"""

    # STEP 10: THE APPROVED TEACHING PLAN. The LAST and MOST SPECIFIC piece of
    # guidance, placed directly before the instruction to plan — same reason
    # skills/script.py places its own equivalent block right before the
    # section it is the final word on. `approach.rationale` is INCLUDED, not
    # summarised: it is the human-approved reason this device fits the
    # concept, and repeating it here is cheaper and more faithful than this
    # step re-deriving its own reason from the approach name alone.
    if approach is not None:
        approach_line = approach.primary
        if approach.combined_with:
            approach_line += f", combined with {', '.join(approach.combined_with)}"
        user += f"""
THE APPROVED TEACHING APPROACH FOR THIS SHORT: {approach_line}
{_VISUAL_APPROACH_GUIDANCE.get(approach.primary, "")}
"""
        for extra in approach.combined_with:
            guidance = _VISUAL_APPROACH_GUIDANCE.get(extra)
            if guidance:
                user += f"ALSO, for the combined approach ({extra}): {guidance}\n"
        if approach.rationale:
            user += f"WHY THIS APPROACH WAS CHOSEN: {approach.rationale}\n"
        user += """
DO NOT OVERRIDE THE APPROVED APPROACH, AND DO NOT DEFAULT TO CODE OR TEXT. In
particular, do not describe a scene built around showing code merely because
the section happens to contain some — use a code-centred must_see only if the
approved approach above IS `code`. The question that governs every beat is
still "what must a learner SEE to understand this concept", never "what text
or code is sitting in the material".
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


def reconsider_visual_strategy(workflow: QuestionWorkflow, section: Section,
                               reason: str, previous_strategy: VisualStrategy,
                               understanding: SectionUnderstanding | None = None,
                               ) -> VisualStrategy:
    """
    One LLM call: reconsider workflow's visual plan given a human's stated
    reason and the PREVIOUS complete plan — Step 11's counterpart to
    skills.teaching_approach.reconsider_teaching_approach, one stage later.

    `reason` IS ASSUMED NON-BLANK — schema.VisualStrategyRegenerationAttempt's
    own validator is what actually enforces that; review.regenerate_visual_plan
    builds the attempt (which raises first) rather than this function
    re-checking a rule it does not own.

    REUSES plan_strategy's OWN INPUTS, NOT A SECOND SCRIPT OR PLAN — the same
    script beats, section, understanding and approved teaching approach that
    plan_strategy_for_workflow already reads, computed here the same way
    (the ref-dedup loop below is the one from plan_strategy, not a
    reinterpretation of it) so a reconsidered plan answers for the EXACT
    same refs the original one did. The previous plan is shown back to the
    model via as_brief — the same rendering a human reviewer would have
    read — never re-serialized ad hoc.

    ALWAYS RETURNS A COMPLETE VisualStrategy, never a patch — see
    VISUAL_STRATEGY_REGENERATE_SYSTEM's own "RECONSIDERING, SPECIFICALLY".
    The previous plan is shown to the model for context, not as a baseline
    it edits in place.
    """
    if workflow.script is None:
        raise ValueError(
            f"cannot reconsider visuals for {workflow.selection.topic.id}: "
            f"no script has been generated yet")
    approach = workflow.approved_teaching_approach
    script = workflow.script

    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = f"QUESTION: {script.question}\n\nBEATS, in order:\n{beats}\n"

    if understanding is not None:
        brief = understanding.as_brief()
        if brief:
            user += f"""
WHAT THIS SECTION ACTUALLY TEACHES:
{brief}
"""

    user += f"""
THE READING MATERIAL THIS SHORT CAME FROM — section [{section.section_id}] {section.title}
---
{section.text}
---
"""

    if approach is not None:
        approach_line = approach.primary
        if approach.combined_with:
            approach_line += f", combined with {', '.join(approach.combined_with)}"
        user += f"""
THE APPROVED TEACHING APPROACH FOR THIS SHORT: {approach_line}
{_VISUAL_APPROACH_GUIDANCE.get(approach.primary, "")}
"""
        if approach.rationale:
            user += f"WHY THIS APPROACH WAS CHOSEN: {approach.rationale}\n"

    user += f"""
THE PREVIOUS PLAN, WHICH A HUMAN REVIEWED:
{as_brief(previous_strategy, refs)}

THE REVIEWER'S REQUESTED CHANGE — address this directly:
{reason}

Reconsider the visual plan. Return one entry for each of these refs, in this
order, using these exact strings: {refs}"""

    return ask_json(VISUAL_STRATEGY_REGENERATE_SYSTEM, user, VisualStrategy,
                    max_tokens=3000, label="visual_strategy_regenerate")


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
        if plan.why_visual:
            lines.append(f"  needs a picture because: {plan.why_visual}")
        lines.append(f"  concept:      {plan.concept}")
        lines.append(f"  relationship: {plan.relationship}")
        if plan.physical_form != "not_applicable":
            lines.append(f"  physical form: {plan.physical_form}")
        lines.append(f"  must see:     {plan.must_see}")
        if plan.changes_from_previous:
            lines.append(f"  changes:      {plan.changes_from_previous}")
        lines.append(f"  focus:        {plan.focus}")
        lines.append("")
    return "\n".join(lines).rstrip()


def plan_strategy_for_workflow(workflow: QuestionWorkflow, section: Section,
                               feedback: str | None = None,
                               understanding: SectionUnderstanding | None = None,
                               ) -> QuestionWorkflow:
    """
    Step 10's entry point: plan the visual strategy for a FULLY APPROVED,
    SCRIPTED workflow — using its approved script as the teaching sequence
    (see plan_strategy's own "no second script-writing call" contract) and
    its approved teaching approach to steer what each beat should show — and
    attach the result to workflow.visual_strategy.

    THE ONE GATE, THE SAME SHAPE AS write_script_for_workflow ONE STAGE
    EARLIER: workflow.approved_topic, workflow.framing,
    workflow.approved_teaching_approach AND workflow.script must all be set.
    All four raise ValueError, checked BEFORE any LLM call, so a workflow
    that fails any of them spends nothing.

    NO SCRIPT-GENERATION LOGIC LIVES HERE, AND NO SEPARATE CALL TO TRANSLATE
    FRAMING OR THE APPROACH FIRST — plan_strategy already accepts
    `understanding` and (Step 10) `approach` directly, so this function's
    only job is the gate and handing plan_strategy exactly what it needs:
    THE APPROVED SCRIPT ITSELF (workflow.script — the actual beats a viewer
    will hear, not the topic or the framing again), the section, and the
    approved teaching approach. One call, same as write_script_for_workflow's
    own contract one stage earlier.

    ONLY workflow.visual_strategy IS WRITTEN. selection, question_approval,
    framing, teaching_approach, teaching_approach_approval and script all
    pass through model_copy untouched.
    """
    if workflow.approved_topic is None:
        raise ValueError(
            f"cannot plan visuals for {workflow.selection.topic.id}: "
            f"question_approval.status={workflow.question_approval.status!r}, "
            f"not 'approved'")
    if workflow.framing is None:
        raise ValueError(
            f"cannot plan visuals for {workflow.selection.topic.id}: "
            f"this workflow has no framing")
    approach = workflow.approved_teaching_approach
    if approach is None:
        raise ValueError(
            f"cannot plan visuals for {workflow.selection.topic.id}: "
            f"teaching_approach_approval.status="
            f"{workflow.teaching_approach_approval.status!r}, not 'approved'")
    if workflow.script is None:
        raise ValueError(
            f"cannot plan visuals for {workflow.selection.topic.id}: "
            f"no script has been generated yet")

    strategy = plan_strategy(workflow.script, section, feedback=feedback,
                             understanding=understanding, approach=approach)
    return workflow.model_copy(update={"visual_strategy": strategy})
