"""
Characters that TEACH (the avatar upgrade, review of job f64077e78448).
Deterministic, no model call: it reads the plan (every caption word and every
scene action already on the reel clock) and directs the characters the way a
teacher at a board would move.

STAGING (plan.stage = "board", library.json frame.board). The visual is the
board, upper left; the explaining character (the language speaker, or the
narrator) stands large beside it on the right, half-body; the asking one is
smaller, lower left. The characters stay on screen through every explanation
shot — code and recap included; only the title and the CTA are theirs alone.

DIRECTION. On top of the rig's own life layer (blinks, breathing, sway):
  - the explainer AIMS an arm at the exact thing a scene action changes while
    it speaks (the player solves the arm so the finger points at it), and
    looks at it; otherwise looks at the asker;
  - counts on fingers on "first / second / third / two things / then" (a
    held count: the hand stays up between counts, only the fingers change);
  - shrugs at the wrong idea (a failure beat saying "not / isn't / doesn't"),
    open palms to explain a highlighted word, thumbs up and a nod when the
    asker gets it;
  - the asker leans in on the hook, tilts its head, curious, on a question,
    looks confused while the wrong idea is taken apart, nods along, looks at
    what the explainer points at, and has an "aha" (a lightbulb) when it says
    it gets it.
  - the jaw follows the LOUDNESS of the recorded voice (envelope), on top of
    the word-timed mouth shapes, and closes in silence.
"""
import re

import numpy as np

from . import config
from . import motion_library as lib
from .motion_camera import part_rect
from .schema import MotionCharacterCue

_NEG = {"not", "isnt", "doesnt", "dont", "never", "wrong", "cant", "wont", "arent"}
_AHA = ("now i get", "i get it", "so the", "so it", "oh", "i see", "that makes sense", "got it")
_COUNT = {"first": "countOne", "second": "countTwo", "third": "countThree", "finally": "countThree"}
_NUM = {"two": "countTwo", "2": "countTwo", "three": "countThree", "3": "countThree"}
_FAIL_BEATS = {"hook", "setup", "break_1", "break_2"}
_SMALL = set("a an the of to in on at for and or but is are it its this that so if be does do you we i my".split())
#: the gestures a cue may name (checked against the rig by motion.test.tsx)
GESTURES = {"point", "pointUp", "handsSpread", "presentLeft", "presentRight", "shrug", "thumbsUp", "nod",
            "nodSlow", "tiltCurious", "leanIn", "chinThink"}
EXPRESSIONS = {"happy", "neutral", "thinking", "confused", "surprised", "listening", "skeptical", "excited", "grin"}


def _plain(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def board() -> dict:
    return lib.library()["frame"]["board"]


# ===================================================================== staging

def stage_board(plan, configs: dict | None = None):
    """The plan staged as a board: characters on every shot but the title and
    the CTA, each track re-directed to teach. `configs`: role -> a rig
    CharacterConfig to wear instead of the track's (a new look)."""
    # off only where a full-frame title or end card is the whole shot
    shots = [s.model_copy(update={"characters": not any(o.kind in ("title_card", "end_card") for o in s.objects)})
             for s in plan.shots]
    staged = plan.model_copy(update={"stage": "board", "shots": shots})
    tracks = []
    for tr in staged.characters:
        cfg = (configs or {}).get(tr.role or "NARRATOR", tr.config)
        tracks.append(tr.model_copy(update={"config": cfg, "cues": []}))
    staged = staged.model_copy(update={"characters": tracks})
    return direct(staged)


# ===================================================================== director

class _Cues:
    def __init__(self):
        self.cues: list[MotionCharacterCue] = []
        self.last_hand = -1e9
        self.last_head = -1e9
        self.face = ""

    def express(self, t, name, cue=""):
        if name != self.face:
            self.cues.append(MotionCharacterCue(t=round(max(0.0, t), 3), kind="expression", name=name, cue=cue))
            self.face = name

    def hand(self, t, name, cue="", gap=1.8, side=None) -> bool:
        if t - self.last_hand < gap:
            return False
        self.cues.append(MotionCharacterCue(t=round(max(0.0, t), 3), kind="gesture", name=name, cue=cue, side=side))
        self.last_hand = t
        return True

    def head(self, t, name, cue="", gap=1.6) -> bool:
        if t - self.last_head < gap:
            return False
        self.cues.append(MotionCharacterCue(t=round(max(0.0, t), 3), kind="gesture", name=name, cue=cue))
        self.last_head = t
        return True

    def gaze(self, t, until, rect=None, target="partner", full=False):
        self.cues.append(MotionCharacterCue(t=round(t, 3), kind="gaze", until=round(until, 3), target=target,
                                            rect=[round(v, 1) for v in rect] if rect else None, full=full))


def _rect_of(shot, action):
    o = next((o for o in shot.objects if o.id == action.target), None)
    if o is None or o.kind in ("connector",):
        return None, False
    part = int(action.value) if action.do == "highlight" and str(action.value or "").isdigit() else None
    if o.kind == "compare":
        part = 2 if action.do == "reveal" else 1      # the wrong side until the fix is revealed
    r = part_rect(o, part)
    full = o.kind if lib.object_kinds()[o.kind]["layout"] == "full" else False
    return r, full


def direct(plan):
    """Every track's teaching cues (see the module docstring)."""
    if not plan.characters:
        return plan
    by_role = {t.role: t for t in plan.characters}
    explainer = next((t for t in plan.characters if t.side in ("right", "center")), plan.characters[0])
    asker = next((t for t in plan.characters if t is not explainer), None)
    ex, ak = _Cues(), _Cues()
    ex.express(0.0, "happy")
    if asker:
        ak.express(0.0, "listening")
    for shot in plan.shots:
        if not shot.characters:
            continue
        acts = sorted([a for a in shot.actions if a.do != "enter" or a.cue not in ("start", "")], key=lambda a: a.t)
        last_aim = -1e9
        for ci, cap in enumerate(shot.captions):
            words = cap.words
            if not words:
                continue
            plain = [_plain(w.text) for w in words]
            text = " ".join(plain)
            me_track = by_role.get(cap.speaker, explainer)
            speaking_ex = me_track is explainer
            me, other = (ex, ak) if speaking_ex else (ak, ex)
            # --- the asker
            if not speaking_ex:
                if shot.beat == "hook":
                    me.hand(words[0].start - 0.15, "leanIn", words[0].text, gap=0)
                if cap.text.rstrip().endswith("?"):
                    me.express(words[0].start - 0.1, "thinking", words[0].text)
                    me.head(words[0].start, "tiltCurious", words[0].text)
                elif any(text.startswith(a) or f" {a}" in f" {text}" for a in _AHA) or shot.beat == "payoff":
                    w = next((w for w in words if _plain(w.text) not in _SMALL), words[0])
                    me.cues.append(MotionCharacterCue(t=round(w.start, 3), kind="aha", cue=w.text))
                    me.express(w.start, "surprised", w.text)
                    me.express(w.start + 0.7, "happy", w.text)
                    # the explainer is pleased: a nod, then a thumbs up on the last word
                    other.head(w.start + 0.2, "nod", w.text, gap=0.5)
                    other.hand(words[-1].start - 0.2, "thumbsUp", words[-1].text, gap=0.8,
                               side="R" if explainer.side == "right" else None)
                    other.express(words[-1].start, "happy", words[-1].text)   # a light smile, never a grin
                else:
                    me.express(words[0].start - 0.1, "neutral", words[0].text)
                # both look at each other while the asker talks
                me.gaze(words[0].start - 0.1, cap.end + 0.1)
                other.gaze(words[0].start, cap.end + 0.1)
                continue
            # --- the explainer
            fail = shot.beat in _FAIL_BEATS and bool(set(plain) & _NEG)
            me.express(words[0].start - 0.1, "skeptical" if fail else "happy", words[0].text)
            if asker:
                ak.express(words[0].start + 0.2, "confused" if fail else "listening", words[0].text)
                if fail:
                    ak.head(words[0].start + 0.3, "tiltCurious", words[0].text)
            done_hand = False
            if fail:
                i = next(i for i, p in enumerate(plain) if p in _NEG)
                done_hand = me.hand(words[i].start - 0.2, "shrug", words[i].text)
            # counting on fingers
            for i, p in enumerate(plain):
                name = _COUNT.get(p) or (_NUM.get(p) if i + 1 < len(plain) and plain[i + 1] in ("things", "steps", "ways", "parts") else None)
                if p == "then" and any(c.kind == "count" and c.name == "one" for c in me.cues[-6:]):
                    name = "countTwo"
                # a held count (cast/teach.ts): the hand rises once beside the
                # face on the side facing the board and the fingers change
                # between counts, so it never swings out through a sideways pose
                if name and words[i].start - 0.2 - me.last_hand >= 0.7:
                    arm = "L" if me_track.side == "right" else "R"
                    fingers = {"countOne": "one", "countTwo": "two", "countThree": "three"}[name]
                    me.cues.append(MotionCharacterCue(t=round(words[i].start - 0.25, 3), kind="count", name=fingers,
                                                      side=arm, until=round(words[i].start + 1.4, 3), cue=words[i].text))
                    me.last_hand = words[i].start - 0.2
                    done_hand = True
                    break
            # aim at what changes on the board while this is said
            spoken = [a for a in acts if cap.start - 0.05 <= a.t <= cap.end + 0.05]
            for a in spoken:
                rect, full = _rect_of(shot, a)
                if rect is None:
                    continue
                # a reveal or a state change is what the sentence is about: it takes
                # over from a lesser point (a pulse, an entrance) still being held
                key = a.do in ("reveal", "state")
                prev = next((c for c in reversed(me.cues) if c.kind == "aim"), None)
                if key and prev is not None and a.t - last_aim < 2.0 and prev.target != a.target or (
                        key and prev is not None and prev.rect != [round(v, 1) for v in rect] and a.t - last_aim < 2.0):
                    prev.until = round(a.t - 0.3, 3)
                elif a.t - last_aim < 2.0 or done_hand and a.t - me.last_hand < 1.6:
                    continue
                until = min(a.t + 1.7, cap.end + 0.35)
                arm = "L" if me_track.side == "right" else "R"
                me.cues.append(MotionCharacterCue(t=round(a.t - 0.3, 3), kind="aim", side=arm, until=round(until, 3),
                                                  rect=[round(v, 1) for v in rect], target=a.target, full=full,
                                                  cue=a.cue))
                me.gaze(a.t - 0.35, until, rect, a.target, full)
                if asker:
                    ak.gaze(a.t - 0.2, until + 0.2, rect, a.target, full)
                me.last_hand = a.t
                last_aim = a.t
                done_hand = True
            if not done_hand:
                hl = [i for i, w in enumerate(words) if w.hl]
                if hl:
                    # the idea itself is presented toward the board, palm up; elsewhere
                    # both open palms explain it
                    present = shot.beat in ("title", "fix_idea", "code_map", "recap")
                    name = ("presentLeft" if me_track.side == "right" else "presentRight") if present else "handsSpread"
                    me.hand(words[hl[0]].start - 0.2, name, words[hl[0]].text)
            # talk to the asker at the start of each line; the asker nods along
            me.gaze(words[0].start - 0.1, min(cap.end, words[0].start + 1.4))
            if asker and len(words) >= 5 and not fail:
                mid = words[len(words) // 2]
                ak.head(mid.start, "nodSlow", mid.text, gap=3.0)
    for c in (ex, ak):
        counts = [q for q in c.cues if q.kind == "count"]
        for a, b in zip(counts, counts[1:]):
            if b.t - a.until < 1.2:
                a.until = b.t + 0.15
    tracks = []
    for t in plan.characters:
        c = ex if t is explainer else ak
        tracks.append(t.model_copy(update={"cues": sorted(c.cues, key=lambda q: q.t)}))
    plan = plan.model_copy(update={"characters": tracks})
    return with_envelopes(plan)


# ===================================================================== voice

def envelope(samples: np.ndarray, rate: int, spans: list[tuple[float, float]], fps: int = 30) -> dict | None:
    """The loudness of the voice inside `spans` (this speaker's captions), 0..1
    at `fps`, zero outside them: fast to open, a little slower to close."""
    if not spans:
        return None
    t0, t1 = min(a for a, _ in spans), max(b for _, b in spans)
    n = int((t1 - t0) * fps) + 1
    hop = rate // fps
    out = np.zeros(n)
    for i in range(n):
        t = t0 + i / fps
        if not any(a - 0.02 <= t <= b + 0.02 for a, b in spans):
            continue
        a = int(t * rate)
        w = samples[a:a + hop]
        out[i] = float(np.sqrt(np.mean(w * w))) if len(w) else 0.0
    inside = out[out > 0]
    ref = np.percentile(inside, 95) if len(inside) else 1.0
    out = np.clip(out / max(ref, 1e-6), 0, 1)
    sm = np.zeros(n)
    for i in range(n):
        prev = sm[i - 1] if i else 0.0
        k = 0.75 if out[i] > prev else 0.35
        sm[i] = prev + (out[i] - prev) * k
    # the mouth is shut outside this speaker's lines, however the smoothing trails
    for i in range(n):
        t = t0 + i / fps
        if not any(a - 0.02 <= t <= b + 0.02 for a, b in spans):
            sm[i] = 0.0
    return {"t0": round(t0, 3), "fps": fps, "v": [round(float(v), 2) for v in sm]}


def with_envelopes(plan):
    """Each track's voice envelope from the reel's mixed narration (audio/reel.wav)."""
    from .motion_voice import _read_wav
    path = config.OUTPUT_DIR / plan.short_id / "audio" / "reel.wav"
    if not path.exists():
        return plan
    samples, rate = _read_wav(path.read_bytes())
    caps = [c for s in plan.shots for c in s.captions]
    tracks = []
    for t in plan.characters:
        spans = [(c.start, c.end) for c in caps if (c.speaker or None) == (t.role or None)]
        tracks.append(t.model_copy(update={"env": envelope(samples, rate, spans)}))
    return plan.model_copy(update={"characters": tracks})


# ===================================================================== 3D avatars

def with_vrm(plan):
    """The plan's characters drawn as 3D VRM avatars (web/src/motion/vrm):
    the explainer wears assets/avatars/mentor.vrm, the asker student.vrm."""
    tracks = [t.model_copy(update={"vrm": "student" if t.side == "left" else "mentor"}) for t in plan.characters]
    return plan.model_copy(update={"avatars": "vrm", "characters": tracks})
