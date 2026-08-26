"""
Render one short to a real MP4, the shape a phone expects: 1080x1920, H.264, AAC.

    python -m shorts.video <short_id>          # -> output/<short_id>/reel.mp4
    python -m shorts.video <short_id> --force  # re-render even if it is cached

WHY THIS IS A PYTHON RENDERER AND NOT REMOTION
The README's Part F plans Remotion, and `ShortUnit.video_path` has been in the
schema from the start waiting for it. Neither was ever built: there is no
render.py, no render/ project, and nothing writes video_path. Standing a Remotion
project up means a second React app, its own dependency tree and a headless Chrome
render farm, to produce something this project already has all the pieces for.

A short is a handful of still frames with known durations plus one audio track.
That is a slideshow, and ffmpeg makes slideshows. The visuals are already SVG with
a fixed 1080x1080 viewBox, the per-beat timings already come out of feed._timeline
(the same numbers the player animates to, so the video cannot drift from the reel),
and voice.synthesize has already written audio.mp3. So the whole renderer is:
compose one HTML page per beat, screenshot it, concatenate with ffmpeg.

WHAT IS LOST, stated plainly: the build animation. In the browser each frame's
elements fade in one by one; here each beat is one still. The composition, the
hero highlight and the captions are all identical — only the motion inside a beat
is gone. Worth it to have a file you can actually post.

TWO SYSTEM DEPENDENCIES, both already present and neither needing sudo:
  * ffmpeg — from the imageio-ffmpeg wheel, a static build, so `apt install
    ffmpeg` is not required. README 0.3 asks for the system one; this does not
    need it.
  * a Chromium — used to rasterise the SVG inside a page that mirrors the player's
    layout. Rasterising the SVG alone would lose the question header and the
    caption, which are half of what a viewer reads.
"""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

from . import config, feed
from .schema import ShortUnit

#: Portrait, the aspect every short-form platform wants. The diagram is a 1080
#: square, so it sits in the middle with the question above and the caption below —
#: the same vertical order the player uses.
WIDTH, HEIGHT = 1080, 1920

#: A still frame needs no frame rate to speak of, but H.264 in a .mp4 that phones
#: and browsers will both scrub wants a sane one.
FPS = 30

_CHROME_NAMES = ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable")


def _chrome() -> str:
    for name in _CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        "no Chromium found for rasterising frames — install one of "
        + ", ".join(_CHROME_NAMES))


def _ffmpeg() -> str:
    """The static ffmpeg from the wheel, falling back to a system one."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise RuntimeError("no ffmpeg — `pip install imageio-ffmpeg` provides a static one")


def _page(unit_question: str, beat: dict) -> str:
    """
    One beat as a full-bleed portrait page, laid out like the player.

    Deliberately mirrors web/src/styles.css rather than importing it: the player's
    stylesheet is built for a scrolling feed with controls, and what is wanted here
    is the three things a viewer actually reads — the question, the diagram, the
    line being spoken.
    """
    speaker = "interviewer" if beat["speaker"] == "interviewer" else "student"
    accent = "#F2B14B" if speaker == "interviewer" else "#2A78C2"
    # The interviewer's line IS the question, so printing both put the same sentence
    # at the top and the bottom of the opening frame — the first thing a viewer sees
    # was one sentence twice. The header carries it; the caption stands down.
    caption = "" if _norm(beat["line"]) == _norm(unit_question) else beat["line"]
    return f"""<!doctype html><meta charset="utf-8">
<style>
  @import url("https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap");
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{WIDTH}px; height:{HEIGHT}px; overflow:hidden;
               background:#0B0F0E; color:#F4F5F3;
               font-family:"Source Sans 3", system-ui, sans-serif; }}
  .wrap {{ height:100%; display:flex; flex-direction:column;
           padding:62px 40px 74px; gap:0; }}
  .q {{ font-size:44px; font-weight:700; line-height:1.22; letter-spacing:-.5px;
        color:#F4F5F3; }}
  .tag {{ margin-top:18px; font-size:26px; font-weight:600; color:{accent};
          text-transform:uppercase; letter-spacing:2px; }}
  .stage {{ flex:1; display:flex; align-items:center; justify-content:center;
            margin:30px 0; min-height:0; }}
  /* The diagram is a 1080 square; let it use the full width it was drawn for. */
  .stage svg {{ width:100%; height:auto; background:#F4F5F3;
                border-radius:34px; }}
  .cap {{ font-size:40px; line-height:1.34; font-weight:600; color:#E8EAE6;
          border-left:8px solid {accent}; padding-left:28px; }}
</style>
<div class="wrap">
  <div class="q">{_esc(unit_question)}</div>
  <div class="tag">{speaker}</div>
  <div class="stage">{beat["svg"] or ""}</div>
  {f'<div class="cap">{_esc(caption)}</div>' if caption else ''}
</div>"""


def _norm(text: str) -> str:
    """Loose equality, for deciding whether the caption repeats the header."""
    return "".join(c for c in str(text).lower() if c.isalnum())


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _shoot(chrome: str, html: Path, png: Path) -> None:
    """Rasterise one page. --virtual-time-budget lets the webfont land first."""
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         f"--window-size={WIDTH},{HEIGHT}", "--virtual-time-budget=4000",
         f"--screenshot={png}", f"file://{html}"],
        check=True, capture_output=True, timeout=120)
    if not png.exists():
        raise RuntimeError(f"chrome produced no frame for {html.name}")


def render(short_id: str, force: bool = False) -> Path:
    """
    Build output/<short_id>/reel.mp4 and return its path.

    Cached: the file is only rebuilt when it is missing, when --force is passed, or
    when the unit JSON is newer than the video. A render is seconds of CPU and no
    API calls, but the download button hits this on every click.
    """
    path = config.OUTPUT_DIR / f"{short_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no such short: {short_id}")
    unit = ShortUnit(**json.loads(path.read_text()))

    outdir = config.OUTPUT_DIR / short_id
    outdir.mkdir(parents=True, exist_ok=True)
    mp4 = outdir / "reel.mp4"
    if mp4.exists() and not force and mp4.stat().st_mtime >= path.stat().st_mtime:
        return mp4

    # The SAME timeline the player animates to, so the video and the reel cannot
    # disagree about when a beat starts.
    beats, total = feed._timeline(unit)
    if not beats:
        raise RuntimeError(f"{short_id} has no beats to render")

    chrome, ff = _chrome(), _ffmpeg()
    audio = outdir / "audio.mp3"

    with tempfile.TemporaryDirectory(prefix=f"reel-{short_id}-") as tmp:
        tmpdir = Path(tmp)
        concat = []
        for i, beat in enumerate(beats):
            html = tmpdir / f"b{i:03d}.html"
            png = tmpdir / f"b{i:03d}.png"
            html.write_text(_page(unit.question, beat), encoding="utf-8")
            _shoot(chrome, html, png)
            seconds = max(0.4, float(beat["end"]) - float(beat["start"]))
            # The concat demuxer needs the last entry repeated without a duration,
            # or it drops the final image.
            concat.append(f"file '{png}'\nduration {seconds:.3f}")
        concat.append(f"file '{tmpdir / f'b{len(beats)-1:03d}.png'}'")
        listing = tmpdir / "frames.txt"
        listing.write_text("\n".join(concat) + "\n", encoding="utf-8")

        cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
        if audio.exists():
            cmd += ["-i", str(audio)]
        cmd += [
            "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x0B0F0E,fps={FPS}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            # yuv420p or Safari and most phones will not play it at all.
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ]
        if audio.exists():
            # -shortest so a track longer than the frames does not leave a black tail.
            cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
        cmd += [str(mp4)]

        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0 or not mp4.exists():
            raise RuntimeError(f"ffmpeg failed for {short_id}: {done.stderr[-600:]}")

    # Record it on the unit, which is what video_path was added for.
    unit.video_path = str(mp4.relative_to(config.ROOT))
    path.write_text(unit.model_dump_json(indent=2))
    return mp4


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("short_id")
    ap.add_argument("--force", action="store_true", help="re-render even if cached")
    args = ap.parse_args()
    try:
        mp4 = render(args.short_id, force=args.force)
    except Exception as e:
        print(f"! {type(e).__name__}: {e}")
        return 1
    size = mp4.stat().st_size / 1e6
    print(f"wrote {mp4}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
