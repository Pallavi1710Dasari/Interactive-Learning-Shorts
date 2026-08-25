"""
The orchestrator. Plain Python. No framework.

    python -m shorts.run content/session_18_paging.md --limit 1 --no-tts

Stages, in cost order — cheap checks always before paid steps:
  parse -> select -> [ script -> timing -> overlays -> grounding -> visuals ->
  svg -> tts -> assemble -> audit ] -> human gate -> render
"""
import argparse, json, sys
from pathlib import Path

from .schema import ShortUnit, TopicList
from .parse import parse_markdown, find_section
from .skills.select import select_topics
from .skills.script import write_script
from .skills.visuals import spec_visuals, render_diagrams
from .skills.audit import audit
from . import checks, config

MAX_SCRIPT_RETRIES = 3


def _save_rejected(topic, section, attempt: int, script, results) -> Path:
    """
    Freeze a failed script attempt so it can become an eval fixture.

    Rejected attempts were the only pipeline output that was never kept, and they
    are the ones worth keeping: a script the graders rejected is exactly the
    "frozen failure" an eval case is built from (README B.1). Two topics were
    abandoned in the first real run and nothing survived to diagnose them.

    `script` is written as a bare Script, which is the shape evals/run_evals.py
    loads — so promoting one to a fixture is a single command:

        jq .script output/rejected/<file>.json > evals/fixtures/<name>.json

    Everything else in the file is the context needed to write the `why` field:
    which section it came from, which attempt it was, and what each grader said.
    """
    outdir = config.OUTPUT_DIR / "rejected"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{topic.id}_attempt{attempt}.json"
    path.write_text(json.dumps({
        "topic_id": topic.id,
        "topic": topic.topic,
        "difficulty": topic.difficulty,
        "section_id": section.section_id,
        "section_title": section.title,
        "attempt": attempt,
        "max_attempts": MAX_SCRIPT_RETRIES,
        "estimated_seconds": script.estimated_seconds,
        "word_count": script.word_count,
        "failed": [{"grader": r.name, "reason": r.reason, "details": r.details}
                   for r in results if not r.passed],
        "passed": [r.name for r in results if r.passed],
        "script": script.model_dump(),
        "source_text": section.text,
    }, indent=2))
    return path


def build_one(topic, section, session_id: str, do_tts: bool, do_svg: bool,
              document: str | None = None) -> ShortUnit | None:
    print(f"\n=== {topic.id} — {topic.topic[:60]}")
    feedback = None

    for attempt in range(1, MAX_SCRIPT_RETRIES + 1):
        script = write_script(topic, section, feedback, document=document)
        results = checks.run_script_graders(script, section.text, doc_text=document)
        for r in results:
            print(f"    {r}")

        if checks.all_passed(results):
            break

        # Every failed attempt is frozen, including the last one before we give up.
        saved = _save_rejected(topic, section, attempt, script, results)
        feedback = "\n".join(f"- {r.name}: {r.reason}" for r in results if not r.passed)
        print(f"    retry {attempt}/{MAX_SCRIPT_RETRIES} — froze attempt to rejected/{saved.name}")
    else:
        print(f"    GIVING UP on {topic.id} after {MAX_SCRIPT_RETRIES} attempts")
        return None

    print(f"    script ok: {script.estimated_seconds}s, {script.word_count} words")

    visuals = spec_visuals(script, section)
    if do_svg:
        visuals = render_diagrams(visuals, script, section)
    print(f"    visuals: {[(v.ref, v.type) for v in visuals.values()]}")

    unit = ShortUnit(
        short_id=script.short_id,
        session_id=session_id,
        source_section_id=section.section_id,
        question=script.question,
        estimated_seconds=script.estimated_seconds,
        beats=script.beats,
        visuals=visuals,
    )

    if do_tts:
        # Through voice.synthesize, not tts.synthesize: a missing or expired key
        # used to raise here and take down the whole run, losing every short built
        # before it. A voice is an enhancement, so its absence downgrades to the
        # browser voice instead of failing.
        from . import voice
        ok, why = voice.configured()
        if not ok:
            print(f"    no recorded voice ({why}) — the player will narrate in-browser")
        else:
            unit.audio = voice.synthesize(script)
            if unit.audio:
                print(f"    audio: {unit.audio.duration_seconds}s real duration")

    grader_results, report = audit(script, section.text, unit)
    for r in grader_results:
        print(f"    {r}")
    if report:
        unit.eval = report
        unit.status = "audited" if report.passed else "rejected"
        print(f"    judge: faith={report.faithfulness} clarity={report.clarity} "
              f"pace={report.pace} -> {'PASS' if report.passed else 'REJECT'}")
        for p in report.problems:
            print(f"      ! {p}")

    return unit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--limit", type=int, default=None, help="only build N shorts")
    ap.add_argument("--topics", type=int, default=5, help="how many topics to select")
    ap.add_argument("--no-tts", action="store_true", help="skip voice generation")
    ap.add_argument("--no-svg", action="store_true", help="skip diagram generation")
    ap.add_argument("--gate-topics", action="store_true",
                    help="stop after topic selection so a human can edit the list")
    ap.add_argument("--topics-file",
                    help="skip selection and read an already-approved topics.json")
    args = ap.parse_args()

    # A misconfigured judge cannot be noticed from its output — it approves
    # everything — so it has to be said out loud before the run starts.
    for warning in config.model_warnings():
        print(f"!! {warning}\n")

    sections = parse_markdown(args.doc)
    session_id = Path(args.doc).stem
    doc_text = Path(args.doc).read_text(encoding="utf-8")
    print(f"parsed {len(sections)} sections: {[s.section_id for s in sections]}")

    # A stub run writes somewhere else, and that is not cosmetic. topics.json is
    # the human-approved list — the one file here that represents a decision rather
    # than an output — and `SHORTS_STUB=1` selection produces placeholders like
    # "How does why paging exists work?". One stub run to exercise the renderer
    # silently replaced a real approved list with those, and every later
    # `--topics-file output/topics.json` build faithfully made shorts out of them.
    # Nothing warned, because reading the file worked perfectly.
    topics_path = config.OUTPUT_DIR / ("topics.stub.json" if config.STUB else "topics.json")

    if args.topics_file:
        topic_list = TopicList(**json.loads(Path(args.topics_file).read_text()))
        print(f"loaded {len(topic_list.topics)} approved topics from {args.topics_file}")
    else:
        topic_list = select_topics(sections, target=args.topics)
        print(f"selected {len(topic_list.topics)} topics")
        topics_path.write_text(topic_list.model_dump_json(indent=2))

    for t in topic_list.topics:
        print(f"  [{t.source_section_id}] {t.id}: {t.topic}")

    # Step 3's human check. Everything downstream inherits these choices, so it is
    # far cheaper to fix a bad topic here than to regenerate five scripts later.
    if args.gate_topics and not args.topics_file:
        print(f"\nwrote {topics_path}")
        print("TOPIC GATE — read that file, delete the topics you don't want, then:")
        print(f"  python -m shorts.run {args.doc} --topics-file {topics_path}")
        return

    topics = topic_list.topics[: args.limit] if args.limit else topic_list.topics
    units = []

    for topic in topics:
        try:
            section = find_section(sections, topic.source_section_id)
        except KeyError as e:
            print(f"  skipping {topic.id}: {e}")
            continue
        unit = build_one(topic, section, session_id, not args.no_tts, not args.no_svg,
                         document=doc_text)
        if unit:
            units.append(unit)

    outdir = config.OUTPUT_DIR
    for u in units:
        (outdir / f"{u.short_id}.json").write_text(u.model_dump_json(indent=2))

    manifest = outdir / "manifest.json"
    manifest.write_text(json.dumps(
        [{"short_id": u.short_id, "question": u.question, "status": u.status,
          "seconds": u.estimated_seconds} for u in units], indent=2))

    print(f"\nwrote {len(units)} unit(s) to {outdir}")
    print("REVIEW THESE BEFORE RENDERING. Nothing renders until you set status=approved.")
    print("  python -m shorts.review          # step 10, the human gate")
    print("  python -m shorts.render <id>     # step 11, minutes per video")


if __name__ == "__main__":
    main()
