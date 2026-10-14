"""
Render a SLICE of a motion reel to an mp4 — a test clip of a feature before
it is applied to the whole reel. The player is photographed exactly as the
full render does it (shorts/video.py: headless Chrome, window.__capture.seek),
from the reel's plan or a preview variant of it (output/<id>/plan.<variant>.json,
served by /api/motion/<id>/plan?variant=). The narration is the same slice of
audio/reel.wav. Local and free; it calls no model.

    python -m shorts.motion_clip <short_id> --from 6.0 --to 19.6
           [--variant camera] [--out clip.mp4] [--base http://127.0.0.1:8000]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config, video


def render_clip(short_id: str, t0: float, t1: float, out: Path, variant: str | None = None,
                base: str | None = None, fps: int = video.FPS, workers: int = 3) -> Path:
    base = (base or config.VIDEO_BASE_URL).rstrip("/")
    if not video._server_is_up(base):
        raise RuntimeError(f"the app at {base} is not answering — start it with `python -m shorts.server`")
    chrome, ff = video._chrome(), video._ffmpeg()
    first, last = int(round(t0 * fps)), int(round(t1 * fps))
    frames = list(range(first, last))
    route = f"#motion-reel/{short_id}?bare=1" + (f"&variant={variant}" if variant else "")
    with tempfile.TemporaryDirectory(prefix=f"clip-{short_id}-", ignore_cleanup_errors=True) as tmp:
        tmpdir = Path(tmp)
        slices = [frames[w::workers] for w in range(workers)]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(video._capture_slice, chrome, base, short_id, tmpdir, part, fps,
                                lambda: None, video._bg_scale_for(workers), route)
                    for part in slices if part]
            for f in futs:
                f.result()
        audio = config.OUTPUT_DIR / short_id / "audio" / "reel.wav"
        cmd = [ff, "-y", "-framerate", str(fps), "-start_number", str(first), "-i", str(tmpdir / "f%06d.jpg")]
        if audio.exists():
            cmd += ["-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(audio)]
        cmd += ["-vf", f"scale={video.WIDTH}:{video.HEIGHT}", "-r", str(fps),
                "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if audio.exists():
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd += [str(out)]
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {done.stderr[-600:]}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m shorts.motion_clip")
    p.add_argument("short_id")
    p.add_argument("--from", dest="t0", type=float, required=True)
    p.add_argument("--to", dest="t1", type=float, required=True)
    p.add_argument("--variant", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--base", default=None)
    a = p.parse_args(argv)
    out = Path(a.out) if a.out else config.OUTPUT_DIR / a.short_id / f"clip_{a.variant or 'reel'}_{a.t0:g}-{a.t1:g}.mp4"
    print(render_clip(a.short_id, a.t0, a.t1, out, a.variant, a.base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
