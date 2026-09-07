"""
Offline smoke test. No API key, no network, no cost. Run this FIRST on day one.
If this passes, your schema, parser, and graders are wired correctly.

    python -m shorts.smoke_test
"""
import json
from pathlib import Path
from .schema import Script, ShortUnit, Visual
from .parse import parse_markdown, find_section
from . import checks

ROOT = Path(__file__).resolve().parent.parent


def main():
    print("1. parsing the sample doc")
    sections = parse_markdown(ROOT / "content" / "session_18_paging.md")
    assert len(sections) == 5, f"expected 5 sections, got {len(sections)}"
    print(f"   ok — {[s.section_id for s in sections]}")

    print("2. loading a known-good script fixture")
    # good_page_fault.json is the known-good shape: one question, 5 short answers —
    # mechanism, then a corrected misconception, then a takeaway.
    data = json.loads((ROOT / "evals/fixtures/good_page_fault.json").read_text())
    script = Script(**data)
    print(f"   ok — {script.word_count} words, {script.estimated_seconds}s estimated")

    print("3. running the code graders")
    section = find_section(sections, "3.3")
    results = checks.run_script_graders(script, section.text)
    for r in results:
        print(f"   {r}")
    assert checks.all_passed(results), "the good fixture should pass every grader"

    print("4. assembling a ShortUnit (no audio yet)")
    visuals = {b.visual_ref: Visual(ref=b.visual_ref, type="text", spec="placeholder")
               for b in script.beats}
    unit = ShortUnit(
        short_id=script.short_id, session_id="os_session_18",
        source_section_id="3.3", question=script.question,
        estimated_seconds=script.estimated_seconds,
        beats=script.beats, visuals=visuals,
    )
    print(f"   ok — {len(unit.beats)} beats, {len(unit.visuals)} visuals, status={unit.status}")

    print("5. confirming a broken unit is rejected")
    try:
        ShortUnit(**{**unit.model_dump(), "visuals": {}})
        raise AssertionError("a unit with missing visuals should NOT validate")
    except Exception as e:
        print(f"   ok — rejected as expected: {str(e).splitlines()[-1][:70]}")

    out = ROOT / "output" / "smoke_unit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(unit.model_dump_json(indent=2))
    print(f"\nALL OFFLINE CHECKS PASSED. Wrote {out.relative_to(ROOT)}")
    print("Next: add your ANTHROPIC_API_KEY to .env and run step 6 in the README.")


if __name__ == "__main__":
    main()
