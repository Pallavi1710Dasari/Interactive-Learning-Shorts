"""
RESTYLE_TO_MOTION_REELS.md phase 1: the motion script contract.

Covers write_motion_script's retry and hook-only repair paths, the
motion_reel runner's setup -> script stages and resume, the REEL_STYLE
switch, and the change request's "no image generation and no paid calls in
motion mode" rule. The graders themselves are covered case by case in
evals/cases.yaml (E129-E156).

No API key, no network, no real LLM calls. The runner is pointed at a temp
directory, so nothing under output/ is created or touched.

    SHORTS_STUB=1 python -m shorts.motion_script_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from shorts import checks, config, imagegen, motion_reel, usage
from shorts.parse import find_section, parse_markdown
from shorts.schema import MotionScript, MotionScriptDraft, MotionHookFix, Topic
from shorts.skills import script as script_mod

ROOT = Path(__file__).resolve().parent.parent
REACT_DOC = ROOT / "content" / "react_usestate_basics.md"
GOLDEN = ROOT / "evals" / "fixtures" / "motion" / "usestate_golden.json"


def _golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _draft(data: dict) -> MotionScriptDraft:
    return MotionScriptDraft(**{k: data[k] for k in (
        "hook_question", "concept_name", "promise", "icon_vocabulary", "takeaways", "shots")})


def _react_inputs():
    sections = parse_markdown(REACT_DOC)
    section = find_section(sections, "7.2")
    topic = Topic(id="why_plain_variable_fails", topic="Why does a plain variable not update?",
                  why_it_matters="w", source_section_id="7.2", difficulty="easy")
    source = "\n\n".join(s.text for s in sections)
    return topic, section, source


@contextlib.contextmanager
def _fake_ask_json(answers: list):
    """Replace skills.script.ask_json with one that hands back `answers` in
    order, recording (schema name, user prompt) for every call."""
    calls: list[tuple[str, str]] = []
    real = script_mod.ask_json

    def fake(system, user, model_cls, **kw):
        calls.append((model_cls.__name__, user))
        return answers.pop(0)
    script_mod.ask_json = fake
    try:
        yield calls
    finally:
        script_mod.ask_json = real


@contextlib.contextmanager
def _temp_output():
    real = config.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as d:
        config.OUTPUT_DIR = Path(d)
        try:
            yield Path(d)
        finally:
            config.OUTPUT_DIR = real


# ------------------------------------------------------------ write_motion_script

def test_stub_script_passes_every_grader_at_no_cost():
    topic, section, source = _react_inputs()
    cursor = usage.mark()
    script, results = script_mod.write_motion_script(
        topic, section, short_id="t__motion", source_text=source, next_topic="Next")
    assert script is not None, [str(r) for r in results if not r.passed]
    assert checks.all_passed(results)
    assert script.reel_style == "motion" and script.short_id == "t__motion"
    assert script.next_topic == "Next" and script.series == config.MOTION_SERIES
    assert [s.id for s in script.shots] == [f"s{i:02d}" for i in range(1, 12)]
    spend = usage.since(cursor)
    assert spend["calls"] == 0 and spend["cost"] == 0.0, spend


def test_hook_only_failure_regenerates_only_the_hook():
    topic, section, source = _react_inputs()
    data = _golden()
    good_hook = data["shots"][0]
    bad = json.loads(json.dumps(data))
    bad["shots"][0]["speech"] = "Have you ever wondered how React handles a button?"
    bad["shots"][0]["captions"] = [{"text": "Have you ever wondered"},
                                   {"text": "how React handles"}, {"text": "a button?"}]
    fix = MotionHookFix(hook_question=data["hook_question"], speech=good_hook["speech"],
                        captions=good_hook["captions"], visual=good_hook["visual"])
    with _fake_ask_json([_draft(bad), fix]) as calls:
        script, results = script_mod.write_motion_script(
            topic, section, short_id="t__motion", source_text=source)
    assert script is not None and checks.all_passed(results)
    assert [c[0] for c in calls] == ["MotionScriptDraft", "MotionHookFix"], calls
    assert script.shots[0].speech == good_hook["speech"]
    assert [s.speech for s in script.shots[1:]] == [s["speech"] for s in data["shots"][1:]]


def test_non_hook_failure_retries_the_whole_script_with_reasons():
    topic, section, source = _react_inputs()
    data = _golden()
    bad = json.loads(json.dumps(data))
    bad["shots"][3]["code"] = ["let likes = 1;"]          # a third code shot
    with _fake_ask_json([_draft(bad), _draft(data)]) as calls:
        script, results = script_mod.write_motion_script(
            topic, section, short_id="t__motion", source_text=source)
    assert script is not None and checks.all_passed(results)
    assert [c[0] for c in calls] == ["MotionScriptDraft", "MotionScriptDraft"]
    assert "FAILED REVIEW" in calls[1][1] and "3 shots show code" in calls[1][1]


def test_gives_up_after_the_retry_budget():
    topic, section, source = _react_inputs()
    bad = _golden()
    bad["shots"][3]["code"] = ["let likes = 1;"]
    answers = [_draft(bad) for _ in range(config.MAX_MOTION_SCRIPT_RETRIES)]
    with _fake_ask_json(answers) as calls:
        script, results = script_mod.write_motion_script(
            topic, section, short_id="t__motion", source_text=source)
    assert script is None
    assert len(calls) == config.MAX_MOTION_SCRIPT_RETRIES
    assert any(not r.passed and r.name == "motion_code_shots" for r in results)


def test_hook_fix_budget_is_two_attempts():
    topic, section, source = _react_inputs()
    data = _golden()
    bad = json.loads(json.dumps(data))
    bad["shots"][0]["speech"] = "Have you ever wondered how React handles a button?"
    bad["shots"][0]["captions"] = [{"text": "Have you ever wondered"},
                                   {"text": "how React handles"}, {"text": "a button?"}]
    still_bad = MotionHookFix(hook_question="How?", speech=bad["shots"][0]["speech"],
                              captions=bad["shots"][0]["captions"])
    answers = [_draft(bad), still_bad, still_bad, _draft(data)]
    with _fake_ask_json(answers) as calls:
        script, _ = script_mod.write_motion_script(
            topic, section, short_id="t__motion", source_text=source)
    names = [c[0] for c in calls]
    assert names == ["MotionScriptDraft", "MotionHookFix", "MotionHookFix",
                     "MotionScriptDraft"], names
    assert config.MAX_MOTION_HOOK_FIX_RETRIES == 2
    assert script is not None


# --------------------------------------------------------------------- runner

def _run_runner(*args: str) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = motion_reel.main([str(REACT_DOC), *args])
    return code, buf.getvalue()


def test_runner_setup_and_script_then_resume():
    with _temp_output() as out:
        code, text = _run_runner("--yes")
        assert code == 0, text
        [motion_file] = list(out.glob("*.motion.json"))
        short_id = motion_file.name[: -len(".motion.json")]
        assert short_id.endswith("__motion")
        assert (out / short_id / "setup.json").exists()
        script = MotionScript.model_validate_json(motion_file.read_text(encoding="utf-8"))
        assert script.reel_style == "motion" and len(script.shots) == 11
        assert "Approve shot list?" in text and "scenes: not built yet" in text

        code, text = _run_runner("--topic", short_id)
        assert code == 0, text
        assert "setup: resumed" in text and "script: resumed" in text


def test_runner_declined_gate_saves_nothing():
    # Not interactive and no --yes: every gate defaults to "no decision".
    real_stdin = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        with _temp_output() as out:
            code, text = _run_runner()
            assert code == 1, text
            assert not list(out.glob("*.motion.json"))
    finally:
        sys.stdin = real_stdin


def test_runner_ids_never_collide_with_other_styles():
    with _temp_output() as out:
        (out / "topic_x.json").write_text("{}", encoding="utf-8")
        (out / "topic_x__motion.story.json").write_text("{}", encoding="utf-8")
        assert motion_reel._next_free_motion_id("topic_x") == "topic_x__motion_2"


def test_next_topic_comes_from_the_document():
    sections = parse_markdown(REACT_DOC)
    assert motion_reel.next_topic_for(sections, "7.2", ["7.2", "7.3"]) == \
        "What state actually means in a React component"
    assert motion_reel.next_topic_for(sections, "7.4", ["7.4"]) == ""


# --------------------------------------------------------- no image, no spend

def test_motion_mode_makes_no_image_or_paid_calls():
    """The change request's rule 4: no image generation in motion mode."""
    def forbidden(*a, **kw):
        raise AssertionError("motion mode called image generation")
    real = {n: getattr(imagegen, n) for n in ("generate_bytes", "render_frame", "select_provider")}
    for n in real:
        setattr(imagegen, n, forbidden)
    try:
        with _temp_output():
            cursor = usage.mark()
            code, text = _run_runner("--yes")
            assert code == 0, text
            spend = usage.since(cursor)
            assert spend["calls"] == 0 and spend["cost"] == 0.0, spend
    finally:
        for n, f in real.items():
            setattr(imagegen, n, f)
    source = (ROOT / "shorts" / "motion_reel.py").read_text(encoding="utf-8")
    assert "import imagegen" not in source and "imagegen." not in source


# ------------------------------------------------------------------ REEL_STYLE

def _python(env_extra: dict, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_extra, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_reel_style_is_validated():
    ok = _python({"REEL_STYLE": "motion"}, "-c", "from shorts import config; print(config.REEL_STYLE)")
    assert ok.returncode == 0 and ok.stdout.strip() == "motion", ok.stderr
    bad = _python({"REEL_STYLE": "motoin"}, "-c", "from shorts import config")
    assert bad.returncode != 0 and "is not one of" in bad.stderr, bad.stderr


def test_run_py_points_motion_to_its_own_runner():
    r = _python({"REEL_STYLE": "motion"}, "-m", "shorts.run", str(REACT_DOC))
    assert r.returncode == 0, r.stderr
    assert "python -m shorts.motion_reel" in r.stdout
    assert "selected" not in r.stdout   # stopped before topic selection


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} motion script tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL MOTION SCRIPT TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
