"""
The six new themes and seven new teaching approaches (2026-10-13, review of
job f64077e78448): each one exists everywhere the old ones do, so the AI
recommends them in the UI the same way.

  - the 7 approaches: the schema, the AI's choice prompt, the reviewer's
    one-line choices, the script and visual-strategy guidance, the stub and
    the web picker;
  - the 6 themes: in the registry with their description, fit, speakers,
    template, hook and tag.

    SHORTS_STUB=1 python -m shorts.motion_new_themes_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from pathlib import Path
from typing import get_args

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_themes
from shorts.schema import TeachingApproachKind

ROOT = Path(__file__).resolve().parent.parent
NEW_APPROACHES = ["predict_then_reveal", "misconception_repair", "build_from_zero", "worked_example_then_try",
                  "socratic_questions", "big_picture_then_zoom", "step_by_step_trace"]
NEW_THEMES = ["live_code_along", "doubt_clinic", "whiteboard_sketch", "pause_and_predict", "error_decoder", "this_or_that"]


def test_the_new_approaches_exist_everywhere():
    kinds = get_args(TeachingApproachKind)
    assert len(kinds) == 14 and all(a in kinds for a in NEW_APPROACHES)
    from shorts.skills import script, strategy, teaching_approach
    from shorts import motion_jobs, stubs
    prompt = teaching_approach._APPROACH_KINDS_AND_RULES + teaching_approach._APPROACH_JSON_INSTRUCTION
    for a in kinds:
        assert a in prompt, a
        assert a in motion_jobs.APPROACHES, a
        assert a in script._APPROACH_GUIDANCE, a
        assert a in strategy._VISUAL_APPROACH_GUIDANCE, a
        assert a in stubs._STUB_APPROACH_SHAPE, a
    web = (ROOT / "web/src/types.ts").read_text()
    assert all(f'"{a}"' in web for a in kinds)


def test_the_new_themes_are_registered_with_their_fields():
    reg = motion_themes.registry()
    for tid in NEW_THEMES:
        t = reg.get(tid)
        assert t is not None, tid
        assert t.description and t.suits and t.works_with and t.tag and t.hook.brief, tid
    assert len(reg.get("doubt_clinic").speakers) == 2
    assert reg.get("live_code_along").template == "walkthrough" and reg.get("live_code_along").needs_code


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} new theme and approach tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL NEW THEME AND APPROACH TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
