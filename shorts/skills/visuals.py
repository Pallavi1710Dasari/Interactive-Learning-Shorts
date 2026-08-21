"""SKILLS 3 & 4 — visual-spec, then diagram-render.

Non-negotiable: technical content becomes code-generated SVG, never an image
model. Image models produce confident nonsense for page tables and flow diagrams.
"""
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel
from ..schema import Script, Visual, Section
from ..llm import ask_json
from .. import config, usage


class VisualPlan(BaseModel):
    visuals: list[Visual]


SPEC_SYSTEM = """You design the visuals for one short video, as a SINGLE COMPOSITION THAT BUILDS.

THE RULE THAT MATTERS MOST
The beats of a short are one continuous explanation, so the visuals are one
continuous diagram — not four unrelated pictures. Decide ONE base composition for
the whole short, then for each beat say what is ADDED or HIGHLIGHTED on it.

A viewer who watched four different diagrams remembers none of them. A viewer who
watched one diagram assemble itself remembers the assembled thing, and that is the
whole point: the picture is the thing they carry out of the video.

So each spec must (a) restate the base composition, and (b) name what changes for
this beat. Beat 3's spec is not "a table" — it is "the same three-row table from
beat 2, with row 2 now highlighted and an arrow entering it from the left".

THE LAST BEAT IS A TAKEAWAY CARD
The final visual is not another step of the diagram. It is the one thing to
remember, composed to be recalled weeks later: the completed composition reduced
to its essential shape, with the single sentence of the takeaway set large. Say so
explicitly in its spec.

TYPE, for each distinct visual_ref:
  "diagram" — anything structural or technical: tables, memory layouts, address
              splits, state transitions, request flows, before/after states, and
              every takeaway card. ALWAYS use this for technical content.
  "image"   — decorative background only. Never carries information. Its spec must
              not name any technical noun (memory, address, page, frame, table,
              cache, bit, queue, stack, tree, flow, architecture, register). If you
              cannot describe it without one, it is not decorative — use "diagram".
              When in doubt, do not choose "image".
  "text"    — a single number or term shown large, no illustration needed.

DRAW WHAT IS BEING SAID, AND NOTHING ELSE
The picture and the voice must be about the same thing at the same moment. The
commonest complaint about these shorts is a diagram that is clearly well made and
clearly about something adjacent — the narration explains why RAM loses data on
power-off, and the diagram is a CPU wired to "currently running programs" and
"saved files", which is a fine picture of something nobody is talking about.

So every label you specify must use the NARRATION'S OWN WORDS. If the beats say
"most significant bit", the label is "Most significant", not "Highest". If a noun
is not in the beats, it does not go on the screen. Introducing a new object the
voice never mentions makes the viewer stop listening and start reading.

ONE IDEA PER FRAME. A frame illustrates the ONE thing its beat says. If you find
yourself specifying a second mechanism to give context, delete it — the previous
frame already established the context, because this is one composition that builds.

Then write `spec`: concrete enough that someone could draw it without seeing the
script. Name every label exactly as it should appear. Two or three sentences.

KEEP THE LABELS SHORT. Whatever you name is drawn as-is on a phone screen, and SVG
does not wrap text, so a long label overflows its box. Every label you specify must
be 3 words or fewer and under 18 characters: "MMU checks PTE", not "MMU checks Page
Table Entry"; "Backing store", not "Backing Store (disk)". Specify at most 5 boxes
in any single row.

Output JSON: {"visuals":[{"ref":"...","type":"diagram|image|text","spec":"..."}]}"""

SVG_SYSTEM = """You draw ONE frame of a technical diagram as an SVG for a VERTICAL phone video.

You are drawing one beat of a short. The other beats' specs are given so that your
frame belongs to the same composition as theirs: the same objects in the SAME
PLACE, at the same size, in the same style. Only the emphasis and the added parts
change between beats. A viewer must feel the diagram growing, not being swapped.

CANVAS
- viewBox="0 0 1080 1080". Nothing outside those bounds, nothing clipped.
- Transparent background. Do not draw a background rect.
- Usable area is x 60..1020 and y 60..940. USE IT ALL — fill the height, do not
  crowd everything into the top half and leave the bottom empty.
- Below y=940 draw nothing: the characters and the caption sit there.
- Three bands, so successive frames line up:
    y   60..190   title
    y  200..820   the diagram itself, vertically centred in this band
    y  830..940   one supporting label or the takeaway line

TEXT DOES NOT WRAP IN SVG — THIS IS THE MOST COMMON WAY THESE COME OUT BROKEN
There is no automatic line breaking. A <text> longer than its box does not wrap,
it overflows and is unreadable. So you must do the arithmetic yourself:

- At font-size F, one character is about 0.55 x F wide. A label of N characters
  needs about N x 0.55 x F pixels.
    "MMU checks Page Table Entry" is 27 chars at F=40 -> 27 x 22 = 594px wide.
    A 200px box CANNOT hold it. Either the box is 594px wide, or the label is
    split across lines, or the label is shortened.
- To put two lines in a box, emit TWO separate <text> elements 1.15 x F apart.
  A single <text> with a newline in it renders as one long line.
- Keep every line to 18 characters or fewer, and every box label to 3 words or
  fewer. Shorten aggressively: "MMU checks PTE", "Backing store", "Free frame".
- Centre with text-anchor="middle" at the box's centre x, and set y to the box's
  centre y plus about 0.35 x F so it sits on the optical centre.
- Check the widest label in your drawing against its box before you finish. A
  label that overflows its box is a broken diagram, not a cosmetic issue.
- NEVER put a transform or a rotate on a <text>. Rotated labels come out
  overlapping and illegible on a phone.

LAYOUT — the part that separates a designed diagram from a generated one
- Work on a grid. Align edges and centres; equal gaps between sibling shapes.
  Two boxes that are nearly aligned look like a mistake; exactly aligned looks
  deliberate.
- Pick coordinates that work for the BUSIEST frame in the composition and reuse
  them in every frame. A shared object must sit at IDENTICAL x/y in every frame
  it appears in — that is what makes the diagram look like it is being added to
  rather than redrawn. Do not rescale or reflow it between frames.
- At most 4 boxes in a row across 960px, which is 200px each with 50px gaps. If the
  labels do not fit in that, use fewer boxes or stack them in two rows.

ARROWS AND THEIR LABELS
- A 50px gap between two boxes has room for an arrow and NOTHING ELSE. A label
  dropped in there prints straight across the box next door, which is the single
  most common way one of these comes out looking broken.
- So a labelled arrow needs its label ABOVE or BELOW the arrow line, clear of every
  box: at least 40px above the arrow, or 40px below it, in empty canvas.
- If there is no clear space for the label, leave the arrow unlabelled. The
  narration is saying it anyway; an unlabelled arrow reads fine, a label printed
  over a box does not.
- Keep arrows straight and horizontal or vertical wherever possible. Curved arrows
  looping back across the drawing cross the boxes and each other; if a step returns
  to the start, route it well below the row, in the clear.
- One clear reading order, top to bottom. The eye should land on the title, then
  the focus element, then the detail — never wander.
- Group related things: align them in a row or column, or enclose them in one
  rounded container with a quiet stroke, so the structure reads before the labels.

SIMPLE BEATS COMPLETE — THE MOST COMMON FAILURE IS TOO MUCH, NOT TOO LITTLE
- 3 to 6 shapes. Not 9. This is watched on a phone, for four seconds, once, while
  someone is talking over it. A frame that needs studying has already failed.
- Draw ONLY what this beat's narration is about. Every extra object is a thing the
  viewer must rule out before finding the one that matters.
- Use the narration's own nouns as labels. A label naming something the voice never
  says sends the viewer hunting for what they missed.
- If the beat's idea is genuinely one number or one comparison, then one number or
  two boxes IS the frame. Do not decorate it up to a diagram.
- Empty space is not waste; it is what makes the remaining marks legible.

TYPE
- font-family="Inter, Helvetica, sans-serif".
- A real hierarchy, not one size everywhere:
    title                             56-64px, font-weight="700"
    the one number that matters        72-96px, font-weight="700"
    box and node labels               36-44px
    secondary and axis labels         32-36px, fill="#8A8880"
  Never below 32px. Use text-anchor to centre properly.

COLOUR — this palette and nothing else
    #E1F5EE  fill for boxes and panels
    #1D9E75  primary stroke, arrows, headings
    #0F6E56  deeper green for a second grouping
    #F2B14B  AMBER — the one element the narration is about RIGHT NOW. Exactly one
             shape per frame, never more. This is what the eye finds first, and
             moving it between beats is how the viewer follows the explanation.
    #E8735A  coral — only for a thing being rejected, lost, wasted, or wrong
    #2C2C2A  text on light fills
    #8A8880  muted labels and secondary text
- Everything not being talked about stays quiet: pale fill, thin stroke, muted
  label. A frame where everything is emphasised communicates nothing.

MAKE IT MEMORABLE — this is the brief, not a nicety
This diagram has to be recallable weeks later, from a syllabus of many shorts.
- Give it ONE strong shape a viewer could sketch from memory: a split bar, a
  ladder of rows, a fork, a loop, a before/after pair. Decide what that shape is
  and commit the whole layout to it.
- Show the mechanism, not a restatement of the words. If the idea is "the value
  doubles each step", the doubling must be visible in the drawing — steps growing,
  a bar twice as long — not written in a caption.
- Anchor abstract things to something countable: number the rows, mark the
  positions, draw the actual bits. Concrete beats abstract for recall.
- If this frame is the TAKEAWAY CARD, drop the working detail: the essential shape,
  large, with the one sentence to remember beneath it. Set that sentence at 52-64px
  and BREAK IT INTO LINES YOURSELF — one <text> per line, at most 24 characters
  each, text-anchor="middle" at x="540", lines 1.2 x font-size apart. A single long
  <text> runs off both edges of the canvas, which is the most visible way one of
  these can fail.

ACCURACY BEATS DECORATION. Every label, number, and state must match the narration
and the source. If the narration says the valid bit is clear, draw it clear. If the
source's example is 1011, draw 1011 and not 1010. A wrong diagram is worse than no
diagram, and a diagram that contradicts the voice is the worst of all.

TECHNICAL
- No <style> blocks, no CSS classes, no external refs, no <image>, no scripts, no
  animation. Inline presentation attributes only.
- Use <rect rx="..."> for rounded boxes, <path> for arrows with a visible head.

Output the raw <svg>...</svg> only. No fences, no explanation."""


def spec_visuals(script: Script) -> dict[str, Visual]:
    # In beat order, not sorted: the specs describe a composition that builds, so
    # the model has to see the sequence it is designing for. Sorting the refs
    # alphabetically handed it the beats shuffled.
    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = (f"QUESTION: {script.question}\n\nBEATS, in order:\n{beats}\n\n"
            f"Design the composition and assign one visual to each of these refs, "
            f"in this order: {refs}\nThe last one, {refs[-1]}, is the takeaway card.")
    plan = ask_json(SPEC_SYSTEM, user, VisualPlan, max_tokens=3000, label="visual_spec")
    return {v.ref: v for v in plan.visuals}


def render_diagrams(visuals: dict[str, Visual], script: Script, section: Section) -> dict[str, Visual]:
    """
    Fill in .svg for every diagram-type visual. One LLM call per diagram.

    Drawn concurrently: a short has 4-5 diagrams and each call takes several
    seconds, so doing them in sequence made building a single short the slowest
    thing in the product. The calls are independent, so wall-clock time drops to
    roughly one diagram instead of the sum of all of them.
    """
    if config.STUB:
        return visuals                      # stub visuals are all type="text"

    todo = [(ref, v) for ref, v in visuals.items() if v.type == "diagram"]
    if not todo:
        return visuals

    # Every frame is given the whole arc, so it can place its shapes where the
    # neighbouring frames place theirs. Without it each call invented its own
    # layout and the "one composition that builds" became four unrelated pictures.
    arc = "\n".join(f"  {i+1}. [{ref}] {visuals[ref].spec}"
                    for i, (ref, _) in enumerate(todo))

    with ThreadPoolExecutor(max_workers=len(todo)) as pool:
        list(pool.map(lambda rv: _draw_one(rv[0], rv[1], script, section, arc, len(todo)), todo))
    return visuals


def _draw_one(ref: str, v: Visual, script: Script, section: Section,
              arc: str, total: int) -> None:
    """
    Draw one diagram, in place. Never raises — a missing SVG is a grader's job.

    Drawn up to twice. The model cannot see what it drew, so the overflowing label
    and the rotated caption are mistakes it has no way to notice; checks.svg_problems
    reads them straight off the markup for free, and a second attempt carrying that
    list fixes them far more often than not. This is the same failed-then-passed
    loop the scripts get, applied to the pictures.
    """
    from ..llm import client, _reasoning as reasoning
    from .. import checks

    narration = " ".join(b.line for b in script.beats if b.visual_ref == ref)
    quotes = " ".join(b.source_quote or "" for b in script.beats
                      if b.visual_ref == ref and b.source_quote)
    base = (
        f"THE FULL COMPOSITION, frame by frame — yours must match the others:\n{arc}\n\n"
        f"YOU ARE DRAWING FRAME [{ref}] of {total}.\n"
        f"ITS SPEC: {v.spec}\n\n"
        f"NARRATION PLAYING OVER IT: {narration}\n\n"
        + (f"THE SOURCE SENTENCE THIS FRAME MUST AGREE WITH: {quotes}\n\n" if quotes else "")
        + f"SOURCE OF TRUTH [{section.section_id}]:\n{section.text}"
    )

    prompt = base
    for attempt in (1, 2):
        try:
            resp = client().messages.create(
                model=config.MODEL_DIAGRAM,
                max_tokens=8000,
                system=SVG_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                **reasoning(config.MODEL_DIAGRAM, False),
            )
            usage.record("diagram", config.MODEL_DIAGRAM, resp)
            svg = "".join(b.text for b in resp.content if b.type == "text").strip()

            # Both tags, not just the opening one. A diagram truncated at max_tokens
            # has "<svg" and no "</svg>", and rindex() then raises mid-pipeline —
            # killing the run for every remaining topic. Leaving .svg as None instead
            # lets check_visuals_resolved report it as a normal grader failure.
            if "<svg" not in svg or "</svg>" not in svg:
                reason = "truncated" if resp.stop_reason == "max_tokens" else "no <svg> in output"
                print(f"    ! diagram {ref}: {reason} — leaving it unrendered")
                return

            candidate = svg[svg.index("<svg"):svg.rindex("</svg>") + 6]
            problems = checks.svg_problems(candidate, collisions=True,
                                           max_shapes=checks.MAX_SHAPES)

            # Keep the frame either way: a diagram with one wide label still beats
            # no diagram. The retry is an attempt to improve it, not a gate.
            if not problems or attempt == 2:
                v.svg = candidate
                if problems:
                    print(f"    ~ diagram {ref}: still {len(problems)} text issue(s) "
                          f"after a redraw — keeping it")
                return

            v.svg = candidate
            print(f"    ~ diagram {ref}: {problems[0][:80]} — redrawing")
            prompt = (base + "\n\nYOUR PREVIOUS ATTEMPT HAD UNREADABLE TEXT:\n"
                      + "\n".join(f"- {p}" for p in problems[:6])
                      + "\n\nRedraw the whole frame with those fixed. Same layout, same "
                        "coordinates for shared objects — shorten the labels or split "
                        "them across separate <text> lines.")
        except Exception as e:
            print(f"    ! diagram {ref}: {type(e).__name__}: {e} — leaving it unrendered")
            return
