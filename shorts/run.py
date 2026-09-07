"""
The orchestrator. Plain Python. No framework.

    python -m shorts.run content/session_18_paging.md --limit 1 --no-tts

Stages, in cost order — cheap checks always before paid steps:
  parse -> select -> [ script -> timing -> overlays -> grounding -> visuals ->
  svg -> tts -> assemble -> audit ] -> human gate -> render
"""
import argparse, io, json, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .schema import ShortUnit, TopicList
from .parse import parse_markdown, find_section
from .skills.select import select_topics
from .skills.understand import understand, evidence_notes
from .skills.script import write_script
from .skills.visuals import design_visuals, render_diagrams
from .skills.audit import audit
from . import checks, config

MAX_SCRIPT_RETRIES = 3

class _StdoutRouter(io.TextIOBase):
    """
    A sys.stdout stand-in that sends each thread's writes to that thread's buffer.

    build_one narrates with print(), and five of them running at once need five
    separate transcripts. contextlib.redirect_stdout looks like the tool for that
    and is not: it swaps the single global sys.stdout, so concurrent workers
    overwrite one another's redirect and lines land in whichever buffer was
    installed last. The result is a per-short log that is confidently wrong about
    which short it describes.

    Routing is thread-local, so a worker can only ever write to its own buffer, and
    anything printed from a thread that has not claimed one (or after it releases)
    falls through to the real stdout rather than vanishing.
    """

    def __init__(self, fallback):
        self._fallback = fallback
        self._local = threading.local()

    def route(self, buf) -> None:
        self._local.buf = buf

    def write(self, text: str) -> int:
        buf = getattr(self._local, "buf", None)
        return (self._fallback if buf is None else buf).write(text)

    def flush(self) -> None:
        self._fallback.flush()


#: How many shorts to build at once. Each one is a handful of sequential model calls
#: with long waits in between, so the work is latency-bound rather than CPU-bound and
#: a small pool is plenty. Capped rather than unbounded because every worker is
#: hitting the same gateway, and five concurrent requests is well inside a rate limit
#: where fifty is not.
MAX_BUILD_WORKERS = 5


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

    # SKILL 1b — read the section before writing anything, ONCE.
    #
    # Deliberately outside the retry loop below. Nothing about what a section
    # teaches changes between attempt 1 and attempt 3 — the graders reject wording,
    # pacing and citation, none of which this answers — so putting it inside the
    # loop would buy three identical readings of a fixed text at three times the
    # price. That is the whole reason it is a separate step and not a longer script
    # prompt.
    #
    # Never fatal, on the same terms as plan_strategy: a short with no understanding
    # is written exactly the way it was written before this step existed. The script
    # prompt does not consume it yet, so today a failure here costs only the log
    # line — but the degradation is written now, while the reasoning is in view,
    # rather than discovered later by a bad minute on the gateway.
    understanding = None
    try:
        understanding = understand(topic, section)
        print(f"    understood: {understanding.core_concept[:74]}")
        print(f"      objective: {understanding.learning_objective[:72]}")
        if understanding.cannot_answer:
            print(f"      section does NOT establish: "
                  f"{'; '.join(understanding.cannot_answer)[:70]}")
        for note in evidence_notes(understanding, section):
            print(f"      ~ {note}")
    except Exception as e:
        print(f"    understanding for {topic.id} unavailable "
              f"({type(e).__name__}: {str(e)[:90]}) — writing from the section alone")

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

    # Designed, graded and redesigned — the same shape as the script loop above.
    # A short whose frames all pass costs exactly one call, as before.
    visuals, design_problems = design_visuals(script, section, draw=do_svg)
    print(f"    visuals: {[(v.ref, v.type) for v in visuals.values()]}")
    for problem in design_problems:
        print(f"    ! visuals still failing after redesign — {problem[:140]}")

    unit = ShortUnit(
        short_id=script.short_id,
        session_id=session_id,
        source_section_id=section.section_id,
        question=script.question,
        estimated_seconds=script.estimated_seconds,
        beats=script.beats,
        visuals=visuals,
        understanding=understanding,
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

    # SHORTS ARE BUILT SIDE BY SIDE, not one after another.
    #
    # This loop was sequential and the web path was not, so `run.py --topics 5` took
    # five times as long as finalizing the same five shorts through the browser —
    # about ten minutes against two. Nothing about a short depends on another one:
    # each is a script call, a design call and a judge call against its own section.
    # The only reason it was serial is that it was written before the web flow.
    #
    # Output is captured per topic and printed as a block when that topic finishes,
    # because build_one narrates every grader and five narrations interleaved line by
    # line is unreadable.
    workers = min(MAX_BUILD_WORKERS, max(1, len(topics)))
    print(f"building {len(topics)} short(s), {workers} at a time")

    # contextlib.redirect_stdout CANNOT BE USED HERE, and using it was a real bug.
    # It rebinds sys.stdout process-wide, so five workers entering it concurrently
    # each replace the others' target: the printed blocks came out interleaved into
    # the wrong buffers. The run above reported a block headed "page_fault_handling"
    # that contained the TLB short's visuals and the fragmentation short's judge
    # notes — every line real, every line filed under the wrong short. Logs that
    # lie are worse than logs that interleave, because they read as correct.
    router = _StdoutRouter(sys.stdout)

    def build(topic):
        buf = io.StringIO()
        router.route(buf)                    # per-thread, so workers cannot collide
        try:
            section = find_section(sections, topic.source_section_id)
            unit = build_one(topic, section, session_id, not args.no_tts,
                             not args.no_svg, document=doc_text)
        except KeyError as e:
            return topic, None, f"  skipping {topic.id}: {e}\n"
        except Exception as e:
            # One short must not take down the other four; they are paid for.
            return topic, None, buf.getvalue() + f"  ! {topic.id}: {type(e).__name__}: {e}\n"
        finally:
            router.route(None)
        return topic, unit, buf.getvalue()

    units = []
    real_stdout = sys.stdout
    sys.stdout = router
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(build, topics))
    finally:
        sys.stdout = real_stdout
    for topic, unit, log in results:
        # No header printed here: build_one already opens with its own "=== <id> — ".
        print(log, end="")
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
