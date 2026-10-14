"""
Checks on a motion reel's PLAN (output/<short_id>/plan.json) — where things
are drawn, not what is said. Run by the timing stage after the plan is built.
They mirror the player's layout rules from the same numbers it reads
(web/src/motion/library.json frame), so they need no browser; the browser's
own audit (web/src/motion/overlap.ts, window.__motionOverlaps) measures the
drawn page beside them.

  motion_caption_layout       the caption / chat bubble stays in its zone: never
                              over a character, the visual or another overlay,
                              inside the safe zone, at most 70 % of the frame wide
  motion_redundant_overlays   one thing is not shown twice on a frame (a caption
                              repeating a card's words)
  motion_decorative_elements  every object on screen carries meaning: it shows
                              words, or an action makes it do something

Plans written before rev 2 are drawn by the old rules and are not checked.
"""
import re

from . import motion_library as lib
from .checks import GraderResult

W, H = 1080, 1920
#: tokens.ts SAFE
SAFE_SIDE = round(W * 0.06)
CAPTION_TOP, CAPTION_BOTTOM = round(H * 0.70), round(H * 0.80)
#: chrome drawn on a rev 2 frame, outside any object box: the progress bar and
#: the section label (MotionStage)
CHROME = {"progress": (54, 52, 1026, 70), "label": (SAFE_SIDE, 180, W - SAFE_SIDE, 222)}
#: kinds whose own words the player shows instead of a caption (rev 2)
CAPTIONLESS = frozenset({"takeaway_list", "recap_grid"})
_CODE = frozenset({"code_window", "code_map"})
_STOP = frozenset("a an the and or but so to of in on at it its is are was be by for with as "
                  "that this then than your you i my me we our just only not no".split())


def _frame() -> dict:
    return lib.library()["frame"]


def plain(text: str) -> str:
    return re.sub(r"</?b>|`", "", text or "")


def bubble_lines(text: str, max_chars: int) -> int:
    """Identity.tsx bubbleLines: greedy word wrap by characters."""
    lines, cur = 1, 0
    for w in text.split():
        if cur and cur + 1 + len(w) > max_chars:
            lines, cur = lines + 1, len(w)
        else:
            cur += (1 if cur else 0) + len(w)
    return lines


def side_bubble_height(text: str, dims: dict | None = None) -> float:
    b = dims or _frame()["chat"]["bubble"]
    return b["label_h"] + 2 * b["pad_y"] + bubble_lines(text, b["chars"]) * b["line_h"]


def board_dst() -> tuple[float, float, float, float]:
    """The board's place on the frame (x0, y0, x1, y1)."""
    x, y, w, h = _frame()["board"]["dst"]
    return (x, y, x + w, y + h)


def board_box(box, full_kind: str | None):
    """A box laid out in the visual's region, where the board draws it
    (cast/teach.ts boardMap)."""
    bd = _frame()["board"]
    src = (bd["src_full_kind"].get(full_kind, bd["src_full"]) if full_kind else bd["src_placed"])
    dx, dy, dw, dh = bd["dst"]
    s = min(dw / src[2], dh / src[3])
    ox = dx + (dw - src[2] * s) / 2
    f = lambda x, y: (ox + (x - src[0]) * s, dy + (y - src[1]) * s)
    (x0, y0), (x1, y1) = f(box[0], box[1]), f(box[2], box[3])
    return (x0, y0, x1, y1)


def character_boxes(plan) -> dict[str, tuple[float, float, float, float]]:
    """Where each character is drawn on the board stage (cast/teach.ts
    placement): the visible half-body, head to waist."""
    bd = _frame()["board"]
    out = {}
    n = len(plan.characters)
    if getattr(plan, "avatars", None) == "vrm":
        # a 3D avatar's canvas: its body stands at body_x, about 0.4 of its height wide
        for t in plan.characters:
            b = bd["vrm"]["asker" if (n > 1 and t.side == "left") else "explainer"]
            cx = b["x"] + b["w"] * b.get("body_x", 0.5)
            out[f"{t.role or 'narrator'} avatar"] = (cx - 0.2 * b["h"], b["y"], cx + 0.2 * b["h"], b["y"] + b["h"])
        return out
    for t in plan.characters:
        spot = bd["narrator"] if n == 1 else bd["asker"] if t.side == "left" else bd["explainer"]
        s = spot["scale"]
        # the drawn body spans about 110-290 of the rig's 400 width, plus the arms
        out[f"{t.role or 'narrator'} character"] = (spot["cx"] - 130 * s, spot["top"], spot["cx"] + 130 * s,
                                                     spot["top"] + (bd["view_bottom"] - 6) * s)
    return out


def _overlap(a, b) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 0 and min(a[3], b[3]) - max(a[1], b[1]) > 0


def _full(shot, full_kinds) -> bool:
    return any(o.kind in full_kinds for o in shot.objects)


def caption_zone(plan, shot) -> tuple[str, tuple[float, float, float, float]] | None:
    """Where the shot's captions are drawn (rev 2): ("chat", box) beside the
    characters, ("chat_plain", box) for a chat with no characters,
    ("caption", box) for the karaoke caption, None when no caption shows."""
    fr = _frame()
    full_kinds = {k for k, s in lib.object_kinds().items() if s["layout"] == "full"}
    full = _full(shot, full_kinds)
    if any(o.kind in CAPTIONLESS for o in shot.objects) or not shot.captions:
        return None
    if getattr(plan, "stage", None) == "board" and plan.characters and shot.characters and shot.layout == "duo":
        c = fr["board"]["chat"]
        side = fr["chat"]["bubble"]["side"]
        return "board_chat", (side, c["top"], W - side, c["bottom"])
    if shot.layout == "duo" and not full:
        if plan.characters and getattr(plan, "rev", 1) >= 2 and not shot.characters:
            b = fr["chat"]["bubble"]
            boxes = [o.box for o in shot.objects if o.box and o.box.h > 0]
            top = max([fr["chat"]["top"]] + [bx.y + bx.h + 40 for bx in boxes])
            return "chat", (b["side"], top, W - b["side"], b["safe_bottom"])
        if plan.characters and shot.characters:
            b = fr["chat"]["bubble"]
            top = fr["characters"]["bottom"] + b["avatar_gap"]
            return "chat", (b["side"], top, W - b["side"], b["safe_bottom"])
        boxes = [o.box for o in shot.objects if o.box and o.box.h > 0]
        top = max([fr["chat"]["top"]] + [bx.y + bx.h + 40 for bx in boxes])
        return "chat_plain", (fr["chat"]["side"], top, W - fr["chat"]["side"], fr["chat"]["bottom"])
    return "caption", (SAFE_SIDE, CAPTION_TOP, W - SAFE_SIDE, CAPTION_BOTTOM)


def check_caption_layout(plan) -> GraderResult:
    name = "motion_caption_layout"
    if getattr(plan, "rev", 1) < 2:
        return GraderResult(name, True, "plan drawn by the rev 1 rules — not checked")
    fr = _frame()
    b = fr["chat"]["bubble"]
    chars = fr["characters"]
    problems: list[str] = []
    off: list[str] = []
    if b["max_w"] > 0.7 * W + 1:
        problems.append(f"bubble max width {b['max_w']} is over 70 % of the frame")
    for shot in plan.shots:
        z = caption_zone(plan, shot)
        if z is None:
            continue
        kind, box = z
        bad: list[str] = []
        if box[0] < SAFE_SIDE - 12 or box[2] > W - SAFE_SIDE + 12 or box[3] > H * 0.82 + 1:
            bad.append("the caption leaves the safe zone")
        board = getattr(plan, "stage", None) == "board" and plan.characters and shot.characters
        if board:
            for who, cb in character_boxes(plan).items():
                if _overlap(box, cb):
                    bad.append(f"the caption overlaps the {who}")
        elif plan.characters and shot.characters:
            band = (0, chars["top"], W, chars["bottom"] + (b["avatar_gap"] if kind == "chat" else 0))
            if _overlap(box, band):
                bad.append("the caption is inside the characters' space (no clear gap)")
        for o in shot.objects:
            if o.box and o.box.h > 0:
                ob = (o.box.x, o.box.y, o.box.x + o.box.w, o.box.y + o.box.h)
                if board:            # drawn onto the board: where it really is
                    ob = board_box(ob, None)
                if _overlap(box, ob):
                    bad.append(f"the caption overlaps {o.id} ({o.kind})")
        if board and _overlap(box, board_dst()):
            bad.append("the caption overlaps the board")
        for part, cb in CHROME.items():
            if _overlap(box, cb):
                bad.append(f"the caption overlaps the {part}")
        if kind in ("chat", "board_chat"):
            room = box[3] - box[1]
            for c in shot.captions:
                h = side_bubble_height(plain(c.text), fr["board"]["chat"] if kind == "board_chat" else None)
                if h > room:
                    bad.append(f"the bubble {plain(c.text)[:30]!r}… needs {h:.0f} of {room:.0f}")
        if bad:
            off.append(shot.id)
            problems.append(f"{shot.id}: " + "; ".join(dict.fromkeys(bad)))
    if problems:
        return GraderResult(name, False, " | ".join(problems), {"shots": off})
    return GraderResult(name, True, "every caption stays in its zone, clear of the characters, "
                                    "the visual and the chrome")


def _content(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", plain(text).lower()) if w not in _STOP]


def _object_texts(o) -> list[str]:
    """Every string an object shows (rows' lines and subs one by one)."""
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in ("icon", "tone", "tones", "name") or o.kind in ("memory_box", "flow", "cycle"):
                    walk(x)
    walk(o.props)
    return [t for t in out if t.strip()]


def check_redundant_overlays(plan) -> GraderResult:
    """The same words twice on one frame: a caption that repeats the text of
    an object shown with it."""
    name = "motion_redundant_overlays"
    if getattr(plan, "rev", 1) < 2:
        return GraderResult(name, True, "plan drawn by the rev 1 rules — not checked")
    problems: list[str] = []
    off: list[str] = []
    for shot in plan.shots:
        if caption_zone(plan, shot) is None:
            continue
        # code is read aloud on purpose: saying a line while it is shown is how it is taught
        texts = [(o.id, t) for o in shot.objects if o.kind not in _CODE for t in _object_texts(o)]
        for c in shot.captions:
            cw = _content(c.text)
            for oid, t in texts:
                ow = _content(t)
                if len(ow) >= 3 and len(set(ow) & set(cw)) / len(set(ow)) >= 0.8:
                    off.append(shot.id)
                    problems.append(f"{shot.id}: the caption {plain(c.text)[:40]!r} repeats {oid}'s {t!r}")
    if problems:
        return GraderResult(name, False, "; ".join(problems), {"shots": sorted(set(off))})
    return GraderResult(name, True, "no frame shows the same words twice")


def check_decorative_elements(plan) -> GraderResult:
    """Decoration: a placed object that says nothing (no words on it) and
    that no action makes do anything — it fills space without meaning. A
    connector counts when it is drawn between two objects (it shows a link)."""
    name = "motion_decorative_elements"
    if getattr(plan, "rev", 1) < 2:
        return GraderResult(name, True, "plan drawn by the rev 1 rules — not checked")
    problems: list[str] = []
    for shot in plan.shots:
        for o in shot.objects:
            if o.box is None or o.kind == "connector":
                continue
            acted = any(a.target == o.id and a.do != "enter" for a in shot.actions)
            words = [w for t in _object_texts(o) for w in re.findall(r"[A-Za-z0-9]+", t)]
            if not acted and not words:
                problems.append(f"{shot.id}.{o.id} ({o.kind}) shows no words and nothing acts on it")
    if problems:
        return GraderResult(name, False, "; ".join(problems))
    return GraderResult(name, True, "every object carries words or does something")


def check_layout_variety(plan) -> GraderResult:
    """motion_layout_variety: no one layout on more than 40 % of the shots,
    and never three shots in a row with the same layout (rev 3: each shot's
    arrangement, or its full-frame card's own layout)."""
    name = "motion_layout_variety"
    if getattr(plan, "rev", 1) < 3:
        return GraderResult(name, True, "plan drawn before layout arrangements (rev < 3) — not checked")
    names = [s.arrangement or "column" for s in plan.shots]
    problems = []
    counts = {n: names.count(n) for n in set(names)}
    worst = max(counts, key=counts.get)
    if len(names) >= 5 and counts[worst] > 0.4 * len(names):
        problems.append(f"{counts[worst]} of {len(names)} shots use the {worst} layout (at most 40 %)")
    for i in range(2, len(names)):
        if names[i] == names[i - 1] == names[i - 2]:
            ids = ", ".join(s.id for s in plan.shots[i - 2:i + 1])
            problems.append(f"{ids} all use the {names[i]} layout")
    if problems:
        return GraderResult(name, False, "; ".join(problems), {"layouts": names})
    return GraderResult(name, True, "layouts: " + ", ".join(f"{n} {c}" for n, c in sorted(counts.items())),
                        {"layouts": names})


def run(plan) -> list[GraderResult]:
    return [check_caption_layout(plan), check_redundant_overlays(plan), check_decorative_elements(plan),
            check_layout_variety(plan)]
