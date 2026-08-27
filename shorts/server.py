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
import json, re, threading, uuid
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
            visuals, design_problems = design_visuals(script, section,
                                                      draw=body.do_svg)

            unit = ShortUnit(
                short_id=script.short_id,
                session_id=Path(_doc_path(body.doc_id)).stem,
                source_section_id=section.section_id,
                question=script.question,
                estimated_seconds=script.estimated_seconds,
                beats=script.beats,
                visuals=visuals,
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
                unit = _rejudge_after_fix(unit, script, topic, section, body) or unit

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
    return {"built": built, "failed": failed, "warnings": warned, "shorts": fresh,
            "quarantined": held,
            "usage": usage.since(cursor), "total": usage.totals()}


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


@app.get("/api/shorts")
def shorts():
    """Everything currently in output/, in the shape the reel player wants."""
    return {"shorts": feed.collect()}


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
#: One render at a time. Each already runs three browsers of its own (see
#: video.DEFAULT_WORKERS); letting two shorts render at once just makes both slower.
_RENDER_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="render")


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


@app.get("/api/health")
def health():
    return {"ok": True, "stub": config.STUB, "model": config.MODEL_GENERATOR,
            "judge": config.MODEL_JUDGE, "diagram": config.MODEL_DIAGRAM,
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
    args = ap.parse_args()
    if not WEB_DIST.exists():
        print("note: web/dist not built — run `cd web && npm run build`, "
              "or use `npm run dev` on :5173 which proxies here")
    uvicorn.run("shorts.server:app", host="127.0.0.1", port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
