"""
Free, local, no-LLM pre-checks on a generated frame — RESTYLE_TO_STORY_REELS.md
Step 6 Part 1.

Run BEFORE skills.vision.judge_story_frame (the paid judge) ever sees a frame.
A failing pre-check is a STRUCTURAL defect — wrong size, blank, off-palette,
carrying text it shouldn't, or drawn into the overlay safe zones — that free
code can catch outright, the same reason checks.py grades a Script before
skills/audit.py ever pays for a judge call on it. story_frames.py's
regenerate loop skips the judge entirely on a pre-check failure; there is
nothing to ask a model's opinion about when the frame is the wrong size.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from . import config
from .schema import Shot

FRAME_SIZE = (1080, 1920)

#: Below this average per-channel stddev (0-255 scale), a frame reads as a
#: single near-flat colour, not an illustration — every real hand-drawn
#: frame (outlines + background + at least one accent) varies far more.
BLANK_STDDEV_THRESHOLD = 8.0

#: How far (max per-RGB-channel delta, 0-255) a pixel may sit from one of
#: the 4 allowed colors (bg/black/accent_1/accent_2) before it no longer
#: counts as "in palette" — generous, because anti-aliasing and shading
#: legitimately produce a spread of nearby tones, not the 4 exact hex values.
PALETTE_TOLERANCE = 40

#: What fraction of the frame's pixels must fall within PALETTE_TOLERANCE of
#: one of the 4 allowed colors for the palette check to pass.
PALETTE_MIN_COVERAGE = 0.55

#: STYLE_BIBLE's own numbers (shorts/style.py) — keep in sync with them.
TOP_SAFE_ZONE_FRACTION = 0.12
BOTTOM_SAFE_ZONE_FRACTION = 0.18
#: Mean value of an edge-detected safe-zone region (0.0-1.0, normalised from
#: 0-255) above this means the zone is busy with drawn detail, not "mostly
#: empty" — an overlay (a caption, a recap line) placed on top of it there
#: would be drawn over real artwork.
MAX_SAFE_ZONE_EDGE_DENSITY = 0.06

try:
    import pytesseract
except ImportError:
    pytesseract = None


@dataclass
class PreCheckResult:
    name: str
    passed: bool
    reason: str = ""
    #: True when this check did not actually run (e.g. pytesseract/tesseract
    #: unavailable) — `passed` is True either way (Step 6's own "skip with a
    #: warning, never crash" rule), but a caller printing results can still
    #: tell "verified clean" apart from "never checked".
    skipped: bool = False

    def __str__(self) -> str:
        if self.skipped:
            return f"[SKIP] {self.name} — {self.reason}"
        mark = "PASS" if self.passed else "FAIL"
        return f"[{mark}] {self.name}" + (f" — {self.reason}" if self.reason else "")


def all_passed(results: list[PreCheckResult]) -> bool:
    return all(r.passed for r in results)


def check_size(img: Image.Image) -> PreCheckResult:
    if img.size != FRAME_SIZE:
        return PreCheckResult("size", False, f"frame is {img.size}, needs {FRAME_SIZE}")
    return PreCheckResult("size", True, f"{FRAME_SIZE}")


def check_not_blank(img: Image.Image) -> PreCheckResult:
    stat = ImageStat.Stat(img.convert("RGB"))
    avg_stddev = sum(stat.stddev) / len(stat.stddev)
    if avg_stddev < BLANK_STDDEV_THRESHOLD:
        return PreCheckResult("not_blank", False,
                              f"near-uniform frame (stddev={avg_stddev:.1f}, needs >= "
                              f"{BLANK_STDDEV_THRESHOLD})")
    return PreCheckResult("not_blank", True, f"stddev={avg_stddev:.1f}")


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _channel_dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return max(abs(a[i] - b[i]) for i in range(3))


def check_palette(img: Image.Image) -> PreCheckResult:
    allowed = [
        _hex_to_rgb(config.BRAND.bg),
        (0, 0, 0),
        _hex_to_rgb(config.BRAND.accent_1),
        _hex_to_rgb(config.BRAND.accent_2),
    ]
    # Downsampled — a palette check does not need every pixel, and this
    # keeps it fast on a full 1080x1920 frame.
    small = img.convert("RGB").resize((108, 192))
    pixels = list(small.getdata())
    within = sum(1 for p in pixels if any(_channel_dist(p, a) <= PALETTE_TOLERANCE
                                          for a in allowed))
    coverage = within / len(pixels)
    if coverage < PALETTE_MIN_COVERAGE:
        return PreCheckResult("palette", False,
                              f"only {coverage:.0%} of pixels are within tolerance of "
                              f"bg/black/accent_1/accent_2, needs >= {PALETTE_MIN_COVERAGE:.0%}")
    return PreCheckResult("palette", True, f"{coverage:.0%} of pixels in palette")


def _ocr_words(img: Image.Image) -> list[tuple[str, float]] | None:
    """
    [(text, confidence 0-100), ...] for every non-blank OCR token, or None if
    OCR isn't usable at all (pytesseract not installed, or the tesseract
    BINARY isn't — that raises at CALL time, not import time, so this must
    guard both). Never raises.

    RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #4: uses image_to_data (per-word
    confidence), not image_to_string (plain text) — a stick-figure line or a
    stray outline artifact OCRs as low-confidence garbage far more often than
    real drawn text does, and check_text below needs that confidence number
    to tell the two apart. Confidence values pytesseract cannot parse as a
    number (it uses "-1" for non-text rows in image_to_data's own output,
    but is not contractually guaranteed to) are treated as 0, never as a
    reason to raise.
    """
    if pytesseract is None:
        return None
    try:
        from pytesseract import Output
        data = pytesseract.image_to_data(img, output_type=Output.DICT)
    except Exception:
        return None

    words = []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        text = text.strip()
        if not text:
            continue
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        words.append((text, conf))
    return words


def check_text(img: Image.Image, shot: Shot) -> PreCheckResult:
    """
    Fails on any OCR'd WORD (>= config.TEXT_CHECK_MIN_WORD_LENGTH letters,
    at >= config.TEXT_CHECK_MIN_CONFIDENCE confidence) or any OCR'd DIGIT not
    in the shot's own ALLOWED GLYPHS. Both thresholds exist for the same
    reason: thick clean stick-figure outlines OCR as short, low-confidence
    noise far more often than real drawn text does, and without them almost
    every honestly clean frame would fail this check on a stray misread.
    """
    from .skills.visuals import allowed_glyphs   # local import: visuals -> imagegen, no cycle back here

    words = _ocr_words(img)
    if words is None:
        return PreCheckResult("text", True,
                              "pytesseract/tesseract not available — skipped", skipped=True)

    allowed_digits = {d.strip() for d in allowed_glyphs(shot).split(",") if d.strip()}
    bad_words: list[str] = []
    bad_digits: set[str] = set()

    for text, conf in words:
        if conf < config.TEXT_CHECK_MIN_CONFIDENCE:
            continue
        letters = re.sub(r"[^A-Za-z]", "", text)
        if len(letters) >= config.TEXT_CHECK_MIN_WORD_LENGTH:
            bad_words.append(text)
        for d in re.findall(r"\d", text):
            if d not in allowed_digits:
                bad_digits.add(d)

    if bad_words:
        return PreCheckResult("text", False,
                              f"OCR found word(s) (>= {config.TEXT_CHECK_MIN_CONFIDENCE}% "
                              f"confidence, >= {config.TEXT_CHECK_MIN_WORD_LENGTH} letters): "
                              f"{bad_words[:5]}")
    if bad_digits:
        return PreCheckResult("text", False,
                              f"OCR found digit(s) not in ALLOWED GLYPHS "
                              f"{sorted(allowed_digits) or 'none'}: {sorted(bad_digits)}")
    return PreCheckResult("text", True, "no letters; any digits match ALLOWED GLYPHS")


def _edge_density(region: Image.Image) -> float:
    edges = region.convert("L").filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(edges).mean[0] / 255.0


def check_safe_zones(img: Image.Image) -> PreCheckResult:
    w, h = img.size
    top_h = round(h * TOP_SAFE_ZONE_FRACTION)
    bottom_h = round(h * BOTTOM_SAFE_ZONE_FRACTION)
    top_density = _edge_density(img.crop((0, 0, w, top_h)))
    bottom_density = _edge_density(img.crop((0, h - bottom_h, w, h)))

    problems = []
    if top_density > MAX_SAFE_ZONE_EDGE_DENSITY:
        problems.append(f"top {TOP_SAFE_ZONE_FRACTION:.0%} safe zone too busy "
                        f"(edge density {top_density:.3f} > {MAX_SAFE_ZONE_EDGE_DENSITY})")
    if bottom_density > MAX_SAFE_ZONE_EDGE_DENSITY:
        problems.append(f"bottom {BOTTOM_SAFE_ZONE_FRACTION:.0%} safe zone too busy "
                        f"(edge density {bottom_density:.3f} > {MAX_SAFE_ZONE_EDGE_DENSITY})")
    if problems:
        return PreCheckResult("safe_zones", False, "; ".join(problems))
    return PreCheckResult("safe_zones", True,
                          f"top={top_density:.3f} bottom={bottom_density:.3f}, both mostly empty")


def run_pre_checks(image_path: Path, shot: Shot) -> list[PreCheckResult]:
    """Every free pre-check, in order, for ONE generated frame. Opens the
    file once and reuses the same Image for every check."""
    img = Image.open(image_path)
    return [
        check_size(img),
        check_not_blank(img),
        check_palette(img),
        check_text(img, shot),
        check_safe_zones(img),
    ]
