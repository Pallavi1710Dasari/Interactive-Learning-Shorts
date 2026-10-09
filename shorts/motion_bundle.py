"""
Everything about one motion reel in one JSON (RESTYLE_TO_MOTION_REELS.md,
phase 3 review): what the web UI's Motion section shows. The server builds it
for reels in output/ (/api/motion, /api/motion/<id>/bundle); shorts/
motion_demo.py builds the same shape for the stub demos in
web/public/motion-demo/, so the UI has one shape to read either way.

Read-only: it only reads files a run already wrote.
"""
import json
from pathlib import Path


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_motion_reel(out_dir: Path, short_id: str) -> bool:
    return (out_dir / short_id / "setup.json").exists() and short_id.find("__motion") >= 0


def list_reels(out_dir: Path) -> list[str]:
    """Every motion reel in `out_dir`, newest first."""
    ids = [p.parent.name for p in out_dir.glob("*/setup.json") if "__motion" in p.parent.name]
    return sorted(ids, key=lambda i: (out_dir / i / "setup.json").stat().st_mtime, reverse=True)


def _stub(out_dir: Path, short_id: str, cost: dict | None) -> bool:
    """A stub reel: every run that wrote it was a stub run, or (for a reel
    from before cost logs) its narration is stub silence."""
    if cost and cost.get("runs"):
        return all(r.get("stub") for r in cost["runs"])
    manifest = _read(out_dir / short_id / "audio" / "manifest.json")
    return bool(manifest and manifest.get("engine") == "stub")


def summary(out_dir: Path, short_id: str) -> dict:
    """The list row: id, topic, stub or real, theme, teaching approach, tags,
    length, cost and how far the reel got."""
    d = out_dir / short_id
    setup = _read(d / "setup.json") or {}
    theme = _read(d / "theme.json") or {}
    tags = _read(d / "tags.json") or {}
    cost = _read(d / "cost.json")
    plan = _read(d / "plan.json")
    script = _read(out_dir / f"{short_id}.motion.json")
    wf = setup.get("workflow") or {}
    approach = (wf.get("teaching_approach") or {}) if isinstance(wf, dict) else {}
    stage = ("timing" if plan else "voice" if (d / "audio" / "manifest.json").exists()
             else "scenes" if script and all(s.get("scene") for s in script.get("shots", []))
             else "script" if script else "theme" if theme else "setup")
    return {
        "short_id": short_id,
        "topic": (setup.get("topic") or {}).get("topic", ""),
        "stub": _stub(out_dir, short_id, cost),
        "theme": theme.get("theme"),
        "template": (script or {}).get("template") or setup.get("template"),
        "teaching_approach": approach.get("primary"),
        "tags": tags.get("tags") or theme.get("tags") or [],
        "language": tags.get("language") or theme.get("language"),
        "duration": (plan or {}).get("duration"),
        "cost": ((cost or {}).get("total") or {}).get("cost", 0.0),
        "cost_estimated": ((cost or {}).get("total") or {}).get("estimated", False),
        "stage": stage,
        "has_plan": plan is not None,
    }


def bundle(out_dir: Path, short_id: str, plan_url: str | None = None,
           audio_url: str | None = None) -> dict:
    """Everything the Motion detail page shows for one reel."""
    d = out_dir / short_id
    setup = _read(d / "setup.json") or {}
    wf = setup.get("workflow") or {}
    return {
        **summary(out_dir, short_id),
        "approach": wf.get("teaching_approach"),
        "theme_choice": _read(d / "theme.json"),
        "script": _read(out_dir / f"{short_id}.motion.json"),
        "facts": _read(d / "fact_sources.json") or [],
        "cost_log": _read(d / "cost.json"),
        "plan_url": plan_url,
        "audio_url": audio_url,
    }
