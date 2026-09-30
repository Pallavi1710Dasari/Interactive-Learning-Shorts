"""
Run one MOTION reel end to end (REEL_STYLE=motion — RESTYLE_TO_MOTION_REELS.md):

    python -m shorts.motion_reel content/react_usestate_basics.md
    python -m shorts.motion_reel <doc.md> --topic <short_id>          # resume
    python -m shorts.motion_reel <doc.md> --topic <id> --force-stage script

Stages: setup -> script -> scenes -> voice -> timing -> render -> report.
Mirrors shorts/story_reel.py's stage and resume behaviour on purpose, so one
runbook habit covers both: a stage runs when its artifact is missing, --from
trusts everything before it, --force-stage redoes that stage and every later
one, and --yes answers every confirmation (but never skips a pre-flight
printout).

THREE HUMAN GATES, all before anything is voiced or drawn:
  1. topic selection — the same approve/reject/regenerate gate as
     `python -m shorts.run --gate-topics` (review.run_question_gate);
  2. teaching approach — the same gate as --gate-teaching-approach
     (review.run_teaching_approach_gate);
  3. the shot list — beat, speech, captions and visual for every shot, shown
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
from . import workflow as question_workflow
from .parse import find_section, parse_markdown, story_evidence_pool
from .schema import (MotionScript, QuestionWorkflow, SectionUnderstanding, Topic,
                     motion_plain_text)
from .skills.script import write_motion_script
from .skills.select import select_topics_with_selections
from .skills.understanding import understanding_for

STAGE_ORDER = ["setup", "script", "scenes", "voice", "timing", "render", "report"]
MONEY_STAGES = {"script", "scenes"}

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


def _setup_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "setup.json"


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


def _run_setup(sections: list, doc_text: str, yes: bool) -> dict | None:
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

    _pool, pool_ids = story_evidence_pool(
        sections, topic.source_section_id,
        teaching_sequence=understanding.teaching_sequence if understanding else None)
    return {
        "topic": topic.model_dump(),
        "section_id": section.section_id,
        "understanding": understanding.model_dump() if understanding else None,
        "workflow": wf.model_dump(),
        "pool_ids": list(pool_ids),
        "next_topic": next_topic_for(sections, section.section_id, list(pool_ids)),
    }


def _save_setup(short_id: str, state: dict) -> None:
    path = _setup_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_setup(short_id: str) -> dict:
    return json.loads(_setup_path(short_id).read_text(encoding="utf-8"))


# =================================================================== script

def print_shot_list(script: MotionScript, results: list | None = None) -> None:
    """The shot-list gate's screen: every shot's beat, speech, captions and
    visual. Also what `--from script` prints for an approved script."""
    print(f"\n=== Shot list: {script.short_id} ({len(script.shots)} shots, "
          f"~{script.estimated_seconds:.1f}s) ===")
    print(f"concept: {script.concept_name}   promise: {script.promise!r}")
    print(f"hook question: {script.hook_question}")
    print(f"icons: {[f'{i.name} ({i.label})' for i in script.icon_vocabulary]}")
    for s in script.shots:
        print(f"\n  {s.id}  {s.beat:<9} ~{s.estimated_seconds:.1f}s")
        print(f"      speech:   {s.speech}")
        print(f"      captions: {' | '.join(motion_plain_text(c.text) for c in s.captions)}")
        print(f"      visual:   {s.visual}")
        for line in s.code:
            print(f"      code:     {line}")
    print("\n  recap:")
    for t in script.takeaways:
        print(f"      [{t.icon}] {t.line} — {t.sub}")
    print(f"  series: {script.series!r}   next up: {script.next_topic or '(none)'}")
    if results is not None:
        print("\ncheck results:")
        for r in results:
            print(f"  {r}")


def stage_script(short_id: str, state: dict, sections: list, yes: bool,
                 reel_cursor: int) -> MotionScript | None:
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

    script, results = write_motion_script(
        topic, section, short_id=short_id, source_text=source_text,
        understanding=understanding, approach=wf.approved_teaching_approach,
        next_topic=state.get("next_topic", ""))
    if script is None:
        print("  GIVING UP — no script passed the motion graders:")
        for r in results:
            print(f"    {r}")
        return None

    print_shot_list(script, results)
    if not _confirm("Approve shot list?", yes):
        print(f"Stopped after script — rerun with --topic {short_id} to continue "
              f"(the script was NOT saved — declining means try again, not skip ahead).")
        return None
    # Written ONLY on approval — same reasoning as story_reel.stage_mapping.
    motion_path(short_id).write_text(script.model_dump_json(indent=2), encoding="utf-8")
    return script


# ======================================================================= run

def run(doc_path: str, topic_short_id: str | None, from_stage: str | None,
        force_stage: str | None, yes: bool) -> int:
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
    else:
        c = usage.mark()
        state = _run_setup(sections, doc_text, yes)
        stage_usage["setup"] = usage.since(c)
        if state is None:
            return 1
        if short_id is None:
            short_id = _next_free_motion_id(state["topic"]["id"])
        _save_setup(short_id, state)
        print(f"\n=== setup complete: short_id={short_id} ===")

    # --------------------------------------------------------------- script
    script = None
    if _needs("script", motion_path(short_id).exists()):
        c = usage.mark()
        script = stage_script(short_id, state, sections, yes, reel_cursor)
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
    for stage, u in stage_usage.items():
        print(f"  {stage}: {u['calls']} call(s), ${u['cost']:.4f}")
    print(f"  total: {spend['calls']} call(s), ${spend['cost']:.4f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.motion_reel",
        description="Run one motion reel: setup -> script -> scenes -> voice -> "
                    "timing -> render -> report.")
    p.add_argument("markdown_path")
    p.add_argument("--topic", dest="topic_short_id", default=None,
                   help="resume an in-progress motion reel by its short_id "
                        "(output/<short_id>/setup.json must already exist)")
    p.add_argument("--from", dest="from_stage", choices=STAGE_ORDER, default=None,
                   help="start here, trusting everything before it is done")
    p.add_argument("--force-stage", dest="force_stage", choices=STAGE_ORDER, default=None,
                   help="redo this stage and every stage after it")
    p.add_argument("--yes", action="store_true",
                   help="answer every confirmation automatically (still prints "
                        "every pre-flight summary and every pause screen)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.markdown_path, args.topic_short_id, args.from_stage,
               args.force_stage, args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
