"""
RESTYLE_TO_STORY_REELS.md Step 9: unit tests for shorts/story_reel.py.

Stages setup..audio run for REAL under SHORTS_STUB=1 (fast, free, local —
the same stub pipeline every other *_test.py in this project already
exercises). MOST tests monkeypatch the render stage to a fake that just
writes a placeholder reel.mp4 — full end-to-end video rendering has its own
separate, slower, real coverage elsewhere (this step's own reply shows a
real, complete run). The two Step 9 Fix 3 tests below are the exception:
they exercise the REAL render stage, including a REAL `python -m
shorts.server` subprocess and a REAL Chrome capture, specifically because
that subprocess start/stop behavior is exactly what Fix 3 is — there is no
way to test "does this actually start and stop a server" without actually
starting and stopping one. Both use a freshly bound free port (never the
project's own default :8000, which may already have someone's own server
on it) and are slower than the rest of this file (~15-30s each) for
exactly that reason.

_run_setup is monkeypatched to a FIXED Topic/Section/understanding=None in
most tests — real topic SELECTION is its own paid LLM call with its own
test coverage elsewhere (select_workflow_test.py); this file is about
story_reel.py's OWN new orchestration logic (resumability, pauses,
--from/--force-stage, MAX_REEL_USD, the prerequisite checklist), not about
re-testing selection.

    SHORTS_STUB=1 python -m shorts.story_reel_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
import json
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path

from shorts import cast_sheets, checks, config, preflight, story_reel, usage, video
from shorts.parse import parse_markdown
from shorts.schema import ConceptMappingSet, MetaphorVerdict, StoryEvalReport, Topic

DOC = (
    "# Test Session\n\n"
    "## 1.1 Why the count never updates\n"
    "A plain variable does not survive a re-render — it is recreated from "
    "scratch every time the component function runs. useState instead keeps "
    "its value in a slot React owns, outside the function body, so the "
    "value read on the next render is the one written on the last one.\n\n"
    "## 1.2 How useState creates and updates state\n"
    "A plain variable does not survive a re-render — it is recreated from "
    "scratch every time the component function runs. useState instead keeps "
    "its value in a slot React owns, outside the function body, so the "
    "value read on the next render is the one written on the last one.\n"
)


def _doc_path() -> str:
    d = tempfile.mkdtemp(prefix="story_reel_test_")
    p = Path(d) / "doc.md"
    p.write_text(DOC, encoding="utf-8")
    return str(p)


def _fixed_setup_for(short_id: str):
    """A monkeypatch for story_reel._run_setup that always returns the SAME
    topic (id=short_id) against this file's own DOC — deterministic, no LLM
    call (the stub topic-selection call is skipped entirely, not just
    stubbed), so every test in this file gets a known, stable short_id."""
    def fixed(sections, requested_short_id):
        topic = Topic(id=short_id, topic="How does useState remember a value?",
                      why_it_matters="test", source_section_id=sections[1].section_id,
                      difficulty="medium")
        return topic, sections[1], None
    return fixed


def _fake_render(short_id, base_url):
    path = video.mp4_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"FAKE MP4 -- story_reel_test.py never spends time on a "
                     b"real Chrome capture; see the step's own reply for that "
                     b"separate manual verification")
    print(f"  wrote {path} (FAKE — test stub, no real browser capture)")
    return True


def _clean(short_id: str):
    """Cleans BOTH `short_id` itself and its Step 9 Fix 4 namespaced
    <short_id>__story variant — a fresh run's _run_setup fixture returns a
    Topic with id=short_id, but run() then assigns the REAL working id via
    _next_free_story_id(short_id), which is __story-suffixed unless that
    exact id is already taken. Cleaning only the bare short_id would leave
    the real (namespaced) directory from a previous test run behind."""
    for sid in (short_id, f"{short_id}__story"):
        shutil.rmtree(config.OUTPUT_DIR / sid, ignore_errors=True)
        (config.OUTPUT_DIR / f"{sid}.mapping.json").unlink(missing_ok=True)
        (config.OUTPUT_DIR / f"{sid}.story.json").unlink(missing_ok=True)
        (config.OUTPUT_DIR / f"{sid}.mapping.stub.json").unlink(missing_ok=True)


def _real_id(base_id: str) -> str:
    """What story_reel._next_free_story_id will assign for a freshly-
    cleaned base_id (see _clean above) — the ACTUAL working short_id a
    fresh (topic_short_id=None) run() call ends up using, per Step 9 Fix 4.
    Call this right after _clean(base_id), before run(), so nothing else
    can have created a colliding id in between."""
    return story_reel._next_free_story_id(base_id)


def _ensure_cast_sheets_once():
    """Every test in this file needs approved cast sheets to exist so
    ensure_cast_sheets short-circuits True with no prompt — reused from
    whatever a previous step already approved in this environment, or
    built here (free, stub) if genuinely missing."""
    for name in cast_sheets.CAST_ORDER:
        if not cast_sheets._approved_path(name).exists():
            cast_sheets.main(["--candidates", "1", "--character", name.lower(), "--yes"])
            cast_sheets.main(["--approve", name.lower(), "1"])


_ensure_cast_sheets_once()


class _patched:
    """Context manager: monkeypatch story_reel.<name> = value for the
    block, always restored on exit, even on failure."""
    def __init__(self, **patches):
        self.patches = patches
        self.originals = {}

    def __enter__(self):
        for name, value in self.patches.items():
            self.originals[name] = getattr(story_reel, name)
            setattr(story_reel, name, value)
        return self

    def __exit__(self, *exc):
        for name, value in self.originals.items():
            setattr(story_reel, name, value)


# ============================================================ prerequisites

def test_check_prerequisites_blocks_when_api_keys_missing_outside_stub():
    original_stub = config.STUB
    original_key = config.ANTHROPIC_API_KEY
    config.STUB = False
    config.ANTHROPIC_API_KEY = ""
    try:
        blocking, warnings = story_reel.check_prerequisites()
    finally:
        config.STUB = original_stub
        config.ANTHROPIC_API_KEY = original_key
    assert any("ANTHROPIC_API_KEY" in b for b in blocking), blocking
    print(f"   ok — outside SHORTS_STUB, a missing ANTHROPIC_API_KEY is a "
         f"BLOCKING prerequisite: {blocking}")


def test_check_prerequisites_never_blocks_under_stub():
    assert config.STUB, "this test must run under SHORTS_STUB=1"
    original_key = config.ANTHROPIC_API_KEY
    config.ANTHROPIC_API_KEY = ""
    try:
        blocking, warnings = story_reel.check_prerequisites()
    finally:
        config.ANTHROPIC_API_KEY = original_key
    assert blocking == [], blocking
    print("   ok — under SHORTS_STUB=1, missing API keys never block (nothing "
         "real is ever called)")


def test_missing_prerequisite_stops_before_any_stage_runs():
    """VERIFY: 'missing prerequisite -> checklist, no calls'."""
    original_stub = config.STUB
    original_key = config.ANTHROPIC_API_KEY
    config.STUB = False
    config.ANTHROPIC_API_KEY = ""
    setup_calls = {"n": 0}

    def counting_setup(*a, **kw):
        setup_calls["n"] += 1
        raise AssertionError("setup must never run when a prerequisite is missing")

    buf = io.StringIO()
    with _patched(_run_setup=counting_setup):
        try:
            with contextlib.redirect_stdout(buf):
                code = story_reel.run(_doc_path(), None, None, None, yes=True)
        finally:
            config.STUB = original_stub
            config.ANTHROPIC_API_KEY = original_key

    assert code == 1
    assert setup_calls["n"] == 0
    assert "Prerequisite checklist" in buf.getvalue()
    assert "Cannot proceed" in buf.getvalue()
    print("   ok — a missing blocking prerequisite prints the checklist and "
         "stops with exit code 1, WITHOUT running stage 1 (0 setup calls)")


def test_story_mode_banner_prints_first_before_the_prerequisite_checklist():
    """
    STEP 9 FIXES ROUND 9: "I keep accidentally generating explainer-mode
    reels instead of story mode" — run() must print an unmissable STORY
    MODE banner as the very first thing, ahead of even the prerequisite
    checklist, so it is obvious which pipeline is running before anything
    else scrolls past. Reuses the missing-prerequisite short-circuit (same
    as the test above) purely to keep this fast — the banner must appear
    even on a run that immediately stops."""
    original_stub = config.STUB
    original_key = config.ANTHROPIC_API_KEY
    config.STUB = False
    config.ANTHROPIC_API_KEY = ""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            story_reel.run(_doc_path(), None, None, None, yes=True)
    finally:
        config.STUB = original_stub
        config.ANTHROPIC_API_KEY = original_key

    out = buf.getvalue()
    assert ">>> STORY MODE <<<" in out
    banner_pos = out.find(">>> STORY MODE <<<")
    checklist_pos = out.find("Prerequisite checklist")
    assert banner_pos != -1 and checklist_pos != -1
    assert banner_pos < checklist_pos, (
        "the STORY MODE banner must print BEFORE the prerequisite checklist, "
        "not after")
    print("   ok — run() prints the STORY MODE banner first, before even the "
         "prerequisite checklist")


def test_mp4_path_is_reel_story_for_a_story_reel_and_plain_reel_for_an_explainer_one():
    """
    STEP 9 FIXES ROUND 9: the other half of the same fix — the short_id's
    own __story suffix (Step 9 Fix 4) already disambiguates the
    DIRECTORY, but the mp4 FILE ITSELF used to be literally named
    "reel.mp4" either way, indistinguishable once out of its folder.
    video.mp4_path now names it reel_STORY.mp4 for a story reel (detected
    by the presence of <short_id>.story.json) and leaves an explainer
    reel's reel.mp4 unchanged."""
    story_id = "story_reel_test_mp4_path_story"
    explainer_id = "story_reel_test_mp4_path_explainer"
    for sid in (story_id, explainer_id):
        (config.OUTPUT_DIR / f"{sid}.story.json").unlink(missing_ok=True)
        (config.OUTPUT_DIR / f"{sid}.json").unlink(missing_ok=True)
    try:
        (config.OUTPUT_DIR / f"{story_id}.story.json").write_text("{}", encoding="utf-8")
        (config.OUTPUT_DIR / f"{explainer_id}.json").write_text("{}", encoding="utf-8")

        assert video.is_story_reel(story_id) is True
        assert video.is_story_reel(explainer_id) is False
        assert video.mp4_path(story_id).name == "reel_STORY.mp4"
        assert video.mp4_path(explainer_id).name == "reel.mp4"
    finally:
        (config.OUTPUT_DIR / f"{story_id}.story.json").unlink(missing_ok=True)
        (config.OUTPUT_DIR / f"{explainer_id}.json").unlink(missing_ok=True)
    print("   ok — video.mp4_path names a story reel's file reel_STORY.mp4 and "
         "an explainer reel's file reel.mp4, keyed off is_story_reel")


# ==================================================== full run, end to end

def test_full_run_with_yes_produces_report_and_every_stage_output():
    short_id = "story_reel_test_full"
    _clean(short_id)
    real_id = _real_id(short_id)
    with _patched(_run_setup=_fixed_setup_for(short_id), stage_render=_fake_render):
        code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 0, code

    outdir = config.OUTPUT_DIR / real_id
    assert (config.OUTPUT_DIR / f"{real_id}.mapping.json").exists()
    assert (config.OUTPUT_DIR / f"{real_id}.story.json").exists()
    assert (outdir / "sample.done").exists()
    assert (outdir / "frames.done").exists()
    assert (outdir / "timings.json").exists()
    assert (outdir / "audio" / "mix.wav").exists()
    assert video.mp4_path(real_id).exists()

    report_path = outdir / "run_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["short_id"] == real_id
    assert set(report["by_stage"].keys()) == {
        "setup", "mapping", "shots", "sample", "frames", "audio", "render"}
    assert "needs_review" in report and "by_model" in report and "total_cost" in report
    print(f"   ok — a full --yes run produces every stage's output file plus "
         f"run_report.json with all 7 stages recorded, under its Step 9 Fix 4 "
         f"namespaced id ({real_id}, not the bare topic id {short_id}): "
         f"{list(report['by_stage'].keys())}")


# ============================================ STEP 9 FIX 3 — render's server

def _build_reel_ready_for_render(short_id: str) -> str:
    """setup..audio, for real (stub, free), stopping right before render —
    so FIX 3's tests (which exercise the REAL render stage: a real server
    subprocess, a real Chrome capture) have a real, complete fixture to
    render, without depending on any OTHER test in this file having
    already run first. Returns the REAL (Step 9 Fix 4 namespaced) short_id
    the fixture actually landed on, since a fresh run() never uses the
    bare id passed in."""
    real_id = _real_id(short_id)
    if (config.OUTPUT_DIR / real_id / "timings.json").exists():
        return real_id
    with _patched(_run_setup=_fixed_setup_for(short_id), stage_render=lambda *a: False):
        story_reel.run(_doc_path(), None, None, None, yes=True)
    return real_id


def test_render_starts_its_own_server_and_stops_it_afterward():
    short_id = _build_reel_ready_for_render("story_reel_test_render_autostart")
    video.mp4_path(short_id).unlink(missing_ok=True)
    (config.OUTPUT_DIR / short_id / "reel.stamp").unlink(missing_ok=True)

    port = video._free_port()
    base = f"http://127.0.0.1:{port}"
    assert not video._server_is_up(base), "the test's own free port must start empty"

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = story_reel.stage_render(short_id, base)
    out = buf.getvalue()

    assert ok, out
    assert video.mp4_path(short_id).exists()
    assert "starting `python -m shorts.server" in out
    assert "started by this runner" in out
    assert "stopped the server this runner started" in out

    # And the server this runner started is verifiably gone afterward —
    # not just a printed claim.
    for _ in range(20):
        if not video._server_is_up(base):
            break
        time.sleep(0.5)
    assert not video._server_is_up(base), (
        "the runner-started server must actually be stopped, not just claimed to be")
    print(f"   ok — stage_render starts its own server (port {port}), waits for "
         f"/api/health, renders a real reel.mp4, then stops the server it "
         f"started — verified both by the log and by re-probing the port")


def test_render_never_stops_a_server_it_did_not_start():
    short_id = _build_reel_ready_for_render("story_reel_test_render_preexisting")
    video.mp4_path(short_id).unlink(missing_ok=True)
    (config.OUTPUT_DIR / short_id / "reel.stamp").unlink(missing_ok=True)

    port = video._free_port()
    base = f"http://127.0.0.1:{port}"
    user_server = subprocess.Popen(
        [sys.executable, "-m", "shorts.server", "--port", str(port)],
        cwd=str(config.ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not video._server_is_up(base):
            time.sleep(0.5)
        assert video._server_is_up(base), "the test's own pre-started server never came up"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = story_reel.stage_render(short_id, base)
        out = buf.getvalue()

        assert ok, out
        assert "already answering" in out and "will not stop it" in out
        assert "stopped the server" not in out
        assert user_server.poll() is None, (
            "a server this runner did NOT start must never be terminated")
        assert video._server_is_up(base), "the pre-existing server must still be up"
    finally:
        user_server.terminate()
        try:
            user_server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            user_server.kill()
    print(f"   ok — stage_render detects an already-running server (port {port}) "
         f"and never stops it — the process is still alive, and /api/health "
         f"still answers, after stage_render returns")


# ======================================================== pause / decline

def test_declining_a_pause_stops_cleanly_and_does_not_persist_the_stage():
    short_id = "story_reel_test_decline"
    _clean(short_id)
    real_id = _real_id(short_id)

    def decline_mapping(prompt, yes):
        return prompt != "Approve mapping?"

    with _patched(_run_setup=_fixed_setup_for(short_id), _confirm=decline_mapping):
        code = story_reel.run(_doc_path(), None, None, None, yes=False)
    assert code == 1
    assert not (config.OUTPUT_DIR / f"{real_id}.mapping.json").exists(), (
        "a DECLINED stage's output must not be written — otherwise a rerun "
        "would silently treat it as already-approved and skip the pause")
    print("   ok — declining 'Approve mapping?' stops with exit code 1 and "
         "leaves NO mapping.json behind")


def test_rerun_after_a_decline_shows_the_same_pause_again():
    short_id = "story_reel_test_decline_rerun"
    _clean(short_id)
    real_id = _real_id(short_id)
    seen_prompts = []

    def decline_once(prompt, yes):
        seen_prompts.append(prompt)
        return prompt != "Approve mapping?"

    with _patched(_run_setup=_fixed_setup_for(short_id), _confirm=decline_once):
        story_reel.run(_doc_path(), None, None, None, yes=False)
    assert seen_prompts.count("Approve mapping?") == 1

    # Rerun with --topic=real_id (the id setup landed on during the first
    # call, above — --topic always names an EXACT existing reel, never the
    # bare pre-namespacing topic id), this time approving everything — the
    # mapping pause must be shown AGAIN (mapping.json didn't exist after
    # the decline), not silently skipped as "already resumed".
    with _patched(_run_setup=_fixed_setup_for(short_id), _confirm=lambda p, y: True,
                 stage_render=_fake_render):
        code = story_reel.run(_doc_path(), real_id, None, None, yes=False)
    assert code == 0, code
    assert (config.OUTPUT_DIR / f"{real_id}.mapping.json").exists()
    print("   ok — after a decline, --topic resumes and RE-SHOWS the mapping "
         "pause (it re-ran plan_story_mapping) rather than skipping it")


def test_approving_every_pause_completes_the_run():
    short_id = "story_reel_test_approve_all"
    _clean(short_id)
    prompts_seen = []

    def approve_all(prompt, yes):
        prompts_seen.append(prompt)
        return True

    with _patched(_run_setup=_fixed_setup_for(short_id), _confirm=approve_all,
                 stage_render=_fake_render):
        code = story_reel.run(_doc_path(), None, None, None, yes=False)
    assert code == 0, code
    for expected in ("Approve mapping?", "Approve shots?", "Approve sample?"):
        assert expected in prompts_seen, (expected, prompts_seen)
    print(f"   ok — approving every pause (without --yes) completes the "
         f"whole run: {prompts_seen}")


# ============================================================== resumability

def test_a_completed_stage_is_skipped_on_rerun():
    short_id = "story_reel_test_resume"
    _clean(short_id)
    real_id = _real_id(short_id)
    mapping_calls = {"n": 0}
    original_plan_story_mapping = story_reel.plan_story_mapping

    def counting_mapping(*a, **kw):
        mapping_calls["n"] += 1
        return original_plan_story_mapping(*a, **kw)

    with _patched(_run_setup=_fixed_setup_for(short_id), plan_story_mapping=counting_mapping,
                 stage_render=_fake_render):
        code1 = story_reel.run(_doc_path(), None, None, None, yes=True)
        assert code1 == 0
        assert mapping_calls["n"] == 1

        # A second full run, resumed by the REAL (Step 9 Fix 4 namespaced)
        # id the first run landed on, must not recompute mapping — every
        # stage's own output already exists.
        code2 = story_reel.run(_doc_path(), real_id, None, None, yes=True)
        assert code2 == 0
        assert mapping_calls["n"] == 1, "mapping must not be recomputed on a plain rerun"
    print("   ok — rerunning the same reel (--topic, no --force-stage) never "
         "recomputes an already-approved stage (mapping called exactly once "
         "across both runs)")


def test_force_stage_recomputes_that_stage_even_though_output_exists():
    short_id = "story_reel_test_force"
    _clean(short_id)
    real_id = _real_id(short_id)
    mapping_calls = {"n": 0}
    original_plan_story_mapping = story_reel.plan_story_mapping

    def counting_mapping(*a, **kw):
        mapping_calls["n"] += 1
        return original_plan_story_mapping(*a, **kw)

    with _patched(_run_setup=_fixed_setup_for(short_id), plan_story_mapping=counting_mapping,
                 stage_render=_fake_render):
        story_reel.run(_doc_path(), None, None, None, yes=True)
        assert mapping_calls["n"] == 1

        story_reel.run(_doc_path(), real_id, None, "mapping", yes=True)
        assert mapping_calls["n"] == 2, (
            "--force-stage mapping must recompute mapping even though "
            "mapping.json already exists")
    print("   ok — --force-stage mapping recomputes mapping on a rerun even "
         "though its output already exists (calls=2)")


def test_from_stage_skips_earlier_stages_without_checking_them():
    short_id = "story_reel_test_from"
    _clean(short_id)
    real_id = _real_id(short_id)
    setup_calls = {"n": 0}
    original_run_setup = _fixed_setup_for(short_id)

    def counting_setup(sections, requested_short_id):
        setup_calls["n"] += 1
        return original_run_setup(sections, requested_short_id)

    with _patched(_run_setup=counting_setup, stage_render=_fake_render):
        story_reel.run(_doc_path(), None, None, None, yes=True)
        assert setup_calls["n"] == 1

        # --from render, with --topic already set to the real (namespaced)
        # id, must never touch setup — it starts the loop directly at
        # render.
        code = story_reel.run(_doc_path(), real_id, "render", None, yes=True)
    assert code == 0
    assert setup_calls["n"] == 1, "setup must not run again when --from starts past it"
    print("   ok — --from render skips setup/mapping/shots/sample/frames/audio "
         "entirely and starts at render (setup called exactly once, not twice)")


# =========================================================== MAX_REEL_USD

def test_max_reel_usd_stops_before_exceeding_it():
    short_id = "story_reel_test_budget"
    _clean(short_id)
    original_max = config.MAX_REEL_USD
    config.MAX_REEL_USD = 0.0001   # any real (mocked) cost estimate exceeds this
    plan_calls = {"n": 0}

    def counting_mapping(*a, **kw):
        plan_calls["n"] += 1
        return None   # never actually reached if the gate works

    try:
        with _patched(_run_setup=_fixed_setup_for(short_id), plan_story_mapping=counting_mapping):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = story_reel.run(_doc_path(), None, None, None, yes=True)
    finally:
        config.MAX_REEL_USD = original_max

    assert code == 1
    assert plan_calls["n"] == 0, "no call may be made once the budget gate refuses"
    assert "MAX_REEL_USD" in buf.getvalue() and "Stopping before any call" in buf.getvalue()
    print(f"   ok — MAX_REEL_USD=$0.0001 refuses the mapping stage before any "
         f"call, printing why: "
         f"{[l for l in buf.getvalue().splitlines() if 'MAX_REEL_USD' in l]}")


def test_max_reel_usd_accounts_for_prior_stages_in_the_same_reel():
    """The cap is checked against THIS REEL's own running total (usage.
    since(reel_cursor)), not each stage's cost in isolation — tested
    directly against _money_gate (the one shared gate every money stage
    calls) rather than the whole run(), since usage.since() only reflects
    REAL recorded calls, and text-call stages record NOTHING under
    SHORTS_STUB=1 (see usage.py's own module docstring) — there is no way
    to make real stub execution accumulate a nonzero running total to
    test against, so this simulates "a prior stage already spent $0.08"
    directly via usage.record_image, the same ledger _money_gate reads."""
    original_max = config.MAX_REEL_USD
    config.MAX_REEL_USD = 0.10
    cursor = usage.mark()
    usage.record_image("prior-stage-for-this-test", "some-model", 0.08, estimated=False)
    try:
        # This stage's own worst-case ($0.05) is well under the $0.10 cap
        # ALONE — only the cumulative $0.08 + $0.05 = $0.13 exceeds it.
        plan = [preflight.ModelPlan("x", "y", 1, 0.05)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            allowed = story_reel._money_gate("mapping", "story_reel_test_budget_cumulative",
                                             plan, yes=True, reel_cursor=cursor)
    finally:
        config.MAX_REEL_USD = original_max

    assert allowed is False
    assert "MAX_REEL_USD" in buf.getvalue()
    print(f"   ok — a stage costing $0.05 alone (under a $0.10 cap) is still "
         f"refused once $0.08 was already spent earlier in this same reel "
         f"(cumulative $0.13 > $0.10): "
         f"{[l for l in buf.getvalue().splitlines() if 'MAX_REEL_USD' in l]}")


# ==================================================== STEP 9 FIX 4 — frozen

def _hash_tree(*paths: Path) -> dict:
    import hashlib
    out = {}
    for path in paths:
        if path.is_file():
            out[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file():
                    out[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def test_existing_explainer_reel_is_byte_for_byte_unchanged_by_a_story_run():
    """VERIFY (a): snapshot file hashes of an EXISTING explainer reel's
    folder, run a full stub story run whose topic id COLLIDES with it (the
    real scenario Fix 4 exists for — the topic-selection LLM landing on the
    same id an explainer reel already used), hash again -> identical."""
    explainer_id = "what_is_a_component"
    explainer_json = config.OUTPUT_DIR / f"{explainer_id}.json"
    explainer_dir = config.OUTPUT_DIR / explainer_id
    assert explainer_json.exists(), (
        f"fixture assumption: {explainer_json} must already exist in this "
        f"environment (a real explainer reel from an earlier step)")

    before = _hash_tree(explainer_json, explainer_dir)
    assert before, "fixture assumption: the explainer reel has at least one file"

    story_id = f"{explainer_id}__story"
    # Clean only the STORY namespace's own artifacts — NEVER the explainer
    # reel itself (explainer_json/explainer_dir are never touched by this
    # cleanup, on purpose: this test's whole point is that they survive).
    shutil.rmtree(config.OUTPUT_DIR / story_id, ignore_errors=True)
    (config.OUTPUT_DIR / f"{story_id}.mapping.json").unlink(missing_ok=True)
    (config.OUTPUT_DIR / f"{story_id}.story.json").unlink(missing_ok=True)

    with _patched(_run_setup=_fixed_setup_for(explainer_id), stage_render=_fake_render):
        code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 0

    after = _hash_tree(explainer_json, explainer_dir)
    assert before == after, (
        "the explainer reel's own files must be byte-for-byte unchanged — "
        "a story run must never modify, regenerate, or delete them")

    assert (config.OUTPUT_DIR / story_id).exists(), (
        "the story run's own output must exist under its OWN namespaced id")
    assert (config.OUTPUT_DIR / f"{story_id}.story.json").exists()
    print(f"   ok — a story run whose topic id collides with an existing "
         f"EXPLAINER reel ({explainer_id}) leaves every one of its "
         f"{len(before)} file(s) byte-for-byte unchanged; the story run "
         f"instead wrote its own files under {story_id}")


def test_id_collision_gets_a_numbered_suffix_without_touching_the_original():
    """VERIFY (b): id collision -> a new id is created, the original
    folder is untouched — this time colliding with an EXISTING STORY id
    (<base>__story already taken), which must fall through to a numbered
    suffix rather than a second '__story'."""
    base = "story_reel_test_collision_base"
    story_id = f"{base}__story"
    numbered_id = f"{story_id}_2"
    for sid in (story_id, numbered_id):
        shutil.rmtree(config.OUTPUT_DIR / sid, ignore_errors=True)
        (config.OUTPUT_DIR / f"{sid}.story.json").unlink(missing_ok=True)

    marker = '{"marker": "the ORIGINAL story reel — must never be touched"}'
    original_path = config.OUTPUT_DIR / f"{story_id}.story.json"
    original_path.write_text(marker, encoding="utf-8")
    try:
        assigned = story_reel._next_free_story_id(base)
        assert assigned == numbered_id, assigned
        assert original_path.read_text(encoding="utf-8") == marker, (
            "the original file at the collided id must be byte-for-byte unchanged")
        assert not story_reel._reel_exists(numbered_id), (
            "the numbered id itself must have been genuinely free")
    finally:
        original_path.unlink(missing_ok=True)
        (config.OUTPUT_DIR / f"{numbered_id}.story.json").unlink(missing_ok=True)
    print(f"   ok — with {story_id} already taken, _next_free_story_id "
         f"assigns a numbered suffix ({assigned}) instead, and the "
         f"original file's content is untouched: {marker!r}")


def test_never_overwrites_without_the_explicit_overwrite_flag():
    """The --overwrite <id> escape hatch: refused for an EXPLAINER id
    (never touched, no exception, file hash proves it), honored for a
    free/story id."""
    explainer_id = "what_is_a_component"
    explainer_json = config.OUTPUT_DIR / f"{explainer_id}.json"
    explainer_dir = config.OUTPUT_DIR / explainer_id
    before = _hash_tree(explainer_json, explainer_dir)

    short_id = "story_reel_test_overwrite_target"
    _clean(short_id)

    buf = io.StringIO()
    with _patched(_run_setup=_fixed_setup_for("anything")):
        with contextlib.redirect_stdout(buf):
            code = story_reel.run(_doc_path(), None, None, None, yes=True,
                                  overwrite_id=explainer_id)
    assert code == 1
    assert "refused" in buf.getvalue()
    after = _hash_tree(explainer_json, explainer_dir)
    assert before == after, "a refused --overwrite must never touch the target's files"

    with _patched(_run_setup=_fixed_setup_for("anything"), stage_render=_fake_render):
        code2 = story_reel.run(_doc_path(), None, None, None, yes=True,
                               overwrite_id=short_id)
    assert code2 == 0
    assert (config.OUTPUT_DIR / f"{short_id}.story.json").exists()
    print(f"   ok — --overwrite {explainer_id} (an explainer reel's own id) "
         f"is refused outright, file hashes unchanged; --overwrite {short_id} "
         f"(a free/story id) is honored")


def test_old_story_json_without_technical_term_still_loads_and_grades():
    """VERIFY (c): an old reel's JSON still loads (and can still be graded/
    rendered) in stub mode — simulated by taking a real, valid StoryScript
    and stripping the technical_term key entirely, the same shape a file
    persisted before Step 9 Fix 2 added that field genuinely has."""
    from shorts.schema import StoryScript
    real = json.loads((config.OUTPUT_DIR / "stub_e2e.story.json").read_text(encoding="utf-8"))
    old_shaped = dict(real)
    old_shaped.pop("technical_term", None)
    assert "technical_term" not in old_shaped

    story = StoryScript(**old_shaped)
    assert story.technical_term == "", (
        "a genuinely missing technical_term must default to '', not raise")

    from shorts import checks
    results = checks.run_story_graders(story, "irrelevant source text for this check",
                                       technical_term=story.technical_term)
    named = next(r for r in results if r.name == "concept_named_once")
    assert named.passed and "skipped" in named.reason, named.reason
    print(f"   ok — an old StoryScript with no technical_term key at all still "
         f"loads (defaults to ''), and run_story_graders still runs against it "
         f"without crashing — concept_named_once correctly skips rather than "
         f"failing on data that predates Step 9 Fix 2: {named.reason}")


def test_old_explainer_reel_json_still_loads():
    """The other half of VERIFY (c) — an OLD explainer reel is completely
    outside anything Step 9 touched (no ShortUnit/Beat schema change in
    this step at all), so this is a direct, simple confirmation rather
    than a simulated-old-data test."""
    from shorts.schema import ShortUnit
    path = config.OUTPUT_DIR / "what_is_a_component.json"
    assert path.exists(), f"fixture assumption: {path} must already exist"
    unit = ShortUnit(**json.loads(path.read_text(encoding="utf-8")))
    assert unit.short_id == "what_is_a_component"
    assert len(unit.beats) > 0
    print(f"   ok — an existing explainer reel's JSON ({path}) still loads "
         f"as a valid ShortUnit, unaffected by anything in this step "
         f"({len(unit.beats)} beat(s))")


def test_topic_flag_never_adopts_an_existing_explainer_reels_outputs():
    """Resumability only resumes a STORY run's own stages — --topic
    pointed at an EXISTING EXPLAINER reel's id (which has no setup.json,
    a story_reel.py-only marker) must be refused, not silently adopted as
    if it were a story run already in progress."""
    explainer_id = "what_is_a_component"
    assert not (config.OUTPUT_DIR / explainer_id / "setup.json").exists()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = story_reel.run(_doc_path(), explainer_id, None, None, yes=True)
    assert code == 1
    assert "no such reel in progress" in buf.getvalue()
    print(f"   ok — --topic {explainer_id} (an existing EXPLAINER reel's id, "
         f"with no setup.json) is refused, not silently adopted as an "
         f"in-progress story run")


# ==================================================== stale hook_line (Fix 1)

def test_force_stage_shots_regenerates_a_stale_hook_line_before_retrying_shots():
    """
    STEP 9 FIXES ROUND 3, FIX 1 — the exact scenario a real run hit:
    output/<short_id>.mapping.json was approved before checks.check_hook's
    4-opener rule existed, so its hook_line ("Ever click a counter that
    stubbornly keeps showing zero?") no longer passes. write_story_shots
    only ever COPIES mapping.hook_line onto the shots verbatim (see its
    own body) — it never regenerates it — so BEFORE this fix, --force-
    stage shots on this exact mapping.json would fail check_hook
    identically on every single retry, forever, no matter how many times
    shots itself was retried. This confirms the resume path now catches
    and repairs the stale field BEFORE stage_shots ever runs a call, and
    that the rest of the approved mapping (setting, entries) is untouched.
    """
    short_id = "story_reel_test_stale_hook"
    _clean(short_id)
    real_id = _real_id(short_id)
    with _patched(_run_setup=_fixed_setup_for(short_id), stage_render=_fake_render):
        code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 0, code

    mapping_path = config.OUTPUT_DIR / f"{real_id}.mapping.json"
    mapping = ConceptMappingSet.model_validate_json(mapping_path.read_text(encoding="utf-8"))
    stale_hook = "Ever click a counter that stubbornly keeps showing zero?"
    assert not checks.check_hook(stale_hook, technical_term=mapping.technical_term).passed, (
        "the reproduction hook_line must itself fail the CURRENT check_hook "
        "for this test to mean anything")
    original_setting = mapping.setting
    original_entries = [m.concept_rule for m in mapping.mapping]
    mapping.hook_line = stale_hook
    mapping_path.write_text(mapping.model_dump_json(indent=2), encoding="utf-8")

    with _patched(_run_setup=_fixed_setup_for(short_id), stage_render=_fake_render):
        code = story_reel.run(_doc_path(), real_id, None, "shots", yes=True)
    assert code == 0, code

    fixed = ConceptMappingSet.model_validate_json(mapping_path.read_text(encoding="utf-8"))
    assert checks.check_hook(fixed.hook_line, technical_term=fixed.technical_term).passed, (
        f"hook_line {fixed.hook_line!r} still fails check_hook after --force-stage "
        f"shots resumed a stale mapping — the old bug would loop on this forever")
    assert fixed.hook_line != stale_hook
    assert fixed.setting == original_setting, "only hook_line may change, never the rest of the mapping"
    assert [m.concept_rule for m in fixed.mapping] == original_entries

    story_path = config.OUTPUT_DIR / f"{real_id}.story.json"
    assert story_path.exists(), "shots must have completed after the hook_line was repaired"
    print(f"   ok — --force-stage shots on a mapping with a stale (pre-4-opener) "
         f"hook_line regenerates ONLY hook_line ({stale_hook!r} -> "
         f"{fixed.hook_line!r}), leaves setting/entries untouched, then "
         f"completes shots successfully")


def test_declining_the_stale_hook_line_fix_leaves_mapping_json_untouched():
    """Same 'declining means try again, not skip ahead' contract every
    other pause in this runner keeps (see stage_mapping/stage_shots's own
    notes) — a declined hook_line correction must not be written."""
    short_id = "story_reel_test_stale_hook_decline"
    _clean(short_id)
    real_id = _real_id(short_id)
    with _patched(_run_setup=_fixed_setup_for(short_id), stage_render=_fake_render):
        code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 0, code

    mapping_path = config.OUTPUT_DIR / f"{real_id}.mapping.json"
    mapping = ConceptMappingSet.model_validate_json(mapping_path.read_text(encoding="utf-8"))
    mapping.hook_line = "Ever click a counter that stubbornly keeps showing zero?"
    mapping_path.write_text(mapping.model_dump_json(indent=2), encoding="utf-8")
    before = mapping_path.read_text(encoding="utf-8")

    def decline_hook_fix(prompt, yes):
        return prompt != "Approve corrected hook_line?"

    with _patched(_run_setup=_fixed_setup_for(short_id), _confirm=decline_hook_fix):
        code = story_reel.run(_doc_path(), real_id, None, "shots", yes=False)
    assert code == 1
    after = mapping_path.read_text(encoding="utf-8")
    assert before == after, "declining the hook_line fix must not change mapping.json on disk"
    print("   ok — declining 'Approve corrected hook_line?' stops with exit "
         "code 1 and leaves mapping.json byte-for-byte unchanged")


def test_fix_stale_hook_line_is_a_noop_when_hook_line_already_passes():
    """The common case (nothing stale) must cost nothing and change
    nothing — _fix_stale_hook_line only acts when check_hook actually
    fails on the resumed mapping."""
    short_id = "story_reel_test_stale_hook_noop"
    _clean(short_id)
    real_id = _real_id(short_id)
    with _patched(_run_setup=_fixed_setup_for(short_id), stage_render=_fake_render):
        code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 0, code

    mapping_path = config.OUTPUT_DIR / f"{real_id}.mapping.json"
    mapping = ConceptMappingSet.model_validate_json(mapping_path.read_text(encoding="utf-8"))
    assert checks.check_hook(mapping.hook_line, technical_term=mapping.technical_term).passed, (
        "fixture assumption: a freshly generated mapping's hook_line already "
        "passes the current check_hook")

    cursor = usage.mark()
    fixed = story_reel._fix_stale_hook_line(
        real_id, mapping, None, None, None, "", True, cursor)
    assert fixed is mapping
    assert fixed.hook_line == mapping.hook_line
    spend = usage.since(cursor)
    assert spend["calls"] == 0 and spend["cost"] == 0.0, (
        "a hook_line that already passes check_hook must not spend anything")
    print("   ok — _fix_stale_hook_line is a zero-cost no-op when the resumed "
         "mapping's hook_line already passes the current check_hook")


# ============================================ metaphor judge visibility (Fix 5)

def test_giving_up_names_the_metaphor_judge_and_prints_its_verdicts_when_it_alone_fails():
    """
    STEP 9 FIXES ROUND 5: a real run had every one of the 15 free
    checks.run_story_graders results print PASS, so the ONLY thing that
    could have failed was judge_story_metaphors — but skills.audit.
    audit_story's own StoryEvalReport (verdicts + per-entry problem text)
    was never printed anywhere, leaving no way to see WHY it rejected the
    script. Confirms stage_shots now (a) names the metaphor judge
    specifically in the GIVING UP message when it alone is what failed,
    and (b) prints every verdict, with the problem text for each reject.
    """
    short_id = "story_reel_test_judge_reject"
    _clean(short_id)

    all_pass_results = [checks.GraderResult("stub_check", True, "ok")]
    reject_report = StoryEvalReport(verdicts=[
        MetaphorVerdict(concept_rule="a plain variable does not survive a re-render",
                       faithful=False,
                       problem="implies a behavior the source never states"),
        MetaphorVerdict(concept_rule="useState keeps the value across renders",
                       faithful=True),
    ])

    def fake_audit_story(story, source_text, technical_term=""):
        return all_pass_results, reject_report

    buf = io.StringIO()
    with _patched(_run_setup=_fixed_setup_for(short_id), audit_story=fake_audit_story):
        with contextlib.redirect_stdout(buf):
            code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 1
    out = buf.getvalue()
    assert "GIVING UP — the final shots failed the metaphor judge" in out
    assert "metaphor judge verdicts:" in out
    assert ("[REJECT] a plain variable does not survive a re-render — implies a "
           "behavior the source never states") in out
    assert "[PASS] useState keeps the value across renders" in out
    print("   ok — GIVING UP names the metaphor judge specifically (not the "
         "ambiguous 'free story graders or the metaphor judge') and prints "
         "every verdict, with problem text on each reject, when the judge "
         "alone is what failed")


def test_giving_up_names_only_free_graders_when_the_judge_never_runs():
    """audit_story only calls the judge once every free check passes (see
    its own body) — when a free check fails, report is None and the judge
    never ran at all, so the message must not imply it did."""
    short_id = "story_reel_test_judge_never_ran"
    _clean(short_id)

    def fake_audit_story(story, source_text, technical_term=""):
        return [checks.GraderResult("stub_check", False, "a free check failed")], None

    buf = io.StringIO()
    with _patched(_run_setup=_fixed_setup_for(short_id), audit_story=fake_audit_story):
        with contextlib.redirect_stdout(buf):
            code = story_reel.run(_doc_path(), None, None, None, yes=True)
    assert code == 1
    out = buf.getvalue()
    assert "GIVING UP — the final shots failed the free story graders:" in out
    assert "metaphor judge" not in out
    print("   ok — GIVING UP names only the free story graders, with no mention "
         "of the metaphor judge, when a free check failure means the judge "
         "never ran at all")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} story_reel tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL STORY_REEL TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
