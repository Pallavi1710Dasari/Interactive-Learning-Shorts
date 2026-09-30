"""
RESTYLE_TO_STORY_REELS.md Step 1 + Step 2: unit tests for every rule added to
checks.check_mapping, checks.check_hook, checks.check_story_not_qa (Step 1),
and Step 2's mapping-accuracy rules (Part A) and shot-generation checks
(Part B), plus a full end-to-end SHORTS_STUB=1 run of the story path.

No API key, no network, no real LLM calls — every test here exercises the
deterministic checks directly (the same shape as hook_grounding_test.py) or
the SHORTS_STUB canned responses, never a real model.

    SHORTS_STUB=1 python -m shorts.story_mode_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import shorts.skills.script as script_mod
from pydantic import ValidationError

from shorts import checks, config, story_audio
from shorts.parse import parse_markdown, story_evidence_pool
from shorts.schema import (ConceptMapping, ConceptMappingSet, MetaphorCandidate,
                           MetaphorVerdict, Section, Shot, StoryEvalReport, Topic)
from shorts.skills.script import _assign_chosen_candidate, plan_story_mapping
from shorts.stubs import build_stub_shots


SOURCE = (
    "A plain variable does not survive a re-render — it is recreated from "
    "scratch every time the component function runs. useState instead keeps "
    "its value in a slot React owns, outside the function body, so the value "
    "read on the next render is the one written on the last one."
)

PROBLEM_QUOTE = "A plain variable does not survive a re-render"
FIX_QUOTE = "useState instead keeps its value in a slot React owns"


def _candidates():
    # No `chosen` set here on purpose — Step 1's fix makes it code-computed
    # (see _assign_chosen_candidate below), never something a test (or the
    # model) needs to supply for check_mapping to grade the mapping.
    return [
        MetaphorCandidate(name="library checkout desk", pitch="a desk that keeps a ledger",
                          familiarity=5, faithfulness=5, drawability=5, drama=5),
        MetaphorCandidate(name="runner-up A", pitch="weaker pick",
                          familiarity=3, faithfulness=3, drawability=3, drama=3),
        MetaphorCandidate(name="runner-up B", pitch="weaker pick",
                          familiarity=2, faithfulness=3, drawability=3, drama=2),
    ]


def _mapping():
    return [
        ConceptMapping(
            concept_rule="a plain variable does not survive a re-render",
            source_quote=PROBLEM_QUOTE, actor="Rahul",
            metaphor_event="Rahul writes a note on the whiteboard and it is wiped clean",
            visible_proof="Rahul writes 5, the room resets, the whiteboard is blank",
            lesson_line="Some things need a better place to live."),
        ConceptMapping(
            concept_rule="useState keeps the value across renders",
            source_quote=FIX_QUOTE, actor="System",
            metaphor_event="the librarian writes the number in the ledger instead of the whiteboard",
            visible_proof="the room resets, the ledger still shows 5",
            lesson_line="Some things are worth remembering."),
    ]


# ============================================================ 1. check_mapping

def test_valid_mapping_passes():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a small library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert result.passed, result.reason
    print("   ok — a well-formed mapping (actors, props, setting, candidates, "
          "problem-first) passes check_mapping")


def test_bad_actor_fails():
    mapping = _mapping()
    mapping[0].actor = "Priya"
    result = checks.check_mapping(mapping, SOURCE, setting="a library checkout desk",
                                  props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — an actor outside {{Rahul, Riya, System}} fails check_mapping: "
          f"{result.reason}")


def test_first_entry_actor_not_rahul_fails():
    """THE ACTOR-ROLE RULE: Rahul owns the problem. A first entry whose
    concept_rule is genuinely the problem, but whose actor is System (a
    valid actor generally), must still fail — it is the wrong role for the
    FIRST entry specifically."""
    mapping = _mapping()
    mapping[0].actor = "System"
    result = checks.check_mapping(mapping, SOURCE, setting="a library checkout desk",
                                  props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — a first (problem) entry whose actor isn't Rahul fails "
          f"check_mapping even though System is a valid actor generally: "
          f"{result.reason}")


def test_too_many_props_fails():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger", "badge", "key"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — more than 3 props fails check_mapping: {result.reason}")


def test_unused_prop_fails():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger", "umbrella"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — a declared prop that never appears in any metaphor_event "
          f"fails check_mapping: {result.reason}")


def test_apparatus_word_in_setting_fails():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a control room with a conveyor belt",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — an invented-apparatus word in setting fails check_mapping "
          f"(the source material never says 'conveyor'): {result.reason}")


def test_apparatus_word_allowed_when_source_is_about_it():
    source = SOURCE + " The whole system is built from gears and a single circuit."
    result = checks.check_mapping(
        _mapping(), source, setting="a workshop full of gears",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert result.passed, result.reason
    print("   ok — 'gears'/'circuit' in setting is allowed when the source "
          "material itself uses those words")


def test_first_entry_not_a_problem_fails():
    mapping = _mapping()
    mapping[0], mapping[1] = mapping[1], mapping[0]  # definition first, problem second
    result = checks.check_mapping(
        mapping, SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — a first entry that is a definition, not the problem, fails "
          f"check_mapping: {result.reason}")


def test_four_entries_without_reason_fails():
    mapping = _mapping() + [
        ConceptMapping(concept_rule="a third rule", source_quote=PROBLEM_QUOTE,
                       actor="Rahul", metaphor_event="ledger event 3 with the whiteboard",
                       visible_proof="proof 3", lesson_line="Lesson three."),
        ConceptMapping(concept_rule="a fourth rule", source_quote=FIX_QUOTE,
                       actor="Riya", metaphor_event="ledger event 4 with the ledger",
                       visible_proof="proof 4", lesson_line="Lesson four."),
    ]
    result = checks.check_mapping(
        mapping, SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — 4 mapping entries with no extra_entry_reason fails "
          f"check_mapping: {result.reason}")


def test_four_entries_with_reason_passes():
    mapping = _mapping() + [
        ConceptMapping(concept_rule="a third rule", source_quote=PROBLEM_QUOTE,
                       actor="Rahul", metaphor_event="ledger event 3 with the whiteboard",
                       visible_proof="proof 3", lesson_line="Lesson three."),
        ConceptMapping(concept_rule="a fourth rule", source_quote=FIX_QUOTE,
                       actor="Riya", metaphor_event="ledger event 4 with the ledger",
                       visible_proof="proof 4", lesson_line="Lesson four."),
    ]
    result = checks.check_mapping(
        mapping, SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(),
        extra_entry_reason="the section has a genuinely separate 4th sub-rule", technical_term="state")
    assert result.passed, result.reason
    print("   ok — 4 entries WITH extra_entry_reason passes check_mapping")


def test_wrong_candidate_count_fails():
    candidates = _candidates()[:2]
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=candidates, technical_term="state")
    assert not result.passed
    print(f"   ok — anything other than 3 candidates fails check_mapping: "
          f"{result.reason}")


def test_candidate_total_is_computed_not_trusted():
    c = MetaphorCandidate(name="x", pitch="y", familiarity=5, faithfulness=5,
                          drawability=5, drama=5)
    assert c.total == 20
    print("   ok — MetaphorCandidate.total is derived from the 4 scores, not "
          "a separate field a model could get wrong")


def test_check_mapping_no_longer_grades_chosen_at_all():
    """Step 1's fix: `chosen` moved out of check_mapping entirely (it is now
    set in code — see _assign_chosen_candidate below). A candidate set with
    every `chosen` left at its False default must not fail check_mapping —
    the old 'exactly one candidate must be marked chosen' rule is gone."""
    candidates = _candidates()
    assert not any(c.chosen for c in candidates), "none should be pre-marked"
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=candidates, technical_term="state")
    assert result.passed, result.reason
    print("   ok — check_mapping passes a candidate set with no `chosen` "
          "marked at all; that field is no longer its job")


# ================================================ 1c. STEP 9 FIX 2 — technical_term

def test_missing_technical_term_fails_check_mapping():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="")
    assert not result.passed
    assert "technical_term" in result.reason
    print(f"   ok — a blank technical_term fails check_mapping: {result.reason}")


def test_missing_technical_term_fails_check_mapping_when_omitted_entirely():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates())
    assert not result.passed
    assert "technical_term" in result.reason
    print(f"   ok — omitting technical_term entirely (default '') also fails "
         f"check_mapping, not just an explicit blank string: {result.reason}")


def test_concept_mapping_set_requires_technical_term_at_the_schema_level():
    kwargs = _mapping_set_kwargs()
    del kwargs["technical_term"]
    try:
        ConceptMappingSet(**kwargs)
        assert False, "expected a ValidationError"
    except ValidationError as e:
        print(f"   ok — ConceptMappingSet requires technical_term at the schema "
             f"level (a genuinely missing field, not just a blank one): "
             f"{str(e).splitlines()[0]}")


def test_concept_mapping_set_rejects_a_blank_technical_term():
    try:
        ConceptMappingSet(**_mapping_set_kwargs(technical_term="   "))
        assert False, "expected a ValidationError"
    except ValidationError as e:
        print(f"   ok — ConceptMappingSet's own field validator rejects a "
             f"whitespace-only technical_term too: {str(e).splitlines()[0]}")


def test_present_technical_term_lets_concept_named_once_actually_run():
    """VERIFY: 'present -> concept_named_once runs (its result must NOT say
    skipped)' — built directly against build_stub_shots (the same generator
    the real stub pipeline uses), proving the field flows end to end: mapping
    -> write_story_shots's prompt -> the stub shot list -> the free check."""
    entries = [{"actor": "Rahul", "rule": "rule 1", "quote": PROBLEM_QUOTE,
               "lesson": "Some things are worth remembering."}]
    shots_raw = build_stub_shots(entries, "Ever noticed the count resets?",
                                 ["notebook"], [], "@handle", "React",
                                 technical_term="state")
    shots = [Shot(**s) for s in shots_raw]
    mapping = [ConceptMapping(concept_rule="rule 1", source_quote=PROBLEM_QUOTE,
                              actor="Rahul", metaphor_event="stub event",
                              visible_proof="stub proof",
                              lesson_line="Some things are worth remembering.")]
    result = checks.check_concept_named_once(shots, mapping, technical_term="state")
    assert result.passed, result.reason
    assert "skipped" not in result.reason
    print(f"   ok — with technical_term supplied, concept_named_once actually "
         f"runs and its result never says 'skipped': {result.reason}")


def test_blank_technical_term_still_skips_concept_named_once():
    """The OPPOSITE case, for contrast — check_concept_named_once's own
    optional-parameter contract (unrelated to check_mapping's now-mandatory
    one) is unchanged: no technical_term at all still means 'nothing to
    grade', not a failure, for a caller that genuinely has none (e.g. an old
    persisted StoryScript — see schema.py's own note on why StoryScript.
    technical_term still defaults to "")."""
    result = checks.check_concept_named_once([], [], technical_term="")
    assert result.passed
    assert "skipped" in result.reason
    print(f"   ok — check_concept_named_once itself is unchanged: still "
         f"skips (not fails) when genuinely given no technical_term: "
         f"{result.reason}")


# =================================================== 1b. _assign_chosen_candidate

def test_assign_chosen_picks_highest_total():
    candidates = _candidates()   # totals: 20, 12, 10
    _assign_chosen_candidate(candidates)
    chosen = [c for c in candidates if c.chosen]
    assert len(chosen) == 1 and chosen[0].name == "library checkout desk"
    print("   ok — _assign_chosen_candidate marks exactly the highest-total "
          "candidate chosen, in code")


def test_assign_chosen_breaks_ties_on_faithfulness_then_familiarity():
    candidates = [
        MetaphorCandidate(name="A", pitch="p", familiarity=4, faithfulness=4,
                          drawability=4, drama=4),   # total 16
        MetaphorCandidate(name="B", pitch="p", familiarity=5, faithfulness=3,
                          drawability=4, drama=4),   # total 16, lower faithfulness
        MetaphorCandidate(name="C", pitch="p", familiarity=3, faithfulness=5,
                          drawability=4, drama=4),   # total 16, highest faithfulness
    ]
    _assign_chosen_candidate(candidates)
    chosen = [c for c in candidates if c.chosen]
    assert len(chosen) == 1 and chosen[0].name == "C"
    print("   ok — a total tie is broken by faithfulness first: "
          f"{[c.name for c in chosen]}")


def test_assign_chosen_overwrites_any_stray_model_supplied_flag():
    """Even if a model response still sets `chosen: true` on a LOSING
    candidate (the exact failure this fix responds to), _assign_chosen_
    candidate corrects it rather than trusting the model's flag."""
    candidates = _candidates()
    candidates[1].chosen = True   # a lower-scoring candidate, marked anyway
    _assign_chosen_candidate(candidates)
    chosen = [c for c in candidates if c.chosen]
    assert len(chosen) == 1 and chosen[0].name == "library checkout desk"
    print("   ok — a stray model-supplied `chosen` on a losing candidate is "
          "overwritten by the code-computed winner")


# ================================================================ 2. check_hook

def test_grounded_curiosity_hook_passes():
    result = checks.check_hook("Ever noticed your button always resets to zero?",
                               technical_term="useState")
    assert result.passed, result.reason
    print("   ok — a curiosity hook about the symptom, naming no technical "
          "term, passes check_hook")


def test_hook_naming_technical_term_fails():
    result = checks.check_hook("Have you ever wondered what useState actually does?",
                               technical_term="useState")
    assert not result.passed
    print(f"   ok — a hook that names the concept's own technical term fails "
          f"check_hook: {result.reason}")


def test_hook_not_matching_curiosity_shape_fails():
    result = checks.check_hook("Rahul walks into the library every morning.",
                               technical_term="useState")
    assert not result.passed
    print(f"   ok — a hook that isn't phrased as a curiosity hook fails "
          f"check_hook: {result.reason}")


def test_hook_spoken_by_a_character_fails():
    result = checks.check_hook("Rahul: have you ever wondered why this keeps happening?",
                               technical_term="")
    assert not result.passed
    print(f"   ok — a hook line prefixed like a character speaking fails "
          f"check_hook (must be the Narrator's line): {result.reason}")


def test_hook_check_skips_term_check_when_blank():
    result = checks.check_hook("Ever noticed how the button never seems to update?",
                               technical_term="")
    assert result.passed, result.reason
    print("   ok — with no technical_term supplied, check_hook only grades "
          "shape and speaker, not the (unknown) term")


def test_short_ever_verb_hook_no_longer_passes():
    """A LATER FIX NARROWED the accepted shape back down from Step 1's
    'any ever <verb>...' to a fixed rotating set of exactly 4 openers
    (checks.HOOK_OPENERS) — this exact line (Step 1's own widened example)
    must now FAIL, the opposite of what it did before that fix."""
    result = checks.check_hook("Ever clicked a button that just refuses to change?")
    assert not result.passed
    assert "does not begin with one of the required openers" in result.reason
    print(f"   ok — 'Ever clicked...' (Step 1's own former example, not one "
         f"of the 4 fixed openers) now fails check_hook: {result.reason}")


def test_all_four_hook_openers_pass():
    variants = [
        "Have you ever wondered why a counter refuses to move?",
        "Ever noticed a counter that refuses to move?",
        "Did you know a counter can refuse to move?",
        "Ever wonder why a counter refuses to move?",
    ]
    for v in variants:
        result = checks.check_hook(v)
        assert result.passed, (v, result.reason)
    print(f"   ok — all 4 required openers pass check_hook: {variants}")


def test_hook_opener_match_is_case_insensitive():
    result = checks.check_hook("DID YOU KNOW a counter can refuse to move?")
    assert result.passed, result.reason
    result2 = checks.check_hook("eVeR nOtIcEd a counter that refuses to move?")
    assert result2.passed, result2.reason
    print("   ok — the 4 required openers match case-insensitively")


def test_non_matching_curiosity_shaped_line_fails_hook():
    """A line that clearly READS as a curiosity hook, but doesn't use one
    of the 4 fixed openers, must still fail — the rule is a specific
    rotating set now, not 'anything curiosity-shaped'."""
    result = checks.check_hook("Curious why your counter keeps resetting?")
    assert not result.passed
    print(f"   ok — a genuinely curiosity-shaped line that isn't one of the "
         f"4 required openers still fails check_hook: {result.reason}")


def test_hook_over_word_limit_fails():
    long_hook = ("Have you ever wondered why clicking a button over and over "
                "again on your screen sometimes just does not seem to work "
                "at all?")
    assert len(long_hook.split()) > checks.HOOK_MAX_WORDS
    result = checks.check_hook(long_hook)
    assert not result.passed
    print(f"   ok — a hook over {checks.HOOK_MAX_WORDS} words fails check_hook "
          f"even with the right curiosity shape: {result.reason}")


def test_hook_at_word_limit_passes():
    twelve_words = "Ever noticed how a number you wrote down can vanish so fast"
    assert len(twelve_words.split()) == checks.HOOK_MAX_WORDS
    result = checks.check_hook(twelve_words)
    assert result.passed, result.reason
    print(f"   ok — a hook at exactly {checks.HOOK_MAX_WORDS} words passes check_hook")


# ======================================================= 3. check_story_not_qa

def _shot(shot_id, characters, line):
    return Shot(shot_id=shot_id, characters=characters, action="stub action", line=line)


def test_story_dialogue_without_qa_passes():
    shots = [
        _shot("s0", [], "Ever wondered why your button always resets to zero?"),
        _shot("s1", ["Rahul"], "Rahul taps the button again and again, nothing sticks."),
        _shot("s2", ["Riya"], "Riya just smiles and writes the number in the ledger."),
    ]
    result = checks.check_story_not_qa(shots)
    assert result.passed, result.reason
    print("   ok — narration + reaction, no character interviewing another, "
          "passes check_story_not_qa")


def test_question_then_explanation_fails():
    shots = [
        _shot("s0", ["Rahul"], "What is useState?"),
        _shot("s1", ["Riya"], "useState is a hook that lets a component keep state "
                             "between renders, unlike a plain variable."),
    ]
    result = checks.check_story_not_qa(shots)
    assert not result.passed
    print(f"   ok — 'What is X?' followed by another character's explanation "
          f"fails check_story_not_qa: {result.reason}")


def test_question_mark_then_definition_fails():
    shots = [
        _shot("s0", ["Rahul"], "Why does the count keep going back to zero?"),
        _shot("s1", ["Riya"], "That happens because a plain variable is recreated "
                             "on every render, so it never remembers anything."),
    ]
    result = checks.check_story_not_qa(shots)
    assert not result.passed
    print(f"   ok — a genuine question mark followed by an explanatory reply "
          f"from a different character fails check_story_not_qa: {result.reason}")


def test_same_speaker_question_is_not_qa():
    """A character wondering out loud, then answering their own action (not
    another character explaining), is not an interview — no OTHER character
    is doing the explaining."""
    shots = [
        _shot("s0", ["Rahul"], "Why does this keep happening?"),
        _shot("s1", ["Rahul"], "Rahul frowns and tries again."),
    ]
    result = checks.check_story_not_qa(shots)
    assert result.passed, result.reason
    print("   ok — the same speaker before and after a question is not "
          "flagged as an interview exchange")


def test_short_reaction_after_question_passes():
    shots = [
        _shot("s0", ["Rahul"], "Why does this keep happening?"),
        _shot("s1", ["Riya"], "Riya just shrugs."),
    ]
    result = checks.check_story_not_qa(shots)
    assert result.passed, result.reason
    print("   ok — a short reaction (not a definition) after a question "
          "passes check_story_not_qa")


# =============================================================== 4. card_facts

def _mapping_set_kwargs(**overrides):
    kwargs = dict(mapping=_mapping(), system_name="React", setting="a library desk",
                  props=["whiteboard", "ledger"], candidates=_candidates(),
                  hook_line="Ever noticed how the desk always resets?",
                  technical_term="state")
    kwargs.update(overrides)
    return kwargs


def test_card_facts_up_to_two_is_fine():
    m = ConceptMappingSet(**_mapping_set_kwargs(card_facts=["useState returns [value, setter]"]))
    assert m.card_facts == ["useState returns [value, setter]"]
    print("   ok — a mapping output with 1-2 card_facts validates fine")


def test_three_card_facts_is_rejected_by_schema():
    try:
        ConceptMappingSet(**_mapping_set_kwargs(
            card_facts=["fact one", "fact two", "fact three"]))
        assert False, "expected a ValidationError"
    except ValidationError as e:
        print(f"   ok — ConceptMappingSet rejects a 3rd card_fact at the schema "
              f"level: {e}".splitlines()[0])


# ===================================================== 5. story_evidence_pool

def _fake_sections():
    return [
        Section(section_id="1", title="Why the count never updates", text="the problem text",
               start_line=1, end_line=2),
        Section(section_id="2", title="How useState creates and updates state",
               text="the mechanism text", start_line=3, end_line=4),
        Section(section_id="3", title="What state actually means in a component",
               text="the meaning text", start_line=5, end_line=6),
    ]


def test_evidence_pool_includes_problem_and_meaning_sections():
    sections = _fake_sections()
    pooled_text, used = story_evidence_pool(sections, "2")
    assert set(used) == {"1", "2", "3"}, used
    assert "the problem text" in pooled_text
    assert "the meaning text" in pooled_text
    print(f"   ok — story_evidence_pool widens past the base section to the "
          f"PROBLEM section ('why') and the MEANING section ('actually "
          f"means'): sections used = {used}")


def test_evidence_pool_is_just_the_base_section_when_no_others_qualify():
    sections = [Section(section_id="2", title="How useState creates and updates state",
                        text="the mechanism text", start_line=1, end_line=2)]
    pooled_text, used = story_evidence_pool(sections, "2")
    assert used == ["2"]
    print("   ok — with no problem/meaning-shaped heading in the document, "
          "story_evidence_pool returns just the base section (a missed "
          "addition, not a wrong one)")


# ==========================================================================
# STEP 2 PART A — mapping accuracy rules
# ==========================================================================

def test_prompt_still_states_the_wrong_vs_right_action_rule():
    """Regression guard on SYSTEM_STORY's prose (Step 2 Part A #1) — cheap
    insurance against a future edit silently dropping the rule."""
    flat = " ".join(script_mod.SYSTEM_STORY.split())
    assert "DIFFERENT, DELIBERATE ACTION" in flat
    assert "System never fixes the wrong approach automatically" in flat
    print("   ok — SYSTEM_STORY still states the wrong-approach/right-approach "
          "distinct-action rule")


def test_prompt_still_states_part_b_structure():
    """Regression guard on SYSTEM_STORY_SHOTS's prose (Step 2 Part B)."""
    for phrase in ("24 TO 30 SHOTS", "text_card", "recap", "cta",
                  "Never 3 `wide`-framed SCENE shots", "close_up"):
        assert phrase in script_mod.SYSTEM_STORY_SHOTS, phrase
    print("   ok — SYSTEM_STORY_SHOTS still states the shot-count, structure "
          "and rhythm rules")


def test_prompt_states_the_per_mini_scene_shot_arithmetic():
    """Regression guard on the under-generation fix: a real production run
    (why_plain_variable_fails, 3-entry mapping) wrote mini-scenes stuck at
    check_scene_coverage's own >= 3 FLOOR, failing shot_count (15 shots,
    needs 24-30) and story_duration (54.8s, needs 60-80s) — the prompt
    stated only a floor, never a target, so the model had no signal to
    aim higher. This checks the arithmetic-based target replacing it is
    still there."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "ONLY THE" in flat and "FLOOR" in flat and "NEVER THE TARGET" in flat
    assert "DO THE ARITHMETIC BEFORE WRITING" in flat
    assert "aim for 8 shots PER MINI-SCENE" in flat
    print("   ok — SYSTEM_STORY_SHOTS states the mini-scene shot count as "
         "computed arithmetic (total budget minus fixed shots, split across "
         "entries), not just a bare '>= 3' floor with no target")


def test_prompt_targets_the_upper_part_of_the_shot_count_range():
    """
    STEP 9 FIXES ROUND 6: the round-3 fix retargeted the MIDDLE of the
    24-30 range (~27) to fix an earlier overcorrection (52.4s/18 shots),
    but real runs kept landing at 22-23 shots — a consistent undershoot
    even against a middle target, not random variance. Duration had real
    headroom the whole time (63-68s against an 80s ceiling), so the fix
    is a further, deliberate nudge UP — past the middle, toward the
    ceiling (~29) — rather than re-centering again, since centering
    alone already proved insufficient against this model's own
    undershoot bias.
    """
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "aim for ~29, close to the ceiling" in flat
    assert "not 24 and not the middle" in flat
    assert "landing at 22-23 shots" in flat
    assert "every real failure of this rule so far has been an undershoot" in flat
    print("   ok — SYSTEM_STORY_SHOTS now targets ~29 shots (near the "
         "ceiling of 24-30), explicitly citing the documented 22-23 "
         "undershoot pattern rather than re-centering on the middle again")


def test_prompt_warns_against_compensating_with_longer_lines():
    """Regression guard on the NEW bug the overcorrection introduced: shot
    5's line was 13 words (over the 12-word check_line_length cap) after
    the model was told most shots should carry no line at all — cutting
    spoken shots without warning against packing more meaning into the
    ones that remain. The prompt must now explicitly forbid that trade."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "Do NOT cut this further to save duration" in flat
    assert ("a line written to cover for a cut spoken shot is exactly how a "
           "line ends up over the word cap") in flat
    assert "give it its OWN shot instead of cramming it into a neighboring line" in flat
    print("   ok — SYSTEM_STORY_SHOTS explicitly warns against writing "
         "longer lines to compensate for fewer spoken shots")


def test_prompt_states_medium_framing_for_text_card_recap_cta():
    """The other half of the same real-run failure: text_card/recap/cta
    shots came back framing='wide' (nothing in the prompt said otherwise),
    and 3 of them in a row failed check_shot_rhythm's 'never 3 wide in a
    row' pacing rule — a rule meant for drawn SCENE composition, not flat
    graphic cards. See checks.check_shot_rhythm's own docstring for the
    robust half of this fix (the check itself is now scene-shot-only);
    this is the belt-and-suspenders prompt half."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert flat.count('`framing`: "medium"') == 3, (
        "the text_card, recap, AND cta steps must each state medium "
        "framing explicitly")
    assert "RHYTHM (SCENE SHOTS ONLY" in flat
    print("   ok — SYSTEM_STORY_SHOTS tells the model exactly what framing "
         "to use for text_card/recap/cta shots (medium, never wide), and "
         "states the RHYTHM section applies to scene shots only")


def test_prompt_states_duration_headroom_and_line_density_guidance():
    """Real-run fix, ROUND 2: why_plain_variable_fails__story landed at
    86.4s (over the 80s ceiling) even with an acceptable shot count —
    driven by too many shots carrying a spoken `line`. ROUND 3 then had to
    retune this AGAIN after round 2's wording overcorrected to 52.4s/18
    shots with a 13-word line — see test_prompt_targets_the_middle_of_
    shot_count_and_duration_ranges and test_prompt_warns_against_
    compensating_with_longer_lines for that fix's own guards. This test
    only checks the guidance that survived unchanged across both rounds:
    a 65-75s target and an explicit line-density instruction."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "65-75 SECONDS" in flat
    assert "Roughly HALF the shots in each mini-scene should carry a spoken" in flat
    print("   ok — SYSTEM_STORY_SHOTS states a 65-75s duration target and "
         "an explicit line-density instruction (roughly half the shots in "
         "each mini-scene carry a spoken line)")


def test_prompt_states_the_reveal_close_up_rule_as_mandatory():
    """Real-run fix: the same run failed check_shot_rhythm's reveal rule 3
    times in one script (shots 5, 12, 17) — the old prompt wording ('the
    shot right after a reveal is always a close_up reaction') was true but
    apparently not forceful enough. Strengthened wording, PLUS a
    deterministic code-level auto-correction (skills.script._force_close_
    up_after_every_reveal, see its own tests) that no longer depends on
    the model complying at all."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "MUST BE FRAMED `close_up` — NO EXCEPTIONS" in flat
    print("   ok — SYSTEM_STORY_SHOTS states the reveal->close_up rule as "
         "mandatory, with no-exceptions language")


def test_card_fact_restating_mapping_entry_fails():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(),
        card_facts=["a plain variable does not survive a re-render, it is recreated"], technical_term="state")
    assert not result.passed
    print(f"   ok — a card_fact that restates a mapping entry's concept_rule "
          f"fails check_mapping: {result.reason}")


def test_card_fact_distinct_from_mapping_passes():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(),
        card_facts=["useState(initialValue) returns exactly two things in an array"], technical_term="state")
    assert result.passed, result.reason
    print("   ok — a card_fact that is genuinely distinct from every "
          "concept_rule passes check_mapping")


def test_prop_that_is_a_mark_not_an_object_fails():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "a chalk tally mark"], candidates=_candidates(), technical_term="state")
    assert not result.passed
    print(f"   ok — a prop that is a mark/effect, not a physical object, "
          f"fails check_mapping: {result.reason}")


def test_physical_object_props_pass():
    result = checks.check_mapping(
        _mapping(), SOURCE, setting="a library checkout desk",
        props=["whiteboard", "ledger"], candidates=_candidates(), technical_term="state")
    assert result.passed, result.reason
    print("   ok — props that are all physical objects pass check_mapping")


def _judge_report(faithful: bool) -> StoryEvalReport:
    return StoryEvalReport(verdicts=[
        MetaphorVerdict(concept_rule="rule 1 does not work without the fix: stub",
                        faithful=faithful,
                        problem="" if faithful else "implies a reset the source never states")])


def test_judge_gate_passes_when_faithful():
    """plan_story_mapping calls judge_story_metaphors on the mechanically-
    approved mapping BEFORE any shot exists — monkeypatched here (rather than
    exercised through the real judge, a paid call) to prove the WIRING: a
    faithful verdict lets the mapping through."""
    calls = []
    original = script_mod.judge_story_metaphors
    script_mod.judge_story_metaphors = lambda mapping: (calls.append(1), _judge_report(True))[1]
    try:
        topic = Topic(id="t1", topic="q", why_it_matters="w", source_section_id="1",
                     difficulty="medium")
        section = Section(section_id="1", title="T", text=SOURCE, start_line=1, end_line=1)
        result = plan_story_mapping(topic, section, source_text=SOURCE)
    finally:
        script_mod.judge_story_metaphors = original
    assert result is not None
    assert len(calls) == 1
    print("   ok — a faithful judge verdict lets plan_story_mapping return the "
          "mapping on the first attempt")


def test_judge_gate_retries_then_gives_up_when_unfaithful():
    """An always-'no' judge must not let a mapping through, ever — and must
    stop after MAX_STORY_JUDGE_RETRIES+1 attempts rather than looping forever
    (no shots are ever written for a mapping the judge rejects)."""
    calls = []
    original = script_mod.judge_story_metaphors
    script_mod.judge_story_metaphors = lambda mapping: (calls.append(1), _judge_report(False))[1]
    try:
        topic = Topic(id="t2", topic="q", why_it_matters="w", source_section_id="1",
                     difficulty="medium")
        section = Section(section_id="1", title="T", text=SOURCE, start_line=1, end_line=1)
        result = plan_story_mapping(topic, section, source_text=SOURCE)
    finally:
        script_mod.judge_story_metaphors = original
    assert result is None
    assert len(calls) == script_mod.MAX_STORY_JUDGE_RETRIES + 1, calls
    print(f"   ok — an unfaithful judge verdict is retried "
          f"{script_mod.MAX_STORY_JUDGE_RETRIES} time(s) then gives up "
          f"(judge called {len(calls)} times), returning no mapping at all")


# ==========================================================================
# STEP 2 PART B — shot-generation checks
# ==========================================================================

HOOK_LINE = "Ever noticed how the count resets on its own?"
PROPS = ["whiteboard"]
CARD_FACTS = ["useState returns exactly two things in an array.",
             "Reading state again costs constant time, written O(1)."]
TECH_TERM = "React"


def _entries_and_mapping():
    raw = [
        ("a plain variable does not survive a re-render", PROBLEM_QUOTE, "Rahul",
         "Some things need a better place to live."),
        ("useState keeps the value across renders", FIX_QUOTE, "System",
         "Some things are worth remembering."),
        ("the next render reads back the same value", FIX_QUOTE, "System",
         "The next render always shows the latest write."),
    ]
    entries = [{"rule": r, "quote": q, "actor": a, "lesson": l} for r, q, a, l in raw]
    mapping = [ConceptMapping(concept_rule=r, source_quote=q, actor=a,
                              metaphor_event=f"{a} does something to the whiteboard",
                              visible_proof="the whiteboard shows the result",
                              lesson_line=l)
              for r, q, a, l in raw]
    return entries, mapping


def _good_shots_and_mapping():
    entries, mapping = _entries_and_mapping()
    # STEP 9 FIXES ROUND 8: topic_label (the cta's "...to learn <this> the
    # simple way" phrase, real usage = mapping.system_name) is deliberately
    # NOT the same string as technical_term here — reusing TECH_TERM for
    # both used to make the cta's own overlay_text always contain the
    # technical term, which check_concept_named_once's now-broadened scan
    # (it reads overlay_text too, not just `line` — see checks.
    # _shot_spoken_words) correctly flags as a second naming. Real reels
    # rarely have system_name == technical_term either (e.g. system_name
    # "React", technical_term "state"), so this fixture now matches that.
    raw_shots = build_stub_shots(entries, HOOK_LINE, PROPS, CARD_FACTS,
                                "@handle", "the app", technical_term=TECH_TERM)
    return [Shot(**d) for d in raw_shots], mapping


def _copy_shots(shots):
    return [s.model_copy(deep=True) for s in shots]


def test_good_stub_shots_pass_every_part_b_check():
    """The one 'everything is right' pass case every fail case below is a
    single mutation away from."""
    shots, mapping = _good_shots_and_mapping()
    checks_to_run = [
        checks.check_shot_count(shots),
        checks.check_story_duration(shots),
        checks.check_line_length(shots),
        checks.check_shot_rhythm(shots),
        checks.check_text_card_budget(shots, CARD_FACTS),
        checks.check_character_ratio(shots),
        checks.check_no_text_in_action(shots),
        checks.check_shot_grounding(shots, SOURCE),
        checks.check_scene_coverage(shots, mapping),
        checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM),
        checks.check_key_prop_valid(shots, PROPS),
        checks.check_structure_ends(shots, mapping),
        checks.check_story_not_qa(shots),
    ]
    failed = [r for r in checks_to_run if not r.passed]
    assert not failed, [(r.name, r.reason) for r in failed]
    print(f"   ok — the good stub script ({len(shots)} shots, "
          f"{sum(s.duration_seconds for s in shots):.1f}s) passes every Part B "
          f"check: {[r.name for r in checks_to_run]}")


def test_stub_duration_lands_with_real_headroom_under_80s():
    """The real-run failure this guards against: why_plain_variable_fails__
    story landed at 86.4s, OVER check_story_duration's own 80s ceiling.
    The fixed stub fixture must not just PASS the 60-80s check — it should
    land with genuine margin (comfortably under the 75s SYSTEM_STORY_SHOTS
    now asks for), so a small real-model overshoot still has room."""
    shots, _ = _good_shots_and_mapping()
    total = sum(s.duration_seconds for s in shots)
    lo, hi = checks.STORY_DURATION_RANGE
    assert lo <= total <= hi, (total, lo, hi)
    assert total <= hi - 5, (
        f"{total}s leaves less than 5s of headroom below the {hi}s ceiling")
    print(f"   ok — the stub fixture's total estimated duration ({total:.1f}s) "
         f"lands with real headroom under the {hi}s ceiling (needs <= {hi - 5}s)")


def test_shot_count_out_of_range_fails():
    shots, _ = _good_shots_and_mapping()
    result = checks.check_shot_count(shots[:10])
    assert not result.passed
    print(f"   ok — fewer than 24 shots fails check_shot_count: {result.reason}")


def test_story_duration_out_of_range_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)[:20]   # 20 shots x 2.0s floor = 40s, clearly under the 60s floor
    for s in shots:
        s.line = None   # every shot floors to 2.0s -> total collapses well under 60s
    result = checks.check_story_duration(shots)
    assert not result.passed
    print(f"   ok — a total estimated duration outside 60-80s fails "
          f"check_story_duration: {result.reason}")


def test_line_length_too_long_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    shots[1].line = " ".join(["word"] * 13)
    result = checks.check_line_length(shots)
    assert not result.passed
    print(f"   ok — a spoken line over 12 words fails check_line_length: {result.reason}")


def test_shot_rhythm_three_wide_in_a_row_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    shots[1].framing = shots[2].framing = shots[3].framing = "wide"
    result = checks.check_shot_rhythm(shots)
    assert not result.passed
    print(f"   ok — 3 consecutive wide-framed shots fails check_shot_rhythm: {result.reason}")


def test_stub_mini_scenes_are_well_above_the_bare_floor():
    """Direct regression guard on the under-generation bug itself: each
    mini-scene should land near the 8 shots/entry this file's own 3-
    entry, 2-card_fact fixture implies (see SYSTEM_STORY_SHOTS's own
    round-6 arithmetic instruction, retuned toward the ceiling after real
    runs kept landing at 22-23 total shots), not check_scene_coverage's
    bare >= 3 floor — a script stuck at the floor is exactly what failed
    on the real why_plain_variable_fails__story run (15 shots total,
    needs 24-30)."""
    shots, mapping = _good_shots_and_mapping()
    for m in mapping:
        n = sum(1 for s in shots if s.concept_ref == m.concept_rule)
        assert n >= 7, (
            f"mini-scene for {m.concept_rule!r} has only {n} shots — too "
            f"close to check_scene_coverage's bare floor (3), not a real scene")
    print(f"   ok — every mini-scene in the stub fixture has >= 7 shots "
         f"(well above the 3-shot floor): "
         f"{[(m.concept_rule[:30], sum(1 for s in shots if s.concept_ref == m.concept_rule)) for m in mapping]}")


def test_stub_fixture_shot_count_sits_clearly_above_the_floor_not_barely_over():
    """
    STEP 9 FIXES ROUND 6, the user's own explicit verification ask: 3
    real runs in a row landed at 22-23 shots — BELOW check_shot_count's
    24 floor, not just barely over it. This checks the STUB fixture
    (kept in step with the retuned prompt — see build_stub_shots's own
    round-6 note) sits with a genuine margin above the floor, not merely
    inside the legal range."""
    shots, _ = _good_shots_and_mapping()
    lo, hi = checks.STORY_SHOT_COUNT_RANGE
    total = len(shots)
    assert lo <= total <= hi, (total, lo, hi)
    margin = total - lo
    assert margin >= 4, (
        f"{total} shots is only {margin} above the {lo}-shot floor — not a "
        f"clear margin, the same 'barely over' failure mode being fixed")
    print(f"   ok — the stub fixture has {total} shots, {margin} above the "
         f"{lo}-shot floor (needs >= 4 margin) — clearly above it, not "
         f"just barely over")


def test_shot_rhythm_wide_text_card_recap_cta_never_fails():
    """The real-run bug this guards against: why_plain_variable_fails__story
    (a real production run) had its text_card/recap/cta shots come back
    framing='wide' from the model (nothing in the OLD prompt said
    otherwise), and 3 of them in a row failed check_shot_rhythm's 'never 3
    wide in a row' rule — a rule about drawn SCENE camera variety, never
    meant to apply to flat graphic cards. Reproduced here directly (rather
    than depending on the model actually doing this, which the stub
    dispatcher never does) by forcing framing='wide' on the last 3 shots
    (2 text_cards -> recap -> cta is 4 shots; take the LAST 3 of those,
    still 3 non-scene shots in a row) and confirming check_shot_rhythm no
    longer cares."""
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    last_three = shots[-3:]
    assert all(s.kind != "scene" for s in last_three), (
        "fixture assumption: the last 3 stub shots must be non-scene "
        f"(text_card/recap/cta): {[(s.shot_id, s.kind) for s in last_three]}")
    for s in last_three:
        s.framing = "wide"
    result = checks.check_shot_rhythm(shots)
    assert result.passed, result.reason
    print(f"   ok — 3 consecutive wide-framed NON-SCENE shots "
         f"({[s.shot_id for s in last_three]}) no longer fails "
         f"check_shot_rhythm — the rule is scene-shot-only now")


def test_shot_rhythm_no_closeup_after_reveal_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    reveal_idx = next(i for i, s in enumerate(shots) if s.story_beat == "reaction")
    shots[reveal_idx + 1].framing = "medium"
    result = checks.check_shot_rhythm(shots)
    assert not result.passed
    print(f"   ok — no close_up shot right after a reveal fails check_shot_rhythm: "
          f"{result.reason}")


def test_shot_rhythm_wide_after_reveal_fails():
    """The EXACT real-run symptom (why_plain_variable_fails__story: shots
    5, 12, 17 framed 'wide' right after a reveal, failing 3 times in one
    script) — 'wide' specifically, not just any non-close_up value."""
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    reveal_idx = next(i for i, s in enumerate(shots) if s.story_beat == "reaction")
    shots[reveal_idx + 1].framing = "wide"
    result = checks.check_shot_rhythm(shots)
    assert not result.passed
    assert "close_up" in result.reason
    print(f"   ok — a reveal followed by a 'wide'-framed shot (the exact "
         f"real-run bug) fails check_shot_rhythm clearly: {result.reason}")


def test_force_close_up_after_every_reveal_corrects_wide_framing():
    """The deterministic auto-repair itself (skills.script._force_close_up_
    after_every_reveal, called from write_story_shots right after the
    model's own output comes back) — proving the fix mechanically corrects
    a model output that got this wrong on EVERY reveal in a script, rather
    than only hoping the strengthened prompt wording is enough."""
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    reveal_idxs = [i for i, s in enumerate(shots) if s.story_beat == "reaction"]
    assert reveal_idxs, "fixture assumption: at least one reveal shot exists"
    for i in reveal_idxs:
        shots[i + 1].framing = "wide"   # simulate the real-run bug on every reveal

    script_mod._force_close_up_after_every_reveal(shots)

    for i in reveal_idxs:
        assert shots[i + 1].framing == "close_up", shots[i + 1].shot_id
    result = checks.check_shot_rhythm(shots)
    assert result.passed, result.reason
    print(f"   ok — _force_close_up_after_every_reveal corrects EVERY "
         f"wrongly-framed reveal follow-up shot ({len(reveal_idxs)} of "
         f"them) deterministically, and check_shot_rhythm passes afterward")


# ============================================== hook_line stale-mapping repair

def test_regenerate_hook_line_stub_produces_a_line_that_passes_check_hook():
    """
    STEP 9 FIXES ROUND 3, FIX 1: skills.script.regenerate_hook_line is the
    narrow repair path for an APPROVED mapping whose persisted hook_line
    predates a check_hook rule (e.g. the 4-opener rule) — see
    story_reel.py's _fix_stale_hook_line for where this is called from.
    Confirms the stub path (shorts.stubs._story_hook_fix, dispatched via
    the HookLineOnly schema) round-trips end to end: a real ask_json call
    under SHORTS_STUB=1 returns a hook_line that passes the CURRENT
    check_hook, with no mutation of the rest of the mapping.
    """
    mapping = ConceptMappingSet(**_mapping_set_kwargs(
        hook_line="Ever click a counter that stubbornly keeps showing zero?"))
    assert not checks.check_hook(mapping.hook_line, technical_term=mapping.technical_term).passed, (
        "fixture assumption: this hook_line must itself fail the current check_hook")
    topic = Topic(id="t3", topic="q", why_it_matters="w", source_section_id="1",
                 difficulty="medium")
    section = Section(section_id="1", title="T", text=SOURCE, start_line=1, end_line=1)

    new_hook = script_mod.regenerate_hook_line(mapping, topic, section, None, SOURCE)

    assert new_hook is not None
    result = checks.check_hook(new_hook, technical_term=mapping.technical_term)
    assert result.passed, result.reason
    print(f"   ok — regenerate_hook_line replaces a stale hook_line "
         f"({mapping.hook_line!r}) with one that passes check_hook "
         f"({new_hook!r})")


def test_regenerate_hook_line_retries_on_a_failing_candidate_then_succeeds():
    """The retry loop itself: the first candidate ask_json returns fails
    check_hook (no opener), the second passes — regenerate_hook_line must
    retry with feedback rather than giving up on attempt 1."""
    topic = Topic(id="t4", topic="q", why_it_matters="w", source_section_id="1",
                 difficulty="medium")
    section = Section(section_id="1", title="T", text=SOURCE, start_line=1, end_line=1)
    mapping = ConceptMappingSet(**_mapping_set_kwargs(
        hook_line="Ever click a counter that stubbornly keeps showing zero?"))

    candidates = iter([
        script_mod.HookLineOnly(hook_line="Your counter never seems to move?"),
        script_mod.HookLineOnly(hook_line="Ever noticed your counter never seems to move?"),
    ])
    calls = []
    original = script_mod.ask_json

    def fake_ask_json(system, user, model_cls, **kw):
        calls.append(1)
        return next(candidates)

    script_mod.ask_json = fake_ask_json
    try:
        new_hook = script_mod.regenerate_hook_line(mapping, topic, section, None, SOURCE)
    finally:
        script_mod.ask_json = original

    assert len(calls) == 2, calls
    assert new_hook == "Ever noticed your counter never seems to move?"
    print(f"   ok — regenerate_hook_line retries a candidate that fails "
         f"check_hook ({calls[0] if calls else '?'} attempt(s) before this "
         f"one) and returns the first one that passes: {new_hook!r}")


def test_regenerate_hook_line_gives_up_after_max_retries():
    """Exhausting MAX_HOOK_FIX_RETRIES on an always-failing candidate must
    return None, not loop forever or raise — same nullable-on-exhaustion
    contract as plan_story_mapping."""
    topic = Topic(id="t5", topic="q", why_it_matters="w", source_section_id="1",
                 difficulty="medium")
    section = Section(section_id="1", title="T", text=SOURCE, start_line=1, end_line=1)
    mapping = ConceptMappingSet(**_mapping_set_kwargs(
        hook_line="Ever click a counter that stubbornly keeps showing zero?"))

    calls = []
    original = script_mod.ask_json

    def always_fails(system, user, model_cls, **kw):
        calls.append(1)
        return script_mod.HookLineOnly(hook_line="Your counter never seems to move?")

    script_mod.ask_json = always_fails
    try:
        new_hook = script_mod.regenerate_hook_line(mapping, topic, section, None, SOURCE)
    finally:
        script_mod.ask_json = original

    assert new_hook is None
    assert len(calls) == script_mod.MAX_HOOK_FIX_RETRIES, calls
    print(f"   ok — an always-failing candidate exhausts "
         f"MAX_HOOK_FIX_RETRIES ({script_mod.MAX_HOOK_FIX_RETRIES}) attempts "
         f"and returns None rather than looping forever")


# ================================================== round 4: new checks fixed

def test_force_mini_scene_endings_to_lesson_line_corrects_paraphrased_ending():
    """
    STEP 9 FIXES ROUND 4, FIX 3: a real run failed check_scene_coverage on
    TWO mini-scenes because their last shot's `line` was a thematically
    similar but NOT verbatim rewrite of the entry's own lesson_line (e.g.
    "My notepad says one, the board still says zero." instead of the
    approved lesson_line). Proves the deterministic auto-repair corrects
    this mechanically rather than only hoping the strengthened prompt
    wording is enough — same pattern as _force_close_up_after_every_reveal.
    """
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    entry = mapping[0]
    last_idx = max(i for i, s in enumerate(shots) if s.concept_ref == entry.concept_rule)
    shots[last_idx].line = "My notepad says one, the board still says zero."
    assert shots[last_idx].line != entry.lesson_line

    mapping_set = ConceptMappingSet(**_mapping_set_kwargs(mapping=mapping))
    script_mod._force_mini_scene_endings_to_lesson_line(shots, mapping_set)

    assert shots[last_idx].line == entry.lesson_line
    result = checks.check_scene_coverage(shots, mapping)
    assert result.passed, result.reason
    print(f"   ok — _force_mini_scene_endings_to_lesson_line corrects a "
         f"paraphrased mini-scene ending back to the approved lesson_line "
         f"({entry.lesson_line!r}), and check_scene_coverage passes afterward")


def test_force_text_card_overlay_from_card_facts_corrects_invented_text():
    """
    STEP 9 FIXES ROUND 4, FIX 2: a real run failed check_text_card_budget
    because a text_card shot's overlay_text was invented wording instead
    of one of the approved card_facts verbatim. Proves the deterministic
    auto-repair reassigns the approved text rather than only hoping the
    strengthened prompt wording is enough."""
    card_facts = ["useState returns [value, setter]", "React batches updates in an event handler"]
    shots = [
        Shot(shot_id="s_card0", characters=[], action="a card appears", kind="text_card",
            overlay_text="a totally made-up fact the model invented"),
        Shot(shot_id="s_card1", characters=[], action="a card appears", kind="text_card",
            overlay_text="another invented sentence, not from card_facts"),
    ]

    script_mod._force_text_card_overlay_from_card_facts(shots, card_facts)

    assert [s.overlay_text for s in shots] == card_facts
    result = checks.check_text_card_budget(shots, card_facts)
    assert result.passed, result.reason
    print(f"   ok — _force_text_card_overlay_from_card_facts replaces invented "
         f"overlay_text with the approved card_facts verbatim, and "
         f"check_text_card_budget passes afterward")


def test_force_text_card_overlay_is_a_noop_on_a_count_mismatch():
    """A text_card COUNT mismatch (model invented or dropped a shot
    entirely) is a structural problem this function must NOT paper over —
    checks.check_text_card_budget still has to catch that case on its
    own."""
    card_facts = ["fact one", "fact two"]
    shots = [Shot(shot_id="s_card0", characters=[], action="a card appears",
                 kind="text_card", overlay_text="invented text")]

    script_mod._force_text_card_overlay_from_card_facts(shots, card_facts)

    assert shots[0].overlay_text == "invented text", "must not touch overlay_text on a count mismatch"
    result = checks.check_text_card_budget(shots, card_facts)
    assert not result.passed
    print(f"   ok — a text_card COUNT mismatch (1 shot for 2 card_facts) is left "
         f"untouched by the auto-repair and still fails check_text_card_budget: "
         f"{result.reason}")


def test_truncate_recap_card_lines_fixes_an_over_length_line():
    """
    STEP 9 FIXES ROUND 4, FIX 4 (RETUNED IN ROUND 7): a real run had a
    recap card_line come back at 6 words ("Only the keeper updates the
    board"), over checks.check_structure_ends's 2-5 word bound. Round 4's
    original flat 5-word cut ("Only the keeper updates the") was itself
    the round-7 bug (a dangling "the") — this now proves the retuned
    truncation lands on a SHORTER, non-dangling cut instead, and still
    leaves an already-compliant line untouched."""
    shots = [Shot(shot_id="s_recap", characters=[], action="a recap card appears", kind="recap",
                 card_lines=["Only the keeper updates the board", "Already fine"])]

    script_mod._truncate_recap_card_lines(shots)

    assert shots[0].card_lines[0] == "Only the keeper updates"
    assert not shots[0].card_lines[0].split()[-1].lower() in script_mod._RECAP_TRUNCATION_DANGLING_WORDS
    assert shots[0].card_lines[1] == "Already fine", "an in-bounds line must not be touched"
    print(f"   ok — _truncate_recap_card_lines truncates an over-length recap "
         f"line to a non-dangling cut ({shots[0].card_lines[0]!r}) rather than "
         f"blindly cutting to exactly {checks.RECAP_LINE_MAX_WORDS} words, and "
         f"leaves an already-compliant line untouched")


def test_truncate_recap_card_lines_never_ends_on_a_dangling_word_real_run_regression():
    """
    STEP 9 FIXES ROUND 7: the ACTUAL bug from a real, APPROVED reel
    (why_plain_variable_fails__story) — round 4's blind first-5-words cut
    shipped "Changing it yourself tells no" and "Only the keeper redraws
    the" into the approved recap, both of which story_audio.spoken_text
    then read aloud as broken sentence fragments (round 4's own docstring
    wrongly assumed recap card_lines were never spoken). Reproduces the
    exact real-run inputs and confirms no output card_line ends on a
    dangling word, and that the resulting spoken_text no longer contains
    either broken fragment.
    """
    shots = [Shot(shot_id="s_recap", characters=[], action="a recap card appears", kind="recap",
                 card_lines=["Changing it yourself tells no one",
                            "No signal means no redraw",
                            "Only the keeper redraws the board"])]

    script_mod._truncate_recap_card_lines(shots)

    for line in shots[0].card_lines:
        last_word = line.split()[-1].strip(".,!?").lower()
        assert last_word not in script_mod._RECAP_TRUNCATION_DANGLING_WORDS, (
            f"{line!r} still ends on a dangling word ({last_word!r})")

    spoken = story_audio.spoken_text(shots[0])
    assert "tells no." not in spoken
    assert "redraws the." not in spoken
    print(f"   ok — the real, previously-shipped-broken recap inputs now "
         f"truncate to {shots[0].card_lines}, none ending on a dangling "
         f"word, and spoken_text ({spoken!r}) no longer contains either "
         f"broken fragment")


def test_force_mini_scene_endings_clears_an_earlier_duplicate_lesson_line():
    """
    STEP 9 FIXES ROUND 7: the OTHER bug from the same real, APPROVED reel
    — two consecutive shots (System, then Rahul) both spoke the exact
    same lesson_line ("Only when the keeper writes it does the board
    change.") because the model had already (correctly) put it on an
    earlier shot in the mini-scene, and round 4's own auto-repair then
    forced it onto the TRUE last shot too, without checking whether an
    earlier one already had it — creating the duplicate rather than
    fixing anything. Confirms the earlier duplicate is now cleared
    (silenced) while the true last shot still ends up with the lesson
    line, exactly as checks.check_scene_coverage requires."""
    lesson = "Only when the keeper writes it does the board change."
    shots = [
        Shot(shot_id="s20", characters=["Rahul"], action="a", concept_ref="rule3",
            line="Rahul finally saw the board change right before him."),
        Shot(shot_id="s21", characters=["System"], action="a", concept_ref="rule3",
            line=lesson),
        Shot(shot_id="s22", characters=["Rahul"], action="a", concept_ref="rule3",
            line="Rahul nodded, understanding at last."),
    ]
    mapping = ConceptMappingSet(**_mapping_set_kwargs(
        mapping=[ConceptMapping(concept_rule="rule3", source_quote="q", actor="System",
                                metaphor_event="e", visible_proof="v", lesson_line=lesson)]))

    script_mod._force_mini_scene_endings_to_lesson_line(shots, mapping)

    assert shots[0].line == "Rahul finally saw the board change right before him."
    assert shots[1].line is None, "the earlier duplicate must be silenced, not left standing"
    assert shots[2].line == lesson, "the TRUE last shot must still carry the lesson_line"
    lines = [s.line for s in shots if s.line]
    assert lines.count(lesson) == 1, "the lesson_line must appear exactly once, not twice"
    print(f"   ok — _force_mini_scene_endings_to_lesson_line clears an earlier "
         f"shot that already duplicated the lesson_line (shot {shots[1].shot_id} "
         f"silenced) rather than leaving two shots speaking the identical "
         f"sentence back to back")


def test_prompt_states_lesson_line_ending_as_verbatim_not_paraphrase():
    """Real-run fix: two mini-scenes ended on a paraphrase of their
    lesson_line instead of the line itself — the prompt stated 'verbatim'
    once but not forcefully enough relative to other now-strengthened
    rules. Regression guard on the stronger wording."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "WORD FOR WORD" in flat
    assert "NOT A PARAPHRASE, NOT A THEMATICALLY SIMILAR LINE" in flat
    print("   ok — SYSTEM_STORY_SHOTS states the mini-scene ending line must "
         "be the lesson_line word for word, not a paraphrase")


def test_prompt_states_text_card_overlay_must_be_verbatim_card_fact():
    """Real-run fix: two text_card shots carried invented overlay_text
    instead of the approved card_facts. Regression guard on the stronger
    wording requiring an exact copy."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "COPIED VERBATIM FROM THE CARD FACTS GIVEN BELOW" in flat
    assert "never a paraphrase, never new wording you compose yourself" in flat
    print("   ok — SYSTEM_STORY_SHOTS states text_card overlay_text must be "
         "copied verbatim from the approved card_facts, never invented")


def test_prompt_states_recap_word_count_forcefully():
    """Real-run fix: a recap card_line came back at 6 words, over the 2-5
    word bound. Regression guard on the stronger wording."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "EXACTLY 2-5 WORDS EACH" in flat
    assert "COUNT THE WORDS IN EACH LINE BEFORE YOU FINALIZE IT" in flat
    print("   ok — SYSTEM_STORY_SHOTS states the recap card_line word count "
         "as an exact, counted bound, not a soft target")


def test_prompt_states_narrator_consecutive_lines_as_a_hard_rule():
    """Real-run fix: shot_07 and shot_08 were both Narrator lines back to
    back outside the one allowed (hook + next shot) pair. Regression
    guard on the stronger, 'no exceptions'-style wording matching the
    reveal->close_up rule's own forcefulness."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "NEVER 2 NARRATOR-SPOKEN LINES BACK TO BACK — NO EXCEPTIONS" in flat
    print("   ok — SYSTEM_STORY_SHOTS states the narrator-consecutive-lines "
         "rule with the same 'no exceptions' forcefulness as the reveal rule")


def test_prompt_names_the_exact_concept_naming_shot_and_forbids_it_elsewhere():
    """
    STEP 9 FIXES ROUND 8: concept_named_once had failed 3 times in a row
    with different symptoms (never spoken, then spoken twice) — the
    user's explicit ask was a single, unmissable instruction naming the
    exact required shot AND an equally explicit ban on the term appearing
    anywhere else, including the recap. Regression guard on that
    stronger wording."""
    flat = " ".join(script_mod.SYSTEM_STORY_SHOTS.split())
    assert "NAMING THE TECHNICAL TERM — EXACTLY ONE SHOT, NEVER ANYWHERE ELSE" in flat
    assert "immediately after the FIRST mapping entry's mini-scene ends" in flat
    assert ("ONLY shot in the ENTIRE SCRIPT — out of every shot you write, in "
           "every mini-scene, the recap, every text_card, and the cta") in flat
    assert "recap lines are read aloud too, not just shown on screen" in flat
    print("   ok — SYSTEM_STORY_SHOTS names the exact required shot for the "
         "concept-naming beat and explicitly forbids the term anywhere else "
         "in the script, including the recap")


def test_stub_fixture_still_passes_shot_count_duration_and_hook_after_round_4():
    """
    Explicit regression guard the user asked for: fixing the 4 NEW round-4
    failures (shot_rhythm/text_card_budget/scene_coverage/structure_ends)
    must not regress the checks that were finally passing (shot_count,
    story_duration, hook) — a repeat of the exact failure pattern this
    whole multi-round fix history has been chasing (fixing one check
    breaks another). Runs the full run_story_graders suite against the
    stub fixture AFTER write_story_shots' own auto-repairs would have run
    (the stub fixture is already compliant, so this also confirms the new
    _force_*/_truncate_* functions are safe no-ops on already-correct
    input, not just correctors of broken input).
    """
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    mapping_set = ConceptMappingSet(**_mapping_set_kwargs(mapping=mapping))

    script_mod._force_close_up_after_every_reveal(shots)
    script_mod._force_mini_scene_endings_to_lesson_line(shots, mapping_set)
    script_mod._force_text_card_overlay_from_card_facts(shots, mapping_set.card_facts)
    script_mod._truncate_recap_card_lines(shots)

    checks_to_run = [
        checks.check_shot_count(shots),
        checks.check_story_duration(shots),
        checks.check_hook(mapping_set.hook_line, technical_term=mapping_set.technical_term),
        checks.check_shot_rhythm(shots),
        checks.check_scene_coverage(shots, mapping),
        checks.check_structure_ends(shots, mapping),
    ]
    failed = [r for r in checks_to_run if not r.passed]
    assert not failed, [(r.name, r.reason) for r in failed]
    print(f"   ok — after round 4's 4 new auto-repairs run (as no-ops on this "
         f"already-compliant fixture), shot_count ({len(shots)} shots), "
         f"story_duration ({sum(s.duration_seconds for s in shots):.1f}s), and "
         f"hook all still pass — no regression from the earlier rounds' fixes")


def test_shot_rhythm_two_narrator_lines_in_a_row_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    # Indices 3 and 4 are NOT the hook (index 0) or the shot right after it —
    # the one exempted pair — so turning both into Narrator-spoken lines must
    # be caught, unlike shots 0-1 which are allowed to both be the Narrator.
    for i in (3, 4):
        shots[i].characters = []
        shots[i].line = f"The Narrator speaks again, shot {i}, right in a row."
    result = checks.check_shot_rhythm(shots)
    assert not result.passed
    print(f"   ok — two Narrator-spoken lines back to back (past the hook "
          f"exception) fails check_shot_rhythm: {result.reason}")


def test_text_card_budget_mismatch_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    extra = [s for s in shots if s.kind == "text_card"][0].model_copy(
        update={"shot_id": "extra_card", "overlay_text": "a fact nobody declared"})
    result = checks.check_text_card_budget(shots + [extra], CARD_FACTS)
    assert not result.passed
    print(f"   ok — a text_card count that doesn't match card_facts fails "
          f"check_text_card_budget: {result.reason}")


def test_character_ratio_too_low_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    for s in shots:
        if s.kind == "scene":
            s.characters = []
    result = checks.check_character_ratio(shots)
    assert not result.passed
    print(f"   ok — scene shots with no characters acting fails "
          f"check_character_ratio: {result.reason}")


def test_no_text_in_action_quoted_line_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    shots[1].action = 'Rahul says "this is broken" out loud'
    result = checks.check_no_text_in_action(shots)
    assert not result.passed
    print(f"   ok — a quoted phrase inside action fails check_no_text_in_action: "
          f"{result.reason}")


def test_grounding_missing_source_quote_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    concept_shot = next(s for s in shots if s.concept_ref)
    concept_shot.source_quote = None
    result = checks.check_shot_grounding(shots, SOURCE)
    assert not result.passed
    print(f"   ok — a concept-carrying shot with no source_quote fails "
          f"check_grounding: {result.reason}")


def test_grounding_fabricated_source_quote_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    concept_shot = next(s for s in shots if s.concept_ref)
    concept_shot.source_quote = "a sentence invented from nowhere, not in the material"
    result = checks.check_shot_grounding(shots, SOURCE)
    assert not result.passed
    print(f"   ok — a source_quote not actually in the material fails "
          f"check_grounding: {result.reason}")


def test_scene_coverage_thin_mini_scene_fails():
    shots, mapping = _good_shots_and_mapping()
    thinned = [s for s in shots if s.concept_ref != mapping[0].concept_rule][:5] + [
        s for s in shots if s.concept_ref == mapping[0].concept_rule][:2]
    result = checks.check_scene_coverage(thinned, mapping)
    assert not result.passed
    print(f"   ok — a mapping entry dramatized by fewer than 3 shots fails "
          f"check_scene_coverage: {result.reason}")


def test_scene_coverage_wrong_ending_line_fails():
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    last_of_first = [s for s in shots if s.concept_ref == mapping[0].concept_rule][-1]
    last_of_first.line = "This is not the lesson line at all."
    result = checks.check_scene_coverage(shots, mapping)
    assert not result.passed
    print(f"   ok — a mini-scene that doesn't end on its own lesson_line fails "
          f"check_scene_coverage: {result.reason}")


def test_concept_named_once_missing_fails():
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    named = next(s for s in shots if s.line and TECH_TERM.lower() in s.line.lower())
    named.line = "And that whiteboard? That's the answer."
    result = checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM)
    assert not result.passed
    print(f"   ok — a script that never speaks the technical term fails "
          f"check_concept_named_once: {result.reason}")


def test_concept_named_once_twice_fails():
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    last_shot = [s for s in shots if s.concept_ref == mapping[-1].concept_rule][-1]
    last_shot.line = f"So that's {TECH_TERM} for you, plain and simple."
    result = checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM)
    assert not result.passed
    print(f"   ok — the technical term spoken twice fails check_concept_named_once: "
          f"{result.reason}")


def test_concept_named_by_a_character_fails():
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    named = next(s for s in shots if s.line and TECH_TERM.lower() in s.line.lower())
    named.characters = ["Rahul"]
    result = checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM)
    assert not result.passed
    print(f"   ok — the technical term spoken by a character, not the Narrator, "
          f"fails check_concept_named_once: {result.reason}")


def test_concept_named_once_ignores_a_compound_word_containing_the_term():
    """
    STEP 9 FIXES ROUND 8: a real run failed concept_named_once as "spoken
    twice" — one hit was the real naming shot, the other was a DIFFERENT
    shot's line that legitimately said "useState" (source-material code
    syntax). "state" is a plain substring of "useState" (and of
    "statement"), but neither is the Narrator naming the concept again.
    The old `term in line.lower()` check could not tell those apart; the
    new \\bword\\b regex must. Uses "react"/"reactive" here — the exact
    same substring relationship as "state"/"useState", but with this
    file's own TECH_TERM ("React")."""
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    other = next(s for s in shots if s.line and TECH_TERM.lower() not in s.line.lower())
    other.characters = []
    other.line = "That reactive little notebook never lies."
    result = checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM)
    assert result.passed, result.reason
    print(f"   ok — a shot saying 'reactive' (contains {TECH_TERM.lower()!r} as a "
         f"substring, but is a different word) does NOT count as a second naming "
         f"of the technical term")


def test_concept_named_once_catches_the_term_hidden_in_a_recap_card_line():
    """
    STEP 9 FIXES ROUND 8: the check used to read ONLY `shot.line` — a
    recap shot's `card_lines` were invisible to it, even though
    story_audio.spoken_text genuinely reads them aloud (the same round-7
    lesson). A term hidden in a recap card_line was a SILENT second
    naming: never caught by this check, but audibly spoken twice in the
    real narration. Confirms it is now caught."""
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    recap = next(s for s in shots if s.kind == "recap")
    recap.card_lines = [f"The {TECH_TERM.lower()} lives on", "Something else entirely"]
    result = checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM)
    assert not result.passed
    assert recap.shot_id in result.reason
    print(f"   ok — the technical term hidden in a recap card_line is now caught "
         f"as a second (spoken-aloud) naming: {result.reason}")


def test_concept_named_once_catches_the_term_hidden_in_a_text_card_overlay():
    """Same blind spot, the text_card/cta half: overlay_text is read aloud
    by the Narrator (story_audio.spoken_text) but was never scanned by
    this check either."""
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    card = next(s for s in shots if s.kind == "text_card")
    card.overlay_text = f"A fact that happens to mention {TECH_TERM.lower()} directly"
    result = checks.check_concept_named_once(shots, mapping, technical_term=TECH_TERM)
    assert not result.passed
    assert card.shot_id in result.reason
    print(f"   ok — the technical term hidden in a text_card's overlay_text is now "
         f"caught as a second naming: {result.reason}")


def test_key_prop_invalid_fails():
    shots, _ = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    shots[1].key_prop = "a prop nobody declared"
    result = checks.check_key_prop_valid(shots, PROPS)
    assert not result.passed
    print(f"   ok — a key_prop outside the declared props fails "
          f"check_key_prop_valid: {result.reason}")


def test_structure_ends_wrong_kind_fails():
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    shots[-1].kind = "scene"
    result = checks.check_structure_ends(shots, mapping)
    assert not result.passed
    print(f"   ok — a last shot that isn't kind='cta' fails check_structure_ends: "
          f"{result.reason}")


def test_structure_ends_bad_recap_length_fails():
    shots, mapping = _good_shots_and_mapping()
    shots = _copy_shots(shots)
    shots[-2].card_lines = ["only one entry here"]
    result = checks.check_structure_ends(shots, mapping)
    assert not result.passed
    print(f"   ok — a recap with the wrong number of card_lines fails "
          f"check_structure_ends: {result.reason}")


# ==========================================================================
# FULL STUB END-TO-END RUN
# ==========================================================================

def test_full_story_path_runs_end_to_end_under_stub(tmp_path=None):
    """
    SHORTS_STUB=1, real plumbing: parse a tiny doc, run plan_story_mapping
    (including the judge gate) and write_story_shots, run run_story_graders +
    the (stubbed) metaphor judge via skills.audit.audit_story, and persist the
    finished StoryScript to output/<short_id>.story.json — exactly the shape
    run.py's build_one_story/build_story_shorts produce, exercised directly
    here so this test does not depend on run.py's CLI argument parsing.
    """
    import tempfile
    from pathlib import Path
    from shorts.skills.script import write_story_shots
    from shorts.skills.understanding import understanding_for
    from shorts.skills.audit import audit_story

    doc = (
        "# Stub Session\n\n"
        "## 1.1 Why the count never updates\n"
        f"{SOURCE}\n\n"
        "## 1.2 How useState creates and updates state\n"
        f"{SOURCE}\n"
    )
    with tempfile.TemporaryDirectory() as d:
        doc_path = Path(d) / "stub_doc.md"
        doc_path.write_text(doc, encoding="utf-8")
        sections = parse_markdown(str(doc_path))

    section = sections[1]
    topic = Topic(id="stub_e2e", topic="How does useState remember a value?",
                 why_it_matters="test", source_section_id=section.section_id,
                 difficulty="medium")

    understanding = understanding_for(section, source_text=section.text)
    mapping = plan_story_mapping(topic, section, understanding=understanding,
                                 source_text=section.text)
    assert mapping is not None, "stub mapping must pass check_mapping/check_hook/judge"

    story = write_story_shots(mapping, topic, section, understanding=understanding,
                             source_text=section.text, session_id="s1")
    assert 24 <= len(story.shots) <= 30, len(story.shots)

    results, report = audit_story(story, section.text, technical_term=story.technical_term)
    failed = [r for r in results if not r.passed]
    assert not failed, [(r.name, r.reason) for r in failed]
    assert report is not None and report.passed, report

    concept_named = next(r for r in results if r.name == "concept_named_once")
    assert "skipped" not in concept_named.reason, concept_named.reason

    out_path = config.OUTPUT_DIR / f"{story.short_id}.story.json"
    out_path.write_text(story.model_dump_json(indent=2), encoding="utf-8")
    assert out_path.exists()
    loaded = out_path.read_text(encoding="utf-8")
    assert '"kind"' in loaded and '"recap"' in loaded and '"cta"' in loaded

    print(f"   ok — full story path (mapping -> judge gate -> shots -> "
          f"run_story_graders -> metaphor judge) runs end to end under "
          f"SHORTS_STUB=1 and writes {out_path} ({len(story.shots)} shots, "
          f"{story.estimated_seconds}s)")


# ==========================================================================
# STEP 3 PART 0 #3 — audit_story() must GATE build_one_story, not just run
# ==========================================================================

def _stub_sections():
    import tempfile
    from pathlib import Path
    doc = (
        "# Stub Session\n\n"
        "## 1.1 Why the count never updates\n"
        f"{SOURCE}\n\n"
        "## 1.2 How useState creates and updates state\n"
        f"{SOURCE}\n"
    )
    with tempfile.TemporaryDirectory() as d:
        doc_path = Path(d) / "stub_doc.md"
        doc_path.write_text(doc, encoding="utf-8")
        return parse_markdown(str(doc_path))


def test_build_one_story_returns_story_when_the_judge_passes():
    from shorts import run as run_mod
    sections = _stub_sections()
    section = sections[1]
    topic = Topic(id="stub_gate_pass", topic="How does useState remember a value?",
                 why_it_matters="test", source_section_id=section.section_id,
                 difficulty="medium")
    story = run_mod.build_one_story(topic, section, "s1", sections, yes=True)
    assert story is not None
    out_path = config.OUTPUT_DIR / f"{story.short_id}.story.json"
    print(f"   ok — build_one_story returns the StoryScript when every gate "
          f"(mapping checks, mapping judge, run_story_graders, shots judge) "
          f"passes (would be persisted to {out_path})")


def test_build_story_shorts_never_persists_a_judge_rejected_reel():
    """
    RESTYLE_TO_STORY_REELS.md Step 3 Part 0 #3's own fix: audit_story() used
    to run and print REJECT without build_one_story actually acting on it —
    `return story` was unconditional, so a rejected reel still reached
    build_story_shorts and got persisted like a passing one. Monkeypatching
    skills.audit.judge_story_metaphors to always say 'no' and driving the
    real persistence path (build_story_shorts, not just build_one_story)
    proves the gate now actually stops *.story.json from being written — the
    same way plan_story_mapping's own mapping-stage judge gate is proven in
    test_judge_gate_retries_then_gives_up_when_unfaithful above.
    """
    import shorts.skills.audit as audit_mod
    from shorts import run as run_mod
    sections = _stub_sections()
    section = sections[1]
    topic = Topic(id="stub_gate_reject", topic="How does useState remember a value?",
                 why_it_matters="test", source_section_id=section.section_id,
                 difficulty="medium")
    out_path = config.OUTPUT_DIR / f"{topic.id}.story.json"
    out_path.unlink(missing_ok=True)   # in case a previous run left one behind

    original = audit_mod.judge_story_metaphors
    audit_mod.judge_story_metaphors = lambda mapping: StoryEvalReport(verdicts=[
        MetaphorVerdict(concept_rule=m.concept_rule, faithful=False,
                        problem="stub-forced rejection") for m in mapping])
    try:
        stories = run_mod.build_story_shorts([topic], sections, "s2", yes=True)
    finally:
        audit_mod.judge_story_metaphors = original

    assert stories == [], stories
    assert not out_path.exists(), (
        "a reel the final judge rejected must never reach *.story.json")
    print("   ok — build_story_shorts persists NO *.story.json for a reel "
          "the FINAL judge rejects — the gate stops the file being written, "
          "not just prints REJECT")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} story-mode hardening tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL STORY-MODE HARDENING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
