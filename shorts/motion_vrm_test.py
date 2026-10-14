"""
3D VRM avatars (web/src/motion/vrm) on the plan side:

  - MOTION_AVATARS=vrm draws the characters as VRM avatars: the explainer
    wears assets/avatars/mentor.vrm, the asker student.vrm; the default (rig)
    and every older plan keep the 2D characters;
  - the 3D canvases end above the chat band: the caption layout check passes
    with them and fails a canvas pushed onto the captions;
  - the avatar files are VRM 1.0 whose licence allows commercial use;
  - the director stays professional: a light smile at most, never a grin.

    SHORTS_STUB=1 python -m shorts.motion_vrm_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
import struct
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_library as lib, motion_plan_checks, motion_teach
from shorts.motion_camera_test import _plan

ROOT = Path(__file__).resolve().parent.parent


def _vrm_meta(path: Path) -> dict:
    b = path.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n])["extensions"]["VRMC_vrm"]


def test_the_default_is_still_the_2d_rig_and_old_plans_keep_it():
    assert config.MOTION_AVATARS == "rig"
    plan = motion_teach.stage_board(_plan())
    assert plan.avatars is None and all(t.vrm is None for t in plan.characters)


def test_vrm_avatars_wear_the_mentor_and_student_files():
    plan = motion_teach.with_vrm(motion_teach.stage_board(_plan()))
    assert plan.avatars == "vrm"
    assert {t.role: t.vrm for t in plan.characters} == {"STUDENT": "student", "MENTOR": "mentor"}


def test_the_3d_canvases_stay_above_the_captions():
    plan = motion_teach.with_vrm(motion_teach.stage_board(_plan()))
    r = motion_plan_checks.check_caption_layout(plan)
    assert r.passed, r.reason
    vrm = lib.library()["frame"]["board"]["vrm"]
    chat_top = lib.library()["frame"]["board"]["chat"]["top"]
    for k, b in vrm.items():
        if not k.startswith("_"):
            assert b["y"] + b["h"] <= chat_top, (k, b)
    old = vrm["asker"]["h"]
    try:
        vrm["asker"]["h"] = 700                    # pushed down onto the chat band
        bad = motion_plan_checks.check_caption_layout(plan)
        assert not bad.passed and "avatar" in bad.reason, bad.reason
    finally:
        vrm["asker"]["h"] = old


def test_the_avatar_files_allow_commercial_use():
    for name in ("mentor", "student"):
        p = ROOT / "assets" / "avatars" / f"{name}.vrm"
        assert p.exists(), p
        meta = _vrm_meta(p)
        assert meta["specVersion"] == "1.0", meta.get("specVersion")
        assert meta["meta"]["commercialUsage"] in ("corporation", "personalProfit"), meta["meta"]["commercialUsage"]


def test_the_director_never_grins():
    plan = motion_teach.stage_board(_plan())
    names = {c.name for t in plan.characters for c in t.cues if c.kind == "expression"}
    assert not names & {"grin", "laugh", "excited"}, names


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} 3D avatar tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL 3D AVATAR TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
