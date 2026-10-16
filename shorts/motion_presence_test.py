"""
The presenters come and go (rev 4, motion_teach.avatar_presence,
library.json avatars):

  - on for the hook, the main idea, the aha, the recap and the end card;
    off while code, a code map, a flow or a panel needs the whole frame;
  - a visual-heavy shot is off even when its scene asks for them, and its
    visual is laid out at full size, never for the board;
  - the scene's own choice wins on any other shot;
  - every on or off run lasts at least min_on / min_off seconds;
  - the shots on the board are laid out against its right edge, nearest the
    mentor's pointing hand; wide objects keep their width;
  - motion_avatar_presence passes on the result and fails a broken one.

    SHORTS_STUB=1 python -m shorts.motion_presence_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_plan_checks, motion_teach
from shorts.motion_camera_test import _plan
from shorts.motion_scenes import BOARD_RIGHT_PAD, BOARD_RIGHT_W, INSET_W
from shorts.motion_timeline import PLAN_REV

ROOT = Path(__file__).resolve().parent.parent


def _staged(plan=None):
    return motion_teach.stage_board(plan or _plan())


def _pattern(plan) -> dict:
    return {s.beat: s.characters for s in plan.shots}


def test_on_at_the_key_beats_off_where_the_visual_needs_the_frame():
    plan = _staged()
    assert plan.rev == PLAN_REV >= 4
    on = _pattern(plan)
    for beat in ("hook", "fix_idea", "payoff", "recap", "cta"):
        assert on[beat], (beat, on)
    for beat in ("title", "setup", "fix_flow", "code_map"):
        assert not on[beat], (beat, on)
    for s in plan.shots:
        if motion_teach.heavy(s):
            assert not s.characters, s.id


def test_a_heavy_shot_stays_off_even_when_its_scene_asks():
    base = _plan()
    shots = [s.model_copy(update={"avatars": "on"}) if s.beat == "code_map" else s for s in base.shots]
    plan = _staged(base.model_copy(update={"shots": shots}))
    assert not _pattern(plan)["code_map"]


def test_the_scenes_choice_wins_elsewhere():
    base = _plan()
    shots = [s.model_copy(update={"avatars": "off"}) if s.beat == "fix_idea" else s for s in base.shots]
    assert not _pattern(_staged(base.model_copy(update={"shots": shots})))["fix_idea"]


def test_every_run_lasts_long_enough():
    base = _plan()
    # a 1-second main idea between two off shots: too short to come on for
    shots = []
    for s in base.shots:
        if s.beat == "fix_idea":
            s = s.model_copy(update={"end": s.start + 1.0})
        shots.append(s)
    plan = _staged(base.model_copy(update={"shots": shots}))
    assert not _pattern(plan)["fix_idea"]
    r = motion_teach.rules()
    runs, a = [], 0
    for i in range(1, len(plan.shots) + 1):
        if i == len(plan.shots) or plan.shots[i].characters != plan.shots[a].characters:
            runs.append(plan.shots[i - 1].end - plan.shots[a].start)
            a = i
    assert min(runs) >= min(r["min_on"], r["min_off"]), runs


def test_board_shots_sit_against_the_mentors_side():
    plan = _staged()
    for s in plan.shots:
        if s.arrangement != "board_right":
            continue
        assert s.characters
        for o in s.objects:
            if o.box and o.box.w:
                assert o.box.w in (BOARD_RIGHT_W, INSET_W), (s.id, o.id, o.box.w)
                # against the right edge, less the margin that keeps a corner badge on the board
                assert abs(o.box.x + o.box.w - (1020 - BOARD_RIGHT_PAD)) < 1, (s.id, o.id, o.box)
    assert any(s.arrangement == "board_right" for s in plan.shots)


def test_the_presence_check_passes_and_catches_a_shrunk_visual():
    plan = _staged()
    r = motion_plan_checks.check_avatar_presence(plan)
    assert r.passed, r.reason
    bad = plan.model_copy(update={"shots": [s.model_copy(update={"characters": True}) if s.beat == "code_map" else s
                                            for s in plan.shots]})
    r = motion_plan_checks.check_avatar_presence(bad)
    assert not r.passed and "shrunk" in r.reason, r.reason
    bad = plan.model_copy(update={"shots": [s.model_copy(update={"characters": False}) if s.beat == "recap" else s
                                            for s in plan.shots]})
    r = motion_plan_checks.check_avatar_presence(bad)
    assert not r.passed and "recap" in r.reason, r.reason


def test_older_plans_are_not_checked():
    plan = _staged().model_copy(update={"rev": 3})
    assert "not checked" in motion_plan_checks.check_avatar_presence(plan).reason


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} presenter on/off tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL PRESENTER ON/OFF TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
