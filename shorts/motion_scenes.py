"""
Motion SCENES (RESTYLE_TO_MOTION_REELS.md phase 3). REEL_STYLE=motion only.

A scene says what one shot SHOWS: its field colour, the transition into it,
its objects (kinds from web/src/motion/library.json, the phase 2 library)
and its timeline actions, each CUED ON A SPOKEN WORD of the shot's captions
(addendum 4.6 D: label, then object, then state change, then result, each
tied to the word that names it).

This module is everything about a scene that is a fixed rule:
  - scene_problems: is a scene drawable (kinds, props, lengths, targets,
    actions, cues, transitions, does it fit its region);
  - resolve_cues / resolve_actions: a cue -> a word -> seconds;
  - layout_scene: where every object goes (the player never decides);
  - change_events: every visible change, for the 2.5 s cadence rule;
  - default_scenes: a deterministic beat -> scene mapping for ANY script,
    built only from the script's own words (captions, highlights, code,
    icons, chapters). It is the stub answer for SYSTEM_MOTION_SCENES and the
    baseline any LLM scene is compared with. Nothing in it names a topic.
"""
import math
import re

from . import motion_library as lib
from .schema import (MotionBox, MotionPlacedObject, MotionScene, MotionSceneAction,
                     MotionSceneObject, MotionScript, MotionShot, motion_plain_text)

#: The 2.5 s rule (addendum 4.6 D): a visible change at least this often.
#: Karaoke caption progress does not count.
MAX_STILL_SECONDS = 2.5
#: Placed objects per shot — more than this is a slide, not a scene.
MAX_PLACED = 4
#: Field transitions rotate and never repeat back to back (addendum 4.6 A);
#: this is the order, mirroring transitions.tsx's ROTATION.
ROTATION = ("iris", "bar_wipe", "double_bar_wipe", "diagonal_stripes", "stack_rise")

#: Colour meanings (tokens.ts): coral = failure, mint = success. Which beats
#: are which. A beat in neither set may use neither colour.
FAILURE_BEATS = frozenset({"hook", "setup", "break_1", "break_2", "chapter", "example"})
SUCCESS_BEATS = frozenset({"fix_idea", "fix_flow", "code_map", "payoff", "recap",
                           "chapter", "result", "takeaway"})


# ===================================================================== words

def _key(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (word or "").lower())


def shot_words(shot: MotionShot) -> list[str]:
    """The shot's caption words, in order, as cue keys — one per shown word,
    so an index here is an index into the timing's words too. A word with no
    letters or digits ("—") has the empty key, which no cue matches."""
    from .motion_timeline import caption_words
    return [_key(w) for c in shot.captions for w, _ in caption_words(c.text)]


def resolve_cues(shot: MotionShot, scene: MotionScene | None = None) -> list[int | None]:
    """Each action's cue as an index into shot_words (-1 for "start"), or
    None when the cue is not found. Cues resolve IN ORDER: each search starts
    after the previous action's cue, so a repeated word means its next
    occurrence and the build-up order is the speaking order. An action with
    exactly the previous action's cue happens WITH it (same word)."""
    scene = scene or shot.scene
    words = shot_words(shot)
    out: list[int | None] = []
    pos = 0
    prev_cue: str | None = None
    for a in scene.actions:
        if a.at.strip().lower() == "start":
            out.append(-1)
            continue
        # a cue copied with the caption's markup ("<b>remember</b>") is the
        # same words: drop the tags before matching
        cue = [_key(w) for w in re.sub(r"</?b>", " ", a.at).split() if _key(w)]
        if prev_cue is not None and cue and cue == prev_cue and out and out[-1] is not None:
            out.append(out[-1])
            continue
        prev_cue = cue
        found = None
        if cue:
            for i in range(pos, len(words) - len(cue) + 1):
                if words[i:i + len(cue)] == cue:
                    found = i
                    break
        out.append(found)
        if found is not None:
            pos = found + 1
    return out


def resolve_actions(shot: MotionShot, clock) -> list[tuple[MotionSceneAction, float]]:
    """Every action with its time on the reel's clock: "start" is the shot's
    start, a word cue is that word's start. An unresolved cue (which a valid
    scene never has) falls back to the shot's start rather than vanishing."""
    words = clock.words()
    out = []
    for a, idx in zip(shot.scene.actions, resolve_cues(shot)):
        if idx is None or idx < 0 or idx >= len(words):
            out.append((a, clock.start))
        else:
            out.append((a, words[idx].start))
    return out


# ==================================================================== layout

def kinetic_lines(text: str) -> list[str]:
    """kinetic_title's lines: greedy word wrap at the library's
    chars_per_line. The player draws exactly these lines."""
    k = lib.library()["kinetic"]
    lines: list[str] = []
    for w in text.split():
        if lines and len(lines[-1]) + 1 + len(w) <= k["chars_per_line"]:
            lines[-1] += " " + w
        else:
            lines.append(w)
    return lines


def object_height(obj: MotionSceneObject) -> float:
    """An object's height in design units — from the library, or computed
    from its content for the kinds whose size depends on it."""
    spec = lib.object_kinds()[obj.kind]
    if "height" in spec:
        return float(spec["height"])
    if obj.kind == "kinetic_title":
        k = lib.library()["kinetic"]
        return len(kinetic_lines(str(obj.props.get("text", "")))) * k["size"] * k["line_height"]
    if obj.kind == "code_window":
        return 174.0 + 120.0 * len(obj.props.get("lines") or [])
    if obj.kind == "lookup_table":
        return 78.0 * (len(obj.props.get("rows") or []) + 1) + 24
    return 0.0


def _region(duo: bool) -> tuple[float, float]:
    f = lib.library()["frame"]
    r = f["duo" if duo else "solo"]
    return float(r["top"]), float(r["bottom"])


def stack_height(scene: MotionScene) -> float:
    """The placed objects' stacked height, gaps included (a connector between
    two neighbours needs the wider gap it is drawn in)."""
    f = lib.library()["frame"]
    placed = [o for o in scene.objects if lib.object_kinds()[o.kind]["layout"] == "placed"]
    links = {(str(o.props.get("from")), str(o.props.get("to"))) for o in scene.objects
             if o.kind == "connector"}
    total = sum(object_height(o) for o in placed)
    for a, b in zip(placed, placed[1:]):
        linked = (a.id, b.id) in links or (b.id, a.id) in links
        total += f["connector_gap"] if linked else f["gap"]
    return total


def layout_scene(scene: MotionScene, duo: bool) -> list[MotionPlacedObject]:
    """Where everything goes. Placed objects stack top to bottom in the
    region (solo: the middle of the frame; duo: above the chat),
    centred vertically, each content_w wide. A connector's points run from
    one object's bottom edge to the next one's top edge. A stamp sits on the
    region's centre. Full-frame objects draw themselves."""
    f = lib.library()["frame"]
    top, bottom = _region(duo)
    x = (f["w"] - f["content_w"]) / 2
    kinds = lib.object_kinds()
    placed = [o for o in scene.objects if kinds[o.kind]["layout"] == "placed"]
    links = {(str(o.props.get("from")), str(o.props.get("to"))) for o in scene.objects
             if o.kind == "connector"}
    y = top + max(0.0, (bottom - top - stack_height(scene)) / 2)
    boxes: dict[str, MotionBox] = {}
    for i, o in enumerate(placed):
        if i:
            prev = placed[i - 1]
            linked = (prev.id, o.id) in links or (o.id, prev.id) in links
            y += f["connector_gap"] if linked else f["gap"]
        h = object_height(o)
        boxes[o.id] = MotionBox(x=x, y=round(y, 1), w=f["content_w"], h=round(h, 1))
        y += h
    out: list[MotionPlacedObject] = []
    for o in scene.objects:
        props = dict(o.props)
        layout = kinds[o.kind]["layout"]
        box = boxes.get(o.id)
        if o.kind == "kinetic_title":
            props["lines"] = kinetic_lines(str(o.props.get("text", "")))
        if layout == "overlay":
            # a stamp marks the first object: in its right half, low, where an
            # entity card and a code window carry no text (its label is top
            # left, its value bottom left) — never on the region's centre,
            # where it covered the card's own words
            first = boxes.get(placed[0].id) if placed else None
            box = (MotionBox(x=round(first.x + first.w * 0.72, 1), y=round(first.y + first.h * 0.5, 1),
                             w=0, h=0) if first is not None
                   else MotionBox(x=f["w"] / 2, y=round((top + bottom) / 2, 1), w=0, h=0))
        if layout == "link":
            a, b = boxes.get(str(o.props.get("from"))), boxes.get(str(o.props.get("to")))
            if a and b:
                upper, lower = (a, b) if a.y <= b.y else (b, a)
                cx = f["w"] / 2
                props["points"] = [[cx, round(upper.y + upper.h + 10, 1)],
                                   [cx, round(lower.y - 10, 1)]]
        out.append(MotionPlacedObject(id=o.id, kind=o.kind, props=props, box=box))
    return out


# ================================================================ validation

def _type_ok(value, kind: str) -> bool:
    if kind == "str":
        return isinstance(value, str) and bool(value.strip())
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "tone":
        return value in lib.tones()
    if kind == "icon":
        return value in lib.icon_names()
    if kind == "str[]":
        return isinstance(value, list) and bool(value) and all(isinstance(v, str) for v in value)
    if kind == "tone[]":
        return isinstance(value, list) and all(v in lib.tones() for v in value)
    if kind == "rows":        # takeaway rows
        return isinstance(value, list) and bool(value) and all(
            isinstance(r, dict) and r.get("icon") in lib.icon_names() and r.get("line") for r in value)
    if kind == "icons":
        return isinstance(value, list) and bool(value) and all(
            isinstance(r, dict) and r.get("name") in lib.icon_names() for r in value)
    if kind == "parts":       # code_map parts
        return isinstance(value, list) and bool(value) and all(
            isinstance(r, dict) and r.get("code") and r.get("icon") in lib.icon_names()
            and r.get("label") for r in value)
    if kind == "table":
        return isinstance(value, list) and bool(value) and all(
            isinstance(r, list) and len(r) == 2 for r in value)
    return False


def object_problems(obj: MotionSceneObject) -> list[str]:
    kinds = lib.object_kinds()
    spec = kinds.get(obj.kind)
    if spec is None:
        return [f"{obj.id}: kind {obj.kind!r} is not in the scene library ({', '.join(kinds)})"]
    problems: list[str] = []
    for name, kind in spec["props"].items():
        optional = kind.endswith("?")
        kind = kind.rstrip("?")
        if name not in obj.props or obj.props[name] in (None, "", []):
            if not optional:
                problems.append(f"{obj.id} ({obj.kind}) needs {name!r}")
            continue
        if not _type_ok(obj.props[name], kind):
            problems.append(f"{obj.id} ({obj.kind}) {name}={obj.props[name]!r} is not a valid {kind}")
            continue
        cap = spec.get("max", {}).get(name)
        val = obj.props[name]
        length = (len(" ".join(str(v.get("label", "")) if isinstance(v, dict) else str(v) for v in val))
                  if isinstance(val, list) else len(str(val)))
        if cap and length > cap:
            problems.append(f"{obj.id} ({obj.kind}) {name} is {length} characters, max {cap} "
                            f"(it would not fit its box)")
    stray = sorted(set(obj.props) - set(spec["props"]))
    if stray:
        problems.append(f"{obj.id} ({obj.kind}) has unknown prop(s) {stray}")
    if obj.kind == "kinetic_title" and "text" in obj.props:
        lines = kinetic_lines(str(obj.props["text"]))
        k = lib.library()["kinetic"]
        if len(lines) > k["max_lines"] or any(len(l) > k["chars_per_line"] + 3 for l in lines):
            problems.append(f"{obj.id} (kinetic_title) wraps to {len(lines)} line(s), max "
                            f"{k['max_lines']} of about {k['chars_per_line']} characters")
    if obj.kind == "code_window" and obj.props.get("lines"):
        if len(obj.props["lines"]) > 3 or any(len(l) > 30 for l in obj.props["lines"]):
            problems.append(f"{obj.id} (code_window) shows more than 3 lines of 30 characters")
    return problems


def scene_problems(shot: MotionShot, scene: MotionScene | None = None, duo: bool = False) -> list[str]:
    """Why a shot's scene cannot be drawn as given. Empty when it can."""
    scene = scene if scene is not None else shot.scene
    if scene is None:
        return [f"{shot.id} has no scene"]
    p: list[str] = []
    kinds = lib.object_kinds()
    if scene.transition not in lib.transitions():
        p.append(f"transition {scene.transition!r} is not one of {lib.transitions()}")
    ids = [o.id for o in scene.objects]
    if not scene.objects:
        p.append("no objects — every shot shows something")
    if len(set(ids)) != len(ids):
        p.append(f"object ids repeat: {ids}")
    for o in scene.objects:
        p += object_problems(o)
    known = [o for o in scene.objects if o.kind in kinds]
    full = [o for o in known if kinds[o.kind]["layout"] == "full"]
    placed = [o for o in known if kinds[o.kind]["layout"] == "placed"]
    if len(full) > 1 or (full and placed):
        p.append("a full-frame object (title_card, end_card, takeaway_list, recap_grid, "
                 "chapter_card, code_map) is the whole shot — nothing else is placed beside it")
    if len(placed) > MAX_PLACED:
        p.append(f"{len(placed)} placed objects, max {MAX_PLACED}")
    for o in known:
        if o.kind == "connector":
            ends = [str(o.props.get("from")), str(o.props.get("to"))]
            bad = [e for e in ends if e not in [q.id for q in placed]]
            if bad:
                p.append(f"{o.id} (connector) joins {bad}, which are not placed objects in this shot")
            elif abs([q.id for q in placed].index(ends[0]) - [q.id for q in placed].index(ends[1])) != 1:
                p.append(f"{o.id} (connector) joins {ends}, which are not next to each other")
    top, bottom = _region(duo)
    if placed and stack_height(scene) > bottom - top:
        p.append(f"the placed objects stack to {stack_height(scene):.0f} units, the "
                 f"{'duo' if duo else 'solo'} region is {bottom - top:.0f} — they do not fit")
    by_id = {o.id: o for o in known}
    for i, a in enumerate(scene.actions):
        if a.do not in lib.action_kinds():
            p.append(f"action {i + 1} {a.do!r} is not one of {sorted(lib.action_kinds())}")
            continue
        o = by_id.get(a.target)
        if o is None:
            p.append(f"action {i + 1} ({a.do}) targets {a.target!r}, which is not an object here")
            continue
        if a.do not in kinds[o.kind]["actions"]:
            p.append(f"action {i + 1}: {o.kind} cannot {a.do!r} (it can {kinds[o.kind]['actions']})")
        if a.tone is not None and a.tone not in lib.tones():
            p.append(f"action {i + 1} tone {a.tone!r} is not one of {lib.tones()}")
    for a, idx in zip(scene.actions, resolve_cues(shot, scene)):
        if idx is None:
            p.append(f"cue {a.at!r} ({a.do} {a.target}) is not a word of this shot's captions, "
                     f"in order after the previous cue")
    return p


# =================================================================== timing

def change_events(shot: MotionShot, clock) -> list[float]:
    """Every moment the frame visibly changes in this shot: its start (the
    transition or cut), each action, and each full-frame card's own built-in
    entrance steps. Karaoke caption progress is NOT a change (decision
    2026-10-01)."""
    kinds = lib.object_kinds()
    times = [clock.start]
    entered: dict[str, float] = {}
    for a, t in resolve_actions(shot, clock):
        times.append(t)
        if a.do in ("enter", "stamp"):
            entered.setdefault(a.target, t)
    for o in shot.scene.objects:
        spec = kinds.get(o.kind, {})
        t0 = entered.get(o.id, clock.start)
        times += [t0 + b for b in spec.get("builtin", [])]
    return sorted(t for t in times if clock.start <= t <= clock.end)


def longest_still(shot: MotionShot, clock) -> tuple[float, float]:
    """The longest stretch with no visible change, and when it starts."""
    ev = change_events(shot, clock) + [clock.end]
    gaps = [(b - a, a) for a, b in zip(ev, ev[1:])]
    return max(gaps) if gaps else (clock.end - clock.start, clock.start)


# ================================================================= defaults

def _highlights(shot: MotionShot) -> list[str]:
    """The shot's <b> highlights in order — the words the script itself
    marked as the ones that matter."""
    out: list[str] = []
    for c in shot.captions:
        out += [re.sub(r"\s+", " ", h).strip(" .,!?") for h in re.findall(r"<b>(.*?)</b>", c.text)]
    return [h for h in out if h]


def _fit(text: str, cap: int) -> str:
    """`text` cut at a word boundary to at most `cap` characters."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= cap:
        return text
    cut = text[:cap + 1].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") or text[:cap]


def _kinetic(text: str, cap: int = 54) -> str:
    """`text` cut (at a word) until it wraps to kinetic_title's line limit."""
    text = _fit(text, cap)
    k = lib.library()["kinetic"]
    while len(kinetic_lines(text)) > k["max_lines"] and " " in text:
        text = text.rsplit(" ", 1)[0].rstrip(" ,;:-")
    return text


# Kinetic titles keep the writer's case ("useState"): the player sets the case
# per design — classic draws them in caps, Midnight Lab in sentence case.
def _whole_title(shot: MotionShot, script) -> str:
    """The hook's kinetic title: the hook's own question sentence, the reel's
    question, or its first sentence — the first that fits the title's lines
    WHOLE. A hook cut mid-phrase ("…STAYS STUCK AT") reads as a mistake, and a
    lead-in ("SAME CLICK.") says nothing; the question is the hook. Cut only
    if none fits."""
    k = lib.library()["kinetic"]
    questions = [motion_plain_text(c.text) for c in shot.captions if motion_plain_text(c.text).rstrip().endswith("?")]
    for text in (*questions, script.hook_question, _first_sentence(shot)):
        t = (text or "").strip()
        if t and len(kinetic_lines(t)) <= k["max_lines"] and len(t) <= 54:
            return t
    return _kinetic(_first_sentence(shot))


def _first_sentence(shot: MotionShot) -> str:
    return motion_plain_text(shot.captions[0].text) if shot.captions else shot.speech


def _cue_for(phrase: str) -> str:
    """A cue for a highlight: its first word (a cue is 1-3 words)."""
    words = [w for w in phrase.split() if _key(w)]
    return " ".join(words[:3]) if words else "start"


class _Builder:
    def __init__(self, shot: MotionShot):
        self.shot = shot
        self.objects: list[MotionSceneObject] = []
        self.actions: list[MotionSceneAction] = []
        self._cue_pos = 0
        self._words = shot_words(shot)

    def add(self, kind: str, **props) -> str:
        oid = f"o{len(self.objects) + 1}"
        self.objects.append(MotionSceneObject(id=oid, kind=kind,
                                              props={k: v for k, v in props.items() if v not in (None, "", [])}))
        return oid

    def cue(self, phrase: str | None) -> str:
        """`phrase` as a cue if it is still ahead of the last cue (or is the
        last cue itself: then it happens with it), else start."""
        if not phrase or phrase == "start":
            return "start"
        key = [_key(w) for w in phrase.split() if _key(w)][:3]
        last = next((a for a in reversed(self.actions) if a.at != "start"), None)
        if last is not None and [_key(w) for w in last.at.split() if _key(w)] == key:
            return last.at
        for i in range(self._cue_pos, len(self._words) - len(key) + 1):
            if self._words[i:i + len(key)] == key:
                self._cue_pos = i + 1
                return " ".join(phrase.split()[:3])
        return "start" if not self.actions else ""

    def act(self, do: str, target: str, at: str | None = "start", **kw):
        cue = self.cue(at) if at != "start" else "start"
        if cue == "":
            return
        self.actions.append(MotionSceneAction(at=cue, do=do, target=target, **kw))


#: Symptom words too vague to name a failure on their own ("Same click" is
#: not what goes wrong).
_WEAK_SYMPTOMS = {"same", "old", "back", "nothing"}


def _symptom(shot: MotionShot) -> str:
    """A short phrase naming what goes wrong: a highlight that names the
    symptom ("stuck at zero"), else the words around the first strong symptom
    word INSIDE one sentence (never across "." or "?"), else the last
    highlight, else the first four words."""
    from .checks import MOTION_SYMPTOM_WORDS
    hl = _highlights(shot)

    def symptomatic(w: str) -> bool:
        return (_key(w) in MOTION_SYMPTOM_WORDS and _key(w) not in _WEAK_SYMPTOMS) or bool(re.search(r"\d", w))

    for h in hl:
        if any(symptomatic(w) for w in h.split()):
            return _fit(h[:1].upper() + h[1:], 26)
    small = {"at", "to", "in", "on", "of", "the", "a", "an", "and", "back"}
    for sentence in re.split(r"(?<=[.!?])\s+", motion_plain_text(" ".join(c.text for c in shot.captions))):
        words = sentence.split()
        for i, w in enumerate(words):
            if symptomatic(w):
                j = min(len(words), i + 3)
                # never end on a little word: "stuck at" -> "stuck at zero"
                while j < len(words) and j - i < 5 and _key(words[j - 1]) in small:
                    j += 1
                phrase = " ".join(words[i:j]).strip(" .,!?")
                return _fit(phrase[:1].upper() + phrase[1:], 26)
    if hl:
        return _fit(hl[-1][:1].upper() + hl[-1][1:], 26)
    words = motion_plain_text(" ".join(c.text for c in shot.captions)).split()
    return _fit(" ".join(words[:4]).strip(" .,!?"), 26)


def _rotation_after(prev: str | None, used: list[str]) -> str:
    start = (ROTATION.index(prev) + 1) if prev in ROTATION else len(used) % len(ROTATION)
    return ROTATION[start % len(ROTATION)]


#: Words too small to hang an action on — a cue should be a word someone hears.
_WEAK_CUES = frozenset("a an the and or but so to of in on at it its is are was be by for with "
                       "as that this then than your you".split())


def _fill_cadence(b: _Builder, shot: MotionShot, primary: str, nudge: str, script) -> None:
    """Add small actions wherever the estimated timing would leave the frame
    still for more than about 2 s — each cued on a content word spoken at
    that moment, so it still moves WITH the narration. The action goes to an
    object that is already on screen by then: chips and rows light up, a
    chip or connector pulses, and only failing those does a title re-scramble."""
    from .motion_timeline import shot_timings
    if not b.objects:
        return
    kinds = lib.object_kinds()

    def nudge_of(o: MotionSceneObject) -> str | None:
        acts = kinds[o.kind]["actions"]
        if "highlight" in acts and _highlight_count(b, o.id):
            return "highlight"
        if "pulse" in acts and o.kind != "connector":
            return "pulse"
        return "scramble" if "scramble" in acts else None

    ranked = sorted(b.objects, key=lambda o: (nudge_of(o) in (None, "scramble"), o.id != primary))

    def clock_for(actions):
        probe = shot.model_copy(update={"scene": MotionScene(objects=b.objects, actions=actions)})
        return probe, shot_timings(script.model_copy(update={"shots": [probe]}))[0]

    # Nothing on screen for the first ~2 s: the first object enters at the
    # start instead, and the word that named it becomes its reveal.
    probe, clock = clock_for(b.actions)
    timed = resolve_actions(probe, clock)
    enters = [(t, j) for j, (a, t) in enumerate(timed) if a.do in ("enter", "stamp")]
    if enters:
        t0, j = min(enters)
        if t0 - clock.start > MAX_STILL_SECONDS - 0.4:
            first = b.actions[j]
            obj = next(o for o in b.objects if o.id == first.target)
            b.actions[j] = first.model_copy(update={"at": "start"})
            reveal = nudge_of(obj)
            if reveal:
                value = "1" if reveal == "highlight" else None
                b.actions.insert(j + 1, MotionSceneAction(at=first.at, do=reveal, target=obj.id,
                                                          value=value))
                if None in resolve_cues(shot, MotionScene(objects=b.objects, actions=b.actions)):
                    del b.actions[j + 1]

    last_gap = None
    for _ in range(16):
        probe, clock = clock_for(b.actions)
        scene = probe.scene
        gap, at = longest_still(probe, clock)
        if gap <= MAX_STILL_SECONDS - 0.4:
            return
        if last_gap is not None and gap >= last_gap[0] and at == last_gap[1]:
            del b.actions[last_gap[2]]
            return                       # the last insertion did not help
        last_gap = None
        words = clock.words()
        keys = shot_words(shot)
        order = resolve_cues(probe, scene)
        target_t = at + min(2.0, gap / 2)
        entered = {}
        for act, k in zip(b.actions, order):
            if act.do in ("enter", "stamp") and k is not None:
                entered.setdefault(act.target, k)
        placed = False
        content = [i for i, w in enumerate(words) if w.start > at + 0.6 and w.start < at + gap - 0.4
                   and len(keys[i]) >= 3 and keys[i] not in _WEAK_CUES]
        for idx in sorted(content, key=lambda i: abs(words[i].start - target_t))[:5]:
            target = next((o for o in ranked if nudge_of(o)
                           and entered.get(o.id, -1 if not any(x.target == o.id and x.do == "enter"
                                                               for x in b.actions) else 10 ** 6) < idx),
                          None)
            if target is None:
                continue
            do = nudge_of(target)
            pos = next((j for j, k in enumerate(order) if k is not None and k > idx), len(order))
            value = None
            if do == "highlight":
                n = sum(1 for x in b.actions[:pos] if x.do == "highlight" and x.target == target.id)
                value = str(n % _highlight_count(b, target.id) + 1)
            for n in (1, 2, 3):
                cue = " ".join(re.sub(r"[^\w'-]", "", words[j].text)
                               for j in range(idx, min(idx + n, len(words)))).strip()
                trial = b.actions[:pos] + [MotionSceneAction(at=cue, do=do, target=target.id,
                                                             value=value)] + b.actions[pos:]
                got = resolve_cues(shot, MotionScene(objects=b.objects, actions=trial))
                if got[pos] == idx and None not in got:
                    b.actions = trial
                    last_gap = (gap, at, pos)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            return


def _highlight_count(b: _Builder, oid: str) -> int:
    o = next(o for o in b.objects if o.id == oid)
    p = o.props
    if o.kind == "code_window":
        return len(p.get("lines") or [])
    if o.kind == "token_row":
        return len(p.get("items") or [])
    if o.kind == "title_card":
        return len(p.get("icons") or [])
    if o.kind == "kinetic_title":
        return len(str(p.get("text", "")).split())
    if o.kind in ("takeaway_list",):
        return len(p.get("rows") or [])
    if o.kind == "recap_grid":
        return len(p.get("steps") or [])
    if o.kind == "code_map":
        return len(p.get("parts") or [])
    if o.kind == "icon_row":
        return len(p.get("icons") or [])
    if o.kind in ("flow", "cycle"):
        return len(p.get("steps") or [])
    if o.kind == "lookup_table":
        return len(p.get("rows") or [])
    return 0


def _nudge_for(kind: str) -> str:
    acts = lib.object_kinds()[kind]["actions"]
    for a in ("highlight", "pulse", "scramble", "state"):
        if a in acts:
            return a
    return "enter"


def _chips(items: list[str], cap: int = 44) -> list[str]:
    """As many items as fit one chip row."""
    out: list[str] = []
    for it in items:
        it = _fit(it, 14)
        if len(" ".join(out + [it])) > cap:
            break
        out.append(it)
    return out


#: A walkthrough's chapter fields, in order (addendum 4.1: navy, then blue,
#: then paper, then yellow, then paper — navy is the hook's).
CHAPTER_FIELDS = ("blue", "paper", "yellow", "paper")

def _code_file(language: str | None) -> str:
    """The code window's tab: a real file name for the reel's language
    (shorts/motion_identities.yaml), never the concept's name."""
    from .motion_identities import languages, identity
    return identity(language).file if language in languages() else ""


#: Words that mean the material is about something a user sees and does on a
#: screen — then the hook acts it out on an app screen.
_UI_WORDS = frozenset("click clicks clicked clicking tap taps tapped button buttons screen screens "
                      "form forms cart counter browser app apps webpage".split())


def _is_ui(script: MotionScript) -> bool:
    text = " ".join(s.speech for s in script.shots).lower()
    return len(set(re.findall(r"[a-z]+", text)) & _UI_WORDS) >= 2


def _number(shot: MotionShot, nth: int = 0) -> str | None:
    """The nth number the shot says, as digits."""
    found = re.findall(r"\b\d+\b", motion_plain_text(" ".join(c.text for c in shot.captions)))
    return found[nth] if len(found) > nth else None


def _last_word(items: list[str]) -> str:
    return items[-1].split()[-1] if items and items[-1].split() else ""


def _later_word(shot: MotionShot, skip: int) -> str:
    """A content word about `skip` words in: an action on it lands while the
    narrator is talking about the picture, not at the very start."""
    spoken = motion_plain_text(" ".join(c.text for c in shot.captions)).split()
    for w in spoken[skip:]:
        k = _key(w)
        if len(k) >= 3 and k not in _WEAK_CUES:
            return re.sub(r"[^\w'-]", "", w)
    return "start"


def _steps(script: MotionScript, shot: MotionShot, vocab_first: bool = False) -> list[dict]:
    """2-4 steps {name: icon, label} for a flow or cycle: what THIS shot says
    (its highlights, else its own content words, with the reel's icons), or —
    `vocab_first`, for the title — the reel's icon vocabulary (the concept's
    parts), else its chapters."""
    names = sorted(lib.icon_names())
    vocab = [i for i in script.icon_vocabulary if i.name in names]
    icons = [i.name for i in vocab] or ["cursor", "bolt", "check"]
    hl = [h for h in _highlights(shot) if len(h) <= 12]
    if not vocab_first:
        # what this shot says: its highlights, topped up with its best words
        said = [w[:1].upper() + w[1:] for w in _said_words(shot, script)
                if _key(w) not in {_key(x) for h in hl for x in h.split()}]
        picked = (hl + said)[:3]
        if len(picked) >= 2:
            return [{"name": icons[k % len(icons)], "label": _fit(h, 12)} for k, h in enumerate(picked)]
    out = [{"name": i.name, "label": _fit(i.label, 12)} for i in vocab[:4]]
    if len(out) < 2 and script.chapters:
        icons = ["file", "layers", "search", "check"]
        out = [{"name": icons[k % 4], "label": _fit(c.title, 12)} for k, c in enumerate(script.chapters[:4])]
    if len(out) < 2:
        hl = _highlights(shot) or [script.concept_name or "Start", "Result"]
        out = [{"name": ["cursor", "bolt", "check"][k % 3], "label": _fit(h, 12)} for k, h in enumerate(hl[:3])]
    while len(out) < 2:
        out.append({"name": "check", "label": "Done"})
    return out[:4]


def _memory(b: "_Builder", shot: MotionShot, script: MotionScript, name: str, tone: str | None = None) -> str:
    # the box is named with a word the shot says: its highlight, else its
    # first content word (the concept's name may not be said here)
    if _key(name) not in "".join(shot_words(shot)):
        said = [re.sub(r"[^\w'-]", "", w) for w in motion_plain_text(" ".join(c.text for c in shot.captions)).split()]
        name = next((w for w in said if len(w) >= 4 and _key(w) not in _WEAK_CUES), name)
    return b.add("memory_box", name=_fit(name, 16), value=_number(shot) or "?", tone=tone)


#: Words that never make a good label on their own.
_NOT_LABELS = frozenset("worse never always every ever really just only plain still again back "
                        "first last next then same other more most much many very also even each "
                        "starts start fresh wondered stays stuck climbing changing changed keeps "
                        "why what how when where who which does do did doesn't don't stay can will "
                        "would should could have has had make makes your you here there now "
                        "works work worked moment act acts thing things way".split())


def _code_names(script: MotionScript) -> list[str]:
    """Names in the reel's code: likes, setLikes, useState."""
    out: list[str] = []
    for sh in script.shots:
        for line in sh.code or []:
            for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", line):
                if w not in out and w not in {"let", "const", "var", "function", "return", "new", "import",
                                              "from", "def", "class", "true", "false", "null", "this"}:
                    out.append(w)
    return out


def _said_words(shot: MotionShot, script: MotionScript | None = None) -> list[str]:
    """The shot's own words that make good labels, best first: names from the
    reel's code, technical terms, highlights' words — never adjectives,
    adverbs or -ing words ("Worse", "never", "changing" made nonsense labels)."""
    from .checks import motion_terms
    code = {c.lower() for c in (_code_names(script) if script else [])}
    terms = {w for t in motion_terms().values() for w in t.get("words", [])}
    hl = {w.lower() for h in _highlights(shot) for w in h.split()}
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for i, w in enumerate(motion_plain_text(" ".join(c.text for c in shot.captions)).split()):
        k = re.sub(r"[^\w'-]", "", w)
        low = k.lower()
        if len(k) < 3 or low in seen or _key(k) in _WEAK_CUES or low in _NOT_LABELS:
            continue
        if low.endswith(("ing", "ly")) or (low.endswith("ed") and low not in code):
            continue
        seen.add(low)
        score = 3 if low in code else 2 if low in terms or low in hl else 1
        scored.append((-score, i, k))
    return [k for _, _, k in sorted(scored)]


def _act_somewhere(b: "_Builder", do: str, target: str, cues: list[str], **kw) -> None:
    """The action on the first of `cues` that is still ahead, else at the start
    — it must happen (the hook's failure, the payoff's success)."""
    for c in cues:
        if c and c != "start":
            n = len(b.actions)
            b.act(do, target, c, **kw)
            if len(b.actions) > n:
                return
    b.actions.append(MotionSceneAction(at="start", do=do, target=target, **kw))


def _ui_names(script: MotionScript, shot: MotionShot) -> tuple[str, str]:
    """An app screen's button and the name of the number it shows, from what
    the reel says: "the like button" -> Like; the value is the variable in its
    code (likes), else the noun next to "count"/"counter", else the button's."""
    speech = " ".join(s.speech for s in script.shots)
    m = re.search(r"\b(\w+)\s+button", speech, re.I)
    button = (m.group(1) if m and m.group(1).lower() not in {"the", "a", "this", "that", "your", "one"} else
              next((w for w in ("Click", "Tap", "Press", "Add", "Submit") if w.lower() in speech.lower()), "Tap"))
    code = _code_names(script)
    var = next((c for c in code if not c.startswith(("set", "use", "on", "handle")) and c.islower()), None)
    m2 = re.search(r"\b(\w+)\s+(?:count|counter)\b", speech, re.I)
    name = var or (m2.group(1) if m2 else None) or button
    # the screen shows something this shot says: else its value is named
    # with the shot's best word
    said_here = set(shot_words(shot))
    if _key(button) not in said_here and _key(name) not in said_here:
        best = _said_words(shot, script) or [
            re.sub(r"[^\w'-]", "", w) for w in motion_plain_text(" ".join(c.text for c in shot.captions)).split()
            if len(re.sub(r"[^\w'-]", "", w)) >= 4 and _key(w) not in _WEAK_CUES]
        if best:
            name = best[0]
    return button[:1].upper() + button[1:], name[:1].upper() + name[1:]


def _wrong_idea(script: MotionScript, shot: MotionShot) -> str:
    """What the reel shows going wrong, by name: the first highlight of the
    setup or break shots that is not the concept itself (plain variable)."""
    concept = _key(script.concept_name or "")
    for sh in script.shots:
        if sh.beat in ("setup", "break_1", "break_2"):
            for h in _highlights(sh):
                if _key(h) != concept and len(h) <= 18 and not re.search(r"\d", h):
                    return h[:1].upper() + h[1:]
    return _symptom(shot) or "Before"


def _demo(b: "_Builder", shot: MotionShot, script: MotionScript, ui: bool, ok: bool) -> str:
    """The hook's picture (ok=False: it fails) and the payoff's (ok=True: the
    same picture, working). A UI topic is an app screen whose button is
    tapped; anything else is a memory box whose value is set. Its words are
    words the shot says."""
    said = _said_words(shot, script)
    symptom = _symptom(shot)
    when = [_cue_for(symptom) if symptom and not ok else "", _later_word(shot, 6), _later_word(shot, 4)]
    if ui:
        button, value_name = _ui_names(script, shot)
        o = b.add("app_screen", title="App", button=_fit(button, 16), label=_fit(value_name, 16),
                  value=_number(shot) or "0", tone=None if ok else "bad")
        b.act("enter", o)
        b.act("tap", o, _later_word(shot, 3))
    else:
        o = b.add("memory_box", name=_fit(said[0] if said else (script.concept_name or "Value"), 16),
                  value=_number(shot) or "?", tone=None if ok else "bad")
        b.act("enter", o)
    if ok:
        _act_somewhere(b, "state", o, when, value=_number(shot, 1) or ("1" if ui else "✓"), tone="ok")
    else:
        _act_somewhere(b, "state", o, when, tone="bad")
    return o


def default_scene(shot: MotionShot, script: MotionScript, index: int) -> MotionScene:
    """One shot's scene from the script's own words. See the module docstring."""
    b = _Builder(shot)
    hl = _highlights(shot)
    beat = shot.beat
    concept = script.concept_name
    walk = script.template == "walkthrough"
    field = "paper"
    label = ""
    primary_nudge: tuple[str, str] | None = None

    ui = _is_ui(script)
    steps = _steps(script, shot, vocab_first=beat in ("title", "name_it"))
    if beat == "hook":
        # ACT THE PROBLEM OUT (2026-10-13): the hook shows the failure
        # happening — a tap that changes nothing on an app screen, or a value
        # in a memory box that does not change — with the question above it
        # (one narrator) or alone (two speakers: the question is in the chat).
        field = "navy"
        duo = bool(script.speakers)
        # the whole question (up to 3 lines + the screen still fit: 319 + 60 + 560)
        o1 = None if duo else b.add("kinetic_title", text=_whole_title(shot, script),
                                    accent=list(hl[:2]))
        if o1:
            b.act("enter", o1)
        o2 = _demo(b, shot, script, ui, ok=False)
        primary_nudge = (o2, "pulse")
    elif beat == "title":
        # the concept, and its parts going round
        field = "blue"
        if not script.speakers:                  # (two speakers: the loop alone fits)
            o1 = b.add("kinetic_title", text=_fit(concept, 30), accent=[concept])
            b.act("enter", o1)
        o2 = b.add("cycle", steps=steps)
        b.act("enter", o2, _later_word(shot, 2))
        b.act("travel", o2, _later_word(shot, 4))
        primary_nudge = (o2, "highlight")
    elif beat in ("setup", "chapter") and shot.code:
        o1 = b.add("code_window", file=_code_file(script.language), lines=shot.code)
        b.act("enter", o1)
        b.act("type", o1)
        for i, h in enumerate(hl[:2]):
            b.act("highlight", o1, _cue_for(h), value=str(min(i + 1, len(shot.code))))
        label = "THE CODE"
        primary_nudge = (o1, "highlight")
    elif beat in ("setup", "break_1", "break_2", "fix_idea", "fix_flow", "takeaway") and not walk:
        label = {"setup": "THE SETUP", "break_1": "WHY IT FAILS", "break_2": "AND ALSO",
                 "fix_idea": "THE FIX", "fix_flow": "HOW IT WORKS", "takeaway": "REMEMBER"}[beat]
        if beat == "setup" and ui:
            # what is remembered, and its value
            o1 = _memory(b, shot, script, hl[0] if hl else concept)
            b.act("enter", o1)
            b.act("state", o1, _later_word(shot, 5), value=_number(shot) or _fit(_last_word(hl) or "?", 10))
            primary_nudge = (o1, "pulse")
        elif beat == "setup":
            # how it goes, step by step
            o1 = b.add("flow", steps=steps)
            b.act("enter", o1)
            b.act("travel", o1, _later_word(shot, 3))
            primary_nudge = (o1, "highlight")
        elif beat == "break_1":
            # the failure, acted out: the tap that changes nothing (a UI topic),
            # or the value wiped away
            if ui:
                button, value_name = _ui_names(script, shot)
                o1 = b.add("app_screen", title="App", button=_fit(button, 16), label=_fit(value_name, 16),
                           value=_number(shot) or "0")
                b.act("enter", o1)
                b.act("tap", o1, _later_word(shot, 3))
                _act_somewhere(b, "state", o1, [_cue_for(_symptom(shot)) if _symptom(shot) else "",
                                                _later_word(shot, 6)], tone="bad")
            else:
                o1 = _memory(b, shot, script, hl[0] if hl else concept, tone="bad")
                b.act("enter", o1)
                b.act("reset", o1, _cue_for(_symptom(shot)) if _symptom(shot) else _later_word(shot, 4))
            primary_nudge = (o1, "pulse")
        elif beat == "break_2":
            # it happens again and again: the steps on a loop (two speakers:
            # a flow, so the symptom still fits under it)
            o1 = b.add("flow" if script.speakers else "cycle", steps=steps)
            b.act("enter", o1)
            b.act("travel", o1, _later_word(shot, 3))
            symptom = _symptom(shot)
            if symptom:
                o2 = b.add("status_pill", text=symptom, tone="bad", icon="x")
                b.act("enter", o2, _cue_for(symptom))
            primary_nudge = (o1, "highlight")
        elif beat == "fix_idea":
            # the wrong way beside the right way; the right appears on its name
            field = "blue"
            wrong = _fit(_wrong_idea(script, shot), 18)
            right = _fit(concept or (hl[-1] if hl else "After"), 18)
            o1 = b.add("compare", left=wrong, right=right, left_icon="x",
                       right_icon=(steps[0]["name"] if steps else "check"))
            b.act("enter", o1)
            b.act("reveal", o1, concept if _key(concept.split()[0] if concept else "") in shot_words(shot)
                  else _later_word(shot, 4))
            primary_nudge = (o1, "pulse")
        elif beat == "fix_flow":
            # the fix as cause and effect: something travels to the result
            o1 = b.add("flow", steps=steps, packet=_fit(hl[0], 10) if hl and len(hl[0]) <= 10 else None)
            b.act("enter", o1)
            b.act("travel", o1, _cue_for(hl[0]) if hl else _later_word(shot, 3))
            ok_text = _fit(hl[-1] if len(hl) > 1 else "It works", 26)
            o2 = b.add("status_pill", text=ok_text[:1].upper() + ok_text[1:], tone="ok", icon="check")
            b.act("enter", o2, _cue_for(hl[-1]) if len(hl) > 1 else _later_word(shot, 8))
            primary_nudge = (o1, "highlight")
        else:      # takeaway: the steps it names, travelled once more
            field = "navy"
            o1 = b.add("flow", steps=steps)
            b.act("enter", o1)
            b.act("travel", o1, _later_word(shot, 2))
            primary_nudge = (o1, "highlight")
    elif beat == "code_map":
        if shot.code:
            parts = []
            vocab = script.icon_vocabulary or []
            plain = motion_plain_text(" ".join(c.text for c in shot.captions))
            for i, h in enumerate([h for h in hl if any(h in l for l in shot.code)][:3]):
                icon = vocab[i % len(vocab)].name if vocab else "code"
                # what the caption says the part does: the words right after it
                after = plain.split(h, 1)[1].split(".")[0].split(",")[0].split() if h in plain else []
                label = _fit(" ".join(after[:5]), 20) or (vocab[i % len(vocab)].label if vocab else h)
                parts.append({"code": h, "icon": icon, "label": label})
            if not parts:
                parts = [{"code": concept, "icon": vocab[0].name if vocab else "code",
                          "label": _fit(vocab[0].label if vocab else concept, 20)}]
            o1 = b.add("code_map", lines=shot.code, parts=parts)
            b.act("enter", o1)
            for i, part in enumerate(parts):
                b.act("highlight", o1, _cue_for(part["code"]), value=str(i + 1))
            primary_nudge = (o1, "highlight")
        elif ui:
            # no code in the material: the value now kept and changing, working
            o1 = _memory(b, shot, script, concept or (hl[0] if hl else "Value"), tone="ok")
            b.act("enter", o1)
            b.act("state", o1, _later_word(shot, 4), value=_number(shot, 1) or "✓", tone="ok")
            label = "HOW IT WORKS"
            primary_nudge = (o1, "pulse")
        else:
            o1 = b.add("cycle", steps=steps)
            b.act("enter", o1)
            b.act("travel", o1, _later_word(shot, 3))
            label = "HOW IT WORKS"
            primary_nudge = (o1, "highlight")
    elif beat == "payoff":
        # the hook's picture again, now working
        field = "navy"
        duo = bool(script.speakers)
        o1 = None if duo else b.add("kinetic_title", text=_kinetic(_first_sentence(shot), 36), accent=list(hl[:2]))
        if o1:
            b.act("enter", o1)
        o2 = _demo(b, shot, script, ui, ok=True)
        primary_nudge = (o2, "pulse")
    elif beat == "recap" and not walk:
        rows = [{"icon": t.icon, "line": t.line, "sub": t.sub} for t in script.takeaways] or \
               [{"icon": "check", "line": _fit(h, 20), "sub": ""} for h in hl[:3]]
        o1 = b.add("takeaway_list", heading="Key takeaways", rows=rows)
        b.act("enter", o1)
        primary_nudge = (o1, "highlight")
    elif beat == "recap":
        final = script.chapters[-1].example_out if script.chapters else []
        o1 = b.add("recap_grid", concept=_fit(concept, 16), steps=[c.title for c in script.chapters],
                   final=_chips(final, 60))
        b.act("enter", o1)
        primary_nudge = (o1, "highlight")
    elif beat == "cta":
        field = "blue"
        o1 = b.add("end_card", up_next=_fit(script.next_topic, 40))
        b.act("enter", o1)
        primary_nudge = (o1, "pulse")
    elif beat == "name_it":
        field = "blue"
        # the steps to come, as a flow something travels through
        o1 = b.add("flow", steps=steps)
        b.act("enter", o1)
        b.act("travel", o1, concept if _key(concept) in "".join(shot_words(shot)) else _later_word(shot, 3))
        primary_nudge = (o1, "highlight")
    elif beat == "example":
        items = _chips(script.running_example.items if script.running_example else hl, 44)
        o1 = b.add("token_row", items=items, tones=["plain"] * len(items))
        b.act("enter", o1, items[0] if items and _key(items[0]) in shot_words(shot) else "start")
        label = "FOLLOW ONE EXAMPLE"
        primary_nudge = (o1, "highlight")
    elif beat == "chapter_card":
        ch = next((c for c in script.chapters if c.n == shot.chapter), None)
        o1 = b.add("chapter_card", n=shot.chapter or 1, of=len(script.chapters) or 1,
                   title=_fit(ch.title if ch else _first_sentence(shot), 32))
        b.act("enter", o1)
    elif beat == "chapter":
        ch = next((c for c in script.chapters if c.n == shot.chapter), None)
        state = shot.example or (ch.example_out if ch else hl)
        items = _chips(state, 44)
        o1 = b.add("token_row", items=items, tones=["plain"] * len(items))
        b.act("enter", o1)
        for h in hl[:2]:
            if any(_key(h) == _key(it) for it in items):
                b.act("highlight", o1, _cue_for(h),
                      value=str([_key(i) for i in items].index(_key(h)) + 1))
        label = _fit((ch.title if ch else "").upper(), 30)
        primary_nudge = (o1, "highlight")
    elif beat == "result":
        first = script.running_example.items if script.running_example else []
        final = script.chapters[-1].example_out if script.chapters else []
        o1 = b.add("big_counter", value=f"{len(first)} → {len(final)}", label="items")
        b.act("enter", o1)
        b.act("count", o1)
        items = _chips(final, 44)
        if items:
            o2 = b.add("token_row", items=items, tones=["ok"] * len(items))
            b.act("enter", o2, hl[0] if hl else None)
            primary_nudge = (o2, "highlight")
    elif beat == "takeaway":
        # the steps it names, travelled once more
        field = "navy"
        o1 = b.add("flow", steps=steps)
        b.act("enter", o1)
        b.act("travel", o1, _later_word(shot, 2))
        primary_nudge = (o1, "highlight")
    else:
        o1 = b.add("kinetic_title", text=_kinetic(_first_sentence(shot).upper()))
        b.act("enter", o1)
        primary_nudge = (o1, "highlight")

    if walk and shot.chapter and beat in ("chapter_card", "chapter"):
        # A walkthrough changes field per chapter (addendum 4.1): its card and
        # its shots share one; yellow at most once.
        field = CHAPTER_FIELDS[(shot.chapter - 1) % len(CHAPTER_FIELDS)]
    if primary_nudge:
        target, nudge = primary_nudge
        kind = next(o.kind for o in b.objects if o.id == target)
        if nudge not in lib.object_kinds()[kind]["actions"]:
            nudge = _nudge_for(kind)
        if nudge == "state":
            nudge = _nudge_for(kind) if _nudge_for(kind) != "state" else "enter"
        if nudge != "enter":
            _fill_cadence(b, shot, target, nudge, script)
    return MotionScene(field=field, label=label, objects=b.objects, actions=b.actions)


def default_scenes(script: MotionScript) -> list[MotionScene]:
    """Every shot's default scene, with transitions: a hard cut when the
    field stays, otherwise the next field transition in the rotation (never
    the same one twice in a row)."""
    scenes = [default_scene(s, script, i) for i, s in enumerate(script.shots)]
    prev_field = None
    last: str | None = None
    used: list[str] = []
    for sc in scenes:
        if prev_field is None or sc.field == prev_field:
            sc.transition = "cut"
        else:
            last = _rotation_after(last, used)
            used.append(last)
            sc.transition = last
        prev_field = sc.field
    return scenes


def fix_transitions(script: MotionScript) -> MotionScript:
    """Make every shot's TRANSITION legal for the fields actually in sequence,
    touching nothing else: a hard cut inside one field, a field transition on
    a field change, type_scatter only out of the hook, never the same field
    transition twice in a row (checks.check_motion_scene_valid). Transitions
    are mechanical — they follow from the fields — so a scene mixed from
    several sources (a first attempt, a repair, a fallback) is made
    consistent here rather than sent back to the model."""
    shots = list(script.shots)
    prev = None
    last: str | None = None
    used: list[str] = []
    for i, sh in enumerate(shots):
        sc = sh.scene
        if sc is None:
            prev = sh
            continue
        t = sc.transition
        if prev is not None and prev.scene is not None:
            if sc.field == prev.scene.field:
                t = "cut"
            elif (t == "cut" or t not in lib.transitions() or t == last
                  or (t == "type_scatter" and prev.beat != "hook")):
                t = _rotation_after(last, used)
                if t == last:
                    t = _rotation_after(t, used)
        elif t not in lib.transitions():
            t = "cut"
        if t != sc.transition:
            shots[i] = sh.model_copy(update={"scene": sc.model_copy(update={"transition": t})})
        if t != "cut":
            last = t
            used.append(t)
        prev = shots[i]
    return script.model_copy(update={"shots": shots})


def with_default_scenes(script: MotionScript) -> MotionScript:
    scenes = default_scenes(script)
    return script.model_copy(update={"shots": [s.model_copy(update={"scene": sc})
                                               for s, sc in zip(script.shots, scenes)]})
