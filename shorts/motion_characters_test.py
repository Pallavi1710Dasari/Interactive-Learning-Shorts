"""
The optional animated characters of motion reels (shorts/motion_characters.py,
shorts/motion_character_presets.py; web/src/motion/characters is the copied
rig, web/src/motion/cast ours).

Covers:
  - presets: every language has a default wearing its signature colour, plus
    the shared host; the files are ours (outside the copied rig); validation
    rejects what the rig cannot draw; save / reset round-trip in a temp file;
    the player's export is current; the designer's API saves, rejects and
    resets;
  - characters = speakers: two on every two-speaker theme (host left
    asking, the language's character right), one narrator on a one-narrator
    reel, never more than there are speakers;
  - per shot: never on a full-frame card, and a narrator only where the
    objects fit above the characters' region (laid out there);
  - the director: cues land on spoken words, gestures spaced and facing the
    other speaker, deterministic;
  - motion_reel --characters / --character <preset> write the plan with the
    preset's config embedded, and leave the switches as they found them;
  - the imported source is recorded.
The player side (purity, lip-sync, the rig's names, regions) is in
web/src/motion/motion.test.tsx.

Stub mode only; every run writes to a temp folder.

    SHORTS_STUB=1 python -m shorts.motion_characters_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
import json
import re
import tempfile
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()   # a temp output/, never the real one

_SAVED = Path(tempfile.mkdtemp(prefix="presets-")) / "saved.yaml"
os.environ["MOTION_CHARACTER_PRESETS_SAVED"] = str(_SAVED)   # never the real saved file

from shorts import config, motion_characters as mc, motion_character_presets as mcp
from shorts import motion_library as lib, motion_reel, motion_scenes as ms, motion_timeline as mtl
from shorts.motion_identities import identity, languages
from shorts.schema import MotionPlan, MotionScript

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "evals" / "fixtures" / "motion"
CHARS = ROOT / "web" / "src" / "motion" / "characters"
TWO = {"usestate_interview_golden": "interview", "usestate_peer_discussion_golden": "peer_discussion",
       "tlb_mentor_student_golden": "mentor_student", "css_interview_golden": "interview",
       "java_interview_golden": "interview"}
ONE = ("usestate_golden", "tlb_golden", "tokenization_golden", "hash_table_golden", "usestate_bug_hunt_golden")


def _script(name: str) -> MotionScript:
    return ms.with_default_scenes(MotionScript(**json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))))


def _plan(name: str, characters: bool, character: str | None = None, script: MotionScript | None = None) -> MotionPlan:
    script = script or _script(name)
    clocks = mtl.shot_timings(script)
    return mtl.build_plan(script, clocks, cast=motion_reel._cast(script), characters=characters, character=character)


def _clean():
    if _SAVED.exists():
        _SAVED.unlink()


# ================================================================ presets

def test_every_language_has_a_default_preset_in_its_signature_colour():
    d = mcp.defaults()
    assert "host" in d
    for lang in languages():
        assert lang in d, lang
        assert d[lang]["outfit"]["topColor"].upper() == identity(lang).colour.upper(), lang
    assert {"arjun", "riya"} <= set(d)
    names = [d[lang]["name"] for lang in languages()]
    assert len(set(names)) == len(names)


def test_presets_live_outside_the_copied_rig():
    for path in (mcp.DEFAULTS_PATH, mcp.saved_path(), mcp.EXPORT):
        assert CHARS not in Path(path).resolve().parents, path
    assert not list(CHARS.rglob("*preset*.yaml")) and not list(CHARS.rglob("presets.generated.json"))


def test_the_saved_presets_file_is_tracked_by_git():
    """Presets designed on one machine must reach the other: the saved file
    exists in the repo and no .gitignore rule hides it."""
    import subprocess
    real = mcp.ROOT / "motion_character_presets.saved.yaml"
    assert real.exists(), "shorts/motion_character_presets.saved.yaml must exist (it is committed, even when empty)"
    for path in (real, mcp.DEFAULTS_PATH, mcp.EXPORT):
        r = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, capture_output=True)
        assert r.returncode == 1, f"{path} is ignored by git"


def test_a_preset_the_rig_cannot_draw_is_refused():
    good = mcp.defaults()["java"]
    bad = [
        {**good, "outfit": {**good["outfit"], "top": "cape"}},
        {**good, "hair": {**good["hair"], "color": "green"}},
        {**good, "skinTone": "#12345"},
        {**good, "build": {"height": 1.4, "shoulders": 1}},
        {**good, "accessories": {"hat": True}},
        {**good, "wings": True},
    ]
    for cfg in bad:
        try:
            mcp.CharacterConfig(**cfg)
        except ValueError:
            continue
        raise AssertionError(f"accepted {cfg}")
    mcp.CharacterConfig(**{**good, "skinTone": "#C68642", "hair": {"style": "bob", "color": "#704214"}})


def test_save_and_reset_round_trip_in_their_own_file():
    _clean()
    assert mcp.saved() == {} and not mcp.is_saved("java")
    cfg = {**mcp.defaults()["java"], "hair": {"style": "curly", "color": "grey"}}
    mcp.save("java", cfg)
    assert mcp.is_saved("java") and mcp.preset("java")["hair"] == {"style": "curly", "color": "grey"}
    assert mcp.preset("react") == mcp.defaults()["react"]
    assert "motion_character_presets.yaml" not in str(_SAVED)
    back = mcp.reset("java")
    assert back == mcp.defaults()["java"] == mcp.preset("java") and not mcp.is_saved("java")
    try:
        mcp.save("klingon", cfg)
        raise AssertionError("saved an unknown preset")
    except KeyError:
        pass
    _clean()


def test_the_player_export_is_current():
    assert json.loads(mcp.EXPORT.read_text(encoding="utf-8")) == json.loads(mcp.export_json()), \
        "run: python -m shorts.motion_character_presets export"


def test_the_designer_api_saves_rejects_and_resets():
    from fastapi.testclient import TestClient
    from shorts.server import app
    _clean()
    with TestClient(app) as client:
        r = client.get("/api/motion-characters/presets").json()
        assert set(r["defaults"]) == set(mcp.ids()) and r["saved"] == {} and r["options"]["top"]
        cfg = {**r["effective"]["python"], "accessories": {"glasses": "rect", "earrings": True}}
        ok = client.put("/api/motion-characters/presets/python", json=cfg)
        assert ok.status_code == 200 and ok.json()["saved"]
        assert client.get("/api/motion-characters/presets").json()["effective"]["python"]["accessories"]["glasses"] == "rect"
        assert client.put("/api/motion-characters/presets/python", json={"name": "x"}).status_code == 422
        assert client.put("/api/motion-characters/presets/nobody", json=cfg).status_code == 404
        back = client.delete("/api/motion-characters/presets/python").json()
        assert back["config"] == mcp.defaults()["python"]
        assert client.get("/api/motion-characters/presets").json()["saved"] == {}
    _clean()


# ============================================= as many characters as speakers

def test_the_switch_is_off_by_default():
    if "MOTION_CHARACTERS" not in os.environ:
        assert config.MOTION_CHARACTERS is False and config.MOTION_CHARACTER_PRESET is None
    for name in [*TWO, *ONE]:
        p = _plan(name, characters=False)
        assert p.characters == [] and not any(s.characters for s in p.shots), name


def test_two_speakers_get_the_host_and_their_language_character():
    for name, theme in TWO.items():
        plan = _plan(name, characters=True)
        script = _script(name)
        assert plan.theme == theme and len(plan.characters) == 2 == len(script.speakers), name
        left, right = plan.characters
        assert (left.preset, left.side) == ("host", "left"), name
        assert (right.preset, right.side) == (script.language, "right"), name
        sides = {m.role: m.side for m in plan.cast}
        assert sides[left.role] == "left" and sides[right.role] == "right"
        assert left.config == mcp.preset("host") and right.config == mcp.preset(script.language)
        assert left.seed != right.seed


def test_one_narrator_gets_one_character():
    for name in ONE:
        script = _script(name)
        plan = _plan(name, characters=True)
        assert not script.speakers
        assert len(plan.characters) == 1, name
        [n] = plan.characters
        assert n.side == "center" and n.role is None, name
        assert n.preset == (script.language if script.language in mcp.ids() else "cs"), name
        assert any(c.kind == "gesture" for c in n.cues), name


def test_never_more_characters_than_speakers():
    for name in [*TWO, *ONE]:
        script = _script(name)
        assert len(_plan(name, characters=True).characters) <= max(1, len(script.speakers)), name
    # characters = speakers: every two-speaker theme gets two, rapid fire included
    from shorts import motion_themes as mt
    two = [k for k, t in mt.registry().themes.items() if len(t.speakers) == 2]
    assert "interview_rapid_fire" in two
    for theme in two:
        script = _script("usestate_interview_golden").model_copy(update={"theme": theme})
        plan = _plan("", characters=True, script=script)
        assert [t.side for t in plan.characters] == ["left", "right"], theme


def test_characters_step_out_of_full_frame_cards_and_crowded_narrator_shots():
    full = {k for k, s in lib.object_kinds().items() if s["layout"] == "full"}
    region = lib.library()["frame"]["characters"]
    upper = lib.library()["frame"]["duo"]
    for name in [*TWO, *ONE]:
        plan = _plan(name, characters=True)
        for s in plan.shots:
            if any(o.kind in full for o in s.objects):
                assert not s.characters, (name, s.id)
            if s.characters:
                for o in s.objects:
                    if o.box and o.box.h:
                        assert o.box.y + o.box.h <= region["top"], (name, s.id, o.kind)
            elif name in TWO:
                assert any(o.kind in full for o in s.objects), (name, s.id)
        shown = [s for s in plan.shots if s.characters]
        assert shown, name
        if name in ONE:          # a narrator shows only where its objects fit the upper region
            for s in plan.shots:
                if not any(o.kind in full for o in s.objects):
                    fits = ms.stack_height(next(x.scene for x in _script(name).shots if x.id == s.id)) \
                        <= upper["bottom"] - upper["top"]
                    assert s.characters == fits, (name, s.id)


# =============================================================== the director

def test_every_cue_lands_on_a_spoken_word_at_its_time():
    v = mc.vocabulary()
    leads = {v["lead"]["hands"], v["lead"]["head"], 0.0, 0.1}
    for name in [*TWO, *ONE]:
        plan = _plan(name, characters=True)
        words = [w for s in plan.shots for c in s.captions for w in c.words]
        for track in plan.characters:
            for cue in track.cues:
                if cue.t == 0.0 and cue.kind == "expression":
                    continue                                    # the opening face
                hits = [w for w in words if w.text == cue.cue]
                assert hits, (name, cue)
                assert any(abs(cue.t - (w.start - lead)) < 1e-3 or (cue.t == 0.0 and w.start - lead <= 0)
                           for w in hits for lead in leads), (name, cue)


def test_the_director_only_names_gestures_in_its_vocabulary():
    v = mc.vocabulary()
    g = v["gestures"]
    allowed = ({n for n in g["explain"] if n != "presentToward"} | set(v["present"].values())
               | set(v["narrator_explain"])
               | {g["why"], g["how"], g["yes"], g["no"], g["agree"], g["end"]} | set(g["count"].values()))
    faces = set(v["expressions"].values())
    for name in [*TWO, *ONE]:
        for track in _plan(name, characters=True).characters:
            for cue in track.cues:
                assert cue.name in (allowed if cue.kind == "gesture" else faces), (name, cue)


def test_gestures_are_spaced_and_every_character_moves():
    gap = mc.vocabulary()["min_gap"]
    end = mc.vocabulary()["gestures"]["end"]
    for name in [*TWO, *ONE]:
        plan = _plan(name, characters=True)
        for track in plan.characters:
            ts = [c.t for c in track.cues if c.kind == "gesture" and c.name != end]
            assert len(ts) >= 3, (name, track.side, ts)
            assert all(b - a >= gap - 1e-6 for a, b in zip(ts, ts[1:])), (name, track.side, ts)


def test_gestures_face_the_other_speaker():
    mirror = set(mc.vocabulary()["mirror_on_right"])
    for name in TWO:
        for track in _plan(name, characters=True).characters:
            for cue in track.cues:
                if cue.kind == "gesture" and cue.name in mirror:
                    assert cue.side == ("R" if track.side == "right" else None), (name, track.side, cue)
                if cue.name.startswith("present"):
                    assert cue.name == ("presentRight" if track.side == "left" else "presentLeft"), (name, cue)


def test_the_director_is_deterministic():
    for name in [*TWO, *ONE]:
        a = _plan(name, characters=True).model_dump()["characters"]
        b = _plan(name, characters=True).model_dump()["characters"]
        assert a == b


def test_a_plan_keeps_the_character_it_was_made_with():
    _clean()
    before = _plan("java_interview_golden", characters=True)
    mcp.save("java", {**mcp.defaults()["java"], "hair": {"style": "bob", "color": "grey"}})
    after = _plan("java_interview_golden", characters=True)
    assert before.characters[1].config["hair"]["style"] == "sidePart"      # unchanged data
    assert after.characters[1].config["hair"] == {"style": "bob", "color": "grey"}   # new reels use the save
    mcp.reset("java")
    _clean()


def test_characters_have_their_own_region():
    f = lib.library()["frame"]
    c = f["characters"]
    assert f["duo"]["bottom"] <= c["top"] < c["bottom"] < c["chat_top"] < f["chat"]["bottom"]
    assert f["chat"]["bottom"] - c["chat_top"] >= 34 + 44 + 4 * 54      # the longest caption (4 lines)
    assert c["cx"][0] < c["center_x"] == f["w"] / 2 < c["cx"][1]
    assert c["bottom"] < round(f["h"] * 0.70)


# ===================================================================== runner

def _run(*extra: str, doc: str = "react_usestate_basics.md") -> tuple[int, str, MotionPlan | None]:
    buf = io.StringIO()
    before = set(Path(config.OUTPUT_DIR).glob("*/plan.json"))
    with contextlib.redirect_stdout(buf):
        code = motion_reel.main([str(ROOT / "content" / doc), "--yes", *extra])
    new = set(Path(config.OUTPUT_DIR).glob("*/plan.json")) - before
    plans = sorted(new or Path(config.OUTPUT_DIR).glob("*/plan.json"), key=lambda p: p.stat().st_mtime)
    plan = MotionPlan.model_validate_json(plans[-1].read_text(encoding="utf-8")) if plans and code == 0 else None
    return code, buf.getvalue(), plan


def test_the_runner_flags_write_characters_and_restore_the_switches():
    before = (config.MOTION_CHARACTERS, config.MOTION_CHARACTER_PRESET)
    code, out, plan = _run("--theme", "interview", "--characters")
    assert code == 0, out[-1500:]
    assert [t.preset for t in plan.characters] == ["host", "react"]
    assert "characters: Arjun (host) as INTERVIEWER" in out
    assert (config.MOTION_CHARACTERS, config.MOTION_CHARACTER_PRESET) == before

    code, out, plan = _run("--theme", "interview", "--force-stage", "timing", "--character", "riya")
    assert code == 0, out[-1500:]
    assert [t.preset for t in plan.characters] == ["host", "riya"]           # --character implies --characters
    assert plan.characters[1].config == mcp.preset("riya")
    assert (config.MOTION_CHARACTERS, config.MOTION_CHARACTER_PRESET) == before

    code, out, _ = _run("--theme", "interview", "--character", "klingon")
    assert code == 2 and "no character preset 'klingon'" in out


def test_the_imported_source_is_recorded():
    src = (CHARS / "SOURCE.md").read_text(encoding="utf-8")
    assert re.search(r"\b[0-9a-f]{40}\b", src), "commit hash"
    for needle in ("lab/characters", "slide-kit/characters-lab", "jeevansravanth", "Web-Slides"):
        assert needle in src, needle
    assert sorted(p.name for p in CHARS.iterdir() if p.is_dir()) == ["actions", "rig", "skins"]
    assert (CHARS / "rig" / "Actor.tsx").exists()
    for left_out in ("playground", "shoot.mjs", "record.mjs", "App.tsx"):
        assert not list(CHARS.rglob(left_out)), left_out
    # our code is not in the copied folder
    assert not [p for p in CHARS.glob("*.ts*")]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} motion character tests")
    try:
        for t in tests:
            print(f"- {t.__name__}")
            t()
    finally:
        _clean()
    print("\nALL MOTION CHARACTER TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
