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

MIN_SECONDS = 30
MAX_SECONDS = 60
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


class TopicList(BaseModel):
    topics: list[Topic]

    @field_validator("topics")
    @classmethod
    def check_count(cls, v):
        if not 3 <= len(v) <= 12:
            raise ValueError(f"expected 3-12 topics, got {len(v)}")
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


class Audio(BaseModel):
    file: str
    duration_seconds: float
    word_timings: list[WordTiming]


class EvalReport(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    pace: int = Field(ge=1, le=5)
    diagram_correct: bool
    problems: list[str] = []

    @property
    def passed(self) -> bool:
        return (
            self.faithfulness >= 4
            and self.clarity >= 4
            and self.pace >= 3
            and self.diagram_correct
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
