"""
Step 3 hardening: cross-beat visual continuity.

checks.check_visual_continuity is new — none of the existing frame graders
(check_frames_develop, check_frames_match_strategy,
check_physical_form_matches_template, check_motion_concept_not_static,
check_mechanism_stage_shows_change) ask the cross-beat question this one
does: does a later beat's switch to a different template say, anywhere, that
it is building on an established composition, or does it just abandon one?
See the grader's own docstring for why each existing check passes the exact
shape this one catches.

No API key, no network, no real LLM calls — every test builds a ShortUnit
fixture directly and calls the grader.

    SHORTS_STUB=1 python -m shorts.visual_continuity_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks
from shorts.schema import Beat, BeatStrategy, Frame, ShortUnit, Visual


def _strategy(ref: str, changes_from_previous: str = "",
             relationship: str = "structure") -> BeatStrategy:
    return BeatStrategy(ref=ref, concept="c", relationship=relationship,
                        must_see="m", focus="f",
                        changes_from_previous=changes_from_previous)


def _unit(templates: list[str], changes: list[str], with_strategy: bool = True) -> ShortUnit:
    """One beat per template, visual_ref v0..vN-1, each frame distinct enough
    that check_frames_develop's own _near_same never collapses them (that
    grader is not under test here, but a fixture that trips it would make
    the wrong check's failure show up in the assertion)."""
    beats, visuals = [], {}
    for i, template in enumerate(templates):
        ref = f"v{i}"
        beats.append(Beat(line=f"Beat number {i} of the explanation.",
                          on_screen=f"Screen {i}", visual_ref=ref))
        strategy = _strategy(ref, changes[i]) if with_strategy else None
        visuals[ref] = Visual(ref=ref, type="diagram", spec=f"frame {i}",
                              frame=Frame(template=template), strategy=strategy)
    return ShortUnit(short_id="t_continuity", session_id="probe", source_section_id="1.1",
                     question="how does it work", estimated_seconds=20,
                     beats=beats, visuals=visuals)


def test_established_composition_abandoned_is_flagged():
    # 3 beats of 'code' (a real build, run_len reaches 3), then an unrelated
    # 'compare' beat with nothing in changes_from_previous about continuity.
    unit = _unit(["code", "code", "code", "compare"],
                ["", "adds the next line", "adds another line",
                 "shows count and setCount side by side"])
    result = checks.check_visual_continuity(unit)
    assert not result.passed
    assert "v3" in result.reason and "abandoned" in result.reason
    print(f"   ok — a 3-beat composition dropped for an unrelated template "
          f"with no continuity claimed is flagged: {result.reason}")


def test_continuity_claim_in_changes_from_previous_passes():
    unit = _unit(["code", "code", "code", "compare"],
                ["", "adds the next line", "adds another line",
                 "keeps the function block from the previous frame and adds "
                 "a comparison of count and setCount beside it"])
    result = checks.check_visual_continuity(unit)
    assert result.passed, result.reason
    print("   ok — the same template switch passes when changes_from_previous "
          "actually says something carries over")


def test_early_switch_with_no_established_run_is_not_flagged():
    # Switches on beat 1 already (run_len is still 1 when it switches) —
    # nothing has been built yet to abandon.
    unit = _unit(["analogy", "code", "code"],
                ["", "introduces the function", "adds the call"])
    result = checks.check_visual_continuity(unit)
    assert result.passed, result.reason
    print("   ok — an early template switch, before any multi-beat "
          "composition exists, is not treated as abandonment")


def test_same_template_throughout_passes():
    unit = _unit(["state", "state", "state"], ["", "value updates", "value updates again"])
    result = checks.check_visual_continuity(unit)
    assert result.passed, result.reason
    print("   ok — a short that never switches templates passes trivially")


def test_frames_with_no_strategy_are_skipped_silently():
    """Units built before the strategist existed (or a caller with no
    strategy in hand at all) must still grade cleanly — same precedent as
    check_frames_match_strategy."""
    unit = _unit(["code", "code", "code", "compare"],
                ["", "", "", ""], with_strategy=False)
    result = checks.check_visual_continuity(unit)
    assert result.passed, result.reason
    print("   ok — frames with no strategy at all are not flagged (nothing "
          "to check changes_from_previous against)")


def test_mechanism_beat_does_not_fall_back_to_comparison_panel():
    """Step 4's literal case: a mechanism/process concept, mid-build, must
    not silently fall back to a comparison/panel representation just
    because that template is easy to generate."""
    unit = _unit(["state", "state", "compare"],
                ["", "the value updates in place",
                 "shows the getter and setter as two cards"],
                )
    # Make the abandoning beat's own relationship explicit: a mechanism/
    # process claim, not a genuine two-way comparison.
    unit.visuals["v2"].strategy = _strategy("v2", "shows the getter and "
                                            "setter as two cards",
                                            relationship="process")
    result = checks.check_visual_continuity(unit)
    assert not result.passed
    assert "v2" in result.reason
    print(f"   ok — a mechanism (process) beat falling back to an unrelated "
          f"'compare' panel after an established composition is caught: "
          f"{result.reason}")


def test_wired_into_unit_graders_and_design_retry_gate():
    assert checks.check_visual_continuity in checks.UNIT_GRADERS
    from shorts.skills import visuals as visuals_mod
    graders = visuals_mod._design_graders(section=None, understanding=None)
    assert checks.check_visual_continuity in graders, (
        "this is actionable by a redesign (pick a template that continues "
        "the composition, or say what carries over) — the same shape as "
        "check_frames_match_strategy and its neighbours, which all gate")
    print("   ok — registered in both UNIT_GRADERS (reports on every build) "
          "and _design_graders (gates a redesign attempt)")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} visual-continuity hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL VISUAL-CONTINUITY HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
