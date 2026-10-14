"""
The virtual CAMERA and CURSOR of a motion reel (cursorcam-style: the feel of
an auto-zoomed screen recording, made synthetically). Plain deterministic
code, no model call.

CAMERA. Each shot draws its visual inside a VIEWPORT (the region the scene
objects own: under the drawn characters' heads on a duo shot with
characters, else the whole frame). A camera cue frames one RECT inside it —
a code token, a memory slot, a card, a button — at a zoom of 1.15-1.8: the
camera eases in so the zoom lands on the cue word, holds (with a slow push),
and eases back out when the narration moves on. Only the visual zooms;
captions, characters and chrome stay where they are, and the zoomed content
is clipped to its viewport, so it can never slide under a caption.

CURSOR. A clean arrow that glides on a curved path to a target, presses (a
click ripple) on its cue word, or types into a code editor one character at
a time behind a caret.

Every rect is computed HERE (where the player draws each part — mirrored
from its renderers, and pinned by web/src/motion/motion.test.tsx), so the
player only applies cues, and check_camera can prove a frame never cuts the
focused thing off.

The director only works where it fits: code scenes, UI scenes (app screens,
memory slots) and the CTA. Its cues are written into MotionShotPlan.camera
and .cursor.
"""
from . import motion_library as lib

W, H = 1080, 1920
ZOOM_MIN, ZOOM_MAX = 1.15, 1.8
MOVE = 0.7          #: seconds an ease in or out takes (web/src/motion/camera.tsx CAMERA.move)
LEAD = 0.35         #: the move starts this long before its word, so the zoom lands on it
MARGIN = 48         #: the framed rect keeps at least this much room to the viewport's edge
MIN_HOLD = 0.8      #: a framing holds at least this long before it moves again


# ===================================================================== rects

def viewport(plan, shot) -> tuple[float, float, float, float]:
    """(x, y, w, h) the shot's visual is drawn in and the camera may zoom, in
    the coordinates it is laid out in. On the board stage that is the region
    the board shows (library.json frame.board src_*)."""
    full = {k for k, s in lib.object_kinds().items() if s["layout"] == "full"}
    if getattr(plan, "stage", None) == "board" and shot.characters:
        b = lib.library()["frame"]["board"]
        kind = next((o.kind for o in shot.objects if o.kind in full), None)
        src = (b["src_full_kind"].get(kind, b["src_full"]) if kind else b["src_placed"])
        return tuple(float(v) for v in src)
    if any(o.kind in full for o in shot.objects):
        # a full-frame card: everything above the caption band (tokens.ts SAFE.captionTop - 40)
        return (0.0, 150.0, float(W), round(H * 0.70) - 40 - 150.0)
    if plan.characters and shot.characters:
        top = lib.library()["frame"]["characters"]["top"]
        return (0.0, 150.0, float(W), float(top - 150))
    return (0.0, 150.0, float(W), 1300.0 - 150.0)


def _code_cols(text: str) -> int:
    return len(text)


def part_rect(obj, part: int | None = None, right: float = W - 60):
    """Where a part of an object is drawn, in frame units (x, y, w, h), or
    None when the object has no such part. Mirrors the renderers. `right`:
    where a code map's callouts must end (left of the presenter on the board)."""
    b = obj.box
    p = obj.props
    k = obj.kind
    if k == "code_window" and b is not None:
        lines = p.get("lines") or []
        i = 0 if part is None else max(0, min(len(lines) - 1, part - 1))
        cw = 43 * 0.6                                 # reference.tsx CodeWindow: 43 px mono
        width = 120 + _code_cols(lines[i] if lines else "") * cw + 40
        return (b.x, b.y + 144 + i * 120, min(b.w, width), 102.0)
    if k == "code_map":
        return _code_map_token(p, part, with_callout=True, right=right)
    if k == "system_panel" and b is not None:
        if p.get("slot_name"):
            # annotated.tsx PointerSlot: the tag, the arrow and the value's box, as drawn
            w = _pointer_width(str(p["slot_name"]), str(p.get("slot_value") or ""), 24, 110, 20, 36)
            return (b.x + 42, b.y + 150, min(b.w - 84, w), b.h - 180)
        return (b.x, b.y, b.w, b.h)
    if k == "memory_box" and b is not None:
        if p.get("points_to"):
            # annotated.tsx PointerBox: tag (50 px mono), the 150 px arrow, the value's box
            w = 20 + _pointer_width(str(p.get("name") or ""), str(p["points_to"]), 30, 190, 25.3, 46)
            return (b.x + 20, b.y + b.h / 2 - 70, min(b.w - 40, w), 140.0)
        bw = min(b.w, 560)
        return (b.x + b.w / 2 - bw / 2, b.y + 10, bw, b.h - 10)
    if k == "compare" and b is not None:
        cw = (b.w - 40) / 2
        if part == 1:
            return (b.x, b.y + 10, cw, b.h - 20)
        if part == 2:
            return (b.x + cw + 40, b.y + 10, cw, b.h - 20)
        return (b.x, b.y, b.w, b.h)
    if k == "end_card":
        if part == 1:                                   # the Follow button (annotated.EndCardCued)
            return (540 - 230, 700 - 75, 460.0, 150.0)
        if part == 2:                                   # the Up next card
            return (90.0, 880.0, 900.0, 260.0)
        return (60.0, 480.0, 960.0, 900.0)
    if k in ("status_pill", "trigger_chip") and b is not None:
        # the pill as drawn, centred in its row (reference.tsx StatusPill / TriggerChip at
        # objects.tsx SIZES 44 / 42): about 0.55 em a character, plus its icon and padding
        size = 44 if k == "status_pill" else 42
        text = str(p.get("text") or p.get("label") or "")
        w = min(b.w, len(text) * size * 0.56 + size * 2.9)
        return (b.x + (b.w - w) / 2, b.y + b.h / 2 - size * 0.95, w, size * 1.9)
    if b is not None and b.h > 0:
        return (b.x, b.y, b.w, b.h)
    return None


def _pointer_width(name: str, value: str, name_cw: float, arrow: float, item_cw: float, item_pad: float) -> float:
    """How wide a name -> value pointer is drawn: the name tag, the arrow and
    the value's box (a list as cells)."""
    import re
    m = re.fullmatch(r"\s*\[(.*)\]\s*", value)
    items = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()] if m else [value]
    box = sum(len(it) * item_cw + item_pad for it in items) + 12 * (len(items) - 1) + 24 + 12
    return 52 + 34 + len(name) * name_cw + arrow + box


def _code_map_token(p: dict, part: int | None, with_callout: bool = False, right: float = W - 60):
    """annotated.tsx CodeAnnotated: x0 60, y0 400, padX 60, rows 114 apart,
    54 px mono (0.6 em a column). `with_callout`: the token together with its
    callout under the code (the label the zoom must show too)."""
    lines = p.get("lines") or []
    parts = p.get("parts") or []
    if part is None or not (1 <= part <= len(parts)):
        return (60.0, 400.0, 960.0, 72.0 + len(lines) * 114)
    tok = _token_rect(lines, parts[part - 1].get("code", ""))
    if tok is None or not with_callout:
        return tok
    # CodeAnnotated places callouts by token x, rightmost shallowest
    placed = []
    for i, pt in enumerate(parts):
        r = _token_rect(lines, pt.get("code", ""))
        if r is not None:
            placed.append((r[0] + r[2] / 2, i))
    depth = {i: d for d, (_, i) in enumerate(sorted(placed, reverse=True))}
    tx = tok[0] + tok[2] / 2
    label = parts[part - 1].get("label", "")
    pill_w = 56 + 26 + len(label) * 23 + 64
    left = max(60.0, min(tx - 44, right - pill_w))
    top = 400 + 72 + len(lines) * 114 + 80 + depth.get(part - 1, 0) * 150
    x0, y0 = min(tok[0], left), tok[1]
    x1, y1 = max(tok[0] + tok[2], left + pill_w), top + 92
    return (x0, y0, x1 - x0, y1 - y0)


def _token_rect(lines: list[str], code: str):
    import re
    order = sorted(range(len(lines)), key=lambda i: bool(re.match(r"\s*(#|//|--)", lines[i])))
    for row in order:
        line = lines[row]
        if re.fullmatch(r"[A-Za-z_$][\w$]*", code):
            m = re.search(rf"(^|[^\w$]){re.escape(code)}(?![\w$])", line)
            col = m.start() + len(m.group(1)) if m else -1
            n = len(code)
        else:
            col, n = line.find(code), len(code)
            if col < 0 and code.strip()[:1] in "[({" :
                a = line.find(code.strip()[0]); close = {"[": "]", "(": ")", "{": "}"}[code.strip()[0]]
                z = line.rfind(close)
                col, n = (a, z - a + 1) if a >= 0 and z > a else (-1, 0)
        if col >= 0:
            cw = 54 * 0.6
            return (60 + 60 + col * cw - 10, 400 + 36 + row * 114 + 6, n * cw + 20, 90.0)
    return None


# ===================================================================== framing

def framing(rect, zoom: float, vp) -> tuple[float, float, float]:
    """(scale, focus x, focus y) that shows `rect` at about `zoom` inside the
    viewport: the zoom is capped so the rect fits with MARGIN on every side,
    and the focus is clamped so the zoomed layer always covers the viewport
    (no empty edge). Same formula as camera.tsx framingOf."""
    x, y, w, h = rect
    vx, vy, vw, vh = vp
    fit = min((vw - 2 * MARGIN) / max(1.0, w), (vh - 2 * MARGIN) / max(1.0, h))
    s = max(1.0, min(zoom, fit))
    cx, cy = x + w / 2, y + h / 2
    hw, hh = vw / (2 * s), vh / (2 * s)
    cx = min(max(cx, vx + hw), vx + vw - hw)
    cy = min(max(cy, vy + hh), vy + vh - hh)
    return s, cx, cy


def on_screen(rect, frame, vp) -> tuple[float, float, float, float]:
    """`rect` after the camera framing `frame` = (s, fx, fy), in frame units."""
    s, fx, fy = frame
    vx, vy, vw, vh = vp
    x, y, w, h = rect
    return (vx + vw / 2 + (x - fx) * s, vy + vh / 2 + (y - fy) * s, w * s, h * s)


# ===================================================================== director

def _word_at(shot, t: float):
    best = None
    for c in shot.captions:
        for w in c.words:
            if w.start <= t + 1e-3:
                best = w
    return best


def _caption_end(shot, t: float) -> float:
    """When the caption being spoken at t ends (the narration moves on)."""
    for c in shot.captions:
        if c.start - 0.05 <= t <= c.end + 0.05:
            return c.end
    return shot.end


def direct(plan):
    """The plan with camera and cursor cues on the shots where they fit."""
    shots = []
    for shot in plan.shots:
        cam, cur = _direct_shot(plan, shot)
        shots.append(shot.model_copy(update={"camera": cam, "cursor": cur}))
    return plan.model_copy(update={"shots": shots})


def _cue(t0, t1, target, part, rect, zoom, vp, why):
    return {"t0": round(t0, 3), "t1": round(t1, 3), "target": target, "part": part,
            "rect": [round(v, 1) for v in rect], "zoom": zoom, "viewport": [round(v, 1) for v in vp], "why": why}


def _direct_shot(plan, shot):
    vp = viewport(plan, shot)
    objs = {o.id: o for o in shot.objects}
    cam: list[dict] = []
    cur: list[dict] = []
    acts = sorted(shot.actions, key=lambda a: a.t)

    board = getattr(plan, "stage", None) == "board" and shot.characters
    right = lib.library()["frame"]["board"]["callout_right"] if board else W - 60

    def focus(a_t, target, part, zoom, why, until=None):
        o = objs.get(target)
        rect = part_rect(o, part, right) if o else None
        if rect is None:
            return
        t0 = max(shot.start + 0.1, a_t - LEAD)
        t1 = until if until is not None else _caption_end(shot, a_t)
        t1 = min(max(t1, t0 + MOVE + MIN_HOLD), shot.end - 0.15)
        if t1 - t0 < MOVE + 0.4:
            return
        if cam and cam[-1]["target"] == target and cam[-1]["part"] == part:
            cam[-1]["t1"] = round(max(cam[-1]["t1"], t1), 3)      # same thing: keep holding
            return
        if cam and t0 < cam[-1]["t0"] + MOVE + MIN_HOLD:
            return                                                 # too soon after the last move
        if framing(rect, zoom, vp)[0] < ZOOM_MIN:
            return                                                 # too big to zoom on: stay wide
        if cam and t0 < cam[-1]["t1"]:
            cam[-1]["t1"] = round(t0, 3)                           # hand over straight from it
        cam.append(_cue(t0, t1, target, part, rect, zoom, vp, why))

    for a in acts:
        o = objs.get(a.target)
        if o is None:
            continue
        k = o.kind
        part = int(a.value) if str(a.value or "").isdigit() else None
        if a.do == "focus":                                       # the scene asked for it
            focus(a.t, o.id, part, 1.6, "asked for by the scene")
        elif a.do == "click":
            rect = (_code_map_token(o.props, part) if k == "code_map" else part_rect(o, part))
            if rect:
                cur.append({"t": round(a.t, 3), "do": "click", "target": o.id, "part": part,
                            "rect": [round(v, 1) for v in rect]})
        elif k == "code_window" and a.do == "type":
            text = "\n".join(o.props.get("lines") or [])
            # typed while the line is talked about: to the end of the next caption
            nxt = [c for c in shot.captions if c.start > a.t]
            t_end = min((nxt[0].end if nxt else _caption_end(shot, a.t)), a.t + 0.07 * len(text) + 1.2)
            rect = part_rect(o, 1)
            cur.append({"t": round(a.t, 3), "do": "type", "target": o.id, "part": 1, "text": text,
                        "t_end": round(t_end, 3), "rect": [round(v, 1) for v in rect]})
            focus(a.t, o.id, 1, 1.4, "the line being typed", until=t_end + 0.6)
        elif k == "code_window" and a.do == "highlight":
            focus(a.t, o.id, int(a.value or 1), 1.6, "the highlighted line")
        elif k == "code_map" and a.do == "highlight":
            part = int(a.value or 1)
            focus(a.t, o.id, part, 1.7, "the code token being explained")
            rect = _code_map_token(o.props, part)                 # the click lands on the token itself
            last = next((c for c in reversed(cur) if c["target"] == o.id), None)
            # a click when the part changes, and never two within 0.9 s (no jitter)
            if rect and (last is None or (last["part"] != part and a.t - last["t"] >= 0.9)):
                cur.append({"t": round(a.t, 3), "do": "click", "target": o.id, "part": part,
                            "rect": [round(v, 1) for v in rect]})
        elif k in ("system_panel", "memory_box") and a.do in ("state", "pulse") \
                and (o.props.get("slot_name") or o.props.get("points_to")):
            focus(a.t, o.id, None, 1.45, "the memory slot being described")
        elif k == "app_screen" and a.do == "tap":
            focus(a.t, o.id, None, 1.3, "the screen being tapped")
        elif k == "end_card" and a.do == "tap":
            rect = part_rect(o, 1)
            cur.append({"t": round(a.t, 3), "do": "click", "target": o.id, "part": 1,
                        "rect": [round(v, 1) for v in rect]})
            focus(a.t, o.id, 1, 1.25, "the Follow button", until=a.t + 1.0)
    # a cursor click on the memory slot's name when the narration names it again
    for a in acts:
        o = objs.get(a.target)
        if o is not None and o.kind == "system_panel" and o.props.get("slot_name"):
            w = _named(shot, o.props["slot_name"], after=a.t - 0.01)
            if w is not None and not any(c["do"] == "click" and c["target"] == o.id for c in cur):
                r = part_rect(o, None)
                tag_w = 76 + len(o.props["slot_name"]) * 24
                cur.append({"t": round(w.start, 3), "do": "click", "target": o.id, "part": None,
                            "rect": [round(r[0], 1), round(r[1], 1), round(tag_w, 1), round(r[3], 1)]})
    cur.sort(key=lambda c: c["t"])
    return cam, cur


def _named(shot, name: str, after: float):
    import re
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    for c in shot.captions:
        for w in c.words:
            if w.start > after and re.sub(r"[^a-z0-9]", "", w.text.lower()) == key:
                return w
    return None


# ===================================================================== check

def check_camera(plan):
    """motion_camera_safe: every framing keeps its target whole inside the
    viewport, zooms within 1.15-1.8 (or not at all when the target is too
    big), holds at least MIN_HOLD, and no two moves overlap."""
    from .checks import GraderResult
    problems = []
    for shot in plan.shots:
        cues = getattr(shot, "camera", None) or []
        last_end = -1.0
        for c in cues:
            rect, vp = c["rect"], c["viewport"]
            frame = framing(rect, c["zoom"], vp)
            x, y, w, h = on_screen(rect, frame, vp)
            vx, vy, vw, vh = vp
            # never cut off: the target wholly inside its viewport (the zoom is chosen
            # to leave MARGIN around it; a target already at the visual's edge stays there)
            if x < vx - 1 or y < vy - 1 or x + w > vx + vw + 1 or y + h > vy + vh + 1:
                problems.append(f"{shot.id}: {c['target']} would be cut off at zoom {frame[0]:.2f}")
            if not (frame[0] == 1.0 or ZOOM_MIN - 1e-6 <= frame[0] <= ZOOM_MAX + 1e-6):
                problems.append(f"{shot.id}: zoom {frame[0]:.2f} outside {ZOOM_MIN}-{ZOOM_MAX}")
            if c["t1"] - c["t0"] < MOVE + MIN_HOLD - 1e-6 and c is not cues[-1]:
                problems.append(f"{shot.id}: {c['target']} framed for only {c['t1'] - c['t0']:.2f}s")
            if c["t0"] < last_end - 1e-6:
                problems.append(f"{shot.id}: two camera moves overlap at {c['t0']:.2f}s")
            last_end = c["t1"]
            if c["t0"] < shot.start - 1e-6 or c["t1"] > shot.end + 1e-6:
                problems.append(f"{shot.id}: a camera cue runs outside its shot")
    if problems:
        return GraderResult("motion_camera_safe", False, "; ".join(problems))
    n = sum(len(getattr(s, "camera", None) or []) for s in plan.shots)
    return GraderResult("motion_camera_safe", True, f"{n} framing(s), every target whole and inside its viewport")
