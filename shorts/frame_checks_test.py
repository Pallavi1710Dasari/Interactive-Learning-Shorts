"""
RESTYLE_TO_STORY_REELS.md Step 6 Part 1: unit tests for shorts/frame_checks.py.

No API key, no network — every check here is pure local image analysis on
small synthetic PNGs built with PIL. OCR is exercised via a monkeypatched
shorts.frame_checks._ocr_text (this machine has neither pytesseract nor the
tesseract binary installed — see test_ocr_missing_skips_with_warning, which
proves the REAL "not installed" path too).

    SHORTS_STUB=1 python -m shorts.frame_checks_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from PIL import Image, ImageDraw

from shorts import config, frame_checks
from shorts.schema import Shot


BG = frame_checks._hex_to_rgb(config.BRAND.bg)
ACCENT = frame_checks._hex_to_rgb(config.BRAND.accent_2)


def _good_frame() -> Image.Image:
    """A synthetic frame that should clear every pre-check: right size, a
    real shape (not blank), on-palette colors, nothing in the safe zones."""
    img = Image.new("RGB", frame_checks.FRAME_SIZE, BG)
    d = ImageDraw.Draw(img)
    top = round(frame_checks.FRAME_SIZE[1] * frame_checks.TOP_SAFE_ZONE_FRACTION)
    bottom = frame_checks.FRAME_SIZE[1] - round(
        frame_checks.FRAME_SIZE[1] * frame_checks.BOTTOM_SAFE_ZONE_FRACTION)
    d.ellipse([300, top + 200, 780, bottom - 200], fill=ACCENT, outline=(0, 0, 0), width=8)
    return img


SHOT = Shot(shot_id="t0", action="a scene", key_prop=None)


# ==================================================================== size

def test_size_correct_passes():
    result = frame_checks.check_size(_good_frame())
    assert result.passed, result.reason
    print("   ok — a 1080x1920 frame passes check_size")


def test_size_wrong_fails():
    img = Image.new("RGB", (500, 500), BG)
    result = frame_checks.check_size(img)
    assert not result.passed
    print(f"   ok — a frame that isn't 1080x1920 fails check_size: {result.reason}")


# ================================================================ not_blank

def test_not_blank_with_content_passes():
    result = frame_checks.check_not_blank(_good_frame())
    assert result.passed, result.reason
    print("   ok — a frame with real drawn content passes check_not_blank")


def test_not_blank_flat_color_fails():
    img = Image.new("RGB", frame_checks.FRAME_SIZE, BG)
    result = frame_checks.check_not_blank(img)
    assert not result.passed
    print(f"   ok — a perfectly flat frame fails check_not_blank: {result.reason}")


# ================================================================== palette

def test_palette_on_brand_passes():
    result = frame_checks.check_palette(_good_frame())
    assert result.passed, result.reason
    print("   ok — a frame using only bg/black/accent colors passes check_palette")


def test_palette_off_brand_fails():
    img = Image.new("RGB", frame_checks.FRAME_SIZE, (255, 0, 255))   # bright magenta
    result = frame_checks.check_palette(img)
    assert not result.passed
    print(f"   ok — a frame dominated by an off-palette color fails check_palette: "
         f"{result.reason}")


# =============================================================== safe_zones

def test_safe_zones_empty_passes():
    result = frame_checks.check_safe_zones(_good_frame())
    assert result.passed, result.reason
    print("   ok — a frame with empty top/bottom margins passes check_safe_zones")


def test_safe_zones_busy_top_fails():
    img = Image.new("RGB", frame_checks.FRAME_SIZE, BG)
    d = ImageDraw.Draw(img)
    for x in range(0, frame_checks.FRAME_SIZE[0], 8):
        d.line([(x, 0), (x, 200)], fill=(0, 0, 0), width=3)
    result = frame_checks.check_safe_zones(img)
    assert not result.passed
    print(f"   ok — dense line art drawn into the top safe zone fails "
         f"check_safe_zones: {result.reason}")


# ======================================================================= text
#
# RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #4: `pip install pytesseract`
# succeeded in this environment (the module IS importable — see
# frame_checks.pytesseract below), but the `tesseract-ocr` SYSTEM BINARY
# could not be — this sandbox has no passwordless root (confirmed: `sudo
# apt-get install tesseract-ocr` prompts for a password with no way to
# supply one, and `apt-get` itself refuses without root). So the REAL,
# UNMOCKED path on this machine is "module present, binary missing", which
# test_ocr_binary_missing_skips_with_warning below exercises for real, not
# mocked. Every other test here monkeypatches frame_checks._ocr_words (the
# per-word, per-confidence list image_to_data returns) to simulate what a
# real OCR engine would report, since there is no way to run one live here.

def test_pytesseract_module_is_installed_but_binary_is_not():
    """Documents the actual state of this sandbox, so the rest of this
    section's mocking makes sense rather than looking arbitrary."""
    assert frame_checks.pytesseract is not None, (
        "pytesseract should be pip-installed in this environment")
    print("   ok — frame_checks.pytesseract is importable (pip install "
          "pytesseract succeeded); the tesseract-ocr system binary is what's "
          "actually missing here, confirmed by the next test")


def test_ocr_binary_missing_skips_with_warning():
    """THE REAL, UNMOCKED PATH on this machine — pytesseract.image_to_data()
    raises TesseractNotFoundError because the system binary isn't on PATH,
    and _ocr_words must swallow that (not just ImportError) and check_text
    must skip with a warning rather than crash."""
    result = frame_checks.check_text(_good_frame(), SHOT)
    assert result.passed and result.skipped
    print(f"   ok — with pytesseract's module present but the tesseract "
         f"binary missing, check_text SKIPS for real (not mocked) rather "
         f"than crashing: {result.reason}")


def _mock_ocr(words: list[tuple[str, float]]):
    """words: [(text, confidence 0-100), ...] — the exact shape
    frame_checks._ocr_words returns."""
    frame_checks._ocr_words = lambda img: words


def test_ocr_high_confidence_word_fails():
    """A synthetic frame with REAL TEXT actually drawn on it (not just a
    mocked OCR result standing alone) — this must fail check_text."""
    img = _good_frame()
    d = ImageDraw.Draw(img)
    d.text((100, 100), "WARNING", fill=(0, 0, 0))
    original = frame_checks._ocr_words
    _mock_ocr([("WARNING", 92.0)])   # what a real OCR engine would report for this frame
    try:
        result = frame_checks.check_text(img, SHOT)
    finally:
        frame_checks._ocr_words = original
    assert not result.passed and not result.skipped
    print(f"   ok — a synthetic frame with real text drawn on it, and a "
         f"high-confidence OCR match for that text, fails check_text: "
         f"{result.reason}")


def test_ocr_clean_line_drawing_passes():
    """A clean line drawing with NO text anywhere — OCR reports nothing —
    must pass check_text."""
    original = frame_checks._ocr_words
    _mock_ocr([])
    try:
        result = frame_checks.check_text(_good_frame(), SHOT)
    finally:
        frame_checks._ocr_words = original
    assert result.passed and not result.skipped
    print("   ok — a clean line drawing (OCR finds nothing) passes "
          "check_text as a real (not skipped) verdict")


def test_ocr_low_confidence_misread_is_ignored():
    """A stick-figure outline OCR'd as a low-confidence garbage 'word' must
    NOT fail the check — this is exactly the false-positive Step 7 Part 0 #4
    asks the confidence threshold to prevent."""
    original = frame_checks._ocr_words
    _mock_ocr([("li", 22.0), ("l", 15.0)])   # below TEXT_CHECK_MIN_CONFIDENCE (60)
    try:
        result = frame_checks.check_text(_good_frame(), SHOT)
    finally:
        frame_checks._ocr_words = original
    assert result.passed
    print(f"   ok — low-confidence OCR noise (stick-figure-line misreads) "
         f"does not fail check_text: {result.reason}")


def test_ocr_short_high_confidence_token_is_ignored():
    """A single high-confidence LETTER (below TEXT_CHECK_MIN_WORD_LENGTH)
    must not fail the check either — a 1-letter misread is still noise, not
    a real word, even at high confidence."""
    original = frame_checks._ocr_words
    _mock_ocr([("l", 95.0)])   # 1 letter, high confidence
    try:
        result = frame_checks.check_text(_good_frame(), SHOT)
    finally:
        frame_checks._ocr_words = original
    assert result.passed
    print(f"   ok — a high-confidence but too-short token (1 letter) does "
         f"not fail check_text: {result.reason}")


def test_ocr_allowed_digit_passes_disallowed_digit_fails():
    shot_with_glyph = Shot(shot_id="t1", action="the button reads 0", key_prop="button")
    original = frame_checks._ocr_words

    _mock_ocr([("0", 95.0)])
    try:
        ok = frame_checks.check_text(_good_frame(), shot_with_glyph)
    finally:
        frame_checks._ocr_words = original
    assert ok.passed

    _mock_ocr([("7", 95.0)])
    try:
        bad = frame_checks.check_text(_good_frame(), shot_with_glyph)
    finally:
        frame_checks._ocr_words = original
    assert not bad.passed

    print(f"   ok — a high-confidence digit OCR'd from the frame that IS in "
         f"the shot's ALLOWED GLYPHS passes ({ok.reason}); one that ISN'T "
         f"fails ({bad.reason})")


# ========================================================== run_pre_checks

def test_run_pre_checks_all_pass_on_a_good_frame(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = f"{d}/good.png"
        _good_frame().save(path)
        results = frame_checks.run_pre_checks(path, SHOT)
        assert frame_checks.all_passed(results), [str(r) for r in results if not r.passed]
    print(f"   ok — run_pre_checks returns all-passing results for a good "
         f"frame: {[r.name for r in results]}")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} frame_checks tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL FRAME_CHECKS TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
