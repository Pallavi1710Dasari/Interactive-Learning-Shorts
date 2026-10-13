"""
REDRAW a motion reel's visuals from a note — the reels feed's "redraw" button
on a motion reel (2026-10-13; the explainer reels had it, motion reels did
not). The script and the recorded voice stay exactly as they are: the scenes
are written again (one paid scenes call and its repairs; free in stub mode),
checked by every scene grader, saved, and the plan is rebuilt on the same
voice by the timing stage (local, free).

    POST /api/motion/<id>/redraw {"note": "..."}   starts it
    GET  /api/motion/<id>/redraw                    where it has got to

One redraw per reel at a time; its cost is added to the reel's cost log.
"""
from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timezone

from . import config, usage
from . import motion_reel as mr
from .schema import MotionScript

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}


def estimate() -> float:
    """The most a redraw can cost: the scenes call and every repair."""
    return 0.0 if config.STUB else round(sum(p.cost for p in mr.scenes_plan()), 4)


def status(short_id: str) -> dict:
    with _LOCK:
        job = dict(_JOBS.get(short_id) or {"status": "idle"})
    job.update(short_id=short_id, estimate=estimate(), stub=bool(config.STUB))
    return job


def start(short_id: str, note: str) -> dict:
    if not note.strip():
        raise ValueError("say what the visuals should show instead")
    if not mr.motion_path(short_id).exists() or not mr.plan_path(short_id).exists():
        raise FileNotFoundError(f"no finished motion reel {short_id}")
    with _LOCK:
        if (_JOBS.get(short_id) or {}).get("status") == "working":
            return status(short_id)
        _JOBS[short_id] = {"status": "working", "step": "Drawing new visuals", "error": None}
    threading.Thread(target=_run, args=(short_id, note), daemon=True).start()
    return status(short_id)


def _set(short_id: str, **kw) -> None:
    with _LOCK:
        _JOBS[short_id] = {**_JOBS.get(short_id, {}), **kw}


def _run(short_id: str, note: str) -> None:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = usage.mark()
    try:
        script = MotionScript.model_validate_json(mr.motion_path(short_id).read_text(encoding="utf-8"))
        scripted, results = mr.write_scenes(short_id, script, log=lambda *a: None, note=note)
        failing = [r for r in results if not r.passed]
        if failing:
            raise RuntimeError("the new visuals did not pass their checks: "
                               + "; ".join(r.reason for r in failing)[:400])
        mr.save_scenes(short_id, scripted)
        _set(short_id, step="Timing them to the voice")
        from . import motion_voice
        manifest = json.loads(motion_voice.manifest_path(short_id).read_text(encoding="utf-8"))
        done = mr.stage_timing(short_id, scripted, manifest)
        if done is None:
            raise RuntimeError("the timing step did not finish")
        _set(short_id, status="done", step="Done", error=None)
    except Exception as e:                  # noqa: BLE001 — reported to the feed
        traceback.print_exc()
        _set(short_id, status="error", step="", error=f"{type(e).__name__}: {e}")
    finally:
        calls = usage.calls_since(cursor)
        if calls:
            mr.record_cost(short_id, calls, started)
