"""
Offline, deterministic tests for the shared evidence-scoping fix (Step 4) and
its integration into the workflow script path, the review judge, and
understanding_for's script guidance.

THE BUG THIS GUARDS AGAINST: a topic's citable evidence used to be exactly one
heading-delimited Section's raw text. A concept written as a one-line
definition under its own heading, elaborated under separate sibling headings
("## Example", "## How It Works", "## Script"), was graded as too thin to cite
even though the concept, read as the small cluster it actually is, plainly was
not — see parse.group_sections_by_concept / parse.evidence_text for the fix.

THE INTEGRATION THIS FILE ALSO COVERS: write_script/check_section_richness/
check_source_quotes/check_answers_its_section agreeing on one resolved
evidence pool was step one. The remaining consumers of "what may this topic
cite" — workflow.py's advance() script branch, the review judge
(server._review_judge/judge_script), and understanding_for (the guidance
write_script is handed) — must resolve and be checked against the SAME pool,
or the fix only moves the inconsistency one layer down.

No API key, no network, no cost: every test here is pure string processing
(parse.py, checks.py) or a monkeypatched LLM call (ask_json /
write_script_for_workflow / plan_strategy_for_workflow are never really
called). This does NOT test whether generated scripts are good —
evals/cases.yaml is for that and costs real API calls.

    python -m shorts.evidence_grouping_test
"""
import tempfile
from pathlib import Path

from .parse import (parse_markdown, find_section, group_sections_by_concept,
                    evidence_text, evidence_section_ids)
from .schema import (Section, Script, Beat, Topic, SectionUnderstanding, ExamplePlan,
                     QuestionWorkflow, QuestionApproval, QuestionFraming,
                     TeachingApproach, TeachingApproachApproval, QuestionSelection,
                     SelectionReason)
from . import checks, config
from .skills import script as script_module
from .skills import understanding as understanding_module
from . import workflow as workflow_module
from . import server as server_module

REACT_PROPS_DOC = "output/uploads/db8cbe8790f9.md"


def _section(section_id, title, text) -> Section:
    return Section(section_id=section_id, title=title, text=text,
                   start_line=1, end_line=1)


# ---------------------------------------------------------------- React Props

def test_react_props_alone_is_still_too_thin_on_its_own():
    """
    LOCKS IN THE ORIGINAL BUG AS A FIXTURE. check_section_richness itself is
    UNCHANGED — the fix is entirely in what text callers resolve and pass to
    it — so grading the bare section still reports exactly the failure the
    investigation found: 2 distinct citable sentences, need 3.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    result = checks.check_section_richness(section.text)
    assert not result.passed, "expected the bare definition section to still read as thin"
    assert result.details["spans"] == 2
    assert result.details["needed"] == 3


def test_react_props_evidence_groups_definition_with_its_elaboration():
    """
    "Example", "How It Works" and "Script" are generic elaboration roles (see
    parse._ELABORATION_TITLES) immediately following "What are Props?", so
    they all group with it — in document order, none dropped.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    ids = evidence_section_ids(sections, "what_are_props")
    assert ids == ["what_are_props", "example", "how_it_works", "script"], ids

    # Symmetric: asking from any member of the group returns the same cluster.
    assert evidence_section_ids(sections, "example") == ids
    assert evidence_section_ids(sections, "how_it_works") == ids
    assert evidence_section_ids(sections, "script") == ids


def test_react_props_resolved_evidence_passes_richness():
    """
    THE FIX, END TO END FOR THE REPORTED CASE. The resolved evidence pool for
    "what_are_props" now holds enough distinct citable sentences for a
    4-beat script — MIN_ANSWERS is untouched; what changed is what text the
    check is handed.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    text = evidence_text(sections, "what_are_props")
    result = checks.check_section_richness(text)
    assert result.passed, result.reason
    assert result.details["spans"] >= result.details["needed"]


def _react_props_script() -> Script:
    """
    A script whose beats cite ACROSS the four sections — the shape that was
    previously impossible to write without check_answers_its_section (every
    beat must quote its "own" section) rejecting it. Quotes copied verbatim
    from the real spans (see checks._citable_spans output on this document).
    """
    return Script(short_id="what_are_props", question="What are props?", beats=[
        Beat(speaker="interviewer", line="What are props?",
            on_screen="What are props?", visual_ref="v0"),
        Beat(speaker="student",
            line="Props are values passed from a parent to a child.",
            on_screen="parent -> child", visual_ref="v1",
            source_quote="Props are values passed from a parent component to a child component."),
        Beat(speaker="student",
            line="Welcome receives the name through props.name.",
            on_screen="props.name", visual_ref="v2",
            source_quote='* `Welcome` receives it through `props.name`.'),
        Beat(speaker="student",
            line="And that's how the same component can show different data.",
            on_screen="reuse", visual_ref="v3",
            source_quote="They help us reuse the same component with different data."),
    ])


def test_grounding_graders_pass_on_resolved_evidence_but_not_on_bare_section():
    """
    CONSISTENCY, THE CORE REQUIREMENT. The same script — one beat quoting the
    definition section, one quoting the "How It Works" bullet — is graded
    correctly (both pass) against the resolved evidence pool, and would have
    been WRONGLY rejected as citing "elsewhere in the document" against the
    bare section alone. This is check_source_quotes and
    check_answers_its_section (the "on_topic" grounding grader) agreeing with
    check_section_richness about what text this topic may draw on.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    bare = find_section(sections, "what_are_props").text
    resolved = evidence_text(sections, "what_are_props")
    script = _react_props_script()

    quotes_on_resolved = checks.check_source_quotes(script, resolved)
    on_topic_resolved = checks.check_answers_its_section(script, resolved)
    assert quotes_on_resolved.passed, quotes_on_resolved.reason
    assert on_topic_resolved.passed, on_topic_resolved.reason

    on_topic_bare = checks.check_answers_its_section(script, bare)
    assert not on_topic_bare.passed, (
        "expected the How It Works beat to read as a stray against the bare "
        "section alone — this is the failure mode the fix closes")


def test_write_script_prompt_uses_resolved_evidence_not_narrow_section(monkeypatch):
    """
    THE GENERATION PROMPT ITSELF, not just the graders. write_script's
    `source_text` override must be what actually lands in the "THE SECTION
    THIS SHORT IS FILED UNDER" block the model is shown — otherwise richness
    and grounding could agree on a wider pool the writer never sees.

    NO LLM CALL: ask_json is monkeypatched to capture the prompt and hand
    back a minimal valid Script, so this is free and network-free.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    resolved = evidence_text(sections, "what_are_props")
    topic = Topic(id="what_are_props", topic="What are props?",
                 why_it_matters="foundational", source_section_id="what_are_props",
                 difficulty="easy")

    captured = {}

    def fake_ask_json(system, user, model_cls, **kwargs):
        captured["user"] = user
        return Script(short_id=topic.id, question=topic.topic, beats=[
            Beat(speaker="interviewer", line=topic.topic, on_screen="", visual_ref="v0"),
        ])

    monkeypatch.setattr(script_module, "ask_json", fake_ask_json)

    script_module.write_script(topic, section, source_text=resolved)
    assert "Welcome" in captured["user"] and "props.name" in captured["user"], (
        "expected the How It Works bullet to appear in the prompt when "
        "source_text is the resolved evidence pool")
    assert "Basic flow: Parent passes data" in captured["user"]

    script_module.write_script(topic, section)          # source_text omitted
    assert "Basic flow: Parent passes data" not in captured["user"], (
        "omitting source_text must fall back to byte-identical section.text "
        "behaviour — no elaboration content should appear")


# ------------------------------------------------- unrelated adjacent sections

def test_unrelated_adjacent_thin_sections_are_not_merged():
    """
    THE GUARDRAIL. Two thin, adjacent, concept-naming sections must never be
    pooled just because both are short — that is exactly the cross-topic
    contamination check_answers_its_section exists to stop. Neither title is
    a recognised elaboration role, so each stays its own group.
    """
    sections = [
        _section("what_are_props", "What are Props?",
                "Props are values passed from a parent to a child."),
        _section("what_is_state", "What is State?",
                "State is data a component owns and can change over time."),
    ]
    groups = group_sections_by_concept(sections)
    assert groups["what_are_props"] == [sections[0]]
    assert groups["what_is_state"] == [sections[1]]

    # Each is still individually too thin — proving no merge inflated either.
    assert not checks.check_section_richness(evidence_text(sections, "what_are_props")).passed
    assert not checks.check_section_richness(evidence_text(sections, "what_is_state")).passed


def test_elaboration_attaches_only_to_the_concept_right_before_it():
    """
    A run of Concept / Example / Concept / Example must not let the second
    Example bleed backward onto the first concept, or the first Example
    forward onto the second concept — each elaboration attaches to its own
    immediately preceding concept only.
    """
    sections = [
        _section("concept_a", "What are Props?", "Props pass data down."),
        _section("example_a", "Example", "function A() { return <B x={1} />; }"),
        _section("concept_b", "What is State?", "State is owned data."),
        _section("example_b", "Example", "const [s, setS] = useState(0);"),
    ]
    groups = group_sections_by_concept(sections)
    assert groups["concept_a"] == sections[0:2]
    assert groups["concept_b"] == sections[2:4]
    assert evidence_text(sections, "concept_a") == \
        sections[0].text + "\n\n" + sections[1].text
    assert "useState" not in evidence_text(sections, "concept_a")
    assert "return <B" not in evidence_text(sections, "concept_b")


def test_leading_elaboration_titled_section_stands_alone():
    """A document that (unusually) opens with an "Example" heading has nothing
    to attach to — it must not be dropped, just left as its own group."""
    sections = [_section("example", "Example", "console.log(1);")]
    groups = group_sections_by_concept(sections)
    assert groups["example"] == sections
    assert evidence_text(sections, "example") == sections[0].text


# ------------------------------------------------------- existing content docs

EXISTING_DOCS = [
    "content/hash_table_basics.md",
    "content/linked_list_basics.md",
    "content/css_specificity.md",
    "content/stack_data_structure.md",
    "content/session_18_paging.md",
    "content/react_usestate_basics.md",
    "content/react_state_repro.md",
    "content/react_state_repro_thin.md",
]


def test_existing_content_docs_are_not_regrouped():
    """
    NO SURPRISE MERGES ON MATERIAL THAT ALREADY PASSES. Every section in
    every existing content doc already earns its own richness pass by being
    self-contained (definition + mechanism + example bundled under one
    heading) — none of their headings are elaboration roles, so
    group_sections_by_concept must leave every one of them a singleton group,
    and evidence_text must be byte-identical to plain section.text.
    """
    for path in EXISTING_DOCS:
        sections = parse_markdown(path)
        groups = group_sections_by_concept(sections)
        for s in sections:
            assert groups[s.section_id] == [s], (
                f"{path}: {s.section_id} ({s.title!r}) was unexpectedly grouped "
                f"with a neighbour")
            assert evidence_text(sections, s.section_id) == s.text, (
                f"{path}: {s.section_id} evidence_text drifted from section.text")


def test_existing_content_docs_richness_verdicts_unchanged():
    """
    Every section that already passed check_section_richness on its own text
    still passes it on evidence_text — a no-op fix for material that does not
    use the thin-elaboration authoring pattern.
    """
    for path in EXISTING_DOCS:
        sections = parse_markdown(path)
        for s in sections:
            before = checks.check_section_richness(s.text)
            after = checks.check_section_richness(evidence_text(sections, s.section_id))
            assert before.passed == after.passed, f"{path}: {s.section_id} verdict changed"
            assert before.details == after.details, f"{path}: {s.section_id} span count changed"


# ------------------------------------------------- understanding_for guidance

def _clear_understanding_cache():
    """understanding_for's cache is module-level and keyed by hash(text), so
    tests that hand it canned ask_json responses must not leak into each
    other via a stale cache entry."""
    understanding_module._CACHE.clear()
    understanding_module._INFLIGHT.clear()


def _canned_understanding(section_id: str) -> SectionUnderstanding:
    """An understanding whose example_plan names a literal ("props.name")
    that exists in the React Props document's "How It Works"/"Example"/
    "Script" sections but NOT in "What are Props?" alone — the exact shape
    check_example_plan's grounding check is built to accept or reject."""
    return SectionUnderstanding(
        section_id=section_id, core_idea="Props pass data from parent to child.",
        example_plan=ExamplePlan(need="required", example="props.name",
                                 learner_takeaway="the child reads the value it was given"),
    )


def test_understanding_reads_and_verifies_against_resolved_evidence():
    """
    ITEM 3: TEACHING GUIDANCE RECEIVES THE RESOLVED EVIDENCE. understand()
    must both READ from `source_text` (not just section.text) and VERIFY its
    own example_plan/teaching_sequence/confusion_plan/hook_plan against that
    SAME text — otherwise a plan honestly grounded in a sibling section (the
    common shape here) is wrongly quarantined by check_example_plan for
    citing something "outside the section" that is, in fact, inside this
    topic's real evidence pool.
    """
    _clear_understanding_cache()
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    resolved = evidence_text(sections, "what_are_props")

    def fake_ask_json(system, user, model_cls, **kwargs):
        return _canned_understanding(section.section_id)

    old_ask_json = understanding_module.ask_json
    understanding_module.ask_json = fake_ask_json
    try:
        with_resolved = understanding_module.understand(section, source_text=resolved)
        _clear_understanding_cache()
        with_bare = understanding_module.understand(section)   # source_text omitted
    finally:
        understanding_module.ask_json = old_ask_json

    assert with_resolved.example_plan is not None, (
        "expected the example plan to survive grounding against the resolved "
        "evidence pool")
    assert with_bare.example_plan is None, (
        "expected the SAME plan to be dropped against the bare section alone "
        "— proves this test is actually exercising the grounding check, not "
        "a check that always passes")


def test_understanding_for_shares_one_reading_across_an_evidence_group():
    """
    THE COST-SHARING GUARANTEE, EXTENDED. understanding_for has always shared
    one reading across every topic filed under one section; the cache key
    change (hash(source_text) instead of hash(section.text)) extends that to
    every topic filed under any MEMBER of one evidence group — two different
    Section objects ("what_are_props", "how_it_works") resolving to the same
    merged text must hit the cache on the second call, not pay for a second
    reading.
    """
    _clear_understanding_cache()
    sections = parse_markdown(REACT_PROPS_DOC)
    resolved = evidence_text(sections, "what_are_props")
    assert resolved == evidence_text(sections, "how_it_works")   # same group

    calls = []

    def fake_ask_json(system, user, model_cls, **kwargs):
        calls.append(1)
        return _canned_understanding("x")

    old_ask_json = understanding_module.ask_json
    understanding_module.ask_json = fake_ask_json
    try:
        a = understanding_module.understanding_for(
            find_section(sections, "what_are_props"), source_text=resolved, quiet=True)
        b = understanding_module.understanding_for(
            find_section(sections, "how_it_works"), source_text=resolved, quiet=True)
    finally:
        understanding_module.ask_json = old_ask_json
        _clear_understanding_cache()

    assert len(calls) == 1, f"expected one shared reading, ask_json was called {len(calls)} times"
    assert a is b


def test_understanding_for_singleton_section_cache_key_unchanged():
    """
    EXISTING BEHAVIOUR PRESERVED (item 5). For a section with no elaborating
    siblings, source_text defaults to section.text, so the cache key —
    hash(text) — is exactly what it was before this integration.
    """
    _clear_understanding_cache()
    sections = parse_markdown("content/hash_table_basics.md")
    section = find_section(sections, "6.1")
    assert evidence_text(sections, "6.1") == section.text

    calls = []

    def fake_ask_json(system, user, model_cls, **kwargs):
        calls.append(1)
        return SectionUnderstanding(section_id=section.section_id, core_idea="x")

    old_ask_json = understanding_module.ask_json
    understanding_module.ask_json = fake_ask_json
    try:
        a = understanding_module.understanding_for(section, quiet=True)   # no source_text
        b = understanding_module.understanding_for(
            section, source_text=evidence_text(sections, "6.1"), quiet=True)
    finally:
        understanding_module.ask_json = old_ask_json
        _clear_understanding_cache()

    assert len(calls) == 1, "explicit source_text=section.text must hit the same cache entry"
    assert a is b


# ------------------------------------------------------- workflow script path

def _ready_workflow(section: Section, section_group_ids=None) -> QuestionWorkflow:
    """
    A QuestionWorkflow already past every human gate write_script_for_workflow
    checks (approved question, framing, an APPROVED teaching approach), with
    no script yet — built directly from the schema rather than through
    select.py/review.py, since every field advance()'s script branch reads is
    a plain, gate-checked property (approved_topic, approved_teaching_approach)
    computed from the statuses set here.
    """
    topic = Topic(id=f"t_{section.section_id}", topic="What are props?",
                 why_it_matters="foundational", source_section_id=section.section_id,
                 difficulty="easy")
    selection = QuestionSelection(
        topic=topic, source_title=section.title,
        reasons=[SelectionReason(category="importance", explanation="central idea")])
    return QuestionWorkflow(
        selection=selection,
        question_approval=QuestionApproval(status="approved"),
        framing=QuestionFraming(source_question=topic.topic, teaching_question=topic.topic),
        teaching_approach=TeachingApproach(primary="direct_explanation"),
        teaching_approach_approval=TeachingApproachApproval(status="approved"),
    )


def test_workflow_advance_script_branch_uses_resolved_evidence():
    """
    ITEM 1: THE WORKFLOW SCRIPT PATH. advance()'s `if workflow.script is None`
    branch must call write_script_for_workflow with the SAME resolved
    evidence pool understanding_for was given — not section.text.

    write_script_for_workflow and plan_strategy_for_workflow (Step 10, the
    very next branch advance() would otherwise fall into once a script
    exists) are monkeypatched so this makes no LLM call and never reaches
    visual planning.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    resolved = evidence_text(sections, "what_are_props")
    wf = _ready_workflow(section)

    captured = {}

    def fake_write_script_for_workflow(workflow, sec, **kwargs):
        captured["source_text"] = kwargs.get("source_text")
        stub_script = Script(short_id=workflow.selection.topic.id, question="What are props?",
                             beats=[Beat(speaker="interviewer", line="q",
                                        on_screen="", visual_ref="v0")])
        return workflow.model_copy(update={"script": stub_script})

    def fake_plan_strategy_for_workflow(workflow, sec, **kwargs):
        return workflow   # visual planning is out of scope for this test

    old_write = workflow_module.write_script_for_workflow
    old_plan = workflow_module.plan_strategy_for_workflow
    workflow_module.write_script_for_workflow = fake_write_script_for_workflow
    workflow_module.plan_strategy_for_workflow = fake_plan_strategy_for_workflow
    try:
        progress = workflow_module.advance(wf, sections, source_text=resolved)
    finally:
        workflow_module.write_script_for_workflow = old_write
        workflow_module.plan_strategy_for_workflow = old_plan

    assert captured["source_text"] == resolved
    assert progress.workflow.script is not None
    assert progress.status != "script_failed"


def test_workflow_advance_omits_source_text_by_default():
    """BACKWARD COMPATIBILITY: a caller of advance() that does not resolve
    evidence (every caller before this integration) gets source_text=None
    forwarded, and write_script_for_workflow's own default (section.text)
    applies — byte-identical to before this change."""
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    wf = _ready_workflow(section)

    captured = {}

    def fake_write_script_for_workflow(workflow, sec, **kwargs):
        captured["source_text"] = kwargs.get("source_text")
        stub_script = Script(short_id=workflow.selection.topic.id, question="q",
                             beats=[Beat(speaker="interviewer", line="q",
                                        on_screen="", visual_ref="v0")])
        return workflow.model_copy(update={"script": stub_script})

    def fake_plan_strategy_for_workflow(workflow, sec, **kwargs):
        return workflow

    old_write = workflow_module.write_script_for_workflow
    old_plan = workflow_module.plan_strategy_for_workflow
    workflow_module.write_script_for_workflow = fake_write_script_for_workflow
    workflow_module.plan_strategy_for_workflow = fake_plan_strategy_for_workflow
    try:
        workflow_module.advance(wf, sections)   # source_text omitted entirely
    finally:
        workflow_module.write_script_for_workflow = old_write
        workflow_module.plan_strategy_for_workflow = old_plan

    assert captured["source_text"] is None


def test_advance_many_resolves_evidence_once_per_section_and_shares_it():
    """
    advance_many computes source_text lazily, once per section per call —
    same contract as its existing `understanding` sharing — and hands the
    SAME value to understanding_for and to advance() for every workflow
    filed under that section, so the two never disagree about "this section".
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    resolved = evidence_text(sections, "what_are_props")
    wf = _ready_workflow(section)

    _clear_understanding_cache()
    captured_understanding_source = []
    captured_advance_source = []

    def fake_ask_json(system, user, model_cls, **kwargs):
        return _canned_understanding(section.section_id)

    def fake_write_script_for_workflow(workflow, sec, **kwargs):
        captured_advance_source.append(kwargs.get("source_text"))
        stub_script = Script(short_id=workflow.selection.topic.id, question="q",
                             beats=[Beat(speaker="interviewer", line="q",
                                        on_screen="", visual_ref="v0")])
        return workflow.model_copy(update={"script": stub_script})

    def fake_plan_strategy_for_workflow(workflow, sec, **kwargs):
        return workflow

    old_ask_json = understanding_module.ask_json
    old_write = workflow_module.write_script_for_workflow
    old_plan = workflow_module.plan_strategy_for_workflow
    understanding_module.ask_json = fake_ask_json
    workflow_module.write_script_for_workflow = fake_write_script_for_workflow
    workflow_module.plan_strategy_for_workflow = fake_plan_strategy_for_workflow
    try:
        [progress] = workflow_module.advance_many([wf], sections)
    finally:
        understanding_module.ask_json = old_ask_json
        workflow_module.write_script_for_workflow = old_write
        workflow_module.plan_strategy_for_workflow = old_plan
        _clear_understanding_cache()

    assert captured_advance_source == [resolved]
    assert progress.workflow.script is not None


# ------------------------------------------------------------- review judge

def test_review_judge_uses_resolved_evidence_not_bare_section():
    """
    ITEM 2: THE REVIEW JUDGE. server._review_judge must hand judge_script the
    SAME resolved evidence the code graders just passed the script against —
    otherwise a script correctly grounded in a sibling section ("How It
    Works") passes every code grader and then gets marked unfaithful by the
    judge for citing material it, from the judge's point of view, was never
    shown.
    """
    sections = parse_markdown(REACT_PROPS_DOC)
    section = find_section(sections, "what_are_props")
    resolved = evidence_text(sections, "what_are_props")
    script = _react_props_script()
    # The specific claim under test is what TEXT the judge is handed, not
    # whether this fixture clears every code grader (dialogue_shape/timing
    # need a full 4-5 beat script — see the other tests for that) — so the
    # gating "all_passed(results)" is satisfied directly rather than by
    # building a fixture that would pass the entire grader suite.
    results = [checks.GraderResult("source_quotes", True, "ok"),
              checks.GraderResult("on_topic", True, "ok")]
    assert checks.check_source_quotes(script, resolved).passed
    assert checks.check_answers_its_section(script, resolved).passed

    captured = {}

    def fake_judge_script(scr, source_text, unit=None):
        captured["source_text"] = source_text
        from .schema import EvalReport
        return EvalReport(faithfulness=5, clarity=5, pace=5, diagram_correct=True,
                          question_answered=True, problems=[])

    old_judge = server_module.judge_script
    old_flag = server_module.config.JUDGE_AT_REVIEW
    server_module.judge_script = fake_judge_script
    server_module.config.JUDGE_AT_REVIEW = True
    try:
        verdict = server_module._review_judge(script, section, results, source_text=resolved)
    finally:
        server_module.judge_script = old_judge
        server_module.config.JUDGE_AT_REVIEW = old_flag

    assert captured["source_text"] == resolved
    assert verdict is not None and verdict["passed"]


def test_review_judge_defaults_to_section_text_when_source_text_omitted():
    """BACKWARD COMPATIBILITY: every existing caller of _review_judge that
    does not resolve evidence keeps grading against section.text exactly as
    before."""
    sections = parse_markdown("content/hash_table_basics.md")
    section = find_section(sections, "6.1")
    script = Script(short_id="x", question="q", beats=[
        Beat(speaker="interviewer", line="q", on_screen="", visual_ref="v0"),
        Beat(speaker="student", line="a", on_screen="", visual_ref="v1", source_quote="a"),
    ])
    results = [checks.GraderResult("dummy", True, "ok")]

    captured = {}

    def fake_judge_script(scr, source_text, unit=None):
        captured["source_text"] = source_text
        from .schema import EvalReport
        return EvalReport(faithfulness=5, clarity=5, pace=5, diagram_correct=True,
                          question_answered=True, problems=[])

    old_judge = server_module.judge_script
    old_flag = server_module.config.JUDGE_AT_REVIEW
    server_module.judge_script = fake_judge_script
    server_module.config.JUDGE_AT_REVIEW = True
    try:
        server_module._review_judge(script, section, results)   # source_text omitted
    finally:
        server_module.judge_script = old_judge
        server_module.config.JUDGE_AT_REVIEW = old_flag

    assert captured["source_text"] == section.text


# ---------------------------------------- the actual UI path (the endpoint)
#
# EVERY TEST ABOVE CALLS THE UNDERLYING FUNCTIONS (write_script, _grade,
# understanding_for, advance()) DIRECTLY. NONE OF THEM CALLS THE ACTUAL
# ENDPOINT FUNCTION FastAPI DISPATCHES TO — server.make_workflow_scripts,
# which is what POST /api/workflow/scripts (StepReview.tsx's "Draft it" AND
# its per-card "Retry" — see web/src/StepReview.tsx: both call
# makeWorkflowScripts, there is no separate retry path) actually runs. That
# function does its OWN sections = _sections(doc_id), find_section, and
# evidence_text call before richness/generation/grading — so a test that
# only exercises write_script/_grade in isolation cannot catch a wiring gap
# in make_workflow_scripts itself. This closes that gap.


def test_make_workflow_scripts_endpoint_uses_resolved_evidence():
    """
    THE EXACT UI-PATH REGRESSION TEST. Calls server.make_workflow_scripts
    directly — the literal function bound to POST /api/workflow/scripts,
    the same one StepReview.tsx's initial draft AND its "Retry" button both
    call — against a document containing the four related sections
    ("what_are_props", "example", "how_it_works", "script"), with a
    QuestionWorkflow already carrying an APPROVED question and an APPROVED
    "conceptual_visual" teaching approach (neither is generated or
    regenerated here — both are set directly, exactly as review.py leaves
    them after a human approves each stage).

    config.STUB=True makes this free and offline (no network, no key), the
    same convention script_workflow_test.py / orchestration_workflow_test.py
    already use for testing this exact endpoint shape.

    checks.check_section_richness is wrapped (not replaced — the real grader
    still runs) so this can assert, precisely, that the endpoint handed it
    the FULL resolved evidence pool — not the bare 2-sentence section that
    produced "only 2 distinct citable sentence(s) ... need 3 for a 4-beat
    script". That message is check_section_richness's own wording; if this
    test ever again hands it `section.text` instead of evidence_text's
    result, `richness_check_input` below will be short and the assertion on
    its span count will fail with exactly that message.
    """
    tmp_uploads = Path(tempfile.mkdtemp())
    old_uploads = server_module.UPLOADS
    doc_id = "regressiontest01"
    (tmp_uploads / f"{doc_id}.md").write_text(
        Path(REACT_PROPS_DOC).read_text(encoding="utf-8"), encoding="utf-8")

    sections = parse_markdown(tmp_uploads / f"{doc_id}.md")
    section = find_section(sections, "what_are_props")
    expected_resolved = evidence_text(sections, "what_are_props")
    expected_ids = evidence_section_ids(sections, "what_are_props")

    topic = Topic(
        id="what_are_props", topic="What are props and why do components use them?",
        why_it_matters="foundational", concept="React props",
        source_section_id="what_are_props", difficulty="easy",
        answer_quote="Props are values passed from a parent component to a child component.",
    )
    selection = QuestionSelection(
        topic=topic, source_title=section.title,
        reasons=[SelectionReason(category="importance", explanation="central idea")])
    wf = QuestionWorkflow(
        selection=selection,
        question_approval=QuestionApproval(status="approved"),
        framing=QuestionFraming(source_question=topic.topic, teaching_question=topic.topic),
        teaching_approach=TeachingApproach(primary="conceptual_visual"),
        teaching_approach_approval=TeachingApproachApproval(status="approved"),
    )
    body = server_module.WorkflowScriptsIn(doc_id=doc_id, workflows=[wf])

    richness_check_input = {}
    real_richness = checks.check_section_richness

    def spy_richness(text, *a, **kw):
        richness_check_input["text"] = text
        return real_richness(text, *a, **kw)

    old_stub = config.STUB
    server_module.UPLOADS = tmp_uploads
    checks.check_section_richness = spy_richness
    config.STUB = True
    try:
        out = server_module.make_workflow_scripts(body)
    finally:
        server_module.UPLOADS = old_uploads
        checks.check_section_richness = real_richness
        config.STUB = old_stub

    [result] = out["results"]

    # THE EXACT FAILURE THIS REPRODUCES AND DISPROVES.
    assert richness_check_input.get("text") is not None, "richness was never checked"
    assert richness_check_input["text"] == expected_resolved, (
        "make_workflow_scripts checked richness against something other than "
        "the resolved evidence pool")
    spans = checks._citable_spans(richness_check_input["text"])
    assert len(spans) >= 3, (
        f"only {len(spans)} distinct citable sentence(s) were handed to "
        f"check_section_richness — this is the exact bare-section failure "
        f"('only 2 distinct citable sentence(s) ... need 3 for a 4-beat "
        f"script') the fix exists to prevent")

    assert "example" in expected_ids and "how_it_works" in expected_ids, (
        "the resolved evidence group does not include the related sections "
        "the reported failure named")

    assert "error" not in result, (
        f"make_workflow_scripts rejected the topic: {result.get('error')}")
    assert result.get("graders"), "expected the retry loop to have run and graded an attempt"
    assert result["topic"]["topic"] == topic.topic, "the approved question must be preserved"
    assert (result.get("workflow") or {}).get("teaching_approach", {}).get("primary") \
        == "conceptual_visual", "the approved teaching approach must be preserved"


def main():
    import inspect
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} evidence-grouping tests")
    for t in tests:
        print(f"- {t.__name__}")
        if "monkeypatch" in inspect.signature(t).parameters:
            t(_FakeMonkeypatch())
        else:
            t()
    print("\nALL EVIDENCE GROUPING TESTS PASSED.")


class _FakeMonkeypatch:
    """The one pytest fixture this file's convention (plain functions, no
    pytest installed — see select_workflow_test.py) needs. Minimal: only
    setattr, restored via undo() if ever needed by a future test."""
    def __init__(self):
        self._sets = []

    def setattr(self, obj, name, value):
        self._sets.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self._sets):
            setattr(obj, name, old)


if __name__ == "__main__":
    main()
