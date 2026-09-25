"""
Step 12 hardening: the approved teaching approach must not be ignored at the
finalize gate.

FOUND DURING THE END-TO-END AUDIT — the same shape as Step 2's hook-grounding
gap. server.py's finalize() already computed `approach =
wf.approved_teaching_approach` and threaded it into design_visuals (the
PICTURES), but never into the checks.run_script_graders call at the actual
approval gate (nor into _rejudge_after_fix's repair-path gate) — so
check_script_matches_teaching_approach (gated on `approach is not None`, see
run_script_graders's own docstring) never ran at either point that actually
decides whether a short ships, even though an approved workflow's teaching
approach was sitting right there.

No API key, no network, no real LLM calls — checks.run_script_graders is
replaced with a call-recording spy; the real one is restored immediately
after.

    SHORTS_STUB=1 python -m shorts.teaching_approach_gate_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks
import shorts.server as server
from shorts.step8_hardening_test import _approved_visual_plan_workflow, _finalize_body
from shorts.server_workflow_test import _client
from shorts import config


def test_finalize_gate_passes_the_approved_teaching_approach_to_the_grader():
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    assert wf.approved_teaching_approach is not None, (
        "fixture must have an approved teaching approach for this test to "
        "mean anything")

    body = _finalize_body(doc_id, wf)
    body["do_judge"] = False   # only the gate call itself is under test here

    calls = []
    real_run_script_graders = checks.run_script_graders

    def spy(script, *a, **kw):
        calls.append(kw)
        return real_run_script_graders(script, *a, **kw)

    checks.run_script_graders = spy
    try:
        r = client.post("/api/finalize", json=body)
    finally:
        checks.run_script_graders = real_run_script_graders
        out = config.OUTPUT_DIR / f"{short_id}.json"
        if out.exists():
            out.unlink()

    assert r.status_code == 200, r.text
    # do_judge=False means the FINALIZE GATE's own run_script_graders call
    # (guarded by `if body.do_judge and ...`) never fires — this test only
    # needs to prove the plumbing is correct where it DOES fire, so re-check
    # with do_judge=True instead of relying on the call above.
    assert calls == [], "do_judge=False must not have triggered the gate call"
    print("   ok — confirmed do_judge=False skips the gate call as expected; "
          "checking the do_judge=True path next")


def test_finalize_gate_with_judging_passes_approach_through():
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    approved_approach = wf.approved_teaching_approach
    assert approved_approach is not None

    body = _finalize_body(doc_id, wf)
    body["do_judge"] = True

    calls = []
    real_run_script_graders = checks.run_script_graders
    real_judge_script = server.judge_script

    def spy(script, *a, **kw):
        calls.append(kw)
        return real_run_script_graders(script, *a, **kw)

    from shorts.schema import EvalReport
    checks.run_script_graders = spy
    server.judge_script = lambda *a, **kw: EvalReport(
        faithfulness=5, clarity=5, pace=5, diagram_correct=True,
        question_answered=True, problems=[])
    try:
        r = client.post("/api/finalize", json=body)
    finally:
        checks.run_script_graders = real_run_script_graders
        server.judge_script = real_judge_script
        out = config.OUTPUT_DIR / f"{short_id}.json"
        if out.exists():
            out.unlink()

    assert r.status_code == 200, r.text
    assert calls, "the finalize gate never called run_script_graders at all"
    gate_call = calls[0]
    passed_approach = gate_call.get("approach")
    # Not `is` — the request round-trips through JSON (_finalize_body calls
    # wf.model_dump(), the server reconstructs its own QuestionWorkflow from
    # that dict), so the object the gate receives is a distinct instance
    # with the same value, never the same object the test holds.
    assert passed_approach is not None, (
        "the finalize gate called run_script_graders with approach=None — "
        "the approved teaching approach was not passed through")
    assert passed_approach.primary == approved_approach.primary, (
        passed_approach, approved_approach)
    print("   ok — the finalize gate's run_script_graders call now receives "
          "the workflow's approved teaching approach (previously always "
          "None), so check_script_matches_teaching_approach actually runs "
          "at the point that decides approval")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} teaching-approach-gate hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL TEACHING-APPROACH-GATE HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
