"""
The other fixes found in the first real motion reel's run
(output/what_state_means__motion, 2026-10-09; its script is the fixture
evals/fixtures/motion/what_state_means_script.json):

  - cost: "reel total, every run" left out earlier runs' setup, theme and
    script. The reel's cost.json is now written after every call and when a
    run ends however it ends, and MAX_REEL_USD counts earlier runs too;
  - source scope: the reel's running example (the counter, `let count = 0`
    inside Counter) came from 7.2 while its section was 7.4, and nothing
    failed. The source-scope rule (2026-10-10): the explanation and the
    running example come from the selected section; other sections may supply
    supporting numbers and defined terms, labelled with their section in the
    facts table. Checked by motion_example_from_selected;
  - the approach: it said "how useState is called is out of scope" and s08
    still showed the call. What an approved approach rules out is now in the
    script prompt and checked (motion_respects_approach);
  - routing: the `screen` call ran on claude-sonnet-5, outside
    motion_models.yaml. It is routed now, and during a motion run an unrouted
    call is an error before anything is sent.

    SHORTS_STUB=1 python -m shorts.motion_first_reel_fixes_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
from pathlib import Path
from types import SimpleNamespace

from shorts.testing import isolate_output
isolate_output()

from shorts import checks, config, llm, motion_models, motion_reel, usage
from shorts.parse import find_section, parse_markdown, story_evidence_pool
from shorts.schema import MotionScript, TeachingApproach
from shorts.skills import script as script_skill

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = MotionScript(**json.loads((ROOT / "evals/fixtures/motion/what_state_means_script.json").read_text()))
SECTIONS = parse_markdown(str(ROOT / "content/react_usestate_basics.md"))
SID = "what_state_means__motion"
#: The approach's exclusion, as the real run's gate showed it.
APPROACH = TeachingApproach(primary="comparison", rationale=(
    "A before-and-after contrast shows what React keeps. How useState is called is out of "
    "scope; this reel is about what state means."))


def _fake_call(cost: float, label: str = "motion_theme"):
    resp = SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                                                 model_extra={"cost": cost}))
    return usage.record(label, "anthropic/claude-opus-5.5", resp)


# ======================================================================= cost

def test_a_run_that_dies_still_records_its_spend():
    """Setup, theme and script spent money, then the run raised: the spend is
    in cost.json, and the next run's total includes it."""
    real = motion_reel._run

    def dying(doc, topic, *a, **k):
        ctx = a[-2]
        ctx["short_id"] = SID
        _fake_call(0.30, "select")
        _fake_call(0.28, "motion_script")
        raise RuntimeError("the scenes stage crashed")

    def scenes_only(doc, topic, *a, **k):
        _fake_call(0.41, "motion_scenes")
        return 1
    try:
        motion_reel._run = dying
        try:
            motion_reel.run(str(ROOT / "content/react_usestate_basics.md"), None, None, None, True)
        except RuntimeError:
            pass
        saved = json.loads(motion_reel.cost_path(SID).read_text())
        assert round(saved["total"]["cost"], 2) == 0.58, saved["total"]
        motion_reel._run = scenes_only
        motion_reel.run(str(ROOT / "content/react_usestate_basics.md"), SID, None, "scenes", True)
    finally:
        motion_reel._run = real
    saved = json.loads(motion_reel.cost_path(SID).read_text())
    assert len(saved["runs"]) == 2
    assert round(saved["total"]["cost"], 2) == 0.99, saved["total"]       # 0.58 + 0.41
    assert set(saved["total"]["by_label"]) == {"select", "motion_script", "motion_scenes"}


def test_the_money_gate_counts_earlier_runs():
    sid = "gate_reel__motion"
    motion_reel.record_cost(sid, [{"label": "motion_script", "model": "m", "cost": 1.90,
                                   "input_tokens": 0, "output_tokens": 0, "estimated": False}],
                            "2026-10-09T10:00:00.000+00:00")
    from shorts import preflight
    plan = [preflight.ModelPlan("motion_scenes", "anthropic/claude-opus-5.5", 1, 0.20)]
    assert motion_reel.earlier_runs_cost(sid, None) == 1.90
    assert not motion_reel._money_gate("scenes", sid, plan, yes=True, reel_cursor=usage.mark())


def test_a_run_rewrites_its_own_entry_not_a_new_one():
    sid = "upsert_reel__motion"
    row = {"label": "x", "model": "m", "cost": 0.1, "input_tokens": 0, "output_tokens": 0, "estimated": False}
    motion_reel.record_cost(sid, [row], "t1")
    motion_reel.record_cost(sid, [row, row], "t1")
    data = motion_reel.record_cost(sid, [row], "t2")
    assert [len(r["calls"]) for r in data["runs"]] == [2, 1] and data["total"]["calls"] == 3


# =============================================================== source scope

def _pool_texts():
    _, pool = story_evidence_pool(SECTIONS, "7.4")
    assert list(pool) == ["7.4", "7.2"]
    return find_section(SECTIONS, "7.4").text, "\n\n".join(find_section(SECTIONS, sid).text for sid in pool)


def test_a_running_example_from_another_section_fails():
    selected, whole = _pool_texts()
    r = checks.check_motion_example_from_selected(SCRIPT, selected, whole.replace(selected, ""))
    assert not r.passed, r
    assert "count (s03, s08) comes from another section, not the selected section 7.4" in r.reason
    assert "setCount (s08)" not in r.reason             # 7.3, not in this pool: not "from another section"
    assert r.details["shots"] == ["s03", "s08"]
    names = checks._example_names(SCRIPT)
    assert "useState" in names and "React" not in names and "let" not in names   # subject, keyword


def test_a_supporting_number_is_allowed():
    """The "zero" of 7.2 is a supporting number: allowed, and labelled."""
    selected, whole = _pool_texts()
    results = {r.name: r for r in checks.run_motion_script_graders(SCRIPT, whole, selected_text=selected)}
    assert results["motion_numbers_sourced"].passed
    assert not results["motion_example_from_selected"].passed


def test_an_example_from_the_selected_section_passes():
    """The same script with 7.2's text as its own section: nothing comes from elsewhere."""
    other = find_section(SECTIONS, "7.2").text
    assert checks.check_motion_example_from_selected(SCRIPT, other, "").passed
    walk = SCRIPT.model_copy(update={"template": "walkthrough"})
    assert checks.check_motion_example_from_selected(walk, "", other).passed       # not a fix_story


def test_the_facts_table_labels_supporting_sections():
    state = {"section_id": "7.4", "pool_ids": ["7.4", "7.2"], "support_ids": []}
    rows = motion_reel.fact_sources(SCRIPT, SECTIONS, state)
    zero = next(r for r in rows if r["value"] == "0")
    assert zero["section"] == "7.2" and zero["role"] == "supporting"
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        motion_reel.print_fact_sources(rows)
    assert "7.2 (supporting)" in buf.getvalue()


def test_the_writer_sees_the_selected_section_apart_from_the_others():
    section = find_section(SECTIONS, "7.4")
    pool = section.text + "\n\n" + find_section(SECTIONS, "7.2").text
    from shorts.schema import Topic
    topic = Topic(id="what_state_means", topic=SCRIPT.topic, why_it_matters="", source_section_id="7.4", difficulty="easy")
    block = script_skill._motion_material_block(topic, section, None, pool, APPROACH, "@x", "")
    material = block.split("MATERIAL (the selected section, 7.4", 1)[1].split("SUPPORTING SECTIONS", 1)[0]
    assert "State is a value that a component is allowed to remember" in material
    assert "let count = 0" not in material
    assert "Take ONLY numbers and defined terms from here; never the example" in block


def test_an_invented_example_is_allowed_with_a_warning():
    """The stub's golden builds its example from `likes` and `onTap`, which no
    section of the document states: it passes, and the shot list and the
    report say so."""
    golden = MotionScript(**json.loads((ROOT / "evals/fixtures/motion/usestate_golden.json").read_text()))
    doc = "\n\n".join(s.text for s in SECTIONS)
    selected, whole = _pool_texts()
    assert checks.check_motion_example_from_selected(golden, selected, whole.replace(selected, "")).passed
    names = checks.invented_example_names(golden, doc)
    assert "likes" in names and "onTap" in names, names
    warning = checks.invented_example_warning(golden, doc)
    assert warning.startswith("WARNING — invented example: likes (")
    assert warning.endswith("— not in any section, please review")
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        motion_reel.print_invented_example(golden, SECTIONS)
    assert "WARNING — invented example: likes" in buf.getvalue()


def test_an_example_from_the_document_shows_no_warning():
    """The first reel's counter is in 7.2: from another section (a failure,
    above), but not invented."""
    doc = "\n\n".join(s.text for s in SECTIONS)
    assert checks.invented_example_names(SCRIPT, doc) == {}
    assert checks.invented_example_warning(SCRIPT, doc) == ""


def test_callers_that_name_no_selected_section_are_unchanged():
    """Evals and older callers pass no selected_text: the example is not checked."""
    _, whole = _pool_texts()
    results = {r.name: r for r in checks.run_motion_script_graders(SCRIPT, whole)}
    assert results["motion_numbers_sourced"].passed and results["motion_example_from_selected"].passed


# =================================================================== approach

def test_what_the_approach_rules_out_is_found():
    rules = checks.approach_exclusions(APPROACH)
    assert rules == [{"clause": "How useState is called is out of scope",
                      "identifiers": ["useState"], "form_only": True}]
    more = TeachingApproach(primary="analogy", rationale=(
        "Teach the idea rather than the setCount syntax. Do not cover `useEffect` at all."))
    found = checks.approach_exclusions(more)
    assert [r["identifiers"] for r in found] == [["setCount"], ["useEffect"]]
    assert [r["form_only"] for r in found] == [True, False]


def test_s08_showing_usestate_fails_the_approach():
    r = checks.check_motion_respects_approach(SCRIPT, APPROACH)
    assert not r.passed and r.details["shots"] == ["s08"], r
    assert "useState in its code" in r.reason
    # an exclusion about how it is written leaves the name sayable:
    no_code = SCRIPT.model_copy(update={"shots": [
        s.model_copy(update={"code": []}) if s.id == "s08" else s for s in SCRIPT.shots]})
    assert checks.check_motion_respects_approach(no_code, APPROACH).passed


def test_an_approach_that_rules_nothing_out_passes():
    plain = TeachingApproach(primary="comparison", rationale="A contrast makes the idea concrete.")
    assert checks.check_motion_respects_approach(SCRIPT, plain).passed
    assert checks.check_motion_respects_approach(SCRIPT, None).passed


def test_the_script_prompt_carries_the_exclusions():
    section = find_section(SECTIONS, "7.4")
    from shorts.schema import Topic
    topic = Topic(id="what_state_means", topic=SCRIPT.topic, why_it_matters="", source_section_id="7.4", difficulty="easy")
    block = script_skill._motion_material_block(topic, section, None, section.text, APPROACH, "@x", "")
    assert "RULED OUT BY THE APPROVED APPROACH — binding" in block
    assert "- How useState is called is out of scope" in block


def test_the_script_loop_fails_a_script_that_ignores_the_approach():
    """write_motion_script grades with the approach: the fixture's s08 is sent back."""
    seen = []
    real = script_skill.ask_json

    def fake(system, user, cls, max_tokens=0, label=""):
        seen.append(user)
        data = SCRIPT.model_dump()
        return cls(**{k: data[k] for k in cls.model_fields if k in data})
    script_skill.ask_json = fake
    try:
        section = find_section(SECTIONS, "7.4")
        from shorts.schema import Topic
        topic = Topic(id="what_state_means", topic=SCRIPT.topic, why_it_matters="", source_section_id="7.4", difficulty="easy")
        out, results = script_skill.write_motion_script(
            topic, section, short_id=SID, source_text=section.text + "\n\n" + find_section(SECTIONS, "7.2").text,
            approach=APPROACH, theme="before_vs_after", language="react")
    finally:
        script_skill.ask_json = real
    assert out is None
    failed = {r.name for r in results if not r.passed}
    assert {"motion_respects_approach", "motion_example_from_selected"} <= failed, failed
    assert "motion_numbers_sourced" not in failed            # 7.2's zero is a supporting number
    assert "THE PREVIOUS SCRIPT FAILED REVIEW" in seen[-1] and "rules it out" in seen[-1]


# ==================================================================== routing

def test_screen_is_routed():
    assert motion_models.model_for("screen") == "anthropic/claude-sonnet-5.5"
    assert "screen" in {r["label"] for r in motion_models.estimate("x" * 4000)}


def test_an_unrouted_call_in_a_motion_run_is_an_error_before_sending():
    with motion_models.use():
        try:
            llm.ask_json("s", "u", TeachingApproach, label="not_a_motion_step")
        except llm.UnroutedLabel as e:
            assert "motion_models.yaml" in str(e)
        else:
            raise AssertionError("an unrouted label went through")
    # outside a motion run, nothing changes
    assert llm._LABEL_MODELS == {}


def test_every_label_a_motion_run_asks_is_routed():
    """Every ask_json label in the modules a motion run calls is in the YAML."""
    import re
    files = ["skills/select.py", "skills/understanding.py", "skills/framing.py",
             "skills/teaching_approach.py", "skills/theme.py", "skills/scenes.py",
             "review.py", "workflow.py"]
    motion_only = ["skills/script.py"]          # also writes explainer/story scripts
    routed = set(motion_models.routes())
    asked = set()
    for f in files:
        path = ROOT / "shorts" / f
        if path.exists():
            asked |= set(re.findall(r'label="([a-z_]+)"', path.read_text(encoding="utf-8")))
    for f in motion_only:
        asked |= {l for l in re.findall(r'label="([a-z_]+)"', (ROOT / "shorts" / f).read_text(encoding="utf-8"))
                  if l.startswith("motion_")}
    missing = asked - routed
    assert not missing, f"not in shorts/motion_models.yaml: {sorted(missing)}"


def test_both_models_think_because_openrouter_requires_it():
    """OpenRouter answers thinking off with "Reasoning is mandatory for this
    endpoint and cannot be disabled." (400) for Opus 5.5 AND Sonnet 5.5."""
    for model in ("anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5"):
        assert motion_models.reasoning_for(model) == {"thinking": "on", "budget": 1024}, model
    with motion_models.use():
        assert llm._reasoning("anthropic/claude-sonnet-5.5", False) == {
            "thinking": {"type": "enabled", "budget_tokens": 1024}}


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} first-reel fix tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL FIRST-REEL FIX TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
