"""
Offline, deterministic tests for TeachingStage (schema.py: TeachingStage,
TeachingStep.stage, Beat.relates_to_step).

No API key, no network. These check that the new fields serialize, default,
and reject bad input the way their docstrings claim — not that any script or
visual step reads them yet, since none does (Step 3 is schema/prompt only;
the stage-aware validators are a later step).

    python -m shorts.teaching_stage_test
"""
import json
from pydantic import ValidationError

from .schema import (
    TeachingStage, TeachingStep, Beat, Script, SectionUnderstanding,
)


def _step(**overrides) -> TeachingStep:
    data = dict(concept="a stack only allows access at one end",
                purpose="establishes the container before anything moves",
                explanation_goal="learner knows which end is reachable")
    data.update(overrides)
    return TeachingStep(**data)


# --------------------------------------------------------------- five stages

def test_all_five_stages_are_accepted():
    for stage in ("hook", "concept", "mechanism", "example", "result"):
        step = _step(stage=stage)
        assert step.stage == stage, (stage, step.stage)
    print("   ok — hook, concept, mechanism, example and result all construct a valid TeachingStep")


def test_no_sixth_stage_exists():
    import typing
    values = typing.get_args(TeachingStage)
    assert set(values) == {"hook", "concept", "mechanism", "example", "result"}, values
    assert len(values) == 5, values
    print("   ok — TeachingStage has exactly the five specified values, no summary/transition/definition extra")


def test_invalid_stage_value_is_rejected():
    for bad in ("summary", "transition", "definition", "intro", "", "CONCEPT"):
        try:
            _step(stage=bad)
        except ValidationError:
            continue
        raise AssertionError(f"stage={bad!r} should have been rejected but was accepted")
    print("   ok — an invented stage (summary/transition/definition/intro/blank/wrong-case) is rejected")


def test_stage_is_optional_and_defaults_to_none():
    step = _step()
    assert step.stage is None
    print("   ok — a TeachingStep with no stage still constructs (backward compatible with pre-Step-3 data)")


# ------------------------------------------------------- serialization round-trip

def test_stage_round_trips_through_json():
    for stage in ("hook", "concept", "mechanism", "example", "result", None):
        step = _step(stage=stage)
        restored = TeachingStep(**json.loads(step.model_dump_json()))
        assert restored.stage == stage, (stage, restored.stage)
    print("   ok — stage (each of the five values, and None) survives a model_dump_json -> reload round trip")


def test_stage_round_trips_inside_section_understanding():
    understanding = SectionUnderstanding(
        section_id="1.1",
        core_idea="a stack is LIFO",
        teaching_sequence=[
            _step(concept="what a stack is", stage="concept"),
            _step(concept="how push and pop work", stage="mechanism"),
            _step(concept="a worked push/pop trace", stage="example"),
            _step(concept="why the last one out is the first added", stage="result"),
        ],
    )
    restored = SectionUnderstanding(**json.loads(understanding.model_dump_json()))
    assert [s.stage for s in restored.teaching_sequence] == [
        "concept", "mechanism", "example", "result"]
    print("   ok — a full 4-step teaching_sequence (one of each non-hook stage) round-trips through JSON in order")


def test_old_teaching_sequence_json_without_stage_still_loads():
    # A teaching_sequence written before this field existed — no "stage" key at all.
    old_json = {
        "section_id": "1.1", "core_idea": "x",
        "teaching_sequence": [
            {"concept": "c", "purpose": "p", "explanation_goal": "g"},
        ],
    }
    understanding = SectionUnderstanding(**old_json)
    assert understanding.teaching_sequence[0].stage is None
    print("   ok — a teaching_sequence step written before `stage` existed still loads, with stage=None")


# --------------------------------------------------- Beat.relates_to_step

def test_beat_can_reference_a_teaching_step():
    beat = Beat(line="Popping removes the item at the top.", on_screen="Pop",
                visual_ref="v2", source_quote="Popping removes the item at the top.",
                relates_to_step=2)
    assert beat.relates_to_step == 2
    print("   ok — a beat can carry relates_to_step, an int pointing at a teaching_sequence step")


def test_beat_relates_to_step_is_optional_and_defaults_to_none():
    beat = Beat(line="A stack only allows access at one end.", on_screen="Stack",
                visual_ref="v1")
    assert beat.relates_to_step is None
    print("   ok — a beat with no relates_to_step still constructs (the hook beat normally leaves it unset)")


def test_relates_to_step_round_trips_through_script_json():
    script = Script(short_id="t1", question="why a stack is LIFO", beats=[
        Beat(line="A stack only allows access at one end.", on_screen="Stack",
             visual_ref="v1"),
        Beat(line="Pushing adds an item to the top.", on_screen="Push", visual_ref="v2",
             source_quote="Pushing adds an item to the top.", relates_to_step=1),
        Beat(line="Popping removes the most recent item.", on_screen="Pop", visual_ref="v3",
             source_quote="Popping removes the most recent item.", relates_to_step=2),
    ])
    restored = Script(**json.loads(script.model_dump_json()))
    assert restored.beats[0].relates_to_step is None
    assert restored.beats[1].relates_to_step == 1
    assert restored.beats[2].relates_to_step == 2
    print("   ok — relates_to_step survives a full Script model_dump_json -> reload round trip, "
          "unset on the hook and set on the beats that reference a step")


def test_beat_stage_is_not_a_field_stage_must_be_resolved_through_the_step():
    beat = Beat(line="x", on_screen="x", visual_ref="v1", relates_to_step=1)
    assert not hasattr(beat, "stage")
    assert "stage" not in Beat.model_fields
    print("   ok — Beat has no `stage` field of its own; a beat's stage is only ever "
          "resolvable by looking up relates_to_step in teaching_sequence, never duplicated")


def test_resolving_a_beats_stage_through_its_teaching_step():
    """The intended read pattern for a later step: Beat.relates_to_step indexes
    (1-based) into SectionUnderstanding.teaching_sequence to find the Beat's stage."""
    understanding = SectionUnderstanding(
        section_id="1.1", core_idea="idea",
        teaching_sequence=[
            _step(concept="what a stack is", stage="concept"),
            _step(concept="push and pop", stage="mechanism"),
        ],
    )
    beat = Beat(line="Pushing adds an item to the top.", on_screen="Push", visual_ref="v2",
               source_quote="Pushing adds an item to the top.", relates_to_step=2)
    resolved_stage = understanding.teaching_sequence[beat.relates_to_step - 1].stage
    assert resolved_stage == "mechanism"
    print("   ok — a beat's stage resolves correctly via relates_to_step -> teaching_sequence[i-1].stage")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} teaching-stage tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL TEACHING STAGE TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
