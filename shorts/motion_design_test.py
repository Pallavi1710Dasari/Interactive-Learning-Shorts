"""
The studio design (2026-10-13, review of job f64077e78448):

  - a new reel is drawn in the studio design (rev 3) with its theme's palette;
    Midnight Lab keeps its own palette; a classic reel has none;
  - every palette keeps the fixed meanings wrong / right / highlight;
  - each shot gets an arrangement and motion_layout_variety fails a reel that
    repeats one layout.

    SHORTS_STUB=1 python -m shorts.motion_design_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_library as lib, motion_plan_checks, motion_themes
from shorts.motion_camera_test import _plan
from shorts.motion_timeline import PLAN_REV, palette_for

ROOT = Path(__file__).resolve().parent.parent


def test_new_reels_are_studio_with_their_themes_palette():
    assert config.MOTION_DESIGN == "studio" and "studio" in config.MOTION_DESIGNS
    assert PLAN_REV == 3
    assert palette_for("mentor_student", "studio") == "chalkboard"
    assert palette_for("interview", "studio") == "deep_teal"
    assert palette_for("myth_vs_fact", "studio") == "plum_gold"
    assert palette_for("bug_hunt", "studio") == "terminal_amber"
    assert palette_for("classic_explainer", "studio") == "paper"
    assert palette_for("mentor_student", "midnight_lab") == "midnight"
    assert palette_for("mentor_student", "classic") is None
    plan = _plan()
    assert plan.rev == 3 and plan.palette == "midnight"      # the fixture's reel was set up in Midnight Lab


def test_every_palette_keeps_the_fixed_meanings():
    st = lib.library()["studio"]
    assert set(st["palettes"]) == {"chalkboard", "paper", "terminal_amber", "deep_teal", "plum_gold", "midnight"}
    for pid, p in st["palettes"].items():
        assert (p["wrong"], p["right"], p["highlight"]) == ("#E5484D", "#2BB673", "#FFD43B"), pid
        assert len(p["notes"]) == 3, pid
    for theme, pid in st["palette_for_theme"].items():
        assert pid in st["palettes"], (theme, pid)
        assert theme in motion_themes.registry().ids(), theme
    assert all(t in st["palette_for_theme"] for t in motion_themes.registry().ids())


def test_layouts_vary_and_the_check_catches_repeats():
    plan = _plan()
    names = [s.arrangement for s in plan.shots]
    assert all(names), names
    r = motion_plan_checks.check_layout_variety(plan)
    assert r.passed, r.reason
    same = plan.model_copy(update={"shots": [s.model_copy(update={"arrangement": "column"}) for s in plan.shots]})
    bad = motion_plan_checks.check_layout_variety(same)
    assert not bad.passed and "40 %" in bad.reason and "all use the column layout" in bad.reason, bad.reason


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} design tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL DESIGN TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
