"""
The human gate. A terminal reviewer — deliberately boring, deliberately fast.

    python -m shorts.review

Shows one short at a time as text. You never watch a video to approve it.
Sets status to approved or rejected in the unit JSON.
"""
import json
from pathlib import Path
from .schema import ShortUnit
from . import config


#          output/ also holds sidecars that are not units. A stray file here used to
#          blow up on ShortUnit(**...) with a wall of pydantic errors.
SIDECARS = {"manifest.json", "topics.json", "smoke_unit.json"}


def main():
    files = sorted(f for f in config.OUTPUT_DIR.glob("*.json") if f.name not in SIDECARS)
    if not files:
        print("nothing to review — run `python -m shorts.run <doc>` first")
        return

    for f in files:
        unit = ShortUnit(**json.loads(f.read_text()))
        if unit.status in ("approved", "rendered"):
            continue

        print("\n" + "=" * 78)
        print(f"{unit.short_id}   section {unit.source_section_id}   {unit.estimated_seconds}s")
        print(f"Q: {unit.question}")
        print("-" * 78)
        for i, b in enumerate(unit.beats):
            who = "INT" if b.speaker == "interviewer" else "STU"
            print(f"{i}. [{who}] {b.line}")
            print(f"        screen: \"{b.on_screen}\"   visual: {b.visual_ref}")
        print("-" * 78)
        for ref, v in unit.visuals.items():
            has_svg = "svg ok" if v.svg else ("no svg" if v.type == "diagram" else "-")
            print(f"  {ref:26} {v.type:8} {has_svg:8} {v.spec[:60]}")
        if unit.eval:
            print(f"\n  judge: faithfulness={unit.eval.faithfulness} "
                  f"clarity={unit.eval.clarity} pace={unit.eval.pace} "
                  f"diagram_ok={unit.eval.diagram_correct}")
            for p in unit.eval.problems:
                print(f"    ! {p}")

        choice = input("\n[a]pprove  [r]eject  [s]kip  [q]uit > ").strip().lower()
        if choice == "q":
            break
        if choice == "a":
            unit.status = "approved"
        elif choice == "r":
            unit.status = "rejected"
        else:
            continue
        f.write_text(unit.model_dump_json(indent=2))
        print(f"  -> {unit.status}")


if __name__ == "__main__":
    main()
