"""
Frame audit — every generated diagram, graded, counted by failure kind.

    python -m shorts.audit                    # every unit in output/
    python -m shorts.audit <short_id> ...     # just these
    python -m shorts.audit --contact-sheet    # also write an HTML contact sheet

WHY THIS IS A MODULE AND NOT A ONE-OFF SCRIPT
Three separate times in this project a change was reported as fixing the diagrams
on the strength of the build log, and three times an audit of the FINISHED frames
found the defects still there. The build log is not evidence: it prints only the
first problem of each redraw attempt, and the renderer kept the frame regardless of
what the checker said. The only trustworthy statement is a count over the units on
disk, which is what this produces.

The categories are kept separate on purpose, because they have different causes and
different fixes:

  empty         no SVG at all. A generation failure — a truncated response, a
                network error. The reel falls back to its overlay text.
  broken        an SVG that exists but cannot render correctly: no closing tag,
                coordinates outside the viewBox, text wider than the canvas.
  overlap       labels printed over each other or over a box they do not label.
                This is the one the template renderer exists to make impossible.
  busy          more shapes than a phone screen can carry in four seconds.
                Advisory: a frame at 7 is fine, one at 20 is a wall of boxes.
"""
import argparse, glob, json, re
from pathlib import Path

from . import checks, config

_SHAPE = re.compile(r"<(rect|circle|ellipse|polygon|polyline|path|line)\b", re.I)

#: Problem strings that mean "two things are drawn on top of each other". Matched
#: on the wording checks._collisions produces.
_OVERLAP_MARKERS = ("printed across the box", "printed on top of each other",
                    "spills out over both edges")

#: Problem strings that mean the frame cannot render correctly as markup.
_BROKEN_MARKERS = ("outside the", "wider than the", "is rotated")

SIDECARS = {"manifest.json", "topics.json", "topics.stub.json", "usage.json"}


def classify(problems: list[str]) -> dict[str, list[str]]:
    """Split one frame's problems into the categories above."""
    out: dict[str, list[str]] = {"overlap": [], "broken": [], "busy": [], "other": []}
    for p in problems:
        if any(m in p for m in _OVERLAP_MARKERS):
            out["overlap"].append(p)
        elif "draws" in p and "shapes" in p:
            out["busy"].append(p)
        elif any(m in p for m in _BROKEN_MARKERS):
            out["broken"].append(p)
        else:
            out["other"].append(p)
    return out


def audit(paths: list[Path]) -> dict:
    totals = {"units": 0, "frames": 0, "empty": 0, "broken": 0, "overlap": 0,
              "busy": 0, "other": 0, "clean_frames": 0}
    units = []

    for path in paths:
        try:
            unit = json.loads(path.read_text())
        except Exception as e:
            print(f"  skipping {path.name}: {type(e).__name__}")
            continue
        totals["units"] += 1
        rows = []

        for ref, visual in (unit.get("visuals") or {}).items():
            svg = visual.get("svg") or ""
            totals["frames"] += 1

            if not svg:
                totals["empty"] += 1
                rows.append({"ref": ref, "template": _template(visual), "state": "EMPTY",
                             "shapes": 0, "problems": {}})
                continue

            # A frame missing its closing tag is broken regardless of what else the
            # checker finds, and svg_problems cannot see it.
            unclosed = "<svg" not in svg or "</svg>" not in svg
            problems = checks.svg_problems(svg, collisions=True,
                                           max_shapes=checks.MAX_SHAPES)
            kinds = classify(problems)
            if unclosed:
                kinds["broken"].append("no closing </svg> — the response was cut off")

            for key in ("overlap", "broken", "busy", "other"):
                totals[key] += len(kinds[key])
            if not any(kinds.values()):
                totals["clean_frames"] += 1

            rows.append({
                "ref": ref, "template": _template(visual), "shapes": len(_SHAPE.findall(svg)),
                "state": "CLEAN" if not any(kinds.values()) else "ISSUES",
                "problems": {k: v for k, v in kinds.items() if v},
            })

        units.append({"short_id": unit.get("short_id"), "question": unit.get("question"),
                      "beats": unit.get("beats", []), "visuals": unit.get("visuals", {}),
                      "rows": rows})
    return {"totals": totals, "units": units}


def _template(visual: dict) -> str:
    return ((visual.get("frame") or {}).get("template")) or "-"


def report(result: dict) -> None:
    for unit in result["units"]:
        print(f"\n== {unit['short_id']}")
        print(f"   Q: {unit['question']}")
        for row in unit["rows"]:
            print(f"   {row['ref']:32} {row['template']:9} shapes={row['shapes']:2}  {row['state']}")
            for kind, items in row["problems"].items():
                for p in items:
                    print(f"       [{kind}] {p[:100]}")

    t = result["totals"]
    print("\n" + "=" * 62)
    print(f"  units                 {t['units']}")
    print(f"  frames total          {t['frames']}")
    print(f"  frames fully clean    {t['clean_frames']}")
    print("  " + "-" * 40)
    print(f"  empty SVGs            {t['empty']}")
    print(f"  broken/truncated      {t['broken']}")
    print(f"  collision/overlap     {t['overlap']}")
    print(f"  too busy (advisory)   {t['busy']}")
    print(f"  other                 {t['other']}")
    print("=" * 62)


def contact_sheet(result: dict, out: Path) -> Path:
    """
    Every frame beside the words spoken over it, as one HTML page.

    This is the check no grader can make: whether the picture is about the same
    thing as the voice. Reading a frame next to its own narration line is the only
    way to see that, so the sheet pairs them rather than showing the diagrams alone.
    """
    blocks = []
    for unit in result["units"]:
        # Which beats play over each visual, in beat order.
        said: dict[str, list[str]] = {}
        for beat in unit["beats"]:
            said.setdefault(beat["visual_ref"], []).append(
                f"<b>{beat['speaker']}:</b> {_esc(beat['line'])}")

        cards = []
        for ref, visual in unit["visuals"].items():
            svg = visual.get("svg") or ""
            lines = "<br>".join(said.get(ref, ["<i>no beat uses this frame</i>"]))
            body = svg or '<div class="none">no SVG</div>'
            cards.append(
                f'<figure><div class="card">{body}</div>'
                f'<figcaption><code>{_esc(ref)}</code> · {_template(visual)}'
                f'<p>{lines}</p>'
                f'<p class="spec">{_esc(visual.get("spec") or "")}</p></figcaption></figure>')
        blocks.append(f"<section><h2>{_esc(unit['question'])}</h2>"
                      f'<div class="row">{"".join(cards)}</div></section>')

    html = f"""<!doctype html><meta charset="utf-8"><title>Frame audit</title><style>
 body{{margin:0;padding:22px;background:#0b0f11;color:#e8e6e0;
      font:14px/1.5 ui-sans-serif,system-ui,sans-serif}}
 h1{{font-size:19px;margin:0 0 4px}} h2{{font-size:15px;font-weight:650;margin:26px 0 10px}}
 .row{{display:flex;gap:14px;flex-wrap:wrap}}
 figure{{margin:0;width:300px}}
 .card{{width:300px;height:300px;background:linear-gradient(168deg,#FCFBF7,#EFF4F1);
       border-radius:16px;display:grid;place-items:center;overflow:hidden}}
 .card svg{{width:100%;height:100%}}
 .none{{color:#a33;font-weight:700}}
 figcaption{{margin-top:7px;font-size:11.5px;color:#a9a7a1}}
 figcaption p{{margin:5px 0 0;color:#e8e6e0;font-size:12px}}
 figcaption .spec{{color:#8e8c86;font-style:italic}}
 code{{color:#5ecfa4}}
</style>
<h1>Frame audit — does the picture match the voice?</h1>
<p style="color:#8e8c86;margin:0 0 6px">Each frame with the narration that plays over it.</p>
{''.join(blocks)}"""
    out.write_text(html, encoding="utf-8")
    return out


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("short_ids", nargs="*", help="default: every unit in output/")
    ap.add_argument("--contact-sheet", metavar="PATH", nargs="?",
                    const="output/frame_audit.html",
                    help="also write frames beside their narration as HTML")
    args = ap.parse_args()

    if args.short_ids:
        paths = [config.OUTPUT_DIR / f"{s}.json" for s in args.short_ids]
    else:
        paths = [Path(p) for p in sorted(glob.glob(str(config.OUTPUT_DIR / "*.json")))
                 if Path(p).name not in SIDECARS]
    paths = [p for p in paths if p.exists()]
    if not paths:
        raise SystemExit("no units in output/ — run `python -m shorts.run <doc>` first")

    result = audit(paths)
    report(result)
    if args.contact_sheet:
        print(f"\ncontact sheet: {contact_sheet(result, Path(args.contact_sheet))}")


if __name__ == "__main__":
    main()
