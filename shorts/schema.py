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
# READ THE HISTORY BEFORE MOVING THESE. It has gone 30-60 -> 18-45 -> 12-28 -> and
# now back up to 35-50, and the two cuts were not mistakes: each one fixed a real
# defect that the raise can bring back.
#
# Why it was cut, twice:
#   30-60 -> 18-45  The floor forced padding. A question whose honest answer is
#                   three short sentences had to be inflated to 75 words, and the
#                   extra beat was always the weakest — a restatement, or a claim
#                   propped up by a citation that did not really support it.
#   18-45 -> 12-28  At 45 seconds a short was five points long, and five points is
#                   what made these unmemorable. One idea and its consequence is
#                   recallable a week later; five lands none of them.
#
# Why it is going back up, and why this is not a repeat of the thing that failed:
# BOTH cuts were fixing the same defect, and it was never length itself — it was
# length applied to a topic that did not have the content to fill it. A 45-second
# short built by stretching a three-sentence answer is padding at any window. A
# 45-second short built on a concept that genuinely carries a mechanism, its
# consequence, and a worked example is not.
#
# So the floor is only honest if the SELECT step is the thing that changed, and it
# is: select now requires a topic to have that depth in its own section before it
# may be returned (see skills/select.py, "ENOUGH TO FILL THE WINDOW"). Raising this
# window WITHOUT that change reproduces the 18-45 failure exactly.
#
# What holds the memorability half in place is not the window, it is
# checks.MAX_ANSWER_WORDS, which stays at 24. More beats, each still one idea —
# never longer beats. 35s is ~87 words, 50s is ~125, and the target is ~45s / ~112.
MIN_SECONDS = 35
MAX_SECONDS = 50
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

    # Which of mechanism / consequence / example / misconception the topic's own
    # section actually holds — the depth test in select.py's prompt.
    #
    # Recorded rather than merely required, because the length window (35-50s) only
    # works when topics have the substance to fill it, and "did select really check
    # that?" is otherwise unanswerable after the fact. When a padded short turns up
    # in review this is the field that says whether selection let a thin topic
    # through or the script step padded a rich one — two different bugs with two
    # different fixes.
    #
    # Free-form list, not an enum, and optional: older topics.json files predate it
    # and a model that returns an unexpected label should not fail validation over
    # a diagnostic.
    depth: list[str] = Field(default_factory=list)

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


class SectionUnderstanding(BaseModel):
    """
    Output of SKILL 1b — what the section actually teaches, before anything writes.

    THE CONTENT BRAIN, AND WHY IT IS SEPARATE FROM THE WRITER
    write_script is handed a topic and a section and asked to do two jobs at once:
    work out what the section teaches, and turn that into interview beats inside a
    12-28 second budget. A model asked for two things does the answerable one, and
    the answerable one is "produce four beats that quote this text" — so
    comprehension happened as a side effect of drafting, was never written down,
    and could not be inspected, graded or reused across the three retry attempts.

    This model is that comprehension, made explicit and cheap to look at.

    NOTHING HERE IS A SOURCE OF QUOTES. `source_evidence` carries sentences the
    section really contains, but checks.check_source_quotes deliberately matches a
    beat against the SECTION and nothing else (see its docstring — four of fifteen
    shipped shorts scored faithfulness 2/5 when quotes were accepted from anywhere).
    Feeding this model's prose back in as quotable material would re-open exactly
    that hole, so every field here is understanding, never citation.
    """

    #: What this topic is actually teaching, in one sentence.
    core_concept: str

    #: What the student should understand after watching. One sentence, from the
    #: learner's side: "why a page table is needed", not "explain page tables".
    learning_objective: str

    #: The ideas needed to explain the core concept.
    key_concepts: list[str] = Field(default_factory=list)

    #: What the student needs to know BEFORE this lands. Named from the section's
    #: own vocabulary; an empty list means the section is self-contained.
    prerequisites: list[str] = Field(default_factory=list)

    #: The actual mechanism, process or relationship — the part that makes this a
    #: concept rather than a definition.
    how_it_works: str

    #: Facts the section supports. Paraphrase is fine and expected; these are for
    #: the writer to understand, not to copy.
    important_facts: list[str] = Field(default_factory=list)

    #: An example the SECTION provides. None when it provides none — an invented
    #: example is the single most likely way this step could poison a script, so
    #: the field is nullable rather than defaulted to a placeholder.
    example: Optional[str] = None

    #: Confusions worth steering around, and ONLY when the section itself gives
    #: grounds for them. Empty is the correct answer for most sections; a list
    #: padded with generic misconceptions is how a reel ends up arguing with a
    #: mistake the learner was never going to make.
    misconceptions: list[str] = Field(default_factory=list)

    #: What this section clearly settles.
    can_answer: list[str] = Field(default_factory=list)

    #: What it does NOT establish. This is the field with teeth: it is the honest
    #: boundary the writer has to respect, and it is what makes "answer the
    #: narrower question the section supports" a decidable instruction rather than
    #: a hope. It complements skills/select.drop_unsupported rather than replacing
    #: it — that screen decides whether a topic ships at all, this describes the
    #: limits of one that already did.
    cannot_answer: list[str] = Field(default_factory=list)

    #: Sentences or claims from the section that carry the answer. GROUNDING ONLY.
    #: Not quotable output — see the class docstring.
    source_evidence: list[str] = Field(default_factory=list)


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


#: What KIND of claim a beat makes. This is the axis the visual is chosen on, and
#: naming it explicitly is the whole point of the strategist step.
#:
#: The educational visual rules the reviewer wrote are mostly rules about THIS
#: field — "if the concept describes a process, animate the process"; "if it
#: describes a comparison, show both states simultaneously"; "if it describes data
#: movement, animate the data movement". None of them can be followed by a step
#: that never decides which one it is looking at, and the old pipeline never did:
#: spec_visuals went straight from a sentence to a template name, so the
#: relationship was implicit in a choice rather than a thing that could be checked.
#:
#: Made explicit, it becomes checkable. A beat that says "process" and renders a
#: static "bar" is a detectable mismatch; the same frame with no declared
#: relationship is just a frame.
Relationship = Literal[
    "process",        # a sequence of events -> rule 6, animate it
    "comparison",     # two states weighed against each other -> rule 7, both at once
    "data_movement",  # something travels from A to B -> rule 8, animate the travel
    "hierarchy",      # containment or levels -> rule 9, spatial hierarchy
    "cause_effect",   # this makes that happen -> rule 10, animate cause then effect
    "structure",      # one thing divided into named parts, held still
    "effect",         # how something LOOKS; the picture IS the answer
    "quantity",       # a figure is the whole point
]


class BeatStrategy(BaseModel):
    """What ONE beat's frame has to make a viewer see, decided before any template.

    THE STEP THAT WAS MISSING. spec_visuals was asked to do two different jobs in
    one call: decide what the viewer should see, and pick the shape that shows it.
    Asked for both at once it did the second one — a template name is a concrete,
    answerable thing and "what should someone SEE to understand this" is not — so
    the frames came out well-formed and educationally empty. That is the reviewer's
    scoring exactly: visual correctness 9, educational clarity 4.

    Separating them forces the question to be answered in words, in its own field,
    before a template is on the table. The template is then chosen to serve an
    answer that already exists rather than standing in for one.
    """
    ref: str

    #: The ONE idea this beat teaches, in a learner's words. Not the beat's
    #: sentence — the idea under it.
    concept: str

    #: What kind of claim it is. Decides which visual rules apply.
    relationship: Relationship

    #: WHAT THE VIEWER MUST SEE — objects, relationships, states. Written as
    #: things on a screen, never as a sentence to print.
    #:
    #: Rule 3 is the test this field exists to pass: the scene must communicate
    #: the concept even if all text is removed. If what is written here stops
    #: making sense once you delete the labels, the strategy is a caption.
    must_see: str

    #: What a viewer would notice changing since the previous beat, with the sound
    #: off. Empty on the first beat.
    changes_from_previous: str = ""

    #: The single object that carries the accent. Exactly one, always.
    focus: str


class VisualStrategy(BaseModel):
    """The composition plan for one short, before any of it is drawn."""

    #: What the whole short is a picture OF — the one subject every frame develops.
    subject: str
    beats: list[BeatStrategy] = Field(default_factory=list)

    def by_ref(self) -> dict[str, BeatStrategy]:
        return {b.ref: b for b in self.beats}


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
                      "code", "compare", "preview", "icons",
                      "hierarchy", "cause_effect", "takeaway"]
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

    #: hierarchy — levels stacked top to bottom, each resting on the one below.
    #:
    #: RULE 9 ("if the concept describes hierarchy, use spatial hierarchy") had no
    #: shape to be expressed in. The nearest pictorial template was `icons`, which
    #: lays its glyphs out IN A ROW — so the layered-system frame the brief quotes
    #: as its worst example, "Users / Applications / Operating System / Hardware",
    #: was drawn as four peers side by side. The arrangement said the opposite of
    #: the concept, and only the reading order of the labels carried the truth.
    levels: list[Cell] = Field(default_factory=list)

    #: cause_effect — the thing that makes something happen, and what happens.
    #:
    #: Rule 10. These went to `flow` before, which draws equal boxes descending a
    #: column and therefore says "a process with two stages" — a different claim
    #: from "this makes that true", and the beat is always about the second one.
    cause: Optional[Cell] = None
    effect: Optional[Cell] = None
    #: cause_effect — the mechanism, written ON the arrow. The one place in this
    #: renderer where the RELATIONSHIP gets named rather than the things it joins.
    mechanism: Optional[str] = None


class VisualScore(BaseModel):
    """What the educational vision judge saw when it LOOKED at one rendered frame.

    Every other score in this file is a judgement about text. This one is a
    judgement about a picture, and the axes are the reviewer's own, kept on their
    0-10 scale rather than squeezed onto EvalReport's 1-5 so the numbers in the
    brief and the numbers in the report are the same numbers.

    TEXT_DEPENDENCY RUNS BACKWARDS AND THAT IS DELIBERATE. It is the only field
    here where high is bad, because it measures a defect rather than a quality:
    how much of this frame's meaning is carried by reading rather than by seeing.
    The reviewer scored the old frames 8/10 on it and marked it BAD. Flipping it to
    a "visual independence" score would have made every axis point the same way and
    made the field stop meaning what it was named for, so it keeps its direction
    and every comparison against it is spelled out at the point of use.
    """
    #: Is the SVG sound — valid, positioned, nothing clipped or overlapping?
    #: The templates make this true by construction, so a low score here is a
    #: renderer bug worth knowing about rather than a redesign to ask for.
    visual_correctness: int = Field(ge=0, le=10)

    #: Could a learner understand the concept from this picture? The gate.
    educational_clarity: int = Field(ge=0, le=10)

    #: HIGH IS BAD. How much of the frame's meaning needs reading. 10 means it is
    #: a slide of words; 0 means the picture would teach with every label erased.
    text_dependency: int = Field(ge=0, le=10)

    #: Does the motion carry the concept, or is it decoration? Scored from the
    #: still plus the motion plan the judge is given in text — see skills/vision.py.
    animation_relevance: int = Field(ge=0, le=10)

    #: Does the visual show the RELATIONSHIP the beat is about?
    concept_communication: int = Field(ge=0, le=10)

    #: Specific, actionable defects. These are what a redesign is shown.
    problems: list[str] = Field(default_factory=list)

    #: Which ref this scored, so a report can be read without its dict key.
    ref: str = ""

    def failures(self) -> list[str]:
        """Every threshold this frame is under, as sentences a redesign can act on.

        Imported late so schema stays importable without config — the thresholds
        are configuration, and this module is what config-free tools parse.
        """
        from . import config
        out = []
        if self.educational_clarity < config.VISION_MIN_CLARITY:
            out.append(
                f"educational_clarity {self.educational_clarity}/10 is below "
                f"{config.VISION_MIN_CLARITY}: a learner could not understand the "
                f"concept from this picture")
        if self.text_dependency > config.VISION_MAX_TEXT_DEPENDENCY:
            out.append(
                f"text_dependency {self.text_dependency}/10 is above "
                f"{config.VISION_MAX_TEXT_DEPENDENCY}: the frame's meaning is carried "
                f"by reading it, not by seeing it")
        return out

    @property
    def passed(self) -> bool:
        return not self.failures()


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

    #: What the strategist decided this frame had to make a viewer see, kept so a
    #: later redesign or a human reviewer can read the intent rather than
    #: reverse-engineering it from the template that was chosen.
    strategy: Optional[BeatStrategy] = None

    #: The vision judge's verdict on the rendered pixels, when one was taken.
    #: None means it was not run (no browser, or turned off), which is
    #: deliberately distinct from a zero — see skills/vision.py.
    score: Optional[VisualScore] = None


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

    #: What SKILL 1b understood about the source section before the script existed.
    #:
    #: RECORDED SO IT CAN BE READ, on the same terms as vision_scores below. The
    #: understanding is computed once per short and was otherwise a thing that
    #: happened inside one process and vanished — which makes "was this reel weak
    #: because the section is thin, or because the writer wandered?" a question you
    #: could only answer by paying for the reading again.
    #:
    #: Nothing downstream consumes it yet. skills/script.py's prompt is unchanged;
    #: wiring it in is a separate change so the judge's scores can attribute the
    #: difference. Optional and None by default, so all 37 units written before this
    #: field existed still load.
    understanding: Optional[SectionUnderstanding] = None
    #: What the vision judge scored each frame, kept instead of thrown away.
    #:
    #: RECORDED, NEVER READ BACK. judge_frames already rasterises every frame and
    #: scores it, the design loop uses those scores to decide on a redesign, and then
    #: they were discarded — so "which of my frames are weak" could only be answered
    #: by paying for the judgement again, one short at a time. Storing it makes that
    #: a question about output/ rather than about the API.
    #:
    #: Nothing downstream consumes this. It is not sent to any model (spec_visuals is
    #: handed `previous` visuals, not the unit), it is not in the feed payload
    #: (feed.collect builds its keys explicitly), and it is not rendered. Optional and
    #: empty by default so every unit written before it still loads.
    vision_scores: dict[str, dict] = Field(default_factory=dict)

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
