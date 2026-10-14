"""
The virtual camera and cursor (shorts/motion_camera.py), on the real reel of
job f64077e78448 (its approved scenes and recorded word times, the fixtures
evals/fixtures/motion/variable_points_to_value_*):

  - the director frames only where it fits (the typed code line, the memory
    slot, each code-map token with its callout, the Follow button), types the
    code line, clicks tokens no closer than 0.9 s apart;
  - every framing keeps its target whole inside its viewport (motion_camera_safe),
    and the check fails a framing that would not;
  - a full-frame card's viewport ends above the caption band;
  - a scene's own "focus" / "click" actions are honoured;
  - the framing formula gives the same numbers as camera.tsx (motion.test.tsx
    pins the same case).

    SHORTS_STUB=1 python -m shorts.motion_camera_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
import random
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_camera, motion_tidy
from shorts.motion_timeline import ShotClock, build_plan
from shorts.schema import MotionCaptionTiming, MotionScript, MotionSceneAction

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "evals/fixtures/motion"
SCRIPT = MotionScript.model_validate_json((FIX / "variable_points_to_value_scenes.json").read_text())
OLD = json.loads((FIX / "variable_points_to_value_plan_rev1.json").read_text())


def _caption(c: dict) -> MotionCaptionTiming:
    """A recorded caption; re-timed evenly when the caption is now split into
    other words than when it was recorded (the code-symbol fix split "The`[]`")."""
    from shorts.motion_timeline import caption_words, even_words
    cap = MotionCaptionTiming(**c)
    if len(cap.words) != len(caption_words(cap.text)):
        cap = cap.model_copy(update={"words": even_words(cap.text, cap.start, cap.end)})
    return cap


def _plan(script=None, characters=True):
    script = script or motion_tidy.tidy(SCRIPT, n_tags=4)[0]
    by_id = {s["id"]: s for s in OLD["shots"]}
    clocks = [ShotClock(id=s.id, start=by_id[s.id]["start"], end=by_id[s.id]["end"],
                        captions=[_caption(c) for c in by_id[s.id]["captions"]]) for s in script.shots]
    from shorts.motion_reel import _cast
    return build_plan(script, clocks, cast=_cast(script), tags=["#python"], characters=characters,
                      character="cs", host_character="host", design="midnight_lab")


def test_the_director_frames_only_where_it_fits():
    plan = motion_camera.direct(_plan())
    cams = {s.id: [(c["target"], c["part"]) for c in s.camera] for s in plan.shots if s.camera}
    assert cams == {"s03": [("o1", 1)], "s04": [("o2", None)], "s07": [("o1", 1), ("o1", 2), ("o1", 3)],
                    "s08": [("o1", None)], "s10": [("o1", 1)]}, cams
    s03 = next(s for s in plan.shots if s.id == "s03")
    assert s03.cursor[0]["do"] == "type" and s03.cursor[0]["text"] == 'cart = ["milk", "bread"]'
    s07 = next(s for s in plan.shots if s.id == "s07")
    clicks = [c["t"] for c in s07.cursor if c["do"] == "click"]
    assert all(b - a >= 0.9 for a, b in zip(clicks, clicks[1:])), clicks
    assert motion_camera.check_camera(plan).passed


def test_every_framing_keeps_its_target_whole():
    plan = motion_camera.direct(_plan())
    for s in plan.shots:
        for c in s.camera:
            f = motion_camera.framing(c["rect"], c["zoom"], c["viewport"])
            assert motion_camera.ZOOM_MIN <= f[0] <= motion_camera.ZOOM_MAX, (s.id, f)


def test_the_check_fails_a_framing_that_cuts_off():
    plan = motion_camera.direct(_plan())
    shots = []
    for s in plan.shots:
        if s.id == "s07":
            bad = dict(s.camera[0], rect=[-200, 442, 300, 90])      # partly off its viewport
            s = s.model_copy(update={"camera": [bad] + s.camera[1:]})
        shots.append(s)
    r = motion_camera.check_camera(plan.model_copy(update={"shots": shots}))
    assert not r.passed and "s07" in r.reason and "cut off" in r.reason, r.reason


def test_a_full_frame_viewport_ends_above_the_captions():
    plan = _plan(characters=False)
    s07 = next(s for s in plan.shots if s.id == "s07")
    x, y, w, h = motion_camera.viewport(plan, s07)
    assert y + h <= round(1920 * 0.70) - 40, (y, h)


def test_a_scene_can_ask_for_the_camera_and_cursor():
    shots = []
    for s in SCRIPT.shots:
        if s.id == "s05":
            acts = list(s.scene.actions)
            i = next(i for i, a in enumerate(acts) if a.at == "box is")
            # in speaking order: focus on "where", the click with the existing "box is" action
            acts[i:i] = [MotionSceneAction(at="where", do="focus", target="o2")]
            acts.insert(i + 2, MotionSceneAction(at="box is", do="click", target="o2"))
            s = s.model_copy(update={"scene": s.scene.model_copy(update={"actions": acts})})
        shots.append(s)
    from shorts.motion_scenes import scene_problems
    s05 = next(s for s in shots if s.id == "s05")
    assert scene_problems(s05, duo=True) == [], scene_problems(s05, duo=True)
    plan = motion_camera.direct(_plan(motion_tidy.tidy(SCRIPT.model_copy(update={"shots": shots}), 4)[0]))
    p05 = next(s for s in plan.shots if s.id == "s05")
    assert any(c["target"] == "o2" for c in p05.camera) and any(c["do"] == "click" for c in p05.cursor)


def test_the_framing_formula_matches_the_player():
    s, fx, fy = motion_camera.framing([110, 442, 150, 90], 1.7, (0, 150, 1080, 1154))
    assert (round(s, 4), round(fx, 2), round(fy, 2)) == (1.7, 317.65, 489.41)
    rnd = random.Random(7)
    vp = (0.0, 150.0, 1080.0, 1154.0)
    for _ in range(300):
        w, h = rnd.uniform(20, 900), rnd.uniform(20, 800)
        rect = (rnd.uniform(0, 1080 - w), rnd.uniform(150, 150 + 1154 - h), w, h)
        f = motion_camera.framing(rect, rnd.uniform(1.15, 1.8), vp)
        if f[0] == 1.0:
            continue
        x, y, ww, hh = motion_camera.on_screen(rect, f, vp)
        # always whole inside the viewport, and with MARGIN to spare unless it sat at the edge already
        assert x >= -1e-6 and y >= 150 - 1e-6 and x + ww <= 1080 + 1e-6 and y + hh <= 150 + 1154 + 1e-6, (rect, f)
        m = motion_camera.MARGIN
        if rect[0] >= m and rect[1] >= 150 + m and rect[0] + w <= 1080 - m and rect[1] + h <= 150 + 1154 - m:
            assert x >= m - 1e-6 and x + ww <= 1080 - m + 1e-6 and y >= 150 + m - 1e-6 and y + hh <= 150 + 1154 - m + 1e-6, (rect, f)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} camera tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL CAMERA TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
