"""
RESTYLE_TO_STORY_REELS.md Step 4 Part 3/4: unit tests for shorts/cast_sheets.py.

No API key, no network, no real provider calls — every test runs under
SHORTS_STUB=1 and drives shorts.cast_sheets.main() directly (no subprocess),
the same way every other *_test.py in this project calls the module under
test as a plain function rather than shelling out.

    SHORTS_STUB=1 python -m shorts.cast_sheets_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
import json
import shutil

from shorts import cast_sheets, config, imagegen


def _clean_state():
    """Every test gets a blank slate: no candidates, no approved sheets, no
    compare output, no leftover per-reel call-count state."""
    for d in (cast_sheets.CANDIDATES_DIR, cast_sheets.COMPARE_DIR, cast_sheets.ASSETS_DIR):
        shutil.rmtree(d, ignore_errors=True)
    imagegen.reset_call_count(None)


def _run(argv):
    """Run cast_sheets.main(argv), capturing stdout. Returns (exit_code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cast_sheets.main(argv)
    return code, buf.getvalue()


# ==================================================================== --dry-run

def test_dry_run_writes_prompts_json_and_calls_no_provider():
    _clean_state()
    calls = []
    original = imagegen.StubImageProvider.generate
    imagegen.StubImageProvider.generate = lambda self, *a, **kw: (calls.append(1), original(self, *a, **kw))[1]
    try:
        code, out = _run(["--dry-run"])
    finally:
        imagegen.StubImageProvider.generate = original

    assert code == 0
    assert not calls, "dry-run must never call a provider"
    prompts_path = cast_sheets.CANDIDATES_DIR / "prompts.json"
    assert prompts_path.exists()
    entries = json.loads(prompts_path.read_text(encoding="utf-8"))
    assert len(entries) == 3   # default candidate count
    assert all(e["character"] == "Rahul" for e in entries)   # Rahul is first
    assert all("STYLE_BIBLE" not in e["prompt"] for e in entries)   # substituted, not literal
    print(f"   ok — --dry-run writes {len(entries)} prompt(s) to {prompts_path} "
          f"and calls zero providers: {out.strip().splitlines()[-1]}")


def test_dry_run_prompt_includes_the_style_bible_and_look():
    _clean_state()
    _run(["--dry-run"])
    entries = json.loads((cast_sheets.CANDIDATES_DIR / "prompts.json").read_text())
    prompt = entries[0]["prompt"]
    assert "Hand-drawn stick figure illustration" in prompt   # STYLE_BIBLE
    assert config.CAST_LOOK["Rahul"] in prompt                # the look
    assert "reference sheet" in prompt
    print("   ok — a candidate prompt is STYLE_BIBLE + the character's look + "
          "the reference-sheet instruction, not a bare character name")


# ================================================== cost estimate + --yes gate

def test_candidates_without_yes_prints_cost_and_does_not_call():
    _clean_state()
    calls = []
    original = imagegen.StubImageProvider.generate
    imagegen.StubImageProvider.generate = lambda self, *a, **kw: (calls.append(1), original(self, *a, **kw))[1]
    try:
        code, out = _run(["--candidates", "5"])
    finally:
        imagegen.StubImageProvider.generate = original

    assert code != 0
    assert not calls, "no --yes means no provider call at all"
    assert "Estimated cost" in out
    assert "5" in out   # the call count
    assert not list(cast_sheets.CANDIDATES_DIR.glob("*.png"))
    print(f"   ok — --candidates without --yes prints the cost estimate and "
          f"calls no provider: {[l for l in out.splitlines() if 'cost' in l.lower()]}")


def test_candidates_with_yes_calls_and_writes_pngs():
    _clean_state()
    code, out = _run(["--candidates", "2", "--yes"])
    assert code == 0
    pngs = sorted(cast_sheets.CANDIDATES_DIR.glob("rahul_*.png"))
    assert len(pngs) == 2, pngs
    print(f"   ok — --candidates 2 --yes writes {[p.name for p in pngs]}")


def test_compare_without_yes_prints_per_provider_cost_and_does_not_call():
    _clean_state()
    calls = []
    original = imagegen.StubImageProvider.generate
    imagegen.StubImageProvider.generate = lambda self, *a, **kw: (calls.append(1), original(self, *a, **kw))[1]
    try:
        code, out = _run(["--compare", "--character", "rahul"])
    finally:
        imagegen.StubImageProvider.generate = original

    assert code != 0
    assert not calls
    assert "Estimated cost" in out or "Total estimated cost" in out
    print(f"   ok — --compare without --yes prints per-provider cost and calls "
          f"nothing: {[l for l in out.splitlines() if '$' in l]}")


# ========================================================================= approve

def test_approve_copies_candidate_to_assets_cast():
    _clean_state()
    _run(["--candidates", "2", "--yes"])
    code, out = _run(["--approve", "rahul", "2"])
    assert code == 0
    dst = cast_sheets.ASSETS_DIR / "rahul.png"
    assert dst.exists()
    assert dst.read_bytes() == cast_sheets.CANDIDATES_DIR.joinpath("rahul_2.png").read_bytes()
    print(f"   ok — --approve rahul 2 copies candidate 2 to {dst}")


def test_candidates_alone_never_overwrites_assets_cast():
    """--candidates (even --yes, even repeated) must never touch assets/cast —
    ONLY --approve does."""
    _clean_state()
    _run(["--candidates", "2", "--yes"])
    _run(["--approve", "rahul", "1"])
    before = (cast_sheets.ASSETS_DIR / "rahul.png").read_bytes()

    _run(["--candidates", "3", "--character", "rahul", "--yes"])
    after = (cast_sheets.ASSETS_DIR / "rahul.png").read_bytes()
    assert before == after, "generating more candidates must not touch the approved file"
    print("   ok — --candidates never writes to assets/cast/, approved or not, "
          "with or without --yes; only --approve does")


def test_approve_missing_candidate_fails_clearly():
    _clean_state()
    code, out = _run(["--approve", "rahul", "9"])
    assert code != 0
    assert not (cast_sheets.ASSETS_DIR / "rahul.png").exists()
    print(f"   ok — approving a candidate that was never generated fails "
          f"clearly, writes nothing: {out.strip().splitlines()[0]}")


# ============================================================ Rahul-first order

def test_riya_and_system_use_rahuls_approved_sheet_as_a_reference():
    _clean_state()
    _run(["--candidates", "2", "--yes"])           # Rahul candidates
    _run(["--approve", "rahul", "1"])              # approve Rahul

    code, out = _run(["--dry-run"])                # next: Riya
    entries = json.loads((cast_sheets.CANDIDATES_DIR / "prompts.json").read_text())
    assert entries[0]["character"] == "Riya"
    assert entries[0]["refs"] == [str(cast_sheets.ASSETS_DIR / "rahul.png")]
    assert "Match the character design" in entries[0]["prompt"]
    print("   ok — once Rahul is approved, Riya's (and by the same code path, "
          "System's) sheet prompt carries assets/cast/rahul.png as a style "
          "reference")


def test_system_is_next_after_riya_is_approved():
    _clean_state()
    _run(["--candidates", "1", "--yes"])
    _run(["--approve", "rahul", "1"])
    _run(["--candidates", "1", "--character", "riya", "--yes"])
    _run(["--approve", "riya", "1"])

    code, out = _run(["--dry-run"])
    entries = json.loads((cast_sheets.CANDIDATES_DIR / "prompts.json").read_text())
    assert entries[0]["character"] == "System"
    assert entries[0]["refs"] == [str(cast_sheets.ASSETS_DIR / "rahul.png")]
    print("   ok — with Rahul and Riya both approved, System is next, also "
          "referencing rahul.png")


def test_no_reference_for_rahul_himself():
    _clean_state()
    code, out = _run(["--dry-run"])
    entries = json.loads((cast_sheets.CANDIDATES_DIR / "prompts.json").read_text())
    assert entries[0]["character"] == "Rahul"
    assert entries[0]["refs"] == []
    print("   ok — Rahul's own sheet carries no reference image (nothing to "
          "match yet)")


def test_all_approved_reports_nothing_to_do():
    _clean_state()
    for name in cast_sheets.CAST_ORDER:
        _run(["--candidates", "1", "--character", name.lower(), "--yes"])
        _run(["--approve", name.lower(), "1"])

    code, out = _run(["--candidates", "1", "--yes"])
    assert code == 0
    assert "already have an approved sheet" in out
    assert not list(cast_sheets.CANDIDATES_DIR.glob("*_2.png"))
    print("   ok — once Rahul, Riya and System are all approved, --candidates "
          "with no --character reports nothing left to do")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} cast_sheets tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL CAST_SHEETS TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
