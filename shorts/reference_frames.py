"""
Cut the reference reel into the frames the #motion-gallery shows beside each
transition and animation (REFERENCE_STYLE_ADDENDUM.md 4.6 E).

    python -m shorts.reference_frames            # every item in the manifest
    python -m shorts.reference_frames iris stamp # just these

Reads web/public/reference/manifest.json — the one place the reference
timestamps live — and writes web/public/reference/<id>/000.jpg, 001.jpg, ...
plus <id>/frames.json (the count and the time of each frame). The MP4 is
git-ignored (23 MB); the frames are small and committed, so the gallery works
on a checkout that never had the video.

Free: no API calls, just the static ffmpeg from the imageio-ffmpeg wheel.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .video import _ffmpeg

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "web" / "public" / "reference"
MANIFEST = REF_DIR / "manifest.json"


def cut(item: dict, source: Path, width: int) -> int:
    out = REF_DIR / item["id"]
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    dur = item["end"] - item["start"]
    subprocess.run(
        [_ffmpeg(), "-v", "error", "-y", "-ss", f"{item['start']:.3f}", "-t", f"{dur:.3f}",
         "-i", str(source), "-vf", f"fps={item['fps']},scale={width}:-2", "-q:v", "5",
         "-start_number", "0", str(out / "%03d.jpg")],
        check=True)
    frames = sorted(out.glob("*.jpg"))
    times = [round(item["start"] + i / item["fps"], 3) for i in range(len(frames))]
    (out / "frames.json").write_text(json.dumps({"id": item["id"], "count": len(frames), "times": times}),
                                     encoding="utf-8")
    return len(frames)


def main(argv: list[str]) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = ROOT / manifest["source"]
    if not source.exists():
        print(f"{source} is missing — it is git-ignored; copy the reference reel there first.")
        return 1
    wanted = set(argv)
    total = 0
    for item in manifest["items"]:
        if wanted and item["id"] not in wanted:
            continue
        n = cut(item, source, manifest.get("width", 270))
        total += n
        print(f"  {item['id']:<20} {item['start']:>7.2f}-{item['end']:<7.2f} {n:>3} frames")
    print(f"{total} frames under {REF_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
