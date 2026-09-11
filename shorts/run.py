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

from .schema import ShortUnit, TopicList, QuestionWorkflow
from .parse import parse_markdown, find_section
from .skills.select import select_topics_with_selections
from .skills.script import write_script
from .skills.understanding import understanding_for
from .skills.visuals import design_visuals, render_diagrams
from .skills.audit import audit
from . import checks, config, review, revision, workflow as question_workflow

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

#: server.py's /api/finalize has overlapped voice with visuals for a while (see
#: its build_one: "the voice depends only on the words, so it records while the
#: visuals are being designed"). This CLI path did the same two calls strictly
#: sequentially — design_visuals, then voice.synthesize, then the judge — for no
#: reason other than having been written first. One small shared pool, matching
#: server.py's _JUDGE_POOL in spirit: TTS is latency-bound (a network call to a
#: voice provider), so a handful of workers is plenty even with MAX_BUILD_WORKERS
#: short-builders each wanting one.
_TTS_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tts")


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


def _realign_topic(topic, section, understanding, document):
    """
    Rewrite a topic's question (and concept) to match the section's own core
    idea, when checks.check_topic_matches_understanding found the two talking
    about different things.

    REUSES write_script ITSELF — the same underlying function server.py's
    POST /api/regenerate calls for a human's "change only the question" edit —
    rather than inventing a second way to ask a model for a question. There is
    no script yet to edit at this point in build_one (this runs before the retry
    loop below even starts), so the call is thrown away except for its
    `.question`: the beats it writes are never graded and never shipped, and
    the ordinary retry loop that follows writes the real script exactly as it
    always has, just handed a topic that already agrees with the reading.

    ONE CALL, ONLY HERE. This only runs on the rarer branch where the free stem
    check above found zero overlap — the common case, a topic already aligned
    with core_idea, never reaches this function and costs nothing extra.

    `concept` is set to understanding.core_idea itself rather than a trimmed
    noun phrase. That is a looser shape than schema.Topic.concept's own
    "short noun phrase" — asking a model to also compress it would be a second
    call for a field nothing downstream reads except select.py's own dedup pass
    (already finished by the time build_one runs) and this same check, which
    trivially agrees with it once concept IS core_idea.

    Failure here downgrades to a warning, not an exception: an unreconciled
    topic is the status quo this function exists to improve on, not a state
    that justifies losing the whole short over.
    """
    instruction = (
        "This topic's question may be drifting from what its own section "
        "actually teaches. Write the interviewer's question so it asks about "
        f"the section's real central idea instead: {understanding.core_idea}\n"
        "Keep it one plain question a beginner could repeat back, following the "
        "same rules as any other question here: start with What/Why/How/Which/"
        "When/Where, never a yes/no opener, exactly one question mark."
    )
    try:
        realigned = write_script(topic, section, instruction,
                                 document=document, understanding=understanding)
    except Exception as e:
        print(f"      ! could not realign {topic.id} to the section's core idea "
              f"({type(e).__name__}: {e}) — writing from the original question")
        return topic

    print(f"      realigned question: {realigned.question[:74]}")
    return topic.model_copy(update={
        "topic": realigned.question,
        "concept": understanding.core_idea,
    })


def build_one(topic, section, session_id: str, do_tts: bool, do_svg: bool,
              document: str | None = None,
              router: _StdoutRouter | None = None,
              buf=None) -> ShortUnit | None:
    """
    `router`/`buf` are optional and exist for exactly one reason: TTS now runs on
    a _TTS_POOL thread rather than this one (see below), and that thread has never
    called router.route(), so anything it prints falls through to the real stdout
    instead of this topic's buffer — not a crash, _StdoutRouter is built to
    degrade that way, but it is the interleaved-logs defect the router exists to
    prevent, just relocated to a second thread. Passing the caller's own buf lets
    the TTS call route into it too. A caller with no router (there are none today,
    but nothing requires one) gets voice.synthesize's prints on real stdout,
    exactly as they would have before this change existed.
    """
    print(f"\n=== {topic.id} — {topic.topic[:60]}")

    # FREE AND FIRST. Does the section have enough distinct sentences to cite,
    # whatever it turns out to teach? Answerable from the raw text with no model
    # call, so it runs before the understanding call below spends the first of what
    # would otherwise be four paid calls (one reading, three script attempts) on a
    # section that was never going to satisfy check_source_quotes' distinctness
    # rule. See checks.check_section_richness for the real case that motivated it.
    richness = checks.check_section_richness(section.text)
    if not richness.passed:
        print(f"    skipping {topic.id} — {richness.reason}")
        return None

    # SKILL 1b — read the section before writing anything, ONCE.
    #
    # Deliberately outside the retry loop below. Nothing about what a section
    # teaches changes between attempt 1 and attempt 3 — the graders reject wording,
    # pacing and citation, none of which this answers — so putting it inside the
    # loop would buy three identical readings of a fixed text at three times the
    # price. That is the whole reason it is a separate step and not a longer script
    # prompt.
    #
    feedback = None

    # READ THE SECTION ONCE, OUTSIDE THE LOOP. The retry below re-runs write_script
    # with a grader's complaint attached, and what the section teaches has not
    # changed between attempts — so re-reading it would buy a second opinion on a
    # settled question at the price of another call. Cached per section too, so a
    # deck with several shorts filed under one section pays for one reading.
    # None when the reading failed; write_script then behaves exactly as before.
    understanding = understanding_for(section, document=document)
    if understanding:
        print(f"    understood: {understanding.core_idea[:74]}")
        print(f"      teaching: "
              f"{' -> '.join(t.concept for t in understanding.teaching_sequence)[:70]}")
        # Every plan is nullable BY DESIGN — understand() sets one to None when it
        # fails its grader, so "quarantined" is a normal state here and not an
        # error. Reading .kind off it unguarded took the whole short down.
        _need = lambda p, a: getattr(p, a, None) or "quarantined"
        print(f"      hook={_need(understanding.hook_plan, 'kind')} "
              f"example={_need(understanding.example_plan, 'need')} "
              f"misconception={_need(understanding.confusion_plan, 'need')}")
        if understanding.cannot_answer:
            print(f"      section does NOT establish: "
                  f"{'; '.join(understanding.cannot_answer)[:70]}")
        # The depth gate, on the validated reading rather than on select's guess.
        # Printed, not enforced: it grades the TOPIC CHOICE, and dropping a short
        # on it would shrink the deck for a judgement made from four booleans. The
        # length grader below is still the hard gate on the script itself.
        depth = checks.check_plan_depth(understanding)
        if not depth.passed:
            print(f"      ~ {depth.reason}")

        # THE RECONCILIATION CHECK. depth, just above, asks whether the reading
        # found enough material; it has never asked whether the topic select.py
        # handed us is even the topic understanding_for just validated for THIS
        # section. See checks.check_topic_matches_understanding for why that gap
        # existed and why zero stem overlap is a real signal, not noise. Free and
        # first — a real mismatch is fixed here, once, rather than shipped and
        # printed as a warning nobody acts on.
        match = checks.check_topic_matches_understanding(topic, understanding)
        if not match.passed:
            print(f"      ~ {match.reason}")
            topic = _realign_topic(topic, section, understanding, document)
    else:
        print(f"    understanding for {topic.id} unavailable "
              f"— writing from the section alone")

    for attempt in range(1, MAX_SCRIPT_RETRIES + 1):
        script = write_script(topic, section, feedback, document=document,
                              understanding=understanding)
        # The SAME understanding that wrote the script grades it. Both sides of the
        # loop read one object, so a retry is judged against the plan it was shown.
        results = checks.run_script_graders(script, section.text, doc_text=document,
                                            understanding=understanding)
        for r in results:
            print(f"    {r}")

        if checks.all_passed(results):
            break

        # Every failed attempt is frozen, including the last one before we give up.
        saved = _save_rejected(topic, section, attempt, script, results)
        # Grouped by revision area, correctness first, with the parts that already
        # work named as things to keep. Same results, same retry count — see
        # shorts/revision.py for why the flat list was costing attempts.
        feedback = revision.feedback_for(results)
        print(f"    retry {attempt}/{MAX_SCRIPT_RETRIES} — froze attempt to rejected/{saved.name}")
    else:
        print(f"    GIVING UP on {topic.id} after {MAX_SCRIPT_RETRIES} attempts")
        return None

    print(f"    script ok: {script.estimated_seconds}s, {script.word_count} words")

    # TTS ONLY NEEDS THE SCRIPT, so it starts here rather than after visuals —
    # the same overlap server.py's /api/finalize already exploits (see its
    # build_one: "the voice depends only on the words"). Submitted to _TTS_POOL
    # before the one paid visual call rather than run after it, so the wall-clock
    # cost of the two is max(voice, visuals) instead of voice + visuals.
    recording = None
    if do_tts:
        # Through voice.synthesize, not tts.synthesize: a missing or expired key
        # used to raise here and take down the whole run, losing every short built
        # before it. A voice is an enhancement, so its absence downgrades to the
        # browser voice instead of failing. Checked here, synchronously, so a
        # misconfigured voice is reported once rather than inside the pool thread.
        from . import voice
        ok, why = voice.configured()
        if not ok:
            print(f"    no recorded voice ({why}) — the player will narrate in-browser")
        else:
            def _synth(_router=router, _buf=buf):
                # See build_one's own docstring: routes this pool thread's prints
                # into the same per-topic buffer the caller is already using.
                if _router is not None:
                    _router.route(_buf)
                try:
                    return voice.synthesize(script)
                finally:
                    if _router is not None:
                        _router.route(None)
            recording = _TTS_POOL.submit(_synth)

    # Designed, graded and redesigned — the same shape as the script loop above.
    # A short whose frames all pass costs exactly one call, as before.
    visuals, design_problems = design_visuals(script, section, draw=do_svg,
                                              understanding=understanding)
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

    if recording is not None:
        unit.audio = recording.result()
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
                    help="run Step 3's question gate after selection — "
                        "interactive approve/reject/regenerate in a terminal, or "
                        "written to a file to decide later (see --selections-file)")
    ap.add_argument("--topics-file",
                    help="skip selection and build from an already-approved "
                        "topics.json (a bare TopicList — every topic in it is "
                        "treated as pre-approved; the original, pre-Step-3 "
                        "contract, unchanged)")
    ap.add_argument("--selections-file",
                    help="skip selection and build from a question_selections.json "
                        "written by --gate-topics — only entries whose "
                        "question_approval.status is 'approved' are built")
    ap.add_argument("--gate-teaching-approach", action="store_true",
                    help="Step 7 DEMONSTRATION: after the question gate approves "
                        "some questions, advance them through framing and "
                        "teaching-approach selection (shorts/workflow.py) and run "
                        "Step 6's gate on the result, then stop — reels are not "
                        "built for these. Implies --gate-topics. Only wired into "
                        "the fresh-selection path (not --topics-file/"
                        "--selections-file), which is the narrowest slice that "
                        "shows the whole chain.")
    ap.add_argument("--gate-visual-plan", action="store_true",
                    help="Step 11 DEMONSTRATION: after --gate-teaching-approach "
                        "approves some teaching approaches, advance them through "
                        "script and visual-plan generation (shorts/workflow.py, "
                        "Step 10) and run Step 11's gate on the result, then stop "
                        "— reels are still not built for these. Implies "
                        "--gate-teaching-approach.")
    args = ap.parse_args()
    if args.topics_file and args.selections_file:
        ap.error("--topics-file and --selections-file are mutually exclusive")
    if args.gate_visual_plan:
        args.gate_teaching_approach = True
    if args.gate_teaching_approach:
        args.gate_topics = True

    # A misconfigured judge cannot be noticed from its output — it approves
    # everything — so it has to be said out loud before the run starts.
    for warning in config.model_warnings():
        print(f"!! {warning}\n")

    sections = parse_markdown(args.doc)
    session_id = Path(args.doc).stem
    doc_text = Path(args.doc).read_text(encoding="utf-8")
    print(f"parsed {len(sections)} sections: {[s.section_id for s in sections]}")

    # A stub run writes somewhere else, and that is not cosmetic. topics.json /
    # question_selections.json are the human-decided lists — the files here that
    # represent a decision rather than an output — and `SHORTS_STUB=1` selection
    # produces placeholders like "How does why paging exists work?". One stub run
    # to exercise the renderer silently replaced a real decided list with those,
    # and every later `--topics-file output/topics.json` build faithfully made
    # shorts out of them. Nothing warned, because reading the file worked
    # perfectly.
    topics_path = config.OUTPUT_DIR / ("topics.stub.json" if config.STUB else "topics.json")
    selections_path = config.OUTPUT_DIR / (
        "question_selections.stub.json" if config.STUB else "question_selections.json")

    if args.topics_file:
        # THE ORIGINAL, PRE-STEP-3 CONTRACT — UNCHANGED. A bare TopicList is
        # already a decision: whoever wrote or hand-edited this file already
        # decided every topic in it belongs, so every one is built. This is the
        # explicit, documented way to skip Step 3's gate entirely (requirement
        # G's "existing automatic behavior remains available explicitly").
        topic_list = TopicList(**json.loads(Path(args.topics_file).read_text()))
        print(f"loaded {len(topic_list.topics)} approved topics from {args.topics_file}")
        for t in topic_list.topics:
            print(f"  [{t.source_section_id}] {t.id}: {t.topic}")
        topics = topic_list.topics

    elif args.selections_file:
        # THE NEW, STEP-3-AWARE COUNTERPART. Only status == "approved" proceeds
        # — see schema.QuestionWorkflow.approved_topic, the one gate every
        # caller of this file (CLI, server) shares. A pending or rejected entry
        # is reported, never built.
        raw = json.loads(Path(args.selections_file).read_text())
        workflows = [QuestionWorkflow(**w) for w in raw]
        topics = [t for wf in workflows if (t := wf.approved_topic) is not None]
        skipped = len(workflows) - len(topics)
        print(f"loaded {len(workflows)} decided question(s) from "
              f"{args.selections_file}: {len(topics)} approved"
              + (f", {skipped} not approved (skipped)" if skipped else ""))
        for t in topics:
            print(f"  [{t.source_section_id}] {t.id}: {t.topic}")
        if not topics:
            print("nothing approved in that file — nothing to build.")
            return

    else:
        # select_topics_with_selections, NOT select_topics — same pipeline, same
        # ranking (see skills.select._select_pipeline, which both wrap), and this
        # one ALSO returns a QuestionSelection per topic so --gate-topics below
        # has something to show a human. Ignored when the gate is not asked for,
        # so the ungated default path pays nothing extra: build_question_selections
        # is pure post-processing on a TopicList that was already computed.
        topic_list, _notes, selections = select_topics_with_selections(
            sections, target=args.topics)
        print(f"selected {len(topic_list.topics)} topics")
        topics_path.write_text(topic_list.model_dump_json(indent=2))
        for t in topic_list.topics:
            print(f"  [{t.source_section_id}] {t.id}: {t.topic}")

        # Step 3's human check. Everything downstream inherits these choices, so
        # it is far cheaper to fix a bad question here — approve, reject, or ask
        # for an LLM regeneration with a reason — than to regenerate five scripts
        # later. EXISTING AUTOMATIC BEHAVIOR REMAINS AVAILABLE EXPLICITLY: with no
        # --gate-topics, none of this runs and the pipeline proceeds exactly as it
        # always did (requirement G).
        if not args.gate_topics:
            topics = topic_list.topics
        else:
            workflows = [QuestionWorkflow(selection=s) for s in selections]
            # sys.stdin.isatty() DECIDES THE MODE, NOT A FLAG A SCRIPT COULD
            # FORGET TO SET. A cron job or a test harness piping this command
            # never has a real terminal on stdin, so it always gets the
            # non-interactive branch below and never blocks on input() — see
            # review.run_question_gate's own docstring for why this, and not
            # "make batch workflows hang", is the contract.
            interactive = sys.stdin.isatty()
            workflows = review.run_question_gate(workflows, sections,
                                                 interactive=interactive)
            selections_path.write_text(
                json.dumps([w.model_dump() for w in workflows], indent=2))

            if not interactive:
                print(f"\nwrote {selections_path}")
                print("TOPIC GATE — not an interactive terminal, so nothing here "
                     "was decided (every question is still 'pending'). Edit each "
                     "entry's question_approval by hand (never the question text "
                     "itself — see schema.QuestionApproval), or rerun this exact "
                     "command from an interactive terminal, then:")
                print(f"  python -m shorts.run {args.doc} "
                     f"--selections-file {selections_path}")
                return

            approved = [t for wf in workflows if (t := wf.approved_topic) is not None]
            print(f"\nwrote {selections_path}")
            if not approved:
                print("no questions approved — nothing to build.")
                return

            if args.gate_teaching_approach:
                # STEP 7'S DEMONSTRATION BOUNDARY, AND WHY IT STOPS HERE. This
                # CLI flow's OWN job, below this block, is building finished
                # reels — and framing/teaching-approach are not wired into
                # that build path (visual-strategy generation and script
                # changes are still out of scope; see shorts/workflow.py's
                # own module docstring). So this flag advances every APPROVED
                # workflow through framing and teaching-approach selection,
                # runs Step 6's human gate on the result, reports where each
                # one landed, and returns — it does not go on to build
                # anything for them. Demonstrating selection -> question gate
                # -> framing -> teaching approach -> teaching-approach gate
                # end to end is the whole point of this flag; building on top
                # of what it produces is a later step's job — UNLESS
                # --gate-visual-plan asks for one more stage below.
                print(f"\nadvancing {len(workflows)} decided question(s) "
                     f"through framing and teaching-approach selection...")
                progress = question_workflow.advance_many(
                    workflows, sections, document=doc_text)
                workflows = [p.workflow for p in progress]
                for p in progress:
                    print(f"  {p.workflow.selection.topic.id}: {p.status} — {p.detail}")

                # interactive IS ALREADY True here — the non-interactive branch
                # above already returned before this point — so this always
                # runs the loop rather than the "nothing decided" message.
                workflows = review.run_teaching_approach_gate(
                    workflows, sections, interactive=interactive)
                selections_path.write_text(
                    json.dumps([w.model_dump() for w in workflows], indent=2))

                if not args.gate_visual_plan:
                    ready = [w for w in workflows if w.approved_teaching_approach is not None]
                    print(f"\nwrote {selections_path}")
                    print(f"{len(ready)}/{len(workflows)} ready for the next future stage.")
                    return

                # STEP 11'S OWN DEMONSTRATION BOUNDARY, ONE STAGE FURTHER. Every
                # workflow whose teaching approach was just approved above is
                # advanced through script and visual-plan generation (Step 10 —
                # shorts/workflow.py's advance_many, one advance() call per
                # workflow, exactly as idempotent and exactly as human-gated as
                # the call above) and Step 11's gate runs on the result. Reels
                # are STILL not built for these — rendering from an approved
                # visual plan is a later step's job.
                approved_approach = [w for w in workflows
                                     if w.approved_teaching_approach is not None]
                print(f"\nadvancing {len(approved_approach)} approved teaching "
                     f"approach(es) through script and visual-plan generation...")
                progress = question_workflow.advance_many(
                    workflows, sections, document=doc_text)
                workflows = [p.workflow for p in progress]
                for p in progress:
                    print(f"  {p.workflow.selection.topic.id}: {p.status} — {p.detail}")

                workflows = review.run_visual_plan_gate(
                    workflows, sections, interactive=interactive)
                selections_path.write_text(
                    json.dumps([w.model_dump() for w in workflows], indent=2))

                ready = [w for w in workflows if w.approved_visual_strategy is not None]
                print(f"\nwrote {selections_path}")
                print(f"{len(ready)}/{len(workflows)} ready for the next future "
                     f"stage (rendering).")
                return

            print(f"{len(approved)} approved — continuing to build.")
            topics = approved

    topics = topics[: args.limit] if args.limit else topics

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
                             not args.no_svg, document=doc_text,
                             router=router, buf=buf)
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
