"""
Offline, deterministic tests for Step 3's web/API surface: /api/material's
`workflows`, and /api/selections/{approve,reject,regenerate}, plus the
downstream gate on /api/script and /api/scripts. ALSO Step 6's
/api/teaching-approach/{approve,regenerate}.

Runs the real FastAPI app in-process via TestClient — no network beyond that,
and SHORTS_STUB=1 (set before shorts.server is imported) means no API key and
no real LLM calls either.

    SHORTS_STUB=1 python -m shorts.server_workflow_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API "
                     "calls, but shorts.server's own model_warnings() and "
                     "understanding_for() are exercised for real otherwise")

from unittest.mock import patch

from fastapi.testclient import TestClient

import shorts.server as server
from shorts import review
from shorts.skills import framing, teaching_approach
from shorts.skills.script import write_script_for_workflow
from shorts.skills.strategy import plan_strategy_for_workflow
from shorts.schema import QuestionWorkflow


SAMPLE_MATERIAL = """## 3.1 Why paging exists

Paging solves external fragmentation by dividing memory into equal fixed-size
frames. Each process is divided into pages of the same size, and the
operating system maintains a page table mapping pages to frames. Because
every frame is the same size, a free frame always fits the next page, which
is exactly what contiguous allocation could not guarantee.
"""


def _client() -> TestClient:
    return TestClient(server.app)


def _material(client: TestClient) -> dict:
    r = client.post("/api/material", data={"text": SAMPLE_MATERIAL, "target": 1})
    assert r.status_code == 200, r.text
    return r.json()


def _workflow_with_teaching_approach(doc_id: str, material: dict) -> dict:
    """
    A workflow dict with an approved question, real framing, and a chosen
    teaching_approach — built by calling the Step 4/5 skill entry points
    directly, since no server endpoint produces framing/teaching_approach yet
    (neither is wired into any orchestration path — see their own modules).
    This is exactly the shape a future orchestration step, or a script
    exercising the pipeline directly, would hand to the Step 6 endpoints.
    """
    sections = server._sections(doc_id)
    wf = QuestionWorkflow(**material["workflows"][0])
    wf = review.approve_question(wf)
    wf = framing.frame_workflow(wf, sections)
    wf = teaching_approach.choose_teaching_approach_for_workflow(wf, sections)
    return wf.model_dump()


def _workflow_with_visual_plan(doc_id: str, material: dict) -> dict:
    """
    A workflow dict with an approved question, real framing, an APPROVED
    teaching_approach, a script, and a visual_strategy — built by calling the
    Step 4/5/8/10 skill entry points directly, exactly as
    _workflow_with_teaching_approach does one stage earlier. This is what a
    real client would hold after /api/workflow/advance has run twice (once
    past the teaching-approach gate, once — after a human approves it —
    past the visual-plan gate), the shape the Step 11 endpoints expect.
    """
    sections = server._sections(doc_id)
    wf = QuestionWorkflow(**material["workflows"][0])
    wf = review.approve_question(wf)
    wf = framing.frame_workflow(wf, sections)
    wf = teaching_approach.choose_teaching_approach_for_workflow(wf, sections)
    wf = review.approve_teaching_approach(wf)
    section = sections[0]
    wf = write_script_for_workflow(wf, section)
    wf = plan_strategy_for_workflow(wf, section)
    return wf.model_dump()


# --------------------------------------------------------------------------- 11
# Web/API exposes the structured workflow.

def test_material_response_includes_structured_workflows():
    client = _client()
    data = _material(client)
    assert "workflows" in data and data["workflows"], "no workflows in response"

    wf = data["workflows"][0]
    selection, approval = wf["selection"], wf["question_approval"]

    # QuestionSelection — the UI must not have to reconstruct any of this from
    # `topics` or anything else (requirement H).
    assert "topic" in selection and "id" in selection["topic"]
    assert isinstance(selection["source_title"], str) and selection["source_title"]
    assert isinstance(selection["reasons"], list) and selection["reasons"]
    assert {"category", "explanation"} <= selection["reasons"][0].keys()

    # QuestionApproval — status plus the full regeneration surface.
    assert approval["status"] == "pending"
    assert approval["regeneration_history"] == []
    assert approval["regenerated_question"] is None
    print("   ok — /api/material's `workflows` carries structured "
          "QuestionSelection + QuestionApproval, including regeneration "
          "fields (requirement 11)")


def test_selections_endpoints_round_trip_structured_workflow():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = data["workflows"][0]

    r = client.post("/api/selections/regenerate",
                    json={"doc_id": doc_id, "workflow": wf,
                          "reason": "too broad, focus on the mechanism"})
    assert r.status_code == 200, r.text
    wf = r.json()["workflow"]
    assert wf["question_approval"]["status"] == "pending"
    assert len(wf["question_approval"]["regeneration_history"]) == 1
    assert wf["question_approval"]["regeneration_history"][0]["reason"] == (
        "too broad, focus on the mechanism")

    r = client.post("/api/selections/approve", json={"doc_id": doc_id, "workflow": wf})
    assert r.status_code == 200, r.text
    wf = r.json()["workflow"]
    assert wf["question_approval"]["status"] == "approved"
    print("   ok — /api/selections/regenerate and /approve return the same "
          "structured workflow shape, round-trippable by the client "
          "(requirement 11)")


def test_regenerate_endpoint_requires_a_reason():
    client = _client()
    data = _material(client)
    wf = data["workflows"][0]
    r = client.post("/api/selections/regenerate",
                    json={"doc_id": data["doc_id"], "workflow": wf, "reason": "   "})
    assert r.status_code == 400
    print("   ok — POST /api/selections/regenerate refuses a blank reason "
          "(requirement 4, at the API boundary)")


# --------------------------------------------------------------------------- 13
# No expensive downstream generation starts before approval.

def test_script_endpoint_refuses_before_any_paid_call_when_not_approved():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = data["workflows"][0]

    # write_script is the paid call /api/script exists to make. Patching it to
    # raise proves the gate check happens BEFORE it, not merely that the
    # response looks wrong — a 409 for the wrong reason would still pass a
    # weaker assertion.
    with patch("shorts.server.write_script", side_effect=AssertionError(
            "write_script must not be called for an unapproved topic")):
        for status in ("pending", "rejected", "regenerating"):
            approval = {**wf["question_approval"], "status": status}
            r = client.post("/api/script", json={
                "doc_id": doc_id, "topic": wf["selection"]["topic"],
                "approval": approval,
            })
            assert r.status_code == 409, (status, r.text)
    print("   ok — POST /api/script never reaches write_script for pending/"
          "rejected/regenerating (requirement 13)")


def test_scripts_endpoint_refuses_unapproved_topics_per_card():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = data["workflows"][0]
    topic = wf["selection"]["topic"]

    with patch("shorts.server.write_script", side_effect=AssertionError(
            "write_script must not be called for an unapproved topic")):
        r = client.post("/api/scripts", json={
            "doc_id": doc_id, "topics": [topic],
            "approvals": {topic["id"]: wf["question_approval"]},   # still pending
        })
    assert r.status_code == 200, r.text          # batch endpoint: per-card error, not a 500
    result = r.json()["results"][0]
    assert result.get("error"), "an unapproved topic must come back as a per-card error"
    assert "not approved" in result["error"]
    print("   ok — POST /api/scripts reports an unapproved topic as a per-card "
          "error, never a write_script call (requirement 13)")


def test_script_endpoint_unchanged_when_no_approval_sent():
    # Backward compatibility: omitting `approval` entirely must behave exactly
    # as it did before Step 3 — this endpoint proceeds and calls write_script.
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    topic = data["workflows"][0]["selection"]["topic"]

    r = client.post("/api/script", json={"doc_id": doc_id, "topic": topic})
    assert r.status_code == 200, r.text
    assert r.json()["qa"]["question"]
    print("   ok — /api/script with no `approval` field behaves exactly as "
          "before Step 3 (backward compatibility)")


# ------------------------------------------------------------------ Step 6 API

def test_teaching_approach_approve_endpoint_returns_structured_state():
    client = _client()
    data = _material(client)
    wf = _workflow_with_teaching_approach(data["doc_id"], data)

    r = client.post("/api/teaching-approach/approve",
                    json={"doc_id": data["doc_id"], "workflow": wf})
    assert r.status_code == 200, r.text
    approval = r.json()["workflow"]["teaching_approach_approval"]
    assert approval["status"] == "approved"
    assert approval["regeneration_history"] == []
    print("   ok — POST /api/teaching-approach/approve returns structured "
          "TeachingApproachApproval state (requirement 15)")


def test_teaching_approach_regenerate_endpoint_requires_a_reason():
    client = _client()
    data = _material(client)
    wf = _workflow_with_teaching_approach(data["doc_id"], data)

    r = client.post("/api/teaching-approach/regenerate",
                    json={"doc_id": data["doc_id"], "workflow": wf, "reason": "   "})
    assert r.status_code == 400
    print("   ok — POST /api/teaching-approach/regenerate refuses a blank "
          "reason (requirement 3, at the API boundary)")


def test_teaching_approach_regenerate_endpoint_round_trips_structured_state():
    client = _client()
    data = _material(client)
    wf = _workflow_with_teaching_approach(data["doc_id"], data)

    r = client.post("/api/teaching-approach/regenerate", json={
        "doc_id": data["doc_id"], "workflow": wf,
        "reason": "code is not necessary for this concept",
    })
    assert r.status_code == 200, r.text
    approval = r.json()["workflow"]["teaching_approach_approval"]
    assert approval["status"] == "pending"
    assert len(approval["regeneration_history"]) == 1
    assert approval["regeneration_history"][0]["reason"] == (
        "code is not necessary for this concept")
    assert approval["regenerated_approach"] is not None
    print("   ok — POST /api/teaching-approach/regenerate returns structured "
          "regeneration history and attempt state (requirement 15)")


def test_teaching_approach_endpoints_refuse_before_earlier_stages_complete():
    client = _client()
    data = _material(client)
    # A workflow straight from /api/material: question still pending, no
    # framing, no teaching_approach at all.
    wf = data["workflows"][0]

    r = client.post("/api/teaching-approach/approve",
                    json={"doc_id": data["doc_id"], "workflow": wf})
    assert r.status_code == 409, r.text

    r = client.post("/api/teaching-approach/regenerate", json={
        "doc_id": data["doc_id"], "workflow": wf, "reason": "a reason"})
    assert r.status_code == 409, r.text
    print("   ok — the teaching-approach endpoints refuse a workflow that "
          "has not cleared question approval + framing + an existing "
          "teaching_approach (requirement 13)")


def test_teaching_approach_endpoints_never_reach_the_llm_when_refused():
    client = _client()
    data = _material(client)
    wf = data["workflows"][0]   # pending question, no framing, no approach

    with patch("shorts.skills.teaching_approach.ask_json", side_effect=AssertionError(
            "a refused request must not reach the LLM")):
        r = client.post("/api/teaching-approach/regenerate", json={
            "doc_id": data["doc_id"], "workflow": wf, "reason": "a reason"})
    assert r.status_code == 409
    print("   ok — a teaching-approach regeneration refused for an earlier-"
          "stage failure never calls the LLM (requirement 17)")


# ------------------------------------------------------------------ Step 7 API

def test_advance_endpoint_generates_framing_and_teaching_approach():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = data["workflows"][0]

    r = client.post("/api/selections/approve", json={"doc_id": doc_id, "workflow": wf})
    approved = r.json()["workflow"]

    r = client.post("/api/workflow/advance",
                    json={"doc_id": doc_id, "workflows": [approved]})
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["status"] == "awaiting_teaching_approach_approval"
    assert result["workflow"]["framing"] is not None
    assert result["workflow"]["teaching_approach"] is not None
    print("   ok — POST /api/workflow/advance generates framing and a "
          "teaching approach for an approved question, and stops at the "
          "next gate")


def test_advance_endpoint_reports_pending_without_generating_anything():
    client = _client()
    data = _material(client)
    wf = data["workflows"][0]   # still pending

    with patch("shorts.skills.framing.ask_json", side_effect=AssertionError(
            "a pending question must not be framed")), \
        patch("shorts.skills.teaching_approach.ask_json", side_effect=AssertionError(
            "a pending question must not get a teaching approach")):
        r = client.post("/api/workflow/advance",
                        json={"doc_id": data["doc_id"], "workflows": [wf]})
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["status"] == "awaiting_question_approval"
    assert result["workflow"]["framing"] is None
    print("   ok — /api/workflow/advance reports a pending question without "
          "spending any generation call")


def test_advance_endpoint_batches_independently():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    pending = data["workflows"][0]
    r = client.post("/api/selections/approve",
                    json={"doc_id": doc_id, "workflow": data["workflows"][0]})
    approved = r.json()["workflow"]
    approved["selection"]["topic"] = {**approved["selection"]["topic"], "id": "t_approved"}
    pending = {**pending, "selection": {**pending["selection"],
              "topic": {**pending["selection"]["topic"], "id": "t_pending"}}}

    r = client.post("/api/workflow/advance",
                    json={"doc_id": doc_id, "workflows": [pending, approved]})
    assert r.status_code == 200, r.text
    by_id = {res["workflow"]["selection"]["topic"]["id"]: res for res in r.json()["results"]}
    assert by_id["t_pending"]["status"] == "awaiting_question_approval"
    assert by_id["t_approved"]["status"] == "awaiting_teaching_approach_approval"
    print("   ok — /api/workflow/advance advances a batch of workflows "
          "independently — one pending does not block another from "
          "reaching its own gate")


def test_advance_endpoint_is_idempotent():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    r = client.post("/api/selections/approve",
                    json={"doc_id": doc_id, "workflow": data["workflows"][0]})
    approved = r.json()["workflow"]

    r = client.post("/api/workflow/advance",
                    json={"doc_id": doc_id, "workflows": [approved]})
    once = r.json()["results"][0]["workflow"]

    with patch("shorts.skills.framing.ask_json", side_effect=AssertionError(
            "framing must not be regenerated")), \
        patch("shorts.skills.teaching_approach.ask_json", side_effect=AssertionError(
            "teaching approach must not be regenerated")):
        r2 = client.post("/api/workflow/advance",
                         json={"doc_id": doc_id, "workflows": [once]})
    assert r2.status_code == 200, r2.text
    twice = r2.json()["results"][0]["workflow"]
    assert twice["framing"] == once["framing"]
    assert twice["teaching_approach"] == once["teaching_approach"]
    print("   ok — repeated /api/workflow/advance calls on an unchanged "
          "workflow spend no additional generation calls")


# ----------------------------------------------------------------- Step 11 API

def test_visual_plan_approve_endpoint_returns_structured_state():
    client = _client()
    data = _material(client)
    wf = _workflow_with_visual_plan(data["doc_id"], data)

    r = client.post("/api/visual-plan/approve",
                    json={"doc_id": data["doc_id"], "workflow": wf})
    assert r.status_code == 200, r.text
    approval = r.json()["workflow"]["visual_plan_approval"]
    assert approval["status"] == "approved"
    assert approval["regeneration_history"] == []
    print("   ok — POST /api/visual-plan/approve returns structured "
          "VisualPlanApproval state (requirement 15)")


def test_visual_plan_regenerate_endpoint_requires_a_reason():
    client = _client()
    data = _material(client)
    wf = _workflow_with_visual_plan(data["doc_id"], data)

    r = client.post("/api/visual-plan/regenerate",
                    json={"doc_id": data["doc_id"], "workflow": wf, "reason": "   "})
    assert r.status_code == 400
    print("   ok — POST /api/visual-plan/regenerate refuses a blank reason "
          "(requirement 3, at the API boundary)")


def test_visual_plan_regenerate_endpoint_round_trips_structured_state():
    client = _client()
    data = _material(client)
    wf = _workflow_with_visual_plan(data["doc_id"], data)

    r = client.post("/api/visual-plan/regenerate", json={
        "doc_id": data["doc_id"], "workflow": wf,
        "reason": "beat 2 shows code, that's not the approach",
    })
    assert r.status_code == 200, r.text
    approval = r.json()["workflow"]["visual_plan_approval"]
    assert approval["status"] == "pending"
    assert len(approval["regeneration_history"]) == 1
    assert approval["regeneration_history"][0]["reason"] == (
        "beat 2 shows code, that's not the approach")
    assert approval["regenerated_strategy"] is not None
    print("   ok — POST /api/visual-plan/regenerate returns structured "
          "regeneration history and attempt state (requirement 15)")


def test_visual_plan_endpoints_refuse_before_earlier_stages_complete():
    client = _client()
    data = _material(client)
    # A workflow straight from /api/material: question still pending, no
    # framing, no teaching_approach, no script, no visual plan at all.
    wf = data["workflows"][0]

    r = client.post("/api/visual-plan/approve",
                    json={"doc_id": data["doc_id"], "workflow": wf})
    assert r.status_code == 409, r.text

    r = client.post("/api/visual-plan/regenerate", json={
        "doc_id": data["doc_id"], "workflow": wf, "reason": "a reason"})
    assert r.status_code == 409, r.text
    print("   ok — the visual-plan endpoints refuse a workflow that has not "
          "cleared question approval + framing + approved teaching approach "
          "+ script + an existing visual plan (requirement 13)")


def test_visual_plan_endpoints_never_reach_the_llm_when_refused():
    client = _client()
    data = _material(client)
    wf = data["workflows"][0]   # pending question, nothing generated

    with patch("shorts.skills.strategy.ask_json", side_effect=AssertionError(
            "a refused request must not reach the LLM")):
        r = client.post("/api/visual-plan/regenerate", json={
            "doc_id": data["doc_id"], "workflow": wf, "reason": "a reason"})
    assert r.status_code == 409
    print("   ok — a visual-plan regeneration refused for an earlier-stage "
          "failure never calls the LLM (requirement 17)")


def test_advance_endpoint_generates_script_and_visual_plan():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = _workflow_with_teaching_approach(doc_id, data)
    wf = review.approve_teaching_approach(QuestionWorkflow(**wf)).model_dump()

    r = client.post("/api/workflow/advance",
                    json={"doc_id": doc_id, "workflows": [wf]})
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["status"] == "awaiting_visual_plan_approval"
    assert result["workflow"]["script"] is not None
    assert result["workflow"]["visual_strategy"] is not None
    print("   ok — POST /api/workflow/advance generates a script and a "
          "visual plan for an approved teaching approach, and stops at the "
          "visual-plan gate")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} server workflow (Step 3 API) tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SERVER WORKFLOW TESTS PASSED.")


if __name__ == "__main__":
    main()
