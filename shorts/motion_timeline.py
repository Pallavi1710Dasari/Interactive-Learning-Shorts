"""
The motion reel's CLOCK (RESTYLE_TO_MOTION_REELS.md phase 3). REEL_STYLE=motion only.

One function decides where every shot, caption and word sits in time —
shot_timings() — whether the caption durations come from real audio (the
voice stage) or from a word-count estimate (the scenes stage, before any
audio exists). The same function feeds the change-cadence grader at both
points, so a scene approved against the estimate is re-checked, unchanged,
against the real audio.

Then build_plan() resolves every scene's word cues to seconds, lays every
object out (motion_scenes.layout_scene) and writes the player's one input,
output/<short_id>/plan.json. The player (web/src/motion/scene/MotionStage)
is a pure function of (plan, t): it never resolves a cue or places an
object itself, so what the graders checked is exactly what it draws.
"""
import re
from dataclasses import dataclass, field

from .schema import (MOTION_WORDS_PER_SECOND, MotionActionTiming, MotionCaptionTiming,
                     MotionCastMember, MotionPlan, MotionScript, MotionShot, MotionShotPlan,
                     MotionWord, motion_plain_text)

#: Silence before a shot's first word: the transition plays and the scene
#: settles before anyone speaks.
SHOT_LEAD = 0.35
#: Silence after a shot's last word, before the next transition.
SHOT_TAIL = 0.45
#: Between two captions of the same speaker / a change of speaker.
CAPTION_GAP = 0.15
SPEAKER_GAP = 0.30
#: Shots whose own animation needs time whatever is said over them.
MIN_SHOT_SECONDS = {"title": 2.6, "chapter_card": 3.2, "cta": 2.4}


def caption_words(text: str) -> list[tuple[str, bool]]:
    """A caption's words as shown, each with whether it is a <b> highlight.
    Punctuation the tags separate from its word ("<b>useState</b>.") stays on
    that word, so the words here are the words a reader sees."""
    out: list[list] = []
    hl = False
    glue = False            # the next piece continues the previous word (no space)
    for piece in re.split(r"(</?b>)", text):
        if piece in ("<b>", "</b>"):
            hl = piece == "<b>"
            continue
        if not piece:
            continue
        starts_joined = not piece[0].isspace()
        for k, w in enumerate(piece.split()):
            if out and k == 0 and starts_joined and glue:
                out[-1][0] += w
                out[-1][1] = out[-1][1] or hl
            else:
                out.append([w, hl])
        glue = not piece[-1].isspace()
    merged: list[tuple[str, bool]] = []
    for w, h in out:
        if merged and not re.search(r"\w", w):
            merged[-1] = (merged[-1][0] + w, merged[-1][1])
        else:
            merged.append((w, h))
    return merged


def estimated_caption_seconds(shot: MotionShot) -> list[float]:
    """Each caption's spoken length estimated from the words of the speech
    it carries (MOTION_WORDS_PER_SECOND). Captions are the speech word for
    word (a code token may stand for several spoken words), so the shot's
    speech is shared out in proportion to each caption's word count."""
    spoken = len(shot.speech.split())
    shown = [max(1, len(motion_plain_text(c.text).split())) for c in shot.captions]
    total = sum(shown) or 1
    return [spoken * n / total / MOTION_WORDS_PER_SECOND for n in shown]


def even_words(text: str, start: float, end: float) -> list[MotionWord]:
    words = caption_words(text)
    if not words:
        return []
    step = (end - start) / len(words)
    return [MotionWord(text=w, start=round(start + i * step, 3),
                       end=round(start + (i + 1) * step, 3), hl=hl)
            for i, (w, hl) in enumerate(words)]


@dataclass
class ShotClock:
    """One shot on the reel's clock."""
    id: str
    start: float
    end: float
    captions: list[MotionCaptionTiming] = field(default_factory=list)

    def words(self) -> list[MotionWord]:
        return [w for c in self.captions for w in c.words]


def shot_timings(script: MotionScript, caption_seconds: dict[str, list[float]] | None = None,
                 word_times: dict[str, list[list[tuple[float, float]] | None]] | None = None,
                 sources: dict[str, list[str]] | None = None,
                 offset: float = 0.0) -> list[ShotClock]:
    """Every shot and caption on one clock.

    caption_seconds: shot id -> each caption's real audio length (the voice
    stage). Missing: estimated. word_times: shot id -> per caption, each
    word's (start, end) relative to that caption's audio, or None for an
    even split. sources: shot id -> per caption, the timing source. offset:
    seconds before the first shot (the optional intro sting)."""
    clocks: list[ShotClock] = []
    t = float(offset)
    for shot in script.shots:
        secs = (caption_seconds or {}).get(shot.id) or estimated_caption_seconds(shot)
        times = (word_times or {}).get(shot.id) or [None] * len(shot.captions)
        srcs = (sources or {}).get(shot.id) or ["even"] * len(shot.captions)
        start = t
        cur = start + SHOT_LEAD
        caps: list[MotionCaptionTiming] = []
        prev_speaker = None
        for i, cap in enumerate(shot.captions):
            if i:
                cur += SPEAKER_GAP if cap.speaker != prev_speaker else CAPTION_GAP
            dur = secs[i] if i < len(secs) else 0.0
            wt = times[i] if i < len(times) else None
            shown = caption_words(cap.text)
            if wt and len(wt) == len(shown):
                words = [MotionWord(text=w, hl=hl, start=round(cur + a, 3), end=round(cur + b, 3))
                         for (w, hl), (a, b) in zip(shown, wt)]
                source = srcs[i] if i < len(srcs) else "even"
            else:
                words = even_words(cap.text, cur, cur + dur)
                source = "even"
            caps.append(MotionCaptionTiming(text=cap.text, speaker=cap.speaker,
                                            start=round(cur, 3), end=round(cur + dur, 3),
                                            words=words, source=source))
            cur += dur
            prev_speaker = cap.speaker
        end = max(cur + SHOT_TAIL, start + MIN_SHOT_SECONDS.get(shot.beat, 0.0))
        clocks.append(ShotClock(id=shot.id, start=round(start, 3), end=round(end, 3),
                                captions=caps))
        t = end
    return clocks


#: Silence kept around a clip's speech when it is trimmed (trim_to_speech):
#: a breath before the first word, a short settle after the last.
TRIM_PAD_IN = 0.06
TRIM_PAD_OUT = 0.15


def trim_to_speech(seconds: dict[str, list[float]], word_times: dict[str, list],
                   sources: dict[str, list[str]]) -> tuple[dict, dict, dict]:
    """Every aligned clip cut to its speech: a TTS clip carries 0.2-0.4 s of
    silence before its first word and after its last, which the timeline
    then adds to its own gaps — 0.75 s of dead air between sentences and
    1.5 s between shots (12.7 s of plain_variable_no_rerender__motion's
    93 s). Uses the word times the alignment already found; a clip timed by
    an even split (no alignment) is left whole. Returns (seconds, word_times,
    trims) with trims: shot id -> per clip (cut_from, cut_to) in clip seconds,
    for motion_voice.mix."""
    out_s: dict = {}
    out_t: dict = {}
    trims: dict = {}
    for sid, secs in seconds.items():
        times = word_times.get(sid) or [None] * len(secs)
        srcs = sources.get(sid) or ["even"] * len(secs)
        out_s[sid], out_t[sid], trims[sid] = [], [], []
        for dur, wt, src in zip(secs, times, srcs):
            if not wt or src == "even":
                out_s[sid].append(dur); out_t[sid].append(wt); trims[sid].append((0.0, dur))
                continue
            a = max(0.0, wt[0][0] - TRIM_PAD_IN)
            b = min(dur, wt[-1][1] + TRIM_PAD_OUT)
            if b - a < 0.3:                       # a clip the aligner could not place
                out_s[sid].append(dur); out_t[sid].append(wt); trims[sid].append((0.0, dur))
                continue
            out_s[sid].append(round(b - a, 3))
            out_t[sid].append([(round(s - a, 3), round(e - a, 3)) for s, e in wt])
            trims[sid].append((round(a, 3), round(b, 3)))
    return out_s, out_t, trims


def total_seconds(clocks: list[ShotClock]) -> float:
    return clocks[-1].end if clocks else 0.0


_SOURCE_RANK = {"forced_alignment": 2, "whisper": 1, "even": 0}


def build_plan(script: MotionScript, clocks: list[ShotClock], audio: str | None = None,
               cast: list[MotionCastMember] | None = None, tags: list[str] | None = None,
               intro: float = 0.0, characters: bool = False,
               character: str | None = None, design: str = "classic",
               host_character: str | None = None) -> MotionPlan:
    """The player's input: every shot's scene laid out, every cue resolved to
    seconds, every caption and word on the reel's clock.

    `characters` adds the animated-character layer (motion_characters;
    config.MOTION_CHARACTERS): one character per speaker — two on a
    two-speaker reel, one narrator on a one-narrator reel.
    `character` names the preset that plays the reel's language (default:
    the language's own). The characters show on a shot that is not a
    full-frame card and whose objects fit the upper region (where they are
    then laid out) — on a two-speaker reel too: drawing them under objects
    that do not fit put a panel on top of both characters."""
    from . import motion_library as lib
    from .motion_scenes import layout_scene, resolve_actions, stack_height
    from . import motion_characters
    duo = bool(script.speakers)
    if not characters:
        cast_mode = None
    elif duo:
        cast_mode = "duo" if cast and len(cast) == len(script.speakers) == 2 else None
    else:
        cast_mode = "narrator"
    upper = lib.library()["frame"]["duo"]
    full_kinds = {k for k, spec in lib.object_kinds().items() if spec["layout"] == "full"}
    shots: list[MotionShotPlan] = []
    weakest = "forced_alignment"
    for shot, clock in zip(script.shots, clocks):
        if shot.scene is None:
            raise ValueError(f"{shot.id} has no scene — run the scenes stage first")
        full = any(o.kind in full_kinds for o in shot.scene.objects)
        fits = stack_height(shot.scene) <= upper["bottom"] - upper["top"]
        shown = bool(cast_mode) and not full and fits
        actions = [MotionActionTiming(t=t, do=a.do, target=a.target, value=a.value,
                                      tone=a.tone, cue=a.at)
                   for a, t in resolve_actions(shot, clock)]
        for c in clock.captions:
            if _SOURCE_RANK[c.source] < _SOURCE_RANK[weakest]:
                weakest = c.source
        shots.append(MotionShotPlan(
            id=shot.id, beat=shot.beat, chapter=shot.chapter, start=clock.start, end=clock.end,
            field=shot.scene.field, transition=shot.scene.transition, label=shot.scene.label,
            layout="duo" if duo else "solo", characters=shown,
            objects=layout_scene(shot.scene, duo=duo or shown),
            actions=actions, captions=clock.captions))
    from .motion_identities import identity, languages
    from .motion_themes import theme_for_script
    from .schema import MotionIdentitySpec
    ident = (MotionIdentitySpec(**identity(script.language).spec())
             if script.language in languages() else None)
    captions = [c for s in shots for c in s.captions]
    tracks = (motion_characters.direct(cast or [], captions, script.language, character, host_character)
              if cast_mode == "duo"
              else motion_characters.direct_narrator(captions, script.language, character)
              if cast_mode == "narrator" else [])
    return MotionPlan(short_id=script.short_id, template=script.template, theme=script.theme, design=design,
                      series=script.series, concept_name=script.concept_name,
                      duration=total_seconds(clocks), audio=audio,
                      timing_source=weakest if shots else "even",
                      identity=ident, theme_label=theme_for_script(script).display,
                      tags=list(tags or []), intro=float(intro),
                      cast=cast or [], characters=tracks, shots=shots)
