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

PHASE 1 (this commit) builds setup and script. scenes/voice/timing/render
report "not built yet" and stop cleanly; they arrive in phases 3 and 4.

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
from .skills.script import write_motion_script
from .skills.theme import MAX_THEME_ATTEMPTS, SYSTEM_MOTION_THEME, choose_theme
from .skills.select import select_topics_with_selections
from .skills.understanding import understanding_for

STAGE_ORDER = ["setup", "theme", "script", "scenes", "voice", "timing", "render", "report"]
MONEY_STAGES = {"theme", "script", "scenes"}

#: Stages that exist in STAGE_ORDER (so --from / --force-stage accept them and
#: resume math is already right) but are built in a later phase.
_NOT_BUILT_YET = {"scenes": 3, "voice": 3, "timing": 3, "render": 4}

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


def _money_gate(stage: str, short_id: str, plan: list, yes: bool, reel_cursor: int) -> bool:
    """Same pre-spend gate as story_reel._money_gate: print + persist the
    pre-flight plan (always, even under --yes), refuse past MAX_REEL_USD,
    then ask."""
    built = preflight.build_plan(f"motion_{stage}", short_id, plan)
    preflight.print_plan(built)
    preflight.write_preflight_json(short_id, built)
    spent = usage.since(reel_cursor)["cost"]
    projected = round(spent + built["total_cost"], 4)
    if projected > config.MAX_REEL_USD:
        print(f"  MAX_REEL_USD (${config.MAX_REEL_USD:.2f}) would be exceeded: "
              f"${spent:.4f} spent on this reel so far + ${built['total_cost']:.4f} "
              f"for {stage} = ${projected:.4f}. Stopping before any call.")
        return False
    return _confirm(f"Proceed with the {stage} stage (est. ${built['total_cost']:.4f})?", yes)


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
    return (answer, "reviewer") if answer else (default, "default")


def _run_setup(sections: list, doc_text: str, yes: bool,
               template_override: str | None = None) -> dict | None:
    """Select a topic, gate it, frame it, pick a teaching approach, gate that.
    Returns the setup state, or None when a human declined (or no human was
    available to decide)."""
    _topics, _notes, selections = select_topics_with_selections(sections, target=1)
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
    who = (" / ".join(f"{sp.role} = {sp.name} ({sp.avatar})"
                      for sp in motion_themes.cast_speakers(spec, choice.language))
           if spec.two_speaker else "one narrator, no avatar")
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
    if not override and len(eligible) > 1:
        plan = [preflight.ModelPlan(
            "motion_theme", config.MODEL_GENERATOR, MAX_THEME_ATTEMPTS,
            preflight.text_cost_per_call(config.MODEL_GENERATOR,
                                         (len(SYSTEM_MOTION_THEME) + len(source_text)) // 3
                                         + 120 * len(eligible), 300))]
        if not _money_gate("theme", short_id, plan, yes, reel_cursor):
            return None
    try:
        choice = choose_theme(section, source_text=source_text, approach=approach,
                              language=language, history=history, template_pin=pin,
                              override=override)
    except ValueError as e:
        print(f"\n  {e}")
        return None
    print_theme(choice, how, history)
    tag_check = checks.check_motion_tags(choice.tags, source_text)
    print(f"  {tag_check}")
    if not tag_check.passed:
        print("  GIVING UP — the tags are not valid (see above).")
        return None
    if not _confirm("Approve theme?", yes):
        print(f"Stopped at the theme — nothing saved. Rerun with --topic {short_id} to see "
              f"this pause again, or --topic {short_id} --theme <id> to choose it yourself "
              f"({', '.join(motion_themes.registry().ids())}).")
        return None
    path = theme_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(choice.model_dump_json(indent=2), encoding="utf-8")
    concepts = [t.lstrip("#") for t in choice.tags[2:]]
    tags = MotionTags(short_id=short_id, language=choice.language, theme=choice.theme,
                      concepts=concepts, tags=choice.tags,
                      created_at=_now_iso())
    tags_path(short_id).write_text(tags.model_dump_json(indent=2), encoding="utf-8")
    return choice


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# =================================================================== script

def fact_sources(script: MotionScript, sections: list, state: dict) -> list[dict]:
    """Every number and long term the script says, with the section it came
    from (checks.motion_fact_sources), against this reel's own main and
    supporting sections."""
    main = [(sid, find_section(sections, sid).text) for sid in state["pool_ids"]]
    support = [(sid, find_section(sections, sid).text) for sid in state.get("support_ids", [])]
    return checks.motion_fact_sources(script, main, support)


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
        print("speakers: " + ", ".join(f"{sp.role} = {sp.name} ({sp.avatar}, voice "
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
    plan = [preflight.ModelPlan(
        "motion_script", config.MODEL_GENERATOR,
        config.MAX_MOTION_SCRIPT_RETRIES * (1 + config.MAX_MOTION_HOOK_FIX_RETRIES),
        preflight.text_cost_per_call(config.MODEL_GENERATOR, 4000, 3500))]
    if not _money_gate("script", short_id, plan, yes, reel_cursor):
        return None

    topic = Topic(**state["topic"])
    section = find_section(sections, state["section_id"])
    understanding = (SectionUnderstanding(**state["understanding"])
                     if state.get("understanding") else None)
    wf = QuestionWorkflow(**state["workflow"])
    source_text = "\n\n".join(find_section(sections, sid).text for sid in state["pool_ids"])
    supporting_text = "\n\n".join(find_section(sections, sid).text
                                   for sid in state.get("support_ids", []))

    script, results = write_motion_script(
        topic, section, short_id=short_id, source_text=source_text,
        understanding=understanding, approach=wf.approved_teaching_approach,
        next_topic=state.get("next_topic", ""),
        template=theme.template if theme else state.get("template", "fix_story"),
        supporting_text=supporting_text,
        theme=theme.theme if theme else None,
        language=theme.language if theme else None)
    if script is None:
        print("  GIVING UP — no script passed the motion graders:")
        for r in results:
            print(f"    {r}")
        return None

    print_shot_list(script, results)
    facts = fact_sources(script, sections, state)
    print_fact_sources(facts)
    if not _confirm("Approve shot list?", yes):
        print(f"Stopped after script — rerun with --topic {short_id} to continue "
              f"(the script was NOT saved — declining means try again, not skip ahead).")
        return None
    # Written ONLY on approval — same reasoning as story_reel.stage_mapping.
    motion_path(short_id).write_text(script.model_dump_json(indent=2), encoding="utf-8")
    _facts_path(short_id).write_text(json.dumps(facts, indent=2), encoding="utf-8")
    return script


# ======================================================================= run

def run(doc_path: str, topic_short_id: str | None, from_stage: str | None,
        force_stage: str | None, yes: bool, template: str | None = None,
        theme: str | None = None, language: str | None = None) -> int:
    print(_MOTION_MODE_BANNER)
    if not config.STUB and not config.ANTHROPIC_API_KEY:
        print("Cannot proceed — ANTHROPIC_API_KEY is not set (every text call goes "
              "through it). Copy .env.example to .env, or run with SHORTS_STUB=1.")
        return 1

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
        state = _run_setup(sections, doc_text, yes, template)
        stage_usage["setup"] = usage.since(c)
        if state is None:
            return 1
        if short_id is None:
            short_id = _next_free_motion_id(state["topic"]["id"])
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
    for stage, u in stage_usage.items():
        print(f"  {stage}: {u['calls']} call(s), ${u['cost']:.4f}")
    print(f"  total: {spend['calls']} call(s), ${spend['cost']:.4f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.motion_reel",
        description="Run one motion reel: setup -> theme -> script -> scenes -> voice -> "
                    "timing -> render -> report.")
    p.add_argument("markdown_path")
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
                   help="the course language for tags, variety and avatars (default: "
                        "detected from the material)")
    p.add_argument("--yes", action="store_true",
                   help="answer every confirmation automatically (still prints "
                        "every pre-flight summary and every pause screen)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.markdown_path, args.topic_short_id, args.from_stage,
               args.force_stage, args.yes, args.template, args.theme, args.language)


if __name__ == "__main__":
    raise SystemExit(main())
