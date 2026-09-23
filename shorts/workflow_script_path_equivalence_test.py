"""
Step 5: proves the two workflow script-generation entry points —
POST /api/workflow/advance (shorts/workflow.py's advance()) and
POST /api/workflow/scripts (server.py's make_workflow_scripts) — both call
the SAME authoritative, graded path: skills.script.write_and_grade_script_for_workflow.

Runs the real FastAPI app in-process via TestClient, SHORTS_STUB=1 (set before
shorts.server is imported) — no API key, no network, no real LLM calls.

    SHORTS_STUB=1 python -m shorts.workflow_script_path_equivalence_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from fastapi.testclient import TestClient

import shorts.server as server
import shorts.workflow as workflow
from shorts import review, checks
from shorts.checks import GraderResult
from shorts.skills import script as script_mod
from shorts.server_workflow_test import (
    SAMPLE_MATERIAL, _client, _material, _workflow_with_teaching_approach,
)
from shorts.schema import QuestionWorkflow


def _approved_wf(client: TestClient):
    """A fresh workflow dict with an APPROVED teaching approach — the one
    precondition both entry points require before they will write a script."""
    data = _material(client)
    doc_id = data["doc_id"]
    wf = _workflow_with_teaching_approach(doc_id, data)
    wf = review.approve_teaching_approach(QuestionWorkflow(**wf)).model_dump()
    return doc_id, wf


# --------------------------------------------------------------- equivalence

def test_advance_and_workflow_scripts_call_the_same_authoritative_function():
    """Both endpoints must invoke skills.script.write_and_grade_script_for_workflow
    — not two separately-written call sites that happen to behave alike."""
    client = _client()

    calls = {"workflow": 0, "server": 0}
    real = script_mod.write_and_grade_script_for_workflow

    def spy_via_workflow(*a, **kw):
        calls["workflow"] += 1
        return real(*a, **kw)

    def spy_via_server(*a, **kw):
        calls["server"] += 1
        return real(*a, **kw)

    # PATCH THE NAME AS EACH MODULE ITSELF SEES IT — both workflow.py and
    # server.py did `from .skills.script import write_and_grade_script_for_workflow`,
    # which binds a SEPARATE reference into each module's own namespace at
    # import time (the same reason script_orchestration_test.py's own spy
    # patches shorts.workflow, not shorts.skills.script).
    doc_id_a, wf_a = _approved_wf(client)
    workflow.write_and_grade_script_for_workflow = spy_via_workflow
    try:
        r = client.post("/api/workflow/advance", json={"doc_id": doc_id_a, "workflows": [wf_a]})
    finally:
        workflow.write_and_grade_script_for_workflow = real
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["workflow"]["script"] is not None
    assert calls["workflow"] == 1, calls

    doc_id_b, wf_b = _approved_wf(client)
    server.write_and_grade_script_for_workflow = spy_via_server
    try:
        r = client.post("/api/workflow/scripts", json={"doc_id": doc_id_b, "workflows": [wf_b]})
    finally:
        server.write_and_grade_script_for_workflow = real
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["qa"] is not None
    assert calls["server"] == 1, calls

    print("   ok — /api/workflow/advance calls write_and_grade_script_for_workflow "
          f"exactly once ({calls['workflow']} call(s))")
    print("   ok — /api/workflow/scripts calls write_and_grade_script_for_workflow "
          f"exactly once ({calls['server']} call(s)) — the SAME function, not a "
          f"second implementation")


def test_both_paths_produce_the_same_script_from_the_same_input():
    """Same starting workflow, same deterministic stub — the two entry points
    must not silently diverge in what they generate."""
    client = _client()

    doc_id_a, wf_a = _approved_wf(client)
    r_a = client.post("/api/workflow/advance", json={"doc_id": doc_id_a, "workflows": [wf_a]})
    script_a = r_a.json()["results"][0]["workflow"]["script"]

    doc_id_b, wf_b = _approved_wf(client)
    r_b = client.post("/api/workflow/scripts", json={"doc_id": doc_id_b, "workflows": [wf_b]})
    script_b = r_b.json()["results"][0]["workflow"]["script"]

    assert script_a["question"] == script_b["question"]
    assert [b["line"] for b in script_a["beats"]] == [b["line"] for b in script_b["beats"]]
    print("   ok — advance() and /api/workflow/scripts produce byte-identical "
          "scripts from the same approved workflow (same authoritative path, "
          "same deterministic stub)")


# ------------------------------------------------------- failing-grader retry

def _always_failing_graders(*a, **kw):
    _always_failing_graders.calls += 1
    return [GraderResult("deliberately_failing_grader", False,
                         "Step 5 equivalence test — this grader never passes, on purpose")]
_always_failing_graders.calls = 0


def _run_with_forced_grader_failure(post_call):
    """Patch checks.run_script_graders (the module attribute every caller of
    write_and_grade_script_for_workflow reaches through `from .. import checks`
    — see script.py's own import) so it ALWAYS fails, then run `post_call` and
    report how many attempts were made."""
    _always_failing_graders.calls = 0
    real = checks.run_script_graders
    checks.run_script_graders = _always_failing_graders
    try:
        return post_call(), _always_failing_graders.calls
    finally:
        checks.run_script_graders = real


def test_advance_retries_the_same_number_of_times_on_a_failing_grader():
    client = _client()
    doc_id, wf = _approved_wf(client)

    def call():
        r = client.post("/api/workflow/advance", json={"doc_id": doc_id, "workflows": [wf]})
        assert r.status_code == 200, r.text
        return r.json()["results"][0]

    result, attempts = _run_with_forced_grader_failure(call)
    assert attempts == 3, f"expected the default max_attempts=3, got {attempts}"
    # advance() discards grader_results (see write_and_grade_script_for_workflow's
    # own call site comment) — it only ever cared whether a script now exists,
    # never whether it graded cleanly. A script is still produced.
    assert result["workflow"]["script"] is not None
    print(f"   ok — /api/workflow/advance retried {attempts} time(s) against an "
          f"always-failing grader (the same ceiling as /api/workflow/scripts, "
          f"below) and still returned the last attempt's script")


def test_workflow_scripts_retries_the_same_number_of_times_on_a_failing_grader():
    client = _client()
    doc_id, wf = _approved_wf(client)

    def call():
        r = client.post("/api/workflow/scripts", json={"doc_id": doc_id, "workflows": [wf]})
        assert r.status_code == 200, r.text
        return r.json()["results"][0]

    result, attempts = _run_with_forced_grader_failure(call)
    assert attempts == 3, f"expected the default max_attempts=3, got {attempts}"
    assert result["qa"] is not None
    assert any(g["name"] == "deliberately_failing_grader" and not g["passed"]
              for g in result["graders"]), result["graders"]
    print(f"   ok — /api/workflow/scripts retried {attempts} time(s) against the "
          f"SAME always-failing grader — identical ceiling to /api/workflow/advance "
          f"above — and surfaced the failing grader chip to the reviewer")


# --------------------------------------------------------- Step 7: architectural
# permanent regression test — no workflow entry point can ship an ungraded script

def test_no_workflow_entry_point_can_generate_an_ungraded_script():
    """
    PERMANENT ARCHITECTURAL REGRESSION TEST (Step 7 audit).

    Whatever ends up in QuestionWorkflow.script after ANY of the three
    workflow script entry points — /api/workflow/advance, /api/workflow/
    scripts, and /api/regenerate's workflow-aware branch — must be a script
    checks.run_script_graders actually graded, not merely one write_script_
    for_workflow (the raw, ungraded primitive underneath) happened to write
    alongside it. This is what write_and_grade_script_for_workflow (Step 5)
    exists to guarantee for all three at once; this test proves the
    guarantee holds for each entry point independently, by making it
    impossible for a script to "pass" without checks.run_script_graders
    having been asked about that EXACT script text first.
    """
    client = _client()
    real_run_script_graders = checks.run_script_graders
    graded: list[str] = []

    def spy(script, *a, **kw):
        graded.append(script.question)
        return real_run_script_graders(script, *a, **kw)

    checks.run_script_graders = spy
    try:
        # /api/workflow/advance
        graded.clear()
        doc_id, wf = _approved_wf(client)
        r = client.post("/api/workflow/advance", json={"doc_id": doc_id, "workflows": [wf]})
        assert r.status_code == 200, r.text
        script = r.json()["results"][0]["workflow"]["script"]
        assert script is not None
        assert graded, "no grading occurred at all for /api/workflow/advance"
        assert script["question"] in graded, (
            "/api/workflow/advance shipped a script that was never graded: "
            f"{script['question']!r} not in graded {graded!r}")

        # /api/workflow/scripts
        graded.clear()
        doc_id, wf = _approved_wf(client)
        r = client.post("/api/workflow/scripts", json={"doc_id": doc_id, "workflows": [wf]})
        assert r.status_code == 200, r.text
        script = r.json()["results"][0]["workflow"]["script"]
        assert script is not None
        assert graded, "no grading occurred at all for /api/workflow/scripts"
        assert script["question"] in graded, (
            "/api/workflow/scripts shipped a script that was never graded: "
            f"{script['question']!r} not in graded {graded!r}")

        # /api/regenerate, workflow-aware branch
        graded.clear()
        doc_id, wf = _approved_wf(client)
        r = client.post("/api/regenerate", json={
            "doc_id": doc_id, "topic": wf["selection"]["topic"],
            "instruction": "make it punchier", "target": "answer",
            "workflow": wf,
        })
        assert r.status_code == 200, r.text
        script = r.json()["workflow"]["script"]
        assert script is not None
        assert graded, "no grading occurred at all for /api/regenerate's workflow branch"
        assert script["question"] in graded, (
            "/api/regenerate's workflow branch shipped a script that was never "
            f"graded: {script['question']!r} not in graded {graded!r}")
    finally:
        checks.run_script_graders = real_run_script_graders

    print("   ok — /api/workflow/advance, /api/workflow/scripts, and "
          "/api/regenerate's workflow branch each ship only a script "
          "checks.run_script_graders actually graded — no entry point can "
          "generate an ungraded script (Step 7 permanent architectural "
          "regression test)")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} workflow script-path equivalence tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL WORKFLOW SCRIPT-PATH EQUIVALENCE TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
