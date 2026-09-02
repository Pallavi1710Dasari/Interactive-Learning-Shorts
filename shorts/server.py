"""
The API behind the web flow: paste material -> review Q&A -> watch reels.

    python -m shorts.server            # http://localhost:8000

The CLI pipeline in run.py stays exactly as it is; this exposes the same steps as
HTTP so a human can sit in the middle of them. The split matters because the
review step is interactive: you cannot regenerate one answer from a batch script.

Cost shape, worth knowing before clicking:
  POST /api/material   1 LLM call  (topic selection)
  POST /api/script     1 call per script, + up to 3 on the grader retry loop
  POST /api/regenerate 1 call
  POST /api/finalize   1 call per diagram + 1 judge call per short  <- the expensive one

So Step 2 is cheap and Step 3 is not. Only finalize what a human approved.
"""
import json, os, re, shutil, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .schema import Script, Topic, Section, ShortUnit
from .parse import parse_markdown, find_section
from .skills.select import select_topics_with_notes
from .skills.script import write_script
from .skills.visuals import design_visuals, render_diagrams
from . import raster
from .skills.audit import judge_script
from . import checks, config, feed, usage, voice

app = FastAPI(title="Interactive Learning Shorts")
usage.load()   # cumulative across restarts

for _warning in config.model_warnings():
    print(f"!! {_warning}")

# Judge calls are launched from inside a build worker and collected by the same
# worker, so they need a pool of their own — submitting to the pool you are running
# on deadlocks once every worker is waiting on a task that is still queued.
_JUDGE_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="judge")

# ------------------------------------------------- provider errors, said out loud
#
# EVERY MODEL ERROR USED TO BE A BARE 500. The reviewer's report was "500 Internal
# Server Error while loading reading material", and the cause was not in this
# project at all — the gateway had answered
#
#     403 permission_error: Key limit exceeded (total limit).
#
# /api/material catches ValueError, because a bad topic selection is a known
# outcome, and nothing caught the API exceptions. So a spending cap, an expired key,
# a rate limit and a provider outage all reached the browser as the same blank 500,
# with the real message visible only in the terminal running uvicorn. Nobody using
# the web flow would ever see it.
#
# None of these are bugs in the pipeline and all of them are actionable by the
# person hitting them, which is exactly what an error message is for.

#: Provider failures worth telling the user apart, and what to say about each.
_PROVIDER_ERRORS: tuple[tuple[type, int, str], ...] = (
    (anthropic.RateLimitError, 429,
     "the model provider is rate-limiting this key — wait a moment and retry"),
    (anthropic.AuthenticationError, 502,
     "the model provider rejected the API key. Check ANTHROPIC_API_KEY in .env"),
    (anthropic.PermissionDeniedError, 502,
     "the model provider refused the request — usually a spending limit on the key, "
     "or a model this key may not use. The provider's own message is below"),
    (anthropic.APIConnectionError, 504,
     "could not reach the model provider — check the network and ANTHROPIC_BASE_URL"),
    (anthropic.APIStatusError, 502,
     "the model provider returned an error"),
)


def _provider_detail(exc: Exception) -> tuple[int, str]:
    for kind, status, hint in _PROVIDER_ERRORS:
        if isinstance(exc, kind):
            return status, f"{hint}: {exc}"
    return 502, f"model provider error: {exc}"


@app.exception_handler(anthropic.APIError)
async def _provider_error(request: Request, exc: anthropic.APIError):
    """Turn a provider failure into something the browser can show a human."""
    status, detail = _provider_detail(exc)
    print(f"!! {request.url.path}: {type(exc).__name__}: {exc}")
    return JSONResponse({"detail": detail, "provider_error": type(exc).__name__},
                        status_code=status)


UPLOADS = config.OUTPUT_DIR / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
WEB_DIST = config.ROOT / "web" / "dist"


# --------------------------------------------------------------------- helpers

def _doc_path(doc_id: str) -> Path:
    """Resolve a doc id to a file, refusing anything that is not a plain id."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", doc_id):
        raise HTTPException(400, "bad doc_id")
    path = UPLOADS / f"{doc_id}.md"
    if not path.exists():
        raise HTTPException(404, f"unknown doc_id {doc_id} — upload the material again")
    return path


def _sections(doc_id: str) -> list[Section]:
    return parse_markdown(_doc_path(doc_id))


def _graders(script: Script, section: Section, doc_text: str | None = None) -> list[dict]:
    return [{"name": r.name, "passed": r.passed, "reason": r.reason}
            for r in checks.run_script_graders(script, section.text, doc_text=doc_text)]


def _as_qa(script: Script) -> dict:
    """
    The review view thinks in questions and answers, not beats.

    The first beat is the interviewer's question; the student beats are the answer,
    one paragraph each. Keeping the mapping in one place means the UI never has to
    know about beat mechanics.
    """
    return {
        "short_id": script.short_id,
        "question": script.question,
        "answers": [{"index": i, "line": b.line, "on_screen": b.on_screen,
                     "visual_ref": b.visual_ref, "source_quote": b.source_quote}
                    for i, b in enumerate(script.beats) if b.speaker == "student"],
        "beats": [b.model_dump() for b in script.beats],
        "seconds": script.estimated_seconds,
        "words": script.word_count,
    }


MAX_MATERIAL_CHARS = 200_000


# ---------------------------------------------------------------- step 1: material

class MaterialIn(BaseModel):
    text: str
    target: int = 5


@app.post("/api/material")
async def material(
    text: str | None = Form(default=None),
    target: int = Form(default=5),
    file: UploadFile | None = File(default=None),
):
    """
    Accept pasted text or an uploaded file, split it, and suggest topics.

    Multipart so one endpoint serves both the textarea and the file picker.
    """
    if file is not None:
        raw = (await file.read()).decode("utf-8", errors="replace")
    elif text:
        raw = text
    else:
        raise HTTPException(400, "provide pasted text or a file")

    raw = raw.strip()
    if len(raw) < 200:
        raise HTTPException(400, "material is too short to make shorts from (need ~200+ chars)")
    if len(raw) > MAX_MATERIAL_CHARS:
        raise HTTPException(413, f"material over {MAX_MATERIAL_CHARS} chars — split it up")

    doc_id = uuid.uuid4().hex[:12]
    path = UPLOADS / f"{doc_id}.md"
    path.write_text(raw, encoding="utf-8")

    sections = parse_markdown(path)
    if not sections:
        # parse.py keys on "## <number> <title>" headings. Without them there is
        # nothing to cite, so say so plainly instead of returning zero topics.
        path.unlink(missing_ok=True)
        raise HTTPException(
            422,
            "no sections found. Use markdown headings like '## 3.1 Why paging exists' "
            "so each short can cite where it came from.",
        )

    cursor = usage.mark()
    try:
        topics, notes = select_topics_with_notes(sections, target)
    except ValueError as e:
        # Every cited section was invented. That is a bad selection, not a bug —
        # say so instead of returning a 500.
        raise HTTPException(422, str(e))
    return {
        "usage": usage.since(cursor), "total": usage.totals(),
        "notes": notes,
        "doc_id": doc_id,
        "sections": [{"section_id": s.section_id, "title": s.title,
                      "chars": len(s.text), "lines": f"{s.start_line}-{s.end_line}"}
                     for s in sections],
        "topics": [t.model_dump() for t in topics.topics],
    }


# ------------------------------------------------------- step 2: scripts + review

class ScriptIn(BaseModel):
    doc_id: str
    topic: Topic


@app.post("/api/script")
def make_script(body: ScriptIn):
    """Write one script, with the same grader retry loop run.py uses."""
    sections = _sections(body.doc_id)
    try:
        section = find_section(sections, body.topic.source_section_id)
    except KeyError as e:
        raise HTTPException(422, str(e))

    cursor = usage.mark()
    doc_text = _doc_path(body.doc_id).read_text(encoding="utf-8")
    feedback, attempts = None, []
    script = None
    for attempt in range(1, 4):
        script = write_script(body.topic, section, feedback, document=doc_text)
        graders = _graders(script, section, doc_text)
        attempts.append({"attempt": attempt, "graders": graders})
        if all(g["passed"] for g in graders):
            break
        feedback = "\n".join(f"- {g['name']}: {g['reason']}"
                             for g in graders if not g["passed"])

    return {"topic": body.topic.model_dump(), "section_id": section.section_id,
            "qa": _as_qa(script), "attempts": attempts,
            "graders": attempts[-1]["graders"],
            "usage": usage.since(cursor), "total": usage.totals()}


class ScriptsIn(BaseModel):
    doc_id: str
    topics: list[Topic]


@app.post("/api/scripts")
def make_scripts(body: ScriptsIn):
    """
    Draft every topic at once.

    Drafting one topic at a time meant the reviewer watched a spinner per card and
    the wall-clock cost was the sum of all of them. These calls are independent, so
    they run concurrently and the wait becomes the slowest single draft.
    """
    cursor = usage.mark()
    sections = _sections(body.doc_id)
    doc_text = _doc_path(body.doc_id).read_text(encoding="utf-8")

    def one(topic: Topic) -> dict:
        """
        One topic -> one drafted script. NEVER raises.

        This ran unguarded, so a single topic whose model call failed propagated
        out of pool.map and turned the whole request into a 500 — the reviewer lost
        four good drafts because the fifth had a bad minute, and the page showed
        "500 Internal Server Error" with nothing to retry. A failure is per-card
        data now: that card offers Retry, the rest render.
        """
        try:
            section = find_section(sections, topic.source_section_id)
        except KeyError as e:
            return {"topic": topic.model_dump(), "error": str(e)}

        feedback, script, graders = None, None, []
        try:
            for _ in range(3):
                script = write_script(topic, section, feedback, document=doc_text)
                graders = _graders(script, section, doc_text)
                if all(g["passed"] for g in graders):
                    break
                feedback = "\n".join(f"- {g['name']}: {g['reason']}"
                                     for g in graders if not g["passed"])
        except Exception as e:
            return {"topic": topic.model_dump(), "section_id": section.section_id,
                    "error": f"{type(e).__name__}: {e}"}

        return {"topic": topic.model_dump(), "section_id": section.section_id,
                "qa": _as_qa(script), "graders": graders}

    # All topics at once. The cap of 6 serialised anything larger into a second
    # round, so asking for 10 shorts took twice as long as asking for 5 for no
    # reason — these are independent network calls, not CPU work.
    with ThreadPoolExecutor(max_workers=max(1, len(body.topics))) as pool:
        results = list(pool.map(one, body.topics))

    return {"results": results, "usage": usage.since(cursor), "total": usage.totals()}


class RegenerateIn(BaseModel):
    doc_id: str
    topic: Topic
    instruction: str
    target: str = "script"          # "question" | "answer" | "script"
    qa: dict | None = None          # the script on screen, so edits are targeted


@app.post("/api/regenerate")
def regenerate(body: RegenerateIn):
    """
    Regenerate from a human note.

    The note goes down the same channel the graders use, because write_script
    already knows how to act on "your previous attempt was rejected". A targeted
    edit is expressed as an instruction plus a hold-everything-else clause rather
    than by trying to patch one beat in isolation — the beats have to stay
    coherent with each other, so the model rewrites the script with the
    constraint applied.
    """
    if not body.instruction.strip():
        raise HTTPException(400, "say what to change")

    sections = _sections(body.doc_id)
    try:
        section = find_section(sections, body.topic.source_section_id)
    except KeyError as e:
        raise HTTPException(422, str(e))

    where = {
        "question": "Change ONLY the interviewer's question. Leave every answer beat "
                    "word-for-word as it is.",
        "answer": "Change ONLY the answer beats. Leave the interviewer's question "
                  "word-for-word as it is.",
    }.get(body.target, "Revise the whole script as directed.")

    # Without this the model rewrote from scratch and the reviewer's targeted edit
    # looked like it had done nothing — the reported "regeneration not working".
    current = None
    if body.qa:
        try:
            current = Script(short_id=body.topic.id, question=body.qa["question"],
                             beats=body.qa["beats"])
        except Exception:
            current = None

    note = body.instruction.strip()
    base = f"A human reviewer asked for this change:\n{note}\n\n{where}"

    # A reviewer's note is about meaning, not length — "be more specific" or "shorten
    # this" routinely lands the script under the 30s floor or over the 60s ceiling.
    # Returning that as a red timing error and stopping left the human fixing a word
    # count by hand, which is not their job. So keep asking, carrying the note forward
    # alongside the mechanical complaint. The reviewer's intent is never dropped, and a
    # failure is only reported if it survives every attempt.
    cursor = usage.mark()
    doc_text = _doc_path(body.doc_id).read_text(encoding="utf-8")
    script, graders, feedback = None, [], base
    for _ in range(3):
        script = write_script(body.topic, section, feedback, current=current,
                              document=doc_text)
        graders = _graders(script, section, doc_text)
        if all(g["passed"] for g in graders):
            break
        broken = "\n".join(f"- {g['name']}: {g['reason']}"
                           for g in graders if not g["passed"])
        feedback = (f"{base}\n\nYour previous attempt also broke these hard rules. Fix them "
                    f"WITHOUT losing the reviewer's change above:\n{broken}")

    return {"topic": body.topic.model_dump(), "qa": _as_qa(script), "graders": graders,
            "usage": usage.since(cursor), "total": usage.totals()}


# ---------------------------------------------------- step 3: visuals, judge, reels

class FinalizeIn(BaseModel):
    doc_id: str
    approved: list[dict]            # [{topic, beats}] straight back from the review UI
    do_svg: bool = True
    do_judge: bool = True
    # Recorded neural narration, when a provider is configured. Off costs nothing
    # and the browser voice narrates instead; see shorts/voice.py.
    do_voice: bool = True


def _rejudge_after_fix(unit: ShortUnit, script: Script, topic: Topic,
                       section: Section, body: "FinalizeIn") -> ShortUnit | None:
    """
    One repair attempt on a short the judge failed, then quarantine. Returns the
    unit to keep, or None to keep the caller's.

    THE COST, because it is not free: one script call, one visual call, one judge
    call — and only for a short that actually failed, which on the fifteen units
    measured was four of them. A short that passes costs exactly what it did before.

    WHAT IT REPAIRS AND WHAT IT DOES NOT. It rewrites the SCRIPT, because that is
    where a faithfulness failure lives — a frame drawing an invented value is a
    faithful drawing of an invented beat, and redesigning the picture around a wrong
    sentence produces a better-looking wrong short. The visuals are then redesigned
    to match the new words, which they must be: the old frames were built for beats
    that no longer exist.

    The repaired short is kept only if it actually scores better. A rewrite that
    fixes the cited problem and breaks something else is not an improvement, and the
    original at least had a human's approval behind its wording.

    Either way the verdict decides the STATUS, and that is the part that matters:
    a short still under the bar is stored "needs_review" and feed.collect keeps it
    out of the reel. It is not deleted — it is paid for, it is on disk, and the
    reviewer can read the judge's problems and fix it by hand.
    """
    before = unit.eval
    problems = "\n".join(f"  - {p}" for p in (before.problems or [])) if before else ""
    print(f"    judge failed {unit.short_id} "
          f"(f={before.faithfulness} c={before.clarity} p={before.pace}) — one repair attempt")

    repaired = None
    try:
        feedback = (
            "The reviewer's grader rejected your previous script. Fix exactly these, "
            "and change nothing else:\n" + (problems or "  - the answer is not "
            "supported by its own section") +
            "\n\nEvery beat must rest on a sentence copied from THIS SHORT'S SECTION. "
            "If a beat cannot be supported from the section, delete it or narrow the "
            "question until it can be.")
        # The REAL topic, not a reconstructed one — Topic requires difficulty and an
        # answer sentence, and a hand-built stand-in fails validation inside the
        # try, which would make the repair silently never happen.
        fixed = write_script(topic=topic, section=section,
                             feedback=feedback, current=script)
        # The code graders come first and are free. A rewrite that breaks a hard
        # rule is not worth a judge call.
        if not checks.all_passed(checks.run_script_graders(fixed, section.text)):
            print(f"    ! repair of {unit.short_id} failed the code graders — keeping the original")
        else:
            visuals, _ = design_visuals(fixed, section, draw=body.do_svg)
            repaired = unit.model_copy(update={
                "question": fixed.question, "beats": fixed.beats,
                "estimated_seconds": fixed.estimated_seconds, "visuals": visuals})
            repaired.eval = judge_script(fixed, section.text, repaired)
            print(f"    repaired {unit.short_id}: f={repaired.eval.faithfulness} "
                  f"c={repaired.eval.clarity} p={repaired.eval.pace}")
    except Exception as e:
        # A failed repair must not lose a short that is already built and paid for.
        print(f"    ! repair of {unit.short_id}: {type(e).__name__}: {e}")

    keep = unit
    if repaired is not None and repaired.eval is not None and before is not None:
        better = (repaired.eval.passed and not before.passed) or (
            repaired.eval.faithfulness > before.faithfulness)
        if better:
            keep = repaired
        else:
            print(f"    repair of {unit.short_id} was not an improvement — keeping the original")

    if keep.eval is not None and not keep.eval.passed:
        keep.status = "needs_review"
        print(f"    ! {keep.short_id} QUARANTINED (f={keep.eval.faithfulness} "
              f"c={keep.eval.clarity} p={keep.eval.pace}) — held out of the reel, "
              f"see its judge problems")
    return keep


@app.post("/api/finalize")
def finalize(body: FinalizeIn):
    """Turn approved Q&A into units on disk, then hand back the reel payload."""
    if not body.approved:
        raise HTTPException(400, "nothing approved")

    cursor = usage.mark()
    sections = _sections(body.doc_id)
    built, failed = [], []

    def build_one(item: dict) -> tuple[str | None, dict | None, list[str]]:
        """One approved Q&A -> one unit on disk. Returns (short_id, failure, warnings)."""
        try:
            topic = Topic(**item["topic"])
            section = find_section(sections, topic.source_section_id)
            script = Script(short_id=topic.id, question=item["qa"]["question"],
                            beats=item["qa"]["beats"])
        except Exception as e:
            return None, {"topic_id": item.get("topic", {}).get("id"), "error": str(e)}, []

        try:
            # The voice depends only on the words, so it records while the visuals
            # are being designed rather than after them.
            recording = None
            if body.do_voice and voice.configured()[0]:
                recording = _JUDGE_POOL.submit(voice.synthesize, script)

            # design_visuals, not spec_visuals: it grades what comes back and asks
            # again for a short whose frames repeat, print the narration, or draw a
            # capital A where a server was meant. One call for a short that passes.
            vision_scores: dict = {}
            visuals, design_problems = design_visuals(script, section,
                                                      draw=body.do_svg,
                                                      scores_out=vision_scores)

            unit = ShortUnit(
                short_id=script.short_id,
                session_id=Path(_doc_path(body.doc_id)).stem,
                source_section_id=section.section_id,
                question=script.question,
                estimated_seconds=script.estimated_seconds,
                beats=script.beats,
                visuals=visuals,
                # Kept, not acted on — see ShortUnit.vision_scores.
                vision_scores=vision_scores,
                status="approved",      # a human already approved it in step 2
            )

            # THE JUDGE GOES AFTER THE VISUALS NOW, and that is a deliberate trade of
            # a few seconds of wall clock for a check that actually happens.
            #
            # It used to be submitted first, on the reasoning that "the judge reads
            # the script, not the pictures, so it does not have to wait for them" —
            # which was true of the code and false of the brief. JUDGE_SYSTEM has
            # always asked for `diagram_correct`, so the judge was being asked about
            # frames that had not been designed yet, and answered True every single
            # time because the schema default is True. The overlap was free because
            # the work was not being done.
            #
            # The voice still records in parallel, so most of the latency is still
            # absorbed; only the judge waits, and only for the one visual call.
            judging = None
            if body.do_judge and checks.all_passed(
                    checks.run_script_graders(script, section.text)):
                judging = _JUDGE_POOL.submit(judge_script, script, section.text, unit)

            if judging is not None:
                try:
                    unit.eval = judging.result()
                except Exception as e:
                    # A short without a score is still a short. Losing the reel
                    # because the grader had a bad minute is the wrong trade.
                    print(f"    ! judge {script.short_id}: {type(e).__name__}: {e}")

            # THE JUDGE NOW DECIDES SOMETHING, which it did not before.
            #
            # Everything above this line used to end at "write it to disk". The
            # comment below still explains why the CODE graders only warn — the
            # script was human-approved and the money is spent — and that reasoning
            # is right for a structural nit and wrong for the judge, because the
            # judge is the only check that reads a claim against its source and says
            # "this is not in the section". Four of fifteen shipped shorts scored
            # faithfulness 2 of 5, each for teaching a fact its own section does not
            # contain, and each was written out as "audited" and shown to students
            # beside a 5.
            #
            # So: one retry with the judge's own problems as the feedback, then
            # quarantine. The retry is worth its cost because the judge's problems
            # are specific and actionable ("beat 3 introduces 'GET /index.html',
            # which does not appear in the source section") — this is the same
            # feedback channel the human reviewer uses in step 2, and write_script
            # already knows how to act on it.
            if unit.eval is not None and not unit.eval.passed:
                if config.REPAIR_FAILED_SHORTS:
                    unit = _rejudge_after_fix(unit, script, topic, section, body) or unit
                else:
                    print(f"    ! {unit.short_id} failed the judge "
                          f"(f={unit.eval.faithfulness} c={unit.eval.clarity} "
                          f"p={unit.eval.pace}) — no repair attempted "
                          f"(REPAIR_FAILED_SHORTS=0). Its verdict is on the short; "
                          f"redraw it from a note or publish it anyway.")

            if recording is not None:
                try:
                    unit.audio = recording.result()
                except Exception as e:
                    # Includes tts.AccountBlocked, which voice.synthesize re-raises
                    # so batch CLIs can stop early. A build must not: the short is
                    # already paid for, and the browser voice narrates it.
                    print(f"    ! voice {script.short_id}: {e} "
                          f"— shipping without a recorded track")

            # THE UNIT GRADERS RUN HERE TOO, and it took a while to notice they did
            # not. Everything that judges the PICTURES — check_frames_are_visual,
            # check_svg_quality, check_diagram_matches_narration — lived only in
            # run.py's audit(), so a diagram defect was caught on the CLI path and
            # sailed straight through the web one. This is the path people actually
            # upload material through, which made it the path with no cover at all.
            #
            # They REPORT, they do not reject. By the time this line runs the script
            # was approved by a human and every model call is already paid for, so
            # throwing the short away would cost money and lose work to fix nothing.
            # The reviewer gets told what is wrong with it and can regenerate the
            # ones worth regenerating.
            warnings = [f"{r.name}: {r.reason}"
                        for r in checks.run_unit_graders(unit, section.text)
                        if not r.passed]
            for warning in warnings:
                print(f"    ! {unit.short_id}: {warning}")

            (config.OUTPUT_DIR / f"{unit.short_id}.json").write_text(
                unit.model_dump_json(indent=2))
            return unit.short_id, None, warnings
        except Exception as e:
            # One bad short must not lose the others in the batch — they have
            # already been paid for by the time anything can go wrong here.
            return None, {"topic_id": item.get("topic", {}).get("id"), "error": str(e)}, []

    # Shorts are independent, so build them side by side rather than end to end.
    warned: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(body.approved))) as pool:
        for short_id, failure, warnings in pool.map(build_one, body.approved):
            if short_id:
                built.append(short_id)
                if warnings:
                    warned[short_id] = warnings
            elif failure:
                failed.append(failure)

    # Only what this build produced. Returning every unit in output/ meant
    # approving one short and then being shown seven, which is not what the
    # reviewer asked for.
    #
    # QUARANTINED SHORTS ARE REPORTED, NOT SILENTLY DROPPED, and that is the whole
    # point of this block. feed.collect() hides "needs_review"/"rejected" from the
    # student feed, which is correct — but this response was assembled from that
    # same filtered list, so a build whose shorts were ALL held back by the judge
    # came back as built:[five ids], failed:[], shorts:[].
    #
    # The browser reads that as success with nothing in it. `failed` is empty so no
    # error renders, and step 3 shows "No reels yet. Paste material in step 1,
    # approve some answers in step 2" — advice to redo the two steps that had just
    # succeeded. Meanwhile five paid-for units are sitting in output/ with the
    # judge's problems attached and nothing anywhere says so.
    #
    # A check that can throw work away has to be the thing that explains itself.
    # The units come back under their own key with their verdicts, and the reviewer
    # is told what the judge objected to.
    produced = {u["short_id"]: u for u in feed.collect(include_quarantined=True)
                if u["short_id"] in set(built)}
    fresh = [u for u in produced.values() if u["status"] not in feed.QUARANTINED]
    held = [u for u in produced.values() if u["status"] in feed.QUARANTINED]
    for u in held:
        print(f"    ! {u['short_id']} held out of the reel ({u['status']})")

    # WHAT THIS BUILD COST, printed per build rather than only accumulated.
    #
    # usage kept a running sum and nothing else, so "is a reel dearer than it used
    # to be?" could only be answered by snapshotting the total before and after and
    # subtracting — which is not a thing anyone does while working. The per-step
    # split is what makes the answer actionable: it is the difference between "the
    # build cost more" and "visual_spec made six calls when it used to make three".
    spent = usage.since(cursor)
    n = max(1, len(built))
    steps = " ".join(f"{k}={v['calls']}x${v['cost']:.3f}"
                     for k, v in sorted((spent.get("by_label") or {}).items(),
                                        key=lambda x: -x[1]["cost"]))
    print(f"    build cost ${spent['cost']:.3f} over {spent['calls']} call(s) for "
          f"{len(built)} short(s) — ${spent['cost'] / n:.3f} each")
    if steps:
        print(f"      {steps}")
    return {"built": built, "failed": failed, "warnings": warned, "shorts": fresh,
            "quarantined": held,
            "usage": spent, "total": usage.totals()}


class RevisualIn(BaseModel):
    short_id: str
    instruction: str


@app.post("/api/revisual")
def revisual(body: RevisualIn):
    """
    Redraw ONE short's pictures from a reviewer's note. One paid call, usually.

    THE ASYMMETRY THIS CLOSES. A script the reviewer dislikes has had a note box
    since step 2 — say what is wrong, get a rewrite. The PICTURES had nothing. The
    only way to change a diagram was `redraw --redesign`, which selects on grader
    failures across the whole of output/ and takes no opinion: a frame that passes
    every grader and is simply confusing was unfixable from the app.

    That is the wrong way round, because the pictures are the half a viewer complains
    about. The note goes down the same channel the design graders use — see
    design_visuals(note=...) — so it is carried across retries rather than lost the
    first time a grader trips.

    Writes the unit back, so the next feed read and the next MP4 render both pick it
    up. The reel this belongs to is already built and paid for; this replaces its
    frames, not the short.
    """
    note = body.instruction.strip()
    if not note:
        raise HTTPException(400, "say what should change about the pictures")

    path = config.OUTPUT_DIR / f"{body.short_id}.json"
    if not path.exists():
        raise HTTPException(404, f"no such short: {body.short_id}")
    unit = ShortUnit(**json.loads(path.read_text()))

    from .redraw import _section_for
    section = _section_for(unit)
    if section is None:
        raise HTTPException(
            422,
            f"the material {body.short_id} was built from is no longer on disk, so "
            f"its frames cannot be redrawn against it — re-upload it and rebuild.")

    cursor = usage.mark()
    script = Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)
    visuals, problems = design_visuals(script, section, previous=unit.visuals, note=note)
    # A renamed ref would fail ShortUnit's every_ref_resolved validator and lose the
    # short; keep the old frame for anything the redesign did not cover.
    for ref, old in unit.visuals.items():
        visuals.setdefault(ref, old)
    unit.visuals = visuals

    warnings = [f"{r.name}: {r.reason}"
                for r in checks.run_unit_graders(unit, section.text) if not r.passed]
    path.write_text(unit.model_dump_json(indent=2))

    # The cached MP4 was rendered from the frames this just replaced.
    stale = config.OUTPUT_DIR / unit.short_id / "reel.mp4"
    stale.unlink(missing_ok=True)

    fresh = [u for u in feed.collect(include_quarantined=True)
             if u["short_id"] == unit.short_id]
    return {"short": fresh[0] if fresh else None,
            "problems": problems, "warnings": warnings,
            "usage": usage.since(cursor), "total": usage.totals()}


@app.get("/api/usage")
def usage_totals():
    """Running token and dollar totals, plus a per-step breakdown."""
    return usage.totals()


@app.post("/api/usage/reset")
def usage_reset():
    usage.reset()
    return usage.totals()


class ReleaseIn(BaseModel):
    short_id: str


@app.post("/api/release")
def release(body: ReleaseIn):
    """
    Publish a held short anyway. The reviewer overrules the judge, on the record.

    THE JUDGE IS A GATE, NOT A VETO. A short it holds back is built and paid for,
    and the verdict can be about the pictures while the script is 5/5/5 — so the
    one person who can weigh "the diagram says 'Inner function' and I do not care"
    had no way to say so, and the reel stayed unpublishable forever. This is that
    way to say so.

    It does NOT edit the verdict. unit.eval keeps every score and problem exactly
    as the judge wrote them, so why the short was held is still readable after it
    is published; only `status` moves. To fix the short properly instead, redraw
    its pictures from a note (POST /api/revisual) or rebuild it from a better
    question in step 2 — those change the reel, and this only changes who decides.
    """
    path = config.OUTPUT_DIR / f"{body.short_id}.json"
    if not path.exists():
        raise HTTPException(404, f"no such short: {body.short_id}")
    unit = ShortUnit(**json.loads(path.read_text()))
    if unit.status not in feed.QUARANTINED:
        raise HTTPException(400, f"{body.short_id} is already in the reel "
                                 f"(status {unit.status})")
    unit.status = "audited"
    path.write_text(unit.model_dump_json(indent=2))
    print(f"    {unit.short_id} RELEASED by the reviewer over the judge's verdict")
    fresh = [u for u in feed.collect() if u["short_id"] == unit.short_id]
    return {"short": fresh[0] if fresh else None}


@app.get("/api/shorts")
def shorts(held: bool = False):
    """
    Everything currently in output/, in the shape the reel player wants.

    HELD SHORTS ARE OPT-IN, not hidden. feed.collect keeps a short the judge scored
    under the bar out of the feed, which is right for the feed and wrong as a dead
    end: step 2 told the reviewer the short exists and is on disk, and then offered
    no way to look at it. `?held=1` is that way — asked for by name, one short at a
    time, so a weak reel never turns up in the ordinary feed by accident.
    """
    return {"shorts": feed.collect(include_quarantined=held)}


@app.get("/api/audio/{short_id}")
def audio(short_id: str):
    """
    The recorded narration for one short, if it has any.

    Same id validation as _doc_path: short_id lands in a filesystem path, so
    anything that is not a plain id is refused rather than resolved.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", short_id):
        raise HTTPException(400, "bad short_id")
    track = voice.existing(short_id)
    if not track:
        raise HTTPException(404, "no recorded narration for this short")
    return FileResponse(track, media_type="audio/mpeg")


@app.get("/api/voice")
def voice_status():
    """Whether recorded narration is available, and what is missing when it is not."""
    ok, why = voice.configured()
    return {"configured": ok, "reason": why}


# Voice comparison samples, written by `python -m shorts.voicesample`. Mounted only
# if they exist so a fresh checkout does not fail to start, and read-only — choosing
# a voice is a listening exercise, not something the app should be able to change.
_SAMPLES = config.OUTPUT_DIR / "voice-samples"
if _SAMPLES.exists():
    app.mount("/voice-samples",
              StaticFiles(directory=_SAMPLES, html=True), name="voice-samples")


#: Renders in flight, by short_id. A render is ~90s of CPU with no API calls, so it
#: is cheap to repeat and expensive to WAIT on — the point of this registry is that
#: the browser does not hold a request open for a minute and a half.
_RENDERS: dict[str, dict] = {}
_RENDER_LOCK = threading.Lock()
#: Two shorts at a time. Each render drives three browsers of its own (see
#: video.DEFAULT_WORKERS), so this is six in flight on a machine with 28 cores —
#: the capture is CPU-bound in SwiftShader and contends, so more than two turns a
#: queue into a traffic jam. One was too strict: a second person clicking download
#: waited out the whole of somebody else's render before their own started, with a
#: progress bar sitting at 0% and nothing to say why.
_RENDER_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="render")


def _render_job(short_id: str) -> None:
    """Run one render, keeping its progress where /api/video/status can see it."""
    from . import video as videomod

    def progress(done: int, total: int) -> None:
        with _RENDER_LOCK:
            job = _RENDERS.get(short_id)
            if job:
                job.update(done=done, total=total, status="rendering")

    try:
        videomod.render(short_id, progress=progress)
        with _RENDER_LOCK:
            _RENDERS[short_id] = {**_RENDERS.get(short_id, {}),
                                  "status": "done", "error": None}
    except BaseException as e:      # noqa: BLE001 - surfaced to the client
        with _RENDER_LOCK:
            _RENDERS[short_id] = {**_RENDERS.get(short_id, {}), "status": "error",
                                  "error": f"{type(e).__name__}: {e}"}


def _check_id(short_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", short_id):
        raise HTTPException(400, "bad short_id")


@app.post("/api/video/{short_id}")
def start_render(short_id: str):
    """
    Begin rendering, and return immediately.

    WHY THIS IS NO LONGER SYNCHRONOUS. The old handler's docstring said a render was
    "seconds, no API calls... a job queue would be more moving parts than the work
    justifies", and that was true when it screenshotted one still per BEAT. It now
    photographs the real player at 30fps and takes about 90 seconds, and a
    minute-and-a-half HTTP request is a different animal: it survives on localhost
    only because nothing in the path has a read timeout. Any proxy in front of this
    would cut it at 60s, and the browser gets no progress out of it either way.

    Idempotent — asking again while one is in flight returns the job already running
    rather than starting a second.
    """
    _check_id(short_id)
    if not (config.OUTPUT_DIR / f"{short_id}.json").exists():
        raise HTTPException(404, f"no such short: {short_id}")

    from . import video as videomod
    with _RENDER_LOCK:
        job = _RENDERS.get(short_id)
        if job and job.get("status") in ("queued", "rendering"):
            return {"short_id": short_id, **job}
        # Cached AND current — the fingerprint check inside render() covers a stale
        # video from an older renderer, so this only short-circuits a real hit.
        mp4 = config.OUTPUT_DIR / short_id / "reel.mp4"
        stamp = config.OUTPUT_DIR / short_id / "reel.stamp"
        unit = config.OUTPUT_DIR / f"{short_id}.json"
        if mp4.exists() and videomod._stamp_matches(
                stamp, videomod._renderer_fingerprint(), unit):
            _RENDERS[short_id] = {"status": "done", "done": 1, "total": 1, "error": None}
            return {"short_id": short_id, **_RENDERS[short_id]}
        _RENDERS[short_id] = {"status": "queued", "done": 0, "total": 0, "error": None}
    _RENDER_POOL.submit(_render_job, short_id)
    with _RENDER_LOCK:
        return {"short_id": short_id, **_RENDERS[short_id]}


@app.get("/api/video/{short_id}/status")
def render_status(short_id: str):
    """Where a render has got to. Poll this; it is cheap and does no work."""
    _check_id(short_id)
    with _RENDER_LOCK:
        job = _RENDERS.get(short_id)
    if not job:
        return {"short_id": short_id, "status": "idle", "done": 0, "total": 0,
                "error": None}
    return {"short_id": short_id, **job}


@app.get("/api/video/{short_id}")
def video(short_id: str):
    """
    Serve the finished MP4.

    Still renders synchronously if asked for a short that has none — the CLI and any
    script that just wants the file keep working — but the app posts first and polls,
    so in practice this is a cache hit by the time it is called.
    """
    from . import video as videomod
    _check_id(short_id)
    try:
        mp4 = videomod.render(short_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        # A render failure is worth naming: the causes are a missing Chromium, a
        # missing ffmpeg, or a unit with no frames, and each needs a different fix.
        raise HTTPException(500, f"could not render {short_id}: {e}")
    return FileResponse(mp4, media_type="video/mp4",
                        filename=f"{short_id}.mp4")


# --------------------------------------------------------------- the voice studio
#
# Recording a voice, hearing it read something, and deciding to keep it are three
# steps of ONE decision made by ear — so they belong on one screen, not spread
# across a .env edit and a CLI. Everything below serves that screen.

_VOICE_JOBS: dict[str, dict] = {}
_VOICE_LOCK = threading.Lock()
#: One at a time: there is a single Chatterbox worker with one model in it.
_VOICE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice")

#: How many preview jobs to remember. This registry used to grow for the life of the
#: process — one entry, plus its scratch audio on disk, per press of "Speak it", and
#: nothing ever released either. Invisible over an afternoon, not free for a server
#: left running for weeks. A preview matters until you adopt it or record the next
#: one, so the last few dozen is already generous.
_VOICE_JOBS_MAX = 32


def _evict_voice_jobs() -> None:
    """Drop the oldest jobs past the cap, and the scratch audio they own.

    Call with _VOICE_LOCK held. Deleting the files is safe because adopting COPIES
    the clip into voices/ (see /api/voice/adopt), so nothing removed here is the
    last copy of a voice anyone chose to keep.
    """
    lab = config.OUTPUT_DIR / "voice-lab"
    while len(_VOICE_JOBS) > _VOICE_JOBS_MAX:
        # dict preserves insertion order, and mark() rewrites values in place
        # rather than reinserting, so the first key is the oldest job.
        old_id = next(iter(_VOICE_JOBS))
        del _VOICE_JOBS[old_id]
        shutil.rmtree(lab / old_id, ignore_errors=True)
        for clip in lab.glob(f"{old_id}_*"):
            clip.unlink(missing_ok=True)


def _voice_job(job_id: str, refs: dict, lines: list[tuple[str, str]]) -> None:
    """
    Speak `lines` — (speaker, text) in order — each in its own speaker's voice.

    ONE TRACK, BOTH VOICES. The lab used to take a single clip and say one line
    with it, which answers "what does this clip sound like" but not the question
    actually being asked: do these two voices work TOGETHER. A reel is an exchange,
    and two voices that are each fine alone can still be too similar to tell apart
    or jarring back to back. So the preview is the exchange.
    """
    from . import providers, tts
    from .schema import Script, Beat

    def mark(**kw):
        with _VOICE_LOCK:
            _VOICE_JOBS[job_id] = {**_VOICE_JOBS.get(job_id, {}), **kw}

    try:
        cb = providers._REGISTRY["chatterbox"]
        if not Path(config.CHATTERBOX_PYTHON).exists():
            raise RuntimeError(
                "Chatterbox is not installed. In a terminal:  python3 -m venv "
                "venv-chatterbox && venv-chatterbox/bin/pip install chatterbox-tts")
        mark(status="speaking")
        out_dir = (config.OUTPUT_DIR / "voice-lab" / job_id).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        # A speaker with no clip of its own borrows the other's, so one uploaded
        # voice still previews rather than erroring.
        only = next(iter(refs.values()))
        use = {"interviewer": str(refs.get("interviewer", only)),
               "student": str(refs.get("student", only))}

        beats = [Beat(speaker=who, line=text, on_screen="voice lab",
                      visual_ref="v") for who, text in lines]
        script = Script(short_id=f"lab_{job_id}", question=lines[0][1], beats=beats)
        # PASSED, NOT ASSIGNED TO GLOBALS. Setting config.CHATTERBOX_VOICE_* here
        # did nothing once a voice had been adopted, because Chatterbox.resolve()
        # reads voices/settings.json first — so the preview played the adopted
        # voices and the clip you had just uploaded was never used.
        audio = tts.synthesize(script, out_dir=out_dir, provider=cb, voices=use)
        mark(status="done", audio_url=f"/api/voice/lab/{job_id}.mp3",
             seconds=round(audio.duration_seconds, 1), error=None)
    except BaseException as e:      # noqa: BLE001 - shown to the user
        mark(status="error", error=f"{type(e).__name__}: {e}")


@app.post("/api/voice/speak")
async def voice_speak(
    text_interviewer: str = Form(default=""),
    text_student: str = Form(default=""),
    clip_interviewer: UploadFile | None = File(default=None),
    clip_student: UploadFile | None = File(default=None),
):
    """
    Preview one or two voices reading an exchange. Returns a job id; poll the job.

    Asynchronous because the first call of a run loads the model — about 158
    seconds on CPU — and a synchronous request would time out having told the
    person nothing while they waited.
    """
    job_id = uuid.uuid4().hex[:12]
    lab = config.OUTPUT_DIR / "voice-lab"
    lab.mkdir(parents=True, exist_ok=True)

    refs: dict[str, str] = {}
    for who, upload in (("interviewer", clip_interviewer), ("student", clip_student)):
        if upload is None:
            continue
        raw = await upload.read()
        if len(raw) < 4000:
            raise HTTPException(
                400, f"the {who} clip is too short to clone a voice from — "
                     f"7 to 20 seconds of clear speech works best")
        suffix = Path(upload.filename or "clip.wav").suffix.lower()
        if suffix not in (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"):
            suffix = ".wav"
        ref = lab / f"{job_id}_{who}{suffix}"
        ref.write_bytes(raw)
        refs[who] = str(ref)

    if not refs:
        raise HTTPException(400, "upload a voice for at least one speaker")

    # In beat order, and the interviewer must go first — Script validates that, and
    # it is the order a reel is heard in anyway.
    lines: list[tuple[str, str]] = []
    if text_interviewer.strip():
        lines.append(("interviewer", text_interviewer.strip()))
    if text_student.strip():
        lines.append(("student", text_student.strip()))
    if not lines:
        raise HTTPException(400, "type something for the voices to say")
    if lines[0][0] != "interviewer":
        lines.insert(0, ("interviewer", "Here is the question."))

    with _VOICE_LOCK:
        _VOICE_JOBS[job_id] = {"status": "queued", "error": None,
                               "audio_url": None, "refs": refs}
        _evict_voice_jobs()
    _VOICE_POOL.submit(_voice_job, job_id, refs, lines)
    return {"job_id": job_id, "status": "queued", "speakers": sorted(refs)}


@app.get("/api/voice/job/{job_id}")
def voice_job(job_id: str):
    """How far a preview has got. Poll this; it is cheap and does no work."""
    with _VOICE_LOCK:
        job = _VOICE_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    # `refs` are server-side paths; the browser has no use for them.
    return {"job_id": job_id,
            **{k: v for k, v in job.items() if k != "refs"},
            "speakers": sorted(job.get("refs") or {})}


@app.get("/api/voice/lab/{name}")
def voice_lab_audio(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        raise HTTPException(400, "bad name")
    path = config.OUTPUT_DIR / "voice-lab" / Path(name).stem / "audio.mp3"
    if not path.exists():
        raise HTTPException(404, "not rendered")
    return FileResponse(path, media_type="audio/mpeg")


@app.post("/api/voice/adopt")
def voice_adopt(job_id: str = Form(...)):
    """
    Keep these voices. Copies each speaker's clip into voices/ and makes it live.

    Takes no speaker argument any more: the job already knows which slots were
    filled, so adopting is "keep what I just listened to" rather than a second set
    of choices made after the fact.

    Writes voices/settings.json rather than .env — the choice was made by ear in
    the app, and it has to survive a restart without sending anyone to an editor.
    """
    with _VOICE_LOCK:
        job = _VOICE_JOBS.get(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(400, "those voices have not been generated yet")

    config.VOICE_DIR.mkdir(parents=True, exist_ok=True)
    settings = config.voice_settings()
    adopted = []
    for who, ref in (job.get("refs") or {}).items():
        src = Path(ref)
        dest = config.VOICE_DIR / f"{who}{src.suffix}"
        dest.write_bytes(src.read_bytes())
        settings[who] = str(dest)
        adopted.append(who)
    # One voice uploaded means both speakers use it, rather than half a
    # configuration that cannot narrate a reel.
    if len(adopted) == 1:
        other = "student" if adopted[0] == "interviewer" else "interviewer"
        settings.setdefault(other, settings[adopted[0]])
    settings["provider"] = "chatterbox"
    config.VOICE_SETTINGS.write_text(json.dumps(settings, indent=2))
    config.TTS_PROVIDER = "chatterbox"
    return {"ok": True, "adopted": adopted, **_voice_state()}


@app.post("/api/voice/keep")
async def voice_keep(
    clip_interviewer: UploadFile | None = File(default=None),
    clip_student: UploadFile | None = File(default=None),
):
    """
    Keep uploaded clips as the narration voices, WITHOUT previewing them first.

    THE PREVIEW WAS MANDATORY AND SHOULD NOT HAVE BEEN. Adopting used to work only
    from a finished preview job, so the button sat disabled until someone had
    pressed "Speak it" and waited out a two-minute model load. Uploading two clips
    and pressing Keep — the obvious thing — did nothing at all, silently, because a
    disabled button has no way to say why.

    Previewing is still there and still worth doing; it is just not a toll gate on
    the way to saving. This path costs nothing and takes no time: the clips are
    copied and recorded, and the model is not loaded until something is narrated.
    """
    uploads = [("interviewer", clip_interviewer), ("student", clip_student)]
    if not any(u for _, u in uploads):
        raise HTTPException(400, "upload a voice for at least one speaker")

    config.VOICE_DIR.mkdir(parents=True, exist_ok=True)
    settings = config.voice_settings()
    kept = []
    for who, upload in uploads:
        if upload is None:
            continue
        raw = await upload.read()
        if len(raw) < 4000:
            raise HTTPException(
                400, f"the {who} clip is too short to clone a voice from — "
                     f"7 to 20 seconds of clear speech works best")
        suffix = Path(upload.filename or "clip.wav").suffix.lower()
        if suffix not in (".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"):
            suffix = ".wav"
        # One name per speaker, so replacing a voice replaces its file rather than
        # leaving the old one behind for the next reader to wonder about.
        for stale in config.VOICE_DIR.glob(f"{who}.*"):
            stale.unlink(missing_ok=True)
        dest = config.VOICE_DIR / f"{who}{suffix}"
        dest.write_bytes(raw)
        settings[who] = str(dest)
        kept.append(who)

    # One voice uploaded means both speakers use it, rather than half a
    # configuration that cannot narrate a reel.
    if len(kept) == 1:
        other = "student" if kept[0] == "interviewer" else "interviewer"
        settings[other] = settings[kept[0]]
    settings["provider"] = "chatterbox"
    config.VOICE_SETTINGS.write_text(json.dumps(settings, indent=2))
    config.TTS_PROVIDER = "chatterbox"
    return {"ok": True, "kept": kept, **_voice_state()}


@app.post("/api/voice/reset")
def voice_reset():
    """Go back to whatever .env says — undo an adoption."""
    config.VOICE_SETTINGS.unlink(missing_ok=True)
    config.TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip()
    return {"ok": True, **_voice_state()}


def _voice_state() -> dict:
    from . import providers
    chosen = config.voice_settings()
    cb = providers._REGISTRY["chatterbox"]
    ok, why = cb.available()
    active_ok, active_why = voice.configured()
    return {
        "chosen": {k: v for k, v in chosen.items() if k in ("interviewer", "student")},
        "chatterbox_ready": ok, "chatterbox_reason": why,
        "installed": Path(config.CHATTERBOX_PYTHON).exists(),
        "active": active_why, "active_ok": active_ok,
    }


@app.get("/api/voice/state")
def voice_state():
    return _voice_state()


@app.get("/api/health")
def health():
    return {"ok": True, "stub": config.STUB, "model": config.MODEL_GENERATOR,
            "judge": config.MODEL_JUDGE, "diagram": config.MODEL_DIAGRAM,
            "strategist": config.MODEL_STRATEGIST,
            # The vision judge reports whether it CAN run, not just which model it
            # would use. It needs a Chromium to rasterise with, and the failure
            # mode when there is none is silent by design — the pipeline carries on
            # with the structural graders — so the fact that the last gate is not
            # running has to be visible somewhere.
            "vision_judge": config.MODEL_VISION_JUDGE if config.VISION_JUDGE else None,
            "vision_judge_ready": bool(config.VISION_JUDGE and raster.available()),
            # Surfaced, not buried in a log nobody reads. A misconfigured judge is
            # invisible by construction — it approves everything — so the one place
            # it can be noticed is next to the model name it applies to.
            "model_warnings": config.model_warnings(),
            "units": len(feed.collect()),
            "total": usage.totals()}


# --------------------------------------------------------------- serve the app

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIST / "index.html")


def main():
    import argparse, uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    # 127.0.0.1 BY DEFAULT, deliberately: this serves an unauthenticated API that
    # can spend money on model calls, so it should not appear on a network unless
    # somebody asks. `--host 0.0.0.0` is the ask — for opening the reels on a phone
    # or a second machine, which is the one thing localhost cannot do.
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 to reach it from other devices on your network")
    args = ap.parse_args()
    if not WEB_DIST.exists():
        print("note: web/dist not built — run `cd web && npm run build`, "
              "or use `npm run dev` on :5173 which proxies here")
    if args.host not in ("127.0.0.1", "localhost"):
        import socket
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            lan = probe.getsockname()[0]
            probe.close()
        except Exception:
            lan = args.host
        print(f"\n  reachable from other devices at  http://{lan}:{args.port}")
        print(f"  the voice you keep lives on THIS machine, so every device that\n"
              f"  opens that address shares it — upload once, not once per device.")
        print(f"  note: recording from a microphone needs localhost or https, so\n"
              f"  on other devices use the upload button.\n")
    uvicorn.run("shorts.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
