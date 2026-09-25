"""
Step 7 hardening: cost — stop at the first valid attempt, no duplicate calls.

design_visuals already had the right shape (`if not problems: return visuals,
[]` — one call for a short whose first attempt is clean) and plan_strategy
already runs once per short and is reused across attempts. This file adds
the call-count assertion neither had: a mocked spec_visuals proves the loop
never asks a second time once the first attempt already passed every
gating grader.

No API key, no network, no real LLM calls — spec_visuals itself is replaced
with a counting fake; nothing underneath it runs.

    SHORTS_STUB=1 python -m shorts.cost_hardening_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts.schema import Beat, Cell, Frame, Script, Visual
from shorts.skills import visuals as visuals_mod


def _clean_visuals(script: Script) -> dict[str, Visual]:
    """One frame per beat, each a `bar` with exactly one hero cell — passes
    every check in _design_graders(section=None, understanding=None) with no
    section/strategy/understanding in play (the same shape
    step8_hardening_test.py's check_ends_on_answer fixtures use)."""
    out = {}
    for beat in script.beats:
        out[beat.visual_ref] = Visual(ref=beat.visual_ref, type="diagram", spec="s",
                                      frame=Frame(template="bar",
                                                 cells=[Cell(label=beat.on_screen, role="hero")]))
    return out


def _script(n_beats: int = 1) -> Script:
    beats = [Beat(line=f"Beat {i}.", on_screen=f"B{i}", visual_ref=f"v{i}")
            for i in range(n_beats)]
    return Script(short_id="t_cost", question="q", beats=beats)


def test_design_visuals_calls_spec_visuals_exactly_once_when_clean():
    script = _script(1)
    calls = []
    real_spec_visuals = visuals_mod.spec_visuals

    def fake_spec_visuals(script_, section=None, feedback=None, model_override=None,
                          strategy=None):
        calls.append(1)
        return _clean_visuals(script_)

    visuals_mod.spec_visuals = fake_spec_visuals
    try:
        visuals, problems = visuals_mod.design_visuals(
            script, section=None, draw=False, vision=False, strategy=None, attempts=3)
    finally:
        visuals_mod.spec_visuals = real_spec_visuals

    assert len(calls) == 1, f"expected exactly 1 call, got {len(calls)}"
    assert problems == [], problems
    assert set(visuals) == {"v0"}
    print("   ok — a short whose first design attempt already passes every "
          "gating grader costs exactly one spec_visuals call, never a "
          "second (requirement: stop early on the first valid attempt)")


def test_design_visuals_stops_within_the_configured_attempt_cap():
    """A spec_visuals that NEVER produces a clean attempt must still stop at
    exactly `attempts` calls, never run away — the other half of the same
    cost guarantee."""
    script = _script(2)
    calls = []
    real_spec_visuals = visuals_mod.spec_visuals

    def fake_spec_visuals_always_broken(script_, section=None, feedback=None,
                                        model_override=None, strategy=None):
        calls.append(1)
        # Both beats get the BYTE-IDENTICAL frame — check_frames_develop's
        # own rule ("identical" branch) fails this every attempt, on
        # purpose, since this fake never varies its output.
        same = Frame(template="bar", cells=[Cell(label="X", role="hero")])
        return {beat.visual_ref: Visual(ref=beat.visual_ref, type="diagram", spec="s",
                                        frame=same)
               for beat in script_.beats}

    visuals_mod.spec_visuals = fake_spec_visuals_always_broken
    try:
        visuals, problems = visuals_mod.design_visuals(
            script, section=None, draw=False, vision=False, strategy=None, attempts=3)
    finally:
        visuals_mod.spec_visuals = real_spec_visuals

    assert len(calls) == 3, f"expected exactly 3 calls (the configured cap), got {len(calls)}"
    print(f"   ok — a short that never passes still stops at the configured "
          f"attempt cap (3), not fewer and not more: {len(calls)} calls")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} cost hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL COST HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
