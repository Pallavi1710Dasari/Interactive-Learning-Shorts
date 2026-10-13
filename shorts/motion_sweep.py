"""
Sweep a motion reel in the real player (headless Chrome, the renderer's own
DevTools client) and run the browser's layout audit — window.__motionOverlaps,
web/src/motion/overlap.ts — at many moments: every shot after it settles, its
middle, its end, and the middle of every caption. Optionally saves a PNG of
chosen moments. Local and free; it calls no model.

    python -m shorts.motion_sweep <short_id> [--base http://127.0.0.1:8000]
           [--shots out_dir] [--json report.json]

The app must be running at --base (it serves the built bundle in web/dist).
"""
import argparse
import base64
import json
import sys
import tempfile
import time
from pathlib import Path

from . import config
from . import video


def moments(plan: dict) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for s in plan["shots"]:
        a, b = s["start"], s["end"]
        out += [(min(b - 0.05, a + 1.0), f"{s['id']} settled"), ((a + b) / 2, f"{s['id']} middle"),
                (max(a, b - 0.08), f"{s['id']} end")]
        for i, c in enumerate(s["captions"]):
            out.append(((c["start"] + c["end"]) / 2, f"{s['id']} caption {i + 1}"))
    return sorted(out)


def sweep(short_id: str, base: str, shots_dir: Path | None = None, picks: list[float] | None = None) -> dict:
    import urllib.request
    with urllib.request.urlopen(f"{base}/api/motion/{short_id}/plan", timeout=10) as r:
        plan = json.load(r)
    chrome = video._chrome()
    port = video._free_port()
    with tempfile.TemporaryDirectory(prefix="sweep-", ignore_cleanup_errors=True) as tmp:
        proc = video._launch(chrome, port, Path(tmp) / "profile")
        dev = None
        try:
            dev = video._Devtools(video._page_ws(port))
            dev.send("Page.enable")
            dev.send("Runtime.enable")
            dev.send("Emulation.setDeviceMetricsOverride",
                     {"width": video.WIDTH, "height": video.HEIGHT, "deviceScaleFactor": 1, "mobile": False})
            dev.send("Page.navigate", {"url": f"{base}/#motion-reel/{short_id}?bare=1"})
            deadline = time.monotonic() + 45
            while not dev.evaluate("!!window.__capture && !!window.__motionOverlaps"):
                if time.monotonic() > deadline:
                    raise RuntimeError("the player never became ready")
                time.sleep(0.2)
            dev.evaluate("document.fonts.ready.then(() => true)")
            found: list[dict] = []
            ms = moments(plan)
            for t, what in ms:
                dev.evaluate(f"window.__capture.seek({t:.4f}).then(() => true)")
                for o in dev.evaluate("window.__motionOverlaps()") or []:
                    found.append({"t": round(t, 2), "moment": what, **o})
            saved = []
            if shots_dir is not None:
                shots_dir.mkdir(parents=True, exist_ok=True)
                for t in picks or []:
                    dev.evaluate(f"window.__capture.seek({t:.4f}).then(() => true)")
                    png = dev.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                    path = shots_dir / f"t{t:06.2f}.png"
                    path.write_bytes(base64.b64decode(png["data"]))
                    saved.append(str(path))
            return {"short_id": short_id, "rev": plan.get("rev", 1), "moments": len(ms),
                    "overlaps": found, "screenshots": saved}
        finally:
            if dev:
                dev.close()
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m shorts.motion_sweep")
    p.add_argument("short_id")
    p.add_argument("--base", default=config.VIDEO_BASE_URL)
    p.add_argument("--shots", default=None, help="folder for screenshots of --at moments")
    p.add_argument("--at", default="", help="comma-separated seconds to screenshot")
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    picks = [float(x) for x in a.at.split(",") if x.strip()]
    rep = sweep(a.short_id, a.base.rstrip("/"), Path(a.shots) if a.shots else None, picks)
    print(f"{a.short_id} (rev {rep['rev']}): {rep['moments']} moments, {len(rep['overlaps'])} problem(s)")
    for o in rep["overlaps"]:
        print(f"  {o['t']:6.2f}s {o['moment']:<20} {o['kind']:<18} {o['a']} / {o['b']}  {o['textA'][:40]!r}")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return 0 if not rep["overlaps"] else 1


if __name__ == "__main__":
    sys.exit(main())
