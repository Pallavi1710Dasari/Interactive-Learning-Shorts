"""
Characters that teach (shorts/motion_teach.py), on the real reel of job
f64077e78448 (fixtures evals/fixtures/motion/variable_points_to_value_*):

  - board staging: characters on every shot but the title and the CTA, the
    explainer the one on the right;
  - the explainer points at what changes on the board, counts "two things /
    first / then" with a HELD count (the hand stays up between counts), and
    the asker has its "aha" on "So the variable just points to it";
  - the voice envelope is zero outside a speaker's lines and follows the
    loudness inside them;
  - on the board the caption layout check still passes, and fails a bubble
    pushed onto a character.

    SHORTS_STUB=1 python -m shorts.motion_teach_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from pathlib import Path

import numpy as np

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_library as lib, motion_plan_checks, motion_teach
from shorts.motion_camera_test import _plan

ROOT = Path(__file__).resolve().parent.parent


def _staged():
    return motion_teach.stage_board(_plan())


def test_characters_stay_on_every_explanation_shot():
    plan = _staged()
    assert plan.stage == "board"
    on = {s.id: s.characters for s in plan.shots}
    assert all(v for k, v in on.items() if k not in ("s02", "s10")) and not on["s02"] and not on["s10"], on


def test_the_explainer_points_counts_and_the_asker_gets_it():
    plan = _staged()
    mentor = next(t for t in plan.characters if t.role == "MENTOR")
    student = next(t for t in plan.characters if t.role == "STUDENT")
    assert mentor.side == "right"
    aims = [c for c in mentor.cues if c.kind == "aim"]
    assert aims and all(c.rect and c.until > c.t for c in aims)
    assert any(c.target == "o1" and 25.5 <= c.t <= 26.5 for c in aims), [(c.t, c.target) for c in aims]
    counts = [(c.name, round(c.t, 2)) for c in mentor.cues if c.kind == "count"]
    assert [n for n, _ in counts] == ["two", "one", "two"], counts
    held = [c for c in mentor.cues if c.kind == "count"]
    # a count held into the next one keeps the arm up (no wind-up through a sideways pose)
    assert held[0].until >= held[1].t, (held[0].until, held[1].t)
    assert any(c.kind == "aha" and 37.5 <= c.t <= 38.5 for c in student.cues)
    assert any(c.kind == "gesture" and c.name == "thumbsUp" for c in mentor.cues)
    names = {c.name for t in plan.characters for c in t.cues if c.kind == "gesture"}
    assert names <= motion_teach.GESTURES, names - motion_teach.GESTURES


def test_the_voice_envelope_follows_the_lines():
    rate = 16000
    t = np.arange(0, 3.0, 1 / rate)
    loud = np.where((t > 0.5) & (t < 1.5), 0.5 * np.sin(2 * np.pi * 180 * t), 0.0)
    env = motion_teach.envelope(loud.astype(np.float32), rate, [(0.4, 1.6), (2.0, 2.6)])
    v = env["v"]
    at = lambda s: v[int(round((s - env["t0"]) * env["fps"]))]
    assert at(1.0) > 0.6 and at(1.8) == 0 and at(2.3) < 0.1, (at(1.0), at(1.8), at(2.3))


def test_the_board_layout_check():
    plan = _staged()
    r = motion_plan_checks.check_caption_layout(plan)
    assert r.passed, r.reason
    # a caption zone pushed up onto the characters fails
    board = lib.library()["frame"]["board"]
    old = board["chat"]["top"]
    try:
        board["chat"]["top"] = 1000
        r = motion_plan_checks.check_caption_layout(plan)
        assert not r.passed and "character" in r.reason, r.reason
    finally:
        board["chat"]["top"] = old


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} teaching tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL TEACHING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
