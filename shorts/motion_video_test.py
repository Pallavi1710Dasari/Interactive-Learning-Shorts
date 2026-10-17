"""
Long-form VIDEOS (format "video", 2026-10-16), end to end and in parts:

  - the job: Upload with "video" skips the Template step (a video is always
    written as a walkthrough), the theme step recommends a walkthrough theme
    and offers every other theme too (2026-10-17: a one-narrator or a
    two-speaker theme sets the video's voice, its chapters stay), the script
    is 6-12 minutes in 5-10 chapters and passes every free grader, the
    scenes are asked in chapter batches, and the finished plan is a
    1920x1080 landscape plan whose every shot has a view, with the mentor as
    a 3D avatar and the video layout checks passing;
  - a reel made the same way is still a 1080x1920 reel;
  - the video limits: a reel-length script fails as a video, and a
    video-length script fails as a reel;
  - the views: never past zoom_cap, inside the board, centred.

    SHORTS_STUB=1 python -m shorts.motion_video_test

Writes only to a temp output folder (shorts.testing.isolate_output).
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
import shutil
import time
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import checks, config, motion_jobs as mj, motion_reel as mr, motion_themes, motion_video
from shorts.schema import MotionBox, MotionPlacedObject, MotionScript
from shorts.skills.scenes import VIDEO_SCENE_BATCH, scene_batches

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "content/react_usestate_basics.md"
REG = motion_themes.registry()


def _upload(doc: Path) -> dict:
    up = config.OUTPUT_DIR / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    path = up / f"video_{time.time_ns()}.md"
    shutil.copy(doc, path)
    return mj.new_job(path, doc.name)


def _wait(job: dict, timeout: float = 600) -> dict:
    end = time.time() + timeout
    while job["job_id"] in mj._RUNNING:
        assert time.time() < end, f"job still running: {job['activity']}"
        time.sleep(0.05)
    fresh = mj.load(job["job_id"])
    assert fresh["status"] != "error", fresh.get("error")
    return fresh


def _past_preflight(job: dict) -> dict:
    job = _wait(job)
    if job["status"] == "preflight":
        job = _wait(mj.decide(job, "proceed"))
    return job


def _make(fmt: str, vrm: dict | None = None,
          theme: str | None = None) -> tuple[dict, MotionScript, dict]:
    """A job from upload to its finished plan, every recommended choice
    (`vrm`: the Characters step's 3D avatar picks, role -> name; `theme`: the
    theme picked instead of the recommended one)."""
    job = _wait(mj.start(_upload(DOC), {"format": fmt}))
    assert (job["stage"], job["status"]) == ("topic", "review"), (job["stage"], job["status"])
    job = _wait(mj.decide(job, "approve", choice=0))
    assert job["stage"] == "approach"
    job = mj.decide(job, "approve", choice=job["review"]["recommended"]["value"])
    # the Template step (the UI's Language step): a video's one choice is the walkthrough
    assert job["stage"] == "template", job["stage"]
    if fmt == "video":
        assert [o["value"] for o in job["review"]["options"]] == ["walkthrough"]
        job = mj.decide(job, "language", choice="react")
    else:
        job = mj.decide(job, "approve", choice=job["review"]["recommended"]["value"])
    sid = job["short_id"]
    state = mr._load_setup(sid)
    assert state["format"] == fmt, state.get("format")
    if fmt == "video":
        assert state["template"] == "walkthrough" and mr.template_pin(state) == "walkthrough"
    job = _past_preflight(job)
    assert job["stage"] == "theme", job["stage"]
    if fmt == "video":
        # the walkthrough is recommended; the other themes are offered after it
        offered = [o["value"] for o in job["review"]["options"]]
        assert REG.themes[job["review"]["recommended"]["value"]].template == "walkthrough"
        assert offered[0] == job["review"]["recommended"]["value"]
        assert {REG.themes[o].template for o in offered} == {"walkthrough", "fix_story"}, offered
        assert any(REG.themes[o].two_speaker for o in offered), offered
    if theme is not None:
        assert theme in [o["value"] for o in job["review"]["options"]], theme
    job = mj.decide(job, "approve", choice=theme or job["review"]["recommended"]["value"])
    job = _past_preflight(job)
    assert job["stage"] == "script", job["stage"]
    if vrm is not None:
        info = mj.cast_info(job)
        assert info["three_d"] and {a["value"] for a in info["vrm_avatars"]} >= {"mentor", "student"}
        job = mj.decide(job, "cast", choice={"characters": True, "vrm": vrm})
        assert job["options"]["vrm"] == vrm, job["options"].get("vrm")
    assert job["review"] is not None, (job["status"], job["message"], job.get("error"))
    rv = job["review"]
    assert rv["passed"], [r for r in rv["results"] if not r["passed"]]
    job = mj.decide(job, "approve")
    script = MotionScript.model_validate_json(mr.motion_path(sid).read_text())
    job = _past_preflight(job)
    assert job["stage"] == "scenes", job["stage"]
    assert job["review"]["passed"], job["review"]
    job = _wait(mj.decide(job, "approve"))
    assert (job["stage"], job["status"]) == ("done", "done"), (job["stage"], job["status"], job["message"])
    plan = json.loads(mr.plan_path(sid).read_text())
    return job, script, plan


def test_a_video_from_upload_to_its_landscape_plan():
    job, script, plan = _make("video")
    assert job["short_id"].endswith("__video"), job["short_id"]
    assert script.format == "video" and script.template == "walkthrough"
    lo, hi = checks.MOTION_VIDEO["MOTION_SECONDS"]
    assert lo <= script.estimated_seconds <= hi, script.estimated_seconds
    clo, chi = checks.MOTION_VIDEO["MOTION_CHAPTERS"]
    assert clo <= len(script.chapters) <= chi
    assert plan["format"] == "video" and (plan["width"], plan["height"]) == (1920, 1080)
    assert plan["stage"] == "video"
    assert all(s["view"] for s in plan["shots"]), "a shot without a view"
    assert plan["characters"] and plan["avatars"] == "vrm"
    assert plan["characters"][0]["vrm"] == "mentor"
    on = [s["characters"] for s in plan["shots"]]
    assert on[0] and not all(on), "".join("+" if o else "." for o in on)
    assert mj.view(job)["summary"]["options"]["detail"].startswith("a video")
    # listed as a motion item, marked a video (the #videos page; out of the reel feed)
    from shorts import motion_bundle
    assert job["short_id"] in motion_bundle.list_reels(config.OUTPUT_DIR)
    assert motion_bundle.summary(config.OUTPUT_DIR, job["short_id"])["format"] == "video"
    print(f"  video {job['short_id']}: {len(plan['shots'])} shots, {plan['duration']:.0f} s, "
          f"{len(script.chapters)} chapters, presenter "
          + "".join("+" if o else "." for o in on))


def test_a_video_in_a_one_narrator_theme_keeps_its_chapters():
    job, script, plan = _make("video", theme="myth_vs_fact")
    assert script.theme == "myth_vs_fact" and script.template == "walkthrough"
    assert not script.speakers
    clo, chi = checks.MOTION_VIDEO["MOTION_CHAPTERS"]
    assert clo <= len(script.chapters) <= chi
    assert plan["format"] == "video" and len(plan["characters"]) == 1
    assert mj.view(mj.load(job["job_id"]))["summary"]["theme"]["value"] == "Myth vs fact"


def test_a_two_speaker_video():
    """Mentor & student as a video: the student asks, the mentor teaches,
    every line is labelled, two 3D avatars stand beside the board, and the
    video's layout checks pass with both of them on."""
    job, script, plan = _make("video", theme="mentor_student")
    assert script.theme == "mentor_student" and script.template == "walkthrough"
    roles = [sp.role for sp in script.speakers]
    assert sorted(roles) == sorted(REG.themes["mentor_student"].roles), roles
    assert all(c.speaker in roles for s in script.shots for c in s.captions)
    assert script.shots[0].captions[0].speaker == REG.themes["mentor_student"].roles[0]
    assert plan["format"] == "video" and len(plan["characters"]) == 2, plan["characters"]
    assert sorted(c["vrm"] for c in plan["characters"]) == ["mentor", "student"]
    assert {c["role"] for c in plan["cast"]} == set(roles)
    assert all(s["view"] for s in plan["shots"])
    print(f"  two-speaker video {job['short_id']}: {len(plan['shots'])} shots, "
          f"{plan['duration']:.0f} s, {len(script.chapters)} chapters")


def test_the_3d_avatar_picked_in_the_characters_step_is_drawn():
    """Step 6 lists the 3D avatars (assets/avatars/*.vrm); the one picked for
    the narrator is the one the video draws."""
    job, script, plan = _make("video", vrm={"narrator": "student"})
    assert [c["vrm"] for c in plan["characters"]] == ["student"], plan["characters"]
    assert "Student" in mj.view(mj.load(job["job_id"]))["summary"]["cast"]["value"]


def test_a_reel_wears_its_picks_too():
    from shorts import motion_teach
    from shorts.schema import MotionCharacterTrack
    tr = lambda role, side: MotionCharacterTrack(role=role, preset="react", config={}, side=side)
    tracks = [tr("STUDENT", "left"), tr("MENTOR", "right")]
    # nothing picked: the asker the student, the explainer the mentor
    assert [motion_teach.vrm_for(t, 2) for t in tracks] == ["student", "mentor"]
    # picked: swapped
    assert [motion_teach.vrm_for(t, 2, {"STUDENT": "mentor", "MENTOR": "student"}) for t in tracks] == ["mentor", "student"]
    narrator = tr(None, "center")
    assert motion_teach.vrm_for(narrator, 1) == "mentor"
    assert motion_teach.vrm_for(narrator, 1, {"narrator": "student"}) == "student"


def test_a_reel_is_still_a_portrait_reel():
    # (and a reel wears the 3D avatar picked in the Characters step too)
    job, script, plan = _make("reel", vrm={"narrator": "student"})
    assert plan["avatars"] == "vrm" and [c["vrm"] for c in plan["characters"]] == ["student"], plan["characters"]
    assert job["short_id"].endswith("__motion")
    assert script.format == "reel"
    assert plan["format"] == "reel" and (plan["width"], plan["height"]) == (1080, 1920)
    assert all(s.get("view") is None for s in plan["shots"])
    assert script.estimated_seconds <= checks.MOTION_MAX_SECONDS


def test_a_video_is_always_a_walkthrough():
    job = _upload(DOC)
    try:
        mj.start(job, {"format": "video", "template": "fix_story"})
    except ValueError as e:
        assert "walkthrough" in str(e)
    else:
        raise AssertionError("a fix_story video was accepted")
    try:
        mj.start(_upload(DOC), {"format": "movie"})
    except ValueError as e:
        assert "format" in str(e)
    else:
        raise AssertionError("an unknown format was accepted")


def _video_script() -> MotionScript:
    from shorts import stub_motion
    from shorts.schema import MotionScriptDraft
    text = DOC.read_text()
    d = MotionScriptDraft(**stub_motion.video_draft(f"MATERIAL (s):\n{text}", None))
    return MotionScript(format="video", template="walkthrough", short_id="x__video", source_section_id="1",
                        topic="t", **d.model_dump())


def test_the_limits_follow_the_format():
    video = _video_script()
    assert checks.check_motion_word_budget(video).passed
    assert checks.check_walkthrough_chapters(video).passed
    # the same script as a reel is far too long, in too many chapters
    reel = video.model_copy(update={"format": "reel"})
    assert not checks.check_motion_word_budget(reel).passed
    assert not checks.check_walkthrough_chapters(reel).passed
    assert not checks.check_motion_duration_cap(reel).passed
    assert checks.check_motion_duration_cap(video).passed
    # a reel-length script is too short for a video
    short = video.model_copy(update={"shots": video.shots[:3] + video.shots[3:11] + video.shots[-4:]})
    assert not checks.check_motion_word_budget(short).passed


def test_scenes_are_asked_in_chapter_batches():
    video = _video_script()
    batches = scene_batches(video)
    assert len(batches) > 1
    assert [i for b in batches for i in b] == [s.id for s in video.shots]
    assert all(len(b) <= VIDEO_SCENE_BATCH for b in batches)
    by_id = {s.id: s for s in video.shots}
    # a batch starts at a chapter card or a whole-video boundary
    for b in batches[1:]:
        assert by_id[b[0]].beat in ("chapter_card", "result", "chapter"), by_id[b[0]].beat
    assert scene_batches(video.model_copy(update={"format": "reel"})) == [[s.id for s in video.shots]]


def test_scene_variety_holds_per_stretch_of_a_video():
    """A video may reuse a kind across the lesson — never more than 3 times
    in any 11 shots in a row (a reel's cap holds across a reel's length)."""
    from shorts.motion_scenes import with_default_scenes
    video = with_default_scenes(_video_script())
    assert checks.check_motion_scene_variety(video).passed, checks.check_motion_scene_variety(video).reason
    assert checks.check_motion_scene_valid(video).passed, checks.check_motion_scene_valid(video).reason
    # the reel's whole-reel cap would fail the same 55 shots
    assert not checks.check_motion_scene_variety(video.model_copy(update={"format": "reel"})).passed
    # four of one kind within 11 shots fails for a video too
    flows = [i for i, s in enumerate(video.shots) if s.scene and s.scene.objects
             and s.scene.objects[0].kind == "flow"]
    assert flows
    sc = video.shots[flows[0]].scene
    shots = list(video.shots)
    for k in (2, 4, 6):
        i = flows[0] + k
        if shots[i].beat == "chapter":
            shots[i] = shots[i].model_copy(update={"scene": sc})
    r = checks.check_motion_scene_variety(video.model_copy(update={"shots": shots}))
    assert not r.passed and "within 11" in r.reason, r.reason


def test_a_batch_answers_only_its_own_shots():
    from shorts.skills.scenes import _batch_note
    video = _video_script()
    only = [s.id for s in video.shots[3:12]]
    note = _batch_note(video, only)
    assert f"ONLY these {len(only)} shots" in note and only[0] in note and only[-1] in note


def test_a_video_repairs_only_its_failing_shots():
    """A caption broken in one shot is fixed by rewriting that shot alone —
    no full rewrite of the 6-12 minutes."""
    from shorts.schema import CaptionChunk, MotionShotsFix
    from shorts.skills import script as script_mod
    good = _video_script()
    i = next(k for k, s in enumerate(good.shots) if s.beat == "chapter")
    orig = good.shots[i]
    long = "This line runs on and on with far too many words for one caption to hold."
    broken = good.model_copy(update={"shots": good.shots[:i] + [orig.model_copy(update={
        "speech": long, "captions": [CaptionChunk(text=long)]})] + good.shots[i + 1:]})
    grade = lambda sc: checks.run_motion_script_graders(sc, DOC.read_text())
    results = grade(broken)
    assert not checks.all_passed(results)
    assert script_mod._failing_shot_ids(results) == [orig.id], script_mod._failing_shot_ids(results)
    asked = []

    def fake(system, user, cls, **kw):
        asked.append((kw.get("label"), user))
        return MotionShotsFix(shots=[orig])
    real = script_mod.ask_json
    script_mod.ask_json = fake
    try:
        fixed, fixed_results = script_mod.repair_video_shots(broken, "MATERIAL", results, grade)
    finally:
        script_mod.ask_json = real
    assert fixed is not None and checks.all_passed(fixed_results), [r for r in fixed_results if not r.passed]
    assert len(asked) == 1 and asked[0][0] == "motion_shot_fix"
    assert f'"id": "{orig.id}"' in asked[0][1] and asked[0][1].count('"beat"') == 1   # that shot alone
    assert [s.speech for s in fixed.shots] == [s.speech for s in good.shots]
    # a whole-length failure is never a targeted repair
    short = good.model_copy(update={"shots": good.shots[:3] + good.shots[3:11] + good.shots[-4:]})
    assert script_mod._failing_shot_ids(grade(short)) is None


def test_a_view_fits_the_board_and_never_over_enlarges():
    g = motion_video.geometry()
    small = [MotionPlacedObject(id="o1", kind="status_pill", props={}, box=MotionBox(x=400, y=500, w=280, h=60))]
    v = motion_video.view_for(small, g["board_off"])
    assert v.s <= g["zoom_cap"] + 1e-9
    dx, dy, dw, dh = g["board_off"]
    assert dx - 0.5 <= v.dst[0] and v.dst[0] + v.dst[2] <= dx + dw + 0.5
    # centred: the pill's centre lands on the board's centre
    cx, cy = motion_video.to_frame(v, 540, 530)
    assert abs(cx - (dx + dw / 2)) < 1 and abs(cy - (dy + dh / 2)) < 1
    tall = [MotionPlacedObject(id="o1", kind="code_window", props={}, box=MotionBox(x=60, y=300, w=960, h=1000))]
    v = motion_video.view_for(tall, g["board_on"])
    x0, y0 = motion_video.to_frame(v, 60, 300)
    x1, y1 = motion_video.to_frame(v, 1020, 1300)
    bx, by, bw, bh = g["board_on"]
    assert bx - 0.5 <= x0 and x1 <= bx + bw + 0.5 and by - 0.5 <= y0 and y1 <= by + bh + 0.5


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"- {t.__name__}")
    print("\nALL MOTION VIDEO TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
