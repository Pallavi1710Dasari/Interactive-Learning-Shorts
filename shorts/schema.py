"""
The data contract for the whole pipeline.

Every step reads one of these models and returns another. If a step's output
does not validate, the pipeline stops there instead of pushing a broken object
further downstream. Design this file first and change it rarely.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Speech pacing. 150 words/min is a conservative average for clear narration.
WORDS_PER_MINUTE = 150
WORDS_PER_SECOND = WORDS_PER_MINUTE / 60.0

# The length window, in seconds of speech.
#
# Was 30-60. The floor was forcing padding: a question whose honest answer is three
# short sentences had to be inflated to 75 words to clear it, and the extra beat was
# always the weakest one — a restatement, or a claim propped up by a citation that
# did not really support it. Short and clear beats long and padded, and a viewer
# decides in the first few seconds anyway.
#
# 18s is about 45 words, which is three real sentences. If a topic cannot be
# answered in that, it is too big for one short and belongs to the select step.
#: Cut again, from 18-45. At 45 seconds a short is five points long, and five
#: points is what made these unmemorable — see checks.MAX_ANSWERS. A question and a
#: two-or-three-part answer is 35-60 words, which is 14 to 24 seconds.
MIN_SECONDS = 12
MAX_SECONDS = 28
MAX_OVERLAY_WORDS = 8


class Section(BaseModel):
    """One chunk of the source reading material."""
    section_id: str          # e.g. "3.2"
    title: str
    text: str
    start_line: int
    end_line: int

    @property
    def span(self) -> str:
        return f"{self.section_id} (lines {self.start_line}-{self.end_line})"


class Topic(BaseModel):
    """Output of Skill 1. One topic becomes one short."""
    id: str
    topic: str
    why_it_matters: str
    source_section_id: str
    difficulty: Literal["easy", "medium", "hard"]

    # The sentence from the section that ANSWERS this question, copied verbatim.
    #
    # This is the fix for questions that cannot be answered from the reading
    # material. Selection used to be asked, in prose, to only pick answerable
    # topics; nothing checked that it had, so a plausible-sounding question whose
    # answer was not in the document survived all the way to a reviewer, and the
    # script step then either refused or invented. Making the model produce the
    # evidence turns that from a request into something select.py can verify by
    # string match, the same way check_source_quotes already does for beats.
    #
    # Optional because topics.json files written before this field existed must
    # still load. Newly selected topics without one are dropped by select.py.
    answer_quote: Optional[str] = None

    # How much this question matters, 1-5, against the rubric in select.py.
    #
    # This exists because selection was returning correct, answerable, forgettable
    # questions — the definition of one CSS property, a yes/no about whether HTML
    # styles a page — alongside the ones a learner is actually asked. Everything
    # about those topics validated, so nothing downstream could tell them apart
    # from the good ones. Scoring them makes "the most important questions in this
    # material" something select.py can sort by and cut, instead of a hope.
    #
    # Optional for the same reason answer_quote is: older topics.json must load.
    importance: Optional[int] = Field(default=None, ge=1, le=5)

    # The one concept this question is about, as a short noun phrase. Used to keep
    # three shorts asking the same thing three ways out of one deck.
    concept: Optional[str] = None


class TopicList(BaseModel):
    topics: list[Topic]

    @field_validator("topics")
    @classmethod
    def check_count(cls, v):
        # 1 is legitimate: a short reading may only contain one thing worth a
        # short, and asking for one reel should not be rejected as malformed.
        if not 1 <= len(v) <= 12:
            raise ValueError(f"expected 1-12 topics, got {len(v)}")
        return v


class Beat(BaseModel):
    """One spoken line plus what the viewer sees while it plays.

    NOTE: on_screen length is deliberately NOT validated here. The schema's job is
    "can this be represented", the grader's job is "is this good". If the schema
    rejects an over-long overlay, you get an exception instead of a diagnosis, and
    you can no longer write an eval case for the failure. Enforcement lives in
    checks.check_overlays().
    """
    speaker: Literal["interviewer", "student"]
    line: str
    on_screen: str
    visual_ref: str

    # The span of the source section this beat is a restatement of, copied out
    # character for character. checks.check_source_quotes() then verifies it really
    # occurs in the section, which turns "is this grounded?" from a judgement call
    # into a substring test that costs nothing and cannot be argued with.
    #
    # Optional because the 20 units already in output/ predate the field and must
    # still load. Enforcement lives in the grader, per the note above.
    source_quote: Optional[str] = None


class Script(BaseModel):
    """Output of Skill 2."""
    short_id: str
    question: str
    beats: list[Beat]

    @property
    def word_count(self) -> int:
        return sum(len(b.line.split()) for b in self.beats)

    @property
    def estimated_seconds(self) -> float:
        return round(self.word_count / WORDS_PER_SECOND, 1)

    @field_validator("beats")
    @classmethod
    def starts_with_interviewer(cls, v):
        if not v:
            raise ValueError("script has no beats")
        if v[0].speaker != "interviewer":
            raise ValueError("first beat must be the interviewer asking the question")
        return v


#: How a cell, box or row is being treated by the narration right now.
#:
#: The narration decides emphasis, not the drawing, so a frame names ROLES and the
#: renderer owns the colours. That is what keeps the palette consistent across every
#: short and stops "amber" being spent on three things at once.
Role = Literal["plain", "hero", "lost", "quiet"]


class Cell(BaseModel):
    """One box in a bar, column, split or flow."""
    label: str = ""
    role: Role = "plain"


class TableRow(BaseModel):
    cells: list[str] = Field(default_factory=list)
    role: Role = "plain"


class Sample(BaseModel):
    """One line of sample text, DRAWN WITH the style being taught.

    The picture for a typography lesson is the type. A frame that says
    "font-family sets the typeface" in a box is a sentence; a frame showing the word
    "Tourism" set in Lobster next to the same word in Roboto is the thing itself,
    and the difference is visible before a single label is read.

    Only styles a browser can actually render are here — no invented ones — because
    this is drawn as real SVG text and the viewer is looking at the genuine effect.
    """
    text: str = ""
    #: What this sample demonstrates, e.g. 'Roboto' or '36px'. Small, under it.
    label: str = ""
    #: A font-family value. Generic families (serif, sans-serif, monospace, cursive)
    #: always render; named ones need loading — see web/index.html.
    font: Optional[str] = None
    #: Relative size, 1-5. NOT pixels: the renderer owns the canvas and scales these
    #: so the largest fits, which is what makes a size comparison honest at any
    #: number of samples.
    scale: Optional[int] = Field(default=None, ge=1, le=5)
    weight: Optional[int] = Field(default=None, ge=100, le=900)
    italic: bool = False
    decoration: Optional[Literal["underline", "line-through", "overline"]] = None

    #: The text colour, as a CSS keyword or hex — the material's own value.
    #:
    #: THIS FIELD WAS MISSING AND THE FRAME LIED WITHOUT IT. Asked to illustrate
    #: `color: blue` / `color: grey`, the model produced two samples labelled "blue"
    #: and "grey" and, with nowhere to put the colour, both rendered in the default
    #: ink — a picture claiming a difference it did not show. A `preview` frame
    #: exists to display an effect, so every effect it is asked to display needs
    #: somewhere to live; see checks.check_samples_differ, which now fails a frame
    #: whose samples claim to differ and render identically.
    color: Optional[str] = None

    #: The background colour behind this sample, same format. For background-color.
    background: Optional[str] = None

    role: Role = "plain"


class Glyph(BaseModel):
    """One pictogram in an `icons` frame: a drawn thing, with a name under it."""
    #: Which pictogram. See layout.PICTOGRAMS for the list; an unknown name falls
    #: back to a plain box rather than failing the build.
    icon: str = "box"
    label: str = ""
    role: Role = "plain"


class Panel(BaseModel):
    """One side of a `compare` frame: a titled card with a small stack inside.

    Two worlds side by side is a shape these shorts need constantly — contiguous
    versus paged, internal versus external, normal versus italic — and it was being
    forced through `table`, which draws a lookup grid and claims a
    row-for-row correspondence that a comparison does not have.
    """
    title: str = ""
    items: list[Cell] = Field(default_factory=list)
    role: Role = "plain"


class Frame(BaseModel):
    """
    One diagram, described as STRUCTURE rather than as coordinates.

    WHY THIS EXISTS
    The model used to emit raw SVG, and the labels overlapped — persistently, on
    every model tried, however the brief was worded. That is not a prompting
    problem: drawing an SVG by hand means doing layout arithmetic in your head
    (does this 27-character label fit inside this 200px box, is there clear space
    between these two <text> elements) with no way to see the result. Three redraw
    attempts guided by checks.svg_problems reduced it and never fixed it, and
    _draw_one kept the frame either way, so broken frames shipped.

    So the model no longer places anything. It chooses a template and supplies the
    words; skills/layout.py computes every coordinate, fits every label to the box
    it belongs to, and reserves a band for anything that cannot fit inside. Labels
    cannot overlap because nothing is ever placed where something else already is.

    The templates are deliberately few. Each one is a shape these shorts actually
    need, and a frame that cannot be said in one of them is a frame that was trying
    to say too much for four seconds of phone screen.
    """
    #: "takeaway" is LEGACY and must not be chosen for new frames — see the
    #: renderer and SPEC_SYSTEM. It stays in the union only so the units already in
    #: output/ still load and can be re-rendered.
    template: Literal["bar", "mapping", "split", "flow", "table", "stat",
                      "code", "compare", "preview", "icons", "takeaway"]
    title: str = ""
    #: LEGACY, and no longer drawn. This was "the one supporting line under the
    #: diagram", and what the model actually put in it was the sentence being
    #: spoken — so every frame carried a caption of its own narration, under a
    #: player that already flows that same line word by word. Two copies of the
    #: voice and no picture is the "visuals are just text" complaint in one field.
    #: Kept so old units load; layout.render ignores it.
    note: Optional[str] = None

    #: bar — a row of equal cells, e.g. memory frames.
    cells: list[Cell] = Field(default_factory=list)
    #: bar / mapping — a quiet caption naming the whole row or column.
    cells_title: Optional[str] = None

    #: mapping — two columns with arrows between them, e.g. pages to frames.
    left: list[Cell] = Field(default_factory=list)
    right: list[Cell] = Field(default_factory=list)
    left_title: Optional[str] = None
    right_title: Optional[str] = None

    #: split — one wide bar cut into named parts, e.g. an address.
    parts: list[Cell] = Field(default_factory=list)

    #: flow — steps top to bottom with arrows, e.g. a page fault path.
    steps: list[Cell] = Field(default_factory=list)

    #: table — a header row and rows, one of them the hero.
    columns: list[str] = Field(default_factory=list)
    rows: list[TableRow] = Field(default_factory=list)

    #: stat — one number or term, large.
    value: Optional[str] = None
    caption: Optional[str] = None

    #: code — the material's OWN snippet, one line per Cell, verbatim including its
    #: leading indentation, with the line under discussion as the hero.
    #:
    #: This is the template that was missing, and its absence is most of why the
    #: frames came out as text. Roughly every web-development document in this
    #: project teaches through a code block — `.main-heading { font-family:
    #: "Roboto"; }` — and there was no shape that could show one. With nothing
    #: pictorial to choose, the model laid the narration out as boxes instead, which
    #: is a slide of the voiceover rather than a diagram of the idea.
    code_lines: list[Cell] = Field(default_factory=list)
    #: code — the file or selector the snippet lives in, e.g. "style.css".
    code_caption: Optional[str] = None

    #: compare — two titled cards side by side, each holding its own small stack.
    panels: list[Panel] = Field(default_factory=list)

    #: preview — sample text rendered IN the style being taught, so the viewer sees
    #: the effect rather than reading a description of it.
    samples: list[Sample] = Field(default_factory=list)

    #: icons — drawn pictograms with names under them. Pictures, not boxes of words.
    glyphs: list[Glyph] = Field(default_factory=list)
    #: icons — draw arrows between the pictograms, for a sequence rather than a set.
    arrows: bool = True


class Visual(BaseModel):
    """Output of Skills 3 and 4."""
    ref: str
    type: Literal["diagram", "image", "text"]
    spec: str                       # what it should show, in words
    svg: Optional[str] = None       # filled in for type == "diagram"
    image_path: Optional[str] = None

    #: The structured frame this diagram was rendered from, when it was rendered
    #: from one. Optional so units written before templates existed still load, and
    #: kept on the unit so a frame can be re-rendered after a layout fix without
    #: spending another LLM call.
    frame: Optional[Frame] = None


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class BeatSpan(BaseModel):
    """When one beat starts and stops in the rendered track."""
    start: float
    end: float


class Audio(BaseModel):
    file: str
    duration_seconds: float
    word_timings: list[WordTiming]

    # Recorded per beat by whoever synthesised the track, rather than re-derived
    # downstream from word counts.
    #
    # feed.py used to cut beats by consuming len(beat.line.split()) word timings in
    # order, which silently assumed the spoken text has exactly as many
    # whitespace tokens as the written line. Speaking the text conversationally
    # breaks that assumption the moment it rewrites "a — b" as "a, b", and the
    # penalty is every later beat drifting by one word. The synthesiser knows each
    # beat's real boundaries because it renders them one at a time, so it says so
    # here. Optional: tracks made before this field existed fall back to the
    # word-count estimate.
    beat_spans: list[BeatSpan] = []


class EvalReport(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    pace: int = Field(ge=1, le=5)
    diagram_correct: bool
    # Whether the answer delivers what the question asked. Defaults True so the 20
    # units judged before this field existed still load.
    question_answered: bool = True
    problems: list[str] = []

    @property
    def passed(self) -> bool:
        return (
            self.faithfulness >= 4
            and self.clarity >= 4
            and self.pace >= 3
            and self.diagram_correct
            and self.question_answered
        )


class ShortUnit(BaseModel):
    """The complete artifact. This is what Remotion renders."""
    short_id: str
    session_id: str
    source_section_id: str
    question: str
    estimated_seconds: float
    beats: list[Beat]
    visuals: dict[str, Visual]
    audio: Optional[Audio] = None
    eval: Optional[EvalReport] = None
    #: "needs_review" is the quarantine state: the short was built and paid for, and
    #: the judge scored it below the bar (see EvalReport.passed). It stays on disk
    #: with its verdict attached so a human can read what was wrong and decide, but
    #: feed.collect keeps it out of the student-facing reel by default. Before this
    #: existed a faithfulness-2 short — one teaching a fact its own section does not
    #: contain — was written as "audited" and appeared in the feed indistinguishable
    #: from a 5.
    status: Literal["draft", "audited", "approved", "rendered", "rejected",
                    "needs_review"] = "draft"
    video_path: Optional[str] = None

    @field_validator("visuals")
    @classmethod
    def every_ref_resolved(cls, v, info):
        beats = info.data.get("beats") or []
        missing = {b.visual_ref for b in beats} - set(v.keys())
        if missing:
            raise ValueError(f"beats reference visuals that don't exist: {sorted(missing)}")
        return v
