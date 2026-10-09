"""
RESTYLE_TO_MOTION_REELS.md phase 3: scenes, timing, avatars and voices.

Covers the scene library contract (web/src/motion/library.json against the
player's renderers), the default beat -> scene mapping on every golden
fixture, the four scene graders and what they reject, word cues, the scenes
call's repair loop and its fallback, per-caption voices (two slots for two
speakers), word timing and its fallbacks, the plan the player plays, the
runner's scenes / voice / timing stages, and the server's plan and audio
endpoints. The graders are also covered case by case in evals/cases.yaml.

No API key, no network, no real LLM or TTS call: stub mode only (the one real
Chatterbox sample is a separate, manual check — see the phase 3 notes).
Every run writes to a temp folder.

    SHORTS_STUB=1 python -m shorts.motion_scene_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import copy
import io
import json
import re
import tempfile
import wave
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()   # a temp output/, never the real one

from shorts import (checks, config, motion_align, motion_library as lib, motion_reel,
                    motion_scenes as ms, motion_themes as mt, motion_timeline as mtl,
                    motion_voice as mv, usage)
from shorts.schema import (MotionPlan, MotionScene, MotionSceneAction, MotionSceneObject,
                           MotionScenesDraft, MotionScript)
from shorts.skills import scenes as scenes_mod

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "evals" / "fixtures" / "motion"
REACT_DOC = ROOT / "content" / "react_usestate_basics.md"
TOKEN_DOC = ROOT / "content" / "tokenization_basics.md"
ALL = ["usestate_golden", "usestate_interview_golden", "usestate_peer_discussion_golden",
       "usestate_bug_hunt_golden", "tlb_golden", "tokenization_golden", "hash_table_golden"]


def _script(name: str) -> MotionScript:
    return MotionScript(**json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


def _scened(name: str) -> MotionScript:
    return ms.with_default_scenes(_script(name))


def _with_scene(script: MotionScript, i: int, scene: MotionScene) -> MotionScript:
    shots = list(script.shots)
    shots[i] = shots[i].model_copy(update={"scene": scene})
    return script.model_copy(update={"shots": shots})


@contextlib.contextmanager
def _temp_output():
    real = config.OUTPUT_DIR
    real_cache = mv.CACHE_DIR
    with tempfile.TemporaryDirectory() as d:
        config.OUTPUT_DIR = Path(d)
        mv.CACHE_DIR = Path(d) / ".motion_audio_cache"
        try:
            yield Path(d)
        finally:
            config.OUTPUT_DIR = real
            mv.CACHE_DIR = real_cache


def _run(*args: str, doc: Path = REACT_DOC) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = motion_reel.main([str(doc), *args])
    return code, buf.getvalue()


# ================================================================== library

def test_every_library_kind_has_a_renderer():
    """library.json is the contract: every object kind it lists is drawn by
    web/src/motion/scene/objects.tsx, and every renderer is in the library."""
    source = (ROOT / "web" / "src" / "motion" / "scene" / "objects.tsx").read_text(encoding="utf-8")
    drawn = set(re.findall(r'case "([a-z_]+)":', source))
    kinds = set(lib.object_kinds())
    assert kinds <= drawn, f"no renderer for {sorted(kinds - drawn)}"
    assert drawn <= kinds, f"renderers for kinds not in the library: {sorted(drawn - kinds)}"
    for kind, spec in lib.object_kinds().items():
        assert spec["layout"] in ("full", "placed", "overlay", "link"), kind
        assert set(spec["actions"]) <= lib.action_kinds(), kind
        if spec["layout"] == "placed" and kind not in ("kinetic_title", "code_window", "lookup_table"):
            assert spec.get("height"), f"{kind} has no height to lay it out with"


def test_avatar_json_matches_the_yaml():
    assert mt.AVATARS_JSON.read_text(encoding="utf-8") == mt.avatars_json(), \
        "web/src/motion/avatars/avatars.generated.json is stale — run " \
        "`python -m shorts.motion_themes export-avatars`"
    reg = mt.avatars()
    vocab = lib.library()["avatar"]
    for a in [reg.host, *reg.characters.values()]:
        assert a.art.body in vocab["bodies"] and a.art.hair in vocab["hair"], a.id
        assert a.palette.primary.upper() not in mt.FIELD_COLOURS, f"{a.id} wears a field colour"


def test_avatar_palette_refuses_a_field_colour():
    try:
        mt.AvatarPalette(primary="#283EE6", secondary="#000000", accent="#FFFFFF", ink="#151936")
    except ValueError as e:
        assert "field colour" in str(e)
    else:
        raise AssertionError("a blue body on the blue field was accepted")


# =========================================================== default scenes

def test_default_scenes_pass_every_scene_grader_on_every_fixture():
    for name in ALL:
        script = _scened(name)
        results = checks.run_motion_scene_graders(script)
        assert checks.all_passed(results), (name, [str(r) for r in results if not r.passed])
        assert all(s.scene and s.scene.objects for s in script.shots), name


def test_default_scenes_are_built_from_the_scripts_own_words():
    """Nothing on screen is invented: every kinetic title, chip, pill and
    label text is taken from the script (captions, highlights, concept,
    promise, takeaways, chapters, code)."""
    for name in ALL:
        script = _scened(name)
        corpus = json.dumps(script.model_dump(exclude={"shots": {"__all__": {"scene"}}})).lower()
        corpus = re.sub(r"<\/?b>", "", corpus)
        stock = {"key takeaways", "it works", "it updates", "follow for more", "the setup",
                 "why it fails", "and also", "the fix", "how it works", "remember", "the code",
                 "how it maps", "follow one example", "items"}
        for s in script.shots:
            for o in s.scene.objects:
                for key in ("text", "label", "title", "promise", "status"):
                    v = o.props.get(key)
                    if isinstance(v, str) and v.lower() not in stock:
                        for word in re.findall(r"[a-z0-9']+", v.lower()):
                            assert word in corpus, (name, s.id, o.kind, key, v, word)
                for item in o.props.get("items", []):
                    assert item.lower() in corpus, (name, s.id, item)


def test_two_speaker_scenes_fit_above_the_avatars():
    script = _scened("usestate_interview_golden")
    f = lib.library()["frame"]
    for s in script.shots:
        for o in ms.layout_scene(s.scene, duo=True):
            if o.box and o.box.h:
                assert o.box.y + o.box.h <= f["duo"]["bottom"] <= f["avatars"]["top"], (s.id, o)


def test_walkthrough_changes_field_per_chapter():
    script = _scened("tokenization_golden")
    fields = {s.chapter: s.scene.field for s in script.shots if s.chapter}
    assert len(set(fields.values())) >= 3, fields
    assert sum(1 for f in fields.values() if f == "yellow") <= 1


# =================================================================== cues

def test_cues_resolve_in_speaking_order():
    shot = _script("usestate_golden").shots[3]   # break_1: "...re-render ... back to zero."
    obj = MotionSceneObject(id="o1", kind="token_row", props={"items": ["re-render", "zero"]})
    acts = [MotionSceneAction(at="re-render", do="enter", target="o1"),
            MotionSceneAction(at="re-render", do="highlight", target="o1", value="1"),
            MotionSceneAction(at="zero", do="highlight", target="o1", value="2")]
    idx = ms.resolve_cues(shot, MotionScene(objects=[obj], actions=acts))
    assert idx[0] is not None and idx[1] == idx[0] and idx[2] > idx[0], idx
    backwards = MotionScene(objects=[obj], actions=list(reversed(acts[1:])))
    assert None in ms.resolve_cues(shot, backwards)      # "re-render" is not after "zero"


# ================================================================= graders

def test_scene_valid_rejects_undrawable_scenes():
    base = _scened("usestate_golden")
    shot = base.shots[3]
    cases = [
        (MotionSceneObject(id="o1", kind="hologram", props={}), "not in the scene library"),
        (MotionSceneObject(id="o1", kind="status_pill", props={"text": "x" * 40, "tone": "bad"}), "max 26"),
        (MotionSceneObject(id="o1", kind="status_pill", props={"text": "ok", "tone": "purple"}), "not a valid tone"),
        (MotionSceneObject(id="o1", kind="kinetic_title", props={"text": "a " * 40}), "max 54"),
    ]
    for obj, needle in cases:
        sc = MotionScene(field="paper", objects=[obj], actions=[MotionSceneAction(do="enter", target="o1")])
        r = checks.check_motion_scene_valid(_with_scene(base, 3, sc))
        assert not r.passed and needle in r.reason, (needle, r.reason)
    sc = shot.scene.model_copy(update={"actions": [MotionSceneAction(at="banana", do="enter", target="o1")]})
    r = checks.check_motion_scene_valid(_with_scene(base, 3, sc))
    assert not r.passed and "cue 'banana' (enter o1) is not a word" in r.reason, r.reason
    sc = shot.scene.model_copy(update={"actions": [MotionSceneAction(do="count", target="o1")]})
    r = checks.check_motion_scene_valid(_with_scene(base, 3, sc))
    assert not r.passed and "cannot 'count'" in r.reason, r.reason
    tall = [MotionSceneObject(id=f"o{i}", kind="system_panel", props={"title": "x", "status": "y"})
            for i in range(1, 5)]
    r = checks.check_motion_scene_valid(_with_scene(base, 3, MotionScene(objects=tall)))
    assert not r.passed and "do not fit" in r.reason, r.reason


def test_transition_rules():
    base = _scened("usestate_golden")
    s4 = base.shots[3].scene
    r = checks.check_motion_scene_valid(_with_scene(base, 3, s4.model_copy(update={"transition": "iris"})))
    assert not r.passed and "into the same paper field" in r.reason, r.reason
    s6 = base.shots[5].scene
    r = checks.check_motion_scene_valid(_with_scene(base, 5, s6.model_copy(update={"transition": "cut"})))
    assert not r.passed and "on a hard cut" in r.reason, r.reason
    prev = base.shots[2].scene.transition
    r = checks.check_motion_scene_valid(_with_scene(base, 5, s6.model_copy(update={"transition": prev})))
    assert not r.passed and "twice in a row" in r.reason, r.reason


def test_payoff_must_mirror_the_hook():
    base = _scened("usestate_golden")
    pay = base.shots[8].scene
    no_ok = pay.model_copy(update={"objects": [o.model_copy(update={"props": {**o.props, "tone": "plain"}})
                                               if o.kind == "status_pill" else o for o in pay.objects]})
    r = checks.check_motion_payoff_mirrors_hook(_with_scene(base, 8, no_ok))
    assert not r.passed and "must show success" in r.reason, r.reason
    other = pay.model_copy(update={"objects": [o for o in pay.objects if o.kind != "status_pill"],
                                   "actions": [a for a in pay.actions if a.target != "o2"]})
    r = checks.check_motion_payoff_mirrors_hook(_with_scene(base, 8, other))
    assert not r.passed and "mirror the hook" in r.reason, r.reason


def test_change_cadence_rejects_a_still_shot():
    base = _scened("usestate_golden")
    s4 = base.shots[3].scene
    still = s4.model_copy(update={"actions": [a for a in s4.actions if a.do == "enter"][:1]})
    r = checks.check_motion_change_cadence(_with_scene(base, 3, still))
    assert not r.passed and "holds still" in r.reason and "s04" in r.reason, r.reason
    assert checks.check_motion_change_cadence(base).details["worst"] <= ms.MAX_STILL_SECONDS


def test_color_semantics():
    base = _scened("usestate_golden")
    title = base.shots[1].scene
    r = checks.check_motion_color_semantics(_with_scene(base, 3, base.shots[3].scene.model_copy(update={
        "objects": [o.model_copy(update={"props": {**o.props, "tone": "ok"}}) if o.kind == "status_pill" else o
                    for o in base.shots[3].scene.objects]})))
    assert not r.passed and "s04 (break_1)" in r.reason and "mint" in r.reason, r.reason
    stamp = MotionSceneObject(id="o9", kind="stamp", props={"text": "FIXED"})
    r = checks.check_motion_color_semantics(_with_scene(base, 6, base.shots[6].scene.model_copy(update={
        "objects": base.shots[6].scene.objects + [stamp]})))
    assert not r.passed and "coral" in r.reason, r.reason
    assert title is not None


# ========================================================= the scenes call

@contextlib.contextmanager
def _fake_scene_calls(answers: list):
    calls: list[tuple[str, str]] = []
    real = scenes_mod.ask_json

    def fake(system, user, model_cls, **kw):
        assert model_cls is MotionScenesDraft
        calls.append((system, user))
        return answers.pop(0)
    scenes_mod.ask_json = fake
    try:
        yield calls
    finally:
        scenes_mod.ask_json = real


def _draft(script: MotionScript, only: list[str] | None = None) -> MotionScenesDraft:
    return MotionScenesDraft(shots=[{"id": s.id, "scene": s.scene.model_dump()} for s in script.shots
                                    if not only or s.id in only])


def test_a_failing_scene_is_repaired_alone():
    good = _scened("usestate_golden")
    bad = _with_scene(good, 3, MotionScene(objects=[MotionSceneObject(id="o1", kind="hologram")]))
    plain = _script("usestate_golden")
    with _fake_scene_calls([_draft(bad), _draft(good, only=["s04"])]) as calls:
        out, results = scenes_mod.write_motion_scenes(plain, log=lambda *_: None)
    assert checks.all_passed(results), [str(r) for r in results]
    assert len(calls) == 2
    assert "REPAIRING" in calls[1][0] and "- s04 break_1" in calls[1][1]
    assert "- s05 " not in calls[1][1].split("SCRIPT (JSON")[0]       # only the failing shot
    assert out.shots[3].scene == good.shots[3].scene


def test_an_unrepairable_scene_falls_back_to_the_default():
    good = _scened("usestate_golden")
    bad = _with_scene(good, 3, MotionScene(objects=[MotionSceneObject(id="o1", kind="hologram")]))
    plain = _script("usestate_golden")
    logged: list[str] = []
    answers = [_draft(bad)] + [_draft(bad, only=["s04"])] * config.MAX_MOTION_SCENE_RETRIES
    with _fake_scene_calls(answers) as calls:
        out, results = scenes_mod.write_motion_scenes(plain, log=logged.append)
    assert len(calls) == 1 + config.MAX_MOTION_SCENE_RETRIES
    assert checks.all_passed(results)
    assert out.shots[3].scene == ms.default_scenes(plain)[3]
    assert any("using the default scene" in line for line in logged), logged


def test_the_scenes_prompt_names_the_library_and_the_rules():
    system = scenes_mod.system_prompt()
    for kind in lib.object_kinds():
        assert f"  {kind} [" in system, kind
    for rule in ("2.5 seconds", "MIRRORS the hook", "coral", "COPIED from this shot's captions"):
        assert rule in system, rule


def test_stub_scenes_cost_nothing():
    cursor = usage.mark()
    out, results = scenes_mod.write_motion_scenes(_script("usestate_bug_hunt_golden"))
    assert checks.all_passed(results)
    assert usage.since(cursor)["calls"] == 0


# =================================================================== voice

def test_caption_speech_splits_exactly():
    for name in ALL:
        for s in _script(name).shots:
            parts = mv.caption_speech(s)
            assert " ".join(parts).split() == s.speech.split() and len(parts) == len(s.captions), (name, s.id)
            for cap, said, ranges in zip(s.captions, parts, mv.shown_to_spoken(s)):
                assert len(ranges) == len(mtl.caption_words(cap.text)), (name, s.id)
                assert ranges[-1][1] == len(said.split()), (name, s.id, ranges)
    s = _script("usestate_golden").shots[7]
    assert mv.shown_to_spoken(s)[0][2] == (2, 6)   # `useState(0)` <- "use State of zero"


def test_two_speakers_get_two_voice_slots():
    iv = _script("usestate_interview_golden")
    slots = mv.speaker_slots(iv)
    assert slots["INTERVIEWER"] == "motion_host" and slots["CANDIDATE"] == "motion_react"
    assert slots["INTERVIEWER"] != slots["CANDIDATE"]
    assert mv.speaker_slots(_script("usestate_bug_hunt_golden")) == {None: "motion_narrator"}


def test_slot_reference_falls_back_and_says_so():
    ref, how = mv.slot_reference("motion_host")
    assert how == "slot" or how.startswith("fallback"), how
    real = mv.SLOT_DIR
    with tempfile.TemporaryDirectory() as d:
        mv.SLOT_DIR = Path(d)
        (Path(d) / "motion_host.wav").write_bytes(mv._silent(0.5))
        try:
            assert mv.slot_reference("motion_host") == (str(Path(d) / "motion_host.wav"), "slot")
        finally:
            mv.SLOT_DIR = real


def test_float_wavs_are_read_and_normalised():
    """Chatterbox writes 32-bit float WAV (format 3), which Python's `wave`
    cannot open — found by the one real sample. Every clip is read, then
    stored as 16-bit PCM at the mix rate."""
    import struct
    import numpy as np
    rate = 16000
    x = (0.5 * np.sin(np.linspace(0, 200, rate))).astype("<f4")
    body = x.tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    data = (b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(body)) + b"WAVE" +
            b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(body)) + body)
    y, r = mv._read_wav(data)
    assert r == rate and len(y) == rate and abs(float(y.max()) - 0.5) < 1e-3
    assert abs(mv.wav_seconds(data) - 1.0) < 1e-6
    pcm = mv.normalise_wav(data)
    with wave.open(io.BytesIO(pcm)) as w:
        assert w.getsampwidth() == 2 and w.getframerate() == mv.SAMPLE_RATE
        assert abs(w.getnframes() / w.getframerate() - 1.0) < 0.01


def test_voice_and_mix_in_stub():
    with _temp_output() as out:
        script = _scened("usestate_interview_golden").model_copy(update={"short_id": "v__motion"})
        manifest = mv.voice_script(script, log=lambda *_: None)
        rows = [r for s in script.shots for r in manifest["shots"][s.id]]
        assert len(rows) == sum(len(s.captions) for s in script.shots)
        assert {r["voice_slot"] for r in rows} == {"motion_host", "motion_react"}
        assert all((out / "v__motion" / "audio" / r["file"]).exists() for r in rows)
        clocks = mtl.shot_timings(script, {s.id: [r["seconds"] for r in manifest["shots"][s.id]]
                                           for s in script.shots})
        reel = mv.mix(script, manifest, clocks)
        with wave.open(str(reel)) as w:
            seconds = w.getnframes() / w.getframerate()
        assert abs(seconds - mtl.total_seconds(clocks)) < 0.2, (seconds, mtl.total_seconds(clocks))


# ================================================================= timing

def test_alignment_falls_back_to_an_even_split_in_stub():
    times, source = motion_align.align_clip(Path("/nonexistent.wav"), "use State of zero", 1.2)
    assert times is None and source == "even"


def test_alignment_helpers():
    filled = motion_align._fill([[0.1, 0.3], None, [0.6, 0.9]], 1.2)
    assert filled == [(0.1, 0.3), (0.3, 0.6), (0.6, 0.9)]
    assert motion_align._fill([None, None], 1.0) is None
    shown = motion_align.shown_times([(0.0, 0.2), (0.2, 0.5), (0.5, 0.6), (0.6, 0.9), (0.9, 1.0)],
                                     [(0, 1), (1, 4), (4, 5)])
    assert shown == [(0.0, 0.2), (0.2, 0.9), (0.9, 1.0)]
    from shorts.motion_align_worker import normalise
    assert normalise("1.2") == "ONEPOINTTWO" and normalise("re-render,") == "RERENDER"
    assert normalise("101") == "ONEHUNDREDONE" and normalise("—") == ""


def test_real_word_times_place_the_captions():
    script = _scened("usestate_golden")
    shot = script.shots[0]
    n = len(mtl.caption_words(shot.captions[0].text))
    times = {shot.id: [[(0.1 * i, 0.1 * i + 0.08) for i in range(n)]]}
    clocks = mtl.shot_timings(script, {shot.id: [n * 0.1]}, times, {shot.id: ["forced_alignment"]})
    cap = clocks[0].captions[0]
    assert cap.source == "forced_alignment"
    assert cap.words[0].start == round(mtl.SHOT_LEAD, 3)
    assert abs(cap.words[-1].start - (mtl.SHOT_LEAD + 0.1 * (n - 1))) < 1e-6
    plan = mtl.build_plan(script, clocks)
    assert plan.timing_source == "even"           # every other caption is still even


def test_plan_resolves_cues_to_word_times():
    script = _scened("usestate_golden")
    clocks = mtl.shot_timings(script)
    plan = mtl.build_plan(script, clocks)
    for sp, shot, clock in zip(plan.shots, script.shots, clocks):
        assert sp.start == clock.start and sp.end == clock.end
        words = {round(w.start, 3) for w in clock.words()} | {clock.start}
        for a in sp.actions:
            assert round(a.t, 3) in words, (shot.id, a)
        for o in sp.objects:
            if lib.object_kinds()[o.kind]["layout"] == "placed":
                assert o.box is not None and o.box.y >= lib.library()["frame"]["solo"]["top"]
    MotionPlan.model_validate_json(plan.model_dump_json())


def test_minimum_shot_lengths():
    script = _scened("tokenization_golden")
    for s, c in zip(script.shots, mtl.shot_timings(script)):
        if s.beat == "chapter_card":
            assert c.end - c.start >= mtl.MIN_SHOT_SECONDS["chapter_card"] - 1e-6


# ================================================================== runner

def test_runner_builds_scenes_voice_timing_and_a_plan():
    with _temp_output() as out:
        cursor = usage.mark()
        code, text = _run("--yes", "--theme", "interview")
        assert code == 0, text
        [plan_file] = list(out.glob("*/plan.json"))
        plan = MotionPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
        assert [m.role for m in plan.cast] == ["INTERVIEWER", "CANDIDATE"]
        assert [m.side for m in plan.cast] == ["left", "right"]
        assert plan.cast[0].avatar.id == "host" and plan.cast[1].avatar.id == "react"
        assert all(s.layout == "duo" for s in plan.shots) and plan.timing_source == "even"
        assert (plan_file.parent / "audio" / "reel.wav").exists()
        for stage in ("Approve scenes?", "=== voice:", "=== timing:", "render: not built yet"):
            assert stage in text, stage
        assert "INTERVIEWER  slot motion_host" in text
        assert usage.since(cursor)["calls"] == 0
        short_id = plan_file.parent.name
        script = MotionScript.model_validate_json((out / f"{short_id}.motion.json").read_text(encoding="utf-8"))
        assert all(s.scene for s in script.shots)

        code, text = _run("--topic", short_id)
        assert code == 0 and "scenes: resumed" in text and "voice: resumed" in text \
            and "timing: resumed" in text, text
        code, text = _run("--topic", short_id, "--yes", "--force-stage", "scenes")
        assert code == 0 and "Approve scenes?" in text and "=== voice:" in text, text


def test_runner_solo_reel_has_no_cast():
    with _temp_output() as out:
        code, text = _run("--yes", "--theme", "bug_hunt")
        assert code == 0, text
        [plan_file] = list(out.glob("*/plan.json"))
        plan = MotionPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
        assert plan.cast == [] and all(s.layout == "solo" for s in plan.shots)
        assert "NARRATOR     slot motion_narrator" in text


def test_declined_scenes_save_nothing():
    import sys
    with _temp_output() as out:
        _run("--yes", "--theme", "interview")
        [motion_file] = list(out.glob("*.motion.json"))
        short_id = motion_file.name[: -len(".motion.json")]
        data = json.loads(motion_file.read_text(encoding="utf-8"))
        for s in data["shots"]:
            s["scene"] = None
        motion_file.write_text(json.dumps(data), encoding="utf-8")
        real = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            code, text = _run("--topic", short_id)
        finally:
            sys.stdin = real
        assert code == 1, text
        saved = json.loads(motion_file.read_text(encoding="utf-8"))
        assert all(s["scene"] is None for s in saved["shots"])


def test_server_serves_the_plan_and_audio():
    from fastapi.testclient import TestClient
    from shorts import server
    with _temp_output() as out:
        _run("--yes", "--theme", "peer_discussion")
        short_id = next(out.glob("*/plan.json")).parent.name
        client = TestClient(server.app)
        r = client.get(f"/api/motion/{short_id}/plan")
        assert r.status_code == 200 and r.json()["audio_url"] == f"/api/motion/{short_id}/audio"
        assert client.get(f"/api/motion/{short_id}/audio").status_code == 200
        assert client.get("/api/motion/nope__motion/plan").status_code == 404
        assert client.get("/api/motion/..%2Fx/plan").status_code in (400, 404)


def test_demo_plans_are_valid_and_current():
    for name in ("interview", "classic", "walkthrough"):
        path = ROOT / "web" / "public" / "motion-demo" / f"{name}.json"
        plan = MotionPlan.model_validate_json(path.read_text(encoding="utf-8"))
        assert plan.audio is None and plan.shots
    iv = json.loads((ROOT / "web" / "public" / "motion-demo" / "interview.json").read_text(encoding="utf-8"))
    assert iv["cast"] and iv["theme"] == "interview"


# ======================================================= models and cost

def test_model_routing_is_on_only_inside_a_motion_run():
    from shorts import llm, motion_models
    routes = motion_models.routes()
    assert routes["motion_script"] == routes["motion_scenes"] == "anthropic/claude-opus-5.5"
    assert routes["understanding"] == routes["teaching_approach"] == routes["motion_theme"] == \
        "anthropic/claude-opus-5.5"
    assert routes["framing"] == "anthropic/claude-sonnet-5.5"
    assert llm._LABEL_MODELS == {}                      # explainer / story: untouched
    with motion_models.use():
        assert llm._LABEL_MODELS["motion_script"] == "anthropic/claude-opus-5.5"
    assert llm._LABEL_MODELS == {}


def test_the_estimate_is_free_and_priced():
    from shorts import motion_models
    rows = motion_models.estimate(REACT_DOC.read_text(encoding="utf-8"))
    by = {r["label"]: r for r in rows}
    assert by["motion_scenes"]["per_call"] > 0 and by["framing"]["per_call"] > 0   # priced models
    assert sum(r["typical"] for r in rows) <= sum(r["worst"] for r in rows) <= config.MAX_REEL_USD
    with _temp_output() as out:
        cursor = usage.mark()
        code, text = _run("--estimate")
        assert code == 0 and "Estimated cost of this motion reel" in text and "total" in text
        assert usage.since(cursor)["calls"] == 0 and not list(out.iterdir())


def test_every_run_logs_its_cost():
    seen = []
    usage.add_listener(seen.append)
    usage.remove_listener(seen.append)
    with _temp_output() as out:
        code, text = _run("--yes", "--theme", "bug_hunt")
        assert code == 0 and "=== cost:" in text and "reel total, every run" in text, text
        [cost_file] = list(out.glob("*/cost.json"))
        data = json.loads(cost_file.read_text(encoding="utf-8"))
        assert data["runs"][0]["stub"] and data["total"]["calls"] == 0
        short_id = cost_file.parent.name
        _run("--topic", short_id)                     # a resume adds no empty run
        data = json.loads(cost_file.read_text(encoding="utf-8"))
        assert len(data["runs"]) == 1


def test_motion_reels_are_listed_with_their_bundle():
    from fastapi.testclient import TestClient
    from shorts import motion_bundle, server
    with _temp_output() as out:
        _run("--yes", "--theme", "interview")
        short_id = next(out.glob("*/plan.json")).parent.name
        client = TestClient(server.app)
        [row] = client.get("/api/motion").json()["reels"]
        assert row["short_id"] == short_id and row["stub"] and row["theme"] == "interview"
        assert row["stage"] == "timing" and row["tags"][1] == "#interview"
        b = client.get(f"/api/motion/{short_id}/bundle").json()
        assert b["plan_url"] == f"/api/motion/{short_id}/plan"
        assert b["script"]["speakers"][0]["role"] == "INTERVIEWER"
        assert b["approach"]["primary"] and b["theme_choice"]["reason"] and b["cost_log"]["runs"]
        assert any(c.get("speaker") for s in b["script"]["shots"] for c in s["captions"])
        assert client.get("/api/motion/nothing__motion/bundle").status_code == 404
        assert motion_bundle.list_reels(out) == [short_id]


def test_demo_bundles_match_the_index():
    demo = ROOT / "web" / "public" / "motion-demo"
    index = json.loads((demo / "index.json").read_text(encoding="utf-8"))["reels"]
    assert [r["demo"] for r in index] == ["interview", "classic", "walkthrough"]
    for r in index:
        b = json.loads((demo / f"{r['demo']}.bundle.json").read_text(encoding="utf-8"))
        assert b["stub"] and b["script"]["shots"] and b["plan_url"] == f"/motion-demo/{r['demo']}.json"
        assert b["theme"] == r["theme"] and b["tags"] == r["tags"]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} motion scene tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL MOTION SCENE TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
