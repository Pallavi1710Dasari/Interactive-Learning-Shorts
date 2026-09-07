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

    print("2. loading the known-good script fixtures")
    # TWO fixtures, at OPPOSITE ENDS of the 25-45s window, and that is the point.
    #
    # One would not catch what this has to catch. The window is wide because the
    # concept decides the length, so "does a good short pass" has two answers that
    # can break independently: a concise 29-second explanation and a 36-second one
    # that also corrects a misconception. A floor that crept up would fail only the
    # first; a cap that crept down, only the second.
    fixtures = [("concise_but_complete.json", "3.1", "concise, 25-30s band"),
                ("good_page_fault.json", "3.3", "mechanism + misconception, 30-38s")]
    scripts = []
    for name, section_id, note in fixtures:
        data = json.loads((ROOT / f"evals/fixtures/{name}").read_text())
        sc = Script(**data)
        scripts.append((sc, section_id, note))
        print(f"   ok — {name}: {sc.word_count} words, {sc.estimated_seconds}s ({note})")
    script = scripts[-1][0]          # the richer one carries on through step 4

    print("3. running the code graders")
    for sc, section_id, note in scripts:
        section = find_section(sections, section_id)
        results = checks.run_script_graders(sc, section.text)
        print(f"   --- {sc.estimated_seconds}s, {note}")
        for r in results:
            print(f"   {r}")
        assert checks.all_passed(results), (
            f"the good fixture at {sc.estimated_seconds}s should pass every grader")

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
