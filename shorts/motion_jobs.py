"""
The web UI's motion reel runner: python -m shorts.motion_reel's stages and
human gates, driven by clicks instead of a terminal.

    Upload (the reading material, then the recommended options and the
            whole-reel estimate — Start is the one confirmation)
    -> Topic -> Teaching approach -> Template -> Theme -> Script -> Scenes
    -> Voice & timing (local, free, clip X of N) -> Done (the player)

AT EVERY STEP THE AI RECOMMENDS AND THE REVIEWER DECIDES. Each review carries
`recommended` (the choice, with a one-line reason) and `options` (every
alternative, with a short description). `decide(job, "approve", choice=...)`
continues with the reviewer's pick — the recommendation when `choice` is
omitted. A pick is respected downstream: the section pins the topic search,
the language and the template pin the theme, the theme pins the script, the
characters and preset go into the plan.

Theme, script and scenes stop at a pre-flight (status "preflight") before
they spend; the page shows that stage's cost and the reel's total against the
cap, and "proceed" starts it. "skip" (shown as "Stop here for now") leaves the
stage pending, exactly as the CLI's skip does: resume shows it again.

ERRORS ARE EXPLAINED, NOT DUMPED. A failure sets job["error"]: what went
wrong, whether anything was lost or charged, and what to do next, in plain
words — and the technical details (the traceback) only behind "Show details".

Every artifact is written by the same shorts/motion_reel helpers the CLI
uses, ONLY on approval, so resuming never pays again for an approved stage.
A JOB is persisted as output/_motion_jobs/<id>.json, so a closed tab, an
error, a cap stop or a server restart can all be resumed. One stage
operation runs at a time across the server (_LOCK): usage listeners and the
model routing (motion_models.use) are process-wide.
"""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import checks, config, motion_models, motion_themes, preflight, review, usage
from . import motion_reel as mr
from . import workflow as question_workflow
from .parse import find_section, parse_markdown
from .schema import (MOTION_FORMATS, MOTION_TEMPLATES, MotionScript, MotionThemeChoice, QuestionWorkflow,
                     SectionUnderstanding)
from .skills.select import select_topics_with_selections
from .skills.understanding import understanding_for

#: The job's stages. The page shows them as eight steps and Done:
#: Upload (options) -> Topic -> Teaching approach -> Template -> Theme ->
#: Script -> Scenes -> Voice & timing (voice, timing) -> Done.
STAGES = ["options", "topic", "approach", "template", "theme", "script", "scenes",
          "voice", "timing", "done"]
REVIEW_STAGES = {"topic", "approach", "template", "theme", "script", "scenes"}
LABELS = {"options": "upload", "topic": "topic", "approach": "teaching approach",
          "template": "template", "theme": "theme", "script": "script", "scenes": "scenes",
          "voice": "voice", "timing": "timing", "done": "done"}
#: Topic candidates the selection call returns: the recommendation and two
#: alternatives, from the same one call.
TOPIC_CHOICES = 3

#: One line per teaching approach, for the reviewer choosing among them.
APPROACHES = {
    "analogy": "Explain it through a familiar everyday comparison.",
    "real_world_example": "Show it in a concrete real situation the learner knows.",
    "code": "Teach it through the code itself, line by line.",
    "conceptual_visual": "Draw its structure or how its state changes.",
    "process_demonstration": "Walk through what happens, step by step, in order.",
    "comparison": "Set two things side by side; the concept is the difference.",
    "direct_explanation": "Say it plainly, one clear idea after another.",
    "predict_then_reveal": "Ask the viewer to guess first, then show what really happens.",
    "misconception_repair": "Name the wrong idea, show where it breaks, replace it with the right one.",
    "build_from_zero": "Build it up from nothing, one piece at a time.",
    "worked_example_then_try": "Solve one example fully, then give the viewer one to try.",
    "socratic_questions": "Lead the learner there with a chain of questions.",
    "big_picture_then_zoom": "Show the whole system first, then zoom into this one part.",
    "step_by_step_trace": "Run the code line by line and track how the values change.",
}
TEMPLATES = {
    "fix_story": "A problem story: the symptom, why it happens, and the fix working.",
    "walkthrough": "A step-by-step walk: one example followed through 2 to 4 steps.",
}

_LOCK = threading.Lock()
_RUNNING: set[str] = set()
_SAVE_LOCK = threading.Lock()


class Busy(Exception):
    """The job already has a stage running."""


class Stale(Exception):
    """A click made on a screen the job has already moved past (a double
    click, or a second tab): refused, so no decision is ever applied twice."""


_JOB_LOCKS: dict[str, threading.Lock] = {}
_JOB_LOCKS_GUARD = threading.Lock()


def job_lock(job_id: str) -> threading.Lock:
    """One lock per job: the server answers requests on several threads, and
    two clicks on the same step must not both act on it."""
    with _JOB_LOCKS_GUARD:
        return _JOB_LOCKS.setdefault(job_id, threading.Lock())


def locked(job_id: str, fn, *args, expect: str | None = None, **kw) -> dict:
    """Run `fn(job, ...)` on the job as it is NOW, under its lock. `expect`
    is the "stage/status" the reviewer's screen showed; if the job has moved
    on since, the click is refused (Stale)."""
    with job_lock(job_id):
        job = load(job_id)
        if expect and expect != f"{job['stage']}/{job['status']}":
            raise Stale(f"{job['stage']}/{job['status']}")
        return fn(job, *args, **kw)


# ===================================================================== store

def jobs_dir() -> Path:
    return config.OUTPUT_DIR / "_motion_jobs"


def _path(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        raise KeyError(job_id)
    return jobs_dir() / f"{job_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def save(job: dict) -> None:
    with _SAVE_LOCK:
        jobs_dir().mkdir(parents=True, exist_ok=True)
        job["updated"] = _now()
        tmp = _path(job["job_id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(job, indent=1), encoding="utf-8")
        tmp.replace(_path(job["job_id"]))


def load(job_id: str) -> dict:
    path = _path(job_id)
    if not path.exists():
        raise KeyError(job_id)
    job = json.loads(path.read_text(encoding="utf-8"))
    if job["status"] == "running" and job_id not in _RUNNING:
        # the server stopped while a stage ran: nothing was approved by it
        _fail(job, "The server stopped while this step was running",
              "The app was restarted (or closed) in the middle of this step, so it "
              "did not finish.", retry="Run this step again")
        save(job)
    return job


def list_jobs() -> list[dict]:
    if not jobs_dir().exists():
        return []
    out = []
    for p in sorted(jobs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            out.append(view(load(p.stem)))
        except (KeyError, ValueError):
            continue
    return out


def _log(job: dict, stage: str, action: str, note: str = "") -> None:
    job.setdefault("history", []).append({"time": _now(), "stage": stage, "action": action,
                                          "note": note})


def new_job(doc_path: Path, doc_name: str, fmt: str = "reel") -> dict:
    """A new job at its options screen. `fmt`: "reel" or "video" — what the
    reviewer chose to make when uploading (start may still change it)."""
    job = {
        "job_id": uuid.uuid4().hex[:12], "created": _now(), "started": _now(),
        "doc_path": str(doc_path), "doc_name": doc_name,
        "options": default_options() | {"format": fmt}, "short_id": None,
        "stage": "options", "status": "options", "activity": None, "activity_info": None,
        "progress": None, "review": None, "preflight": None, "message": "", "error": None,
        "calls": [], "data": {}, "history": [], "stub": bool(config.STUB),
    }
    save(job)
    return job


def default_options() -> dict:
    """The CLI's defaults, except characters: ON in the UI (one per speaker)."""
    return {"format": "reel", "section": None, "language": None, "theme": None, "template": None,
            "characters": True, "character": None,
            # the Characters step (2026-10-13): who asks (two speakers), each
            # speaker's voice, and whether the reviewer has confirmed them
            "host_character": None, "voices": {}, "cast_confirmed": False}


# ===================================================================== views

def _sections(job: dict) -> list:
    return parse_markdown(job["doc_path"])


def _doc_text(job: dict) -> str:
    return Path(job["doc_path"]).read_text(encoding="utf-8")


def _state(job: dict) -> dict:
    return mr._load_setup(job["short_id"])


def spent(job: dict) -> dict:
    """The reel's spend: every other run of it, plus this job's calls."""
    mine = round(sum(c["cost"] for c in job["calls"]), 6)
    earlier = mr.earlier_runs_cost(job["short_id"], job["started"]) if job["short_id"] else 0.0
    return {"reel": round(earlier + mine, 4), "job": round(mine, 4), "earlier": round(earlier, 4),
            "cap": _cap(job), "calls": len(job["calls"]),
            "estimated": any(c.get("estimated") for c in job["calls"])}


def view(job: dict) -> dict:
    """What the browser gets: the job without its internal scratch data."""
    out = {k: v for k, v in job.items() if k not in ("data", "calls")}
    out["cost"] = spent(job)
    out["running"] = job["job_id"] in _RUNNING
    out["stages"] = STAGES
    out["summary"] = summary(job)
    if job["short_id"]:
        out["links"] = {"reel": f"#motion/reel/{job['short_id']}",
                        "player": f"#motion-reel/{job['short_id']}"}
    return out


def summary(job: dict) -> dict:
    """What was decided at each step so far, in words — the one-screen view
    shows every finished step with its choice. Only finished steps appear."""
    out: dict[str, dict] = {}
    d, opts, sid = job["data"], job["options"], job["short_id"]
    if job["stage"] != "options":
        out["options"] = {"value": job["doc_name"], "detail": ", ".join(filter(None, [
            "a video (6-12 min, landscape)" if opts.get("format") == "video" else "a reel",
            f"section {opts['section']}" if opts.get("section") else "AI picks the section",
            opts.get("language") or "language detected",
            "characters on" if opts.get("characters") else "characters off",
            opts.get("character") or None]))}
    if opts.get("cast_confirmed") and opts.get("avatars"):
        from . import motion_character_presets as mcp
        from . import motion_voice
        names = mcp.defaults()
        vlabels = {k: v[1] for k, v in motion_voice.available_voices().items()}
        parts = [f"{(names.get(a, {}).get('name') or a)}{' (host)' if a == 'host' else ''} · "
                 f"{vlabels.get(opts['voices'].get(r, ''), 'voice')}" for r, a in opts["avatars"].items()]
        out["cast"] = {"value": ", ".join(parts) + ("" if opts.get("characters") else " — avatars off"),
                       "detail": f"{len(parts)} speaker{'s' if len(parts) > 1 else ''}"}
    if d.get("workflow"):
        wf = QuestionWorkflow(**d["workflow"])
        out["topic"] = {"value": wf.effective_question,
                        "detail": f"from section {wf.selection.topic.source_section_id}"}
        a = wf.approved_teaching_approach
        if a is not None:
            out["approach"] = {"value": a.primary.replace("_", " "),
                               "detail": APPROACHES.get(a.primary, "")}
    if sid:
        state = _state(job)
        out["template"] = {"value": state["template"].replace("_", " "),
                           "detail": TEMPLATES.get(state["template"], "")}
        theme = mr._load_theme(sid)
        if theme is not None:
            spec = motion_themes.registry().themes[theme.theme]
            out["theme"] = {"value": spec.label, "detail": _first_sentence(spec.description, 120)}
        if mr.motion_path(sid).exists():
            script = _scripted(job)
            out["script"] = {"value": f"{len(script.shots)} shots, about "
                                      f"{round(script.estimated_seconds)} seconds",
                             "detail": f"teaches {script.concept_name}"}
            if mr._scenes_done(script):
                out["scenes"] = {"value": f"{len(script.shots)} scenes", "detail": "every shot drawn"}
        if job["stage"] == "done" and mr.plan_path(sid).exists():
            plan = json.loads(mr.plan_path(sid).read_text(encoding="utf-8"))
            out["voice"] = {"value": f"{plan.get('duration', 0):.0f} seconds, voiced and timed",
                            "detail": "stub mode: silent" if job.get("stub") else "Chatterbox voice"}
    return out


def _first_sentence(text: str, limit: int = 150) -> str:
    flat = re.sub(r"\s+", " ", re.sub(r"[`*#>]", "", text or "")).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", flat)
    out = m.group(1) if m else flat
    return out if len(out) <= limit else out[:limit - 1].rstrip() + "…"


def _model_name(label: str) -> str:
    """"anthropic/claude-opus-5.5" -> "Claude Opus 5.5"; stub mode says so."""
    if config.STUB:
        return "the stub (free, instant)"
    model = motion_models.model_for(label) or config.MODEL_GENERATOR
    name = model.split("/")[-1].replace("-", " ")
    return " ".join(w.capitalize() if not re.match(r"\d", w) else w for w in name.split())


def _video_rows(rows: list[dict]) -> list[dict]:
    """The whole-reel estimate made a video's: its script calls cost what the
    script gate plans for a video (motion_reel.SCRIPT_TOKENS), and its scenes
    are asked in motion_reel.VIDEO_SCENE_CALLS batches."""
    def ratio(plan) -> float:
        reel, video = plan("reel")[0].cost_per_call, plan("video")[0].cost_per_call
        return video / reel if reel else 1.0
    out = []
    for r in rows:
        r = dict(r)
        k = ratio(mr.script_plan) if r["label"] in ("motion_script", "motion_hook_fix") \
            else ratio(mr.scenes_plan) if r["label"].startswith("motion_scenes") else 1.0
        if r["label"] == "motion_scenes":
            r["typical_calls"] = r["worst_calls"] = mr.VIDEO_SCENE_CALLS
        if r["label"] == "motion_script":
            r["worst_calls"] = config.MAX_VIDEO_SCRIPT_ATTEMPTS
        if r["label"] == "motion_hook_fix":
            r["worst_calls"] = config.MAX_VIDEO_SCRIPT_ATTEMPTS * config.MAX_MOTION_HOOK_FIX_RETRIES
        if r["label"] == "motion_shot_fix":
            # one targeted repair round is the usual case for 120+ captions
            r["typical_calls"] = 1
            r["worst_calls"] = config.MAX_VIDEO_SCRIPT_ATTEMPTS * config.MAX_VIDEO_SHOT_FIX_ROUNDS
        r["per_call"], r["per_call_worst"] = round(r["per_call"] * k, 4), round(r["per_call_worst"] * k, 4)
        r["typical"] = round(r["per_call"] * r["typical_calls"], 4)
        r["worst"] = round(r["per_call_worst"] * r["worst_calls"], 4)
        out.append(r)
    return out


def options_info(job: dict) -> dict:
    """The upload step's recommendations, each with its reason and every
    alternative with a short description, plus the whole-reel estimate.
    Free: no model call."""
    from . import motion_character_presets as mcp
    from .motion_identities import identity
    sections = _sections(job)
    doc = _doc_text(job)
    rows = motion_models.estimate(doc)
    if _format(job) == "video":
        rows = _video_rows(rows)
    lang, how = motion_themes.detect_language(doc, doc)
    how = re.sub(r"`{3}\s*", "", how)          # "the section's ```jsx code" -> "jsx code"
    presets = mcp.defaults()

    def preset_label(pid: str) -> str:
        name = presets.get(pid, {}).get("name") or pid
        return name if name.lower() == pid else f"{name} ({pid})"

    def lang_name(tag: str) -> str:
        try:
            return identity(tag).name
        except Exception:
            return tag
    return {
        "section": {
            "recommended": {"value": None, "label": "Let the AI choose the section",
                            "reason": f"It reads all {len(sections)} sections and picks the "
                                      f"idea most worth a reel."},
            "options": [{"value": s.section_id, "label": f"{s.section_id}  {s.title}",
                         "description": _first_sentence(s.text)} for s in sections],
        },
        "language": {
            "recommended": {"value": lang, "label": lang_name(lang),
                            "reason": f"Detected from {how}."},
            "options": [{"value": t, "label": lang_name(t),
                         "description": f"Tags, badge and voices for {lang_name(t)}."}
                        for t in motion_themes.language_tags()],
        },
        "characters": {
            "recommended": {"value": True, "label": "On — one animated character per speaker",
                            "reason": "A face on screen makes a reel easier to follow; a "
                                      "two-speaker reel gets two."},
            "options": [{"value": True, "label": "On",
                         "description": "One per speaker: two on a dialogue, one narrator "
                                        "otherwise."},
                        {"value": False, "label": "Off",
                         "description": "Scenes only, no characters."}],
        },
        "character": {
            "recommended": {"value": None, "label": f"{preset_label(lang)}",
                            "reason": f"The character made for {lang_name(lang)} material."},
            "options": [{"value": p, "label": preset_label(p),
                         "description": "The host who asks the questions." if p == "host"
                         else f"Plays {lang_name(p)}." if p in motion_themes.language_tags()
                         else "An extra character."}
                        for p in presets if p != "host"],
        },
        "estimate": {"rows": [r for r in rows if r["worst_calls"] or r["typical_calls"]],
                     "typical": round(sum(r["typical"] for r in rows), 4),
                     "worst": round(sum(r["worst"] for r in rows), 4),
                     "cap": _cap(job)},
        "sections_count": len(sections),
    }


def _results(results: list) -> list[dict]:
    return [{"name": r.name, "passed": r.passed, "reason": r.reason} for r in results]


# ===================================================================== errors

#: Provider failures, in plain words: (exception class name, what happened,
#: what to do). Matched by name so this module does not import the SDK.
_PROVIDER = (
    ("RateLimitError", "The AI service is busy and asked us to slow down.",
     "Wait a minute, then retry."),
    ("AuthenticationError", "The AI service did not accept the API key.",
     "Check ANTHROPIC_API_KEY in the .env file, restart the server, then retry."),
    ("PermissionDeniedError", "The AI service refused the request — usually a spending limit "
     "on the key, or a model the key may not use.",
     "Check the key's limits with your provider, then retry."),
    ("APIConnectionError", "The AI service could not be reached.",
     "Check the internet connection, then retry."),
    ("APITimeoutError", "The AI service took too long to answer.", "Retry."),
    ("APIStatusError", "The AI service returned an error.", "Retry in a moment."),
    ("UnroutedLabel", "This step asked for a model that is not set up for motion reels.",
     "This needs a fix in shorts/motion_models.yaml — tell the developer."),
)


def _fail(job: dict, title: str, what: str, *, retry: str = "Retry this step",
          next_step: str = "", details: str = "", cost: float = 0.0, calls: int = 0) -> None:
    """Put the job in the error state, explained: what went wrong, whether
    anything was lost or charged, and what to do next."""
    kept = _kept(job)
    charged = ("Nothing was charged (stub mode)." if config.STUB
               else f"This attempt cost ${cost:.4f} ({calls} call{'s' if calls != 1 else ''}) "
                    f"before it failed." if calls else "Nothing was charged for this attempt.")
    job.update(status="error", activity=None, activity_info=None, progress=None,
               error={"title": title, "what": what,
                      "lost": f"Nothing you approved was lost{': ' + kept if kept else ''}. "
                              f"{charged}",
                      "next": next_step or f"Press “{retry}” to run this step again.",
                      "action": retry, "details": details[-6000:]},
               message=title)


def _kept(job: dict) -> str:
    """The approved steps the reel keeps, in words ("topic and theme")."""
    sid = job["short_id"]
    done = []
    if sid:
        done += ["topic", "teaching approach", "template"]
        if mr.theme_path(sid).exists():
            done.append("theme")
        if mr.motion_path(sid).exists():
            done.append("script")
            try:
                if mr._scenes_done(MotionScript.model_validate_json(
                        mr.motion_path(sid).read_text(encoding="utf-8"))):
                    done.append("scenes")
            except Exception:
                pass
    elif job["data"].get("workflow"):
        done.append("topic")
    if not done:
        return ""
    items = done[0] if len(done) == 1 else ", ".join(done[:-1]) + " and " + done[-1]
    return f"your approved {items} {'is' if len(done) == 1 else 'are'} saved"


def _explain(job: dict, exc: Exception, cost: float, calls: int) -> None:
    trace = traceback.format_exc()
    name = type(exc).__name__
    names = {c.__name__ for c in type(exc).__mro__}
    doing = (job.get("activity") or "this step").rstrip(".…")
    for cls, what, nxt in _PROVIDER:
        if cls in names:
            return _fail(job, f"The AI service failed while {doing.lower()}", what,
                         next_step=nxt, details=f"{name}: {exc}\n\n{trace}",
                         cost=cost, calls=calls)
    if isinstance(exc, NotImplementedError) and config.STUB:
        return _fail(job, "Stub mode cannot do this step for this material",
                     "Stub mode answers with prepared text, and it has none for this step.",
                     next_step="Retry, or run without stub mode (real calls cost money).",
                     details=f"{name}: {exc}\n\n{trace}", cost=cost, calls=calls)
    _fail(job, f"Something went wrong while {doing.lower()}",
          "The step stopped unexpectedly. This is a problem in the app, not in your "
          "material.", next_step="Retry. If it fails again, open “Show details” and send "
          "them to the developer.", details=f"{name}: {exc}\n\n{trace}", cost=cost, calls=calls)


# =================================================================== workers

#: What each operation tells the reviewer while it runs: the words, the model
#: label it calls (None: local), and roughly how long it takes on real models.
_ACTIVITY = {
    "select": ("Reading your material and choosing the best topic", "select", 20),
    "regen_topic": ("Rewording the question", "select", 15),
    "approach": ("Understanding the section and choosing how to teach it",
                 "teaching_approach", 45),
    "regen_approach": ("Reconsidering how to teach it", "teaching_approach", 15),
    "theme": ("Choosing the reel's format", "motion_theme", 10),
    "script": ("Writing the script", "motion_script", 90),
    "scenes": ("Drawing the scenes", "motion_scenes", 60),
    "voice": ("Recording every line (Chatterbox, on this computer)", None, 0),
    "timing": ("Timing every word to the audio (on this computer)", None, 0),
}


def _activity(job: dict, key: str, eta: float | None = None) -> None:
    text, label, seconds = _ACTIVITY[key]
    model = _model_name(label) if label else "this computer"
    eta = 1 if config.STUB else (eta if eta is not None else seconds)
    job["activity"] = text
    job["activity_info"] = {"key": key, "model": model, "eta_seconds": eta,
                            "since": time.time(), "local": label is None}


def _spawn(job: dict, fn, key: str, *args) -> dict:
    """Run one stage operation on a thread: status "running" while it runs,
    every call's cost on the job (and the reel's cost.json) as it happens."""
    jid = job["job_id"]
    if jid in _RUNNING:
        raise Busy(jid)
    _RUNNING.add(jid)
    job.update(status="running", progress=None, message="", preflight=None, error=None)
    _activity(job, key)
    save(job)
    base = list(job["calls"])

    def work():
        with _LOCK:
            cursor = usage.mark()

            def on_call(_call=None):
                job["calls"] = base + usage.calls_since(cursor)
                if job["short_id"]:
                    mr.record_cost(job["short_id"], job["calls"], job["started"])
                save(job)

            usage.add_listener(on_call)
            try:
                with motion_models.use():
                    fn(job, *args)
            except Exception as e:     # explained on the job page, resumable
                mine = usage.calls_since(cursor)
                _explain(job, e, sum(c["cost"] for c in mine), len(mine))
            finally:
                usage.remove_listener(on_call)
                on_call()
                _RUNNING.discard(jid)
                if job["status"] == "running":
                    job["status"] = "stopped"
                if job["status"] != "error":
                    job["activity"] = job["activity_info"] = None
                save(job)

    threading.Thread(target=work, name=f"motion-job-{jid}", daemon=True).start()
    return job


def _review(job: dict, stage: str, payload: dict) -> None:
    job.update(stage=stage, status="review", review=payload, activity=None,
               activity_info=None, progress=None, error=None)
    # kept, so "Change" can reopen this step later without a new call
    job["data"].setdefault("reviews", {})[stage] = payload


def _stop(job: dict, message: str) -> dict:
    job.update(status="stopped", message=message, activity=None, activity_info=None,
               progress=None, preflight=None, error=None)
    save(job)
    return job


def _gate(job: dict, stage: str, plan: list, then: str, arg=None) -> dict:
    """A paid stage's pre-flight: show the plan, refuse past MAX_REEL_USD,
    wait for "proceed" (motion_reel._money_gate's rule, as a screen)."""
    built = preflight.build_plan(f"motion_{stage}", job["short_id"], plan)
    preflight.write_preflight_json(job["short_id"], built)
    now = spent(job)["reel"]
    projected = round(now + built["total_cost"], 4)
    cap = _cap(job)
    fits = projected <= cap
    what = "video (MAX_VIDEO_USD)" if _format(job) == "video" else "reel (MAX_REEL_USD)"
    job.update(stage=stage, status="preflight" if fits else "cap", review=None, error=None,
               preflight={"stage": stage, "models": built["models"],
                          "total": built["total_cost"], "spent": now,
                          "projected": projected, "cap": cap, "fits": fits,
                          "then": then, "arg": arg},
               message="" if fits else (
                   f"This step could cost up to ${built['total_cost']:.2f}. With "
                   f"${now:.2f} already spent, that could reach ${projected:.2f} — over the "
                   f"${cap:.2f} limit for one {what}. Nothing was spent."))
    save(job)
    return job


# ======================================================================= setup

def start(job: dict, options: dict) -> dict:
    """The one confirmation: the reviewer saw the estimate and the options."""
    opts = default_options() | {k: v for k, v in options.items() if k in default_options()}
    for k in ("section", "language", "theme", "template", "character"):
        opts[k] = opts[k] or None
    opts["characters"] = bool(opts["characters"])
    # the format chosen at upload stays unless start names another
    opts["format"] = options.get("format") or job["options"].get("format") or "reel"
    if opts["format"] not in MOTION_FORMATS:
        raise ValueError(f"format {opts['format']!r} is not one of {MOTION_FORMATS}")
    if opts["format"] == "video" and opts["template"] not in (None, "walkthrough"):
        # a video is always a walkthrough (its chapters); the Template step
        # still runs, as the UI's Language step, and pins it (_template_review)
        raise ValueError("a video is always a walkthrough")
    opts["voices"] = dict(opts.get("voices") or {})
    opts["cast_confirmed"] = bool(opts.get("cast_confirmed"))
    if opts["template"] and opts["template"] not in MOTION_TEMPLATES:
        raise ValueError(f"template {opts['template']!r} is not one of {MOTION_TEMPLATES}")
    if opts["theme"] and opts["theme"] not in motion_themes.registry().ids():
        raise ValueError(f"no theme {opts['theme']!r}")
    if opts["language"] and opts["language"] not in motion_themes.language_tags():
        raise ValueError(f"no language {opts['language']!r}")
    if opts["section"] and not any(s.section_id == opts["section"] for s in _sections(job)):
        raise ValueError(f"no section {opts['section']}")
    if opts["character"]:
        from . import motion_character_presets
        if opts["character"] not in motion_character_presets.ids():
            raise ValueError(f"no character preset {opts['character']!r}")
        opts["characters"] = True
    if not config.STUB and not config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set — every text call goes through it")
    job["options"] = opts
    _log(job, "options", "start", json.dumps(opts))
    return _spawn(job, _op_select, "select")


def _op_select(job: dict, section: str | None = None) -> None:
    sections = _sections(job)
    pin = section or job["options"]["section"]
    pool = [s for s in sections if s.section_id == pin] if pin else sections
    _topics, _notes, selections = select_topics_with_selections(pool, target=TOPIC_CHOICES)
    job["data"]["workflows"] = [QuestionWorkflow(selection=s).model_dump() for s in selections]
    _topic_review(job)


def _wf(job: dict, key: str = "workflow") -> QuestionWorkflow:
    if key == "workflows":
        return QuestionWorkflow(**job["data"]["workflows"][0])
    return QuestionWorkflow(**job["data"][key])


def _topic_review(job: dict) -> None:
    wfs = [QuestionWorkflow(**w) for w in job["data"]["workflows"]]
    wf = wfs[0]
    sel = wf.selection
    reasons = [r.explanation for r in sel.reasons if r.explanation]
    _review(job, "topic", {
        "question": wf.effective_question, "original": sel.topic.topic,
        "section_id": sel.topic.source_section_id, "source_title": sel.source_title,
        "why_it_matters": sel.topic.why_it_matters, "answer_quote": sel.topic.answer_quote,
        "reasons": [{"category": r.category, "explanation": r.explanation} for r in sel.reasons],
        "regenerations": wf.question_approval.regeneration_attempts,
        "limit": config.MAX_QUESTION_REGENERATIONS,
        "recommended": {"value": 0, "label": wf.effective_question,
                        "reason": _first_sentence(sel.topic.why_it_matters or
                                                  (reasons[0] if reasons else ""))},
        "options": [{"value": i, "label": w.effective_question,
                     "description": f"From section {w.selection.topic.source_section_id} "
                                    f"({w.selection.source_title}). "
                                    + _first_sentence(w.selection.topic.why_it_matters, 110)}
                    for i, w in enumerate(wfs)],
        "sections": [{"value": s.section_id, "label": f"{s.section_id}  {s.title}",
                      "description": _first_sentence(s.text, 110)} for s in _sections(job)],
        "section_cost": _one_call_cost("select"),
    })


def _one_call_cost(label: str) -> float:
    rows = {r["label"]: r for r in motion_models.estimate("")}
    return round(rows.get(label, {}).get("per_call", 0.0), 4)


def _op_regen_topic(job: dict, reason: str) -> None:
    wf = review.regenerate(_wf(job, "workflows"), reason, _sections(job))
    job["data"]["workflows"][0] = wf.model_dump()
    _topic_review(job)


def _op_approach(job: dict) -> None:
    wf = _wf(job, "workflows")
    sections = _sections(job)
    section = find_section(sections, wf.approved_topic.source_section_id)
    understanding = understanding_for(section, source_text=section.text)
    progress = question_workflow.advance(wf, sections, understanding=understanding)
    job["data"]["understanding"] = understanding.model_dump() if understanding else None
    job["data"]["workflow"] = progress.workflow.model_dump()
    if progress.workflow.teaching_approach is None:
        _fail(job, "The AI did not suggest a teaching approach",
              f"It gave no approach for this topic ({progress.detail}).")
        return
    _approach_review(job)


def _approach_review(job: dict) -> None:
    wf = _wf(job)
    a = wf.effective_teaching_approach
    rec = a.primary if a else None
    others = [k for k in APPROACHES if k != rec]
    # the ones the AI considered come first
    others.sort(key=lambda k: (k not in (a.alternatives if a else []), k))
    _review(job, "approach", {
        "question": wf.effective_question, "approach": a.model_dump() if a else None,
        "regenerations": wf.teaching_approach_approval.regeneration_attempts
        if wf.teaching_approach_approval else 0,
        "limit": config.MAX_TEACHING_APPROACH_REGENERATIONS,
        "recommended": {"value": rec, "label": rec.replace("_", " ") if rec else "",
                        "reason": _first_sentence(a.rationale if a else ""),
                        "description": APPROACHES.get(rec, "")},
        "options": [{"value": k, "label": k.replace("_", " "), "description": APPROACHES[k],
                     "considered": bool(a and k in a.alternatives)} for k in [rec] + others if k],
    })


def _op_regen_approach(job: dict, reason: str) -> None:
    wf = review.regenerate_teaching_approach(_wf(job), reason, _sections(job))
    job["data"]["workflow"] = wf.model_dump()
    _approach_review(job)


def _format(job: dict) -> str:
    """"reel" or "video": what this job makes."""
    return job["options"].get("format") or "reel"


def _cap(job: dict) -> float:
    """This job's spend cap: MAX_VIDEO_USD for a video, MAX_REEL_USD for a reel."""
    return config.MAX_VIDEO_USD if _format(job) == "video" else config.MAX_REEL_USD


def _template_review(job: dict) -> dict:
    wf = _wf(job)
    approach = wf.approved_teaching_approach
    video = _format(job) == "video"
    # a video is always a walkthrough: its one choice
    default = "walkthrough" if video else mr.default_template(approach)
    kind = approach.primary.replace("_", " ") if approach else "the approach"
    _review(job, "template", {
        "default": default, "choices": list(MOTION_TEMPLATES),
        "approach": approach.primary if approach else None,
        "note": "Your choice locks the template: later steps only offer themes that use it.",
        "recommended": {"value": default, "label": default.replace("_", " "),
                        "reason": ("A video teaches in chapters, step by step." if video else
                                   f"A {kind} approach walks through steps in order."
                                   if default == "walkthrough" else
                                   f"A {kind} approach fits a problem-and-fix story."),
                        "description": TEMPLATES[default]},
        "options": [{"value": t, "label": t.replace("_", " "), "description": TEMPLATES[t]}
                    for t in [default] + ([] if video else [t for t in MOTION_TEMPLATES if t != default])],
    })
    save(job)
    return job


def _finish_setup(job: dict, template: str, source: str) -> dict:
    """Setup approved: the reel gets its short_id and setup.json, exactly as
    the CLI's, plus the document and options it was made from."""
    sections = _sections(job)
    wf = _wf(job)
    und = job["data"].get("understanding")
    fmt = job["options"].get("format", "reel")
    state = mr.build_setup_state(sections, wf, SectionUnderstanding(**und) if und else None,
                                 template, source, fmt)
    state["doc_path"] = job["doc_path"]
    state["ui_options"] = job["options"]
    state["design"] = config.MOTION_DESIGN
    # finished again after "Change": the same reel keeps its id (and cost log)
    job["short_id"] = job.get("short_id") or mr._next_free_motion_id(state["topic"]["id"], fmt)
    mr._save_setup(job["short_id"], state)
    mr.record_cost(job["short_id"], job["calls"], job["started"])
    _log(job, "template", "approve", f"{template} ({source})")
    return _enter_theme(job)


# ====================================================================== theme

def _theme_inputs(job: dict, override: str | None = None) -> dict:
    return mr.theme_inputs(job["short_id"], _state(job), _sections(job), _doc_text(job),
                           override, job["options"]["language"])


def _enter_theme(job: dict, override: str | None = None) -> dict:
    override = override or job["options"]["theme"]
    t = _theme_inputs(job, override)
    job["stage"] = "theme"
    if t["plan"] is not None:
        return _gate(job, "theme", t["plan"], "theme", override)
    return _spawn(job, _op_theme, "theme", override)


def _op_theme(job: dict, override: str | None) -> None:
    t = _theme_inputs(job, override)
    try:
        choice = mr.run_theme_choice(t, override)
    except ValueError as e:
        if override == job["options"]["theme"]:
            job["options"]["theme"] = None        # so Retry lets the AI choose again
        _fail(job, "That theme can't be used for this reel", str(e),
              retry="Choose the theme again",
              next_step="Press “Choose the theme again” and pick another theme.")
        return
    job["data"]["theme"] = choice.model_dump()
    _theme_review(job, choice, t)


def _theme_review(job: dict, choice: MotionThemeChoice, t: dict) -> None:
    reg = motion_themes.registry()
    spec = reg.themes[choice.theme]
    who = ([{"label": sp.label, "identity": sp.identity, "voice_slot": sp.voice_slot}
            for sp in motion_themes.cast_speakers(spec, choice.language)]
           if spec.two_speaker else [{"label": "NARRATOR", "identity": None, "voice_slot": None}])
    usable = [i for i in reg.ids()
              if not motion_themes.theme_problems(
                  i, approach=t["approach"].primary if t["approach"] else None,
                  has_code=motion_themes.section_has_code(t["source_text"]),
                  template=t["pin"], history=None, language=t["language"])]
    def said(text: str) -> str:
        # a walkthrough theme's description counts a reel's chapters; a video has more
        if _format(job) != "video":
            return text
        return re.sub(r"\b2 to 4 (numbered )?(chapters|steps)", r"5 to 10 \1\2", text)
    _review(job, "theme", {
        "choice": choice.model_dump(), "label": spec.label, "description": said(spec.description),
        "speakers": who, "language_how": t["how"], "history": t["history"],
        "tag_checks": _results(mr.theme_tag_checks(choice, t)),
        "themes": [{"id": i, "label": reg.themes[i].label, "template": reg.themes[i].template}
                   for i in reg.ids()],
        "pinned_template": t["pin"],
        "recommended": {"value": choice.theme, "label": spec.label,
                        "reason": _first_sentence(choice.reason), "description": said(spec.description)},
        "options": [{"value": i, "label": reg.themes[i].label,
                     "description": _first_sentence(said(reg.themes[i].description), 140),
                     "speakers": "two speakers" if reg.themes[i].two_speaker else "one narrator"}
                    for i in [choice.theme] + [i for i in usable if i != choice.theme]],
    })


# ===================================================================== script

def _theme(job: dict) -> MotionThemeChoice | None:
    return mr._load_theme(job["short_id"])


def _enter_script(job: dict, regenerate: bool = False) -> dict:
    job["stage"] = "script"
    if not regenerate:
        saved = mr.reuse_script(job["short_id"], _state(job), _sections(job), _theme(job))
        if saved is not None:
            script, results, path, repaired = saved
            _script_review(job, script, results,
                           reused=f"A script saved from an earlier attempt now passes every "
                                  f"check{' after its captions were re-cut' if repaired else ''}"
                                  f" — no new call was made.")
            save(job)
            return job
    return _gate(job, "script", mr.script_plan(_format(job)), "script")


def _op_script(job: dict) -> None:
    script, results = mr.write_script(job["short_id"], _state(job), _sections(job), _theme(job))
    _script_review(job, script, results)


def _script_review(job: dict, script: MotionScript | None, results: list,
                   reused: str = "") -> None:
    job["data"]["script"] = script.model_dump(mode="json") if script else None
    facts, warning = [], ""
    if script is not None:
        sections = _sections(job)
        facts = mr.fact_sources(script, sections, _state(job))
        warning = checks.invented_example_warning(script, "\n\n".join(s.text for s in sections))
    job["data"]["facts"] = facts
    _review(job, "script", {
        "script": job["data"]["script"], "results": _results(results), "facts": facts,
        "warning": warning, "reused": reused,
        "passed": script is not None,
        "message": "" if script is not None else
        "None of the attempts passed every check, so there is no script to approve. "
        "Write a new one (this costs money again), or stop here for now.",
    })


# ===================================================================== scenes

def _scripted(job: dict) -> MotionScript:
    return MotionScript.model_validate_json(
        mr.motion_path(job["short_id"]).read_text(encoding="utf-8"))


def _enter_scenes(job: dict) -> dict:
    job["stage"] = "scenes"
    return _gate(job, "scenes", mr.scenes_plan(_format(job)), "scenes")


def _op_scenes(job: dict) -> None:
    scripted, results = mr.write_scenes(job["short_id"], _scripted(job), log=lambda *_: None)
    job["data"]["scenes"] = scripted.model_dump(mode="json")
    shots = []
    for s in scripted.shots:
        sc = s.scene
        shots.append({
            "id": s.id, "beat": s.beat, "speech": s.speech,
            "field": sc.field if sc else None, "transition": sc.transition if sc else None,
            "label": sc.label if sc else None,
            "objects": [{"id": o.id, "kind": o.kind, "brief": {
                k: v for k, v in o.props.items()
                if k in ("text", "title", "label", "items", "value", "lines", "status")}}
                for o in (sc.objects if sc else [])],
            "actions": [{"at": a.at, "do": a.do, "target": a.target, "value": a.value,
                         "tone": a.tone} for a in (sc.actions if sc else [])],
        })
    passed = checks.all_passed(results)
    _review(job, "scenes", {
        "shots": shots, "results": _results(results), "passed": passed,
        "message": "" if passed else
        "The scenes did not pass every check, so they can't be approved. Draw new ones "
        "(this costs money again), or stop here for now.",
    })


# ============================================================== voice, timing

#: SPEED (2026-10-13): the voice depends only on the approved script, so it is
#: recorded while the scenes are being drawn. job_id -> {"thread", "result",
#: "progress": (done, total)}.
_EARLY_VOICE: dict[str, dict] = {}


def _start_voice_early(job: dict) -> None:
    jid, sid, voices = job["job_id"], job["short_id"], job["options"].get("voices") or None
    script = _scripted(job)
    slot = {"result": None, "progress": (0, sum(len(s.captions) for s in script.shots)), "error": None}

    def run():
        try:
            slot["result"] = mr.stage_voice(sid, script, voices=voices,
                                            progress=lambda d, t: slot.__setitem__("progress", (d, t)))
        except Exception as e:                  # noqa: BLE001 — reported by _op_voice_timing
            slot["error"] = e
    t = threading.Thread(target=run, daemon=True)
    slot["thread"] = t
    _EARLY_VOICE[jid] = slot
    t.start()


def _op_voice_timing(job: dict) -> None:
    script = _scripted(job)
    clips = sum(len(s.captions) for s in script.shots)

    def tell(label):
        def cb(done, total):
            job["progress"] = {"done": done, "total": total, "label": label}
            save(job)
        return cb

    job["stage"] = "voice"
    _activity(job, "voice", eta=clips * 4)
    save(job)
    opts = job["options"]
    early = _EARLY_VOICE.pop(job["job_id"], None)
    if early is not None:
        # already recording since the script was approved: wait for it
        while early["thread"].is_alive():
            d, t = early["progress"]
            tell("Line")(d, t)
            early["thread"].join(1.0)
        tell("Line")(*early["progress"])
        manifest = early["result"]
    else:
        manifest = mr.stage_voice(job["short_id"], script, progress=tell("Line"), voices=opts.get("voices") or None)
    if manifest is None:
        _fail(job, "Recording the voice failed",
              "The voice engine on this computer could not record the lines.",
              next_step="Check that Chatterbox is installed (see the README), then retry.")
        return
    job.update(stage="timing", progress=None)
    _activity(job, "timing", eta=clips)
    save(job)
    done = mr.stage_timing(job["short_id"], script, manifest, progress=tell("Line"),
                           characters=bool(opts.get("characters")),
                           character=opts.get("character"),
                           host_character=opts.get("host_character"))
    if done is None:
        _fail(job, "Timing the words failed",
              "The words could not be lined up with the recorded audio.")
        return
    _, results = done
    failed = [r for r in results if not r.passed]
    job.update(stage="done", status="done", progress=None, review=None, error=None,
               message=("Some timing checks did not pass: "
                        + "; ".join(f"{r.name}: {r.reason}" for r in failed)) if failed else "")
    _log(job, "timing", "done")


# ================================================================== decisions

_OPS = {"theme": (_op_theme, "theme"), "script": (_op_script, "script"),
        "scenes": (_op_scenes, "scenes")}


def decide(job: dict, action: str, reason: str = "", choice=None) -> dict:
    """A reviewer's click. At a review: approve (with an optional `choice`
    of the alternatives offered), regenerate, skip; at the topic also
    "section" (find a topic in the section `choice`). At a pre-flight:
    proceed or stop. "choose" is kept for a theme pick that only re-checks."""
    if job["job_id"] in _RUNNING:
        raise Busy(job["job_id"])
    stage, status = job["stage"], job["status"]
    _log(job, stage, action, reason or (str(choice) if choice is not None else ""))

    if action == "back":
        return _back(job, str(choice or ""))
    if action == "cast":
        return _set_cast(job, choice or {})
    if status in ("preflight", "cap"):
        if action == "stop" or status == "cap":
            return _stop(job, f"Stopped before the {LABELS[stage]}. Nothing was spent on it.")
        if action != "proceed":
            raise ValueError("at a pre-flight: proceed or stop")
        pf = job["preflight"]
        fn, key = _OPS[pf["then"]]
        args = (pf["arg"],) if pf["then"] == "theme" else ()
        return _spawn(job, fn, key, *args)

    if status != "review" or stage not in REVIEW_STAGES:
        raise ValueError(f"nothing to decide: the job is {status} at {stage}")
    if action == "skip":
        return _stop(job, f"Stopped at the {LABELS[stage]}, which is still waiting for your "
                          f"decision. Nothing was saved for it. Resume to pick up here.")
    if action == "regenerate" and stage in ("topic", "approach") and not reason.strip():
        raise ValueError("say what should improve")

    if stage == "topic":
        if action == "approve":
            pick = int(choice or 0)
            wfs = job["data"]["workflows"]
            if not 0 <= pick < len(wfs):
                raise ValueError(f"no topic {pick}")
            wfs.insert(0, wfs.pop(pick))      # the chosen topic is the one carried on
            wfs[0] = review.approve_question(QuestionWorkflow(**wfs[0])).model_dump()
            return _spawn(job, _op_approach, "approach")
        if action == "regenerate":
            return _spawn(job, _op_regen_topic, "regen_topic", reason)
        if action == "section":
            if not any(s.section_id == choice for s in _sections(job)):
                raise ValueError(f"no section {choice}")
            job["options"]["section"] = choice           # respected from here on
            return _spawn(job, _op_select, "select", choice)
    if stage == "approach":
        if action == "approve":
            wf = _wf(job)
            current = wf.effective_teaching_approach
            if choice and choice not in APPROACHES:
                raise ValueError(f"no teaching approach {choice!r}")
            if choice and current is not None and choice != current.primary:
                wf = review.select_teaching_approach(wf, choice)
            else:
                wf = review.approve_teaching_approach(wf)
            job["data"]["workflow"] = wf.model_dump()
            if job["options"]["template"]:
                return _finish_setup(job, job["options"]["template"], "flag")
            return _template_review(job)
        if action == "regenerate":
            return _spawn(job, _op_regen_approach, "regen_approach", reason)
    if stage == "template":
        if action == "language":
            # the UI's Language step (2026-10-13): the template is not asked —
            # the approach's default, and the theme the reviewer picks next
            # may change it; the language is set before the theme is chosen
            if choice and choice not in motion_themes.language_tags():
                raise ValueError(f"no language {choice!r}")
            if choice:
                job["options"]["language"] = choice
            # a video's walkthrough is pinned: the theme step offers walkthrough themes only
            return _finish_setup(job, job["review"]["default"],
                                 "flag" if _format(job) == "video" else "default")
        if action == "approve":
            template = choice or job["review"]["default"]
            if template not in MOTION_TEMPLATES:
                raise ValueError(f"template {template!r} is not one of {MOTION_TEMPLATES}")
            if _format(job) == "video" and template != "walkthrough":
                raise ValueError("a video is always a walkthrough")
            # the reviewer saw it and chose it: it pins the theme (CLI fix 2026-10-12)
            return _finish_setup(job, template, "reviewer")
    if stage == "theme":
        if action == "approve":
            if choice and choice != job["data"]["theme"]["theme"]:
                t = _theme_inputs(job, choice)
                try:
                    picked = mr.run_theme_choice(t, choice)     # --theme: no call
                except ValueError as e:
                    raise ValueError(f"{choice} can't be used here: {e}")
                failing = [r for r in mr.theme_tag_checks(picked, t) if not r.passed]
                if failing:
                    raise ValueError("; ".join(r.reason for r in failing))
                job["data"]["theme"] = picked.model_dump()
            mr.save_theme(job["short_id"], MotionThemeChoice(**job["data"]["theme"]))
            return _enter_script(job)
        if action == "choose":
            if not choice:
                raise ValueError("choose which theme")
            return _spawn(job, _op_theme, "theme", choice)
        if action == "regenerate":
            return _enter_theme(job)
    if stage == "script":
        if action == "recheck":
            _recheck_script(job)
            save(job)
            return job
        if action == "approve":
            if not job["data"].get("script"):
                raise ValueError("there is no passing script to approve — write a new one, "
                                 "or stop here for now")
            script = MotionScript(**job["data"]["script"])
            mr.save_script(job["short_id"], script, job["data"].get("facts", []))
            _start_voice_early(job)
            return _enter_scenes(job)
        if action == "regenerate":
            return _enter_script(job, regenerate=True)
    if stage == "scenes":
        if action == "approve":
            if not job["review"].get("passed"):
                raise ValueError("the scenes do not pass every check — draw new ones, or stop "
                                 "here for now")
            mr.save_scenes(job["short_id"], MotionScript(**job["data"]["scenes"]))
            return _spawn(job, _op_voice_timing, "voice")
        if action == "regenerate":
            return _enter_scenes(job)
    raise ValueError(f"{action!r} is not an action at the {LABELS[stage]}")


# ================================================================ back, cast

#: The steps a reviewer can go back to, in order; the reel being made
#: (scenes, voice, timing, done) cannot be undone this way.
BACK_ORDER = ("topic", "approach", "template", "theme", "cast", "script")


def _back(job: dict, target: str) -> dict:
    """Reopen an earlier step with what it showed before (no new call); every
    later step is decided again from there. "cast" reopens the Characters
    step (the reviewer confirms the speakers again)."""
    stage = job["stage"]
    if stage not in ("topic", "approach", "template", "theme", "script") or job["status"] not in (
            "review", "preflight", "stopped", "error", "cap"):
        raise ValueError("the reel is already being made — this step can no longer be changed")
    if target not in BACK_ORDER:
        raise ValueError(f"no step {target!r} to go back to")
    here = "cast" if stage == "script" and not job["options"].get("cast_confirmed") else stage
    if BACK_ORDER.index(target) >= BACK_ORDER.index(here):
        raise ValueError(f"the {target} step is not behind you")
    job["options"]["cast_confirmed"] = False if BACK_ORDER.index(target) <= BACK_ORDER.index("cast") \
        else job["options"].get("cast_confirmed")
    if target == "cast":
        job["status"] = "preflight" if job.get("preflight") else job["status"]
        save(job)
        return job
    saved = (job["data"].get("reviews") or {}).get(target)
    if saved is None:
        raise ValueError(f"the {target} step has nothing to show again")
    _review(job, target, saved)
    job["preflight"] = None
    _log(job, target, "back")
    save(job)
    return job


def cast_info(job: dict) -> dict:
    """The Characters step: the reel's speakers (from the chosen theme) and,
    for each, the recommended avatar and voice with every alternative. Free."""
    from . import motion_character_presets as mcp
    from . import motion_voice
    from .motion_characters import language_preset
    theme = (job["data"].get("theme") or {}).get("theme") or job["options"].get("theme")
    if not theme:
        raise ValueError("the theme is not chosen yet")
    spec = motion_themes.registry().themes[theme]
    language = job["options"].get("language") or "cs"
    voices = motion_voice.available_voices()
    from pathlib import Path as _P
    voice_opts = [{"value": vid, "label": label, "stamp": int(_P(path).stat().st_mtime)}
                  for vid, (path, label) in voices.items()]
    presets = mcp.defaults()

    def label(pid: str) -> str:
        p = presets.get(pid, {})
        name = p.get("name") or pid
        # the host and an extra can share a name ("Arjun"): say which is which
        return f"{name} (host)" if pid == "host" else name
    avatar_opts = [{"value": pid, "label": label(pid), "gender": presets.get(pid, {}).get("gender")}
                   for pid in presets]
    lang = language_preset(language)
    vids = list(voices)
    if len(spec.speakers) > 1:
        cast = motion_themes.cast_speakers(spec, language)
        rows = []
        for sp in cast:
            asking = sp.identity == "host"
            rows.append({"role": sp.role, "label": sp.label,
                         "does": "asks the questions" if asking else "explains",
                         "avatar": "host" if asking else lang,
                         "voice": (vids[0] if asking else vids[min(1, len(vids) - 1)]) if vids else None})
    else:
        rows = [{"role": "narrator", "label": "Narrator", "does": "tells the whole story",
                 "avatar": lang, "voice": vids[0] if vids else None}]
    th = job["data"].get("theme") or {}
    video = _format(job) == "video"
    # a video's mentor presents it, beside the board: always recommended there
    recommend = True if video else bool(th.get("show_avatars", True))
    reason = ("A video is presented: the mentor stands beside the board and points at what "
              "changes, and steps aside while code or a table needs the whole frame."
              if video else th.get("avatar_reason") or "")
    return {"speakers": rows, "avatars": avatar_opts, "voices": voice_opts,
            "characters": bool(job["options"].get("characters", True)) if job["options"].get("cast_confirmed") else recommend,
            "avatars_recommended": recommend,
            "avatars_reason": reason,
            "reason": (f"The {spec.label} style has {len(rows)} speaker{'s' if len(rows) > 1 else ''}, "
                       f"so the {'video' if video else 'reel'} needs {len(rows)} avatar{'s' if len(rows) > 1 else ''} and "
                       f"{len(rows)} voice{'s' if len(rows) > 1 else ''}; each language has its own character.")}


def _recheck_script(job: dict) -> None:
    """FREE: grade the scripts saved from earlier attempts again with today's
    checks (a check fix can make one pass) — no call is made either way."""
    saved = mr.reuse_script(job["short_id"], _state(job), _sections(job), _theme(job))
    if saved is not None:
        script, results, path, repaired = saved
        _script_review(job, script, results,
                       reused="A script saved from an earlier attempt passes every check now — "
                              "no new call was made.")
    elif job.get("review") is not None:
        job["review"]["message"] = ("No saved attempt passes yet. Write a new one (this costs "
                                    "money again), or stop here for now.")
        job["review"]["rechecked"] = True


def _set_cast(job: dict, choice: dict) -> dict:
    """The reviewer's speakers: characters on/off, an avatar and a voice per
    speaker. Two speakers get two different voices."""
    if job["stage"] not in ("script",) or job["status"] not in ("preflight", "review", "stopped"):
        raise ValueError("the characters are chosen after the theme, before the script")
    info = cast_info(job)
    rows = {r["role"]: r for r in info["speakers"]}
    avatars = choice.get("avatars") or {}
    voices = choice.get("voices") or {}
    from . import motion_character_presets as mcp
    from . import motion_voice
    have_v = motion_voice.available_voices()
    for role, pid in avatars.items():
        if role not in rows or pid not in mcp.ids():
            raise ValueError(f"no avatar {pid!r} for {role!r}")
    for role, vid in voices.items():
        if role not in rows or vid not in have_v:
            raise ValueError(f"no voice {vid!r} for {role!r}")
    picked_v = {r: voices.get(r, rows[r]["voice"]) for r in rows}
    picked_a = {r: avatars.get(r, rows[r]["avatar"]) for r in rows}
    if len(rows) > 1 and len(set(picked_v.values())) < len(rows):
        raise ValueError("two speakers need two different voices")
    opts = job["options"]
    opts["characters"] = bool(choice.get("characters", True))
    opts["voices"] = picked_v
    opts["avatars"] = picked_a
    host_role = next((r for r, row in rows.items() if row["does"] == "asks the questions"), None)
    lang_role = next((r for r in rows if r != host_role), None)
    opts["host_character"] = picked_a.get(host_role) if host_role else None
    opts["character"] = picked_a.get(lang_role) if lang_role else opts.get("character")
    opts["cast_confirmed"] = True
    _log(job, "cast", "approve", json.dumps({"avatars": avatars, "voices": picked_v}))
    # a script that failed before is checked again (free) on the way back to it
    if job["status"] == "review" and job.get("review") and not job["review"].get("passed"):
        _recheck_script(job)
    save(job)
    return job


# ===================================================================== resume

def resume(job: dict) -> dict:
    """Carry on where the job stopped, paying for nothing already approved:
    a review still pending shows again as it was; an approved stage's
    artifact on disk moves the job past it. Also the Retry of an error."""
    if job["job_id"] in _RUNNING:
        raise Busy(job["job_id"])
    _log(job, job["stage"], "resume")
    was_error = job["status"] == "error"
    job.update(message="", error=None)
    sid = job["short_id"]
    d = job["data"]
    if not sid:
        if job["stage"] == "options":
            job["status"] = "options"
            save(job)
            return job
        if job["stage"] == "topic" or not d.get("workflow"):
            if d.get("workflows") and _wf(job, "workflows").approved_topic is None:
                _topic_review(job)
                save(job)
                return job
            if d.get("workflows"):
                return _spawn(job, _op_approach, "approach")
            return _spawn(job, _op_select, "select")
        if _wf(job).approved_teaching_approach is None:
            _approach_review(job)
            save(job)
            return job
        if job["options"]["template"]:
            return _finish_setup(job, job["options"]["template"], "flag")
        return _template_review(job)
    if not mr.theme_path(sid).exists():
        if d.get("theme") and job["stage"] == "theme" and not was_error:
            _theme_review(job, MotionThemeChoice(**d["theme"]), _theme_inputs(job))
            save(job)
            return job
        return _enter_theme(job)
    if not mr.motion_path(sid).exists():
        if d.get("script") and job["stage"] == "script":
            script = MotionScript(**d["script"])
            source, kw = _grading(job)
            _script_review(job, script, checks.run_motion_script_graders(script, source, **kw))
            save(job)
            return job
        return _enter_script(job)
    script = _scripted(job)
    if not mr._scenes_done(script):
        return _enter_scenes(job)
    if mr._voice_current(script) and mr.plan_path(sid).exists() and job["stage"] == "done":
        job.update(status="done")
        save(job)
        return job
    return _spawn(job, _op_voice_timing, "voice")


def _grading(job: dict) -> tuple:
    from .skills.script import _motion_grading_texts
    k = mr._script_kwargs(job["short_id"], _state(job), _sections(job), _theme(job))
    source, main, selected = _motion_grading_texts(k["section"], k["source_text"],
                                                   k["supporting_text"], k["template"])
    return source, {"main_text": main, "selected_text": selected, "approach": k["approach"]}


# ========================================================== reels from the CLI

def find_document(state: dict) -> Path | None:
    """The document a CLI reel was made from: setup.json does not record it
    (a reel made in the UI does), so look in content/ and the uploads for one
    whose section quotes what the setup quotes — the topic's answer quote or
    the understanding's source evidence, all verbatim from that section.
    None rather than a guess: another document can have a section 7.2 too."""
    if state.get("doc_path") and Path(state["doc_path"]).exists():
        return Path(state["doc_path"])
    sid = state["section_id"]
    flat = lambda t: re.sub(r"\s+", " ", t or "").strip()
    quotes = [flat((state.get("topic") or {}).get("answer_quote"))] + \
        [flat(q) for q in ((state.get("understanding") or {}).get("source_evidence") or [])]
    quotes = [q[:80] for q in quotes if len(q) >= 20]
    candidates = sorted(Path(config.ROOT / "content").glob("*.md")) + \
        sorted((config.OUTPUT_DIR / "uploads").glob("*.md"))
    for path in candidates:
        try:
            sec = next((x for x in parse_markdown(path) if x.section_id == sid), None)
        except Exception:
            continue
        if sec is not None and any(q in flat(sec.text) for q in quotes):
            return path
    return None


def job_for_reel(short_id: str) -> dict:
    """The job that resumes a reel — its own, or a new one for a reel the CLI
    started (or that predates jobs), at the stage its files say it reached."""
    for j in list_jobs():
        if j["short_id"] == short_id:
            return load(j["job_id"])
    state = mr._load_setup(short_id)
    doc = find_document(state)
    if doc is None:
        raise ValueError(f"Can't find the document {short_id} was made from, so it can't be "
                         f"resumed here. Resume it from the command line: python -m "
                         f"shorts.motion_reel <doc.md> --topic {short_id}")
    job = new_job(doc, doc.name)
    opts = default_options() | (state.get("ui_options") or {})
    opts["format"] = state.get("format") or opts.get("format") or "reel"   # a video stays a video
    job.update(short_id=short_id, options=opts, stage="theme", status="stopped",
               message="This reel was started from the command line. Resume to carry on "
                       "from where it stopped.")
    script = (MotionScript.model_validate_json(mr.motion_path(short_id).read_text(encoding="utf-8"))
              if mr.motion_path(short_id).exists() else None)
    if script is not None:
        job["stage"] = ("done" if mr.plan_path(short_id).exists() and mr._voice_current(script)
                        else "voice" if mr._scenes_done(script) else "scenes")
    elif mr.theme_path(short_id).exists():
        job["stage"] = "script"
    if job["stage"] == "done":
        job["status"] = "done"
        job["message"] = ""
    _log(job, job["stage"], "adopted", short_id)
    save(job)
    return job
