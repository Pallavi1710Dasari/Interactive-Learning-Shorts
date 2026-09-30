"""
RESTYLE_TO_STORY_REELS.md Step 8 Part 0 #4: unit + integration tests for
shorts/preflight.py and its wiring into the three real jobs that spend money
— shorts/run.py's build_one_story ("story"), shorts/story_frames.py's run()
("frames"), and shorts/cast_sheets.py's cmd_candidates ("cast_sheets").

No API key, no network — every real-job test below runs under SHORTS_STUB=1
and asserts the job's own first real ask_json/provider call never happens
without --yes.

    SHORTS_STUB=1 python -m shorts.preflight_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
import json
import shutil

from shorts import config, preflight
from shorts.schema import Section, Topic


# ==================================================================== unit

def test_model_plan_cost_multiplies_calls_by_per_call_price():
    m = preflight.ModelPlan(label="x", model="m", planned_calls=4, cost_per_call=0.125)
    assert m.cost == 0.5
    print(f"   ok — ModelPlan.cost is planned_calls x cost_per_call: {m.cost}")


def test_text_cost_per_call_matches_the_usage_price_table():
    # claude-sonnet-5 is in usage.PRICES: (2.0e-6, 10.0e-6) per input/output token.
    cost = preflight.text_cost_per_call("claude-sonnet-5", 1000, 500)
    expected = 1000 * 2.0e-6 + 500 * 10.0e-6
    assert abs(cost - expected) < 1e-9, (cost, expected)
    print(f"   ok — text_cost_per_call('claude-sonnet-5', 1000, 500) = "
         f"${cost:.6f}, matching usage.PRICES directly")


def test_text_cost_per_call_is_zero_for_a_model_with_no_price_table_entry():
    """
    STEP 9 FIXES ROUND 14: this test used to name MODEL_STORY_VISION_JUDGE's
    gemini-3.8-flash as ITS OWN example of a genuinely-free model (config.py's
    old note) — a real sample stage showed that was wrong (Google's own free
    tier does not carry through OpenRouter, the actual gateway every call
    here goes through): $0.0000 estimated, $0.0430 actual. gemini-3.8-flash
    now has a real, regression-fitted usage.PRICES entry (see that table's
    own note) specifically so this is no longer true for it. The underlying
    behavior this test is actually guarding — a model with NO price-table
    entry at all estimates $0.0, rather than silently guessing — is still
    real and still worth a test; it just needs a genuinely-unpriced model
    name now, not one that used to be (wrongly) unpriced.
    """
    cost = preflight.text_cost_per_call("a-totally-unknown-model-xyz", 5000, 5000)
    assert cost == 0.0, cost
    print("   ok — a model with no price-table entry at all estimates $0.0, "
         "not a guessed price")


def test_gemini_3_8_flash_no_longer_estimates_free():
    """The other half of round 14: the specific model this bug was actually
    about must now come back with a real, non-zero estimate."""
    cost = preflight.text_cost_per_call(config.MODEL_STORY_VISION_JUDGE, 2900, 600)
    assert cost > 0.0, cost
    print(f"   ok — {config.MODEL_STORY_VISION_JUDGE!r} now estimates "
         f"${cost:.4f} for a realistic vision-judge call, not $0.0")


def test_write_preflight_json_merges_by_job_name_not_overwrites():
    short_id = "preflight_merge_test"
    shutil.rmtree(config.OUTPUT_DIR / short_id, ignore_errors=True)

    plan_a = preflight.build_plan("story", short_id,
                                  [preflight.ModelPlan("story_mapping", "m1", 2, 0.01)])
    plan_b = preflight.build_plan("frames", short_id,
                                  [preflight.ModelPlan("image:gemini", "m2", 3, 0.03)])
    preflight.write_preflight_json(short_id, plan_a)
    path = preflight.write_preflight_json(short_id, plan_b)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert set(saved.keys()) == {"story", "frames"}, saved.keys()
    assert saved["story"]["models"][0]["model"] == "m1"
    assert saved["frames"]["models"][0]["model"] == "m2"
    print(f"   ok — writing a 'frames' plan after a 'story' plan for the same "
         f"short_id keeps both under their own job key in {path}: "
         f"{list(saved.keys())}")


def test_write_preflight_json_path_override_for_reel_agnostic_jobs():
    # cast_sheets.py's own use: no short_id really applies (a sheet is
    # shared across reels), so it points this at its own shared file.
    override = config.OUTPUT_DIR / "preflight_path_override_test" / "preflight.json"
    override.unlink(missing_ok=True)
    plan = preflight.build_plan("cast_sheets", "rahul",
                                [preflight.ModelPlan("image:gemini", "m3", 1, 0.02)])
    path = preflight.write_preflight_json("rahul", plan, path=override)
    assert path == override
    assert override.exists()
    print(f"   ok — an explicit path= overrides the reel-scoped default: {path}")


def test_run_preflight_blocks_without_yes_and_proceeds_with_yes():
    short_id = "preflight_gate_test"
    shutil.rmtree(config.OUTPUT_DIR / short_id, ignore_errors=True)
    usages = [preflight.ModelPlan("story_mapping", config.MODEL_GENERATOR, 1, 0.01)]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        proceed = preflight.run_preflight("story", short_id, usages, yes=False)
    assert proceed is False
    assert "Re-run with --yes to proceed." in buf.getvalue()
    assert (config.OUTPUT_DIR / short_id / "preflight.json").exists(), (
        "the plan must still be written even when --yes is missing — a human "
        "deciding whether to proceed needs the file, not just the printout")

    proceed = preflight.run_preflight("story", short_id, usages, yes=True)
    assert proceed is True
    print("   ok — run_preflight returns False (and prints the re-run hint) "
         "without --yes, True with it, writing preflight.json either way")


# =============================================================== integration

def _sections():
    import tempfile
    from pathlib import Path
    from shorts.parse import parse_markdown
    SOURCE = ("A plain variable does not survive a re-render — it is recreated "
             "from scratch every time the component function runs. useState "
             "instead keeps its value in a slot React owns, outside the function "
             "body, so the value read on the next render is the one written on "
             "the last one.")
    doc = ("# Stub Session\n\n"
          "## 1.1 Why the count never updates\n"
          f"{SOURCE}\n\n"
          "## 1.2 How useState creates and updates state\n"
          f"{SOURCE}\n")
    with tempfile.TemporaryDirectory() as d:
        doc_path = Path(d) / "stub_doc.md"
        doc_path.write_text(doc, encoding="utf-8")
        return parse_markdown(str(doc_path))


def test_build_one_story_never_calls_plan_story_mapping_without_yes():
    from shorts import run as run_mod

    called = {"n": 0}
    original = run_mod.plan_story_mapping

    def counting(*a, **kw):
        called["n"] += 1
        return original(*a, **kw)

    run_mod.plan_story_mapping = counting
    try:
        section = _sections()[1]
        topic = Topic(id="preflight_story_gate", topic="How does useState remember a value?",
                     why_it_matters="test", source_section_id=section.section_id,
                     difficulty="medium")
        out_path = config.OUTPUT_DIR / f"{topic.id}.story.json"
        out_path.unlink(missing_ok=True)

        result = run_mod.build_one_story(topic, section, "s1", [section], yes=False)
        assert result is None
        assert called["n"] == 0, "plan_story_mapping must never run without --yes"
        preflight_path = config.OUTPUT_DIR / topic.id / "preflight.json"
        assert preflight_path.exists()
        saved = json.loads(preflight_path.read_text(encoding="utf-8"))
        assert saved["story"]["job"] == "story"
        assert not out_path.exists()
    finally:
        run_mod.plan_story_mapping = original

    print(f"   ok — build_one_story(..., yes=False) writes {preflight_path}, "
         f"prints the plan, and returns None WITHOUT ever calling "
         f"plan_story_mapping (0 calls recorded)")


def test_story_frames_run_never_calls_the_provider_without_yes():
    from shorts import cast_sheets, imagegen, story_frames

    short_id = "stub_e2e"   # the shared fixture story every story_frames test uses
    shutil.rmtree(config.OUTPUT_DIR / short_id, ignore_errors=True)
    story_path = config.OUTPUT_DIR / f"{short_id}.story.json"
    if not story_path.exists():
        import shorts.story_mode_test as smt
        smt.test_full_story_path_runs_end_to_end_under_stub()
    # A previous test in this file (or in cast_sheets_test.py, alphabetically
    # sorted before this one under main()'s own test loop) may have cleared
    # assets/cast/ — story_frames.run needs every character's approved sheet.
    for name in cast_sheets.CAST_ORDER:
        if not cast_sheets._approved_path(name).exists():
            cast_sheets.main(["--candidates", "1", "--character", name.lower(), "--yes"])
            cast_sheets.main(["--approve", name.lower(), "1"])
    story = story_frames.load_story(short_id)
    shots = story_frames.select_sample(story_frames._scene_shots(story), 2)
    imagegen.reset_call_count(short_id)

    calls = []
    original = imagegen.StubImageProvider.generate
    imagegen.StubImageProvider.generate = lambda self, *a, **kw: (
        calls.append(1), original(self, *a, **kw))[1]
    try:
        code = story_frames.run(short_id, shots, story, dry_run=False, yes=False)
    finally:
        imagegen.StubImageProvider.generate = original

    assert code == 1
    assert not calls, "no provider call may happen without --yes"
    preflight_path = config.OUTPUT_DIR / short_id / "preflight.json"
    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert saved["frames"]["job"] == "frames"
    assert any(m["label"].startswith("image:") for m in saved["frames"]["models"])
    print(f"   ok — story_frames.run(..., yes=False) writes {preflight_path} "
         f"under the 'frames' job and calls the provider 0 times")


def test_cast_sheets_candidates_never_calls_the_provider_without_yes():
    from shorts import cast_sheets, imagegen

    shutil.rmtree(cast_sheets.ASSETS_DIR, ignore_errors=True)
    shutil.rmtree(cast_sheets.CANDIDATES_DIR, ignore_errors=True)
    calls = []
    original = imagegen.StubImageProvider.generate
    imagegen.StubImageProvider.generate = lambda self, *a, **kw: (
        calls.append(1), original(self, *a, **kw))[1]
    try:
        code = cast_sheets.cmd_candidates(2, "rahul", dry_run=False, yes=False)
    finally:
        imagegen.StubImageProvider.generate = original

    assert code == 1
    assert not calls
    preflight_path = cast_sheets.CANDIDATES_DIR / "preflight.json"
    saved = json.loads(preflight_path.read_text(encoding="utf-8"))
    assert saved["cast_sheets"]["job"] == "cast_sheets"
    print(f"   ok — cast_sheets.cmd_candidates(..., yes=False) writes "
         f"{preflight_path} under the 'cast_sheets' job and calls the "
         f"provider 0 times")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} preflight tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL PREFLIGHT TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
