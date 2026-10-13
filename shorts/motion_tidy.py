"""
Deterministic clean-ups of a motion reel's scenes, run by the timing stage
before the plan is written (so they apply to every new reel, and to a saved
reel when its plan is rebuilt). Nothing here calls a model.

  - code comments used as labels ("# cart: the variable") are removed from
    code_map / code_window lines: the player points a callout at the token;
  - a memory panel whose slot is backwards (slot_name "tag", slot_value
    "cart") is turned round: the name on the left, the value it points to on
    the right (taken from the reel's own code);
  - the CTA's end card gets word-cued actions over its whole length: Follow
    pressed on "follow", the Up next card on "next", the hashtags one per
    word after it, a final settle on the last word;
  - a LOW-VALUE shot — one whose every object repeats an earlier shot's
    object, prop for prop, and which only relabels it (no tap, travel,
    count, reveal or type) — gets a picture that shows something new (a
    memory box drawn as its name pointing at its value), or is dropped;
  - on the REAL audio clock, any stretch that would hold still longer than
    the cadence limit gets an action cued on a word spoken there.

Each function returns what it changed as plain notes for the timing report.
"""
import re

from . import motion_library as lib
from .schema import MotionScene, MotionSceneAction, MotionScript, MotionShot

#: Words that name the ROLE of a slot, never a value: a panel slot named one
#: of these, holding a code name, is backwards.
_ROLE_WORDS = frozenset("tag name label variable var pointer ref reference key handle".split())
#: Beats a shot can never be dropped from: the reel's frame.
_STRUCTURAL = frozenset({"hook", "title", "recap", "cta", "chapter_card", "name_it", "takeaway"})
#: Actions that SHOW something happening (a shot with one of these is not a relabel).
_DOING = frozenset({"tap", "travel", "count", "reveal", "type", "reset", "stamp"})
#: Props that only style an object; two objects differing in these are the same object.
_STYLE_PROPS = frozenset({"tone", "tones", "accent"})

_COMMENT = re.compile(r"^\s*(#|//|--|/\*)\s*(.*?)\s*(\*/)?\s*$")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


# ============================================================ code comments

def _code_lines(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not _COMMENT.match(ln)]


def comment_label(line: str, others: list[str]) -> bool:
    """Is `line` a comment used as a LABEL: "# cart: the variable",
    "// count - the state"? It names a token of the real code, then says
    what it is. A real explanatory comment ("# make the list first") is
    kept."""
    m = _COMMENT.match(line)
    if not m:
        return False
    body = m.group(2)
    lab = re.match(r"^([\w$.\[\]=()]+|\[ ?\]|=)\s*(:|-|–|—|→|->|is)\s+\S", body)
    if not lab:
        return False
    token = lab.group(1)
    return any(token in ln for ln in others)


def strip_comment_labels(script: MotionScript) -> tuple[MotionScript, list[str]]:
    notes: list[str] = []
    shots = []
    for sh in script.shots:
        sc = sh.scene
        if sc is None:
            shots.append(sh)
            continue
        objs = []
        for o in sc.objects:
            lines = o.props.get("lines") if o.kind in ("code_map", "code_window") else None
            if lines:
                real = _code_lines(lines)
                keep = [ln for ln in lines if not comment_label(ln, real)]
                if keep and len(keep) < len(lines):
                    notes.append(f"{sh.id}: removed comment label(s) "
                                 + ", ".join(repr(ln) for ln in lines if ln not in keep))
                    o = o.model_copy(update={"props": {**o.props, "lines": keep}})
            objs.append(o)
        shots.append(sh.model_copy(update={"scene": sc.model_copy(update={"objects": objs})}))
    return script.model_copy(update={"shots": shots}), notes


# ============================================================ memory slots

def _assigned_value(name: str, code: list[str]) -> str | None:
    """The right-hand side of `name = ...` in the reel's code."""
    for ln in code:
        m = re.match(rf"^\s*(?:let |const |var )?{re.escape(name)}\s*=\s*(.+?);?\s*$", ln)
        if m and not m.group(1).startswith("="):
            return m.group(1)
    return None


def fix_panel_slots(script: MotionScript) -> tuple[MotionScript, list[str]]:
    """slot_name "tag" + slot_value "cart" -> slot_name "cart" + slot_value
    '["milk", "bread"]' (the value cart is assigned in the reel's code)."""
    code = [ln for s in script.shots for ln in _code_lines(s.code)]
    cap = lib.object_kinds()["system_panel"].get("max", {}).get("slot_value", 18)
    notes: list[str] = []
    shots = []
    for sh in script.shots:
        sc = sh.scene
        if sc is None:
            shots.append(sh)
            continue
        objs = []
        for o in sc.objects:
            p = o.props
            name, value = str(p.get("slot_name") or ""), str(p.get("slot_value") or "")
            if (o.kind == "system_panel" and name.lower() in _ROLE_WORDS and _IDENT.fullmatch(value)
                    and any(re.search(rf"\b{re.escape(value)}\b", ln) for ln in code)):
                rhs = _assigned_value(value, code)
                if rhs and len(rhs) <= cap:
                    o = o.model_copy(update={"props": {**p, "slot_name": value, "slot_value": rhs}})
                    notes.append(f"{sh.id}: memory slot turned round — {value} -> {rhs} "
                                 f"(was {name!r} | {value!r})")
            objs.append(o)
        shots.append(sh.model_copy(update={"scene": sc.model_copy(update={"objects": objs})}))
    return script.model_copy(update={"shots": shots}), notes


# ============================================================ the CTA

def _words(shot: MotionShot) -> list[str]:
    from .motion_timeline import caption_words
    return [re.sub(r"[^\w'@#-]", "", w) for c in shot.captions for w, _ in caption_words(c.text)]


def cta_actions(shot: MotionShot, n_tags: int) -> list[MotionSceneAction]:
    """The end card's timeline, every step on a spoken word: the card at the
    start, Follow pressed on "follow", the Up next card on "next", each
    hashtag on the next word after it, and a settle on the last word."""
    from .motion_scenes import _key
    words = _words(shot)
    keys = [_key(w) for w in words]
    oid = shot.scene.objects[0].id
    acts = [MotionSceneAction(at="start", do="enter", target=oid)]
    used: list[int] = []

    def cue_at(i: int) -> str:
        # one word, made unique going forward by taking the next words too
        for n in (1, 2, 3):
            phrase = " ".join(w for w in words[i:i + n] if w)
            k = [_key(x) for x in phrase.split()]
            first = next((j for j in range((used[-1] + 1) if used else 0, len(keys) - len(k) + 1)
                          if keys[j:j + len(k)] == k), None)
            # the same words as the action before would happen WITH it (resolve_cues)
            same = [_key(x) for x in acts[-1].at.split()] == k
            if first == i and not same:
                return phrase
        return ""

    def add(i: int, do: str, value: str | None = None) -> None:
        if i is None or i < 0 or i >= len(words) or (used and i <= used[-1]):
            return
        cue = cue_at(i)
        if cue:
            acts.append(MotionSceneAction(at=cue, do=do, target=oid, value=value))
            used.append(i)

    follow = next((i for i, k in enumerate(keys) if k.startswith("follow")), None)
    nxt = next((i for i, k in enumerate(keys) if k == "next" and (follow is None or i > follow)), None)
    if follow is None:
        follow = 0 if keys else None
    add(follow, "tap")
    if nxt is None and follow is not None:
        nxt = min(len(keys) - 1, follow + 2)
    add(nxt, "reveal")
    after = [i for i in range((nxt if nxt is not None else 0) + 1, len(keys) - 1) if len(keys[i]) >= 3]
    for j, i in enumerate(after[:n_tags]):
        add(i, "highlight", str(j + 1))
    add(len(keys) - 1, "pulse")
    return acts


def cue_cta(script: MotionScript, n_tags: int) -> tuple[MotionScript, list[str]]:
    shots, notes = [], []
    for sh in script.shots:
        sc = sh.scene
        if sh.beat == "cta" and sc is not None and len(sc.objects) == 1 and sc.objects[0].kind == "end_card":
            acts = cta_actions(sh, n_tags)
            sh = sh.model_copy(update={"scene": sc.model_copy(update={"actions": acts})})
            notes.append(f"{sh.id}: end card cued on its words — "
                         + ", ".join(f"{a.do}@{a.at}" for a in acts[1:]))
        shots.append(sh)
    return script.model_copy(update={"shots": shots}), notes


# ============================================================ low-value shots

def _same_object(a, b) -> bool:
    strip = lambda p: {k: v for k, v in p.items() if k not in _STYLE_PROPS}
    return a.kind == b.kind and strip(a.props) == strip(b.props)


def low_value_shots(script: MotionScript) -> list[tuple[str, str]]:
    """(shot id, reason) for every shot that shows nothing new: each of its
    main objects repeats an earlier shot's object exactly, and its actions
    only relabel or pulse it."""
    minor = {"status_pill", "connector", "stamp"}
    out: list[tuple[str, str]] = []
    seen: list[tuple[str, object]] = []
    for sh in script.shots:
        sc = sh.scene
        if sc is None:
            continue
        main = [o for o in sc.objects if o.kind not in minor]
        if main and sh.beat not in _STRUCTURAL and not any(a.do in _DOING for a in sc.actions):
            twins = [next((sid for sid, e in seen if _same_object(o, e)), None) for o in main]
            if all(twins):
                out.append((sh.id, f"repeats {twins[0]}'s {main[0].kind} and only relabels it"))
        seen += [(sh.id, o) for o in main]
    return out


def _resolve(shot: MotionShot, code: list[str]) -> MotionShot | None:
    """A low-value shot given a picture that shows something new, when there
    is one: a memory box whose name the reel's code assigns is drawn as the
    name POINTING at its value (memory_box points_to) — the arrow draws on the
    shot's first state change, and its tone becomes the box's. The relabel
    values ("→ list") go: the arrow says it."""
    main = [o for o in shot.scene.objects if o.kind not in ("status_pill", "connector", "stamp")]
    if len(main) != 1 or main[0].kind != "memory_box":
        return None
    box = main[0]
    rhs = _assigned_value(str(box.props.get("name", "")), code)
    cap = lib.object_kinds()["memory_box"].get("max", {}).get("points_to", 18)
    if not rhs or len(rhs) > cap:
        return None
    objs = [o.model_copy(update={"props": {**o.props, "points_to": rhs}}) if o.id == box.id else o
            for o in shot.scene.objects]
    acts = [a.model_copy(update={"value": None}) if a.target == box.id and a.do == "state" else a
            for a in shot.scene.actions]
    return shot.model_copy(update={"scene": shot.scene.model_copy(update={"objects": objs, "actions": acts})})


def drop_low_value(script: MotionScript) -> tuple[MotionScript, list[str]]:
    """Every low-value shot gets a picture that shows something new
    (_resolve), or, when there is none, is dropped."""
    low = dict(low_value_shots(script))
    if not low:
        return script, []
    code = [ln for s in script.shots for ln in _code_lines(s.code)]
    shots, notes = [], []
    for s in script.shots:
        if s.id not in low:
            shots.append(s)
            continue
        fixed = _resolve(s, code)
        if fixed is not None:
            box = next(o for o in fixed.scene.objects if o.props.get("points_to"))
            shots.append(fixed)
            notes.append(f"{s.id}: {low[s.id]} — now shows {box.props['name']} pointing to "
                         f"{box.props['points_to']}")
        else:
            notes.append(f"{s.id}: dropped — {low[s.id]}")
    return script.model_copy(update={"shots": shots}), notes


# ============================================================ all of it

def tidy(script: MotionScript, n_tags: int = 4) -> tuple[MotionScript, list[str]]:
    """Every clean-up above that needs no audio, in order."""
    notes: list[str] = []
    for step in (strip_comment_labels, fix_panel_slots, drop_low_value):
        script, n = step(script)
        notes += n
    script, n = cue_cta(script, n_tags)
    notes += n
    from .motion_scenes import fix_transitions
    return fix_transitions(script), notes


def fill_cadence(script: MotionScript, clocks) -> tuple[MotionScript, list[str]]:
    """On the real clock: every shot that would hold still past the cadence
    limit gets actions cued on words spoken in the still stretch."""
    from .motion_scenes import MAX_STILL_SECONDS, fill_cadence_on_clock, longest_still
    shots, notes = [], []
    for sh, clock in zip(script.shots, clocks):
        if sh.scene is not None:
            gap, _ = longest_still(sh, clock)
            if gap > MAX_STILL_SECONDS:
                new = fill_cadence_on_clock(sh, clock)
                after, at = longest_still(new, clock)
                added = len(new.scene.actions) - len(sh.scene.actions)
                if added:
                    notes.append(f"{sh.id}: {added} word-cued action(s) added — still "
                                 f"{gap:.1f}s -> {after:.1f}s")
                sh = new
        shots.append(sh)
    return script.model_copy(update={"shots": shots}), notes
