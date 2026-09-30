"""
SKILL 5a — LOOK at the rendered frames and score whether they teach.

THE GAP THIS FILLS
Everything else that grades a diagram in this project reads its description.
checks.py walks the Frame's fields; skills/audit.py hands the judge the same Frame
as JSON. Those catch what structure can express — an invented code line, a label
the narration never says, two frames that do not differ — and they are the reason
the frames are correct.

They cannot catch the thing the frames were actually failing at, because it is not
in the structure. A frame can pass every one of them and still be four labelled
rectangles that communicate nothing, and the reviewer's scoring says exactly that:

    Visual correctness      9/10
    Educational clarity     4/10
    Text dependency         8/10   <- BAD
    Animation relevance     3/10
    Concept communication   5/10

Nine out of ten on the axis the graders measure. Four on the axis nobody was
measuring. The only way to close that is to render the picture and look at it,
which is what this does.

ONE CALL FOR THE WHOLE SHORT, NOT ONE PER FRAME
The frames go in together, in beat order, as one multimodal turn. Cheaper, but
that is not the reason — the reason is that the loudest complaint these shorts get
is about the SEQUENCE ("showing same visuals again and again which feel bore"),
and a judge shown one frame at a time cannot see it. Four separate calls each
score a perfectly good picture 8/10 and none of them notices it is the same
picture four times.

WHAT IT IS TOLD ABOUT MOTION
A still cannot show animation, and animation_relevance is one of the axes. So the
judge is given the frame's MOTION PLAN in text — the arrival order the renderer
tagged and what the player does with each tag — and scores the motion from the
still plus the plan. That is honest about what it saw and it is enough to catch
the defect that matters: motion that is decoration, arriving in an order that has
nothing to do with the explanation.

WHY IT MUST NOT BE THE MODEL THAT DREW THE FRAME
See config._vision_warning. A model grading its own composition approves it.
"""
import re
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ..schema import Script, Section, Visual, VisualScore, VisualStrategy, Shot, StoryFrameJudge
from ..llm import ask_json
from .. import config, raster
from .strategy import EDUCATIONAL_VISUAL_RULES


class VisionReport(BaseModel):
    """Every frame's verdict, plus what is wrong with the sequence as a whole."""
    frames: list[VisualScore] = Field(default_factory=list)
    #: Defects that belong to the SHORT rather than to any single frame — the same
    #: picture twice, a composition that never develops, a build that returns to a
    #: scene it already showed. Folded into the worst offending frame's problems by
    #: judge_frames so the redesign loop sees them.
    composition_problems: list[str] = Field(default_factory=list)


JUDGE_SYSTEM = """You are the EDUCATIONAL VISION JUDGE for a short teaching video.

You are shown the ACTUAL RENDERED FRAMES of one short, in beat order, exactly as a
learner sees them. You are the only step in this pipeline that can see a picture.
Every other check reads the JSON the picture was built from, so they have already
confirmed that the labels come from the narration, the code is really in the
document, and nothing overlaps. Do not spend your answer re-checking those.

Your question is the one nothing else can ask:

    WOULD A LEARNER UNDERSTAND THE CONCEPT FROM THIS PICTURE?

__RULES__

SCORE EACH FRAME 0-10 ON FIVE AXES

visual_correctness — is the SVG sound? Positioned properly, nothing clipped,
    overlapping, or running off the canvas, nothing rendered as a broken glyph.
    These frames come from a template renderer that computes every coordinate, so
    this should be high. If it is not, say precisely what is wrong: it means the
    renderer has a bug, which is worth more than a redesign.

educational_clarity — could a learner who has not read the material understand
    the concept from this frame?
    9-10 the picture teaches on its own; the narration confirms what was seen
    7-8  understandable; a learner gets it with the audio
    5-6  the frame is about the right thing but shows it weakly
    3-4  correct, tidy, and communicates nothing — labelled containers
    0-2  the picture would mislead
    THIS IS THE GATE. Score it strictly. A neat diagram is not a clear one, and
    the failure being hunted here scores 4: everything correct, nothing taught.

text_dependency — HIGH IS BAD, and read the direction twice before answering.
    How much of this frame's meaning is carried by READING rather than by SEEING?
    Apply rule 3 literally: mentally delete every label.
    0-2  the picture still teaches with the words gone
    3-5  the words name things the picture already shows
    6-8  the picture is containers; the words are the content
    9-10 it is a slide of sentences
    A row of four boxes reading "Users", "Applications", "Hardware" is an 8: the
    boxes are identical, so every distinction is in the text.

animation_relevance — you are given each frame's MOTION PLAN below. Does the
    motion carry the explanation, or is it decoration?
    9-10 the motion IS the concept — the process runs, the data travels, the
         cause fires before the effect
    5-6  a sensible build order that does not itself explain anything
    0-3  parts appearing in an arbitrary order, or motion on a frame whose concept
         has nothing moving in it
    Judge it against the beat's relationship, which is given. A "process" or
    "data_movement" beat whose plan is "everything arrives together" scores low —
    rules 6 and 8 are not being followed. A "structure" beat does not need motion
    and is not penalised for arriving quietly.

concept_communication — does the frame show the RELATIONSHIP the beat is about?
    Not the topic, the relationship. A frame about "the browser fetches the
    stylesheet" that draws a browser and a stylesheet side by side with no arrow
    has the right objects and shows no relationship: that is a 4. The same two
    objects with the file travelling along an arrow into the browser is a 9.

BE SPECIFIC IN `problems`, AND WRITE THEM AS INSTRUCTIONS
Each problem is one actionable sentence naming what to change. The redesign step
is shown these verbatim and cannot see your reasoning.
  BAD   "the frame is unclear"
  GOOD  "the three boxes are identical rectangles, so nothing is visible until the
        labels are read — draw the OS as a slab the app windows physically rest on
        so the layering carries the claim"
Leave it empty for a frame you are not asking to change.

`composition_problems` IS ABOUT THE SEQUENCE, NOT ANY ONE FRAME
Look across all the images together and report:
  * two frames that are the same picture with only the accent moved
  * a composition that returns to a scene it already showed
  * a sequence where nothing develops — the viewer has read everything by frame 1
  * a first frame that is a title card or restates the question instead of drawing
    the subject
This is the most common complaint these shorts get and no single-frame score
catches it. Empty if the sequence genuinely builds.

DO NOT GRADE THE NARRATION. It is given only so you know what each frame is meant
to be showing. A frame that is a beautiful picture of the wrong thing scores low
on concept_communication; a frame that is an accurate picture of the right thing
scores high even if the sentence is clumsy.

Output JSON:
{"frames":[{"ref":"...","visual_correctness":n,"educational_clarity":n,
  "text_dependency":n,"animation_relevance":n,"concept_communication":n,
  "problems":["..."]}],
 "composition_problems":["..."]}

Return one entry per image, with `ref` copied exactly from the label given for
that image."""

JUDGE_SYSTEM = JUDGE_SYSTEM.replace("__RULES__", EDUCATIONAL_VISUAL_RULES)


#: Every tagged element in a rendered SVG. layout.py writes data-enter for arrival
#: order and data-role for what the player should do with the element.
_TAG_RE = re.compile(
    r"<(?P<tag>[a-zA-Z]+)(?P<attrs>[^>]*?)"
    r"(?:data-enter=\"(?P<enter>\d+)\"|data-role=\"(?P<role>[a-z]+)\")[^>]*>")


def motion_plan(svg: str) -> str:
    """
    What the player will actually DO with this frame, in words.

    Read off the tags the renderer emitted rather than guessed at, because the
    behaviour lives in web/src/AnimatedSvg.tsx and the tags are the contract
    between the two. If that file changes what a role means, this sentence becomes
    wrong — which is a real maintenance cost, and cheaper than the alternative of
    the judge scoring animation it was never told anything about.
    """
    stages: dict[int, int] = {}
    roles: dict[str, int] = {}
    for m in _TAG_RE.finditer(svg):
        whole = m.group(0)
        e = re.search(r'data-enter="(\d+)"', whole)
        if e:
            stages[int(e.group(1))] = stages.get(int(e.group(1)), 0) + 1
        r = re.search(r'data-role="([a-z]+)"', whole)
        if r:
            roles[r.group(1)] = roles.get(r.group(1), 0) + 1

    if not stages:
        return ("untagged — the whole frame fades in at once, in document order. "
                "No part of the build carries meaning.")

    order = sorted(stages)
    lines = [f"arrives in {len(order)} stages, spread across roughly the first half "
             f"of the spoken beat (about a second apart), then holds still while the "
             f"line finishes:"]
    for i, key in enumerate(order, 1):
        n = stages[key]
        lines.append(f"  stage {i}: {n} element{'s' if n != 1 else ''}")

    if roles.get("focus"):
        lines.append(f"  {roles['focus']} element(s) tagged focus — arrive on their own "
                     f"stage and hold the eye")
    if roles.get("flow"):
        lines.append(f"  {roles['flow']} arrow(s) tagged flow — drawn along their own "
                     f"length, then dashes march along them continuously to show "
                     f"direction of travel")
    if roles.get("travel"):
        lines.append(f"  {roles['travel']} arrow group(s) tagged travel — a payload token "
                     f"leaves the source, moves along the arrow, and arrives at the "
                     f"target, repeating. The transfer is drawn, not implied")
    if roles.get("base"):
        lines.append(f"  {roles['base']} element(s) tagged base — carried over from the "
                     f"previous beat, already on screen, not re-animated")
    lines.append("  strokes are drawn along their length; filled shapes rise and fade in")
    return "\n".join(lines)


def judge_frames(script: Script, visuals: dict[str, Visual],
                 strategy: VisualStrategy | None = None,
                 section: Section | None = None,
                 model_override: str | None = None) -> tuple[dict[str, VisualScore], list[str]]:
    """
    Rasterise this short's frames and score them by looking.

    Returns ({ref: score}, composition_problems). An EMPTY dict means the judge did
    not run — no browser, no frames, or VISION_JUDGE=0 — and that is deliberately
    distinguishable from a dict of low scores. A caller that cannot tell "not
    judged" from "judged badly" will either gate on nothing or redesign everything.

    NEVER RAISES ON A MISSING BROWSER. The vision pass is an improvement to a
    pipeline that worked without it; a box with no Chromium must still build
    shorts, so every failure here degrades to "not judged" with a printed reason.
    """
    if not config.VISION_JUDGE:
        return {}, []

    refs, seen = [], set()
    for b in script.beats:
        if b.visual_ref not in seen and b.visual_ref in visuals:
            seen.add(b.visual_ref)
            refs.append(b.visual_ref)

    svgs = {ref: visuals[ref].svg for ref in refs if visuals[ref].svg}
    if not svgs:
        return {}, []

    try:
        pngs = raster.render_pngs(svgs)
    except raster.RasterUnavailable as e:
        print(f"    vision judge skipped: {e}")
        return {}, []
    except Exception as e:
        print(f"    vision judge skipped: {type(e).__name__}: {str(e)[:120]}")
        return {}, []

    shown = [ref for ref in refs if ref in pngs]
    if not shown:
        return {}, []

    by_ref = strategy.by_ref() if strategy else {}
    lines_by_ref: dict[str, list[str]] = {}
    for beat in script.beats:
        lines_by_ref.setdefault(beat.visual_ref, []).append(beat.line)

    blocks = []
    for i, ref in enumerate(shown, 1):
        plan = by_ref.get(ref)
        spoken = "\n    ".join(lines_by_ref.get(ref, []))
        block = [f"IMAGE {i} — ref: {ref}"]
        if plan:
            block.append(f"  concept:      {plan.concept}")
            block.append(f"  relationship: {plan.relationship}")
            block.append(f"  must show:    {plan.must_see}")
            block.append(f"  focus:        {plan.focus}")
        elif visuals[ref].spec:
            block.append(f"  intended:     {visuals[ref].spec}")
        block.append(f"  spoken over it:\n    {spoken}")
        block.append("  MOTION PLAN: " + motion_plan(svgs[ref]).replace("\n", "\n  "))
        blocks.append("\n".join(block))

    user = f"""QUESTION THIS SHORT ANSWERS: {script.question}
"""
    if strategy:
        user += f"WHAT THE WHOLE SHORT IS A PICTURE OF: {strategy.subject}\n"
    user += f"""
{len(shown)} IMAGES FOLLOW, IN BEAT ORDER. They are the real rendered frames, on the
same light card the viewer watches them on.

{chr(10).join(blocks)}

Score every image and report what is wrong with the sequence."""

    images = [pngs[ref] for ref in shown]
    report = ask_json(JUDGE_SYSTEM, user, VisionReport,
                      model=model_override or config.MODEL_VISION_JUDGE,
                      max_tokens=4000, think=True, label="vision_judge",
                      images=images)

    # REF DRIFT IS REPAIRED POSITIONALLY. A judge that renamed a ref, or returned
    # them in a different order, would otherwise lose every verdict — and losing a
    # verdict reads as "this frame passed", which is the one failure mode a gate
    # must not have. The images were sent in `shown` order and the model was asked
    # for one entry per image, so position is a sound fallback when the string is
    # not recognised.
    scored: dict[str, VisualScore] = {}
    unmatched = []
    for entry in report.frames:
        if entry.ref in svgs and entry.ref not in scored:
            scored[entry.ref] = entry
        else:
            unmatched.append(entry)
    for entry in unmatched:
        for ref in shown:
            if ref not in scored:
                entry.ref = ref
                scored[ref] = entry
                break

    return scored, list(report.composition_problems)


def problems_for_redesign(scored: dict[str, VisualScore],
                          composition_problems: list[str]) -> list[str]:
    """
    The judge's verdict as the feedback lines a redesign is shown.

    Only FAILING frames contribute their problems. A frame that cleared both
    thresholds may still have had a note attached, and feeding those back asks the
    designer to change frames that were working — which is how a retry loop makes
    a short worse. The composition problems always go in, because they are never
    about a frame that is individually fine.
    """
    out: list[str] = []
    for ref, score in scored.items():
        failures = score.failures()
        if not failures:
            continue
        detail = "; ".join(score.problems) or "no specific defect named"
        out.append(f"frame [{ref}] was LOOKED AT and rejected — "
                   + "; ".join(failures) + f". What the judge saw: {detail}")
    out += [f"the sequence as a whole: {p}" for p in composition_problems]
    return out


# =============================================================================
# STORY MODE — RESTYLE_TO_STORY_REELS.md Step 6 Part 2. A completely separate
# judge from judge_frames above (explainer mode, unchanged by anything below
# this line): that one scores a WHOLE SHORT's SVG diagrams against motion and
# narration; this one scores ONE GENERATED IMAGE FRAME against its shot spec
# and reference sheets. shorts/story_frames.py is the only caller.
# =============================================================================

STORY_FRAME_JUDGE_SYSTEM = """You are judging ONE generated illustration frame from an
illustrated teaching story, against its shot spec and reference images.

IMAGE 1 is the GENERATED FRAME being judged. The images after it are reference
material: the CAST REFERENCE SHEET(S) for every character in this shot, in
order, and then — unless this is the reel's first `wide` shot, which has none
— the SETTING REFERENCE (the first wide shot's own generated frame, already
approved, establishing what the setting looks like).

Score six axes, 1-5 each:

1. character_match — does every character in the frame match its reference
   sheet: head shape, hair, cap/badge, proportions? A character who looks
   like a different person (or a different cast member) scores low here,
   even if the picture is otherwise well-drawn.
2. no_text — no letters, garbled text, speech bubbles, or logos anywhere in
   the frame. A single stray letter-like mark is enough to fail this axis.
3. action_visible — the shot's own ACTION and KEY OBJECT are both clearly,
   unambiguously shown — a viewer who only sees this frame (sound off)
   should be able to tell what is physically happening. The key object
   should read as glowing softly in yellow.
4. emotion_readable — the shot's own EMOTION is readable on the character's
   face at PHONE SIZE, not just at full resolution — a subtle expression
   that only reads zoomed-in scores low here.
5. style_match — outlines, palette, and background follow the style bible:
   thick clean black outlines, off-white paper background, accent colors
   only purple/warm yellow, flat 2D, no gradients, no photorealism, no 3D.
6. setting_match — the same setting as the SETTING REFERENCE image. OMIT
   this field entirely (do not guess a score) if no setting reference image
   was given — that only happens for the reel's first `wide` shot.

PASS RULE (strict — read carefully, this is not "every axis >= 3"):
  - no_text MUST BE A PERFECT 5. Any text at all — even one stray letter-like
    mark — fails the whole frame, no exceptions.
  - character_match MUST BE >= 4. Merely recognizable is not enough; the
    fixed cast has to stay visually consistent across every shot in the feed.
  - action_visible, emotion_readable, style_match, and setting_match (when
    scored) each only need >= 3.

Be specific in `reasons`: name exactly what's wrong ("the badge is missing
from System's chest", "the whiteboard prop has become a laptop, not matching
the setting reference") rather than a vague restatement of a low score.

Output JSON: {"character_match": n, "no_text": n, "action_visible": n,
"emotion_readable": n, "style_match": n, "setting_match": n (or omit it),
"reasons": ["..."]}"""


#: RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #3 — the judge is rate-limited to
#: config.JUDGE_RPM calls/minute, with exponential backoff-and-retry (never a
#: hard failure) on a 429. Module-level (not per-call) state: the throttle
#: has to hold across every judge call in a process, not reset per shot.
_judge_lock = threading.Lock()
_last_judge_call: list[float] = [0.0]
JUDGE_MAX_RETRIES = 5


def _is_rate_limited(exc: Exception) -> bool:
    """True for anything that smells like an HTTP 429 — the Anthropic SDK's
    own RateLimitError when available, or any exception carrying a
    status_code/response.status_code of 429 (covers a raw HTTP client, or a
    gateway wrapping a different SDK). Never imports anthropic unconditionally
    at module load — this project already runs against gateways where that
    import may not even be present the same way."""
    try:
        import anthropic
        if isinstance(exc, anthropic.RateLimitError):
            return True
    except ImportError:
        pass
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status == 429


def _throttle_judge_rpm() -> None:
    """Block until at least 60/JUDGE_RPM seconds have passed since the last
    judge call started — a plain fixed-interval throttle, not a bursty token
    bucket, because a judge call is expensive enough that "space them out
    evenly" is the right shape, not "allow a burst then cool down".

    A NO-OP UNDER SHORTS_STUB=1 — there is no real rate limit to respect
    against a canned local response, and a mandatory 60/JUDGE_RPM-second
    sleep before every stub judge call would make the entire test suite
    minutes slower for a limit that does not apply to it.
    """
    if config.STUB:
        return
    with _judge_lock:
        min_interval = 60.0 / max(1, config.JUDGE_RPM)
        wait = _last_judge_call[0] + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_judge_call[0] = time.monotonic()


def judge_story_frame(frame_path: Path, shot: Shot, cast_refs: list[Path],
                      setting_ref: Path | None = None) -> StoryFrameJudge:
    """
    Look at ONE generated frame and score it against its own shot spec and
    reference images — story_frames.py's regenerate loop calls this only
    AFTER shorts.frame_checks.run_pre_checks has already passed (see that
    module's own docstring: no paying for a judge's opinion on a frame that
    is already known to be the wrong size or blank).

    `cast_refs` must be in the SAME order as build_shot_prompt's own
    "reference image n" numbering (skills.visuals.cast_refs_for_shot already
    guarantees that) — IMAGE 1 is always the generated frame; images 2..N+1
    are the cast refs, in order; the setting reference, when given, is last.

    RATE-LIMITED AND NEVER FAILS A REEL OVER IT (Step 7 Part 0 #3): every
    call waits for _throttle_judge_rpm() first, and a 429 is retried with
    exponential backoff (1s, 2s, 4s, ...) up to JUDGE_MAX_RETRIES times
    before finally raising — a reel stops on a genuinely broken judge call,
    never on ordinary rate limiting.
    """
    images = [Path(frame_path).read_bytes()]
    images += [Path(r).read_bytes() for r in cast_refs]
    if setting_ref is not None:
        images.append(Path(setting_ref).read_bytes())

    characters = ", ".join(shot.characters) or "(none — a Narrator-only shot)"
    user = f"""SHOT SPEC
characters: {characters}
framing:    {shot.framing}
emotion:    {shot.emotion or '(none)'}
action:     {shot.action}
key_prop:   {shot.key_prop or '(none)'}

{len(cast_refs)} cast reference sheet(s) follow the generated frame, in order.
{"A setting reference follows them — score setting_match." if setting_ref else
"No setting reference is given (first wide shot) — omit setting_match."}

Score the generated frame (IMAGE 1)."""

    for attempt in range(JUDGE_MAX_RETRIES + 1):
        _throttle_judge_rpm()
        try:
            return ask_json(STORY_FRAME_JUDGE_SYSTEM, user, StoryFrameJudge,
                            model=config.MODEL_STORY_VISION_JUDGE, max_tokens=1500,
                            think=True, label="story_frame_judge", images=images)
        except Exception as e:
            if _is_rate_limited(e) and attempt < JUDGE_MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise
