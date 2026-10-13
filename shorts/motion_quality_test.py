"""
Motion reel quality fixes (2026-10-12):

  layout     a stamp marks its object without covering its words; characters
             only stand where the objects fit above them (two-speaker reels
             too); the audit covers every scene type in every context;
  pacing     each voiced clip is cut to its speech (no dead air);
  warning    the invented-example warning reads code, not comments;
  language   reading level about grade 7; technical terms explained when
             first said;
  scenes     no two shots in a row with the same main objects, no kind on
             more than 3 shots, each shot shows what it says.

    SHORTS_STUB=1 python -m shorts.motion_quality_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import checks, motion_audit, motion_timeline
from shorts.motion_scenes import default_scenes, layout_scene
from shorts.schema import CaptionChunk, MotionScene, MotionSceneObject, MotionScript

ROOT = Path(__file__).resolve().parent.parent
GOLDENS = sorted((ROOT / "evals/fixtures/motion").glob("*_golden.json"))


def _golden(name: str) -> MotionScript:
    d = json.loads((ROOT / "evals/fixtures/motion" / name).read_text())
    d.pop("_comment", None)
    return MotionScript(**d)


def _with_speech(script: MotionScript, sid: str, speech: str) -> MotionScript:
    sentences = checks._sentences(speech)
    return script.model_copy(update={"shots": [
        s.model_copy(update={"speech": speech, "captions": [CaptionChunk(text=x) for x in sentences]})
        if s.id == sid else s for s in script.shots]})


# ===================================================================== layout

def test_a_stamp_sits_in_its_objects_empty_right_half():
    scene = MotionScene(objects=[
        MotionSceneObject(id="o1", kind="entity_card", props={"label": "<Counter />", "value": "0"}),
        MotionSceneObject(id="o2", kind="stamp", props={"text": "BUG"})])
    card, stamp = layout_scene(scene, duo=False)
    assert stamp.box.x > card.box.x + card.box.w * 0.6           # right of the label and value
    assert card.box.y < stamp.box.y < card.box.y + card.box.h


def test_characters_step_aside_when_the_objects_do_not_fit():
    """A two-speaker reel used to draw both characters under a panel."""
    idx = motion_audit.build()
    shown = {r["scene"]: r["characters"] for r in idx["contexts"]["duo_characters"]}
    assert shown["entity_to_panel"] is False and shown["hook"] is False
    assert shown["code_window"] is True and shown["token_row"] is True


def test_the_audit_covers_every_object_kind():
    lib = json.loads((ROOT / "web/src/motion/library.json").read_text())
    used = {o.kind for s in motion_audit.SCENES for o in s[3]}
    assert used == set(lib["objects"]), set(lib["objects"]) - used


# ===================================================================== pacing

def test_clips_are_cut_to_their_speech():
    secs = {"s01": [3.6, 2.0]}
    times = {"s01": [[(0.35, 0.8), (0.9, 3.2)], [(0.3, 1.6)]]}
    srcs = {"s01": ["forced_alignment", "even"]}
    s, t, cuts = motion_timeline.trim_to_speech(secs, times, srcs)
    a, b = cuts["s01"][0]
    assert a == round(0.35 - motion_timeline.TRIM_PAD_IN, 3) and b == round(3.2 + motion_timeline.TRIM_PAD_OUT, 3)
    assert s["s01"][0] == round(b - a, 3) and t["s01"][0][0][0] == round(0.35 - a, 3)
    assert cuts["s01"][1] == (0.0, 2.0) and s["s01"][1] == 2.0      # an even clip is left whole


# ==================================================================== warning

def test_comment_and_string_words_are_not_code_names():
    assert checks._code_names("count = count + 1; // no re-render asked") == ["count", "count"]
    assert checks._code_names("print('asked politely')") == ["print"]
    assert "header" in checks._code_names("#header .title { color: red }")
    script = _golden("usestate_golden.json")
    shots = [s.model_copy(update={"code": ["likes = likes + 1; // nobody asked"]}) if s.id == "s03" else s
             for s in script.shots]
    names = checks._example_names(script.model_copy(update={"shots": shots}))
    assert "asked" not in names and "nobody" not in names


# =================================================================== language

def test_every_golden_reads_simply_and_explains_its_terms():
    for f in GOLDENS:
        s = _golden(f.name)
        for r in (checks.check_motion_reading_level(s), checks.check_motion_terms_explained(s)):
            assert r.passed, (f.name, r.reason)


def test_an_unexplained_term_fails_and_its_meaning_is_suggested():
    s = _with_speech(_golden("usestate_golden.json"), "s04",
                     "On every re-render the counter resets. That is the problem.")
    r = checks.check_motion_terms_explained(s)
    assert not r.passed and "'render'" in r.reason and "draw the screen again" in r.reason, r.reason


def test_a_term_explained_in_other_words_passes():
    s = _with_speech(_golden("usestate_golden.json"), "s04",
                     "On every re-render, React runs your component function again from the top.")
    assert checks.check_motion_terms_explained(s).passed


def test_a_long_hard_sentence_fails_the_reading_level():
    s = _with_speech(_golden("usestate_golden.json"), "s05",
                     "Consequently, reconciliation necessitates comprehensive evaluation of hierarchical "
                     "dependencies throughout the application.")
    r = checks.check_motion_reading_level(s)
    assert not r.passed and "s05" in r.reason


def test_the_writer_is_told_the_terms_its_material_uses():
    from shorts.parse import find_section, parse_markdown
    from shorts.schema import Topic
    from shorts.skills.script import _motion_material_block
    sec = find_section(parse_markdown(str(ROOT / "content/react_usestate_basics.md")), "7.1")
    topic = Topic(id="t", topic="?", why_it_matters="x", source_section_id="7.1", difficulty="medium")
    block = _motion_material_block(topic, sec, None, sec.text, None, "@x", "")
    assert "TECHNICAL TERMS" in block and "render:" in block and "component:" in block


# ===================================================================== scenes

def _scened(name: str) -> MotionScript:
    s = _golden(name)
    return s.model_copy(update={"shots": [x.model_copy(update={"scene": sc})
                                          for x, sc in zip(s.shots, default_scenes(s))]})


def test_every_golden_default_scene_set_passes_every_scene_grader():
    for f in GOLDENS:
        bad = [r for r in checks.run_motion_scene_graders(_scened(f.name)) if not r.passed]
        assert not bad, (f.name, [r.reason for r in bad])


def test_two_shots_in_a_row_with_the_same_objects_fail():
    s = _scened("usestate_golden.json")
    shots = list(s.shots)
    shots[4] = shots[4].model_copy(update={"scene": shots[3].scene})      # break_2 = break_1
    r = checks.check_motion_scene_variety(s.model_copy(update={"shots": shots}))
    assert not r.passed and "show the same objects" in r.reason, r.reason


def test_one_kind_on_too_many_shots_fails():
    s = _scened("usestate_golden.json")
    card = MotionScene(objects=[MotionSceneObject(id="o1", kind="entity_card",
                                                  props={"label": "likes", "value": "0"})])
    other = MotionScene(objects=[MotionSceneObject(id="o1", kind="callout",
                                                   props={"label": "likes", "text": "likes"})])
    shots = [x.model_copy(update={"scene": card if i % 2 else other}) if 2 <= i <= 9 else x
             for i, x in enumerate(s.shots)]
    r = checks.check_motion_scene_variety(s.model_copy(update={"shots": shots}))
    assert not r.passed and "entity_card is the main object on 4 shots" in r.reason, r.reason


def test_a_shot_showing_something_it_never_says_fails():
    s = _scened("usestate_golden.json")
    odd = MotionScene(objects=[MotionSceneObject(id="o1", kind="token_row",
                                                 props={"items": ["database", "index"]})])
    shots = [x.model_copy(update={"scene": odd}) if x.id == "s05" else x for x in s.shots]
    r = checks.check_motion_scene_matches_narration(s.model_copy(update={"shots": shots}))
    assert not r.passed and "s05" in r.reason


def test_the_real_reels_scenes_are_flagged_for_repetition():
    """plain_variable_no_rerender__motion's scenes put an entity_card on 7 of
    11 shots — the clumsy repetition the user saw."""
    f = ROOT / "output/plain_variable_no_rerender__motion.motion.json"
    if not f.exists():
        return
    s = MotionScript.model_validate_json(f.read_text())
    r = checks.check_motion_scene_variety(s)
    assert not r.passed and "entity_card" in r.reason


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} motion quality tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL MOTION QUALITY TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
