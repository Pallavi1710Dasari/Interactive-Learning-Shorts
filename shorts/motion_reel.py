"""
Run one MOTION reel end to end (REEL_STYLE=motion — RESTYLE_TO_MOTION_REELS.md):

    python -m shorts.motion_reel content/react_usestate_basics.md
    python -m shorts.motion_reel <doc.md> --topic <short_id>          # resume
    python -m shorts.motion_reel <doc.md> --topic <id> --force-stage script
    python -m shorts.motion_reel <doc.md> --theme interview           # pick the theme

Stages: setup -> theme -> script -> scenes -> voice -> timing -> render -> report.
Mirrors shorts/story_reel.py's stage and resume behaviour on purpose, so one
runbook habit covers both: a stage runs when its artifact is missing, --from
trusts everything before it, --force-stage redoes that stage and every later
one, and --yes answers every confirmation (but never skips a pre-flight
printout).

THREE HUMAN GATES, all before anything is voiced or drawn:
  1. topic selection — the same approve/reject/regenerate gate as
     `python -m shorts.run --gate-topics` (review.run_question_gate);
  2. teaching approach — the same gate as --gate-teaching-approach
     (review.run_teaching_approach_gate), followed by the script TEMPLATE:
     walkthrough when the approved approach is process_demonstration, else
     fix_story (REFERENCE_STYLE_ADDENDUM.md section 3) — the reviewer can
     switch it there, or pass --template;
  3. the theme (phase 2b) — the reel's FORMAT (interview, story, bug hunt, ...;
     shorts/motion_themes.yaml), with the reason it was chosen and the reel's
     tags. Override it with --theme;
  4. the shot list — beat, speech, captions and visual for every shot, shown
     after the script passes the free motion graders.
Each writes its artifact ONLY on approval, so declining means "show me this
pause again on the next run", never "skip ahead".

NO IMAGE GENERATION, EVER. Motion reels are drawn by web/src/motion; this
module does not import shorts.imagegen, and motion_script_test asserts it.

PHASES 1-3 build setup, theme, script, scenes, voice and timing. render
reports "not built yet" and stops cleanly; it arrives in phase 4. Until then
the reel plays in the browser: #motion-reel/<short_id> (shorts/server.py
serves output/<short_id>/plan.json and its audio).

Motion reels get their OWN id namespace, <topic>__motion, never landing on an
explainer reel's or a story reel's files — the same rule story_reel.py keeps
with __story.
"""
import argparse
import json
import sys
from pathlib import Path

from . import checks, config, preflight, review, usage
from . import motion_themes
from . import workflow as question_workflow
from .parse import find_section, parse_markdown, story_evidence_pool
from .schema import (MOTION_TEMPLATES, MotionScript, MotionTags, MotionThemeChoice,
                     QuestionWorkflow, SectionUnderstanding, TeachingApproach, Topic,
                     motion_plain_text)
from .skills.script import reuse_saved_motion_script, write_motion_script
from .skills.theme import MAX_THEME_ATTEMPTS, SYSTEM_MOTION_THEME, choose_theme
from .skills.select import select_topics_with_selections
from .skills.understanding import understanding_for

STAGE_ORDER = ["setup", "theme", "script", "scenes", "voice", "timing", "render", "report"]
MONEY_STAGES = {"theme", "script", "scenes"}

#: Stages that exist in STAGE_ORDER (so --from / --force-stage accept them and
#: resume math is already right) but are built in a later phase.
_NOT_BUILT_YET = {"render": 4}

_MOTION_MODE_BANNER = (
    "\n"
    "############################################################\n"
    "#                                                          #\n"
    "#                >>> MOTION MODE <<<                       #\n"
    "#                                                          #\n"
    "#   shorts/motion_reel.py — NOT shorts/run.py (explainer)  #\n"
    "#   or shorts/story_reel.py (story). Every reel this       #\n"
    "#   produces gets a __motion short_id. No image calls.     #\n"
    "#                                                          #\n"
    "############################################################\n"
)


# ======================================================================= io

def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        print(f"{prompt} [y/N] y   (--yes)")
        return True
    if not sys.stdin.isatty():
        print(f"{prompt} [y/N] — non-interactive session, defaulting to N. "
              f"Pass --yes to proceed automatically.")
        return False
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except EOFError:
        # Windows reports the NUL device as a terminal, so a piped run can
        # reach input() anyway. No input is no decision: N.
        print("\n  no input — defaulting to N.")
        return False


#: The run in progress: its start, which keys its entry in cost.json.
_RUN: dict = {"started": None}


def _money_gate(stage: str, short_id: str, plan: list, yes: bool, reel_cursor: int) -> bool:
    """Same pre-spend gate as story_reel._money_gate: print + persist the
    pre-flight plan (always, even under --yes), refuse past MAX_REEL_USD,
    then ask."""
    built = preflight.build_plan(f"motion_{stage}", short_id, plan)
    preflight.print_plan(built)
    preflight.write_preflight_json(short_id, built)
    spent = round(earlier_runs_cost(short_id, _RUN["started"]) + usage.since(reel_cursor)["cost"], 6)
    projected = round(spent + built["total_cost"], 4)
    if projected > config.MAX_REEL_USD:
        print(f"  MAX_REEL_USD (${config.MAX_REEL_USD:.2f}) would be exceeded: "
              f"${spent:.4f} spent on this reel so far + ${built['total_cost']:.4f} "
              f"for {stage} = ${projected:.4f}. Stopping before any call.")
        return False
    return _confirm(f"Proceed with the {stage} stage (est. ${built['total_cost']:.4f})?", yes)


def _model(label: str) -> str:
    """The model a motion call uses (shorts/motion_models.yaml)."""
    from . import motion_models
    return motion_models.model_for(label) or config.MODEL_GENERATOR


# ======================================================================= ids

def motion_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / f"{short_id}.motion.json"


def _facts_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "fact_sources.json"


def _setup_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "setup.json"


def theme_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "theme.json"


def tags_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "tags.json"


def _reel_exists(short_id: str) -> bool:
    """Does ANY reel — explainer, story or motion — already occupy this id?"""
    out = config.OUTPUT_DIR
    return any(p.exists() for p in (
        out / f"{short_id}.json", out / f"{short_id}.story.json",
        out / f"{short_id}.motion.json", out / short_id))


def _next_free_motion_id(base_id: str) -> str:
    candidate = f"{base_id}__motion"
    if not _reel_exists(candidate):
        return candidate
    n = 2
    while _reel_exists(f"{candidate}_{n}"):
        n += 1
    return f"{candidate}_{n}"


def next_topic_for(sections: list, section_id: str, used_ids: list[str]) -> str:
    """The end card's "Up next": the first section AFTER this reel's own, in
    document order, whose text this reel did not already draw on. From the
    document, never the LLM (user decision, 2026-09-30). "" when none is left."""
    ids = [s.section_id for s in sections]
    if section_id not in ids:
        return ""
    for s in sections[ids.index(section_id) + 1:]:
        if s.section_id not in used_ids:
            return s.title
    return ""


# ==================================================================== setup

def _decide_questions(workflows: list[QuestionWorkflow], sections: list,
                      yes: bool) -> list[QuestionWorkflow]:
    if yes:
        print("  --yes: approving the selected question(s) as they stand.")
        return [review.approve_question(w, note="--yes") for w in workflows]
    try:
        return review.run_question_gate(workflows, sections, interactive=sys.stdin.isatty())
    except EOFError:   # see _confirm: no input is no decision
        print("\n  no input — nothing decided.")
        return workflows


def _decide_approach(workflows: list[QuestionWorkflow], sections: list,
                     yes: bool) -> list[QuestionWorkflow]:
    if yes:
        print("  --yes: approving the recommended teaching approach(es).")
        return [review.approve_teaching_approach(w, note="--yes")
                if w.teaching_approach is not None else w for w in workflows]
    try:
        return review.run_teaching_approach_gate(workflows, sections,
                                                 interactive=sys.stdin.isatty())
    except EOFError:
        print("\n  no input — nothing decided.")
        return workflows


def default_template(approach: TeachingApproach | None) -> str:
    """The template a teaching approach implies: a walked sequence of steps is
    a walkthrough ("how does X work"); everything else is a fix_story ("why
    does X fail"). The reviewer can override it — see _decide_template."""
    if approach is not None and approach.primary == "process_demonstration":
        return "walkthrough"
    return "fix_story"


def walkthrough_session_ids(sections: list, section_id: str) -> list[str]:
    """Every section in the same numbered session as `section_id` ("1.1" ->
    every "1.x"), in document order. A walkthrough follows a process step by
    step, and a lesson usually gives each step its own heading — so its
    evidence is the whole session, not only the heading the topic is filed
    under. A string-only rule, like story_evidence_pool's own: a section id
    with no "major.minor" shape adds nothing."""
    major = section_id.split(".")[0] if "." in section_id else None
    if not major:
        return []
    return [s.section_id for s in sections
            if "." in s.section_id and s.section_id.split(".")[0] == major]


def _decide_template(default: str, yes: bool, override: str | None) -> tuple[str, str]:
    """The template gate: --template wins, then --yes keeps the default, then
    an interactive reviewer may switch it. Choosing a template spends nothing,
    so a non-interactive run keeps the default rather than stopping.

    Returns (template, source). Since phase 2b the THEME decides the template
    unless a human chose it here: source "flag" or "reviewer" pins it, and the
    theme step then only considers themes of that template; "default" leaves
    it to the theme."""
    if override:
        print(f"  template: {override}   (--template)")
        return override, "flag"
    if yes or not sys.stdin.isatty():
        print(f"  template: {default}   (from the teaching approach"
              + ("; --yes" if yes else "; non-interactive — pass --template to change it")
              + ")")
        return default, "default"
    try:
        answer = input(f"  template [{default}] — Enter to keep, or type "
                       f"{' / '.join(MOTION_TEMPLATES)}: ").strip().lower()
    except EOFError:
        answer = ""
    if answer and answer not in MOTION_TEMPLATES:
        print(f"  {answer!r} is not a template — keeping {default}")
        answer = ""
    # The reviewer saw the template and kept or chose it: either way it is
    # their choice, and it pins the theme step. Returning "default" for Enter
    # let the theme step pick a fix_story theme after a reviewer had kept
    # walkthrough (plain_variable_no_rerender__motion, 2026-10-12).
    return answer or default, "reviewer"


def _run_setup(sections: list, doc_text: str, yes: bool,
               template_override: str | None = None,
               section_pin: str | None = None) -> dict | None:
    """Select a topic, gate it, frame it, pick a teaching approach, gate that.
    Returns the setup state, or None when a human declined (or no human was
    available to decide)."""
    # --section: choose the topic from that one section (the rest of the
    # document still supplies evidence, the next topic and so on).
    pool = [s for s in sections if s.section_id == section_pin] if section_pin else sections
    if section_pin and not pool:
        print(f"\n--section {section_pin}: no such section. The document has: "
              f"{', '.join(s.section_id for s in sections)}")
        return None
    _topics, _notes, selections = select_topics_with_selections(pool, target=1)
    workflows = [QuestionWorkflow(selection=s) for s in selections]
    for w in workflows:
        print(f"  candidate [{w.selection.topic.source_section_id}] {w.effective_question}")

    workflows = _decide_questions(workflows, sections, yes)
    approved = [w for w in workflows if w.approved_topic is not None]
    if not approved:
        print("\nTOPIC GATE — nothing approved. Rerun from an interactive terminal, "
              "or pass --yes to approve the selected question.")
        return None
    wf = approved[0]
    topic = wf.approved_topic
    section = find_section(sections, topic.source_section_id)
    understanding = understanding_for(section, source_text=section.text)

    progress = question_workflow.advance(wf, sections, understanding=understanding)
    print(f"  {topic.id}: {progress.status} — {progress.detail}")
    [wf] = _decide_approach([progress.workflow], sections, yes)
    approach = wf.approved_teaching_approach
    if approach is None:
        print("\nTEACHING APPROACH GATE — not approved. Rerun from an interactive "
              "terminal, or pass --yes to approve the recommendation.")
        return None
    template, template_source = _decide_template(default_template(approach), yes,
                                                 template_override)
    return build_setup_state(sections, wf, understanding, template, template_source)


def build_setup_state(sections: list, wf: QuestionWorkflow,
                      understanding: SectionUnderstanding | None,
                      template: str, template_source: str) -> dict:
    """The setup state saved as output/<short_id>/setup.json, once the topic,
    the teaching approach and the template are decided. Shared by the CLI's
    setup and the web UI's (shorts/motion_jobs.py)."""
    topic = wf.approved_topic
    section = find_section(sections, topic.source_section_id)
    _pool, pool_ids = story_evidence_pool(
        sections, topic.source_section_id,
        teaching_sequence=understanding.teaching_sequence if understanding else None)
    pool_ids = list(pool_ids)
    # A walkthrough also sees the rest of its numbered session — but only as
    # SUPPORTING sections, for numbers and defined terms. The explanation
    # comes from pool_ids, the selected section's own evidence (decision
    # 2026-10-01; checks.check_walkthrough_main_source).
    support_ids = ([sid for sid in walkthrough_session_ids(sections, topic.source_section_id)
                    if sid not in pool_ids] if template == "walkthrough" else [])
    return {
        "topic": topic.model_dump(),
        "section_id": section.section_id,
        "understanding": understanding.model_dump() if understanding else None,
        "workflow": wf.model_dump(),
        "template": template,
        "template_source": template_source,
        "pool_ids": list(pool_ids),
        "support_ids": support_ids,
        "next_topic": next_topic_for(sections, section.section_id,
                                     list(pool_ids) + support_ids),
    }


def _save_setup(short_id: str, state: dict) -> None:
    path = _setup_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_setup(short_id: str) -> dict:
    return json.loads(_setup_path(short_id).read_text(encoding="utf-8"))


# ==================================================================== theme

def template_pin(state: dict) -> str | None:
    """The template a human chose at setup (--template, or the reviewer at the
    template gate), which the theme must use. None when the template was only
    the teaching approach's default — then the theme decides it. A setup
    written before phase 2b has no template_source; its template was the
    approved one then, so it stays pinned."""
    if state.get("template_source", "pinned") == "default":
        return None
    return state.get("template", "fix_story")


def _load_theme(short_id: str) -> MotionThemeChoice | None:
    path = theme_path(short_id)
    if not path.exists():
        return None
    return MotionThemeChoice.model_validate_json(path.read_text(encoding="utf-8"))


def print_theme(choice: MotionThemeChoice, language_how: str = "",
                history: list[str] | None = None) -> None:
    """The theme gate's screen: the theme and why, what it was chosen from,
    the fit check, the cast and the tags."""
    spec = motion_themes.registry().themes[choice.theme]
    print(f"\n=== Theme: {choice.theme} ({choice.source}) ===")
    print(f"  reason:   {choice.reason}")
    print(f"  format:   {spec.description}")
    print(f"  template: {choice.template}   approach: {choice.teaching_approach or '(none)'}")
    who = (" / ".join(f"{sp.label} ({sp.identity} badge, voice {sp.voice_slot})"
                      for sp in motion_themes.cast_speakers(spec, choice.language))
           if spec.two_speaker else "one narrator")
    print(f"  speakers: {who}")
    print(f"  language: {choice.language}" + (f"   ({language_how})" if language_how else ""))
    if history is not None:
        print(f"  earlier reels in {choice.language}: {', '.join(history) or 'none'}")
    print(f"  eligible: {', '.join(choice.eligible) or '(none)'}")
    fit = choice.fit_check
    print(f"  fit check: {'passed' if fit.passed else 'FAILED'}"
          f"{f' after {fit.attempts} pick(s)' if fit.attempts else ''}")
    for r in fit.rejected:
        print(f"      rejected {r.theme} (pick {r.attempt}): {'; '.join(r.problems)}")
    if fit.fallback:
        print(f"      FALLBACK: {fit.fallback_reason}")
    for o in fit.overrides:
        print(f"      override: {o}")
    print(f"  tags:     {' '.join(choice.tags)}")


def stage_theme(short_id: str, state: dict, sections: list, doc_text: str, yes: bool,
                reel_cursor: int, override: str | None = None,
                language_override: str | None = None) -> MotionThemeChoice | None:
    """Choose the reel's theme (skills/theme.py), show it at the theme gate,
    and on approval save theme.json and tags.json. The fit call is the only
    spend, and only when two or more themes are eligible and --theme is not
    given."""
    t = theme_inputs(short_id, state, sections, doc_text, override, language_override)
    if t["plan"] is not None and not _money_gate("theme", short_id, t["plan"], yes, reel_cursor):
        return None
    try:
        choice = run_theme_choice(t, override)
    except ValueError as e:
        print(f"\n  {e}")
        return None
    print_theme(choice, t["how"], t["history"])
    tag_checks = theme_tag_checks(choice, t)
    for r in tag_checks:
        print(f"  {r}")
    if not checks.all_passed(tag_checks):
        print("  GIVING UP — the tags are not valid (see above).")
        return None
    if not _confirm("Approve theme?", yes):
        print(f"Stopped at the theme — nothing saved. Rerun with --topic {short_id} to see "
              f"this pause again, or --topic {short_id} --theme <id> to choose it yourself "
              f"({', '.join(motion_themes.registry().ids())}).")
        return None
    save_theme(short_id, choice)
    return choice


def theme_inputs(short_id: str, state: dict, sections: list, doc_text: str,
                 override: str | None = None, language_override: str | None = None) -> dict:
    """Everything the theme step decides from, free: the language (and how it
    was decided), the reel history, the template pin, the eligible themes and
    the fit call's pre-flight plan (None when no call is needed: --theme, or
    one eligible theme)."""
    section = find_section(sections, state["section_id"])
    source_text = "\n\n".join(find_section(sections, sid).text for sid in state["pool_ids"])
    if language_override:
        language, how = language_override, "--language"
    else:
        language, how = motion_themes.detect_language(source_text, doc_text)
    history = [t.theme for t in motion_themes.reel_history(config.OUTPUT_DIR, language,
                                                           exclude_id=short_id)]
    pin = template_pin(state)
    wf = QuestionWorkflow(**state["workflow"])
    approach = wf.approved_teaching_approach
    kind = approach.primary if approach is not None else None
    eligible = motion_themes.eligible_themes(
        approach=kind, has_code=motion_themes.section_has_code(source_text),
        template=pin, history=history, language=language)
    plan = None
    if not override and len(eligible) > 1:
        plan = [preflight.ModelPlan(
            "motion_theme", _model("motion_theme"), MAX_THEME_ATTEMPTS,
            preflight.text_cost_per_call(_model("motion_theme"),
                                         (len(SYSTEM_MOTION_THEME) + len(source_text)) // 3
                                         + 120 * len(eligible), 300))]
    headings = motion_themes.reel_headings(
        doc_text, [section.title] + [find_section(sections, sid).title
                                     for sid in state["pool_ids"]
                                     if sid != section.section_id])
    return {"section": section, "source_text": source_text, "language": language, "how": how,
            "history": history, "pin": pin, "approach": approach, "eligible": eligible,
            "plan": plan, "headings": headings}


def run_theme_choice(t: dict, override: str | None = None) -> MotionThemeChoice:
    """The theme call itself (skills/theme.choose_theme) on theme_inputs.
    Raises ValueError when --theme cannot be used here."""
    return choose_theme(t["section"], source_text=t["source_text"], approach=t["approach"],
                        language=t["language"], history=t["history"], template_pin=t["pin"],
                        override=override, headings=t["headings"])


def theme_tag_checks(choice: MotionThemeChoice, t: dict) -> list:
    return [checks.check_motion_tags(choice.tags),
            checks.check_motion_tag_concepts(choice.tags, t["headings"], t["source_text"])]


def save_theme(short_id: str, choice: MotionThemeChoice) -> None:
    """The theme gate's approval: theme.json and tags.json."""
    path = theme_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(choice.model_dump_json(indent=2), encoding="utf-8")
    concepts = [t.lstrip("#") for t in choice.tags[2:]]
    tags = MotionTags(short_id=short_id, language=choice.language, theme=choice.theme,
                      concepts=concepts, tags=choice.tags,
                      created_at=_now_iso())
    tags_path(short_id).write_text(tags.model_dump_json(indent=2), encoding="utf-8")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# =================================================================== script

def fact_sources(script: MotionScript, sections: list, state: dict) -> list[dict]:
    """Every number and long term the script says, with the section it came
    from (checks.motion_fact_sources): the selected section first, then every
    other section as SUPPORTING, labelled with its id (source-scope rule,
    2026-10-10)."""
    selected = state["section_id"]
    pool = [(sid, find_section(sections, sid).text) for sid in state["pool_ids"]]
    support = [(sid, find_section(sections, sid).text) for sid in state.get("support_ids", [])]
    if state.get("template") == "walkthrough":
        # a walkthrough's whole pool is its main material (decision 2026-10-01)
        return checks.motion_fact_sources(script, pool, support)
    main = [(sid, t) for sid, t in pool if sid == selected] or [
        (selected, find_section(sections, selected).text)]
    others = [(sid, t) for sid, t in pool if sid != selected]
    return checks.motion_fact_sources(script, main, others + support)


def print_invented_example(script: MotionScript, sections: list) -> str:
    """Print the invented-example WARNING (checks.invented_example_warning)
    when the running example's names are in no section; returns it ("" when
    there is none)."""
    warning = checks.invented_example_warning(script, "\n\n".join(s.text for s in sections))
    if warning:
        print(f"\n  {warning}")
    return warning


def print_fact_sources(rows: list[dict]) -> None:
    print("\n  facts (every number and term, with the section it came from):")
    if not rows:
        print("      (none)")
    for r in rows:
        role = f" ({r['role']})" if r["role"] else ""
        print(f"      {r['kind']:<6} {r['value']:<14} {r['section']}{role}   "
              f"shots {', '.join(r['shots'])}")


def print_shot_list(script: MotionScript, results: list | None = None) -> None:
    """The shot-list gate's screen: every shot's beat, speech, captions and
    visual. Also what `--from script` prints for an approved script."""
    print(f"\n=== Shot list: {script.short_id} — {script.template}"
          + (f", theme {script.theme}" if script.theme else "")
          + f" ({len(script.shots)} shots, ~{script.estimated_seconds:.1f}s) ===")
    if script.speakers:
        print("speakers: " + ", ".join(f"{sp.role} = {sp.label} ({sp.identity} badge, voice "
                                        f"{sp.voice_slot})" for sp in script.speakers))
    print(f"concept: {script.concept_name}   promise: {script.promise!r}")
    print(f"hook question: {script.hook_question}")
    walkthrough = script.template == "walkthrough"
    if walkthrough:
        ex = script.running_example
        print(f"running example: {ex.text if ex else '(none)'}  {ex.items if ex else ''}")
        for c in script.chapters:
            print(f"  chapter {c.n}: {c.title}   {c.example_in} -> {c.example_out}")
    else:
        print(f"icons: {[f'{i.name} ({i.label})' for i in script.icon_vocabulary]}")
    for s in script.shots:
        chapter = f" ch{s.chapter}" if s.chapter is not None else ""
        print(f"\n  {s.id}  {s.beat:<12}{chapter} ~{s.estimated_seconds:.1f}s")
        if any(c.speaker for c in s.captions):
            for c in s.captions:
                print(f"      {c.speaker or '?'}: {motion_plain_text(c.text)}")
        else:
            print(f"      speech:   {s.speech}")
            print(f"      captions: {' | '.join(motion_plain_text(c.text) for c in s.captions)}")
        print(f"      visual:   {s.visual}")
        if s.example:
            print(f"      example:  {s.example}")
        for line in s.code:
            print(f"      code:     {line}")
    if not walkthrough:
        print("\n  recap:")
        for t in script.takeaways:
            print(f"      [{t.icon}] {t.line} — {t.sub}")
    print(f"  series: {script.series!r}   next up: {script.next_topic or '(none)'}")
    if results is not None:
        print("\ncheck results:")
        for r in results:
            print(f"  {r}")


def stage_script(short_id: str, state: dict, sections: list, yes: bool,
                 reel_cursor: int, theme: MotionThemeChoice | None = None) -> MotionScript | None:
    # A draft rejected on an earlier run may pass today's graders (a grader
    # fixed since, or a caption re-cut): free, so it is tried before the
    # money gate. The shot-list gate below still shows it for approval.
    saved = reuse_script(short_id, state, sections, theme)
    if saved is not None:
        script, results, path, repaired = saved
        print(f"\n=== script: a saved draft passes every grader"
              f"{' after a caption re-cut' if repaired else ''} — no call made ===")
        print(f"  from {path}")
    else:
        if not _money_gate("script", short_id, script_plan(), yes, reel_cursor):
            return None
        script, results = write_script(short_id, state, sections, theme)
    if script is None:
        print("  GIVING UP — no script passed the motion graders:")
        for r in results:
            print(f"    {r}")
        return None

    print_shot_list(script, results)
    facts = fact_sources(script, sections, state)
    print_fact_sources(facts)
    print_invented_example(script, sections)
    if not _confirm("Approve shot list?", yes):
        print(f"Stopped after script — rerun with --topic {short_id} to continue "
              f"(the script was NOT saved — declining means try again, not skip ahead).")
        return None
    # Written ONLY on approval — same reasoning as story_reel.stage_mapping.
    save_script(short_id, script, facts)
    return script


def _script_kwargs(short_id: str, state: dict, sections: list,
                   theme: MotionThemeChoice | None) -> dict:
    """The script stage's inputs from a reel's setup state and approved theme."""
    return {
        "topic": Topic(**state["topic"]),
        "section": find_section(sections, state["section_id"]),
        "understanding": (SectionUnderstanding(**state["understanding"])
                          if state.get("understanding") else None),
        "approach": QuestionWorkflow(**state["workflow"]).approved_teaching_approach,
        "source_text": "\n\n".join(find_section(sections, sid).text
                                    for sid in state["pool_ids"]),
        "supporting_text": "\n\n".join(find_section(sections, sid).text
                                        for sid in state.get("support_ids", [])),
        "template": theme.template if theme else state.get("template", "fix_story"),
        "theme": theme.theme if theme else None,
        "language": theme.language if theme else None,
        "next_topic": state.get("next_topic", ""),
    }


def reuse_script(short_id: str, state: dict, sections: list,
                 theme: MotionThemeChoice | None):
    """A saved rejected draft that passes today's graders (free), or None."""
    k = _script_kwargs(short_id, state, sections, theme)
    return reuse_saved_motion_script(
        k["section"], short_id=short_id, source_text=k["source_text"], approach=k["approach"],
        template=k["template"], supporting_text=k["supporting_text"], theme=k["theme"])


def script_plan() -> list:
    """The script stage's pre-flight plan: every attempt and hook fix."""
    return [preflight.ModelPlan(
        "motion_script", _model("motion_script"),
        config.MAX_MOTION_SCRIPT_RETRIES * (1 + config.MAX_MOTION_HOOK_FIX_RETRIES),
        preflight.text_cost_per_call(_model("motion_script"), 7000, 4500))]


def write_script(short_id: str, state: dict, sections: list,
                 theme: MotionThemeChoice | None) -> tuple[MotionScript | None, list]:
    """The paid script call (skills.script.write_motion_script)."""
    k = _script_kwargs(short_id, state, sections, theme)
    return write_motion_script(
        k["topic"], k["section"], short_id=short_id, source_text=k["source_text"],
        understanding=k["understanding"], approach=k["approach"], next_topic=k["next_topic"],
        template=k["template"], supporting_text=k["supporting_text"], theme=k["theme"],
        language=k["language"])


def save_script(short_id: str, script: MotionScript, facts: list[dict]) -> None:
    """The shot-list gate's approval: the script and its fact sources."""
    motion_path(short_id).write_text(script.model_dump_json(indent=2), encoding="utf-8")
    _facts_path(short_id).write_text(json.dumps(facts, indent=2), encoding="utf-8")


# =================================================================== scenes

def _scenes_done(script: MotionScript) -> bool:
    return all(s.scene is not None for s in script.shots)


def print_scenes(script: MotionScript, results: list | None = None) -> None:
    """The scene gate's screen: per shot, the field, the transition in, every
    object and every action with the word it is cued on."""
    print(f"\n=== Scenes: {script.short_id} ===")
    for s in script.shots:
        sc = s.scene
        if sc is None:
            print(f"  {s.id} {s.beat}: (no scene)")
            continue
        label = f"  [{sc.label}]" if sc.label else ""
        print(f"\n  {s.id}  {s.beat:<12} {sc.field:<6} <- {sc.transition}{label}")
        for o in sc.objects:
            brief = {k: v for k, v in o.props.items() if k in ("text", "title", "label", "items",
                                                             "value", "lines", "status")}
            print(f"      {o.id} {o.kind:<14} {json.dumps(brief, ensure_ascii=False)[:90]}")
        for a in sc.actions:
            extra = "".join(f" {k}={v}" for k, v in (("value", a.value), ("tone", a.tone)) if v)
            print(f"      @ {a.at!r:<18} {a.do} {a.target}{extra}")
    if results is not None:
        print("\nscene check results:")
        for r in results:
            print(f"  {r}")


def stage_scenes(short_id: str, script: MotionScript, yes: bool,
                 reel_cursor: int) -> MotionScript | None:
    if not _money_gate("scenes", short_id, scenes_plan(), yes, reel_cursor):
        return None
    scripted, results = write_scenes(short_id, script)
    print(f"  attempts: {scenes_attempts_path(short_id)}")
    print_scenes(scripted, results)
    if not checks.all_passed(results):
        print("  GIVING UP — the scenes do not pass the scene graders (see above).")
        return None
    if not _confirm("Approve scenes?", yes):
        print(f"Stopped after scenes — nothing saved. Rerun with --topic {short_id} to see "
              f"this pause again.")
        return None
    save_scenes(short_id, scripted)
    return scripted


def scenes_plan() -> list:
    """The scenes stage's pre-flight plan: the first call and every repair."""
    from .skills.scenes import SYSTEM_MOTION_SCENES
    return [preflight.ModelPlan(
        "motion_scenes", _model("motion_scenes"), 1 + config.MAX_MOTION_SCENE_RETRIES,
        preflight.text_cost_per_call(_model("motion_scenes"),
                                     len(SYSTEM_MOTION_SCENES) // 3 + 3500, 6000))]


def write_scenes(short_id: str, script: MotionScript, log=print, note: str = "") -> tuple[MotionScript, list]:
    """The paid scenes call (skills.scenes.write_motion_scenes)."""
    from .skills.scenes import write_motion_scenes
    attempts: list = []
    try:
        return write_motion_scenes(script, log=log, attempts=attempts, note=note)
    finally:
        # every attempt's scenes, per-shot reasons and fallbacks — kept even
        # when the stage gives up, so a failed run can be diagnosed from disk
        scenes_attempts_path(short_id).write_text(json.dumps(
            {"short_id": short_id, "attempts": attempts}, indent=1), encoding="utf-8")


def save_scenes(short_id: str, scripted: MotionScript) -> None:
    """The scene gate's approval: the script, now with its scenes."""
    motion_path(short_id).write_text(scripted.model_dump_json(indent=2), encoding="utf-8")


# ============================================================ voice, timing

def scenes_attempts_path(short_id: str) -> Path:
    path = config.OUTPUT_DIR / short_id / "scenes_attempts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def plan_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "plan.json"


def _speech_stamp(script: MotionScript) -> str:
    """What the voice depends on: every caption's text and speaker."""
    import hashlib
    blob = json.dumps([[s.id, s.speech, [[c.text, c.speaker] for c in s.captions]]
                       for s in script.shots])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _voice_current(script: MotionScript) -> bool:
    from . import motion_voice
    path = motion_voice.manifest_path(script.short_id)
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("stamp") == _speech_stamp(script)
    except ValueError:
        return False


def stage_voice(short_id: str, script: MotionScript, progress=None,
                voices: dict[str, str] | None = None) -> dict | None:
    """Every caption in its speaker's voice (shorts/motion_voice.py). Local
    and free — no money gate — but it prints which voice each slot uses."""
    from . import motion_voice
    slots = motion_voice.speaker_slots(script)
    print(f"\n=== voice: {sum(len(s.captions) for s in script.shots)} caption clip(s), "
          f"{'silence (MOTION_VOICE=silent)' if config.MOTION_SILENT else 'Chatterbox (local, free)'} ===")
    for role, slot in slots.items():
        if role is None and script.speakers:
            continue
        ref, how = motion_voice.slot_reference(slot)
        print(f"  {role or 'NARRATOR':<12} slot {slot:<18} {how}"
              + (f" — {Path(ref).name}" if ref else ""))
    try:
        manifest = motion_voice.voice_script(script, log=lambda *_: None, progress=progress, voices=voices)
    except RuntimeError as e:
        print(f"  GIVING UP — {e}")
        return None
    manifest["stamp"] = _speech_stamp(script)
    motion_voice.manifest_path(short_id).write_text(json.dumps(manifest, indent=2),
                                                    encoding="utf-8")
    return manifest


def _cast(script: MotionScript) -> list:
    """The two speakers' badges: the host on the left (the asking role), the
    language speaker on the right."""
    from .motion_identities import identity, registry
    from .schema import MotionCastMember, MotionIdentitySpec
    out = []
    for sp in script.speakers:
        ident = registry().host if sp.identity == "host" else identity(sp.identity)
        out.append(MotionCastMember(role=sp.role, side="left" if sp.identity == "host" else "right",
                                    label=sp.label, voice_slot=sp.voice_slot,
                                    identity=MotionIdentitySpec(**ident.spec())))
    return out


def stage_timing(short_id: str, script: MotionScript, manifest: dict, progress=None,
                 characters: bool | None = None,
                 character: str | None = None,
                 host_character: str | None = None) -> tuple[Path, list] | None:
    """Word times from the real audio (motion_align: forced alignment, then
    whisper, then an even split), every shot on one clock, the scene graders
    again on that clock, the narration mixed, and the player's plan written.
    `progress(done, total)` is told after every clip is aligned. `characters`
    and `character` default to config.MOTION_CHARACTERS / _PRESET (the CLI's
    --characters / --character)."""
    characters = config.MOTION_CHARACTERS if characters is None else characters
    character = config.MOTION_CHARACTER_PRESET if character is None else character
    from . import motion_align, motion_plan_checks, motion_timeline, motion_voice
    print(f"\n=== timing: {short_id} ===")
    tags = []
    if tags_path(short_id).exists():
        tags = json.loads(tags_path(short_id).read_text(encoding="utf-8")).get("tags", [])
    total_clips = sum(len(manifest["shots"].get(s.id, [])) for s in script.shots)
    aligned = 0
    seconds: dict[str, list[float]] = {}
    times: dict[str, list] = {}
    sources: dict[str, list[str]] = {}
    adir = motion_voice.audio_dir(short_id)
    for shot in script.shots:
        rows = manifest["shots"].get(shot.id, [])
        ranges = motion_voice.shown_to_spoken(shot)
        seconds[shot.id] = [r["seconds"] for r in rows]
        times[shot.id], sources[shot.id] = [], []
        for row, rng in zip(rows, ranges):
            spoken, src = motion_align.align_clip(adir / row["file"], row["text"], row["seconds"])
            times[shot.id].append(motion_align.shown_times(spoken, rng))
            sources[shot.id].append(src)
            aligned += 1
            if progress is not None:
                progress(aligned, total_clips)
    motion_align.close()
    # each clip cut to its speech: no dead air between lines and shots
    seconds, times, trims = motion_timeline.trim_to_speech(seconds, times, sources)
    intro = config.MOTION_INTRO_SECONDS if config.MOTION_INTRO_STING else 0.0
    clocks = motion_timeline.shot_timings(script, seconds, times, sources, offset=intro)
    counts: dict[str, int] = {}
    for c in clocks:
        for cap in c.captions:
            counts[cap.source] = counts.get(cap.source, 0) + 1
    print("  caption timing: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    # the look chosen when the reel was set up; none saved = an older reel, "classic"
    design = (_load_setup(short_id).get("design") if _setup_path(short_id).exists() else None) or "classic"
    plan = motion_timeline.build_plan(script, clocks, audio=None, cast=_cast(script),
                                      tags=tags, intro=intro, characters=characters,
                                      character=character, design=design,
                                      host_character=host_character)
    results = checks.run_motion_scene_graders(script, clocks) + [
        checks.check_motion_duration_cap(script, measured_seconds=motion_timeline.total_seconds(clocks)),
        *motion_plan_checks.run(plan)]
    for r in results:
        print(f"  {r}")
    audio = motion_voice.mix(script, manifest, clocks, trims)
    plan = plan.model_copy(update={"audio": f"audio/{audio.name}"})
    if plan.characters:
        shown = sum(s.characters for s in plan.shots)
        print("  characters: " + ", ".join(
            f"{t.config.get('name', t.preset)} ({t.preset}) as {t.role or 'narrator'} "
            f"({sum(c.kind == 'gesture' for c in t.cues)} gestures)" for t in plan.characters)
            + f" — on {shown} of {len(plan.shots)} shots")
    path = plan_path(short_id)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print(f"  {motion_timeline.total_seconds(clocks):.1f}s — {path}")
    print(f"  play it: run the app and open #motion-reel/{short_id}")
    return path, results


# ======================================================================= run

def cost_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "cost.json"


def _print_call(call) -> None:
    """One line per LLM call, as it happens."""
    est = " (estimated)" if call.estimated else ""
    print(f"    $ {call.label:<28} {call.model:<30} {call.input_tokens:>6} in {call.output_tokens:>6} out"
          f"   ${call.cost:.4f}{est}")


def _load_cost(short_id: str) -> dict:
    path = cost_path(short_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"short_id": short_id, "runs": []}


def earlier_runs_cost(short_id: str, started: str | None) -> float:
    """What every OTHER run of this reel has spent (output/<short_id>/cost.json),
    so MAX_REEL_USD caps the reel, not just the run in progress."""
    return round(sum(r.get("cost", 0.0) for r in _load_cost(short_id)["runs"]
                     if r.get("started") != started), 6)


def record_cost(short_id: str, calls: list[dict], started: str) -> dict:
    """Write this run's calls into output/<short_id>/cost.json — the run
    started at `started` is replaced, so this is called after EVERY call and
    once more when the run ends, however it ends (a crash or Ctrl+C included:
    the first real reel's history lost the setup, theme and script runs).
    Returns the reel's whole history: every run, every call, and the total."""
    from datetime import datetime, timezone
    path = cost_path(short_id)
    data = _load_cost(short_id)
    run = {"started": started, "ended": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "stub": bool(config.STUB), "calls": calls,
           "cost": round(sum(c["cost"] for c in calls), 6)}
    same = [i for i, r in enumerate(data["runs"]) if r.get("started") == started]
    if same:
        data["runs"][same[0]] = run
    elif calls or not data["runs"]:
        data["runs"].append(run)
    every = [c for r in data["runs"] for c in r["calls"]]
    by_label: dict[str, dict] = {}
    for c in every:
        row = by_label.setdefault(c["label"], {"calls": 0, "cost": 0.0, "model": c["model"]})
        row["calls"] += 1
        row["cost"] = round(row["cost"] + c["cost"], 6)
    data["total"] = {"calls": len(every), "cost": round(sum(c["cost"] for c in every), 6),
                     "estimated": any(c.get("estimated") for c in every), "by_label": by_label}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def run(doc_path: str, topic_short_id: str | None, from_stage: str | None,
        force_stage: str | None, yes: bool, template: str | None = None,
        theme: str | None = None, language: str | None = None,
        estimate_only: bool = False, section: str | None = None) -> int:
    """The motion run, with the model routing of shorts/motion_models.yaml
    switched on, a whole-reel cost estimate (and one confirmation) before a
    real run starts, every LLM call's cost printed as it happens, and the
    reel's cost log written to output/<short_id>/cost.json."""
    from datetime import datetime, timezone
    from . import motion_models
    print(_MOTION_MODE_BANNER)
    print(f"  handle: {config.BRAND_HANDLE!r}   series: {config.MOTION_SERIES!r}   "
          f"(BRAND_HANDLE / MOTION_SERIES in .env)")
    if estimate_only or (not config.STUB and topic_short_id is None):
        doc_text = Path(doc_path).read_text(encoding="utf-8")
        typical, worst = motion_models.print_estimate(motion_models.estimate(doc_text))
        if estimate_only:
            return 0
        if worst > config.MAX_REEL_USD:
            print(f"  The worst case is over MAX_REEL_USD (${config.MAX_REEL_USD:.2f}); each stage "
                  f"still stops before it would cross it.")
        if not _confirm(f"Start this motion reel (about ${typical:.2f}, at most ${worst:.2f})?", yes):
            print("Nothing was run. Nothing was spent.")
            return 1
    if not config.STUB and not config.ANTHROPIC_API_KEY:
        print("Cannot proceed — ANTHROPIC_API_KEY is not set (every text call goes "
              "through it). Copy .env.example to .env, or run with SHORTS_STUB=1.")
        return 1
    # milliseconds: the start keys this run's entry in cost.json
    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    _RUN["started"] = started
    cursor = usage.mark()
    ctx: dict = {"short_id": topic_short_id}

    def _save(_call=None) -> None:
        # after every call: a run that dies later still has its spend on disk
        # (setup's calls are written with the first call after the id is known)
        if ctx.get("short_id"):
            record_cost(ctx["short_id"], usage.calls_since(cursor), started)

    usage.add_listener(_print_call)
    usage.add_listener(_save)
    try:
        with motion_models.use():
            code = _run(doc_path, topic_short_id, from_stage, force_stage, yes, template,
                        theme, language, ctx, section)
    finally:
        usage.remove_listener(_print_call)
        usage.remove_listener(_save)
        _RUN["started"] = None
        _save()
        if not ctx.get("short_id") and usage.calls_since(cursor):
            print(f"\n  no reel was created; this run's {len(usage.calls_since(cursor))} call(s), "
                  f"${usage.since(cursor)['cost']:.4f}, are in {usage.STORE} only")
    if ctx.get("short_id"):
        data = record_cost(ctx["short_id"], usage.calls_since(cursor), started)
        this = usage.since(cursor)
        print(f"\n=== cost: {ctx['short_id']} ===")
        print(f"  this run: {this['calls']} call(s), ${this['cost']:.4f}"
              + (" (some estimated)" if this.get("estimated") else ""))
        for label, row in data["total"]["by_label"].items():
            print(f"    {label:<28} {row['model']:<30} {row['calls']:>3} call(s)  ${row['cost']:.4f}")
        print(f"  reel total, every run: {data['total']['calls']} call(s), "
              f"${data['total']['cost']:.4f}   ({cost_path(ctx['short_id'])})")
    return code


def _run(doc_path: str, topic_short_id: str | None, from_stage: str | None,
         force_stage: str | None, yes: bool, template: str | None,
         theme: str | None, language: str | None, ctx: dict, section: str | None = None) -> int:

    sections = parse_markdown(doc_path)
    doc_text = Path(doc_path).read_text(encoding="utf-8")
    force_idx = STAGE_ORDER.index(force_stage) if force_stage else len(STAGE_ORDER)
    start_idx = STAGE_ORDER.index(from_stage) if from_stage else 0
    reel_cursor = usage.mark()
    stage_usage: dict[str, dict] = {}

    def _needs(stage: str, output_exists: bool) -> bool:
        idx = STAGE_ORDER.index(stage)
        if idx < start_idx:
            return False
        return idx >= force_idx or not output_exists

    # ---------------------------------------------------------------- setup
    short_id = topic_short_id
    if short_id and not _setup_path(short_id).exists():
        print(f"\nno such motion reel in progress: {short_id} "
              f"({_setup_path(short_id)} does not exist). Omit --topic to start one.")
        return 1
    if short_id is None and start_idx > 0:
        print("--from past setup requires --topic <short_id>")
        return 1
    if short_id and not _needs("setup", True):
        state = _load_setup(short_id)
        print(f"\n=== setup: resumed {short_id} from {_setup_path(short_id)} ===")
        saved = state.get("template", "fix_story")
        if template and template != saved:
            print(f"--template {template} does not match this reel's saved template "
                  f"{saved!r}. Rerun with --force-stage setup to choose again.")
            return 1
    else:
        c = usage.mark()
        state = _run_setup(sections, doc_text, yes, template, section)
        stage_usage["setup"] = usage.since(c)
        if state is None:
            return 1
        if short_id is None:
            short_id = _next_free_motion_id(state["topic"]["id"])
        ctx["short_id"] = short_id
        state["design"] = config.MOTION_DESIGN
        _save_setup(short_id, state)
        print(f"\n=== setup complete: short_id={short_id} ===")

    # ---------------------------------------------------------------- theme
    choice = _load_theme(short_id)
    if _needs("theme", choice is not None):
        c = usage.mark()
        choice = stage_theme(short_id, state, sections, doc_text, yes, reel_cursor,
                             override=theme, language_override=language)
        stage_usage["theme"] = usage.since(c)
        if choice is None:
            return 1
    elif choice is not None:
        if theme and theme != choice.theme:
            print(f"--theme {theme} does not match this reel's approved theme "
                  f"{choice.theme!r}. Rerun with --force-stage theme to choose again.")
            return 1
        print(f"\n=== theme: resumed {choice.theme} from {theme_path(short_id)} ===")
        print(f"  {' '.join(choice.tags)}")

    # --------------------------------------------------------------- script
    script = None
    if _needs("script", motion_path(short_id).exists()):
        c = usage.mark()
        script = stage_script(short_id, state, sections, yes, reel_cursor, choice)
        stage_usage["script"] = usage.since(c)
        if script is None:
            return 1
    else:
        script = MotionScript.model_validate_json(
            motion_path(short_id).read_text(encoding="utf-8"))
        print(f"\n=== script: resumed from {motion_path(short_id)} ===")
        print_shot_list(script)
        print_invented_example(script, sections)

    # --------------------------------------------------------------- scenes
    redone = False
    if _needs("scenes", _scenes_done(script)):
        c = usage.mark()
        script = stage_scenes(short_id, script, yes, reel_cursor)
        stage_usage["scenes"] = usage.since(c)
        if script is None:
            return 1
        redone = True
    else:
        print(f"\n=== scenes: resumed ({sum(1 for s in script.shots if s.scene)} scenes) ===")

    # ---------------------------------------------------------------- voice
    from . import motion_voice
    if _needs("voice", _voice_current(script)):
        manifest = stage_voice(short_id, script)
        if manifest is None:
            return 1
        redone = True
    else:
        manifest = motion_voice.load_manifest(short_id)
        print(f"\n=== voice: resumed from {motion_voice.manifest_path(short_id)} ===")

    # --------------------------------------------------------------- timing
    timing_results: list = []
    if _needs("timing", plan_path(short_id).exists() and not redone):
        done = stage_timing(short_id, script, manifest)
        if done is None:
            return 1
        _, timing_results = done
    else:
        print(f"\n=== timing: resumed from {plan_path(short_id)} ===")

    # ------------------------------------------------------ later phases
    for stage, phase in _NOT_BUILT_YET.items():
        if STAGE_ORDER.index(stage) >= start_idx:
            print(f"\n=== {stage}: not built yet (phase {phase}) — stopping here ===")
            break

    # --------------------------------------------------------------- report
    spend = usage.since(reel_cursor)
    print(f"\n=== report: {short_id} ===")
    print(f"  {motion_path(short_id)}")
    print(f"  template: {script.template}   ~{script.estimated_seconds:.1f}s estimated")
    if choice is not None:
        print(f"  theme: {choice.theme} ({choice.source}) — {choice.reason}")
        print(f"  tags: {' '.join(choice.tags)}   ({tags_path(short_id)})")
    print_fact_sources(fact_sources(script, sections, state))
    print_invented_example(script, sections)
    if plan_path(short_id).exists():
        print(f"  plan: {plan_path(short_id)}   (#motion-reel/{short_id} in the app)")
    if timing_results and not checks.all_passed(timing_results):
        print("  WARNING — on the real audio some scene checks fail (above); rerun with "
              "--force-stage scenes")
    for stage, u in stage_usage.items():
        print(f"  {stage}: {u['calls']} call(s), ${u['cost']:.4f}")
    print(f"  total: {spend['calls']} call(s), ${spend['cost']:.4f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.motion_reel",
        description="Run one motion reel: setup -> theme -> script -> scenes -> voice -> "
                    "timing -> render -> report.")
    p.add_argument("markdown_path", nargs="?", default=None)
    p.add_argument("--topic", dest="topic_short_id", default=None,
                   help="resume an in-progress motion reel by its short_id "
                        "(output/<short_id>/setup.json must already exist)")
    p.add_argument("--from", dest="from_stage", choices=STAGE_ORDER, default=None,
                   help="start here, trusting everything before it is done")
    p.add_argument("--force-stage", dest="force_stage", choices=STAGE_ORDER, default=None,
                   help="redo this stage and every stage after it")
    p.add_argument("--template", choices=MOTION_TEMPLATES, default=None,
                   help="the script template (default: walkthrough when the approved "
                        "teaching approach is process_demonstration, else fix_story)")
    p.add_argument("--theme", choices=motion_themes.registry().ids(), default=None,
                   help="the reel's theme (default: the best fit among the themes that "
                        "pass the fit and variety rules — shorts/motion_themes.yaml)")
    p.add_argument("--language", choices=motion_themes.language_tags(), default=None,
                   help="the course language: tags, variety, badge and voices (default: "
                        "detected from the material)")
    p.add_argument("--section", default=None,
                   help="choose the topic from this section of the document (e.g. 3.4) "
                        "instead of the whole document")
    p.add_argument("--characters", action="store_true",
                   help="draw the speakers as animated characters, one per speaker: the host and "
                        "the language character on a two-speaker reel, the language character as "
                        "narrator on a one-narrator reel (same as MOTION_CHARACTERS=1; off by default)")
    p.add_argument("--character", default=None, metavar="PRESET",
                   help="the character preset that plays the reel's language, for this reel only "
                        "(a language id, or an extra such as riya — shorts/motion_character_"
                        "presets.yaml); implies --characters")
    p.add_argument("--design", choices=config.MOTION_DESIGNS, default=None,
                   help="the look of a NEW reel, saved when it is set up (default: "
                        "MOTION_DESIGN, midnight_lab); a reel keeps the look it was set up with")
    p.add_argument("--check-models", action="store_true",
                   help="make ONE tiny call per model in shorts/motion_models.yaml with its "
                        "reasoning setting, and report OK or the exact error with its cost "
                        "(about $0.03 in all; no document needed). With SHORTS_STUB=1 it "
                        "only shows what it would send.")
    p.add_argument("--estimate", action="store_true",
                   help="print the whole reel's estimated cost per step and model, and stop "
                        "(free — no call is made)")
    p.add_argument("--yes", action="store_true",
                   help="answer every confirmation automatically (still prints "
                        "every pre-flight summary and every pause screen)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check_models:
        from . import motion_models
        rows = motion_models.check_models(dry_run=config.STUB)
        return 0 if motion_models.print_check(rows) else 1
    if not args.markdown_path:
        parser.error("markdown_path is required (except with --check-models)")
    if args.character:
        from . import motion_character_presets
        if args.character not in motion_character_presets.ids():
            print(f"no character preset {args.character!r} — choose from: "
                  f"{', '.join(motion_character_presets.ids())}")
            return 2
    default, default_preset = config.MOTION_CHARACTERS, config.MOTION_CHARACTER_PRESET
    default_design = config.MOTION_DESIGN
    config.MOTION_CHARACTERS = default or args.characters or bool(args.character)
    config.MOTION_CHARACTER_PRESET = args.character or default_preset
    config.MOTION_DESIGN = args.design or default_design
    try:
        return run(args.markdown_path, args.topic_short_id, args.from_stage,
                   args.force_stage, args.yes, args.template, args.theme, args.language,
                   estimate_only=args.estimate, section=args.section)
    finally:
        config.MOTION_CHARACTERS, config.MOTION_CHARACTER_PRESET = default, default_preset
        config.MOTION_DESIGN = default_design


if __name__ == "__main__":
    raise SystemExit(main())
