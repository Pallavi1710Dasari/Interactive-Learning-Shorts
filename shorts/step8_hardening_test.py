"""
Step 8: the final hardening pass before the first real reel — deterministic
tests for the four concrete fixes made in this step:

  1. VisualStrategy.compatible_with + server.py's finalize-time check that a
     re-planned strategy still matches what a human approved.
  2. checks.check_ends_on_answer wired into UNIT_GRADERS and design_visuals's
     own retry gate.
  3. checks.run_script_graders(..., strict_stage_references=True) — only
     write_and_grade_script_for_workflow passes it — turning off the
     "zero beats reference a step" inconclusive-pass for freshly generated
     workflow scripts, while leaving every legacy/other caller unchanged.

No API key, no network, no real LLM calls — SHORTS_STUB=1 for the one
end-to-end finalize test; everything else is hand-built fixtures or direct
grader calls.

    SHORTS_STUB=1 python -m shorts.step8_hardening_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks, review
from shorts.schema import (
    Script, Beat, Section, SectionUnderstanding, TeachingStep,
    Visual, Frame, Cell, VisualStrategy, BeatStrategy, ShortUnit, QuestionWorkflow,
)
from shorts.skills import visuals as visuals_mod
from shorts.server_workflow_test import (
    _client, _material, _workflow_with_visual_plan,
)
import shorts.server as server


# ============================================================== 1. visual strategy

def _strategy(subject="a stack", refs=("v1", "v2")) -> VisualStrategy:
    return VisualStrategy(subject=subject, beats=[
        BeatStrategy(ref=r, concept="c", relationship="structure",
                     must_see="m", focus="f") for r in refs])


def test_identical_strategy_is_compatible():
    s = _strategy()
    assert s.compatible_with(s)
    assert s.compatible_with(s.model_copy(deep=True))
    print("   ok — a strategy is compatible with an identical copy of itself")


def test_reworded_same_subject_same_refs_is_compatible():
    approved = _strategy()
    replanned = VisualStrategy(subject=approved.subject, beats=[
        BeatStrategy(ref="v1", concept="c", relationship="process",  # refined
                     must_see="a DIFFERENT must_see, the judge's own words",
                     focus="f"),
        BeatStrategy(ref="v2", concept="c", relationship="structure",
                     must_see="m", focus="f"),
    ])
    assert replanned.compatible_with(approved)
    print("   ok — a re-plan that keeps the same subject and beat coverage is "
          "compatible even though per-beat relationship/must_see changed — "
          "legitimate re-planning is not penalized (requirement: legitimate "
          "re-plan that remains compatible)")


def test_different_subject_is_incompatible():
    approved = _strategy(subject="a stack")
    replanned = _strategy(subject="a queue")
    assert not replanned.compatible_with(approved)
    print("   ok — a re-plan with a different subject is incompatible")


def test_different_beat_coverage_is_incompatible():
    approved = _strategy(refs=("v1", "v2"))
    replanned = _strategy(refs=("v1", "v3"))
    assert not replanned.compatible_with(approved)
    print("   ok — a re-plan that covers different beats is incompatible")


def _approved_visual_plan_workflow(client):
    """A fully-approved workflow: question approved, teaching approach
    approved, script generated, visual_strategy planned AND its approval
    granted — the one precondition the new finalize check activates on."""
    data = _material(client)
    doc_id = data["doc_id"]
    wf = QuestionWorkflow(**_workflow_with_visual_plan(doc_id, data))
    wf = review.approve_visual_plan(wf)
    assert wf.approved_visual_strategy is not None
    return doc_id, wf


def _finalize_body(doc_id, wf: QuestionWorkflow) -> dict:
    topic = wf.selection.topic.model_dump()
    return {
        "doc_id": doc_id,
        "approved": [{
            "topic": topic,
            "qa": {"question": wf.script.question,
                   "beats": [b.model_dump() for b in wf.script.beats]},
            "workflow": wf.model_dump(),
        }],
        "do_svg": False, "do_judge": False, "do_voice": False,
    }


def test_finalize_succeeds_when_approved_strategy_is_unchanged():
    """No monkeypatch: do_judge=False means the vision judge (the only thing
    that can trigger a re-plan) never runs, so the strategy actually used is
    the exact approved one — the ordinary case."""
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    try:
        r = client.post("/api/finalize", json=_finalize_body(doc_id, wf))
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["failed"] == [], result
        assert short_id in result["built"], result
        print("   ok — finalize succeeds when the strategy actually drawn is "
              "the approved one, unchanged (requirement: approved strategy "
              "unchanged -> finalize succeeds)")
    finally:
        from shorts import config
        out = config.OUTPUT_DIR / f"{short_id}.json"
        if out.exists():
            out.unlink()


def test_finalize_succeeds_on_a_compatible_replan():
    """Simulates design_visuals having legitimately re-planned the strategy
    (same subject, same beat coverage, refined per-beat detail) by wrapping
    the real function and substituting strategy_out afterward — the cheapest
    deterministic way to exercise this without driving the real vision-judge
    retry loop end to end."""
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    approved_strategy = wf.approved_visual_strategy
    real_design_visuals = server.design_visuals

    def fake_design_visuals(script, section, **kwargs):
        visuals, problems = real_design_visuals(script, section, **kwargs)
        strategy_out = kwargs.get("strategy_out")
        if strategy_out is not None:
            strategy_out["strategy"] = VisualStrategy(
                subject=approved_strategy.subject,
                beats=[bs.model_copy(update={"must_see": bs.must_see + " (re-planned)"})
                      for bs in approved_strategy.beats])
        return visuals, problems

    server.design_visuals = fake_design_visuals
    try:
        r = client.post("/api/finalize", json=_finalize_body(doc_id, wf))
    finally:
        server.design_visuals = real_design_visuals
    try:
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["failed"] == [], result
        assert short_id in result["built"], result
        print("   ok — finalize succeeds when design_visuals legitimately "
              "re-planned the strategy but kept the same subject/beat "
              "coverage (requirement: legitimate re-plan that remains "
              "compatible -> finalize succeeds)")
    finally:
        from shorts import config
        out = config.OUTPUT_DIR / f"{short_id}.json"
        if out.exists():
            out.unlink()


def test_finalize_rejects_an_incompatible_replan():
    """Same simulation, but the substituted strategy has a different subject
    — a re-plan that drifted onto a different composition than the one a
    human approved."""
    client = _client()
    doc_id, wf = _approved_visual_plan_workflow(client)
    short_id = wf.selection.topic.id
    approved_strategy = wf.approved_visual_strategy
    real_design_visuals = server.design_visuals

    def fake_design_visuals(script, section, **kwargs):
        visuals, problems = real_design_visuals(script, section, **kwargs)
        strategy_out = kwargs.get("strategy_out")
        if strategy_out is not None:
            strategy_out["strategy"] = VisualStrategy(
                subject="a completely different subject the judge steered toward",
                beats=list(approved_strategy.beats))
        return visuals, problems

    server.design_visuals = fake_design_visuals
    try:
        r = client.post("/api/finalize", json=_finalize_body(doc_id, wf))
    finally:
        server.design_visuals = real_design_visuals
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["built"] == [], result
    assert len(result["failed"]) == 1, result
    assert "no longer matches the approved visual plan" in result["failed"][0]["error"], \
        result["failed"][0]
    print("   ok — finalize rejects a workflow whose actually-drawn strategy "
          "diverged (different subject) from the approved one, instead of "
          "silently shipping it as though it were still approved "
          "(requirement: incompatible final strategy -> finalize is "
          "rejected)")


# ============================================================== 2. check_ends_on_answer

def _unit_with_last_frame(frame: Frame) -> ShortUnit:
    beats = [Beat(line="A stack only allows access at one end.", on_screen="Stack",
                  visual_ref="v0"),
             Beat(line="The last item pushed is the first popped.", on_screen="LIFO",
                  visual_ref="v1", source_quote="The last item pushed is the first popped.")]
    visuals = {"v0": Visual(ref="v0", type="diagram", spec="stub",
                            frame=Frame(template="bar", cells=[Cell(label="a", role="hero")])),
               "v1": Visual(ref="v1", type="diagram", spec="stub", frame=frame)}
    return ShortUnit(short_id="t_ends", session_id="probe", source_section_id="1.1",
                     question="how does a stack behave", estimated_seconds=20,
                     beats=beats, visuals=visuals)


def test_check_ends_on_answer_passes_when_final_frame_has_a_hero():
    unit = _unit_with_last_frame(Frame(template="bar", cells=[Cell(label="LIFO", role="hero")]))
    result = checks.check_ends_on_answer(unit)
    assert result.passed, result.reason
    print("   ok — a short whose final frame marks a hero element passes "
          "check_ends_on_answer (requirement: correct final landing -> passes)")


def test_check_ends_on_answer_fails_on_a_neutral_final_frame():
    unit = _unit_with_last_frame(Frame(template="bar", cells=[Cell(label="LIFO", role="plain")]))
    result = checks.check_ends_on_answer(unit)
    assert not result.passed
    print(f"   ok — a short that trails off on a neutral final frame (no hero "
          f"anywhere) fails check_ends_on_answer: {result.reason} "
          f"(requirement: neutral/wrong final frame -> fails)")


def test_check_ends_on_answer_does_not_reject_a_hard_coded_focus_template():
    # `stat`/`takeaway` hard-code their own emphasis and carry no role-bearing
    # collections at all — exactly the "genuinely static conceptual visual"
    # class Step 7 already proved must not be falsely rejected elsewhere.
    unit = _unit_with_last_frame(Frame(template="stat", value="LIFO", caption="order"))
    result = checks.check_ends_on_answer(unit)
    assert result.passed, result.reason
    print("   ok — a legitimate stat/takeaway final frame (hard-codes its own "
          "focus, no role-bearing elements to check) is not falsely rejected")


def test_check_ends_on_answer_is_wired_into_unit_graders():
    assert checks.check_ends_on_answer in checks.UNIT_GRADERS
    print("   ok — check_ends_on_answer is registered in checks.UNIT_GRADERS "
          "(load-bearing on the post-build warnings report)")


def test_check_ends_on_answer_is_wired_into_design_visuals_retry_gate():
    graders = visuals_mod._design_graders(section=None, understanding=None)
    assert checks.check_ends_on_answer in graders
    print("   ok — check_ends_on_answer is registered in design_visuals's own "
          "_design_graders (load-bearing DURING generation, gates a retry)")


# ============================================================== 3. relates_to_step strictness

def _step(stage=None, concept="how the stack behaves", n=1) -> TeachingStep:
    return TeachingStep(concept=f"{concept} {n}", purpose=f"needed before stack step {n + 1}",
                        explanation_goal=f"learner understands stack step {n}", stage=stage)


def _understanding(stages: list, core_idea="a stack is LIFO") -> SectionUnderstanding:
    steps = [_step(stage=s, n=i) for i, s in enumerate(stages, 1)]
    return SectionUnderstanding(section_id="1.1", core_idea=core_idea,
                                teaching_sequence=steps)


def _script(relates: list, question="why a stack is LIFO") -> Script:
    beats = [Beat(line="A stack only allows access at one end.", on_screen="Stack",
                  visual_ref="v0")]
    for i, r in enumerate(relates, 1):
        beats.append(Beat(line=f"Body sentence number {i}.", on_screen=f"B{i}",
                          visual_ref=f"v{i}", source_quote=f"Body sentence number {i}.",
                          relates_to_step=r))
    return Script(short_id="t1", question=question, beats=beats)


def test_strict_all_body_beats_linked_passes():
    understanding = _understanding(["concept", "mechanism", "result"])
    script = _script([1, 2, 3])
    result = checks.check_teaching_sequence(understanding, script=script,
                                            strict_stage_references=True)
    assert result.passed, result.reason
    print("   ok — strict mode passes when every body beat correctly links to "
          "a real, staged teaching step (requirement: all body beats "
          "correctly linked -> pass)")


def test_strict_one_missing_reference_fails():
    # beat 2 has no relates_to_step at all; beats 1 and 3 do.
    understanding = _understanding(["concept", "mechanism", "result"])
    script = _script([1, None, 3])
    result = checks.check_teaching_sequence(understanding, script=script,
                                            strict_stage_references=True)
    assert not result.passed
    assert "beat 2" in result.reason and "no relates_to_step" in result.reason
    print(f"   ok — strict mode fails a script where even ONE body beat has "
          f"no relates_to_step, though others do: {result.reason} "
          f"(requirement: one invalid reference -> fail)")


def test_strict_one_out_of_range_reference_fails():
    understanding = _understanding(["concept", "result"])
    script = _script([1, 5])  # only 2 steps exist
    result = checks.check_teaching_sequence(understanding, script=script,
                                            strict_stage_references=True)
    assert not result.passed
    assert "out of range" in result.reason
    print(f"   ok — strict mode fails an out-of-range relates_to_step exactly "
          f"like non-strict mode does: {result.reason} (requirement: one "
          f"invalid reference -> fail)")


def test_strict_zero_references_fails_instead_of_passing_vacuously():
    understanding = _understanding(["concept", "mechanism", "result"])
    script = _script([None, None, None])
    result = checks.check_teaching_sequence(understanding, script=script,
                                            strict_stage_references=True)
    assert not result.passed
    print(f"   ok — strict mode FAILS a newly generated workflow script with "
          f"zero beat-to-step references, instead of the inconclusive pass "
          f"legacy callers get: {result.reason} (requirement: zero "
          f"references in a newly generated workflow script -> fail)")


def test_non_strict_zero_references_remains_inconclusive_pass():
    """The exact same fixture as above, graded the way every OTHER caller of
    run_script_graders/check_teaching_sequence still does (the default) —
    proves legacy behaviour is untouched."""
    understanding = _understanding(["concept", "mechanism", "result"])
    script = _script([None, None, None])
    result = checks.check_teaching_sequence(understanding, script=script)
    assert result.passed, result.reason
    print("   ok — the SAME zero-reference script still passes (inconclusive, "
          "not a failure) when strict_stage_references is left at its "
          "default False — legacy/other callers are unaffected (requirement: "
          "legacy fixture without references -> remains compatible)")


def test_write_and_grade_script_for_workflow_requests_strict_checking():
    """Integration-level proof that the ONE authoritative new-workflow script
    path (Step 5) actually passes strict_stage_references=True to the
    grader — not just that the grader supports the flag."""
    client = _client()
    data = _material(client)
    doc_id = data["doc_id"]
    from shorts.skills import framing, teaching_approach as ta_mod
    wf = QuestionWorkflow(**data["workflows"][0])
    wf = review.approve_question(wf)
    sections = server._sections(doc_id)
    wf = framing.frame_workflow(wf, sections)
    wf = ta_mod.choose_teaching_approach_for_workflow(wf, sections)
    wf = review.approve_teaching_approach(wf)

    captured_kwargs = []
    real_run_script_graders = checks.run_script_graders

    def spy(script, *a, **kw):
        captured_kwargs.append(kw)
        return real_run_script_graders(script, *a, **kw)

    checks.run_script_graders = spy
    try:
        from shorts.skills.script import write_and_grade_script_for_workflow
        section = sections[0]
        write_and_grade_script_for_workflow(wf, section)
    finally:
        checks.run_script_graders = real_run_script_graders

    assert captured_kwargs, "run_script_graders was never called"
    assert all(kw.get("strict_stage_references") is True for kw in captured_kwargs), captured_kwargs
    print("   ok — write_and_grade_script_for_workflow passes "
          "strict_stage_references=True on every grading attempt — the "
          "'existing workflow generation context' the strict check is "
          "scoped to")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} Step 8 hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL STEP 8 HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
