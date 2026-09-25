"""
Step 10 hardening: sub-beat highlighting — the smallest useful version.

schema.BeatStrategy.sub_focus is a NEW, optional, ordered list of additional
things a single beat calls out beyond its one `focus` — for the beat that
genuinely names more than one object ("count is the current value... setCount
changes it") in one breath. Deliberately not a timeline: no entry carries a
timestamp. checks.check_sub_focus_is_grounded is the validator that keeps it
honest — every named entry must be a real label on the frame or a real word
in the beat's own line.

DOCUMENTED LIMITATION, on purpose: nothing populates this field yet
(skills/visuals.py's design prompt does not ask for it) and nothing renders
it with sub-beat timing yet (web/src/AnimatedSvg.tsx's data-role="focus" is
still per-frame, not per-word — see the field's own docstring). This is the
validated foundation that work would build on; true word-level visual sync
is frontend animation work, out of scope for this backend hardening pass.

No API key, no network, no real LLM calls.

    SHORTS_STUB=1 python -m shorts.sub_focus_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks
from shorts.schema import Beat, BeatStrategy, Cell, Frame, ShortUnit, Visual


def _unit(line: str, sub_focus: list[str], frame_labels: list[str]) -> ShortUnit:
    frame = Frame(template="bar", cells=[Cell(label=l, role="plain") for l in frame_labels])
    strategy = BeatStrategy(ref="v0", concept="c", relationship="structure",
                            must_see="m", focus=frame_labels[0] if frame_labels else "x",
                            sub_focus=sub_focus)
    beat = Beat(line=line, on_screen="B0", visual_ref="v0")
    visual = Visual(ref="v0", type="diagram", spec="s", frame=frame, strategy=strategy)
    return ShortUnit(short_id="t_subfocus", session_id="probe", source_section_id="1.1",
                     question="q", estimated_seconds=10, beats=[beat], visuals={"v0": visual})


def test_default_is_empty_and_unchanged():
    strategy = BeatStrategy(ref="v0", concept="c", relationship="structure",
                            must_see="m", focus="x")
    assert strategy.sub_focus == []
    print("   ok — sub_focus defaults to empty, so every strategy written "
          "before this field existed still loads unchanged")


def test_sub_focus_grounded_in_frame_labels_passes():
    unit = _unit("count is the current value, and setCount changes it.",
                sub_focus=["count", "setCount"],
                frame_labels=["count", "setCount"])
    result = checks.check_sub_focus_is_grounded(unit)
    assert result.passed, result.reason
    print("   ok — sub_focus entries that match real labels on the frame pass")


def test_sub_focus_grounded_in_narration_passes():
    """Grounded in the SPOKEN line even when the frame's own labels use
    different exact strings (e.g. a code frame whose text is the line
    itself) — the check accepts either kind of evidence."""
    unit = _unit("The request travels from the client to the server.",
                sub_focus=["client", "server"],
                frame_labels=["Request"])
    result = checks.check_sub_focus_is_grounded(unit)
    assert result.passed, result.reason
    print("   ok — sub_focus entries grounded in the beat's own narration "
          "(not necessarily the frame's labels) also pass")


def test_invented_sub_focus_is_caught():
    unit = _unit("count is the current value.", sub_focus=["setCount"],
                frame_labels=["count"])
    result = checks.check_sub_focus_is_grounded(unit)
    assert not result.passed
    assert "setCount" in result.reason
    print(f"   ok — a sub_focus entry that names something not on the frame "
          f"and not in the narration is caught: {result.reason}")


def test_empty_sub_focus_is_skipped():
    unit = _unit("count is the current value.", sub_focus=[], frame_labels=["count"])
    result = checks.check_sub_focus_is_grounded(unit)
    assert result.passed, result.reason
    assert "no sub_focus" in result.reason
    print("   ok — a beat with no sub_focus at all (the ordinary case, "
          "today, for every beat) is skipped, not penalized")


def test_wired_into_unit_graders_not_design_gate():
    assert checks.check_sub_focus_is_grounded in checks.UNIT_GRADERS
    from shorts.skills import visuals as visuals_mod
    graders = visuals_mod._design_graders(section=None, understanding=None)
    assert checks.check_sub_focus_is_grounded not in graders, (
        "nothing populates sub_focus yet, so gating a paid redesign retry "
        "on it would only ever cost money for zero effect")
    print("   ok — registered in UNIT_GRADERS (validates the moment "
          "anything populates sub_focus) and not in the design retry gate "
          "(nothing does yet, so gating it would be pure cost)")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} sub-focus hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SUB-FOCUS HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
