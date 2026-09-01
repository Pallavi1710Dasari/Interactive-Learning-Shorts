"""
Render one short to a real MP4, the shape a phone expects: 1080x1920, H.264, AAC.

    python -m shorts.video <short_id>          # -> output/<short_id>/reel.mp4
    python -m shorts.video <short_id> --force  # re-render even if it is cached

WHAT THIS IS NOW, AND WHAT IT REPLACED
It photographs the actual player, one video frame at a time, and the reason is the
complaint that prompted it: "when I download the reels it is not same as am
watching here, I don't see any animation and background and it is looking like
video not the reel."

That was accurate, and it was structural. The old renderer composed its OWN HTML
page per beat — a page whose docstring admitted it "deliberately mirrors
web/src/styles.css rather than importing it" — and screenshotted it once. So the
file was one still per beat, and it was missing the gradient background, the WebGL
depth layer, the story-progress segments, the word-by-word caption reveal and the
build animation, because none of those existed on that page. It was not a lossy
capture of the reel; it was a different design that happened to contain the same
diagram.

So there is no second design any more. web/src/ReelStage.tsx is the picture, the
player and this renderer both draw it, and #capture/<id> is a route that renders it
alone on a page with no controls. This walks that page frame by frame.

HOW IT IS FRAME-EXACT rather than a screen recording. CaptureStage exposes
`window.__capture.seek(t)`, which puts the short in the state it would be in t
seconds in — every Web Animations API animation on the page has its `currentTime`
written and is then paused — and resolves once that state has painted. One
screenshot is therefore exactly one frame at a known time, so 30 of them are
exactly one second, and the wall-clock cost of the capture cannot affect the
result. The build animation is real motion in the file, not a still.

WHAT IT COSTS, measured rather than estimated: roughly six seconds of wall clock
per second of video. A 12.4s short renders in about 72s, a 22.5s short in about
130s. The old renderer took about five, because it took one screenshot per BEAT
rather than thirty per second. It is cached on the same terms it always was, so the
cost is paid once per short — and `python -m shorts.video <id>` pre-renders one
from the terminal if you would rather not wait on the button.

THE HTTP ENDPOINT BLOCKS FOR THAT WHOLE TIME. /api/video renders synchronously, as
it always has; at five seconds that was invisible and at two minutes it is not. It
still completes (FastAPI runs the sync handler in a threadpool, so the server stays
responsive and the browser's fetch has no timeout of its own), and the rail button
spins throughout — but a reverse proxy with a 60s read timeout in front of this
would cut it off. Worth making a background job if that ever becomes the setup.

THREE SYSTEM DEPENDENCIES, none needing sudo:
  * ffmpeg — from the imageio-ffmpeg wheel, a static build.
  * a Chromium — driven over the DevTools protocol, not the --screenshot flag,
    because the page has to be seeked between shots.
  * the built web app — web/dist must exist, and the API server must be reachable,
    because the page this photographs IS the app. `cd web && npm run build`.
"""
import argparse, base64, hashlib, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config, feed
from .schema import ShortUnit

#: Portrait, the aspect every short-form platform wants.
WIDTH, HEIGHT = 1080, 1920

#: 30 is what the user picked over a cheaper 20 when asked. Every frame is a real
#: screenshot, so this is the single biggest lever on render time.
#: Frames per second of the exported MP4, and the most direct lever on how long a
#: render takes — the cost is almost exactly linear in frame count. 30 is smooth;
#: 24 is cinema and takes a fifth less time, which on a 12-second short is about
#: 19 seconds saved. Override with REEL_FPS when turnaround matters more than
#: smoothness. The capture seeks to i/fps, so the animation is correct at any rate.
FPS = max(12, min(60, int(os.getenv("REEL_FPS", "30"))))

#: A frame is a seek plus a screenshot; neither should ever take this long, and a
#: page that has stopped answering must fail rather than hang the download request.
FRAME_TIMEOUT = 30.0

_CHROME_NAMES = ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable")


def _chrome() -> str:
    for name in _CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        "no Chromium found for capturing frames — install one of "
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


def _renderer_fingerprint() -> str:
    """
    What this renderer WOULD produce, as a hash — the cache's missing half.

    The cache keyed on the unit's JSON mtime alone, which answers "has the content
    changed" and not "has the PICTURE changed". Every improvement to the renderer or
    to the player it photographs therefore left a directory of stale videos that
    looked, to the button, perfectly fresh: this session alone produced six MP4s
    that had to be deleted by hand before a download would show the fixes.

    The page being photographed is the built web bundle, so the bundle's own
    filenames are in here — Vite content-hashes them, so any CSS or component change
    is a new name and a new fingerprint. video.py is hashed too, for the encode
    settings and the frame rate.
    """
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes())
    dist = config.ROOT / "web" / "dist"
    for f in sorted(dist.rglob("*")):
        if f.is_file() and f.suffix in (".js", ".css", ".html"):
            h.update(f.name.encode())          # content-hashed by Vite
            h.update(str(f.stat().st_size).encode())
    return h.hexdigest()[:16]


def _stamp_matches(stamp: Path, fingerprint: str, unit: Path) -> bool:
    """Is the cached video current for both this renderer and this unit?"""
    if not stamp.exists():
        return False
    parts = stamp.read_text().split()
    if len(parts) != 2 or parts[0] != fingerprint:
        return False
    try:
        return int(parts[1]) == unit.stat().st_mtime_ns
    except (ValueError, OSError):
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Devtools:
    """
    The smallest DevTools client that can drive a page: connect, evaluate, shoot.

    Written against the raw protocol rather than pulled in as a dependency because
    three commands is not worth a Playwright install, and because the render path
    has to work on a box that only ever ran `pip install -r requirements.txt`.
    """

    def __init__(self, ws_url: str):
        from websockets.sync.client import connect
        self._ws = connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=20)
        self._id = 0

    def send(self, method: str, params: dict | None = None, timeout: float = FRAME_TIMEOUT):
        self._id += 1
        want = self._id
        self._ws.send(json.dumps({"id": want, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"devtools timed out on {method}")
            msg = json.loads(self._ws.recv(timeout=left))
            if msg.get("id") != want:
                continue                      # an event, or a reply we are past
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})

    def evaluate(self, expression: str, timeout: float = FRAME_TIMEOUT):
        r = self.send("Runtime.evaluate",
                      {"expression": expression, "awaitPromise": True,
                       "returnByValue": True}, timeout=timeout)
        if "exceptionDetails" in r:
            raise RuntimeError(f"page error: {json.dumps(r['exceptionDetails'])[:400]}")
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self._ws.close()
        except Exception:
            pass


def _launch(chrome: str, port: int, profile: Path) -> subprocess.Popen:
    """
    Headless Chrome, sized to the video, with WebGL actually working.

    --use-gl=angle + --use-angle=swiftshader is what keeps ThreeStage's depth layer
    in the file. Plain --disable-gpu gives a context that silently fails to render,
    and the background then captures as flat colour — one of the two things the
    download was reported as missing.
    """
    return subprocess.Popen(
        [chrome, "--headless=new", "--no-sandbox", "--hide-scrollbars",
         "--mute-audio", "--no-first-run", "--disable-extensions",
         "--use-gl=angle", "--use-angle=swiftshader",
         "--enable-unsafe-swiftshader",
         "--force-device-scale-factor=1",
         "--autoplay-policy=no-user-gesture-required",
         f"--window-size={WIDTH},{HEIGHT}",
         f"--user-data-dir={profile}",
         f"--remote-debugging-port={port}",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _page_ws(port: int, timeout: float = 30.0) -> str:
    """Wait for Chrome to come up and hand back its first page target."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:
                targets = json.load(r)
            for t in targets:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    return t["webSocketDebuggerUrl"]
        except Exception as e:      # not up yet
            last = e
        time.sleep(0.25)
    raise RuntimeError(f"Chrome did not expose a debugging page on {port}: {last}")


def _server_is_up(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


#: How many browsers capture at once. The screenshot is the whole cost — profiled
#: at 1080x1920 it is 474ms against 49ms for the seek, because SwiftShader
#: rasterises the WebGL layer in software on every frame — and it is almost
#: entirely per-process. So N browsers each taking every Nth second of the short
#: finish in about 1/N the time, and the frames are independent by construction:
#: seek(t) is absolute, so no worker needs to know what any other has done.
#:
#: Three, not more, is about memory rather than CPU: each instance holds a
#: 1080x1920 software GL surface, and the machine this was tuned on has 28 cores
#: but shares its RAM with the model calls the rest of the pipeline is making.
DEFAULT_WORKERS = 3


def _capture_slice(chrome: str, base: str, short_id: str, outdir: Path,
                   indices: list[int], fps: int, on_frame) -> None:
    """Photograph one worker's share of the frames. Owns its own browser."""
    port = _free_port()
    profile = outdir / f"profile-{port}"
    proc = _launch(chrome, port, profile)
    dev = None
    try:
        dev = _Devtools(_page_ws(port))
        dev.send("Page.enable")
        dev.send("Runtime.enable")
        # THE VIEWPORT, NOT THE WINDOW. --window-size sizes the OS window, chrome
        # included, so a 1080x1920 window gave a 1080x1781 page: every screenshot
        # came out 139px short and ffmpeg's scale+pad quietly letterboxed it back.
        # A chunk of every frame was not the reel at all.
        dev.send("Emulation.setDeviceMetricsOverride",
                 {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1,
                  "mobile": False})
        url = f"{base}/#capture/{short_id}"
        dev.send("Page.navigate", {"url": url})

        deadline = time.monotonic() + 45
        while True:
            state = dev.evaluate(
                "({ready: !!window.__capture, err: window.__captureError || null})")
            if state and state.get("ready"):
                break
            if state and state.get("err"):
                raise RuntimeError(f"capture page: {state['err']}")
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"the capture page never became ready at {url} — is "
                    f"{short_id} in /api/shorts? Quarantined shorts are not.")
            time.sleep(0.2)

        # Fonts before the first frame, or it captures fallback metrics and the
        # caption visibly reflows one frame in.
        dev.evaluate("document.fonts.ready.then(() => true)")

        for i in indices:
            t = i / fps
            dev.evaluate(f"window.__capture.seek({t:.5f}).then(() => true)")
            # JPEG, NOT PNG. Measured on css_color_property: 373 frames in 91s
            # with PNG, 72s with JPEG. A lossless frame costs a quarter of a second
            # to encode inside Chrome and is then thrown away — x264 re-encodes it
            # at crf 20 seconds later. optimizeForSpeed trades a little file size
            # on an intermediate nobody keeps for encoder time.
            shot = dev.send("Page.captureScreenshot",
                            {"format": "jpeg", "quality": 95,
                             "optimizeForSpeed": True,
                             "captureBeyondViewport": False})
            (outdir / f"f{i:06d}.jpg").write_bytes(base64.b64decode(shot["data"]))
            on_frame()
    finally:
        if dev:
            dev.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def render(short_id: str, force: bool = False,
           base_url: str | None = None, fps: int = FPS,
           progress=None, workers: int | None = None) -> Path:
    """
    Build output/<short_id>/reel.mp4 and return its path.

    Cached: rebuilt only when missing, when --force is passed, or when the unit
    JSON is newer than the video.
    """
    path = config.OUTPUT_DIR / f"{short_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no such short: {short_id}")
    unit = ShortUnit(**json.loads(path.read_text()))

    outdir = config.OUTPUT_DIR / short_id
    outdir.mkdir(parents=True, exist_ok=True)
    mp4 = outdir / "reel.mp4"
    stamp = outdir / "reel.stamp"
    fingerprint = _renderer_fingerprint()
    if mp4.exists() and not force and _stamp_matches(stamp, fingerprint, path):
        return mp4

    # The SAME timeline the player animates to, so the video and the reel cannot
    # disagree about when a beat starts.
    beats, total = feed._timeline(unit)
    if not beats:
        raise RuntimeError(f"{short_id} has no beats to render")
    if total <= 0:
        raise RuntimeError(f"{short_id} has a zero-length timeline")

    base = (base_url or config.VIDEO_BASE_URL).rstrip("/")
    if not _server_is_up(base):
        raise RuntimeError(
            f"the app at {base} is not answering — the renderer photographs the "
            f"real player, so the server has to be running. Start it with "
            f"`python -m shorts.server`, or set VIDEO_BASE_URL.")

    dist = config.ROOT / "web" / "dist" / "index.html"
    if not dist.exists():
        raise RuntimeError("web/dist is not built — run `cd web && npm run build`. "
                           "The renderer photographs the built app.")

    chrome, ff = _chrome(), _ffmpeg()
    audio = outdir / "audio.mp3"
    frames = max(1, int(round(total * fps)))
    workers = max(1, min(workers or DEFAULT_WORKERS, frames))

    with tempfile.TemporaryDirectory(prefix=f"reel-{short_id}-") as tmp:
        tmpdir = Path(tmp)

        # Round-robin, not contiguous blocks. Every worker then covers the whole
        # short, so they all do the same mix of cheap frames (a held picture) and
        # expensive ones (a beat mid-build) and finish together — contiguous blocks
        # left whoever drew the busiest beat still working alone at the end.
        slices = [list(range(w, frames, workers)) for w in range(workers)]
        done = 0
        lock = threading.Lock()

        def tick() -> None:
            nonlocal done
            with lock:
                done += 1
                if progress and (done % fps == 0 or done == frames):
                    progress(done, frames)

        errors: list[BaseException] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_capture_slice, chrome, base, short_id,
                                   tmpdir, part, fps, tick)
                       for part in slices if part]
            for f in futures:
                try:
                    f.result()
                except BaseException as e:      # noqa: BLE001 - reported below
                    errors.append(e)
        if errors:
            raise RuntimeError(f"frame capture failed for {short_id}: {errors[0]}")

        missing = [i for i in range(frames) if not (tmpdir / f"f{i:06d}.jpg").exists()]
        if missing:
            # ffmpeg's image sequence reader stops at the first gap, so a partial
            # capture would silently produce a truncated video rather than fail.
            raise RuntimeError(
                f"{len(missing)} of {frames} frames missing (first: {missing[0]}) "
                f"— the render would have been silently short")

        # A numbered image sequence at a fixed rate — no concat demuxer and no
        # per-frame durations, because every frame is the same length by
        # construction now.
        cmd = [ff, "-y", "-framerate", str(fps),
               "-i", str(tmpdir / "f%06d.jpg")]
        if audio.exists():
            cmd += ["-i", str(audio)]
        cmd += [
            "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x0B0F0E",
            "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            # yuv420p or Safari and most phones will not play it at all.
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ]
        if audio.exists():
            cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
        cmd += [str(mp4)]

        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0 or not mp4.exists():
            raise RuntimeError(f"ffmpeg failed for {short_id}: {done.stderr[-600:]}")

    # THE UNIT IS WRITTEN BEFORE THE STAMP, and that order is the whole fix.
    #
    # The cache compared the video's mtime against the unit JSON's, and render()
    # writes video_path back into the unit AFTER producing the video — so the unit
    # was always a few milliseconds newer than the file it had just produced, and
    # the cache never hit. Every render was followed by an identical re-render on
    # the next request. It went unnoticed because the old renderer took five seconds
    # and everything here was called with --force.
    #
    # The stamp now records the unit mtime it was built FROM, written last, so the
    # comparison is against a number rather than a race.
    unit.video_path = str(mp4.relative_to(config.ROOT))
    path.write_text(unit.model_dump_json(indent=2))
    stamp.write_text(f"{fingerprint} {path.stat().st_mtime_ns}")
    return mp4


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("short_id")
    ap.add_argument("--force", action="store_true", help="re-render even if cached")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--workers", type=int, default=None,
                    help=f"browsers capturing in parallel (default {DEFAULT_WORKERS})")
    ap.add_argument("--base-url", default=None,
                    help=f"where the app is served (default {config.VIDEO_BASE_URL})")
    args = ap.parse_args()

    def show(done: int, total: int) -> None:
        pct = 100 * done / total
        print(f"\r  capturing {done}/{total} frames ({pct:.0f}%)", end="", flush=True)

    started = time.monotonic()
    try:
        mp4 = render(args.short_id, force=args.force,
                     base_url=args.base_url, fps=args.fps, progress=show,
                     workers=args.workers)
    except Exception as e:
        print(f"\n! {type(e).__name__}: {e}")
        return 1
    size = mp4.stat().st_size / 1e6
    print(f"\nwrote {mp4}  ({size:.1f} MB, {time.monotonic() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
