"""SKILLS 3 & 4 — visual-spec, then diagram-render.

Non-negotiable: technical content becomes code-generated SVG, never an image
model. Image models produce confident nonsense for page tables and flow diagrams.
"""
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
- Only these colours: #1D9E75 (highlight), #0F6E56 (dark teal), #E1F5EE (fill),
  #2C2C2A (text), #8A8880 (muted). Nothing else.
- font-family="Inter, Helvetica, sans-serif". Minimum font-size 34 — this is read
  on a phone at arm's length. Labels under 5 words.
- Maximum 7 shapes. A short's diagram is glanceable, not a textbook figure.
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
    """Fill in .svg for every diagram-type visual. One LLM call per diagram."""
    from ..llm import client
    if config.STUB:
        return visuals                      # stub visuals are all type="text"
    for ref, v in visuals.items():
        if v.type != "diagram":
            continue
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
    return visuals
