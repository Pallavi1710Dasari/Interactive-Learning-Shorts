"""
Turn a rendered frame into a PNG, so something can LOOK at it.

WHY THIS EXISTS
Every quality gate in this pipeline reads structure. checks.py walks a Frame's
fields, and skills/audit.py's judge is handed the same Frame as JSON. Both are
good at the questions structure can answer — is this label from the narration, is
this code line really in the document, do these two frames differ — and neither
can answer the question the visuals were actually failing:

    would a learner understand the concept from this picture?

That is not a property of the JSON. A frame can pass every structural grader and
still be four boxes of nouns that communicate nothing, which is exactly the
scoring the reviewer put on it: visual correctness 9/10, educational clarity 4/10.
The structure was fine. The picture was not, and nothing in the pipeline had ever
seen one.

So: rasterise, and send the pixels to a model that can look. See skills/vision.py.

WHAT IT DRAWS ON, AND WHY IT MATTERS
Not the bare SVG. layout.py draws near-black ink and pale blue tints with NO
background rect of its own, because in the player the drawing sits on a light card
(`.reel .stageinner`, a #FCFBF7 -> #EFF4F1 gradient). Rasterised on the default
transparent-becomes-black, every frame would come back as dark ink on dark and the
judge would score legibility that no viewer experiences. The card is reproduced
here so the judge grades the real thing.

Fonts are pulled from the same Google Fonts link web/index.html uses, because a
"preview" frame's entire content is a typeface — judged in a fallback sans, a
frame demonstrating Lobster against Roboto shows two identical words and reads as
a broken diagram when it is only an unloaded font. Offline, the wait times out and
rendering continues; the judge is told the fonts may be substituted.

NO BROWSER, NO JUDGE — never a failed build. Chromium is a hard dependency of
video.py and an optional one here, so every entry point degrades to "vision judge
skipped" rather than taking the short down with it.
"""
import json, re, time
from pathlib import Path

# The CDP plumbing already exists for the video renderer and is exactly what this
# needs — launch, find the page target, evaluate, screenshot. Importing it beats a
# second copy, and beats adding Playwright for three commands.
from .video import _chrome, _launch, _free_port, _page_ws, _Devtools
from . import config

#: The square the judge is shown, in pixels.
#:
#: The canvas is a 1080 square (layout.VIEW) and the frames are legible far below
#: that. 720 is the smallest size at which a `code` frame's smallest line is still
#: comfortably readable, measured by rendering one and reading it — below about 600
#: the quiet lines start to matter, and a judge squinting at a real defect it cannot
#: resolve reports a text problem that is really a resolution problem.
#:
#: It is also the input bill. Images are charged by area, so 720 rather than 1080
#: is a little over half the tokens for the same verdict on every frame of every
#: short.
PNG_WIDTH = 720

#: The card the drawing sits on in the player — `.reel .stageinner` in
#: web/src/styles.css. Kept in sync BY HAND, which is a real cost, but the
#: alternative is booting the whole Vite app to photograph one static frame.
#: Per theme, and it MUST track `.reel .stageinner`: the judge grades what it
#: photographs, so a stale value here means it is grading a surface no viewer sees.
CARD_BACKGROUNDS = {
    "paper": "linear-gradient(168deg, #FCFBF7 0%, #EFF4F1 100%)",
    "neon":  "radial-gradient(120% 90% at 50% 8%, #0C1226 0%, #05070E 62%, #03050A 100%)",
}
CARD_BACKGROUND = CARD_BACKGROUNDS.get(config.REEL_THEME, CARD_BACKGROUNDS["paper"])

#: The exact families web/index.html loads. Same URL, so a frame that renders in
#: the player renders here.
FONTS_HREF = (
    "https://fonts.googleapis.com/css2?family=Bree+Serif&family=Caveat:wght@400;700"
    "&family=Lobster&family=Monoton&family=Open+Sans:ital,wght@0,400;0,700;1,400"
    "&family=Playfair+Display:ital,wght@0,400;0,700"
    "&family=Roboto:ital,wght@0,100;0,400;0,700;0,900;1,400"
    "&family=Source+Sans+3:ital,wght@0,400;0,700"
    "&family=Work+Sans:ital,wght@0,400;0,700&display=swap"
)

#: How long to wait for the webfonts before giving up and shooting anyway.
FONT_TIMEOUT = 6.0

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="__FONTS__">
<style>
  html, body { margin: 0; padding: 0; background: #05080a; }
  /* The light card, matching .reel .stageinner. */
  #card {
    width: __W__px; height: __W__px; background: __CARD__;
    display: grid; place-items: center; padding: 12px; box-sizing: border-box;
    font-family: Inter, Helvetica, sans-serif;
  }
  #card svg { width: 100%; height: 100%; }
</style></head>
<body><div id="card"></div></body></html>"""


#: The padding cropFor() leaves around the ink, in canvas units. Must match
#: web/src/AnimatedSvg.tsx — a different pad here means the judge grades the
#: diagram at a different scale from the one the viewer watches.
CROP_PAD = 24

_VIEWBOX_RE = re.compile(r'\sviewBox="[^"]*"')


def _with_viewbox(svg: str, x: float, y: float, w: float, h: float) -> str:
    """Re-crop an SVG string to a box, letterboxing the way the player does."""
    box = f' viewBox="{x:.2f} {y:.2f} {w:.2f} {h:.2f}"'
    svg = _VIEWBOX_RE.sub(box, svg, count=1)
    if 'preserveAspectRatio' not in svg:
        svg = svg.replace("<svg", '<svg preserveAspectRatio="xMidYMid meet"', 1)
    return svg


class RasterUnavailable(RuntimeError):
    """No Chromium, or it would not start. Callers skip the vision judge."""


def available() -> bool:
    """Is there a browser to rasterise with? Cheap; safe to call on every run."""
    try:
        _chrome()
        return True
    except RuntimeError:
        return False


class Rasteriser:
    """
    One browser, many frames.

    Deliberately a context manager over a batch rather than a render_one()
    function. Chrome costs about a second to start and nothing per frame after
    that, so a short's four frames through one instance is a second of overhead
    instead of four — and the vision judge always has a whole short's worth.
    """

    def __init__(self, workdir: Path | None = None, width: int = PNG_WIDTH):
        self.width = width
        self._workdir = workdir
        self._proc = None
        self._dev = None
        self._tmp = None

    def __enter__(self) -> "Rasteriser":
        try:
            chrome = _chrome()
        except RuntimeError as e:
            raise RasterUnavailable(str(e)) from e

        if self._workdir is None:
            import tempfile
            self._tmp = tempfile.TemporaryDirectory(prefix="raster-")
            self._workdir = Path(self._tmp.name)

        port = _free_port()
        self._proc = _launch(chrome, port, self._workdir / f"profile-{port}")
        try:
            self._dev = _Devtools(_page_ws(port))
            self._dev.send("Page.enable")
            self._dev.send("Runtime.enable")
            # The window _launch asks for is video-shaped (1080x1920). Override it
            # to the square being shot so the screenshot needs no clip and no
            # scroll — the card IS the viewport.
            self._dev.send("Emulation.setDeviceMetricsOverride",
                           {"width": self.width, "height": self.width,
                            "deviceScaleFactor": 1, "mobile": False})
            self._dev.send("Page.navigate", {"url": "about:blank"})
            self._install_page()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        for closer in (lambda: self._dev and self._dev.close(),
                       lambda: self._proc and self._proc.terminate(),
                       lambda: self._tmp and self._tmp.cleanup()):
            try:
                closer()
            except Exception:
                pass
        self._dev = self._proc = self._tmp = None
        return False

    def _install_page(self) -> None:
        """Write the card shell once, then swap only the SVG per frame.

        Page.setDocumentContent per frame would re-fetch and re-parse the webfont
        stylesheet every time. Installing the shell once means the faces are
        loaded before the first shot and cached for the rest.
        """
        html = (_PAGE.replace("__FONTS__", FONTS_HREF)
                     .replace("__CARD__", CARD_BACKGROUND)
                     .replace("__W__", str(self.width)))
        frame_id = self._dev.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
        self._dev.send("Page.setDocumentContent", {"frameId": frame_id, "html": html})

        # Fonts, best effort. An offline box gets the fallback stack and a judge
        # that was told so, which is better than a build that fails on a diagram.
        deadline = time.monotonic() + FONT_TIMEOUT
        while time.monotonic() < deadline:
            try:
                if self._dev.evaluate("document.fonts.ready.then(() => true)"):
                    return
            except Exception:
                pass
            time.sleep(0.2)

    def _put(self, svg: str) -> None:
        """Drop one SVG into the card and let it lay out."""
        # json.dumps, not an f-string: an SVG is full of quotes and the code
        # template's labels can contain anything the document did. This is the
        # only escaping that is right for every one of them.
        self._dev.evaluate(
            f"(() => {{ document.getElementById('card').innerHTML = {json.dumps(svg)};"
            f" return true; }})()")
        # One frame for layout to settle. Nothing here animates — AnimatedSvg is a
        # player concern and this is the still — so a single rAF is enough.
        self._dev.evaluate(
            "new Promise(r => requestAnimationFrame(() => requestAnimationFrame("
            "() => r(true))))")

    def ink_box(self, svg: str) -> tuple[float, float, float, float] | None:
        """This frame's ink bounding box in canvas units, or None if unmeasurable.

        getBBox in a real browser, which is the same measurement AnimatedSvg's
        cropFor() makes — and it has to be, or the judge and the viewer see
        differently scaled pictures.
        """
        self._put(svg)
        return self._dev.evaluate(
            "(() => { const s = document.querySelector('#card svg'); if (!s) return null;"
            " try { const b = s.getBBox();"
            "   return (b.width && b.height) ? [b.x, b.y, b.width, b.height] : null; }"
            " catch (e) { return null; } })()")

    def shoot(self, svg: str, crop: tuple[float, float, float, float] | None = None) -> bytes:
        """One SVG in, PNG bytes out. `crop` is a viewBox in canvas units."""
        if self._dev is None:
            raise RasterUnavailable("rasteriser used outside its `with` block")
        if crop is not None:
            x, y, w, h = crop
            # preserveAspectRatio to match the player: the card is square and a
            # crop rarely is, so the drawing letterboxes inside it exactly as
            # AnimatedSvg letterboxes it inside .stageinner.
            svg = _with_viewbox(svg, x, y, w, h)
        self._put(svg)
        # PNG here, unlike video.py's JPEG: this frame is READ by a model rather
        # than re-encoded by x264, and JPEG ringing around small text is exactly
        # the artefact that would make a judge report an illegible label.
        import base64
        shot = self._dev.send("Page.captureScreenshot",
                              {"format": "png", "captureBeyondViewport": False})
        return base64.b64decode(shot["data"])


def render_pngs(svgs: dict[str, str], width: int = PNG_WIDTH) -> dict[str, bytes]:
    """
    Rasterise a whole short's frames. {ref: svg} -> {ref: png bytes}.

    Raises RasterUnavailable if there is no browser. A frame that fails to shoot
    is DROPPED rather than raising: the judge then grades the frames it could see
    and says which it could not, which is strictly better than losing the verdict
    on all of them because one SVG was malformed.
    """
    if not svgs:
        return {}
    out: dict[str, bytes] = {}
    with Rasteriser(width=width) as r:
        # THE CROP IS MEASURED ACROSS THE WHOLE SHORT, exactly as cropFor() does
        # it, and the reason is the reason cropFor gives: a per-frame crop rescales
        # the picture on every beat, so a sparse frame and a busy one are drawn at
        # different sizes and the composition appears to jump. Judging per-frame
        # crops would also have the judge grade a zoom the viewer never sees.
        #
        # It matters for the verdict as much as for fidelity. Uncropped, every
        # frame carries the empty band layout.py reserves and no longer draws, and
        # a judge looking at that reports wasted space on a frame the viewer sees
        # filled.
        boxes = []
        for ref, svg in svgs.items():
            if not svg:
                continue
            try:
                box = r.ink_box(svg)
            except Exception:
                box = None
            if box:
                boxes.append(box)

        crop = None
        if boxes:
            x0 = min(b[0] for b in boxes)
            y0 = min(b[1] for b in boxes)
            x1 = max(b[0] + b[2] for b in boxes)
            y1 = max(b[1] + b[3] for b in boxes)
            crop = (x0 - CROP_PAD, y0 - CROP_PAD,
                    x1 - x0 + 2 * CROP_PAD, y1 - y0 + 2 * CROP_PAD)

        for ref, svg in svgs.items():
            if not svg:
                continue
            try:
                out[ref] = r.shoot(svg, crop)
            except Exception as e:
                print(f"    rasterise {ref} failed: {type(e).__name__}: {str(e)[:100]}")
    return out


if __name__ == "__main__":  # pragma: no cover - a hand check that it draws
    import sys
    from .schema import Frame
    from .skills import layout
    frame = Frame(template="icons", title="Browser reads the file",
                  glyphs=[{"icon": "file", "label": "index.html", "role": "plain"},
                          {"icon": "browser", "label": "Browser", "role": "hero"}])
    png = render_pngs({"probe": layout.render(frame)})["probe"]
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "output/raster-probe.png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png)
    print(f"wrote {dest} ({len(png)} bytes)")
