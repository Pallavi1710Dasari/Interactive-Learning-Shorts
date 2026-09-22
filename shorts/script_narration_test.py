"""
Offline, deterministic tests for the script-generation NARRATION-QUALITY fix:
Script.full_narration, check_no_stage_directions, and check_narration_sentence_form
(formerly check_qa_sentence_form) now actually running as part of
run_script_graders (it existed but was never wired into SCRIPT_GRADERS before
this fix — see checks.py's own comment).

Also covers the later, bigger change these tests predate: the move from a
scripted interviewer/student DIALOGUE to a single narrator's connected
explanation — see schema.py's Script/Beat docstrings and checks.py's
check_narration_shape. Every beat here is the same narrator; `_beat(opening=...)`
distinguishes beat 0 (the opening, ungrounded by design) from the beats that
follow it (the answer, each grounded in a source_quote) POSITIONALLY, the way
checks.py itself now does, rather than by a second speaker value.

No API key, no network, no LLM call — every test here builds a Script by hand
and runs the deterministic graders directly.

    python -m shorts.script_narration_test
"""
from .schema import Script, Beat
from . import checks


def _beat(opening=False, line="A sentence.", on_screen="label", visual_ref="d_1",
         source_quote=None) -> Beat:
    data = dict(speaker="narrator", line=line, on_screen=on_screen, visual_ref=visual_ref)
    if not opening:
        data["source_quote"] = source_quote or "A sentence."
    return Beat(**data)


def _script(beats: list[Beat], question="What happens here?") -> Script:
    all_beats = [_beat(opening=True, line=question, on_screen="the question",
                       visual_ref="title")] + beats
    return Script(short_id="t_narration", question=question, beats=all_beats)


# --------------------------------------------------------------------------- A
# Script.full_narration

def test_full_narration_joins_beats_in_speaking_order():
    beats = [
        _beat(line="Say the count starts at 0."),
        _beat(line="Calling setCount tells React the state should update."),
        _beat(line="React then re-runs the component with the new value."),
    ]
    script = _script(beats, question="What happens after you call setCount?")
    expected = " ".join(b.line for b in script.beats)
    assert script.full_narration == expected
    # And nothing is lost or reordered relative to the beats themselves.
    for beat in script.beats:
        assert beat.line in script.full_narration
    print("   ok — full_narration is exactly the beats' lines joined in order, "
          "nothing missing and nothing reordered")


def test_full_narration_skips_blank_lines_without_leaving_double_spaces():
    # Built directly (not via _script's helper, which prepends its own
    # opening beat) so the expected string is exact and self-contained.
    script = Script(short_id="t", question="What happens?", beats=[
        _beat(opening=True, line="First sentence."),
        _beat(line="   "),
        _beat(line="Last sentence."),
    ])
    assert script.full_narration == "First sentence. Last sentence."
    print("   ok — a blank beat line does not leave a gap or stray whitespace "
          "in the joined narration")


def test_full_narration_is_not_part_of_the_serialized_payload():
    # Same convention as word_count/estimated_seconds — a plain property, not
    # a computed_field, so the wire format to the API/frontend is unchanged.
    script = _script([_beat(line="One sentence.")])
    dumped = script.model_dump()
    assert "full_narration" not in dumped
    assert "word_count" not in dumped and "estimated_seconds" not in dumped
    print("   ok — full_narration follows the existing word_count/"
          "estimated_seconds convention: computed, not serialized")


# --------------------------------------------------------------------------- B
# check_no_stage_directions (new)

def test_bracketed_direction_is_rejected():
    beats = [
        _beat(line="[cut to the state diagram]"),
        _beat(line="React re-renders the component."),
    ]
    result = checks.check_no_stage_directions(_script(beats))
    assert not result.passed
    assert "beat 1" in result.reason
    print("   ok — a bracketed stage direction in `line` is caught")


def test_beat_number_label_is_rejected():
    beats = [_beat(line="Beat 3: the state setter is called.")]
    result = checks.check_no_stage_directions(_script(beats))
    assert not result.passed
    print("   ok — a 'Beat N:' label opening a line is caught")


def test_camera_direction_is_rejected():
    beats = [_beat(line="Zoom on the counter as it updates.")]
    result = checks.check_no_stage_directions(_script(beats))
    assert not result.passed
    print("   ok — a camera-direction opener ('Zoom on...') is caught")


def test_screen_label_is_rejected():
    beats = [_beat(line="On screen: count goes from 0 to 1.")]
    result = checks.check_no_stage_directions(_script(beats))
    assert not result.passed
    print("   ok — an 'On screen:' label opening a line is caught")


def test_natural_narration_is_not_flagged():
    beats = [
        _beat(line="Say the count starts at 0."),
        _beat(line="Calling setCount doesn't change that number directly "
                  "— it tells React the state should update."),
        _beat(line="React then re-runs the component to work out what the "
                  "screen should look like now."),
        _beat(line="So it's that re-render, not the setCount call itself, "
                  "that puts count: 1 on the screen."),
    ]
    result = checks.check_no_stage_directions(_script(beats))
    assert result.passed, result.reason
    print("   ok — natural, connected narration (including mid-sentence "
          "colons and numbers) is never flagged")


def test_word_that_merely_contains_a_flagged_term_is_not_flagged():
    # NARROW MATCHING, ON PURPOSE. "cut" and "scene" as ordinary English words
    # mid-sentence must not trip this — only the specific opening shapes of a
    # real stage direction.
    beats = [_beat(line="The budget cut forced a smaller cache, which changed "
                       "the scene entirely for later lookups.")]
    result = checks.check_no_stage_directions(_script(beats))
    assert result.passed, result.reason
    print("   ok — ordinary prose containing 'cut'/'scene' as plain words is "
          "not mistaken for a stage direction")


def test_opening_beat_is_also_checked():
    beats = [_beat(line="React re-renders the component.")]
    script = _script(beats, question="[hook: dramatic pause] What happens?")
    result = checks.check_no_stage_directions(script)
    assert not result.passed
    print("   ok — the opening beat's own line is checked too, not just the "
          "beats after it")


# --------------------------------------------------------------------------- C
# check_narration_sentence_form — now actually wired into SCRIPT_GRADERS

def test_narration_sentence_form_is_now_part_of_run_script_graders():
    beats = [_beat(line="This line trails off with no punctuation")]
    script = _script(beats)
    results = checks.run_script_graders(script)
    names = [r.name for r in results]
    assert "narration_sentence_form" in names, names
    result = next(r for r in results if r.name == "narration_sentence_form")
    assert not result.passed
    print("   ok — check_narration_sentence_form is now part of "
          "run_script_graders' output (it existed but was never wired into "
          "SCRIPT_GRADERS before this fix)")


def test_no_stage_directions_is_also_part_of_run_script_graders():
    beats = [_beat(line="[cut to diagram]")]
    script = _script(beats)
    results = checks.run_script_graders(script)
    names = [r.name for r in results]
    assert "no_stage_directions" in names, names
    print("   ok — check_no_stage_directions runs as part of the real "
          "script-generation retry gate, not only as a standalone function")


# --------------------------------------------------------------------------- D
# Downstream compatibility — timing/TTS/reel generation still see the same
# beat list, unaffected by this fix.

def test_word_count_and_timing_unaffected_by_full_narration():
    beats = [_beat(line="Say the count starts at zero today.")]
    script = _script(beats)
    assert script.word_count == sum(len(b.line.split()) for b in script.beats)
    assert script.estimated_seconds == round(script.word_count / 150 * 60, 1)
    print("   ok — word_count/estimated_seconds (what timing/TTS read) are "
          "unchanged by adding full_narration")


def test_beat_count_and_speaker_unchanged():
    # The pipeline downstream of script-writing (voice.py, video.py, feed.py)
    # iterates script.beats directly and still assumes beat 0 is the opening —
    # nothing about this fix touches that shape. What HAS changed (see
    # schema.py's Script/Beat docstrings) is that every beat, including beat 0,
    # now carries the SAME speaker: there is one narrator, not two roles.
    beats = [_beat(line=f"Sentence number {i}.") for i in range(3)]
    script = _script(beats)
    assert len(script.beats) == 4   # opening + 3 answer beats
    assert script.beats[0] is script.opening_beat
    assert script.beats[1:] == script.body_beats
    assert all(b.speaker == "narrator" for b in script.beats)
    print("   ok — beat count and order are unchanged, and every beat "
          "(opening included) is now the same narrator — nothing downstream "
          "(voice/video/feed) sees a different shape")


def test_existing_narration_shape_and_repetition_graders_still_run_and_pass_a_good_script():
    # A GOOD script — well-formed, connected, no stage directions — must
    # still pass every pre-existing grader as well as the two newly wired in.
    beats = [
        _beat(line="Say the count starts at 0.",
             source_quote="the count starts at 0"),
        _beat(line="Calling setCount tells React the state should update, "
                  "not the variable directly.",
             source_quote="setCount tells React the state should update"),
        _beat(line="React then re-runs the component with the new value.",
             source_quote="React re-runs the component"),
        _beat(line="So that re-render is what puts count: 1 on the screen.",
             source_quote="that re-render puts the new value on the screen"),
    ]
    script = _script(beats, question="What happens after you call setCount?")
    results = checks.run_script_graders(script)
    by_name = {r.name: r for r in results}
    assert by_name["narration_shape"].passed, by_name["narration_shape"].reason
    assert by_name["no_repetition"].passed, by_name["no_repetition"].reason
    assert by_name["narration_sentence_form"].passed, by_name["narration_sentence_form"].reason
    assert by_name["no_stage_directions"].passed, by_name["no_stage_directions"].reason
    print("   ok — a well-formed, connected script passes every grader, old "
          "and newly-wired-in alike")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} script-narration tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL SCRIPT NARRATION TESTS PASSED.")


if __name__ == "__main__":
    main()
