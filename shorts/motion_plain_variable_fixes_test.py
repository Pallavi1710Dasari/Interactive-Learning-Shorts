"""
Two fixes found in the real reel plain_variable_no_rerender__motion
(2026-10-12), which failed at the script stage:

  - captions: all three Opus scripts failed only motion_captions_match_speech,
      s03: caption word '0`.' does not match the narration at 'equals zero. Your click'
      s08: caption word '0`' does not match the narration at 'equals zero creates it'
    The caption kept real code (`let count = 0`) and the speech said "equals
    zero", which motion_speech_vs_caption asks for. The matcher split the
    caption on spaces, reduced the lone "=" to nothing and skipped it, so the
    narration's "equals" was left unmatched and the failure was reported at
    the next word. Operators now key as the words they are spoken as;
  - template: the reviewer kept walkthrough at the template prompt (Enter on
    the default), setup.json saved template_source "default", the theme step
    treated the template as unpinned and chose under_the_hood, a fix_story
    theme. A template the reviewer saw and kept now pins the theme step.

The run did not save its rejected drafts, so the captions below are rebuilt
from the grader's messages: s03 is the fixture's s03 with the code kept as
code; s08's sentence is the shortest one matching its message.

    SHORTS_STUB=1 python -m shorts.motion_plain_variable_fixes_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import builtins
import json
import sys
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import checks, config, motion_reel, motion_voice
from shorts.schema import CaptionChunk, MotionScript

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = MotionScript(**json.loads(
    (ROOT / "evals/fixtures/motion/what_state_means_script.json").read_text()))


def _with_shot(speech: str, captions: list[str], sid: str = "s03") -> MotionScript:
    """The fixture with one shot's speech and captions replaced."""
    shots = []
    for s in FIXTURE.shots:
        if s.id == sid:
            s = s.model_copy(update={
                "speech": speech, "captions": [CaptionChunk(text=t) for t in captions]})
        shots.append(s)
    return FIXTURE.model_copy(update={"shots": shots})


S03_SPEECH = ("Here's the before. Inside Counter, you write let count equals zero. "
              "Your click handler adds one to count.")
S03_CAPTIONS = ["Here's the <b>before</b>.",
                "Inside <b>Counter</b>, you write `let count = 0`.",
                "Your click handler adds one to <b>count</b>."]
S08_SPEECH = "Each new render runs let count equals zero creates it fresh at zero."
S08_CAPTIONS = ["Each new render runs `let count = 0` creates it fresh at zero."]


def _match(script: MotionScript):
    return checks.check_motion_captions_match_speech(script)


# =================================================================== captions

def test_code_with_an_operator_then_a_full_stop_matches():
    """s03: '0`.' — the code, then the sentence's full stop."""
    r = _match(_with_shot(S03_SPEECH, S03_CAPTIONS))
    assert r.passed, r.reason


def test_code_with_an_operator_mid_sentence_matches():
    """s08: '0`' — the code with nothing after it."""
    r = _match(_with_shot(S08_SPEECH, S08_CAPTIONS, sid="s08"))
    assert r.passed, r.reason


def test_the_same_shots_also_pass_speech_vs_caption():
    """The pair the grader asked for: real code shown, words spoken."""
    for script in (_with_shot(S03_SPEECH, S03_CAPTIONS),
                   _with_shot(S08_SPEECH, S08_CAPTIONS, sid="s08")):
        r = checks.check_motion_speech_vs_caption(script)
        assert r.passed, r.reason


def test_other_trailing_punctuation_matches():
    speech = "Inside Counter, you write let count equals zero."
    for cap in ("Inside Counter, you write `let count = 0`!",
                "Inside Counter, you write `let count = 0`?",
                "Inside Counter, (you write `let count = 0`).",
                "Inside Counter, you write `let count = 0`, see."):
        said = speech[:-1] + ", see." if cap.endswith("see.") else speech
        r = _match(_with_shot(said, [cap]))
        assert r.passed, (cap, r.reason)


def test_the_increment_matches_its_spoken_form():
    """`count = count + 1` <- "count equals count plus one"."""
    r = _match(_with_shot("The handler runs count equals count plus one.",
                          ["The handler runs `count = count + 1`."]))
    assert r.passed, r.reason


def test_operators_without_spaces_match_too():
    r = _match(_with_shot("The handler runs count equals count plus one.",
                          ["The handler runs `count=count+1`."]))
    assert r.passed, r.reason


def test_a_real_mismatch_still_fails():
    """The fix maps operators to words; it does not make the matcher lenient."""
    r = _match(_with_shot("Inside Counter, you write let count equals one.",
                          ["Inside Counter, you write `let count = 0`."]))
    assert not r.passed
    r = _match(_with_shot("Inside Counter, you write let count is zero.",
                          ["Inside Counter, you write `let count = 0`."]))
    assert not r.passed


def test_an_arrow_is_not_read_as_equals():
    """"=>" is left out of the spoken operators; its "=" must not become "equals"."""
    assert checks._motion_key("=>") == ""
    assert checks._motion_key("!==") == ""
    assert checks._motion_key("=") == "equals"


def test_caption_speech_slices_follow_the_matcher():
    """motion_voice.caption_speech (which feeds the voice timing) consumes the
    speech the way the grader does, so the "=" caption gets its "equals"."""
    shot = next(s for s in _with_shot(S03_SPEECH, S03_CAPTIONS).shots if s.id == "s03")
    assert motion_voice.caption_speech(shot) == [
        "Here's the before.",
        "Inside Counter, you write let count equals zero.",
        "Your click handler adds one to count."]


# =================================================================== template

def _gate(answer: str | None, *, yes: bool = False, override: str | None = None,
          tty: bool = True):
    real_input, real_isatty = builtins.input, sys.stdin.isatty
    builtins.input = lambda _prompt="": answer
    sys.stdin.isatty = lambda: tty
    try:
        return motion_reel._decide_template("walkthrough", yes, override)
    finally:
        builtins.input, sys.stdin.isatty = real_input, real_isatty


def test_enter_at_the_template_prompt_pins_the_template():
    """The reel's case: the default was walkthrough and the reviewer pressed Enter."""
    assert _gate("") == ("walkthrough", "reviewer")
    state = {"template": "walkthrough", "template_source": "reviewer"}
    assert motion_reel.template_pin(state) == "walkthrough"


def test_typing_a_template_pins_it():
    assert _gate("walkthrough") == ("walkthrough", "reviewer")
    assert _gate("fix_story") == ("fix_story", "reviewer")


def test_nobody_asked_leaves_it_to_the_theme():
    """--yes and a non-interactive run never showed the prompt: unpinned, as before."""
    assert _gate(None, yes=True) == ("walkthrough", "default")
    assert _gate(None, tty=False) == ("walkthrough", "default")
    assert _gate(None, override="fix_story") == ("fix_story", "flag")


def test_a_pinned_walkthrough_only_offers_walkthrough_themes():
    """With the pin, under_the_hood (a fix_story theme) is not eligible."""
    from shorts import motion_themes
    eligible = motion_themes.eligible_themes(
        approach="process_demonstration", has_code=True, template="walkthrough",
        history=[], language="react")
    assert eligible, "no walkthrough theme is eligible"
    assert "under_the_hood" not in eligible
    reg = motion_themes.registry()
    assert all(reg.get(t).template == "walkthrough" for t in eligible), eligible


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} plain-variable reel fix tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL PLAIN-VARIABLE REEL FIX TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
