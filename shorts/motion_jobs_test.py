"""
The web UI's motion runner (shorts/motion_jobs.py), end to end in stub mode:
upload -> options -> topic -> approach -> template -> theme -> script ->
scenes -> voice -> timing -> done, with every gate's approve / regenerate /
skip, the pre-flight and cap stops, and resume paying for nothing approved.

    SHORTS_STUB=1 python -m shorts.motion_jobs_test
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

from shorts import config, motion_jobs as mj, motion_reel as mr

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "content/react_usestate_basics.md"

# Stub calls cost nothing and never reach the usage ledger, so "resume pays
# for nothing approved" is checked by counting the model calls themselves:
# every stub answer goes through stubs.fake.
from shorts import stubs
_CALLS: list[str] = []
_real_fake = stubs.fake


def _counting_fake(model_cls, system, user):
    _CALLS.append(model_cls.__name__)
    return _real_fake(model_cls, system, user)


stubs.fake = _counting_fake


def _upload() -> dict:
    up = config.OUTPUT_DIR / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    path = up / f"test_{time.time_ns()}.md"
    shutil.copy(DOC, path)
    return mj.new_job(path, DOC.name)


def _wait(job: dict, timeout: float = 120) -> dict:
    end = time.time() + timeout
    while job["job_id"] in mj._RUNNING:
        assert time.time() < end, f"job still running: {job['activity']}"
        time.sleep(0.05)
    fresh = mj.load(job["job_id"])
    assert fresh["status"] != "error", fresh.get("error")
    return fresh


def _to(job: dict, stage: str, status: str = "review") -> None:
    assert (job["stage"], job["status"]) == (stage, status), \
        (job["stage"], job["status"], job["message"])


def _run_to_theme(options: dict | None = None) -> dict:
    job = _wait(mj.start(_upload(), options or {}))
    _to(job, "topic")
    job = _wait(mj.decide(job, "approve"))
    _to(job, "approach")
    job = _wait(mj.decide(job, "approve"))
    return job


def test_a_whole_reel_from_upload_to_player():
    job = _upload()
    _to(job, "options", "options")
    info = mj.options_info(job)
    assert info["estimate"]["worst"] > 0 and info["estimate"]["cap"] == config.MAX_REEL_USD
    assert any(o["value"] == "7.2" for o in info["section"]["options"])
    assert job["options"]["characters"] is True          # ON by default in the UI

    job = _run_to_theme()
    _to(job, "template")
    assert job["review"]["default"] in ("fix_story", "walkthrough")
    job = mj.decide(job, "approve", choice="fix_story")
    sid = job["short_id"]
    assert sid and "__motion" in sid
    state = mr._load_setup(sid)
    assert state["template"] == "fix_story" and state["template_source"] == "reviewer"
    assert state["doc_path"] == job["doc_path"]

    _to(job, "theme", "preflight")                       # a fit call: shown before spending
    pf = job["preflight"]
    assert pf["total"] > 0 and pf["fits"] and pf["cap"] == config.MAX_REEL_USD
    job = _wait(mj.decide(job, "proceed"))
    _to(job, "theme")
    assert job["review"]["choice"]["template"] == "fix_story"   # the pin held
    assert job["review"]["tag_checks"] and all(r["passed"] for r in job["review"]["tag_checks"])
    job = mj.decide(job, "approve")
    assert mr.theme_path(sid).exists() and mr.tags_path(sid).exists()

    _to(job, "script", "preflight")
    job = _wait(mj.decide(job, "proceed"))
    _to(job, "script")
    r = job["review"]
    assert r["passed"] and r["results"] and all(x["passed"] for x in r["results"])
    assert r["facts"] and r["script"]["shots"]
    assert not mr.motion_path(sid).exists()              # written only on approval
    job = mj.decide(job, "approve")
    assert mr.motion_path(sid).exists()

    _to(job, "scenes", "preflight")
    job = _wait(mj.decide(job, "proceed"))
    _to(job, "scenes")
    assert job["review"]["passed"] and job["review"]["shots"][0]["objects"]
    job = _wait(mj.decide(job, "approve"))
    _to(job, "done", "done")
    plan = json.loads(mr.plan_path(sid).read_text())
    assert plan["characters"], "characters are ON by default"
    assert mj.view(job)["links"]["player"] == f"#motion-reel/{sid}"

    from shorts import motion_bundle
    assert sid in motion_bundle.list_reels(config.OUTPUT_DIR)
    cost = json.loads(mr.cost_path(sid).read_text())
    # the job's spend is one run of the reel (stub calls cost nothing and log none)
    assert [r["started"] for r in cost["runs"]] == [job["started"]] and cost["runs"][0]["stub"]


def test_voice_and_timing_report_clip_progress():
    seen = []
    real = mj.save

    def spy(job):
        if job.get("progress"):
            seen.append((job["stage"], job["progress"]["done"], job["progress"]["total"]))
        real(job)
    mj.save = spy
    try:
        job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
        _to(job, "theme")                                # --theme: no fit call, no pre-flight
        job = mj.decide(job, "approve")
        job = _wait(mj.decide(job, "proceed"))
        job = mj.decide(job, "approve")
        job = _wait(mj.decide(job, "proceed"))
        job = _wait(mj.decide(job, "approve"))
        _to(job, "done", "done")
    finally:
        mj.save = real
    voice = [s for s in seen if s[0] == "voice"]
    timing = [s for s in seen if s[0] == "timing"]
    # the voice is recorded while the scenes are drawn (2026-10-13): by the
    # voice step it may be finished already — its progress ends at the total
    assert voice and voice[-1][1] == voice[-1][2] and voice[-1][2] > 0, voice[:3]
    assert timing and timing[-1][1] == timing[-1][2], timing[-3:]


def test_the_characters_step_and_going_back():
    """Two speakers: two avatars and two different voices, the recommendation
    first; the reviewer's other picks reach the plan and the voices; "Change"
    goes back to an earlier step without a new call (2026-10-13)."""
    job = _run_to_theme({"theme": "interview", "template": "fix_story"})
    _to(job, "theme")
    job = mj.decide(job, "approve")
    assert job["stage"] == "script"
    info = mj.cast_info(job)
    roles = [r["role"] for r in info["speakers"]]
    assert len(roles) == 2 and info["speakers"][0]["voice"] != info["speakers"][1]["voice"]
    asker = next(r for r in info["speakers"] if r["does"] == "asks the questions")
    other = next(r for r in info["speakers"] if r is not asker)
    same = {r: asker["voice"] for r in roles}
    try:
        mj.decide(job, "cast", choice={"characters": True, "avatars": {}, "voices": same})
        raise AssertionError("two speakers with one voice was accepted")
    except ValueError as e:
        assert "two different voices" in str(e)
    # go back to the theme, approve it again: no new call
    calls = len(_CALLS)
    job = mj.decide(job, "back", choice="theme")
    _to(job, "theme")
    assert len(_CALLS) == calls
    job = mj.decide(job, "approve")
    swapped = {asker["role"]: other["voice"], other["role"]: asker["voice"]}
    job = mj.decide(job, "cast", choice={"characters": True,
                                         "avatars": {asker["role"]: "riya", other["role"]: "arjun"},
                                         "voices": swapped})
    assert job["options"]["cast_confirmed"] and job["options"]["host_character"] == "riya"
    if job["status"] == "preflight":
        job = _wait(mj.decide(job, "proceed"))
    job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed")) if job["status"] == "preflight" else _wait(job)
    if job["stage"] == "scenes":
        job = _wait(mj.decide(job, "approve"))
    _to(job, "done", "done")
    plan = json.loads(mr.plan_path(job["short_id"]).read_text())
    assert [c["preset"] for c in plan["characters"]] == ["riya", "arjun"], plan["characters"]
    from shorts import motion_voice
    manifest = json.loads(motion_voice.manifest_path(job["short_id"]).read_text())
    refs = {v["ref"] for v in manifest["slots"].values()}
    assert len(refs) == 2, manifest["slots"]
    try:
        mj.decide(job, "back", choice="topic")
        raise AssertionError("went back after the reel was made")
    except ValueError:
        pass


def test_the_template_option_locks_without_a_template_screen():
    job = _run_to_theme({"template": "walkthrough"})
    assert job["short_id"]
    assert mr._load_setup(job["short_id"])["template_source"] == "flag"
    assert job["stage"] == "theme"


def test_skip_leaves_it_pending_and_resume_shows_it_again_for_free():
    job = _wait(mj.start(_upload(), {}))
    question = job["review"]["question"]
    job = mj.decide(job, "skip")
    _to(job, "topic", "stopped")
    before = len(_CALLS)
    job = mj.resume(job)
    _to(job, "topic")
    assert job["review"]["question"] == question
    assert len(_CALLS) == before, _CALLS[before:]


def test_regenerate_needs_a_reason_and_rewords_the_question():
    job = _wait(mj.start(_upload(), {}))
    try:
        mj.decide(job, "regenerate", reason="")
        raise AssertionError("a regeneration without a reason was sent")
    except ValueError:
        pass
    before = len(_CALLS)
    job = _wait(mj.decide(job, "regenerate", reason="make it about the screen"))
    _to(job, "topic")
    assert len(_CALLS) > before                          # the counter does see calls
    assert job["review"]["regenerations"] == 1


def test_a_cap_stop_spends_nothing_and_resume_does_not_repay_approved_stages():
    real_cap = config.MAX_REEL_USD
    job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    job = mj.decide(job, "approve")                      # theme approved and saved
    _to(job, "script", "preflight")
    config.MAX_REEL_USD = 0.0001
    try:
        job = mj.resume(job)                             # re-enter the gate under the cap
        _to(job, "script", "cap")
        assert "limit for one reel" in job["message"] and "Nothing was spent" in job["message"]
        before = len(_CALLS)
        job = mj.decide(job, "proceed")                  # refused: stop, nothing spent
        _to(job, "script", "stopped")
        assert len(_CALLS) == before, _CALLS[before:]
    finally:
        config.MAX_REEL_USD = real_cap
    before = len(_CALLS)
    job = mj.resume(job)
    _to(job, "script", "preflight")                      # theme not redone
    assert len(_CALLS) == before, _CALLS[before:]


def test_a_pending_script_survives_a_closed_tab():
    job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed"))
    _to(job, "script")
    # the tab closes; a stop (or a server restart) leaves the job stopped
    job = mj._stop(job, "closed")
    before = len(_CALLS)
    job = mj.resume(job)
    _to(job, "script")
    assert job["review"]["script"] and all(r["passed"] for r in job["review"]["results"])
    assert len(_CALLS) == before, _CALLS[before:]


def test_a_rejected_script_saved_by_the_cli_is_reused():
    from shorts import motion_repair
    from shorts.schema import MotionScript
    job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed"))
    script = MotionScript(**job["review"]["script"])
    motion_repair.save_rejected(script, [])
    job = mj._stop(job, "closed")
    job["data"]["script"] = None
    mj.save(job)
    before = len(_CALLS)
    job = mj.resume(job)
    _to(job, "script")
    assert "no new call was made" in job["review"]["reused"]
    assert len(_CALLS) == before, _CALLS[before:]


def test_an_interrupted_stage_is_resumable():
    job = _upload()
    job.update(stage="topic", status="running")
    mj.save(job)
    job = mj.load(job["job_id"])
    _to(job, "topic", "error")
    e = job["error"]
    assert "server stopped" in e["title"] and "Nothing you approved was lost" in e["lost"]
    assert e["action"] == "Run this step again"


def test_a_cli_reel_is_adopted_at_the_stage_it_reached():
    state_job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    sid = state_job["short_id"]
    mj._path(state_job["job_id"]).unlink()               # as if the CLI had made it
    setup = mr._load_setup(sid)
    setup.pop("doc_path")
    mr._save_setup(sid, setup)
    job = mj.job_for_reel(sid)
    assert job["short_id"] == sid and Path(job["doc_path"]).name == DOC.name
    _to(job, "theme", "stopped")
    job = _wait(mj.resume(job))
    _to(job, "theme")                                    # --theme: free; shown for approval


def test_a_stub_run_on_any_upload_reaches_the_player():
    """The reported error (2026-10-12): a stub run on the user's own upload
    with theme mentor_student stopped at the shot list — "NotImplementedError:
    no fix_story motion stub fixture teaches this material as mentor_student".
    The stub now writes a script from any material, so the same run, with the
    same document and options, goes all the way to the player."""
    up = config.OUTPUT_DIR / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    path = up / f"dyn_{time.time_ns()}.md"
    shutil.copy(ROOT / "evals/fixtures/motion/dynamic_web_app_material.md", path)
    job = mj.new_job(path, "dynamic_web_app_material.md")
    job = _wait(mj.start(job, {"theme": "mentor_student", "template": "fix_story"}))
    while job["status"] != "done":
        assert job["status"] in ("review", "preflight"), (job["stage"], job["status"], job["message"])
        if job["stage"] == "script" and job["status"] == "review":
            assert job["review"]["passed"], job["review"]["results"]
            assert job["review"]["script"]["theme"] == "mentor_student"
        job = _wait(mj.decide(job, "proceed" if job["status"] == "preflight" else "approve"))
    plan = json.loads(mr.plan_path(job["short_id"]).read_text())
    assert len(plan["characters"]) == 2                 # STUDENT and MENTOR


def test_an_error_is_explained_and_retry_recovers():
    """A step that fails says what went wrong, that nothing approved was lost
    and nothing was charged, and what to do; the traceback is only in the
    details. Retry runs the step again and the reel carries on."""
    class RateLimitError(Exception):     # matched by name, as the SDK's is
        pass
    job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    job = mj.decide(job, "approve")                      # theme saved
    real = mr.write_script

    def fails(*a, **k):
        raise RateLimitError("429 slow down")
    mr.write_script = fails
    try:
        job = mj.decide(job, "proceed")
        while job["job_id"] in mj._RUNNING:
            time.sleep(0.05)
        job = mj.load(job["job_id"])
    finally:
        mr.write_script = real
    _to(job, "script", "error")
    e = job["error"]
    assert e["title"] == "The AI service failed while writing the script", e["title"]
    assert e["what"] == "The AI service is busy and asked us to slow down."
    assert "theme are saved" in e["lost"] and "Nothing was charged" in e["lost"], e["lost"]
    assert e["next"] == "Wait a minute, then retry." and e["action"] == "Retry this step"
    assert "Traceback" in e["details"] and "Traceback" not in e["what"] + e["lost"] + e["next"]
    job = mj.resume(job)                                 # Retry
    _to(job, "script", "preflight")
    job = _wait(mj.decide(job, "proceed"))
    _to(job, "script")
    assert job["review"]["passed"]


def test_every_pick_is_respected_downstream():
    """The AI recommends; the reviewer's different pick is the one used."""
    job = _wait(mj.start(_upload(), {}))
    r = job["review"]
    assert r["recommended"]["value"] == 0 and r["recommended"]["reason"]
    assert len(r["options"]) >= 2 and all(o["description"] for o in r["options"])
    second = r["options"][1]["label"]
    job = _wait(mj.decide(job, "approve", choice=1))     # a different topic
    assert job["review"]["question"] == second
    rec = job["review"]["recommended"]["value"]
    other = next(o["value"] for o in job["review"]["options"] if o["value"] != rec)
    job = mj.decide(job, "approve", choice=other)        # a different approach
    _to(job, "template")
    t = job["review"]
    assert t["recommended"]["reason"] and len(t["options"]) == 2
    pick = next(o["value"] for o in t["options"] if o["value"] != t["recommended"]["value"])
    job = mj.decide(job, "approve", choice=pick)         # the other template
    state = mr._load_setup(job["short_id"])
    assert state["template"] == pick and state["template_source"] == "reviewer"
    from shorts.schema import QuestionWorkflow
    assert QuestionWorkflow(**state["workflow"]).approved_teaching_approach.primary == other
    assert QuestionWorkflow(**state["workflow"]).effective_question == second
    if job["status"] == "preflight":
        job = _wait(mj.decide(job, "proceed"))
    else:
        job = _wait(job)
    th = job["review"]
    assert all(o["value"] for o in th["options"]) and th["recommended"]["reason"]
    from shorts import motion_themes
    reg = motion_themes.registry()
    assert all(reg.themes[o["value"]].template == pick for o in th["options"])
    alt = next((o["value"] for o in th["options"] if o["value"] != th["recommended"]["value"]),
               None)
    if alt:
        job = mj.decide(job, "approve", choice=alt)      # a different theme
        assert mr._load_theme(job["short_id"]).theme == alt


def test_a_different_section_pins_the_topic_search():
    job = _wait(mj.start(_upload(), {}))
    job = _wait(mj.decide(job, "section", choice="7.3"))
    _to(job, "topic")
    assert all(o["description"].startswith("From section 7.3") for o in job["review"]["options"])
    assert job["options"]["section"] == "7.3"


def test_the_upload_step_recommends_each_option_with_a_reason():
    info = mj.options_info(_upload())
    for key in ("section", "language", "characters", "character"):
        rec = info[key]["recommended"]
        assert rec["label"] and rec["reason"], key
        assert info[key]["options"] and all(o["description"] for o in info[key]["options"]), key
    assert info["language"]["recommended"]["value"] == "react"
    assert info["characters"]["recommended"]["value"] is True


def test_a_double_click_is_applied_once():
    """Two clicks on the same step, at the same moment, on the server's
    threads: one acts, the other is refused — setup never runs twice."""
    import threading
    from fastapi.testclient import TestClient
    from shorts.server import app
    job = _wait(mj.start(_upload(), {}))
    job = _wait(mj.decide(job, "approve"))
    job = mj.decide(job, "approve")                       # approach -> template
    _to(job, "template")
    c = TestClient(app)
    codes = []
    go = threading.Barrier(2)

    def click():
        go.wait()
        r = c.post(f"/api/motion-jobs/{job['job_id']}/decide",
                   json={"action": "approve", "choice": "fix_story", "expect": "template/review"})
        codes.append(r.status_code)
    ts = [threading.Thread(target=click) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(codes) == [200, 409], codes
    sid = mj.load(job["job_id"])["short_id"]
    base = sid.rsplit("__motion", 1)[0] + "__motion"
    made = [p for p in config.OUTPUT_DIR.glob(f"{base}*/setup.json")
            if json.loads(p.read_text()).get("doc_path") == job["doc_path"]]
    assert len(made) == 1, made


def test_the_working_screen_names_the_model_and_the_time():
    """Real mode: "Writing the script with Claude Opus 5.5", about 90 s."""
    job = {"activity": None, "activity_info": None}
    real = config.STUB
    config.STUB = False
    try:
        from shorts import motion_models
        with motion_models.use():
            mj._activity(job, "script")
    finally:
        config.STUB = real
    assert job["activity"] == "Writing the script"
    assert job["activity_info"]["model"].startswith("Claude "), job["activity_info"]
    assert job["activity_info"]["eta_seconds"] == 90 and not job["activity_info"]["local"]


def test_one_screen_shows_every_finished_step_and_the_feed_knows_the_reel():
    """The one-screen view (StepMotion) lists each finished step with what was
    chosen; the player is told a stub reel has no voice; the reel carries the
    time the reels feed sorts by."""
    from fastapi.testclient import TestClient
    from shorts.server import app
    job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    s = mj.view(job)["summary"]
    assert set(s) == {"options", "topic", "approach", "template"}, set(s)
    assert s["template"]["value"] == "fix story" and s["topic"]["value"]
    job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed")); job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed")); job = _wait(mj.decide(job, "approve"))
    _to(job, "done", "done")
    s = mj.view(job)["summary"]
    assert set(s) == {"options", "topic", "approach", "template", "theme", "script", "scenes", "voice"}
    assert s["theme"]["value"] == "Explainer" and "shots" in s["script"]["value"]
    c = TestClient(app)
    plan = c.get(f"/api/motion/{job['short_id']}/plan").json()
    assert plan["voice"] == "stub", plan.get("voice")
    row = next(r for r in c.get("/api/motion").json()["reels"] if r["short_id"] == job["short_id"])
    assert row["created"] > 0 and row["has_plan"]


def test_a_recorded_reel_is_not_called_stub():
    from fastapi.testclient import TestClient
    from shorts.server import app
    job = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed")); job = mj.decide(job, "approve")
    job = _wait(mj.decide(job, "proceed")); job = _wait(mj.decide(job, "approve"))
    manifest = config.OUTPUT_DIR / job["short_id"] / "audio" / "manifest.json"
    data = json.loads(manifest.read_text())
    data["engine"] = "chatterbox"                    # as a real run writes it
    manifest.write_text(json.dumps(data))
    plan = TestClient(app).get(f"/api/motion/{job['short_id']}/plan").json()
    assert plan["voice"] == "recorded"


def test_the_http_routes():
    """The routes the web UI calls: upload, options, start, decide, resume,
    the job list, and resume-from-the-Motion-list."""
    from fastapi.testclient import TestClient
    from shorts.server import app
    c = TestClient(app)
    r = c.post("/api/motion-jobs", files={"file": ("react.md", DOC.read_bytes(), "text/markdown")})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    assert r.json()["status"] == "options" and r.json()["cost"]["cap"] == config.MAX_REEL_USD
    assert c.post("/api/motion-jobs", data={"text": "too short"}).status_code == 400
    o = c.get(f"/api/motion-jobs/{jid}/options").json()
    assert o["estimate"]["typical"] > 0 and o["character"]["options"] and o["language"]["options"]
    assert c.post(f"/api/motion-jobs/{jid}/start", json={"theme": "nope"}).status_code == 400
    r = c.post(f"/api/motion-jobs/{jid}/start", json={"theme": "classic_explainer",
                                                      "template": "fix_story"})
    assert r.status_code == 200 and r.json()["status"] in ("running", "review")  # the stub may finish first
    job = _wait(mj.load(jid))
    assert c.post(f"/api/motion-jobs/{jid}/decide", json={"action": "regenerate"}).status_code == 400
    r = c.post(f"/api/motion-jobs/{jid}/decide", json={"action": "skip"})
    assert r.json()["status"] == "stopped"
    r = c.post(f"/api/motion-jobs/{jid}/resume")
    assert r.json()["stage"] == "topic" and r.json()["status"] == "review"
    assert any(j["job_id"] == jid for j in c.get("/api/motion-jobs").json()["jobs"])
    assert c.get("/api/motion-jobs/000000000000").status_code == 404
    assert c.get("/api/motion-jobs/../etc").status_code == 404
    # resume from the Motion list: a reel's own job
    done = _run_to_theme({"theme": "classic_explainer", "template": "fix_story"})
    r = c.post(f"/api/motion/{done['short_id']}/job")
    assert r.status_code == 200 and r.json()["job_id"] == done["job_id"]
    assert c.post("/api/motion/no_such__motion/job").status_code == 404


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} motion job tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL MOTION JOB TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
