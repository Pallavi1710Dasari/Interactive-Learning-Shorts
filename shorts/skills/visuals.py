"""SKILLS 3 & 4 — visual-spec, then diagram-render.

Non-negotiable: technical content becomes code-generated SVG, never an image
model. Image models produce confident nonsense for page tables and flow diagrams.
"""
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel
from ..schema import Script, Visual, Section
from ..llm import ask_json
from .. import config, usage


class VisualPlan(BaseModel):
    visuals: list[Visual]


SPEC_SYSTEM = """You assign a visual to every beat of a short video script.

For each distinct visual_ref in the script, choose a type:
  "diagram" — anything structural or technical: tables, memory layouts, address
              splits, state transitions, request flows, before/after states.
              ALWAYS use this for technical content.
  "image"   — decorative background only. Never carries information. Its spec must
              not name any technical noun (memory, address, page, frame, table,
              cache, bit, queue, stack, tree, flow, architecture, register). If you
              cannot describe it without one, it is not decorative — use "diagram".
              When in doubt, do not choose "image".
  "text"    — a single number or term shown large, no illustration needed.

Then write `spec`: what the visual must show, in one or two sentences, concrete
enough that someone could draw it without seeing the script. Name the labels.

Output JSON: {"visuals":[{"ref":"...","type":"diagram|image|text","spec":"..."}]}"""

SVG_SYSTEM = """You draw a single technical diagram as an SVG for a VERTICAL phone video.

CONSTRAINTS
- viewBox="0 0 1080 1080". Nothing outside those bounds.
- Transparent background. Do not draw a background rect.
- Palette, and nothing outside it:
    #E1F5EE  fill for boxes and panels
    #1D9E75  primary stroke, arrows, headings
    #0F6E56  deeper green for a second grouping
    #F2B14B  AMBER — the one element the narration is about right now. Use it on
             exactly one shape per diagram, never more. This is what the eye finds.
    #E8735A  coral — only for a thing being rejected, lost, or wasted
    #2C2C2A  text on light fills
    #8A8880  muted labels and secondary text
  A diagram drawn in a single colour reads as a wireframe; the amber accent is
  what makes it look designed rather than generated.
- font-family="Inter, Helvetica, sans-serif". Minimum font-size 34 — this is read
  on a phone at arm's length. Labels under 5 words.
- 4 to 9 shapes. Glanceable, not a textbook figure — but do not leave it bare:
  give boxes real labels, and draw the arrow or bracket that carries the idea.
- Use ONE accent: highlight the single element the narration is about right now
  (thicker stroke or the highlight fill), and leave the rest quiet. A diagram
  where everything is emphasised communicates nothing.
- Group related things visually — align them, or enclose them in one rounded
  container — so the structure is readable before the labels are.
- No <style> blocks, no external refs, no <image>, no scripts. Inline attributes only.

ACCURACY BEATS DECORATION. If the narration says the valid bit is clear, the
diagram must show it clear. A wrong diagram is worse than no diagram.

Output the raw <svg>...</svg> only. No fences, no explanation."""


def spec_visuals(script: Script) -> dict[str, Visual]:
    refs = sorted({b.visual_ref for b in script.beats})
    beats = "\n".join(f"[{b.visual_ref}] {b.speaker}: {b.line}" for b in script.beats)
    user = f"QUESTION: {script.question}\n\nBEATS:\n{beats}\n\nAssign a visual to each of: {refs}"
    plan = ask_json(SPEC_SYSTEM, user, VisualPlan, max_tokens=2000, label="visual_spec")
    return {v.ref: v for v in plan.visuals}


def render_diagrams(visuals: dict[str, Visual], script: Script, section: Section) -> dict[str, Visual]:
    """
    Fill in .svg for every diagram-type visual. One LLM call per diagram.

    Drawn concurrently: a short has 4-5 diagrams and each call takes several
    seconds, so doing them in sequence made building a single short the slowest
    thing in the product. The calls are independent, so wall-clock time drops to
    roughly one diagram instead of the sum of all of them.
    """
    if config.STUB:
        return visuals                      # stub visuals are all type="text"

    todo = [(ref, v) for ref, v in visuals.items() if v.type == "diagram"]
    if not todo:
        return visuals
    with ThreadPoolExecutor(max_workers=min(5, len(todo))) as pool:
        list(pool.map(lambda rv: _draw_one(rv[0], rv[1], script, section), todo))
    return visuals


def _draw_one(ref: str, v: Visual, script: Script, section: Section) -> None:
    """Draw one diagram, in place. Never raises — a missing SVG is a grader's job."""
    from ..llm import client
    try:
        narration = " ".join(b.line for b in script.beats if b.visual_ref == ref)
        resp = client().messages.create(
            model=config.MODEL_GENERATOR,
            max_tokens=8000,
            system=SVG_SYSTEM,
            messages=[{"role": "user", "content":
                f"DIAGRAM SPEC: {v.spec}\n\nNARRATION PLAYING OVER IT: {narration}\n\n"
                f"SOURCE OF TRUTH [{section.section_id}]:\n{section.text}"}],
        )
        usage.record("diagram", config.MODEL_GENERATOR, resp)
        svg = "".join(b.text for b in resp.content if b.type == "text").strip()

        # Both tags, not just the opening one. A diagram truncated at max_tokens has
        # "<svg" and no "</svg>", and rindex() then raises mid-pipeline — killing the
        # run for every remaining topic. Leaving .svg as None instead lets
        # check_visuals_resolved report it as a normal grader failure.
        if "<svg" in svg and "</svg>" in svg:
            v.svg = svg[svg.index("<svg"):svg.rindex("</svg>") + 6]
        else:
            reason = "truncated" if resp.stop_reason == "max_tokens" else "no <svg> in output"
            print(f"    ! diagram {ref}: {reason} — leaving it unrendered")
    except Exception as e:
        print(f"    ! diagram {ref}: {type(e).__name__}: {e} — leaving it unrendered")
