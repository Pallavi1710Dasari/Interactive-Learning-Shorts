"""SKILLS 3 & 4 — choose the composition, then render it.

Non-negotiable: technical content becomes code-generated SVG, never an image
model. Image models produce confident nonsense for page tables and flow diagrams.

AND NOT MODEL-PLACED SVG EITHER, WHICH IS THE CHANGE HERE
This used to ask a model for raw <svg> and then police it: checks.svg_problems read
the markup for overflowing and colliding labels, and _draw_one redrew up to three
times carrying that list. It never converged. Rendered and inspected, the finished
frames still carried around twenty label problems per pair of shorts on every model
tried — "External frag" printed on top of "No single block", column captions across
the tables they labelled — and because a missing diagram is worse than a flawed one,
_draw_one kept the frame regardless. So broken frames shipped by design.

The cause was not the wording of the brief. Placing SVG by hand means doing layout
arithmetic with no way to see the result, and no model can check its own work there.

So the model no longer places anything. It picks one of seven templates and supplies
the words; skills/layout.py computes every coordinate and fits every label to the
box that holds it. Overlap is not graded any more because it cannot be constructed.
That also makes drawing FREE — rendering is local, so the diagram calls that were
82% of the bill are gone.
"""

from pydantic import BaseModel
from ..schema import Script, Visual, Section, Frame
from ..llm import ask_json
from . import layout


class FramedVisual(BaseModel):
    ref: str
    spec: str
    frame: Frame


class VisualPlan(BaseModel):
    visuals: list[FramedVisual]


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

NAME THE FOCUS, AND NAME WHAT CARRIES OVER
Because the composition builds, every spec after the first has two parts the
drawing step depends on, and both must be explicit:

  CARRIED OVER — the objects already on screen from the previous beat, which must
                 be drawn in the same place, unchanged and quiet.
  FOCUS        — the ONE object this beat is about. Exactly one. It is the thing
                 that gets the accent colour, it is drawn LARGER than everything
                 else in the frame, and it is the only thing the viewer is asked to
                 look at while this line is spoken.

A composition of equal parts has no focus. If your base composition is four
same-sized boxes in a row, it is wrong however neatly it is drawn — the viewer is
given nothing to look at first. Build the composition around one dominant shape and
let the beats move the emphasis around inside it.

Write them in those words. "Carried over: the three-row table and the MMU box.
Focus: row 2." A spec that does not say which single object is the focus produces
a frame where everything is emphasised, which communicates nothing.

Then write `spec`: concrete enough that someone could draw it without seeing the
script. Name every label exactly as it should appear. Two or three sentences.

CHOOSE A TEMPLATE, DO NOT DRAW
You do not place anything on the canvas. You choose the SHAPE of each frame and
supply its words; the renderer computes every coordinate and fits every label to
its box. There are seven shapes. Pick the one the sentence actually needs.

  "bar"      One row of equal cells. For anything countable laid out in a line:
             physical memory, frames, slots, a timeline.
             -> cells: up to 10, each {label, role}. cells_title names the row
                ("Physical memory").
  "mapping"  Two columns with arrows between them, ROW BY ROW. For a
             correspondence between two sets of things: these pages live in those
             frames, this key finds that entry.
             -> left, right: up to 4 each. left_title, right_title.
             GIVE THE TWO COLUMNS THE SAME NUMBER OF BOXES. A mapping is a
             row-for-row claim, and an arrow is only drawn where both sides have a
             box — so two boxes facing four renders as two arrows and two
             unexplained boxes, which reads as a diagram with pieces missing.
  "split"    ONE wide bar cut into named parts. For one thing divided into fields:
             an address into page number and offset.
             -> parts: up to 3.
  "flow"     Steps top to bottom with arrows. For a sequence of events:
             what happens on a page fault.
             -> steps: up to 4.
  "table"    A header row and rows, one of them highlighted. For lookups and
             comparisons: a page table, internal versus external.
             -> columns: up to 3, rows: up to 4, each {cells, role}.
  "stat"     One number or term, very large, with a caption. For a frame whose
             whole content is a figure: "4 GB".
             -> value, caption.
  "takeaway" The last frame. One sentence, set large, nothing else.
             -> caption: the sentence to remember.

PICK THE TEMPLATE FROM THE RELATIONSHIP, NOT FROM THE SUBJECT
Ask what the sentence CLAIMS, and the template follows:

  one thing divides into named fields    -> "split"
  two sets correspond, row for row       -> "mapping"
  a sequence of events in order          -> "flow"
  countable slots in a line              -> "bar"
  a lookup, or two things compared       -> "table"
  a single figure is the whole point     -> "stat"

The commonest wrong choice is "mapping" for something that is really a "split". A
logical address is NOT a mapping from "logical address" to "page number": it is one
address CUT INTO a page number and an offset, which is "split" with two parts. Drawn
as a mapping it becomes three left boxes pointing at two right boxes, which claims
a correspondence that does not exist and contradicts the very sentence being spoken.
Whenever a column would contain both a whole and its own parts, you wanted "split".

ROLES ARE HOW YOU POINT, AND THERE IS EXACTLY ONE HERO
Every cell, box and row takes a role, and the role decides its colour:
  "hero"   the ONE thing this beat is about. Exactly one per frame, never two.
           This is the element the viewer's eye is sent to.
  "plain"  present and relevant, but not what is being said right now.
  "lost"   something wasted, rejected, invalid or unusable. Used sparingly.
  "quiet"  context the viewer should not read yet.
Moving the hero between beats, on the same template, is how the explanation is
carried. That is the "one composition that builds" rule, made concrete: keep the
SAME template and the SAME cells across the beats of a short, and change which one
is the hero.

KEEP THE LABELS SHORT — 14 CHARACTERS OR FEWER
The renderer will shrink a long label, wrap it to two lines, and finally truncate
it with an ellipsis rather than let it overflow. Nothing breaks, but a truncated
label is still a worse label. "MMU checks PTE", not "MMU checks Page Table Entry".
"Backing store", not "Backing Store (disk)".

`note` is the one supporting line under the diagram, in its own reserved band. One
short sentence, or leave it out.

`title` is the frame's heading. Three or four words.

`spec` is one sentence of prose saying what the frame shows, for the graders and
for a human reading the unit later. It is not drawn.

Output JSON:
{"visuals":[{"ref":"...","spec":"one sentence","frame":{
  "template":"bar|mapping|split|flow|table|stat|takeaway",
  "title":"...", "note":"...",
  "cells":[{"label":"...","role":"plain|hero|lost|quiet"}], "cells_title":"...",
  "left":[...], "right":[...], "left_title":"...", "right_title":"...",
  "parts":[...], "steps":[...],
  "columns":["..."], "rows":[{"cells":["..."],"role":"..."}],
  "value":"...", "caption":"..."}}]}

Include only the fields the chosen template uses. The last ref is the takeaway."""


def spec_visuals(script: Script) -> dict[str, Visual]:
    """
    One call for the whole short: a template and its words for every visual_ref.

    In beat order, not sorted: the specs describe a composition that builds, so the
    model has to see the sequence it is designing for. Sorting the refs
    alphabetically handed it the beats shuffled.

    This is now the ONLY paid step in the visual pipeline. Drawing used to be one
    call per frame on top of this — four or five per short, and 82% of the bill.
    """
    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = (f"QUESTION: {script.question}\n\nBEATS, in order:\n{beats}\n\n"
            f"Design the composition and assign one frame to each of these refs, "
            f"in this order: {refs}\nThe last one, {refs[-1]}, is the takeaway card.")
    plan = ask_json(SPEC_SYSTEM, user, VisualPlan, max_tokens=4000, label="visual_spec")

    return {v.ref: Visual(ref=v.ref, type="diagram", spec=v.spec, frame=v.frame)
            for v in plan.visuals}


def render_diagrams(visuals: dict[str, Visual], script: Script,
                    section: Section) -> dict[str, Visual]:
    """
    Fill in .svg for every frame. No LLM calls, no network, no failure mode.

    `script` and `section` are no longer read — a Frame already carries everything
    the drawing needs. They stay in the signature because run.py and server.py both
    call this, and because a future renderer that wants to check a label against the
    source would want them back.

    There is no retry loop here any more, and nothing to retry: layout.render is
    deterministic and cannot produce an overlapping label. What used to be four
    concurrent model calls per short, a three-attempt redraw loop, a truncation
    path, and a "keep it anyway" fallback is now one function call per frame.
    """
    for visual in visuals.values():
        if visual.frame is not None:
            visual.svg = layout.render(visual.frame)
    return visuals
