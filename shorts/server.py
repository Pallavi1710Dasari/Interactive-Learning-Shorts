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
import json, re, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .schema import Script, Topic, Section, ShortUnit
from .parse import parse_markdown, find_section
from .skills.select import select_topics_with_notes
from .skills.script import write_script
from .skills.visuals import spec_visuals, render_diagrams
from .skills.audit import audit
from . import checks, config, feed, usage

app = FastAPI(title="Interactive Learning Shorts")
usage.load()   # cumulative across restarts

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
                     "visual_ref": b.visual_ref}
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
        script = write_script(body.topic, section, feedback)
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
        try:
            section = find_section(sections, topic.source_section_id)
        except KeyError as e:
            return {"topic": topic.model_dump(), "error": str(e)}
        feedback, script, graders = None, None, []
        for _ in range(3):
            script = write_script(topic, section, feedback)
            graders = _graders(script, section, doc_text)
            if all(g["passed"] for g in graders):
                break
            feedback = "\n".join(f"- {g['name']}: {g['reason']}"
                                 for g in graders if not g["passed"])
        return {"topic": topic.model_dump(), "section_id": section.section_id,
                "qa": _as_qa(script), "graders": graders}

    with ThreadPoolExecutor(max_workers=min(6, len(body.topics) or 1)) as pool:
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
        script = write_script(body.topic, section, feedback, current=current)
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


@app.post("/api/finalize")
def finalize(body: FinalizeIn):
    """Turn approved Q&A into units on disk, then hand back the reel payload."""
    if not body.approved:
        raise HTTPException(400, "nothing approved")

    cursor = usage.mark()
    sections = _sections(body.doc_id)
    built, failed = [], []

    def build_one(item: dict) -> tuple[str | None, dict | None]:
        """One approved Q&A -> one unit on disk. Returns (short_id, failure)."""
        try:
            topic = Topic(**item["topic"])
            section = find_section(sections, topic.source_section_id)
            script = Script(short_id=topic.id, question=item["qa"]["question"],
                            beats=item["qa"]["beats"])
        except Exception as e:
            return None, {"topic_id": item.get("topic", {}).get("id"), "error": str(e)}

        try:
            visuals = spec_visuals(script)
            if body.do_svg:
                visuals = render_diagrams(visuals, script, section)

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
            if body.do_judge:
                _, report = audit(script, section.text, unit)
                if report:
                    unit.eval = report
            (config.OUTPUT_DIR / f"{unit.short_id}.json").write_text(
                unit.model_dump_json(indent=2))
            return unit.short_id, None
        except Exception as e:
            # One bad short must not lose the others in the batch — they have
            # already been paid for by the time anything can go wrong here.
            return None, {"topic_id": item.get("topic", {}).get("id"), "error": str(e)}

    # Shorts are independent, so build them side by side rather than end to end.
    with ThreadPoolExecutor(max_workers=min(4, len(body.approved))) as pool:
        for short_id, failure in pool.map(build_one, body.approved):
            if short_id:
                built.append(short_id)
            elif failure:
                failed.append(failure)

    # Only what this build produced. Returning every unit in output/ meant
    # approving one short and then being shown seven, which is not what the
    # reviewer asked for.
    fresh = [s for s in feed.collect() if s["short_id"] in set(built)]
    return {"built": built, "failed": failed, "shorts": fresh,
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


@app.get("/api/health")
def health():
    return {"ok": True, "stub": config.STUB, "model": config.MODEL_GENERATOR,
            "judge": config.MODEL_JUDGE, "units": len(feed.collect()),
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
