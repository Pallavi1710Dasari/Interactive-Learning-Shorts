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

So the model no longer places anything. It picks one of eight templates and supplies
the words; skills/layout.py computes every coordinate and fits every label to the
box that holds it. Overlap is not graded any more because it cannot be constructed.
That also makes drawing FREE — rendering is local, so the diagram calls that were
82% of the bill are gone.

AND THE FRAMES ARE PICTURES NOW, WHICH IS THE SECOND CHANGE
Templates fixed the overlap and left a different defect: the frames were legible and
they were text. Three things caused it and all three are fixed here.

  The `note` field. It asked for "one supporting line under the diagram" and got the
  sentence being spoken, on 6 of 11 frames measured — under a player that already
  captions that same line word by word. layout.render no longer draws it.

  The `takeaway` template, which was a sentence set large and which the brief made
  the last frame of EVERY short. It is not offered any more; the last frame is the
  finished composition with the hero on the answer.

  And the real cause: this step could not see the reading material. Given only the
  dialogue, the dialogue is the only thing there is to draw, so `bar` became a row
  of boxes holding the three beats of the conversation. spec_visuals now gets the
  section, plus two templates that can show what a document actually contains —
  "code" for the snippet it teaches from, "compare" for two named alternatives.
"""

from pydantic import BaseModel
from ..schema import Script, Visual, Section, Frame
from ..llm import ask_json
from .. import config
from . import layout


class FramedVisual(BaseModel):
    ref: str
    spec: str
    frame: Frame


class VisualPlan(BaseModel):
    visuals: list[FramedVisual]


SPEC_SYSTEM = """You design the visuals for one short video, as a SINGLE COMPOSITION THAT BUILDS.

THE RULE THAT MATTERS MOST
The beats of a short are one continuous explanation, so the visuals belong to one
continuous idea — not four unrelated pictures. Decide what the short is a picture
OF, then give each beat a frame that shows the part of it that beat is about.

A viewer who watched four unrelated diagrams remembers none of them. A viewer who
watched one thing develop remembers the thing.

BUT "DEVELOP" MEANS SOMETHING CHANGES. RECOLOURING ONE CELL IS NOT A NEW FRAME.
This is the defect to avoid, and it is the one that gets complained about:

  BAD   Beat 1: the same 7-line snippet, line 3 amber.
        Beat 2: the same 7-line snippet, line 2 amber.
        Beat 3: the same 7-line snippet, line 3 amber again.
        ^ A real short this pipeline produced. Watching it, nothing happens: it is
          one slide for the whole video with a highlight sliding around on it.
          The viewer has read everything on screen within two seconds and then
          stares at an unchanging picture for the remaining twelve.

  GOOD  Beat 1: an "icons" frame — a file, a browser, a screen.
        Beat 2: a "preview" frame — the same words set in two different typefaces.
        Beat 3: a "code" frame — the rule that produced the difference.
        ^ Three pictures, one subject, and each beat shows something the last one
          could not.

So every frame after the first must ADD, REMOVE or REPLACE something a viewer would
notice with the sound off. Moving the accent is allowed as PART of a change; it is
never the whole change. Two consecutive frames that differ ONLY in which element is
the hero are rejected — give those two beats the SAME visual_ref instead, which
holds one picture still and is honest about doing so, or find the second picture.

A COSMETIC LABEL EDIT IS NOT A CHANGE. This is the loophole, and a real short went
through it:
        Beat 1: icons — Users, Applications, Operating System, Hardware
        Beat 3: icons — Users, Applications, Operating System, Hardware (CPU, I/O, RAM)
        ^ The same four pictograms, same order, same one lit. Adding a parenthetical
          changes the text and changes NOTHING a viewer sees. Labels are compared by
          meaning, not by characters, so this is rejected.

AND NEVER RETURN TO A FRAME YOU HAVE ALREADY SHOWN. Not just the previous frame —
ANY earlier frame. The short above was A, B, A: every adjacent pair differed and the
composition still ended exactly where it started, which is the complaint these
shorts get most ("showing same visuals again and again which feel bore"). A
composition that builds does not revisit. If a later beat genuinely needs an earlier
picture back, give it that beat's visual_ref and hold the picture honestly.

DO NOT OPEN ON A CARD THAT RESTATES THE QUESTION. Beat 1's frame is not a title
slide and not a "what is being asked" placeholder — those are the frames that get
skipped past. Beat 1 draws THE SUBJECT, as an object: the two things about to be
related, the device, the file, the structure. If the honest answer is "the subject
is an abstract idea", draw what it acts on or sits between.

AND DO NOT OPEN ON THE ANSWER'S CODE. Beat 1 is the interviewer's question, and its
frame should show the SUBJECT — the thing being asked about, drawn — not the listing
that answers it. A short that starts on the same code panel it ends on has shown the
viewer the answer before the question finished, and then has nothing left to reveal.
Lead with an "icons" or "preview" frame and let the code arrive when it is earned.

CHANGING TEMPLATE BETWEEN BEATS IS ENCOURAGED, not a failure of continuity. The
continuity comes from the subject, not from the shape: showing the effect and then
the code that causes it is one explanation told in two pictures, and it is far
stronger than either picture held on screen twice.

THE LAST BEAT IS THE COMPOSITION FINISHED, NOT A SENTENCE ON A CARD
The final visual is the SAME composition with the hero moved onto the thing that
answers the question — the assembled diagram, complete, pointing at its own
conclusion. It is the frame that has to survive in someone's memory for a week, and
what survives is the shape, not a paraphrase of the audio.

It used to be a card with the last spoken line set large. Do not do that. Every
short ended on a slide of its own voiceover, which is the single most common
complaint these shorts get: "the visuals are just text, and the text is just the
narration". A sentence is already being spoken and already being captioned under the
frame. Printing it a third time inside the picture is not a visual.

NEVER PUT A SENTENCE IN A FRAME. THIS IS THE RULE THAT IS BROKEN MOST OFTEN.
Every label you write is a NOUN or a VALUE — a thing on the screen that could be
pointed at. Never a clause, never a claim, never a line of the dialogue.

  BAD   cells: ["font-family?", "Import font CSS", "Which typeface"]
        ^ This is a real frame this pipeline produced. The three cells are the
          three beats of the conversation, laid out as boxes. It is the script in a
          row of rectangles: no memory is drawn, no code, no structure, nothing a
          learner could not have got from the audio. A viewer reads it once in half
          a second and then watches nothing for twelve seconds.
  GOOD  a "code" frame showing the material's own rule, `.main-heading { ... }`,
        with `font-family: "Roboto";` as the hero line.

If your cells, steps or rows could be read aloud as the answer, you have drawn the
transcript. Throw it away and draw the SUBJECT instead.

There is NO caption band and NO note field. Do not ask for one.

TYPE, for each distinct visual_ref:
  "diagram" — anything structural or technical: code and markup, tables, memory
              layouts, address splits, state transitions, request flows,
              before/after states. ALWAYS use this for technical content, which in
              practice means every frame of every one of these shorts.
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

EVERY FRAME IS A CLAIM ABOUT THE MATERIAL, AND IT IS CHECKED
A frame is not decoration; it asserts something, and a viewer believes a picture
faster than a sentence. So accuracy here matters more than in the narration, not
less — a wrong diagram is not noticed as wrong, it is simply learned.

Three rules, and all three are verified by code after you answer:
  * A "code" frame's lines must OCCUR IN THE MATERIAL, character for character
    modulo whitespace. Copy them; do not reconstruct them from memory. A plausible
    CSS rule is indistinguishable from the real one to everybody except the
    document, which is why this is checked rather than trusted.
  * A "preview" sample must RENDER what its caption claims — see that template.
  * Every label must come from the narration, the material's code, or its values.

If you cannot support a claim, make a smaller claim. A frame showing one rule
correctly beats a frame showing three where one is invented.

DRAW WHAT THE READING MATERIAL SHOWS YOU
You are given the section of the reading material this short came from, and that is
not background — it is where the picture comes from. The dialogue is a compression
of it into speech; the material still has the things speech had to drop, and those
things are exactly what a diagram is for:

  a style, or anything VISUAL     -> a "preview" frame showing the real effect
  named things and what links them-> an "icons" frame of drawn pictograms
  a code block or markup snippet  -> a "code" frame, the lines COPIED VERBATIM
  a table of values               -> a "table" frame with the real values in it
  a number, size or range         -> a "stat" frame
  two named alternatives          -> a "compare" frame
  a structure, layout or sequence -> "split", "bar", "flow", "mapping"

Take the first row that fits before the later ones. A document about how text looks
is best drawn by showing the text; its code block is the SECOND-best picture of it,
because code still has to be read to be understood and an effect does not.

A frame built from the material's own artifact is grounded by construction and
cannot drift, which is why it is always the better frame. Copy the material's
identifiers, values, selectors and numbers CHARACTER FOR CHARACTER — do not
paraphrase `font-family` into "font property", and do not substitute a value you
find neater for the one the document uses.

WHAT YOU MAY NOT TAKE FROM THE MATERIAL is its prose. You are looking for the
things it DRAWS and LISTS, not the sentences it writes. A noun from a paragraph
nobody in this short mentions is drift; a line from its code block is evidence.

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
its box. There are eight shapes. Pick the one the sentence actually needs.

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
  "stat"     ONE NUMBER, very large, with a caption naming it. For a frame whose
             whole content is a figure: "4 GB", "1011", "36px", "65".
             -> value, caption. The caption names the figure ("addressable bytes"),
                it is NOT a sentence about it.
             THE VALUE MUST CONTAIN A DIGIT. A grader rejects one that does not, and
             here is why, from a reel this pipeline built:
                 title "What is being asked", value "Computing system",
                 caption "Computing system"
             The same two words printed twice, as the OPENING frame of the short. A
             viewer's first two seconds went on reading one noun three times. A bare
             term set large is the takeaway card this brief already removed, wearing
             a different template name. If your beat has no figure in it, this is
             not your template — draw the thing.
  "code"     A code or markup snippet on a dark editor panel, one line lit. For any
             material that teaches through code — CSS rules, HTML markup, a
             command, a config. IF THE SECTION CONTAINS A CODE BLOCK RELEVANT TO
             THE QUESTION, THIS IS ALMOST ALWAYS THE RIGHT TEMPLATE, and it is the
             one that was missing while these shorts were coming out as walls of
             text.
             -> code_lines: up to 7, each {label, role}. `label` is ONE LINE of
                code, copied from the material verbatim, KEEPING ITS LEADING
                SPACES — indentation is drawn, so `  font-family: "Roboto";` nests
                inside its selector the way it does in the document. Mark the ONE
                line this beat is about role="hero"; every other line stays
                "plain" or "quiet". code_caption is the file it lives in
                ("style.css", "index.html"), or leave it out.
                Moving the hero DOWN THE SAME SNIPPET across beats is the strongest
                build this renderer can draw: the code holds still and the light
                walks through it.
                KEEP THE SNIPPET TO WHAT IS BEING TAUGHT. Copy the lines that carry
                the point and leave out boilerplate — a 500-character
                `@import url("https://fonts.googleapis.com/css2?family=...")` is
                setup, not the lesson. Elide a long line as
                `@import url("...");` rather than pasting it whole. Four focused
                lines beat seven with the subject buried among them.
  "icons"    DRAWN PICTOGRAMS in a row, named underneath, with arrows between
             them. The most literally pictorial shape here, and the right answer
             whenever the beat is about THINGS and what passes between them: a
             browser reading a file, a CPU reaching memory, a page being painted.
             -> glyphs: 2 to 4, each {icon, label, role}. `icon` MUST be one of:
__ICON_LIST__
                Anything else draws a plain box, so pick from the list.
                `label` names it in 1-2 words. arrows: false for a set rather than
                a sequence.
             A box with the word "Browser" in it is the word "browser" with a
             border round it. A drawn browser window is a picture. Prefer the
             picture.

             THE ICON MUST BE A PICTURE OF THE LABEL. This is the rule that was
             broken most often, and it produced the single worst frame this pipeline
             has shipped: a glyph labelled "HTTP" drawn as `text`, which renders as
             A CAPITAL LETTER A. The viewer is told, in a picture, that HTTP is a
             letter of the alphabet. The same short drew its server as `disk`, a
             storage cylinder; another labelled "Authentication" with the capital A
             and "Printer" with an empty box.

             None of those was a wrong choice from a good list — the list had no
             server, no network, no lock. It does now. So:

               "text" draws a CAPITAL A and means TYPOGRAPHY. Use it only when the
                      subject really is type: a font, a typeface, text styling. It
                      is not a general-purpose glyph for an abstract noun, and a
                      grader fails it on any other label.
               "box"  is not available. It was the "renderer does not know this
                      name" fallback and using it deliberately is drawing nothing.

             If nothing on the list is a picture of your label, THE LABEL IS NOT A
             THING and this is the wrong template. A protocol, a guarantee, a
             property, a concept — these have no pictogram because they are not
             objects. Draw what they act ON instead (`server` and `browser` with an
             arrow between them, not a glyph named "HTTP"), or use "flow", "code" or
             "compare", which are built for claims rather than for things.
  "preview"  SAMPLE TEXT RENDERED IN THE STYLE BEING TAUGHT — the effect itself,
             not a description of it. For every typography and text property:
             font-family, font-size, font-style, font-weight, text-decoration.
             -> samples: up to 3, each {text, label, role} plus any of
                font, scale (1-5), weight (100-900), italic, decoration
                ("underline" | "line-through" | "overline"), color, background.
                color / background are CSS values — a keyword ("blue", "grey",
                "lightblue") or a hex ("#3366ff"). Use the material's own value.
                `text` is the words to render — use the material's own example
                ("Tourism", "Plan your trip"). `label` names what it shows
                ("Lobster", "36px", "bold").
                `font` must be a family that actually renders: serif, sans-serif,
                monospace, cursive, fantasy, or one of Bree Serif, Caveat, Lobster,
                Monoton, Open Sans, Playfair Display, Roboto, Source Sans 3,
                Work Sans. Naming anything else shows the viewer a typeface that is
                not the one the caption claims, so do not.
                `scale` is RELATIVE, not pixels. For "36px versus 28px" use scale 5
                and scale 4 — the renderer fits them to the canvas, and real pixel
                values both come out the same size on a 1080 square, which erases
                the very difference being demonstrated.
             THE LABEL IS A CLAIM AND THE SAMPLE MUST BACK IT UP. Whatever the
             caption says, the fields have to actually produce. This is the way it
             goes wrong: asked to show `color: blue` against `color: grey` the frame
             came back with two samples captioned "blue" and "grey" and NO color set
             on either, so both drew in the default near-black. The captions were
             right, the material was right, and the picture told the viewer that
             blue and grey look the same. Watched back it read as "it says the main
             heading is blue but the paragraph is blue too".
             So: a sample captioned "blue" sets color "blue". One captioned "bold"
             sets weight 700. One captioned "36px" gets the larger `scale`. If the
             effect has no field on this template, DO NOT use "preview" for it —
             use "code" and show the rule instead. A caption the drawing cannot
             honour is worse than a plainer frame, because it is confidently wrong.

             READ THE VALUE OFF THE RULE THAT SETS IT, PER SELECTOR. The material
             gives each selector its own value:

                 .main-heading { color: blue; }
                 .paragraph    { color: grey; }

             so the sample showing the heading sets color "blue" and the sample
             showing the paragraph sets color "grey". Do not colour one and leave the
             other to default — an unset colour is not neutral, it draws in the
             near-black page ink, so a frame about colour that sets only one is
             telling the viewer the other element is black. Every sample in the
             frame gets the value the material gives ITS selector.

             And do not caption a sample with its own words. `text` is "Main heading"
             and the caption is "blue" — the words are already on screen at four
             times the size; the caption is there to name what is being demonstrated.

             SET ONLY THE FIELDS THIS BEAT IS ABOUT. Leave the rest out.
             Every field you fill in is a claim about the material, and a field the
             section never mentions is an invented one. On a frame about `color`,
             adding font "Roboto" and weight 700 asserts a typeface and a weight
             that the colour section does not give — the frame is then mostly
             fabricated even though the colour it was built for is right. Omitted
             fields render in a neutral default, which claims nothing.
             `scale` is the exception: something has to decide the size, so use it
             for relative emphasis and do not read it as a claim about font-size
             unless font-size IS the subject.

             THE SAMPLES MUST LOOK OBVIOUSLY DIFFERENT FROM EACH OTHER, or the
             frame shows nothing. This is the way this template fails: asked to
             demonstrate font-family it returns "Main heading" in `sans-serif`
             above "Main heading" in `Roboto` — which ARE the same shape, because
             Roboto IS the default sans on most screens. The viewer sees one word
             twice and is told to notice a difference that is not there.
             So pick faces from DIFFERENT categories. `Lobster` or `Caveat`
             (script) against `Roboto` (sans); `Playfair Display` (serif) against
             `monospace`. If you cannot tell the two apart when you imagine them,
             the frame is wrong however correct the labels are.
             Same for the other properties: weight 200 against 700, not 400
             against 500. scale 5 against scale 2, not 4 against 3.
             And never repeat one sample's own `text` as its `label` — the label
             names the STYLE ("Lobster", "36px", "bold"), not the words.

             THIS IS THE RIGHT TEMPLATE FOR ANY QUESTION ABOUT HOW SOMETHING LOOKS.
             "What does font-family specify?" is answered by two words in two
             typefaces, side by side, in a way no sentence and no code listing can.
  "compare"  Two cards side by side, each holding its own small stack. For two
             named alternatives, a before and after, a right way and a wrong way.
             -> panels: EXACTLY 2, each {title, role, items} where items is up to
                4 {label, role}. The panel's own role colours its border, so put
                role="lost" on the approach that wastes something and role="hero"
                on the one being recommended. Item roles work inside that.
             Use this and NOT "table" for a comparison. A table is a lookup, so its
             two columns claim a row-for-row correspondence — and two alternatives
             are not a correspondence, they are a choice.

PICK THE TEMPLATE FROM THE RELATIONSHIP, NOT FROM THE SUBJECT
Ask what the sentence CLAIMS, and the template follows:

  one thing divides into named fields    -> "split"
  two sets correspond, row for row       -> "mapping"
  a sequence of events in order          -> "flow"
  countable slots in a line              -> "bar"
  a lookup: this key gives that value    -> "table"
  two alternatives weighed against each  -> "compare"
  how something LOOKS, or a style        -> "preview"
  things, and what passes between them   -> "icons"
  the material teaches it with code      -> "code"
  a single figure is the whole point     -> "stat"

Work down that list in order of how CONCRETE the frame ends up. A "code" frame of
the document's own rule beats a "flow" of your paraphrase of it every time, because
one is the thing itself and the other is a description of the thing.

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

A label over about four words is a sentence wearing a box, and it is the tell that
a frame has become a slide. The one exception is `code_lines`, whose labels are
lines of real code and are as long as the document made them.

`title` is the frame's heading. Three or four words. A NAME for what is on screen
("Physical memory", "The font-family rule") — not a statement about it, and not the
beat's sentence shortened.

`spec` is one sentence of prose saying what the frame shows, for the graders and
for a human reading the unit later. It is not drawn.

Output JSON:
{"visuals":[{"ref":"...","spec":"one sentence","frame":{
  "template":"bar|mapping|split|flow|table|stat|code|compare|preview|icons",
  "title":"...",
  "cells":[{"label":"...","role":"plain|hero|lost|quiet"}], "cells_title":"...",
  "left":[...], "right":[...], "left_title":"...", "right_title":"...",
  "parts":[...], "steps":[...],
  "columns":["..."], "rows":[{"cells":["..."],"role":"..."}],
  "value":"...", "caption":"...",
  "code_lines":[{"label":"  font-family: \"Roboto\";","role":"hero"}],
  "code_caption":"style.css",
  "panels":[{"title":"...","role":"...","items":[{"label":"...","role":"..."}]}],
  "glyphs":[{"icon":"browser","label":"Browser","role":"hero"}], "arrows":true,
  "samples":[{"text":"Tourism","label":"Lobster","font":"Lobster","scale":3,
              "weight":700,"italic":false,"decoration":null,"color":"blue",
              "background":null,"role":"hero"}]}}]}

Include only the fields the chosen template uses. There is no "takeaway" template
and no "note" field — the last ref is the finished composition, see above."""


#: The icon names the brief offers, wrapped to fit it, taken from the renderer
#: itself. SPEC_SYSTEM cannot be an f-string — it is mostly JSON braces — so this is
#: a substitution rather than an interpolation.
_ICON_LINES = "\n".join(
    "                " + ", ".join(layout.OFFERED_ICONS[i:i + 7])
    for i in range(0, len(layout.OFFERED_ICONS), 7))
SPEC_SYSTEM = SPEC_SYSTEM.replace("__ICON_LIST__", _ICON_LINES)


def spec_visuals(script: Script, section: Section | None = None,
                 feedback: str | None = None,
                 model_override: str | None = None) -> dict[str, Visual]:
    """
    One call for the whole short: a template and its words for every visual_ref.

    In beat order, not sorted: the specs describe a composition that builds, so the
    model has to see the sequence it is designing for. Sorting the refs
    alphabetically handed it the beats shuffled.

    This is now the ONLY paid step in the visual pipeline. Drawing used to be one
    call per frame on top of this — four or five per short, and 82% of the bill.

    `section` IS WHY THE FRAMES STOPPED BEING TEXT, so it is worth being explicit
    about. This step used to receive the dialogue and nothing else, and a step that
    can only see sentences can only draw sentences: the frames that came back were
    the beats laid out as boxes — cells reading "font-family?", "Import font CSS",
    "Which typeface", which is the script in a row of rectangles. There was nothing
    else in the prompt to draw.

    The material is where the pictures actually are. The section behind that CSS
    short contains

        .main-heading {
          font-family: "Roboto";
        }

    and a "code" frame of those three lines with the middle one lit is a real
    diagram of the answer, grounded character for character in the document, that no
    amount of rewording the brief could have produced without the document present.

    Optional, so callers that genuinely have no section (and the eval harness) still
    work — they just get the weaker, dialogue-only framing they had before.
    """
    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = f"QUESTION: {script.question}\n\nBEATS, in order:\n{beats}\n"

    if section is not None:
        # After the beats, not before: the composition is designed for the dialogue,
        # and the material is the source of what the dialogue's nouns look like. Put
        # first, the model plans a diagram of the section and then tries to hang the
        # beats off it, which is how a frame drifts onto a neighbouring idea.
        user += f"""
THE READING MATERIAL THIS SHORT CAME FROM — section [{section.section_id}] {section.title}
Draw from the things this document SHOWS: its code blocks, its tables, its values
and its numbers, copied exactly. Not from its prose.
---
{section.text}
---
"""

    user += (f"\nDesign ONE composition and assign a frame to each of these refs, in "
             f"this order: {refs}\nThe last one, {refs[-1]}, is that composition "
             f"finished, with the hero on the thing that answers the question — it is "
             f"NOT a card with a sentence on it."
             f"\n\nRETURN EXACTLY {len(refs)} VISUALS, whose `ref` values are these "
             f"strings character for character: {refs}\nDo not invent a ref, do not "
             f"merge two refs into one, do not drop one. A renamed ref makes the whole "
             f"answer unusable — the beats are keyed to these strings.")

    # LAST, so it is the final thing read before answering. The script step has had a
    # retry loop since the beginning and this step had none — one call, whatever came
    # back, shipped. That asymmetry is why 11 of 15 shipped shorts failed a visual
    # grader that already existed and already said the right thing.
    if feedback:
        user += f"""

YOUR PREVIOUS DESIGN WAS REJECTED. These are the exact defects a code grader found
in it — they are structural, not opinions, and the same grader runs again on your
next answer:

{feedback}

Do not repeat them. If a beat has no second picture in it, give it the SAME
visual_ref as the beat before rather than redrawing one frame with the accent
moved — one honest still is better than two frames pretending to differ."""
    # MODEL_DIAGRAM, which until now nothing read — /api/health advertised it and no
    # call site used it, so setting it did nothing at all. This is the call it should
    # always have named: the one paid step that decides what every frame of the short
    # contains. Defaults to the generator.
    plan = ask_json(SPEC_SYSTEM, user, VisualPlan,
                    model=model_override or config.MODEL_DIAGRAM,
                    max_tokens=4000, label="visual_spec")

    return {v.ref: Visual(ref=v.ref, type="diagram", spec=v.spec, frame=v.frame)
            for v in plan.visuals}


#: How many times the visual step may be asked again before its best answer ships.
#: The script step has used 3 since the beginning; this matches it.
MAX_DESIGN_ATTEMPTS = 3

#: The graders a redesign can actually act on. All structural, all free, all about
#: the DESIGN rather than the drawing — a failure here means asking the model again
#: is worth a call. Deliberately not the whole of UNIT_GRADERS: check_svg_quality
#: fails on a line of the material's own code being too long to fit, which a
#: redesign cannot shorten without inventing code, and check_diagram_matches_narration
#: is a vocabulary heuristic that a correct frame can trip.
def _design_graders(section: Section | None = None):
    """Imported late: checks imports schema, and schema is what defines a Frame.

    check_code_frames_quote_source IS IN THIS LIST, and leaving it out was a real
    hole. It needs the section, which is why it was skipped when this list was first
    written — and the consequence showed up immediately after the design model
    changed: a frame came back captioning

        GET /index.html HTTP/1.1
        Host: example.com

    as the material's own snippet, on a document that contains neither line. The
    retry loop never saw it, because the only graders it gated on were the ones that
    need no source. A fabricated code line is the most harmful thing this pipeline
    can put on screen — a learner cannot tell it from the real thing, and it is
    presented as the document's own text — so it belongs in the gate, not in a
    warning printed after the short is written.
    """
    from .. import checks
    graders = [checks.check_frames_develop, checks.check_frames_are_visual,
               checks.check_icons_are_pictures, checks.check_samples_differ]
    if section is not None:
        graders.append(lambda u: checks.check_code_frames_quote_source(u, section.text))
    return graders


def design_visuals(script: Script, section: Section | None = None, *,
                   draw: bool = True,
                   previous: dict[str, Visual] | None = None,
                   attempts: int = MAX_DESIGN_ATTEMPTS) -> tuple[dict[str, Visual], list[str]]:
    """
    Design the frames, grade them, and ask again for the ones that failed.

    Returns (visuals, remaining problems). The problems list is empty on success and
    is what the caller should warn about when every attempt has been spent.

    WHY THIS EXISTS. Every defect it catches was already detectable, by graders that
    already lived in checks.py and already printed the right sentence — and every
    one of them shipped anyway, because nothing was wired to act on them.
    check_frames_develop says so in its own docstring: "This reports, it does not
    gate — no retry loop hangs off it." Measured on the fifteen shorts in output/,
    11 failed at least one of these four. Three shorts were four frames of the SAME
    four icons with only the amber highlight moving between them, which is exactly
    the complaint the grader was written for.

    So the gap was never detection. It was that the script step had a retry loop and
    the visual step did not: one call, whatever came back, straight to disk.

    The loop is cheap by construction. Drawing is local and free, so an attempt
    costs one model call and only happens for a short that actually failed — the
    common case is one call, unchanged from before. The best attempt is kept rather
    than the last: a second try that fixes two defects and introduces one is still
    the better frame set, and returning the final attempt regardless would sometimes
    ship a worse design than the one it replaced.
    """
    from ..schema import ShortUnit

    # Every ref the beats actually name. A returned design MUST cover all of them or
    # ShortUnit will not validate — see the ref-drift note below.
    needed = {b.visual_ref for b in script.beats}

    best: dict[str, Visual] | None = None
    best_problems: list[str] | None = None
    feedback: str | None = None

    for attempt in range(1, max(1, attempts) + 1):
        # ONE BAD ATTEMPT MUST NOT LOSE THE GOOD ONES.
        #
        # It did, and this is the bug that cost a whole redesign sweep. On a retry
        # the model sometimes RENAMES the refs — asked again for
        # "what_is_a_computing_system_q, definition, hardware_and_software" it came
        # back with a single "system_icons" — and the probe below then failed
        # ShortUnit's every_ref_resolved validator. That ValidationError escaped
        # design_visuals entirely, so the caller's `except Exception` logged it and
        # moved on, discarding two perfectly usable earlier attempts. Five of nine
        # units in one sweep were silently left un-redesigned this way.
        try:
            visuals = spec_visuals(script, section, feedback=feedback)
            if draw:
                visuals = render_diagrams(visuals, script, section)

            # REF DRIFT, repaired rather than punished. A design that renamed a ref
            # is still a usable design for the refs it did produce; fill the gaps
            # from the previous frames when the caller has them.
            missing = needed - set(visuals)
            if missing:
                for ref in missing:
                    if previous and ref in previous:
                        visuals[ref] = previous[ref]
                if needed - set(visuals):
                    raise ValueError(
                        f"design dropped refs {sorted(needed - set(visuals))} and there "
                        f"is no previous frame to fall back on")

            probe = ShortUnit(short_id=script.short_id, session_id="probe",
                              source_section_id=section.section_id if section else "",
                              question=script.question,
                              estimated_seconds=script.estimated_seconds,
                              beats=script.beats, visuals=visuals)
            problems = [f"{r.name}: {r.reason}"
                        for r in (g(probe) for g in _design_graders(section)) if not r.passed]
        except Exception as e:
            print(f"    attempt {attempt}/{attempts} for {script.short_id} unusable: "
                  f"{type(e).__name__}: {str(e)[:120]}")
            feedback = ((feedback or "") +
                        f"\n  - your previous answer was unusable ({type(e).__name__}). "
                        f"Return a frame for EVERY ref you were given, using those exact "
                        f"ref strings and no others.")
            continue

        if best_problems is None or len(problems) < len(best_problems):
            best, best_problems = visuals, problems
        if not problems:
            return visuals, []

        if attempt < attempts:
            print(f"    redesign {attempt}/{attempts} for {script.short_id}: "
                  + "; ".join(p[:110] for p in problems[:2]))
        feedback = "\n".join(f"  - {p}" for p in problems)

    # Every attempt unusable: hand back what the caller already had rather than an
    # empty dict, which would fail validation at the call site for a different reason.
    if best is None:
        return dict(previous or {}), ["design produced no usable frame set"]
    return best, best_problems or []


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
