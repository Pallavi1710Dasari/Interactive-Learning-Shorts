"""
Step 6 hardening: can the visual system actually show a mechanism, generically?

THE AUDIT'S FINDING FOR THIS STEP: the generic machinery already exists —
schema.Relationship + schema.PhysicalForm decide the CLAIM and the SHAPE,
checks.check_frames_match_strategy / check_physical_form_matches_template
enforce that the template chosen can actually carry them, and
schema.Slot.state (arriving/leaving) + schema.Store.pointer_at_previous +
checks.check_state_item_transitions_visible enforce that a change is SEEN,
not just relabelled. None of it is React/useState-specific — it is keyed on
`relationship`/`physical_form`, not on any topic's vocabulary.

This file proves that claim with four GENERIC (non-React) fixtures, one per
Step 6 example: a value/state transition, a parent-child relationship, a
data-movement relationship, and a code-only concept. If any of these needed
a topic-specific change to represent, that would be the real gap Step 6 asks
about; none of them do.

No API key, no network, no real LLM calls — every fixture is a hand-built
ShortUnit, and every assertion calls an existing deterministic grader
directly.

    SHORTS_STUB=1 python -m shorts.mechanism_representation_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from shorts import checks
from shorts.schema import (
    Beat, BeatStrategy, Branch, Cell, Frame, Graph, Node, ShortUnit, Slot, Store, Visual,
)


def _unit(beats, visuals) -> ShortUnit:
    return ShortUnit(short_id="t_mechanism", session_id="probe", source_section_id="1.1",
                     question="how does it work", estimated_seconds=20,
                     beats=beats, visuals=visuals)


# ============================================================ 1. value/state transition

def test_value_transition_is_representable_and_checked():
    """A register/counter holding a value, updated — deliberately NOT React:
    'a counter starts at 0, then an increment sets it to 1'."""
    before = Frame(template="state", store=Store(
        label="Counter", orientation="horizontal",
        slots=[Slot(label="0", role="hero", state="resting")]))
    # Both the outgoing and incoming value are present ON THIS FRAME so the
    # transition itself — not just the destination — is drawn: "0" marked
    # leaving, "1" marked arriving. See check_state_item_transitions_visible's
    # own three rules for why this, rather than "1" simply replacing "0" in
    # place, is what the checker (and a viewer) needs to see a change rather
    # than a teleport.
    after = Frame(template="state", store=Store(
        label="Counter", orientation="horizontal",
        slots=[Slot(label="0", role="lost", state="leaving"),
              Slot(label="1", role="hero", state="arriving")]))
    strategy_before = BeatStrategy(ref="v0", concept="the counter holds a value",
                                   relationship="structure", physical_form="single_object",
                                   must_see="a counter showing 0", focus="0")
    strategy_after = BeatStrategy(ref="v1", concept="incrementing changes the value",
                                  relationship="process", physical_form="single_object",
                                  must_see="the counter's value replaced by 1",
                                  changes_from_previous="the counter's value updates from 0 to 1",
                                  focus="1")
    beats = [Beat(line="A counter starts at 0.", on_screen="Counter: 0", visual_ref="v0"),
             Beat(line="Calling increment sets it to 1.", on_screen="Counter: 1",
                  visual_ref="v1", source_quote="increment sets it to 1")]
    visuals = {"v0": Visual(ref="v0", type="diagram", spec="s0", frame=before, strategy=strategy_before),
              "v1": Visual(ref="v1", type="diagram", spec="s1", frame=after, strategy=strategy_after)}
    unit = _unit(beats, visuals)

    strategy_check = checks.check_frames_match_strategy(unit)
    assert strategy_check.passed, strategy_check.reason
    form_check = checks.check_physical_form_matches_template(unit)
    assert form_check.passed, form_check.reason
    transition_check = checks.check_state_item_transitions_visible(unit)
    assert transition_check.passed, transition_check.reason
    print("   ok — a generic value/state transition (counter 0 -> 1) is "
          "representable with the existing `state` template + Slot.state, "
          "and passes every relevant grader without any topic-specific code")


def test_value_transition_without_a_visible_arrival_is_caught():
    """The same change, but the new value is dropped straight into 'resting'
    instead of marked arriving — the exact defect check_state_item_transitions
    _visible exists to catch, generically."""
    before = Frame(template="state", store=Store(
        slots=[Slot(label="0", role="hero", state="resting")]))
    after_broken = Frame(template="state", store=Store(
        slots=[Slot(label="1", role="hero", state="resting")]))  # teleported
    beats = [Beat(line="A counter starts at 0.", on_screen="Counter: 0", visual_ref="v0"),
             Beat(line="Calling increment sets it to 1.", on_screen="Counter: 1",
                  visual_ref="v1")]
    visuals = {"v0": Visual(ref="v0", type="diagram", spec="s0", frame=before),
              "v1": Visual(ref="v1", type="diagram", spec="s1", frame=after_broken)}
    unit = _unit(beats, visuals)
    result = checks.check_state_item_transitions_visible(unit)
    assert not result.passed
    print(f"   ok — a value that changes with no arrival drawn is caught: {result.reason}")


# ============================================================ 2. parent-child relationship

def test_parent_child_relationship_is_representable():
    """Deliberately NOT props/React: 'a build script calls two other
    scripts, one to compile and one to package'."""
    graph = Graph(root=Node(label="build.sh", role="hero"),
                  branches=[Branch(node=Node(label="compile.sh"), edge_label="calls"),
                           Branch(node=Node(label="package.sh"), edge_label="calls")])
    frame = Frame(template="graph", graph=graph)
    strategy = BeatStrategy(ref="v0", concept="one script depends on two others",
                            relationship="hierarchy", physical_form="flat_parts",
                            must_see="build.sh with arrows to compile.sh and package.sh",
                            focus="build.sh")
    beats = [Beat(line="The build script calls two other scripts.",
                  on_screen="build.sh -> 2 scripts", visual_ref="v0",
                  source_quote="the build script calls two other scripts")]
    visuals = {"v0": Visual(ref="v0", type="diagram", spec="s0", frame=frame, strategy=strategy)}
    unit = _unit(beats, visuals)

    strategy_check = checks.check_frames_match_strategy(unit)
    assert strategy_check.passed, strategy_check.reason
    form_check = checks.check_physical_form_matches_template(unit)
    assert form_check.passed, form_check.reason
    print("   ok — a generic parent-child/depends-on relationship (one root, "
          "two labelled edges) is representable with the existing `graph` "
          "template, no topic-specific code")


# ============================================================ 3. data movement

def test_data_movement_relationship_is_representable():
    """Deliberately NOT props/state: 'a request arrives at a queue and
    waits to be handled'."""
    frame = Frame(template="state", store=Store(
        label="Queue", orientation="horizontal",
        slots=[Slot(label="", role="plain", state="resting"),
              Slot(label="request", role="hero", state="arriving")]))
    strategy = BeatStrategy(ref="v0", concept="a request travels into the queue",
                            relationship="data_movement", physical_form="single_container",
                            must_see="a request entering an empty slot in the queue",
                            focus="request")
    beats = [Beat(line="A new request arrives and joins the queue.",
                  on_screen="Request arrives", visual_ref="v0",
                  source_quote="a new request arrives and joins the queue")]
    visuals = {"v0": Visual(ref="v0", type="diagram", spec="s0", frame=frame, strategy=strategy)}
    unit = _unit(beats, visuals)

    strategy_check = checks.check_frames_match_strategy(unit)
    assert strategy_check.passed, strategy_check.reason
    form_check = checks.check_physical_form_matches_template(unit)
    assert form_check.passed, form_check.reason
    print("   ok — a generic data-movement relationship (a request arriving "
          "into a queue) is representable with the existing `state` "
          "template + Slot.state='arriving', no topic-specific code")


# ============================================================ 4. code-only concept

def test_code_only_concept_is_representable_across_relationships():
    """Deliberately NOT a React snippet: a CSS rule, where the code itself
    IS the concept. Checked against several relationships at once — 'code'
    is legitimately allowed in every row of _RELATIONSHIP_TEMPLATES."""
    for relationship in ("structure", "process", "comparison", "hierarchy", "cause_effect"):
        frame = Frame(template="code",
                     code_lines=[Cell(label=".card { border: 1px solid; }", role="hero")])
        strategy = BeatStrategy(ref="v0", concept="the rule itself is the answer",
                                relationship=relationship, must_see="the CSS rule",
                                focus=".card")
        beats = [Beat(line="The rule sets a border on every card.", on_screen="CSS rule",
                      visual_ref="v0", source_quote="sets a border on every card")]
        visuals = {"v0": Visual(ref="v0", type="diagram", spec="s0", frame=frame, strategy=strategy)}
        unit = _unit(beats, visuals)
        result = checks.check_frames_match_strategy(unit)
        assert result.passed, (relationship, result.reason)
    print("   ok — a code-only concept (the material's own snippet) is "
          "representable regardless of which relationship the beat is "
          "classified as — 'code' is a legitimate picture of nearly any claim")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} mechanism-representation hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL MECHANISM-REPRESENTATION HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
