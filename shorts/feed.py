"""
Turns the unit JSON in output/ into the payload the web app plays.

    python -m shorts.feed            # writes web/public/shorts.json

This is the only place that decides what a "reel" looks like as data — the API
serves the same structure from /api/shorts, so the app has one shape to render
whether it is reading a file or talking to the server.

There is deliberately no HTML renderer here any more. The React app in web/ is
the single UI; a second hand-written player was one more thing to keep in sync.
"""
import argparse, json, re
from pathlib import Path

from .schema import ShortUnit, WORDS_PER_SECOND
from . import config

# Files that live in output/ but are not shorts. This list is a convenience, not
# the safety net — collect() also skips anything that fails to validate, because
# every time something new gets written here (topics.json, then usage.json) a
# blocklist that has to be updated by hand becomes a 500.
SIDECARS = {"manifest.json", "topics.json", "smoke_unit.json", "usage.json"}
MIN_BEAT_SECONDS = 1.4


def _timeline(unit: ShortUnit) -> tuple[list[dict], float]:
    """
    Give every beat a start and end.

    Three sources, best first:

      1. The synthesiser's own per-beat spans. Exact, and the only one that stays
         correct when the spoken text is repunctuated for delivery.
      2. Word timings, cut by the written word count. Kept for tracks recorded
         before spans existed. It assumes the spoken text has exactly as many
         whitespace tokens as the written line, which conversational formatting
         breaks — hence (1).
      3. Word count at the project's words-per-minute constant, when there is no
         audio at all. The browser voice then overrides it at playback time by
         advancing on each utterance ending.
    """
    spans, cursor = [], 0.0
    beat_spans = unit.audio.beat_spans if unit.audio else []
    timings = unit.audio.word_timings if unit.audio else []
    consumed = 0

    for i, beat in enumerate(unit.beats):
        n = len(beat.line.split())
        if i < len(beat_spans):
            start, end = beat_spans[i].start, beat_spans[i].end
        elif timings:
            slice_ = timings[consumed:consumed + n]
            consumed += n
            start = slice_[0].start if slice_ else cursor
            end = slice_[-1].end if slice_ else cursor + n / WORDS_PER_SECOND
        else:
            start = cursor
            end = cursor + max(MIN_BEAT_SECONDS, n / WORDS_PER_SECOND)
        cursor = end
        visual = unit.visuals.get(beat.visual_ref)
        spans.append({
            "speaker": beat.speaker,
            "line": beat.line,
            "on_screen": beat.on_screen,
            "visual_ref": beat.visual_ref,
            "svg": _clean_svg(visual.svg) if visual and visual.svg else None,
            "start": round(start, 2),
            "end": round(end, 2),
        })
    return spans, round(cursor, 2)


def _clean_svg(svg: str) -> str:
    """
    The SVG is model-generated and gets injected into the DOM. SVG_SYSTEM forbids
    scripts, but a prompt is not an enforcement mechanism.
    """
    svg = re.sub(r"<script.*?</script>", "", svg, flags=re.S | re.I)
    return re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", svg, flags=re.I)


def collect() -> list[dict]:
    """Every unit in output/, newest section first, in reel-playable form."""
    units = []
    for path in sorted(config.OUTPUT_DIR.glob("*.json")):
        if path.name in SIDECARS:
            continue
        try:
            unit = ShortUnit(**json.loads(path.read_text()))
        except Exception as e:
            # Not a short. Skipping beats taking down every caller of this
            # function — which includes the endpoint that has just spent money
            # building shorts and is trying to return them.
            print(f"  skipping {path.name}: not a short unit ({type(e).__name__})")
            continue
        beats, total = _timeline(unit)
        units.append({
            "short_id": unit.short_id,
            "question": unit.question,
            "section": unit.source_section_id,
            "status": unit.status,
            "seconds": total,
            # Present only when a recorded neural track exists on disk. The player
            # prefers it over browser speech; absent, it narrates in the browser.
            "audio_url": (f"/api/audio/{unit.short_id}"
                          if (config.OUTPUT_DIR / unit.short_id / "audio.mp3").exists()
                          else None),
            "judge": ({"faithfulness": unit.eval.faithfulness,
                       "clarity": unit.eval.clarity,
                       "pace": unit.eval.pace,
                       "problems": unit.eval.problems} if unit.eval else None),
            "diagrams": sum(1 for b in beats if b["svg"]),
            "beats": beats,
        })
    units.sort(key=lambda u: u["section"])
    return units


def build_json(out: Path | None = None) -> Path:
    units = collect()
    if not units:
        raise SystemExit("no units in output/ — run `python -m shorts.run <doc>` first")
    out = out or config.ROOT / "web" / "public" / "shorts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(units, indent=2), encoding="utf-8")
    print(f"wrote {out}  ({len(units)} shorts, {sum(u['diagrams'] for u in units)} diagrams)")
    for u in units:
        j = u["judge"]
        score = f"judge {j['faithfulness']}/{j['clarity']}/{j['pace']}" if j else "no judge"
        print(f"  §{u['section']:4} {u['short_id']:40} {u['status']:9} {u['seconds']:5}s  {score}")
    return out


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    build_json()
    print("serve it with: python -m shorts.server")


if __name__ == "__main__":
    main()
