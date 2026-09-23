"""
Step 6: proves workflow versioning, approval-invalidation, and server-side
authority over approval state — human approvals must be checked from the
workflow object itself (question_approval/teaching_approach_approval/
visual_plan_approval and the version they gate), never trusted as a separate
client-supplied flag, and /api/finalize must not accept a workflow whose own
fields contradict what it claims to have approved.

Runs the real FastAPI app in-process via TestClient, SHORTS_STUB=1 (set
before shorts.server is imported) — no API key, no network, no real LLM or
render calls (do_svg/do_judge/do_voice are all False in every /api/finalize
call here).

    SHORTS_STUB=1 python -m shorts.workflow_versioning_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import config, review
from shorts.schema import QuestionWorkflow, TeachingApproachApproval
from shorts.skills import framing, teaching_approach
from shorts.skills.script import write_script_for_workflow
from shorts.skills.strategy import plan_strategy_for_workflow
from shorts.server_workflow_test import (
    SAMPLE_MATERIAL, _client, _material, _workflow_with_teaching_approach,
    _workflow_with_visual_plan,
)


def _sections_for(doc_id: str):
    import shorts.server as server
    return server._sections(doc_id)


# --------------------------------------------------------------------- 1/2/3
# version field itself

def test_new_workflow_starts_with_valid_default_version():
    client = _client()
    data = _material(client)
    wf = QuestionWorkflow(**data["workflows"][0])
    assert wf.version == 1
    print("   ok — a freshly selected workflow starts at version=1, never "
          "'unset' (requirement 1)")


def test_question_mutation_increments_version():
    client = _client()
    data = _material(client)
    wf = QuestionWorkflow(**data["workflows"][0])
    before = wf.version

    approved = review.approve_question(wf)
    assert approved.version == before + 1, approved.version

    rejected = review.reject_question(wf)
    assert rejected.version == before + 1, rejected.version

    sections = _sections_for(data["doc_id"])
    regenerated = review.regenerate(wf, "make it sharper", sections)
    assert regenerated.version == before + 1, regenerated.version
    print("   ok — approve_question/reject_question/regenerate each bump "
          "version by exactly one (requirement 2)")


def test_teaching_approach_mutation_increments_version():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = QuestionWorkflow(**_workflow_with_teaching_approach(doc_id, data))
    before = wf.version

    approved = review.approve_teaching_approach(wf)
    assert approved.version == before + 1, approved.version

    sections = _sections_for(doc_id)
    regenerated = review.regenerate_teaching_approach(wf, "try a different device", sections)
    assert regenerated.version == before + 1, regenerated.version
    print("   ok — approve_teaching_approach/regenerate_teaching_approach each "
          "bump version by exactly one (requirement 3)")


# ------------------------------------------------------------------------- 4/5
# invalidation still fires, and now carries a version bump with it

def test_question_mutation_invalidates_downstream_teaching_approach_approval():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = QuestionWorkflow(**_workflow_with_teaching_approach(doc_id, data))
    wf = review.approve_teaching_approach(wf)
    assert wf.approved_teaching_approach is not None

    sections = _sections_for(doc_id)
    regenerated = review.regenerate(wf, "reconsider the wording", sections)

    assert regenerated.teaching_approach is None
    assert regenerated.teaching_approach_approval == TeachingApproachApproval()
    assert regenerated.approved_teaching_approach is None
    print("   ok — regenerating the question clears teaching_approach and its "
          "approval, so a stale approval cannot survive under a new question "
          "(requirement 4)")


def test_teaching_approach_mutation_invalidates_downstream_script_and_visual_state():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = QuestionWorkflow(**_workflow_with_visual_plan(doc_id, data))
    assert wf.script is not None
    assert wf.visual_strategy is not None

    sections = _sections_for(doc_id)
    regenerated = review.regenerate_teaching_approach(wf, "use a different device", sections)

    assert regenerated.script is None
    assert regenerated.visual_strategy is None
    assert regenerated.approved_visual_strategy is None
    print("   ok — regenerating the teaching approach clears script and "
          "visual_strategy (and resets visual_plan_approval), so neither can "
          "be finalized as still current (requirement 5)")


# --------------------------------------------------------------------------- 6
# approval-aware endpoints already re-derive from the workflow itself

def test_unapproved_workflow_cannot_pass_an_approval_aware_endpoint():
    client = _client()
    data = _material(client)
    wf = data["workflows"][0]   # question_approval.status == "pending"

    r = client.post("/api/teaching-approach/approve",
                     json={"doc_id": data["doc_id"], "workflow": wf})
    assert r.status_code == 409, r.text
    print("   ok — /api/teaching-approach/approve refuses a workflow whose "
          "question is not approved, deriving that from the workflow itself "
          "(requirement 6)")


# --------------------------------------------------------------------------- 7
# a hand-forged / inconsistent snapshot is rejected even though its own
# status field claims an approval that happened

def test_inconsistent_workflow_version_is_rejected_at_finalize():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = _workflow_with_teaching_approach(doc_id, data)

    # FORGE IT: teaching_approach_approval claims "approved" while
    # question_approval has reverted to "pending" — exactly the shape
    # approved_teaching_approach ALONE cannot catch, since that property only
    # reads teaching_approach_approval.status, never question_approval's.
    wf["question_approval"]["status"] = "pending"
    wf["teaching_approach_approval"]["status"] = "approved"

    topic = wf["selection"]["topic"]
    body = {
        "doc_id": doc_id,
        "approved": [{
            "topic": topic,
            "qa": {"question": "does paging avoid fragmentation?",
                   "beats": [{"role": "narrator", "line": "hi",
                              "on_screen": "x", "visual_ref": "v0"}]},
            "workflow": wf,
        }],
        "do_svg": False, "do_judge": False, "do_voice": False,
    }
    r = client.post("/api/finalize", json=body)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["built"] == [], result
    assert len(result["failed"]) == 1, result
    assert "inconsistent" in result["failed"][0]["error"], result["failed"][0]
    print("   ok — /api/finalize rejects a workflow whose teaching-approach "
          "approval contradicts its own (unapproved) question — the version/"
          "consistency check the stateless architecture CAN do (requirement 7)")


# --------------------------------------------------------------------------- 8
# a workflow that is honestly incomplete (nothing forged, just not approved
# yet) is refused too

def test_finalize_rejects_workflow_missing_required_approvals():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = _workflow_with_teaching_approach(doc_id, data)   # teaching_approach
    # chosen but NOT approved — legitimate "not there yet" state, no forgery.
    assert QuestionWorkflow(**wf).approved_teaching_approach is None

    topic = wf["selection"]["topic"]
    body = {
        "doc_id": doc_id,
        "approved": [{
            "topic": topic,
            "qa": {"question": "does paging avoid fragmentation?",
                   "beats": [{"role": "narrator", "line": "hi",
                              "on_screen": "x", "visual_ref": "v0"}]},
            "workflow": wf,
        }],
        "do_svg": False, "do_judge": False, "do_voice": False,
    }
    r = client.post("/api/finalize", json=body)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["built"] == [], result
    assert len(result["failed"]) == 1, result
    assert "teaching_approach_approval" in result["failed"][0]["error"], result["failed"][0]
    print("   ok — /api/finalize refuses to finalize a workflow whose teaching "
          "approach is not approved, rather than silently planning visuals as "
          "though it were (requirement 8)")


# --------------------------------------------------------------------------- 9
# the honest, fully-approved case still works

def test_finalize_accepts_a_valid_approved_workflow():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    wf = _workflow_with_visual_plan(doc_id, data)
    assert QuestionWorkflow(**wf).approved_teaching_approach is not None
    assert wf["script"] is not None

    topic = wf["selection"]["topic"]
    short_id = topic["id"]
    body = {
        "doc_id": doc_id,
        "approved": [{
            "topic": topic,
            "qa": {"question": wf["script"]["question"], "beats": wf["script"]["beats"]},
            "workflow": wf,
        }],
        "do_svg": False, "do_judge": False, "do_voice": False,
    }
    try:
        r = client.post("/api/finalize", json=body)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["failed"] == [], result
        assert short_id in result["built"], result
        print("   ok — /api/finalize accepts a genuinely approved workflow "
              "fixture (question approved, teaching approach approved, "
              "script matching the workflow's own) and builds it "
              "(requirement 9)")
    finally:
        out = config.OUTPUT_DIR / f"{short_id}.json"
        if out.exists():
            out.unlink()


# -------------------------------------------------------------------------- 10
# the legacy no-workflow finalize path is untouched

def test_finalize_simple_flow_unchanged_without_a_workflow():
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    topic = data["workflows"][0]["selection"]["topic"]
    short_id = topic["id"]

    body = {
        "doc_id": doc_id,
        "approved": [{
            "topic": topic,
            "qa": {"question": "does paging avoid fragmentation?",
                   "beats": [{"role": "narrator", "line": "hi",
                              "on_screen": "x", "visual_ref": "v0"}]},
            # NO "workflow" KEY AT ALL — the simple flow.
        }],
        "do_svg": False, "do_judge": False, "do_voice": False,
    }
    try:
        r = client.post("/api/finalize", json=body)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["failed"] == [], result
        assert short_id in result["built"], result
        print("   ok — /api/finalize's no-workflow ('simple flow') path still "
              "builds a short from bare topic+qa, completely unaffected by "
              "the Step 6 workflow-approval checks (requirement 10)")
    finally:
        out = config.OUTPUT_DIR / f"{short_id}.json"
        if out.exists():
            out.unlink()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} workflow versioning / approval-authority tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL WORKFLOW VERSIONING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
