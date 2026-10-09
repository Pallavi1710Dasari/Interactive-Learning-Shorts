"""
RESTYLE_TO_MOTION_REELS.md phase 2b: themes and tags (and, since the phase 3
badge change, the language identities that replaced the avatars).

Covers the theme and identity registries (and that a new theme is a registry
entry, not a code change), the fit check, the variety rule, the one retry and
the classic_explainer fallback, --theme, tags, language detection, the
theme-aware prompts and graders, and the runner's theme stage — including stub
reels in five different themes. The graders are also covered case by case in
evals/cases.yaml (E175 onward).

No API key, no network, no real LLM calls. Every run writes to a temp folder,
never output/ or assets/.

    SHORTS_STUB=1 python -m shorts.motion_theme_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path

from shorts.testing import isolate_output
isolate_output()   # a temp output/, never the real one

import yaml

from shorts import checks, config, motion_reel, motion_themes as mt, usage
from shorts.parse import find_section, parse_markdown
from shorts.schema import (MotionScript, MotionTags, MotionThemeDraft, TeachingApproach,
                           Topic)
from shorts.skills import script as script_mod
from shorts.skills import theme as theme_mod

ROOT = Path(__file__).resolve().parent.parent
REACT_DOC = ROOT / "content" / "react_usestate_basics.md"
TOKEN_DOC = ROOT / "content" / "tokenization_basics.md"
PAGING_DOC = ROOT / "content" / "session_18_paging.md"
FIXTURES = ROOT / "evals" / "fixtures" / "motion"
THEMED = {"interview": "usestate_interview_golden.json",
          "peer_discussion": "usestate_peer_discussion_golden.json",
          "bug_hunt": "usestate_bug_hunt_golden.json"}
EXPECTED_THEMES = [
    "classic_explainer", "narrative", "interview", "interview_rapid_fire", "peer_discussion",
    "mentor_student", "bug_hunt", "myth_vs_fact", "common_mistakes", "predict_the_output",
    "under_the_hood", "step_by_step_walkthrough", "real_world_scenario", "before_vs_after"]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _react():
    sections = parse_markdown(REACT_DOC)
    return sections, find_section(sections, "7.2")


def _registry_data() -> dict:
    return yaml.safe_load(mt.THEMES_PATH.read_text(encoding="utf-8"))


@contextlib.contextmanager
def _temp_output():
    real = config.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as d:
        config.OUTPUT_DIR = Path(d)
        try:
            yield Path(d)
        finally:
            config.OUTPUT_DIR = real


@contextlib.contextmanager
def _fake_theme_calls(answers: list):
    calls: list[str] = []
    real = theme_mod.ask_json

    def fake(system, user, model_cls, **kw):
        assert model_cls is MotionThemeDraft
        calls.append(user)
        return answers.pop(0)
    theme_mod.ask_json = fake
    try:
        yield calls
    finally:
        theme_mod.ask_json = real


def _run_runner(*args: str, doc: Path = REACT_DOC) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = motion_reel.main([str(doc), *args])
    return code, buf.getvalue()


def _expect_value_error(fn, needle: str):
    try:
        fn()
    except ValueError as e:
        assert needle in str(e), str(e)
        return str(e)
    raise AssertionError(f"expected a ValueError containing {needle!r}")


# ================================================================== registry

def test_registry_has_the_fourteen_themes():
    reg = mt.registry()
    assert reg.ids() == EXPECTED_THEMES, reg.ids()
    for t in reg.themes.values():
        assert t.description and t.suits and t.hook.brief, t.id
        assert 1 <= len(t.speakers) <= 2
    assert reg.fallback == {"fix_story": "classic_explainer",
                            "walkthrough": "step_by_step_walkthrough"}
    two = [t.id for t in reg.themes.values() if t.two_speaker]
    assert two == ["interview", "interview_rapid_fire", "peer_discussion", "mentor_student"]


def test_walkthrough_is_one_theme_not_a_copy():
    """The existing walkthrough template became step_by_step_walkthrough and
    uses the template's own beats and prompt — nothing duplicated."""
    reg = mt.registry()
    walk = [t for t in reg.themes.values() if t.template == "walkthrough"]
    assert [t.id for t in walk] == ["step_by_step_walkthrough"]
    assert walk[0].beats == "walkthrough" and walk[0].base
    system, hook_fix = script_mod.motion_system_for("walkthrough", walk[0])
    assert system is script_mod.SYSTEM_MOTION_WALKTHROUGH
    assert hook_fix is script_mod.SYSTEM_MOTION_WALKTHROUGH_HOOK_FIX
    assert reg.themes["classic_explainer"].beats == "fix_story"


def test_beat_templates_cover_the_eleven_beat_contract():
    from shorts.schema import MOTION_BEAT_ORDER
    for t in mt.registry().themes.values():
        if not t.base:
            assert list(t.beats) == list(MOTION_BEAT_ORDER), t.id


def test_registry_refuses_a_broken_entry():
    def broken(theme_id: str, **change) -> str:
        data = _registry_data()
        data["themes"][theme_id].update(change)
        try:
            mt.parse_theme_registry(data)
        except ValueError as e:
            return str(e)
        raise AssertionError(f"accepted {change}")

    beats = copy.deepcopy(_registry_data()["themes"]["narrative"]["beats"])
    del beats["payoff"]
    assert "missing ['payoff']" in broken("narrative", beats=beats)
    assert "is not one of" in broken("narrative", template="listicle")
    assert "lowercase letters and digits" in broken("narrative", tag="Story Time")
    assert "is not a teaching approach" in broken("narrative", works_with=["vibes"])
    assert "hook style" in broken("narrative", hook={"style": "shout", "openers": ["hey"]})
    iv = copy.deepcopy(_registry_data()["themes"]["interview"]["beats"])
    iv["title"]["speakers"] = ["HOST"]
    assert "unknown speaker(s) ['HOST']" in broken("interview", beats=iv)
    assert "a two-speaker theme needs its own beat template" in broken("interview",
                                                                      beats="fix_story")


def test_a_new_theme_is_only_a_registry_entry():
    """A registry with one extra theme: it is offered, chosen, prompted and
    graded with no code change."""
    data = _registry_data()
    data["themes"]["quiz_show"] = {
        **copy.deepcopy(data["themes"]["myth_vs_fact"]),
        "tag": "quiz", "description": "A quiz host asks, then answers.",
        "hook": {"style": "question", "openers": ["quiz time", "pop quiz"], "symptom": False,
                 "brief": "A quiz question."},
    }
    reg = mt.parse_theme_registry(data)
    with mt.use_registry(reg):
        assert "quiz_show" in mt.eligible_themes(approach="code", has_code=True, template=None,
                                                 history=[], language="react")
        system, hook_fix = script_mod.motion_system_for("fix_story", reg.themes["quiz_show"])
        assert "FORMAT — THEME: quiz_show" in system and "Pop quiz..." in system
        assert "quiz_show format" in hook_fix
        assert mt.tag_problems(["#react", "#quiz", "#state"]) == []
        data = _fixture("usestate_golden.json")
        data["theme"] = "quiz_show"
        r = checks.check_motion_hook_curiosity(MotionScript(**data))
        assert not r.passed and "quiz_show hook" in r.reason, r.reason


# ================================================================ identities

def test_every_language_has_an_identity():
    from shorts import motion_identities as mi
    reg = mi.registry()
    assert mt.language_tags() == list(reg.languages)
    assert len({reg.voices[k] for k in ("narrator", "host", "character_1", "character_2")}) == 4
    for k, ident in [("host", reg.host), *reg.languages.items()]:
        on_dark, on_light = ident.tones
        for f in mi.DARK_FIELDS:
            assert mi.contrast(on_dark, mi.FIELDS[f]) >= 3, (k, f)
        for f in mi.LIGHT_FIELDS:
            assert mi.contrast(on_light, mi.FIELDS[f]) >= 3, (k, f)
        for c in (ident.colour, on_dark, on_light):
            assert min(mi.distance(c, r) for r in mi.RESERVED.values()) >= mi.RESERVED_DISTANCE, (k, c)
        if k != "host":
            assert ident.file and ident.voice in mi.VOICE_KEYS, k


def test_the_identity_registry_refuses_bad_entries():
    import yaml
    from shorts import motion_identities as mi
    def broken(change: dict, lang: str = "python") -> str:
        data = yaml.safe_load(mi.PATH.read_text(encoding="utf-8"))
        data["languages"][lang].update(change)
        try:
            mi.parse(data)
        except ValueError as e:
            return str(e)
        raise AssertionError(f"accepted {change}")
    assert "too close to coral" in broken({"colour": "#F0585C"})
    assert "too close to mint" in broken({"colour": "#19B07D"})
    assert "outside the 100 x 100 grid" in broken({"symbol": [{"rect": [80, 80, 40, 40]}]})
    assert "drawn as a stroke" in broken({"symbol": [{"path": "M10 10 L90 90"}]})
    assert "is not one of" in broken({"voice": "character_9"})


def test_only_two_speaker_themes_cast_speakers():
    reg = mt.registry()
    cast = mt.cast_speakers(reg.themes["interview"], "python")
    assert [(s.role, s.identity, s.label, s.voice_slot) for s in cast] == [
        ("INTERVIEWER", "host", "Interviewer", "motion_host"),
        ("CANDIDATE", "python", "Candidate", "motion_char_1")]
    assert mt.cast_speakers(reg.themes["interview"], "java")[1].voice_slot == "motion_char_2"
    assert mt.cast_speakers(reg.themes["bug_hunt"], "python") == []
    assert mt.cast_speakers(reg.themes["classic_explainer"], "python") == []


# ================================================================ fit, variety

def test_fit_check_rejects_missing_code_and_incompatible_approaches():
    p = mt.theme_problems("predict_the_output", approach="code", has_code=False)
    assert p and p[0].startswith("requirement:") and "needs code" in p[0]
    p = mt.theme_problems("bug_hunt", approach="analogy", has_code=True)
    assert p == ["incompatible: bug_hunt does not work with the analogy teaching approach"]
    p = mt.theme_problems("interview", approach="code", has_code=True, template="walkthrough")
    assert p and p[0].startswith("template:")
    assert mt.theme_problems("nonsense", approach=None, has_code=True)[0].startswith("unknown:")
    assert mt.theme_problems("bug_hunt", approach="code", has_code=True) == []


def test_section_code_detection():
    sections, section = _react()
    assert mt.section_has_code(section.text)                    # `let count = 0`
    tok = parse_markdown(TOKEN_DOC)
    assert not mt.section_has_code(find_section(tok, "1.1").text)   # `[CLS]` is not code


def test_variety_rule():
    assert mt.variety_problems("interview", []) == []
    assert "previous reel" in mt.variety_problems("interview", ["narrative", "interview"])[0]
    # Window of 5 with the new reel: two earlier interviews in the last four -> 3.
    p = mt.variety_problems("interview", ["interview", "narrative", "interview", "bug_hunt"])
    assert p == ["variety: interview would be 3 of the last 5 reels, max 2"], p
    assert mt.variety_problems("interview", ["interview", "narrative", "bug_hunt", "myth_vs_fact"]) == []
    # The fifth reel back has left the window.
    assert mt.variety_problems("interview",
                               ["interview", "interview", "narrative", "bug_hunt", "myth_vs_fact"]) == []


def test_history_reads_tags_json_in_the_same_language():
    with _temp_output() as out:
        def put(short_id, language, theme, when):
            (out / short_id).mkdir()
            (out / short_id / "tags.json").write_text(MotionTags(
                short_id=short_id, language=language, theme=theme, concepts=["x"],
                tags=[f"#{language}", "#x", "#x"], created_at=when).model_dump_json())
        put("b", "react", "narrative", "2026-10-02T00:00:00+00:00")
        put("a", "react", "interview", "2026-10-01T00:00:00+00:00")
        put("c", "python", "bug_hunt", "2026-10-03T00:00:00+00:00")
        (out / "d").mkdir()
        (out / "d" / "tags.json").write_text("not json")
        hist = mt.reel_history(out, "react")
        assert [h.theme for h in hist] == ["interview", "narrative"]
        assert [h.theme for h in mt.reel_history(out, "react", exclude_id="b")] == ["interview"]


# ================================================================== choosing

def _choose(answers=None, **kw):
    sections, section = _react()
    args = dict(source_text=section.text, approach=TeachingApproach(primary="code"),
                language="react", history=[], log=lambda *_: None)
    args.update(kw)
    if answers is None:
        return theme_mod.choose_theme(section, **args), []
    with _fake_theme_calls(answers) as calls:
        return theme_mod.choose_theme(section, **args), calls


def test_the_llm_judges_fit_among_eligible_themes_only():
    choice, calls = _choose([MotionThemeDraft(theme="interview", reason="crisp Q&A",
                                              concept_tags=["Plain variable", "re-render",
                                                            "useState"])],
                            history=["bug_hunt"], headings=_react_headings("7.2")[0])
    assert choice.theme == "interview" and choice.source == "llm"
    assert choice.fit_check.passed and choice.fit_check.attempts == 1
    # Neither "plain variable", "re-render" nor useState is a heading term or
    # defined term of 7.2, so all three are dropped and the section's own
    # candidates stand in.
    assert choice.tags == ["#react", "#interview", "#state", "#variable"], choice.tags
    assert "CONCEPT TERMS (headings and defined terms): state, components, variable" in calls[0]
    assert "bug_hunt" not in choice.eligible            # variety, before the call
    assert "- bug_hunt [" not in calls[0] and "- interview [" in calls[0]
    assert "APPROVED TEACHING APPROACH: code" in calls[0]
    assert "EARLIER REELS IN THIS LANGUAGE (oldest first): bug_hunt" in calls[0]


def test_a_rejected_pick_gets_one_retry_with_the_reason():
    choice, calls = _choose([MotionThemeDraft(theme="bug_hunt", reason="r"),
                             MotionThemeDraft(theme="narrative", reason="a story")],
                            history=["bug_hunt"])
    assert choice.theme == "narrative" and choice.fit_check.attempts == 2
    [rej] = choice.fit_check.rejected
    assert rej.theme == "bug_hunt" and "previous reel" in rej.problems[0]
    assert "YOUR PREVIOUS PICK 'bug_hunt' WAS REJECTED" in calls[1]


def test_two_rejected_picks_fall_back_to_classic_explainer_and_log_why():
    logged: list[str] = []
    choice, calls = _choose([MotionThemeDraft(theme="predict_the_output"),
                             MotionThemeDraft(theme="made_up")],
                            approach=TeachingApproach(primary="analogy"), log=logged.append)
    assert len(calls) == 2
    assert choice.theme == "classic_explainer" and choice.source == "fallback"
    fit = choice.fit_check
    assert fit.fallback and not fit.passed and len(fit.rejected) == 2
    assert "incompatible" in fit.rejected[0].problems[0]
    assert "unknown" in fit.rejected[1].problems[0]
    assert any("falling back to classic_explainer" in line for line in logged), logged


def test_a_pinned_walkthrough_falls_back_to_the_walkthrough():
    choice, calls = _choose(template_pin="walkthrough", history=["step_by_step_walkthrough"])
    assert calls == []                                   # nothing eligible: no call
    assert choice.theme == "step_by_step_walkthrough" and choice.source == "fallback"
    assert choice.fit_check.overrides and "previous reel" in choice.fit_check.overrides[0]


def test_one_eligible_theme_needs_no_call():
    choice, calls = _choose(template_pin="walkthrough")
    assert calls == [] and choice.source == "only_candidate"
    assert choice.theme == "step_by_step_walkthrough" and choice.template == "walkthrough"


def test_theme_flag_overrides_variety_but_not_requirements():
    choice, _ = _choose(override="interview", history=["interview"])
    assert choice.theme == "interview" and choice.source == "flag"
    assert "relaxed by --theme" in choice.fit_check.overrides[0]
    _expect_value_error(lambda: _choose(override="bug_hunt",
                                        approach=TeachingApproach(primary="analogy")),
                        "incompatible")
    tok = parse_markdown(TOKEN_DOC)
    _expect_value_error(lambda: theme_mod.choose_theme(
        find_section(tok, "1.1"), source_text=find_section(tok, "1.1").text,
        approach=None, language="cs", history=[], override="predict_the_output"),
        "needs code")


# ====================================================================== tags

def _react_headings(section_id: str):
    sections = parse_markdown(REACT_DOC)
    section = find_section(sections, section_id)
    return mt.reel_headings(REACT_DOC.read_text(encoding="utf-8"), [section.title]), section


def test_tag_format():
    ok = checks.check_motion_tags(["#react", "#interview", "#state", "#variable"])
    assert ok.passed, ok.reason
    for tags, needle in (
        (["#React", "#interview", "#state"], "lowercase"),
        (["#react", "#inter view", "#state"], "no spaces"),
        (["#interview", "#react", "#state"], "language tag, first"),
        (["#react", "#state"], "2 tags"),
        (["#react", "#podcast", "#state"], "theme tag"),
        (["#react", "#interview", "#a", "#b", "#c", "#d"], "6 tags"),
        (["#react", "#interview", "#python"], "exactly one language tag"),
        (["#react", "#story", "#state"], "theme tag"),          # renamed to #narrative
    ):
        r = checks.check_motion_tags(tags)
        assert not r.passed and needle in r.reason, (tags, r.reason)


def test_concept_tags_are_searchable_concepts():
    """Phase 2b review: concept tags come from headings and defined terms;
    a code identifier or a stray word is rejected."""
    headings, section = _react_headings("7.2")
    ok = checks.check_motion_tag_concepts(["#react", "#interview", "#state", "#variable"],
                                          headings, section.text)
    assert ok.passed, ok.reason
    for tag, needle in (("#count", "code identifier"), ("#counter", "code identifier"),
                        ("#screen", "stray word"), ("#different", "stray word"),
                        ("#closures", "stray word")):
        r = checks.check_motion_tag_concepts(["#react", "#interview", tag], headings,
                                             section.text)
        assert not r.passed and needle in r.reason, (tag, r.reason)
    # An identifier a HEADING names is a concept: useState in 7.3's title.
    headings, section = _react_headings("7.3")
    r = checks.check_motion_tag_concepts(["#react", "#interview", "#usestate"], headings,
                                         section.text)
    assert r.passed, r.reason
    r = checks.check_motion_tag_concepts(["#react", "#interview", "#setcount"], headings,
                                         section.text)
    assert not r.passed and "code identifier" in r.reason, r.reason
    # Defined terms count: "called its vocabulary".
    tok = parse_markdown(TOKEN_DOC)
    s13 = find_section(tok, "1.3")
    h = mt.reel_headings(TOKEN_DOC.read_text(encoding="utf-8"), [s13.title])
    assert mt.concept_vocabulary(h, s13.text).get("vocabulary") == "defined term" or \
        "vocabulary" in mt.concept_vocabulary(h, s13.text)


def test_concept_tags_are_taken_from_headings_and_defined_terms():
    headings, section = _react_headings("7.2")
    exclude = set(mt.language_tags()) | set(mt.registry().tags().values())
    kept, dropped = mt.clean_concept_tags(["State", "variable", "setCount", "react", "#count",
                                           "state"], headings, section.text, exclude)
    assert kept == ["state", "variable"], kept
    assert any("'#count'" in d and "code identifier" in d for d in dropped), dropped
    assert any("setCount" in d and "stray word" in d for d in dropped), dropped   # not in 7.2 at all
    assert any("'react'" in d and "language or theme" in d for d in dropped), dropped
    assert any("repeated" in d for d in dropped), dropped
    assert mt.candidate_concept_tags(headings, section.text, exclude) == ["state", "variable"]
    paging = PAGING_DOC.read_text(encoding="utf-8")
    sec = find_section(parse_markdown(PAGING_DOC), "3.2")
    cands = mt.candidate_concept_tags(mt.reel_headings(paging, [sec.title]), sec.text, exclude)
    assert cands[:2] == ["addresstranslation", "pagetable"], cands
    assert mt.doc_title("# Session 18: Paging and Virtual Memory\n") == "Paging and Virtual Memory"


def test_language_detection():
    react = REACT_DOC.read_text(encoding="utf-8")
    assert mt.detect_language("", react)[0] == "react"
    assert mt.detect_language("```python\nx = 1\n```", "")[0] == "python"
    assert mt.detect_language("", "# Session 19: CSS Specificity\n\nrules")[0] == "css"
    assert mt.detect_language("", PAGING_DOC.read_text(encoding="utf-8"))[0] == "os"
    assert mt.detect_language("", TOKEN_DOC.read_text(encoding="utf-8"))[0] == "cs"
    assert mt.detect_language("", "# Django views\n\n```python\ndef v(r): pass\n```")[0] == "django"
    assert mt.detect_language("", "# Routing in Express\n\n```js\napp.get(h)\n```")[0] == "node"
    assert mt.detect_language("```dockerfile\nFROM python\n```", "")[0] == "docker"
    assert mt.detect_language("", "# Lists\n\n```python\nx = [1]\n```")[0] == "python"


# =================================================== prompts and script graders

def test_base_themes_keep_the_original_prompts():
    system, hook_fix = script_mod.motion_system_for("fix_story", None)
    same, same_fix = script_mod.motion_system_for("fix_story", mt.registry().themes["classic_explainer"])
    assert system == same and hook_fix is same_fix is script_mod.SYSTEM_MOTION_HOOK_FIX
    assert "__ICONS__" not in system and "Never a dialogue" in system


def test_a_themed_prompt_swaps_only_format_and_beats():
    base, _ = script_mod.motion_system_for("fix_story", None)
    system, hook_fix = script_mod.motion_system_for("fix_story", mt.registry().themes["interview"])
    assert "FORMAT — THEME: interview" in system and "Never a dialogue" not in system
    assert "[INTERVIEWER then CANDIDATE]" in system
    assert '"speaker": "INTERVIEWER"' in system and '"speaker": "INTERVIEWER"' in hook_fix
    for rule in ("LENGTH", "WORDS", "SPEECH AND CAPTIONS ARE SEPARATE FIELDS", "CODE",
                 "VISUAL", "ICONS"):
        assert rule in system, rule
    # Every reel gets 40-120 s, the cap stated as a cap; every rule but FORMAT
    # and THE BEATS is the base prompt's, word for word.
    assert "110 to 312 spoken words in total (40 to 120 seconds spoken)" in base
    assert "hard CAP" in base and "(40-120 seconds)" in base
    tail = lambda text: text[text.index("LENGTH"):].split("Return JSON")[0]
    assert tail(base) == tail(system)


def test_themed_fixtures_pass_every_grader():
    source = "\n\n".join(s.text for s in parse_markdown(REACT_DOC))
    for theme, name in THEMED.items():
        script = MotionScript(**_fixture(name))
        assert script.theme == theme and script.template == "fix_story"
        results = checks.run_motion_script_graders(script, source)
        assert checks.all_passed(results), (theme, [str(r) for r in results if not r.passed])
    two = MotionScript(**_fixture(THEMED["interview"]))
    assert all(c.speaker in ("INTERVIEWER", "CANDIDATE") for s in two.shots for c in s.captions)


def test_every_reel_gets_forty_to_one_twenty_seconds():
    """Phase 3 review: every theme — classic_explainer included — and both
    templates get 40-120 s. Over 120 s still fails. (Shot-level word caps are
    a separate rule — this checks only the whole-reel window, length_ok.)"""
    def padded(theme: str, sentences: int) -> MotionScript:
        data = _fixture(THEMED["bug_hunt"])
        data["theme"] = theme
        extra = "It keeps the same value safe through every single render."
        for i in range(sentences):
            shot = data["shots"][3 + i % 6]
            shot["speech"] += " " + extra
            shot["captions"].append({"text": extra})
        return MotionScript(**data)

    for theme in ("bug_hunt", "classic_explainer"):
        mid = padded(theme, 6)                          # ~58 s + 6 x 10 words
        assert 75 < mid.estimated_seconds < 120, mid.estimated_seconds
        assert checks.check_motion_word_budget(mid).details["length_ok"], theme
    r = checks.check_motion_word_budget(padded("bug_hunt", 18))      # past 312 words
    assert not r.details["length_ok"] and "a bug_hunt reel needs 110-312" in r.reason, r.reason
    r = checks.check_motion_word_budget(padded("classic_explainer", 18))
    assert not r.details["length_ok"] and "a fix_story needs 110-312" in r.reason, r.reason


def test_theme_speaker_grader():
    source = "\n\n".join(s.text for s in parse_markdown(REACT_DOC))
    data = _fixture(THEMED["interview"])
    data["shots"][1]["captions"][0]["speaker"] = "INTERVIEWER"     # title is the candidate's
    r = checks.check_motion_theme_speakers(MotionScript(**data))
    assert not r.passed and "s02 (title) has ['INTERVIEWER'] speaking" in r.reason, r.reason
    data = _fixture(THEMED["interview"])
    data["shots"][3]["captions"][0].pop("speaker")
    r = checks.check_motion_theme_speakers(MotionScript(**data))
    assert not r.passed and "caption speaker(s) [None]" in r.reason, r.reason
    data = _fixture(THEMED["bug_hunt"])
    data["shots"][0]["captions"][0]["speaker"] = "NARRATOR"
    r = checks.check_motion_theme_speakers(MotionScript(**data))
    assert not r.passed and "one narrator" in r.reason, r.reason
    data = _fixture(THEMED["interview"])
    data["speakers"] = []
    r = checks.check_motion_theme_speakers(MotionScript(**data))
    assert not r.passed and "cast nobody" in r.reason, r.reason
    # A phase 1 script (no theme) is graded as its template's base theme.
    assert checks.check_motion_theme_speakers(MotionScript(**_fixture("usestate_golden.json"))).passed
    assert checks.all_passed(checks.run_motion_script_graders(
        MotionScript(**_fixture("usestate_golden.json")), source))


def test_only_asking_roles_may_ask():
    data = _fixture(THEMED["interview"])
    data["shots"][3]["captions"][1]["text"] = "The variable starts fresh, back to <b>zero</b>?"
    data["shots"][3]["speech"] = data["shots"][3]["speech"].rstrip(".") + "?"
    r = checks.check_motion_not_qa(MotionScript(**data))
    assert not r.passed and "s04 (break_1) CANDIDATE asks" in r.reason, r.reason
    r = checks.check_motion_not_qa(MotionScript(**_fixture(THEMED["interview"])))
    assert r.passed and "dialogue between INTERVIEWER and CANDIDATE" in r.reason
    data = _fixture(THEMED["interview"])
    data["shots"][2]["speech"] = "INTERVIEWER: " + data["shots"][2]["speech"]
    r = checks.check_motion_not_qa(MotionScript(**data))
    assert not r.passed and "speaker label" in r.reason


def test_themed_hook_uses_the_theme_openers():
    data = _fixture(THEMED["bug_hunt"])
    ok = checks.check_motion_hook_curiosity(MotionScript(**data))
    assert ok.passed, ok.reason                       # a claim, not a question
    data["shots"][0]["speech"] = "Ever wondered why this like button stays stuck at zero?"
    data["shots"][0]["captions"] = [{"text": data["shots"][0]["speech"]}]
    r = checks.check_motion_hook_curiosity(MotionScript(**data))
    assert not r.passed and "a bug_hunt hook does" in r.reason, r.reason


def test_a_themed_hook_failure_is_repaired_with_the_themed_prompt():
    from shorts.schema import MotionHookFix, MotionScriptDraft
    sections = parse_markdown(REACT_DOC)
    section = find_section(sections, "7.2")
    topic = Topic(id="t", topic="Why?", why_it_matters="w", source_section_id="7.2",
                  difficulty="easy")
    source = "\n\n".join(s.text for s in sections)
    data = _fixture(THEMED["interview"])
    good = data["shots"][0]
    bad = copy.deepcopy(data)
    bad["shots"][0]["speech"] = "Have you ever wondered about React counters?"
    bad["shots"][0]["captions"] = [{"text": "Have you ever wondered about React counters?",
                                    "speaker": "INTERVIEWER"}]
    draft = MotionScriptDraft(**{k: bad[k] for k in ("hook_question", "concept_name", "promise",
                                                    "icon_vocabulary", "takeaways", "shots")})
    fix = MotionHookFix(hook_question=data["hook_question"], speech=good["speech"],
                        captions=good["captions"], visual=good["visual"])
    calls = []
    real = script_mod.ask_json

    def fake(system, user, model_cls, **kw):
        calls.append((model_cls.__name__, system, user))
        return [draft, fix][len(calls) - 1]
    script_mod.ask_json = fake
    try:
        script, results = script_mod.write_motion_script(
            topic, section, short_id="t__motion", source_text=source, theme="interview",
            language="react")
    finally:
        script_mod.ask_json = real
    assert script is not None and checks.all_passed(results), [str(r) for r in results]
    assert [c[0] for c in calls] == ["MotionScriptDraft", "MotionHookFix"]
    assert "FORMAT — THEME: interview" in calls[0][1] and "THEME: interview" in calls[0][2]
    assert "interview format" in calls[1][1] and '"speaker": "INTERVIEWER"' in calls[1][1]
    assert script.theme == "interview" and script.language == "react"
    assert [(sp.label, sp.identity) for sp in script.speakers] == [("Interviewer", "host"), ("Candidate", "react")]


def test_write_motion_script_refuses_a_theme_of_the_wrong_template():
    sections, section = _react()
    topic = Topic(id="t", topic="Why?", why_it_matters="w", source_section_id="7.2",
                  difficulty="easy")
    _expect_value_error(lambda: script_mod.write_motion_script(
        topic, section, short_id="t__motion", source_text=section.text,
        theme="step_by_step_walkthrough"), "is a walkthrough theme")
    _expect_value_error(lambda: script_mod.write_motion_script(
        topic, section, short_id="t__motion", source_text=section.text, theme="podcast"),
        "not in the theme registry")


# ==================================================================== runner

def _runner_reel(out: Path, *args: str, doc: Path = REACT_DOC) -> tuple[str, MotionScript, dict, dict]:
    code, text = _run_runner("--yes", *args, doc=doc)
    assert code == 0, text
    newest = max(out.glob("*.motion.json"), key=lambda p: p.stat().st_mtime_ns)
    short_id = newest.name[: -len(".motion.json")]
    script = MotionScript.model_validate_json(newest.read_text(encoding="utf-8"))
    theme = json.loads((out / short_id / "theme.json").read_text(encoding="utf-8"))
    tags = json.loads((out / short_id / "tags.json").read_text(encoding="utf-8"))
    return text, script, theme, tags


def test_stub_reels_in_five_themes_at_no_cost():
    """Five different themes end to end in stub mode: the three themed
    fixtures through --theme, classic_explainer by fit, and the walkthrough
    through --template. Every script passes every grader; nothing is spent."""
    with _temp_output() as out:
        cursor = usage.mark()
        seen = {}
        for theme in ("interview", "peer_discussion", "bug_hunt"):
            text, script, saved, tags = _runner_reel(out, "--theme", theme)
            assert script.theme == theme and saved["theme"] == theme and saved["source"] == "flag"
            assert tags["tags"][:2] == ["#react", f"#{mt.registry().themes[theme].tag}"]
            assert f"=== Theme: {theme} (flag) ===" in text and "Approve theme?" in text
            seen[theme] = script
        assert [sp.role for sp in seen["interview"].speakers] == ["INTERVIEWER", "CANDIDATE"]
        assert [sp.identity for sp in seen["peer_discussion"].speakers] == ["host", "react"]
        assert seen["bug_hunt"].speakers == []
        assert "INTERVIEWER: Why does this like counter" in _run_runner(
            "--topic", next(p.parent.name for p in out.glob("*/theme.json")
                            if json.loads(p.read_text())["theme"] == "interview"))[1]

        text, script, saved, _ = _runner_reel(out)
        assert saved["source"] == "llm" and script.theme == "classic_explainer"
        assert "bug_hunt" not in saved["eligible"]       # the previous reel's theme
        assert "earlier reels in react: interview, peer_discussion, bug_hunt" in text
        seen["classic_explainer"] = script

        text, script, saved, tags = _runner_reel(out, "--template", "walkthrough", doc=TOKEN_DOC)
        assert script.theme == "step_by_step_walkthrough" and script.template == "walkthrough"
        assert saved["source"] == "only_candidate" and tags["language"] == "cs"
        seen["step_by_step_walkthrough"] = script
        assert len(seen) == 5
        spend = usage.since(cursor)
        assert spend["calls"] == 0 and spend["cost"] == 0.0, spend


def test_runner_theme_gate_declined_saves_nothing():
    import sys
    with _temp_output() as out:
        _run_runner("--yes", "--theme", "interview")
        [setup] = list(out.glob("*/setup.json"))
        short_id = setup.parent.name
        for f in ("theme.json", "tags.json"):
            (out / short_id / f).unlink()
        (out / f"{short_id}.motion.json").unlink()
        real = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            code, text = _run_runner("--topic", short_id, "--theme", "bug_hunt")
        finally:
            sys.stdin = real
        assert code == 1 and "Stopped at the theme" in text and "--theme <id>" in text, text
        assert not (out / short_id / "theme.json").exists()
        assert not (out / short_id / "tags.json").exists()


def test_runner_resume_keeps_the_approved_theme():
    with _temp_output() as out:
        _, _, _, _ = _runner_reel(out, "--theme", "bug_hunt")
        short_id = next(out.glob("*/theme.json")).parent.name
        code, text = _run_runner("--topic", short_id)
        assert code == 0 and "theme: resumed bug_hunt" in text, text
        code, text = _run_runner("--topic", short_id, "--theme", "interview")
        assert code == 1 and "--force-stage theme" in text, text
        code, text = _run_runner("--topic", short_id, "--theme", "interview", "--yes",
                                 "--force-stage", "theme")
        assert code == 0 and "=== Theme: interview (flag) ===" in text, text


def test_runner_refuses_a_theme_the_section_cannot_carry():
    with _temp_output():
        code, text = _run_runner("--yes", "--theme", "predict_the_output", doc=TOKEN_DOC)
        assert code == 1 and "needs code in the section" in text, text


def test_explainer_and_story_paths_do_not_import_themes():
    for name in ("run.py", "story_reel.py", "workflow.py", "review.py"):
        source = (ROOT / "shorts" / name).read_text(encoding="utf-8")
        assert "motion_themes" not in source and "skills.theme" not in source, name


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} motion theme tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL MOTION THEME TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
