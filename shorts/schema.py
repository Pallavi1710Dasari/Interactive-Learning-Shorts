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
MIN_SECONDS = 18
MAX_SECONDS = 45
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


class Visual(BaseModel):
    """Output of Skills 3 and 4."""
    ref: str
    type: Literal["diagram", "image", "text"]
    spec: str                       # what it should show, in words
    svg: Optional[str] = None       # filled in for type == "diagram"
    image_path: Optional[str] = None


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
    status: Literal["draft", "audited", "approved", "rendered", "rejected"] = "draft"
    video_path: Optional[str] = None

    @field_validator("visuals")
    @classmethod
    def every_ref_resolved(cls, v, info):
        beats = info.data.get("beats") or []
        missing = {b.visual_ref for b in beats} - set(v.keys())
        if missing:
            raise ValueError(f"beats reference visuals that don't exist: {sorted(missing)}")
        return v
