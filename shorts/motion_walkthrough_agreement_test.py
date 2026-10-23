"""
The walkthrough prompt and the walkthrough checks agree — proven on a script
shaped like the Opus drafts plain_variable_no_rerender__motion's walkthrough
run rejected four times on 2026-10-12 (reel total $0.99), before another
paid attempt. The fixture, evals/fixtures/motion/plain_variable_walkthrough_
script.json, is rebuilt from that run's error text (its drafts were not
saved). The checks that rejected it were wrong, not the script:

  1. motion_hook_curiosity only allowed "How does..." / "What happens
     when...": "Why doesn't your counter change...?" was rejected. Any
     curiosity question opening with why / what / how now passes;
  2. motion_caption_sentences counted the prompt's own chapter card format,
     "Step one. Counter runs.", as two sentences. The step label is not one;
  3. walkthrough_running_example and walkthrough_main_source compared the
     literal 'let count = 0, inside Counter' as one string with no
     code-to-speech mapping. Both now match it part by part, the way the
     caption check matches code against speech;
  4. walkthrough_main_source required every chapter title word, "you" and
     "notices" included, in the main section. Stopwords are ignored, words
     match by stem, and a word fails only when it came from a SUPPORTING
     section.

And the rejected-draft handling (shorts/motion_repair.py): every rejected
draft is saved to output/<id>/rejected/; a saved draft that passes today's
graders is used before the money gate; a mechanical failure is repaired in
code with no paid call.

    SHORTS_STUB=1 python -m shorts.motion_walkthrough_agreement_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import json
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import checks, config, motion_reel, motion_repair, motion_themes
from shorts.parse import find_section, parse_markdown
from shorts.schema import CaptionChunk, MotionScript, MotionScriptDraft, QuestionWorkflow
from shorts.skills import script as script_skill

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "evals/fixtures/motion/plain_variable_walkthrough_script.json"
SECTIONS = parse_markdown(str(ROOT / "content/react_usestate_basics.md"))
SECTION = find_section(SECTIONS, "7.2")
#: The reel's own split (output/plain_variable_no_rerender__motion/setup.json):
#: pool 7.2 + 7.4 is the main material, 7.1 + 7.3 are supporting.
MAIN = "\n\n".join(find_section(SECTIONS, s).text for s in ("7.2", "7.4"))
SUPPORT = "\n\n".join(find_section(SECTIONS, s).text for s in ("7.1", "7.3"))
SID = "plain_variable_no_rerender__motion"
#: A copy of the reel's setup.json (topic, approved workflow, pools).
SETUP = json.loads((ROOT / "evals/fixtures/motion/plain_variable_setup.json").read_text())


def _load() -> MotionScript:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    spec = motion_themes.registry().get(data["theme"])
    data["speakers"] = [sp.model_dump()
                        for sp in motion_themes.cast_speakers(spec, data["language"])]
    return MotionScript(**data)


SCRIPT = _load()


#: The reel's approved teaching approach, whose exclusions the script must respect.
APPROACH = QuestionWorkflow(**SETUP["workflow"]).approved_teaching_approach


def _grade(script: MotionScript) -> list:
    source, main, selected = script_skill._motion_grading_texts(SECTION, MAIN, SUPPORT,
                                                                "walkthrough")
    return checks.run_motion_script_graders(script, source, main_text=main,
                                            selected_text=selected, approach=APPROACH)


def _failed(script: MotionScript) -> dict:
    return {r.name: r.reason for r in _grade(script) if not r.passed}


def _shot(script: MotionScript, sid: str, **update) -> MotionScript:
    shots = [s.model_copy(update=update) if s.id == sid else s for s in script.shots]
    return script.model_copy(update={"shots": shots})


def _captions(*texts: str) -> list[CaptionChunk]:
    return [CaptionChunk(text=t) for t in texts]


# ============================================================ the whole script

def test_the_realistic_walkthrough_passes_every_grader():
    assert APPROACH is not None and APPROACH.primary == "process_demonstration"
    failed = _failed(SCRIPT)
    assert not failed, failed
    assert len(_grade(SCRIPT)) == 22      # + reading level, terms explained (2026-10-12); + video code walk (2026-10-23)


# ===================================================================== 1. hook

def _hook(speech: str, question: str | None = None) -> MotionScript:
    first = speech.split("?")[0] + "?"
    s = _shot(SCRIPT, "s01", speech=speech,
              captions=_captions(*checks._sentences(speech)))
    return s.model_copy(update={"hook_question": question or first})


def test_why_what_and_how_hooks_all_pass():
    for speech in ("Why doesn't your counter change when you change the number? Nothing asks React.",
                   "What happens when you click the button? Nothing asks React to look.",
                   "How does your counter stay stuck at zero? Nothing asks React to look.",
                   "Where does your click actually go? Nothing asks React to look."):
        r = checks.check_motion_hook_curiosity(_hook(speech))
        assert r.passed, (speech, r.reason)


def test_a_hook_that_is_not_a_curiosity_question_still_fails():
    r = checks.check_motion_hook_curiosity(_hook("However you click, it stays. Nothing asks React."))
    assert not r.passed and "curiosity question" in r.reason, r.reason
    r = checks.check_motion_hook_curiosity(_hook("Your counter is stuck at zero. Nothing asks React."))
    assert not r.passed


def test_a_walkthrough_hook_still_needs_its_answer_line():
    r = checks.check_motion_hook_curiosity(
        _hook("Why doesn't your counter change when you change the number?"))
    assert not r.passed and "no answer line" in r.reason, r.reason


def test_the_prompt_offers_the_hooks_the_check_accepts():
    for prompt in (script_skill.SYSTEM_MOTION_WALKTHROUGH,
                   script_skill.SYSTEM_MOTION_WALKTHROUGH_HOOK_FIX):
        for opener in ("Why does...", "How does...", "What happens when..."):
            assert opener in prompt, opener
            assert opener.split()[0].lower() in checks.MOTION_WALKTHROUGH_HOOK_OPENERS


# ========================================================== 2. step label

def test_the_prompt_format_step_label_is_one_sentence():
    """The prompt's chapter_card format, "Step one. <title>.", as ONE caption."""
    assert '"Step one. <the chapter title, short>."' in script_skill.SYSTEM_MOTION_WALKTHROUGH
    r = checks.check_motion_caption_sentences(SCRIPT)
    assert r.passed, r.reason


def test_the_label_as_its_own_caption_still_passes():
    """The golden fixture's form: "Step one." and "Counter runs." apart."""
    s = _shot(SCRIPT, "s04", captions=_captions("Step <b>one</b>.", "Counter runs."))
    assert checks.check_motion_caption_sentences(s).passed
    assert checks.check_motion_captions_match_speech(s).passed


def test_digits_and_colons_are_labels_too():
    for cap, speech in (("Step 1. Counter runs.", "Step one. Counter runs."),
                        ("Step one: Counter runs.", "Step one: Counter runs.")):
        s = _shot(SCRIPT, "s04", speech=speech, captions=_captions(cap))
        r = checks.check_motion_caption_sentences(s)
        assert r.passed, (cap, r.reason)


def test_a_card_with_two_real_sentences_still_fails():
    s = _shot(SCRIPT, "s04", speech="Step one. Counter runs. Then it stops.",
              captions=_captions("Step one. Counter runs. Then it stops."))
    r = checks.check_motion_caption_sentences(s)
    assert not r.passed and "holds 2 sentences" in r.reason, r.reason


def test_the_label_is_only_skipped_on_a_chapter_card():
    s = _shot(SCRIPT, "s05", speech="Step one. React runs Counter from the top.",
              captions=_captions("Step one. React runs Counter from the top."))
    assert not checks.check_motion_caption_sentences(s).passed


# ===================================================== 3. code against speech

def test_the_running_example_is_found_in_the_spoken_example_shot():
    """Speech "let count equals zero" says the example 'let count = 0, inside Counter'."""
    assert checks.check_walkthrough_running_example(SCRIPT).passed
    spoken_only = _shot(SCRIPT, "s03", captions=_captions(
        "Let's follow one counter.", "Inside Counter, you write let count equals zero."))
    assert checks.check_walkthrough_running_example(spoken_only).passed


def test_the_running_example_is_found_in_the_main_section():
    """7.2 says "If `let count = 0` is declared inside `Counter`" — not the
    literal string, but every part of it."""
    assert checks._motion_says(MAIN, "let count = 0, inside Counter")
    r = checks.check_walkthrough_main_source(SCRIPT, MAIN, MAIN + "\n\n" + SUPPORT)
    assert r.passed, r.reason


def test_a_different_example_still_fails_both_checks():
    wrong = SCRIPT.model_copy(update={"running_example": SCRIPT.running_example.model_copy(
        update={"text": "let count = 5, inside Counter"})})
    assert not checks.check_walkthrough_running_example(wrong).passed
    r = checks.check_walkthrough_main_source(wrong, MAIN, MAIN + "\n\n" + SUPPORT)
    assert not r.passed and "running example" in r.reason
    other = SCRIPT.model_copy(update={"running_example": SCRIPT.running_example.model_copy(
        update={"text": "let total = 0, inside Cart"})})
    assert not checks.check_walkthrough_running_example(other).passed


def test_number_words_inside_long_text_match_digits():
    assert checks._motion_text_key("let count equals zero") == \
        checks._motion_text_key("`let count = 0`") == "letcountequals0"


# ========================================================= 4. chapter titles

def _titled(n: int, title: str) -> MotionScript:
    chapters = [c.model_copy(update={"title": title}) if c.n == n else c
                for c in SCRIPT.chapters]
    return SCRIPT.model_copy(update={"chapters": chapters})


def _main_source(script: MotionScript):
    return checks.check_walkthrough_main_source(script, MAIN, MAIN + "\n\n" + SUPPORT)


def test_you_and_word_forms_pass():
    for title in ("You click, count goes up", "Nobody notices the change",
                  "The next render resets it", "React never runs it again"):
        r = _main_source(_titled(2, title))
        assert r.passed, (title, r.reason)


def test_a_step_from_a_supporting_section_still_fails():
    """7.1 (supporting) explains how React compares and patches the JSX; 7.2
    and 7.4 never do. A chapter built on that is borrowed explanation."""
    r = _main_source(_titled(3, "React compares and patches JSX"))
    assert not r.passed, r.reason
    assert "'compares'" in r.reason and "'patches'" in r.reason, r.reason


def test_a_title_with_no_main_section_word_fails():
    r = _main_source(_titled(3, "Nobody notices"))
    assert not r.passed and "none of" in r.reason, r.reason


def test_the_tokenization_golden_still_flags_the_double_hash():
    """E174's case: the double-hash notation is explained only in 1.3."""
    doc = parse_markdown(str(ROOT / "content/tokenization_basics.md"))
    data = json.loads((ROOT / "evals/fixtures/motion/tokenization_golden.json").read_text())
    data["chapters"][3]["title"] = "Read the double hash"
    script = MotionScript(**data)
    main = "\n\n".join(find_section(doc, s).text for s in ("1.1", "1.6"))
    r = checks.check_walkthrough_main_source(script, main, "\n\n".join(s.text for s in doc))
    assert not r.passed and "['double', 'hash']" in r.reason, r.reason


# ============================================ 5. rejected drafts and repairs

def _clear_rejected():
    folder = motion_repair.rejected_dir(SID)
    if folder.exists():
        for f in folder.glob("*.json"):
            f.unlink()


def test_a_rejected_draft_is_saved_with_its_failures():
    _clear_rejected()
    bad = _hook("Your counter is stuck at zero. Nothing asks React.")
    path = motion_repair.save_rejected(bad, _grade(bad))
    assert path.parent == config.OUTPUT_DIR / SID / "rejected"
    data = json.loads(path.read_text())
    assert data["template"] == "walkthrough" and data["theme"] == "step_by_step_walkthrough"
    assert [f["grader"] for f in data["failures"]] == ["motion_hook_curiosity"]
    assert MotionScript(**data["script"]).shots[0].speech.startswith("Your counter")
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")


def test_two_sentences_in_one_caption_are_split_in_code():
    s = _shot(SCRIPT, "s09", captions=_captions(
        "Nothing <b>observes</b> that change. Nothing tells React a <b>re-render</b> is "
        "needed, so the screen still shows zero."))
    results = _grade(s)
    assert motion_repair.is_mechanical(results), [r.name for r in results if not r.passed]
    fixed = motion_repair.try_mechanical(s, results, _grade)
    assert fixed is not None
    assert [c.text for c in fixed[0].shots[8].captions] == [c.text for c in SCRIPT.shots[8].captions]


def test_plain_captions_that_drift_from_speech_are_rebuilt():
    s = _shot(SCRIPT, "s12", captions=_captions(
        "So count went up for a <b>moment</b>.", "The screen stayed at <b>zero</b>."))
    results = _grade(s)
    assert motion_repair.is_mechanical(results)
    fixed = motion_repair.try_mechanical(s, results, _grade)
    assert fixed is not None
    assert [c.text for c in fixed[0].shots[11].captions] == [
        "So count went up for a <b>moment</b>.", "The screen stayed at <b>zero</b> the whole time."]


def test_a_code_caption_is_never_rebuilt():
    """Only the writer knows which code a caption shows."""
    s = _shot(SCRIPT, "s07", captions=_captions(
        "Your click handler runs `count += 1`.", "In memory, <b>count</b> really is one now."))
    results = _grade(s)
    assert motion_repair.repair(s, results) is None


def test_a_real_failure_is_not_mechanical():
    bad = _hook("Your counter is stuck at zero. Nothing asks React.")
    assert not motion_repair.is_mechanical(_grade(bad))
    assert motion_repair.try_mechanical(bad, _grade(bad), _grade) is None


def test_a_mechanical_failure_costs_one_call_not_two():
    """write_motion_script: attempt 1 has a two-sentence caption; it is
    repaired in code and returned without a second ask."""
    _clear_rejected()
    broken = _shot(SCRIPT, "s09", captions=_captions(
        "Nothing <b>observes</b> that change. Nothing tells React a <b>re-render</b> is "
        "needed, so the screen still shows zero."))
    draft = MotionScriptDraft(**{k: getattr(broken, k) for k in (
        "hook_question", "concept_name", "promise", "icon_vocabulary", "takeaways",
        "shots", "chapters", "running_example")})
    calls = []

    def fake_ask(system, user, model, **kw):
        calls.append(kw.get("label"))
        return draft
    real = script_skill.ask_json
    script_skill.ask_json = fake_ask
    try:
        from shorts.schema import Topic
        script, results = script_skill.write_motion_script(
            Topic(**SETUP["topic"]), SECTION, short_id=SID, source_text=MAIN, supporting_text=SUPPORT,
            template="walkthrough", theme="step_by_step_walkthrough", language="react")
    finally:
        script_skill.ask_json = real
    assert calls == ["motion_script"], calls
    assert script is not None and checks.all_passed(results), \
        [r for r in results if not r.passed]
    saved = list(motion_repair.rejected_dir(SID).glob("*_script.json"))
    assert len(saved) == 1, saved


def test_a_saved_draft_that_now_passes_is_used_with_no_call():
    """The case this reel needed: drafts rejected by a grader bug pass once
    the grader is fixed. The script stage uses one before its money gate."""
    _clear_rejected()
    motion_repair.save_rejected(SCRIPT, [checks.GraderResult(
        "motion_hook_curiosity", False, "the old opener list")])
    found = script_skill.reuse_saved_motion_script(
        SECTION, short_id=SID, source_text=MAIN, supporting_text=SUPPORT,
        template="walkthrough", theme="step_by_step_walkthrough")
    assert found is not None
    script, results, path, repaired = found
    assert checks.all_passed(results) and not repaired
    # another template or theme never reuses it
    assert script_skill.reuse_saved_motion_script(
        SECTION, short_id=SID, source_text=MAIN, supporting_text=SUPPORT,
        template="fix_story", theme="under_the_hood") is None


def test_the_script_stage_skips_its_money_gate_for_a_saved_draft():
    _clear_rejected()
    motion_repair.save_rejected(SCRIPT, [])
    state = dict(SETUP)
    choice = motion_reel.MotionThemeChoice(
        theme="step_by_step_walkthrough", reason="test", template="walkthrough",
        language="react", tags=["#react", "#walkthrough"], source="flag",
        fit_check={"passed": True})
    gates, writes = [], []
    real_gate, real_write = motion_reel._money_gate, motion_reel.write_motion_script
    motion_reel._money_gate = lambda *a, **k: gates.append(a) or False
    motion_reel.write_motion_script = lambda *a, **k: writes.append(a) or (None, [])
    try:
        script = motion_reel.stage_script(SID, state, SECTIONS, True, 0, choice)
    finally:
        motion_reel._money_gate, motion_reel.write_motion_script = real_gate, real_write
    assert not gates and not writes
    assert script is not None and script.shots[0].speech == SCRIPT.shots[0].speech
    assert motion_reel.motion_path(SID).exists()
    assert str(motion_reel.motion_path(SID)).startswith(str(config.OUTPUT_DIR))
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} walkthrough agreement tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL WALKTHROUGH AGREEMENT TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
