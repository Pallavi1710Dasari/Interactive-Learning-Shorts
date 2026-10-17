"""
Long-form VIDEOS (format "video", 2026-10-16): a motion plan staged for a
1920x1080 landscape frame, the way a YouTube lesson looks.

Deterministic, no model call. A video's script and scenes are a walkthrough's
(many more chapters), and its shots are laid out exactly as a reel's are — in
the 1080x1920 design units every scene object is drawn in. Staging then gives
each shot a VIEW: the region of that layout its visual is drawn from (src)
and the landscape rect it is drawn into (dst), at one uniform scale. So every
scene object, animation and transition is reused as it is; only where it
lands on the frame is new.

THE FRAME (library.json frame.video):
  - presenter on (motion_teach.avatar_presence: on unless the visual needs the
    whole frame — frame.video.off_kinds: a code map, a panel, an app screen,
    a table, a title or chapter card): the visual
    on the board at the left (board_on), the mentor — a 3D VRM avatar — on
    the right, pointing at what changes (motion_teach.direct);
  - presenter off (code, a flow, a panel, a table, a title card): the visual
    on a wider board in the middle (board_off);
  - subtitles along the bottom (never under the mentor), a chapter label top
    left, a progress bar with chapter ticks at the very bottom
    (web/src/motion/video/VideoFrame.tsx draws them).
A placed visual's src is the tight box around its objects (plus a margin),
grown to the board's shape and never enlarged past zoom_cap, so a small
visual fills the board without turning into a poster. A full-frame card
(title, chapter card, recap, end card) keeps the region its own content fills.
"""
from __future__ import annotations

from . import motion_library as lib
from . import motion_teach
from .checks import GraderResult
from .schema import MotionScene, MotionSceneObject, MotionView

W, H = 1920, 1080


def geometry() -> dict:
    return lib.library()["frame"]["video"]


def _full_src(kind: str) -> list[float]:
    bd = lib.library()["frame"]["board"]
    return [float(v) for v in bd["src_full_kind"].get(kind, bd["src_full"])]


def _bbox(objects) -> tuple[float, float, float, float] | None:
    boxes = [o.box for o in objects if o.box is not None and o.box.w > 0 and o.box.h > 0]
    if not boxes:
        return None
    return (min(b.x for b in boxes), min(b.y for b in boxes),
            max(b.x + b.w for b in boxes), max(b.y + b.h for b in boxes))


def view_for(objects, dst: list[float], full_kind: str | None = None) -> MotionView:
    """The mapping that draws `objects` (laid out in reel units) into `dst`.
    A full-frame card: its own region, fitted. Placed objects: their tight box
    plus a margin, fitted but never enlarged past zoom_cap, centred in dst."""
    g = geometry()
    dx, dy, dw, dh = dst
    if full_kind:
        src = _full_src(full_kind)
        s = min(dw / src[2], dh / src[3])
    else:
        box = _bbox(objects)
        if box is None:
            box = (60.0, 240.0, 1020.0, 840.0)
        pad = g["pad"]
        x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
        s = min(dw / (x1 - x0), dh / (y1 - y0), g["zoom_cap"])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        src = [cx - dw / s / 2, cy - dh / s / 2, dw / s, dh / s]
    # the src drawn centred in dst
    sw, sh = src[2] * s, src[3] * s
    out = [dx + (dw - sw) / 2, dy + (dh - sh) / 2, sw, sh]
    return MotionView(src=[round(v, 1) for v in src], dst=[round(v, 1) for v in out], s=round(s, 4))


def to_frame(view: MotionView, x: float, y: float) -> tuple[float, float]:
    """A reel-layout point where the video frame draws it."""
    return (view.dst[0] + (x - view.src[0]) * view.s, view.dst[1] + (y - view.src[1]) * view.s)


def _relayout(shot, on: bool, duo: bool = False):
    """The shot's placed objects laid out for the board it is drawn on: with
    the presenter, against the right edge (board_right, the mentor's side, as
    a reel's board does); with two presenters, centred between them (column);
    without, in the upper region when the stack fits there (wider and
    shorter: the landscape board's shape), else as it is."""
    from .motion_scenes import layout_scene, stack_height
    kinds = lib.object_kinds()
    if not any(kinds[o.kind]["layout"] == "placed" for o in shot.objects):
        return shot
    scene = MotionScene(field=shot.field, objects=[MotionSceneObject(id=o.id, kind=o.kind, props=o.props)
                                                   for o in shot.objects])
    if on and duo:
        return shot.model_copy(update={"arrangement": "column",
                                       "objects": layout_scene(scene, duo=True, arrangement="column")})
    if on:
        return shot.model_copy(update={"arrangement": "board_right",
                                       "objects": layout_scene(scene, duo=True, arrangement="board_right")})
    upper = lib.library()["frame"]["duo"]
    if stack_height(scene) <= upper["bottom"] - upper["top"]:
        arrangement = shot.arrangement if shot.arrangement != "board_right" else "column"
        return shot.model_copy(update={"objects": layout_scene(scene, duo=True, arrangement=arrangement)})
    return shot


def stage_video(plan, vrm: dict | None = None):
    """The plan staged as a landscape video: the presenter (one VRM mentor
    per speaker) on the shots avatar_presence picks, every shot given its
    view, the characters directed to teach. A plan without characters gets
    only the views. `vrm`: role -> the 3D avatar picked for it (the
    Characters step; motion_teach.vrm_for)."""
    g = geometry()
    kinds = lib.object_kinds()
    plan = plan.model_copy(update={"format": "video"})
    on = (motion_teach.avatar_presence(plan, default_on=True) if plan.characters
          else [False] * len(plan.shots))
    duo = is_duo(plan)
    board = g["board_duo"] if duo else g["board_on"]
    shots = []
    for shot, o in zip(plan.shots, on):
        full = next((x.kind for x in shot.objects if kinds[x.kind]["layout"] == "full"), None)
        staged = shot if full else _relayout(shot, o, duo)
        view = view_for(staged.objects, board if o else g["board_off"], full)
        shots.append(staged.model_copy(update={"characters": o, "view": view}))
    video = plan.model_copy(update={"format": "video", "width": W, "height": H, "stage": "video",
                                    "shots": shots})
    if plan.characters:
        n = len(plan.characters)
        tracks = [t.model_copy(update={"cues": [], "vrm": motion_teach.vrm_for(t, n, vrm)})
                  for t in plan.characters]
        video = motion_teach.direct(video.model_copy(update={"avatars": "vrm", "characters": tracks}))
    return video


# ===================================================================== checks

def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def is_duo(plan) -> bool:
    """Two presenters (a two-speaker theme): the asker left, the explainer
    right, the board between them (frame.video.board_duo)."""
    return len(plan.characters or []) == 2


def mentor_box(slot: str = "explainer") -> tuple[float, float, float, float]:
    """A presenter's visible body on the frame (`slot`: explainer, the mentor;
    asker, the second presenter of a two-speaker video): about 0.42 of the
    canvas height wide, centred at body_x (as motion_plan_checks reads a
    reel's canvas)."""
    b = geometry()["vrm"][slot]
    cx = b["x"] + b["w"] * b.get("body_x", 0.5)
    return (cx - 0.21 * b["h"], b["y"], cx + 0.21 * b["h"], b["y"] + b["h"])


def check_video_layout(plan) -> GraderResult:
    """motion_video_layout: every shot has a view; every drawn object lands
    inside the frame, above the subtitles, and — with the presenter on — clear
    of the mentor; and the view never enlarges a visual past zoom_cap."""
    name = "motion_video_layout"
    g = geometry()
    sub_top = g["subtitle"]["top"]
    bodies = [("the mentor", mentor_box())] + ([("the asker", mentor_box("asker"))]
                                               if is_duo(plan) else [])
    problems: list[str] = []
    for s in plan.shots:
        v = s.view
        if v is None:
            problems.append(f"{s.id} has no view")
            continue
        if v.s > g["zoom_cap"] + 1e-6 and not any(lib.object_kinds()[o.kind]["layout"] == "full"
                                                   for o in s.objects):
            problems.append(f"{s.id} is enlarged {v.s:.2f}x, past {g['zoom_cap']}x")
        for o in s.objects:
            if o.box is None or o.box.w <= 0 or o.box.h <= 0:
                continue
            x0, y0 = to_frame(v, o.box.x, o.box.y)
            x1, y1 = to_frame(v, o.box.x + o.box.w, o.box.y + o.box.h)
            if x0 < -1 or y0 < -1 or x1 > W + 1 or y1 > sub_top + 1:
                problems.append(f"{s.id} {o.id} ({o.kind}) lands at "
                                f"{x0:.0f},{y0:.0f}-{x1:.0f},{y1:.0f}, outside the picture area")
            for who, body in bodies:
                if s.characters and _overlap((x0, y0, x1, y1), body):
                    problems.append(f"{s.id} {o.id} ({o.kind}) runs under {who}")
    if problems:
        return GraderResult(name, False, "; ".join(problems[:12]))
    return GraderResult(name, True, f"all {len(plan.shots)} shots fit the 1920x1080 frame")


def check_video_presence(plan) -> GraderResult:
    """motion_video_presence: the presenter is never over a visual-heavy shot
    (frame.video.off_kinds: a code map, a panel, an app screen, a table, a
    title or chapter card), is on for the hook, and every on or
    off run lasts at least min_on / min_off seconds."""
    name = "motion_video_presence"
    if not plan.characters:
        return GraderResult(name, True, "no presenter — not checked")
    r = motion_teach.rules()
    problems = []
    for i, s in enumerate(plan.shots):
        if motion_teach.heavy(s, True) and s.characters:
            problems.append(f"{s.id} shows {', '.join(o.kind for o in s.objects)} with the presenter")
        if i == 0 and not motion_teach.heavy(s, True) and not s.characters:
            problems.append(f"{s.id} (the hook) should have the presenter")
    runs, a = [], 0
    for i in range(1, len(plan.shots) + 1):
        if i == len(plan.shots) or plan.shots[i].characters != plan.shots[a].characters:
            runs.append((a, i - 1))
            a = i
    if len(runs) > 1:
        for a, b in runs:
            on = plan.shots[a].characters
            dur = plan.shots[b].end - plan.shots[a].start
            least = r["min_on"] if on else r["min_off"]
            if dur < least - 1e-6 and not (not on and any(motion_teach.heavy(x, True) for x in plan.shots[a:b + 1])):
                problems.append(f"{plan.shots[a].id}-{plan.shots[b].id}: presenter {'on' if on else 'off'} "
                                f"for only {dur:.1f} s")
    pattern = "".join("+" if s.characters else "." for s in plan.shots)
    if problems:
        return GraderResult(name, False, "; ".join(problems[:12]), {"pattern": pattern})
    return GraderResult(name, True, f"presenter on {pattern.count('+')} of {len(pattern)} shots",
                        {"pattern": pattern})


def run_checks(plan) -> list[GraderResult]:
    """A video plan's layout checks (a reel's are motion_plan_checks.run)."""
    from . import motion_plan_checks as mpc
    return [check_video_layout(plan), check_video_presence(plan),
            mpc.check_redundant_overlays(plan), mpc.check_decorative_elements(plan)]
