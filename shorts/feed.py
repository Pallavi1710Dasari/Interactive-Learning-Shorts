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

# The two statuses that keep a short out of the student-facing reel. Named here
# because collect() is not the only caller that has to reason about them: the
# finalize endpoint has to tell the reviewer that a short it just paid for was
# held back, and it can only do that if "held back" is one shared definition
# rather than a tuple written out twice and drifting.
QUARANTINED = ("needs_review", "rejected")


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
            # Word-by-word timings for the flowing caption. Always present, even
            # with no recorded audio: estimated timings still let the caption
            # reveal itself rather than land as a wall of text.
            "words": _caption_words(beat.line, start, end),
        })
    return spans, round(cursor, 2)


def _caption_words(line: str, start: float, end: float) -> list[dict]:
    """
    Give every word of the line its own start and end, so the caption can flow
    word by word under the voice instead of appearing as a finished block.

    Distributed across the beat's own span, weighted by length. "the" and
    "fragmentation" do not take the same time to say, so an even split makes the
    highlight visibly lag on long words and race on short ones; weighting by
    characters, with a pause added after sentence-ending punctuation, tracks real
    speech closely enough that the eye reads it as synchronised.

    WHY NOT unit.audio.word_timings, WHICH EXIST
    Because they are this same estimate, made worse. Read tts._even_words: no
    provider in providers.py returns real alignments, so those timings are an EVEN
    split — and of the *spoken* text, which speech.conversational has repunctuated,
    so there is often not even one per written word. Lining an even split of a
    different string up against the words on screen is strictly worse than
    weighting the written words across the same measured span. If a provider that
    reports true word alignments is ever added, this is the function that should
    prefer them.

    The span itself is exact whenever there is a recorded track — it comes from the
    measured beat audio — so the words are spread across a real duration even
    though their individual boundaries are estimated.
    """
    words = line.split()
    if not words:
        return []

    span = max(end - start, 0.001)
    weights = []
    for word in words:
        weight = max(len(re.sub(r"[^\w]", "", word)), 1)
        if word.endswith((".", "!", "?")):
            weight += 4          # a full stop is a real pause, not a fast word
        elif word.endswith((",", ";", ":", "—")):
            weight += 2
        weights.append(float(weight))

    total = sum(weights)
    out, cursor = [], start
    for word, weight in zip(words, weights):
        length = span * weight / total
        out.append({"w": word, "s": round(cursor, 3),
                    "e": round(cursor + length, 3)})
        cursor += length
    return out


def _clean_svg(svg: str) -> str:
    """
    The SVG is model-generated and gets injected into the DOM. Nothing upstream is
    an enforcement mechanism, so this is.

    KNOWN COSMETIC EDGE, deliberately not fixed: the handler strip runs over the
    whole string, so a "code" frame drawing HTML markup that itself contains
    `onclick="..."` loses that fragment from the DISPLAYED code as well. No document
    in this project has an inline handler, and the alternative — teaching the regex
    to tell a real attribute from escaped text inside <text> — trades a security
    boundary for the prettiness of a rare frame. Wrong way round.
    """
    svg = re.sub(r"<script.*?</script>", "", svg, flags=re.S | re.I)
    return re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", svg, flags=re.I)


def collect(include_quarantined: bool = False) -> list[dict]:
    """
    Every unit in output/, newest section first, in reel-playable form.

    QUARANTINED UNITS ARE HELD BACK. A short whose judge verdict came in under the
    bar is stored with status "needs_review" and left out of this list, because this
    list is what students watch. Pass include_quarantined=True to see them — that is
    for the reviewer's own listing, not for the reel.
    """
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
        # "rejected" is the CLI path's word for the same thing — run.py sets it when
        # the judge verdict fails — and it was being shown to students too.
        if unit.status in QUARANTINED and not include_quarantined:
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
