"""
Animated characters for motion reels (REEL_STYLE=motion only).

An optional layer, off by default (config.MOTION_CHARACTERS, or motion_reel
--characters / --character <preset>). The rig is the characters lab's,
copied to web/src/motion/characters (SOURCE.md there); WHO the characters are
is ours, in shorts/motion_character_presets.yaml: one shared host, and one
character per course language wearing its signature colour.

Characters = speakers:

  - a two-speaker reel (interview, interview_rapid_fire, peer_discussion,
    mentor_student — any theme with two speakers): the host asks on the
    left, the reel's language character answers on the right;
  - a one-narrator reel: the language character alone, as the narrator.

The badges, the chat and the language identity are unchanged. The characters
stand in their own region (library.json frame.characters) between the scene
objects and the chat or captions, so they never cover either; on a
full-frame card, or a one-narrator shot whose objects need the whole middle
of the frame, they step out (MotionShotPlan.characters).

This module is the DIRECTOR. It reads the captions on the final clock and
writes each character's gestures and expressions, each cued on a spoken
word exactly like a scene action (`t` = that word's start, a little earlier
for a hand gesture so its wind-up lands on the word). Plain, deterministic
code: no LLM call, so it costs nothing and the same captions always give the
same performance. The mouth is not directed here: the player drives it from
the same caption words (forced-alignment timings in a real reel), so the
lips match the audio.
"""
import re
import zlib

from . import motion_character_presets as presets
from . import motion_library as lib
from .schema import MotionCaptionTiming, MotionCastMember, MotionCharacterCue, MotionCharacterTrack

_YES = {"yes", "yeah", "right", "exactly", "correct", "sure"}
_NO = {"no", "nope", "wrong"}
_ASK = {"how", "what", "which", "where", "when"}
_SMALL = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "but", "is", "are",
          "it", "its", "this", "that", "so", "if", "be", "does", "do", "you", "we", "i"}


def vocabulary() -> dict:
    return lib.library()["characters"]


def language_preset(language: str | None, override: str | None = None) -> str:
    """The preset that plays the reel's language: the override if given, else
    the language's own, else the generic CS character."""
    if override:
        presets.preset(override)          # raises on an unknown id
        return override
    ids = presets.ids()
    return language if language in ids and language != "host" else "cs"


def _seed(preset_id: str) -> int:
    return zlib.crc32(preset_id.encode()) % 997 + 1


def _plain(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def _content_word(words) -> int:
    """The first word worth landing a gesture on: past the small words."""
    for i, w in enumerate(words):
        if _plain(w.text) not in _SMALL and len(_plain(w.text)) > 2:
            return i
    return 0


class _Actor:
    """One character's cues, with the spacing rule: a new hand or head
    gesture waits min_gap seconds after the last, so gestures never pile up."""

    def __init__(self, role: str | None, preset_id: str, side: str, min_gap: float):
        self.track = MotionCharacterTrack(role=role, preset=preset_id, config=presets.preset(preset_id),
                                          side=side, seed=_seed(preset_id + side))
        self.min_gap = min_gap
        self.last_gesture = -1e9
        self.expression = ""
        self.explained = 0

    def express(self, t: float, name: str, cue: str) -> None:
        if name != self.expression:
            self.track.cues.append(MotionCharacterCue(t=round(max(0.0, t), 3), kind="expression",
                                                      name=name, cue=cue))
            self.expression = name

    def gesture(self, t: float, name: str, cue: str, force: bool = False) -> bool:
        if not force and t - self.last_gesture < self.min_gap:
            return False
        side = None
        # one-handed gestures are drawn reaching screen-right; the character
        # on the right mirrors them so they reach toward the other speaker
        if self.track.side == "right" and name in vocabulary()["mirror_on_right"]:
            side = "R"
        self.track.cues.append(MotionCharacterCue(t=round(max(0.0, t), 3), kind="gesture", name=name,
                                                  side=side, cue=cue))
        self.last_gesture = t
        return True


def _speak(me: _Actor, cap: MotionCaptionTiming, last: bool, explain: list[str]) -> None:
    """The speaker's gesture for one line: the first rule that matches."""
    v = vocabulary()
    g, ex = v["gestures"], v["expressions"]
    lead_hands, lead_head = v["lead"]["hands"], v["lead"]["head"]
    words = cap.words
    first = words[0]
    plain = [_plain(w.text) for w in words]
    question = cap.text.rstrip().endswith("?")
    if last:
        w = words[-1]
        me.gesture(w.start - lead_hands, g["end"], w.text, force=True)
        me.express(w.start, ex["end"], w.text)
        return
    for i, p in enumerate(plain):
        if p in g["count"]:
            if me.gesture(words[i].start - lead_hands, g["count"][p], words[i].text):
                return
            break
    if plain[0] in _YES and me.gesture(first.start - lead_head, g["yes"], first.text):
        return
    if plain[0] in _NO and me.gesture(first.start - lead_head, g["no"], first.text):
        return
    if question:
        kind = "why" if "why" in plain else "how" if _ASK & set(plain) else None
        if kind:
            i = _content_word(words)
            if me.gesture(words[i].start - lead_hands, g[kind], words[i].text):
                return
    hl = [i for i, w in enumerate(words) if w.hl]
    i = hl[0] if hl else (_content_word(words) if len(words) >= 7 else None)
    if i is not None:
        name = explain[me.explained % len(explain)]
        if name == "presentToward":
            name = v["present"]["left" if me.track.side == "left" else "right"]
        if me.gesture(words[i].start - lead_hands, name, words[i].text):
            me.explained += 1


def direct(cast: list[MotionCastMember], captions: list[MotionCaptionTiming], language: str | None,
           override: str | None = None) -> list[MotionCharacterTrack]:
    """Two characters for a two-speaker reel: the host (left, asking) and the
    language character (right, answering)."""
    v = vocabulary()
    if len(cast) != 2:
        return []
    ex = v["expressions"]
    lang = language_preset(language, override)
    actors = {m.role: _Actor(m.role, "host" if m.side == "left" else lang, m.side, v["min_gap"]) for m in cast}
    asking = next((m.role for m in cast if m.side == "left"), cast[0].role)
    spoken = [c for c in captions if c.speaker in actors and c.words]
    for a in actors.values():
        a.express(0.0, ex["listening"], "")

    for n, cap in enumerate(spoken):
        me = actors[cap.speaker]
        other = next(a for r, a in actors.items() if r != cap.speaker)
        first = cap.words[0]
        question = cap.text.rstrip().endswith("?")
        last = n == len(spoken) - 1
        face = ex["question"] if question and cap.speaker == asking else (
            ex["asking"] if cap.speaker == asking else ex["speaking"])
        me.express(first.start - 0.1, face, first.text)
        other.express(first.start, ex["thinking"] if question else ex["listening"], first.text)
        _speak(me, cap, last, v["gestures"]["explain"])
        # the listener agrees at the end of a statement, now and then
        if not question and not last and n % 2 == 1:
            w = cap.words[-1]
            other.gesture(w.start - v["lead"]["head"], v["gestures"]["agree"], w.text)
    for a in actors.values():
        a.track.cues.sort(key=lambda c: c.t)
    return [a.track for a in sorted(actors.values(), key=lambda a: a.track.side != "left")]


def direct_narrator(captions: list[MotionCaptionTiming], language: str | None,
                    override: str | None = None) -> list[MotionCharacterTrack]:
    """One character for a one-narrator reel: the language character, centre."""
    v = vocabulary()
    ex = v["expressions"]
    me = _Actor(None, language_preset(language, override), "center", v["min_gap"])
    spoken = [c for c in captions if c.words]
    me.express(0.0, ex["speaking"], "")
    for n, cap in enumerate(spoken):
        first = cap.words[0]
        question = cap.text.rstrip().endswith("?")
        me.express(first.start - 0.1, ex["question"] if question else ex["speaking"], first.text)
        _speak(me, cap, n == len(spoken) - 1, v["narrator_explain"])
    me.track.cues.sort(key=lambda c: c.t)
    return [me.track]
