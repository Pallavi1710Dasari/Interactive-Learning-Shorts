"""
The style bible — RESTYLE_TO_STORY_REELS.md Step 4.

ONE constant, prepended VERBATIM to every image prompt in the pipeline,
never edited per shot or per character. That is the whole point of having
it: a feed where every frame opens with the identical style paragraph reads
as one studio's work; a feed where each shot's prompt improvises its own
version of "hand-drawn, thick outlines, ..." drifts, frame to frame, in ways
nobody chose on purpose.

Colors are named in PLAIN WORDS ("soft purple", "warm yellow"), not
config.BRAND's own hex codes (STEP 9 FIXES ROUND 14): a real reel came back
with no accent colors anywhere in the output at all, and flux-1-schnell (the
Cloudflare fallback, a fast/cheap model) is the prime suspect — a hex code
sitting in a text prompt is meaningless to a diffusion model's own color
understanding, at best inert filler, at worst a distraction from the actual
instruction. This DOES mean a brand-color .env edit (config.BRAND.accent_1/
accent_2) no longer automatically reflows into the image prompt the way it
used to — the tradeoff was judged worth it against the confirmed no-color
defect. If BRAND ever needs to drive the prompt again, that has to go
through a genuine hex-to-plain-color-name mapping, not the hex string
itself; nothing here does that today.
"""
from . import config

#: Cast sheets (shorts/cast_sheets.py) are landscape — the one place Step 4
#: says to override the 9:16 rule. Everything else in STYLE_BIBLE (outlines,
#: colors, no-text rule) still applies to a sheet; only the composition line
#: changes.
_PORTRAIT_COMPOSITION = (
    "Vertical 9:16 composition, subject centered in the middle 60% of the "
    "frame; keep the top 12% and bottom 18% empty for overlays. The "
    "illustration must fill the ENTIRE frame edge-to-edge — no border, no "
    "letterboxing, no blank margin or bars down the left or right side.")
_LANDSCAPE_COMPOSITION = (
    "Horizontal composition (this is a character reference sheet, not a shot), "
    "views evenly spaced left to right across the frame.")


def style_bible(landscape: bool = False) -> str:
    """
    The style bible, with the one line that's allowed to differ — the
    composition rule — swapped for landscape (cast sheets only). Everything
    else is the fixed paragraph every image prompt in this project opens
    with; if you are tempted to add a per-shot variant of any OTHER line,
    that is the mistake this function exists to make harder, not easier.
    """
    composition = _LANDSCAPE_COMPOSITION if landscape else _PORTRAIT_COMPOSITION
    return (
        "Hand-drawn stick figure illustration. Thick clean black outlines, "
        "LARGE, EXAGGERATED round white heads (roughly a third of the "
        "character's total height, clearly bigger than a realistic head), "
        "big expressive eyes and eyebrows, simple line bodies. Off-white "
        "paper background, minimal environment, soft shadows. Accent "
        "colors only soft purple and warm yellow — no other colors "
        "anywhere in the image. The key object glows softly in yellow. "
        "Clean flat 2D, no gradients on characters, no photorealism, no 3D.\n"
        f"{composition}\n"
        "ABSOLUTELY NO TEXT, LETTERS, NUMBERS, LOGOS OR SPEECH BUBBLES in the "
        "image unless listed under ALLOWED GLYPHS."
    )


#: The default (portrait, every ordinary shot) style bible — a plain string
#: constant, computed once at import, for callers that just want to prepend
#: it and don't need the landscape variant. `style_bible(landscape=True)` is
#: still the one to call from cast_sheets.py.
STYLE_BIBLE = style_bible(landscape=False)


def mascot_prompt() -> str:
    """
    The CTA screen's fixed mascot beat — Rahul, config.MASCOT_POSE, against
    the ordinary (portrait) style bible; a shot, not a sheet, so it uses
    STYLE_BIBLE as-is, no landscape override.

    ONE prompt, computed the same way every time it's asked for — Step 5's
    own "generated once and cached" rule for the mascot relies on that: the
    cache key is content-addressed on the prompt text, so calling this twice
    for two different reels' cta shots produces the identical prompt and
    therefore the identical cache key, and the second reel's mascot image is
    a cache hit rather than a second paid call.
    """
    return (f"{STYLE_BIBLE}\n\nCharacter: Rahul. Look: {config.CAST_LOOK['Rahul']}, "
           f"matching reference image 1.\nPOSE: {config.MASCOT_POSE}.\n"
           f"ALLOWED GLYPHS: none.")
