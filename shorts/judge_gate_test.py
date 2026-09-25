"""
Hardening pass: the judge's verdict must actually gate approval.

Before this, /api/finalize built every unit with status="approved" and then,
when config.REPAIR_FAILED_SHORTS was off (the default), a failing judge
verdict (diagram_correct=False, or any score under EvalReport.passed's bar)
only printed a warning — the unit still shipped "approved", identical to a
short the judge scored a clean 5. The retry-then-quarantine path
(_rejudge_after_fix) already did the right thing, but only when
REPAIR_FAILED_SHORTS=1; the far more common no-repair path bypassed the gate
entirely.

No API key, no network, no real LLM calls — SHORTS_STUB=1, and every judge
call in these tests is a monkeypatched shorts.server.judge_script, never the
real skills.audit.judge_script.

    SHORTS_STUB=1 python -m shorts.judge_gate_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import shorts.server as server
from shorts import checks, config, feed
from shorts.schema import EvalReport, ShortUnit
from shorts.server_workflow_test import _client, _material
from shorts.step8_hardening_test import (
    _approved_visual_plan_workflow, _finalize_body,
    test_finalize_succeeds_when_approved_strategy_is_unchanged,
)


def _judge(faithfulness=5, clarity=5, pace=5, diagram_correct=True,
          question_answered=True, problems=None) -> EvalReport:
    return EvalReport(faithfulness=faithfulness, clarity=clarity, pace=pace,
                      diagram_correct=diagram_correct,
                      question_answered=question_answered,
                      problems=list(problems or []))


def _load_unit(short_id: str) -> ShortUnit:
    path = config.OUTPUT_DIR / f"{short_id}.json"
    return ShortUnit.model_validate_json(path.read_text(encoding="utf-8"))


def _cleanup(short_id: str) -> None:
    out = config.OUTPUT_DIR / f"{short_id}.json"
    if out.exists():
        out.unlink()


def _finalize_with_judge(client, judge_fn, *, repair: bool = False):
    """POST /api/finalize with judge_script and write_script (only used by
    the repair path) monkeypatched, do_judge=True, do_svg=False (so
    design_visuals never draws frames and the vision judge — gated on
    `vision and draw` — never fires, real or otherwise).

    checks.run_script_graders is also stubbed to return a clean pass: the
    stub workflow's generated script is deliberately short (SHORTS_STUB's
    fixed canned beats) and fails the real timing/beat-count graders on its
    own, which would skip the judge call entirely (finalize only submits it
    once the deterministic graders already pass) — a fixture limitation
    unrelated to what this test is checking, so it is bypassed rather than
    worked around with a hand-built Script that would drift from what
    _approved_visual_plan_workflow actually produces.
    """
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    body = _finalize_body(doc_id, wf)
    body["do_judge"] = True

    real_judge_script = server.judge_script
    real_write_script = server.write_script
    real_run_script_graders = checks.run_script_graders
    real_repair_flag = config.REPAIR_FAILED_SHORTS
    server.judge_script = judge_fn
    # The repair path rewrites the script from the judge's feedback; a real
    # rewrite is exactly what this test suite must not pay for, and the
    # already-approved script already passes the (stubbed) graders once —
    # reusing it keeps the repair path exercised without a second script
    # generation.
    server.write_script = lambda **kw: kw["current"]
    checks.run_script_graders = lambda *a, **kw: []
    config.REPAIR_FAILED_SHORTS = repair
    try:
        r = client.post("/api/finalize", json=body)
    finally:
        server.judge_script = real_judge_script
        server.write_script = real_write_script
        checks.run_script_graders = real_run_script_graders
        config.REPAIR_FAILED_SHORTS = real_repair_flag
    return short_id, r


# ============================================================ 1. simple pass/fail

def test_clean_judge_result_ships_as_approved():
    client = _client()
    short_id, r = _finalize_with_judge(client, lambda *a, **kw: _judge())
    try:
        assert r.status_code == 200, r.text
        result = r.json()
        assert short_id in result["built"], result
        assert result["quarantined"] == [], result
        unit = _load_unit(short_id)
        assert unit.status == "approved", unit.status
        print("   ok — diagram_correct=True and no substantive problems -> "
              "ships approved (requirement 1)")
    finally:
        _cleanup(short_id)


def test_diagram_incorrect_blocks_approval():
    client = _client()
    short_id, r = _finalize_with_judge(
        client, lambda *a, **kw: _judge(
            diagram_correct=False,
            problems=["frame d_two_returns shows invented syntax not in the source"]))
    try:
        assert r.status_code == 200, r.text
        unit = _load_unit(short_id)
        assert unit.status == "needs_review", unit.status
        print("   ok — diagram_correct=False blocks automatic approval "
              "(requirement 2)")
    finally:
        _cleanup(short_id)


def test_substantive_score_failure_blocks_approval():
    """diagram_correct True, but faithfulness under the bar — proves the
    gate is not diagram_correct-only, it is EvalReport.passed as a whole."""
    client = _client()
    short_id, r = _finalize_with_judge(
        client, lambda *a, **kw: _judge(
            faithfulness=2, diagram_correct=True,
            problems=["beat 1 states a claim its section does not contain"]))
    try:
        assert r.status_code == 200, r.text
        unit = _load_unit(short_id)
        assert unit.status == "needs_review", unit.status
        print("   ok — a substantive non-diagram judge failure (low "
              "faithfulness) blocks approval too (requirement 3)")
    finally:
        _cleanup(short_id)


# ============================================================ 2. retry / re-plan

def test_retry_recovers_and_ships_approved():
    """REPAIR_FAILED_SHORTS on, first judge call fails, the repair's own
    re-judge call passes — the retry must run (call count == 2) and the
    final status must reflect the SECOND, passing verdict."""
    client = _client()
    calls = []

    def judge_fn(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            return _judge(diagram_correct=False,
                         problems=["frame shows the wrong destructuring"])
        return _judge()

    short_id, r = _finalize_with_judge(client, judge_fn, repair=True)
    try:
        assert r.status_code == 200, r.text
        assert len(calls) == 2, (
            f"expected the judge to be called twice (initial + repair "
            f"re-judge), got {len(calls)}")
        unit = _load_unit(short_id)
        assert unit.status == "approved", unit.status
        assert unit.eval.diagram_correct, unit.eval
        print("   ok — a blocking judge failure with a retry mechanism "
              "available (REPAIR_FAILED_SHORTS=1) triggers retry/re-plan, "
              "and a recovered short ships approved on the new verdict "
              "(requirement 4)")
    finally:
        _cleanup(short_id)


def test_exhausted_retry_does_not_become_approved():
    """Same setup, but the repair's re-judge call fails too — the existing
    one-repair-then-quarantine limit must still end in needs_review, never
    approved."""
    client = _client()
    calls = []

    def judge_fn(*a, **kw):
        calls.append(1)
        return _judge(diagram_correct=False, problems=["still wrong"])

    short_id, r = _finalize_with_judge(client, judge_fn, repair=True)
    try:
        assert r.status_code == 200, r.text
        assert len(calls) == 2, calls
        unit = _load_unit(short_id)
        assert unit.status == "needs_review", unit.status
        print("   ok — a blocking judge failure that survives the repair "
              "attempt (retries exhausted) does NOT become approved "
              "(requirement 5)")
    finally:
        _cleanup(short_id)


# ============================================================ 3. finalize response

def test_finalize_response_cannot_bypass_the_gate():
    client = _client()
    short_id, r = _finalize_with_judge(
        client, lambda *a, **kw: _judge(diagram_correct=False, problems=["x"]))
    try:
        assert r.status_code == 200, r.text
        result = r.json()
        assert short_id in result["built"], (
            "a quarantined short is still built and paid for — it must not "
            "disappear from 'built'")
        assert short_id not in [s["short_id"] for s in result["shorts"]], (
            "a quarantined short must not appear in the student-facing "
            "'shorts' list")
        assert short_id in [s["short_id"] for s in result["quarantined"]], (
            "a quarantined short must be reported under 'quarantined', not "
            "silently dropped")
        assert _load_unit(short_id).status in feed.QUARANTINED
        print("   ok — a caller cannot get a visually-failed result "
              "reported as shipped: it is built, held out of 'shorts', and "
              "surfaced under 'quarantined' (requirement 6 — finalize "
              "respects the gate)")
    finally:
        _cleanup(short_id)


# ============================================================ 4. informational findings

def test_informational_finding_does_not_block():
    """The judge's own instructions (skills/audit.py's JUDGE_SYSTEM) allow a
    non-substantive note in `problems` — e.g. 'no frames were given to
    check' — while diagram_correct stays True and every score is clean.
    That must not be treated as a blocking failure."""
    client = _client()
    short_id, r = _finalize_with_judge(
        client, lambda *a, **kw: _judge(
            diagram_correct=True,
            problems=["no frames were given, so diagram_correct was not "
                     "actually checked"]))
    try:
        assert r.status_code == 200, r.text
        unit = _load_unit(short_id)
        assert unit.status == "approved", unit.status
        print("   ok — an informational judge note with clean scores does "
              "not block approval (requirement 7)")
    finally:
        _cleanup(short_id)


# ============================================================ 5. no regression

def test_existing_strategy_protection_still_works():
    """Re-runs Step 8's own finalize test (do_judge=False, so this gate
    never engages) to prove the approval/version/strategy protections it
    added are untouched by this change."""
    test_finalize_succeeds_when_approved_strategy_is_unchanged()
    print("   ok — Step 8's approved-strategy-unchanged finalize test still "
          "passes unmodified (requirement 8 — no regression)")


# ============================================================ 6. Step 11: no verdict

def test_judge_exception_does_not_ship_approved():
    """The judge call itself raising must not leave unit.eval (and
    unit.status) exactly as if judging had never been asked for."""
    def judge_raises(*a, **kw):
        raise RuntimeError("simulated judge outage")

    client = _client()
    short_id, r = _finalize_with_judge(client, judge_raises)
    try:
        assert r.status_code == 200, r.text
        unit = _load_unit(short_id)
        assert unit.eval is None, (
            "no EvalReport must be fabricated for a crashed judge call")
        assert unit.status == "needs_review", unit.status
        print("   ok — a judge call that raises leaves unit.eval None (not "
          "fabricated) and blocks approval — NO VERDICT is not treated as "
          "JUDGE PASSED")
    finally:
        _cleanup(short_id)


def test_no_verdict_because_deterministic_graders_already_failed_still_quarantines():
    """do_judge=True (a verdict was requested), but the script fails the
    finalize-time deterministic graders before the judge is ever called —
    checks.run_script_graders is deliberately NOT stubbed here, so the
    stub-generated script's own natural failure (too short / too few
    beats — see _finalize_with_judge's own docstring) is what triggers
    this, not a hand-built failure."""
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    body = _finalize_body(doc_id, wf)
    body["do_judge"] = True

    real_judge_script = server.judge_script
    calls = []
    server.judge_script = lambda *a, **kw: calls.append(1) or _judge()
    try:
        r = client.post("/api/finalize", json=body)
    finally:
        server.judge_script = real_judge_script
    try:
        assert r.status_code == 200, r.text
        assert calls == [], "the judge must not be called when the "\
            "deterministic pre-check already failed"
        unit = _load_unit(short_id)
        assert unit.eval is None
        assert unit.status == "needs_review", unit.status
        print("   ok — a verdict requested (do_judge=True) but never even "
          "attempted, because the script already fails the deterministic "
          "graders at this gate, still quarantines rather than shipping "
          "approved with no verdict at all")
    finally:
        _cleanup(short_id)


def test_do_judge_false_is_unaffected_by_the_no_verdict_gate():
    """The existing, intentional cost-control opt-out (do_judge=False) must
    keep shipping approved with no verdict — this is 'no verdict requested',
    not 'verdict requested and missing', and Step 11 must not conflate them."""
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    body = _finalize_body(doc_id, wf)
    body["do_judge"] = False
    try:
        r = client.post("/api/finalize", json=body)
        assert r.status_code == 200, r.text
        unit = _load_unit(short_id)
        assert unit.eval is None
        assert unit.status == "approved", unit.status
        print("   ok — do_judge=False (no verdict requested at all) still "
          "ships approved, unchanged — the no-verdict gate only engages "
          "when a verdict was actually requested")
    finally:
        _cleanup(short_id)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} judge-gate hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL JUDGE-GATE HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
