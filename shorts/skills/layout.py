"""
SKILL 4 — turning a Frame into an SVG, in code.

THE POINT OF THIS FILE
Nothing here asks a model anything. A Frame says what the diagram contains; this
computes where every mark goes. That division is the fix for the one defect these
shorts could not shake: overlapping labels.

Drawing SVG by hand means doing layout arithmetic blind — does a 27-character
label fit inside a 200px box, is there clear space between these two <text>
elements — and a language model cannot see what it drew. Three redraw attempts
guided by checks.svg_problems reduced the overlaps and never eliminated them, on
every model tried, and _draw_one kept the frame regardless, so broken frames
shipped anyway. Prompting harder was never going to close it.

TWO RULES MAKE OVERLAP IMPOSSIBLE, AND EVERY TEMPLATE OBEYS THEM
  1. Text is only ever drawn inside a rectangle reserved for it, and it is FITTED
     to that rectangle first — shrunk, wrapped, and finally truncated (see fit()).
  2. Reserved rectangles are disjoint by construction. Bands are carved out of the
     canvas up front; a label that will not fit inside its box goes into a band
     that holds at most one label, never "just below", never "in the gap".

So the failure mode becomes an ugly frame — a truncated label, a smaller type size
— instead of an unreadable one. That trade is the whole design.

The renderers also emit the animation tags the player drives (data-enter for
arrival order, data-role="focus" on the hero, data-role="flow" on arrows), which
the model used to have to remember to add. See web/src/AnimatedSvg.tsx.
"""
import re

from ..schema import Frame, Cell, TableRow, Panel, Sample, Glyph

VIEW = 1080
MARGIN = 60
USABLE = VIEW - 2 * MARGIN               # 960

# Bands, carved up front and never overlapping. Everything below is placed inside
# one of these, which is what makes "disjoint by construction" true rather than
# aspirational.
TITLE_TOP, TITLE_BOTTOM = 60, 200
BODY_TOP, BODY_BOTTOM = 230, 820
NOTE_TOP, NOTE_BOTTOM = 850, 950

#: Advance width of Inter as a fraction of font-size. The same constant
#: checks.CHAR_WIDTH_RATIO measures with, deliberately: the renderer and the grader
#: must agree about how wide text is, or the grader flags frames the renderer
#: believes are fine.
CHAR_W = 0.55

#: Advance width of a monospace face, which is the whole point of one: every glyph
#: is this wide, so a code block can be laid out at ONE size for every line and the
#: indentation lines up. Wider than Inter, so a snippet needs measuring separately.
CHAR_W_MONO = 0.60

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# The palette. checks and SVG_SYSTEM describe it; here it is the only thing that
# assigns it, which is why a short cannot end up with three amber elements.
FILL = "#E1F5EE"
STROKE = "#1D9E75"
DEEP = "#0F6E56"
AMBER = "#F2B14B"
CORAL = "#E8735A"
INK = "#2C2C2A"
MUTED = "#8A8880"
PAPER = "#F4F5F3"

#: fill, stroke, ink for each role.
ROLE_COLOURS: dict[str, tuple[str, str, str]] = {
    "plain": (FILL, STROKE, INK),
    "hero":  (AMBER, DEEP, INK),
    "lost":  ("#FBE3DE", CORAL, INK),
    "quiet": (PAPER, MUTED, MUTED),
}

#: Ink for text drawn ON the dark code panel. The role colours above are ink for
#: text inside a LIGHT box, so reusing them there would print near-black on
#: near-black. Same roles, inverted ground.
CODE_INK: dict[str, str] = {
    "plain": FILL,
    "hero":  AMBER,
    "lost":  CORAL,
    "quiet": MUTED,
}

#: Hard caps. Past these a frame is not a diagram, it is a spreadsheet — and the
#: renderer would have to shrink type below legibility to fit it.
MAX_CELLS = 10
MAX_COLUMN = 4
MAX_PARTS = 3
MAX_STEPS = 4
MAX_ROWS = 4
MAX_CODE_LINES = 7
MAX_PANELS = 2
MAX_PANEL_ITEMS = 4


# --------------------------------------------------------------------- text

def esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def wrap(text: str, max_chars: int) -> list[str]:
    """Greedy word wrap. A word longer than the line is hard-split, not overflowed."""
    words, lines, line = str(text).split(), [], ""
    for word in words:
        while len(word) > max_chars:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{line} {word}".strip()
        if len(candidate) <= max_chars:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def fit(text: str, width: float, hi: int, lo: int, max_lines: int = 2) -> tuple[list[str], int]:
    """
    The largest size at which `text` fits in `width` across at most `max_lines`.

    Steps down through sizes rather than solving for one, because wrapping is
    discrete: 18 characters might need two lines at 44px and one at 40px, and the
    line count is what decides whether the label clears its box.

    If nothing fits even at `lo`, the text is TRUNCATED with an ellipsis. That is
    deliberate and it is the last line of defence: a clipped label is a frame that
    reads as slightly wrong, while an overflowing one is a frame that reads as
    broken and takes its neighbours down with it.
    """
    text = str(text).strip()
    if not text:
        return [], lo
    for size in range(hi, lo - 1, -2):
        limit = max(1, int(width / (size * CHAR_W)))
        lines = wrap(text, limit)
        if len(lines) <= max_lines:
            return lines, size
    limit = max(1, int(width / (lo * CHAR_W)))
    lines = wrap(text, limit)[:max_lines]
    if lines and len(wrap(text, limit)) > max_lines:
        lines[-1] = lines[-1][: max(1, limit - 1)] + "…"
    return lines, lo


def fit_unbroken(text: str, width: float, hi: int, lo: int,
                 max_lines: int = 2) -> tuple[list[str], int] | None:
    """
    Like fit(), but returns None rather than breaking a word.

    fit() hard-splits any word too long for the line, which is the right last
    resort when there is nowhere else to put the text — it keeps the label inside
    its box instead of overflowing into the next one. In a narrow cell it is the
    wrong answer: at 96px a cell renders "Frame 0" as "Fram" / "e 0" and "Process"
    as "Proc" / "ess". That scores zero problems from the checker — it is neither an
    overflow nor a collision — and reads as broken text, which is worse than no text.

    So callers that HAVE somewhere else to put a label ask for this first, and fall
    back to that somewhere else when it returns None.
    """
    text = str(text).strip()
    if not text:
        return [], lo
    longest = max((len(w) for w in text.split()), default=0)
    for size in range(hi, lo - 1, -2):
        limit = max(1, int(width / (size * CHAR_W)))
        if longest > limit:
            continue                      # a word would have to be cut
        lines = wrap(text, limit)
        if len(lines) <= max_lines:
            return lines, size
    return None


def text_block(lines: list[str], cx: float, cy: float, size: int, fill: str = INK,
               weight: int = 600, anchor: str = "middle") -> str:
    """
    Lines centred vertically on cy, at `size`, one <text> each.

    One element per line and never a newline inside a <text>: SVG does not break
    lines, so a multi-line string renders as one long one running off the canvas.
    """
    if not lines:
        return ""
    step = size * 1.18
    top = cy - (len(lines) - 1) * step / 2
    out = []
    for i, line in enumerate(lines):
        y = top + i * step + size * 0.35
        out.append(
            f'<text x="{cx:.0f}" y="{y:.0f}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{esc(line)}</text>'
        )
    return "".join(out)


def label_in_box(label: str, x: float, y: float, w: float, h: float,
                 role: str, hi: int = 44, lo: int = 24) -> str:
    """A label fitted to the inside of its own box, with real padding."""
    if not label:
        return ""
    _, _, ink = ROLE_COLOURS[role]
    pad = 14
    lines, size = fit(label, w - 2 * pad, hi, lo, max_lines=2)
    # Two lines need 2.36 x size of height; drop to one and shrink if they do not fit.
    if len(lines) == 2 and 2.36 * size > h - 8:
        lines, size = fit(label, w - 2 * pad, min(hi, int((h - 8) / 1.2)), lo, max_lines=1)
    return text_block(lines, x + w / 2, y + h / 2, size, ink, 700)


def box(x: float, y: float, w: float, h: float, role: str, rx: int = 14,
        dashed: bool = False) -> str:
    fill, stroke, _ = ROLE_COLOURS[role]
    dash = ' stroke-dasharray="12 10"' if dashed else ""
    return (f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="5"{dash}/>')


def arrow(x1: float, y1: float, x2: float, y2: float, role: str = "flow") -> str:
    """A straight arrow with a solid head. Horizontal or vertical only."""
    head = 22
    if abs(y2 - y1) < 1:                                  # horizontal
        tip = x2
        shaft = f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{tip - head:.0f}" y2="{y1:.0f}"'
        pts = f"{tip},{y1} {tip - head},{y1 - head * 0.5} {tip - head},{y1 + head * 0.5}"
    else:                                                 # vertical
        tip = y2
        shaft = f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x1:.0f}" y2="{tip - head:.0f}"'
        pts = f"{x1},{tip} {x1 - head * 0.5},{tip - head} {x1 + head * 0.5},{tip - head}"
    tag = f' data-role="{role}"' if role else ""
    return (f'<g{tag}>{shaft} stroke="{STROKE}" stroke-width="7"/>'
            f'<polygon points="{pts}" fill="{STROKE}"/></g>')


def group(body: str, enter: int, role: str | None = None) -> str:
    """
    One arrival step for the player's build animation.

    A shape and its own label are always in the same group, because a box that
    fades in while its label waits its turn looks broken. See AnimatedSvg.tsx.
    """
    attrs = f' data-enter="{enter}"'
    if role:
        attrs += f' data-role="{role}"'
    return f"<g{attrs}>{body}</g>"


def band_text(text: str | None, top: float, bottom: float, hi: int, lo: int,
              fill: str = INK, weight: int = 600, enter: int = 1) -> str:
    """
    Text filling a reserved band, and nothing else may be drawn in that band.

    This is the mechanism behind rule 2 in the module docstring: a label that will
    not fit inside its box goes into a band that holds exactly one label. There is
    no "place it in the gap" path anywhere in this file, which is why there is no
    label-over-box failure to grade.
    """
    if not text:
        return ""
    height = bottom - top
    lines, size = fit(text, USABLE, hi, lo, max_lines=max(1, int(height / (hi * 1.2))))
    return group(text_block(lines, VIEW / 2, (top + bottom) / 2, size, fill, weight), enter)


# --------------------------------------------------------------- the templates

def _bar(frame: Frame, enter: int) -> tuple[str, int]:
    """A row of equal cells. Memory, frames, a timeline — anything countable."""
    cells = (frame.cells or [Cell()])[:MAX_CELLS]
    n = len(cells)
    cell_w = USABLE / n
    height = 170
    top = (BODY_TOP + BODY_BOTTOM) / 2 - height / 2

    # The row caption gets its own strip above the bar. Reserved, so nothing else
    # is ever placed there.
    out = ""
    if frame.cells_title:
        lines, size = fit(frame.cells_title, USABLE, 40, 30, max_lines=1)
        out += group(text_block(lines, VIEW / 2, top - 46, size, MUTED, 600), enter)
        enter += 1

    # A cell's label goes inside the cell only if it fits there WITHOUT breaking a
    # word. At 10 cells a cell is 96px, which holds "F0" and not "Frame 0", and a
    # label chopped to "Fram" / "e 0" is worse than no label — it is unreadable in a
    # way no grader catches, because it is neither an overflow nor a collision.
    #
    # A label that does not fit is therefore dropped from its cell, and if it is the
    # hero's it is printed once in the strip below the bar instead. Exactly one
    # label goes in that strip, so nothing there can collide with anything. A wide
    # bar of unlabelled cells with one label under the amber one is also simply what
    # a ten-cell bar should look like.
    spill: str | None = None
    body = ""
    for i, cell in enumerate(cells):
        x = MARGIN + i * cell_w
        body += box(x, top, cell_w, height, cell.role, rx=10)
        if not cell.label:
            continue
        fitted = fit_unbroken(cell.label, cell_w - 20, 40, 22, max_lines=2)
        if fitted is None:
            if cell.role == "hero" and spill is None:
                spill = cell.label
            continue
        lines, size = fitted
        _, _, ink = ROLE_COLOURS[cell.role]
        body += text_block(lines, x + cell_w / 2, top + height / 2, size, ink, 700)

    hero = next((i for i, c in enumerate(cells) if c.role == "hero"), None)
    out += group(body, enter, "focus" if hero is not None else None)
    enter += 1

    if spill:
        # Full canvas width here, so a word only breaks if it is genuinely enormous.
        fitted = fit_unbroken(spill, USABLE, 44, 28, max_lines=1) \
            or fit(spill, USABLE, 44, 28, max_lines=1)
        lines, size = fitted
        out += group(text_block(lines, VIEW / 2, top + height + 60, size, INK, 700), enter)
        enter += 1
    return out, enter


def _mapping(frame: Frame, enter: int) -> tuple[str, int]:
    """
    Two columns and arrows. Pages to frames, logical to physical.

    THE COLUMNS SHARE ONE ROW GRID, AND THAT IS THE FIX FOR DANGLING ARROWS.
    Each column used to size its own boxes from its own item count, so a 2-item
    left column and a 4-item right column had boxes of different heights at
    different heights — nothing lined up. The arrows were then drawn at
    max(left, right) evenly spaced positions, which matched neither column, so two
    of the four arrows started in empty space and pointed at a box nothing was
    mapped to. On screen it read as a diagram with pieces missing.

    So the grid is computed once from the longer column and both sides place their
    boxes in it, and an arrow is drawn ONLY on a row where both sides actually have
    a box. Unequal columns now render as unequal columns — which is honest — rather
    than as arrows from nowhere. SPEC_SYSTEM asks for equal columns, and this is
    what happens when it does not get them.
    """
    left = (frame.left or [Cell()])[:MAX_COLUMN]
    right = (frame.right or [Cell()])[:MAX_COLUMN]
    col_w = 360
    left_x = MARGIN
    right_x = VIEW - MARGIN - col_w
    gutter_x0 = left_x + col_w
    gutter_x1 = right_x

    # One grid, from the longer column. Reserve the top strip for column titles.
    rows = max(len(left), len(right))
    gap = 26
    title_h = 56
    avail = BODY_BOTTOM - BODY_TOP - title_h
    row_h = min(150, (avail - (rows - 1) * gap) / rows)
    total = rows * row_h + (rows - 1) * gap
    top = BODY_TOP + title_h + (avail - total) / 2

    def row_y(i: int) -> float:
        return top + i * (row_h + gap)

    out = ""
    for items, x, title in ((left, left_x, frame.left_title),
                            (right, right_x, frame.right_title)):
        if title:
            lines, size = fit(title, col_w, 38, 28, max_lines=1)
            out += group(text_block(lines, x + col_w / 2, BODY_TOP + 22, size, MUTED, 600),
                         enter)
            enter += 1
        for i, cell in enumerate(items):
            y = row_y(i)
            out += group(box(x, y, col_w, row_h, cell.role)
                         + label_in_box(cell.label, x, y, col_w, row_h, cell.role),
                         enter, "focus" if cell.role == "hero" else None)
            enter += 1

    # An arrow only where there is something at both ends of it.
    paired = min(len(left), len(right))
    if paired:
        arrows = "".join(
            arrow(gutter_x0 + 16, row_y(i) + row_h / 2, gutter_x1 - 8, row_y(i) + row_h / 2,
                  role="")
            for i in range(paired))
        out += group(arrows, enter, "flow")
        enter += 1
    return out, enter


def _split(frame: Frame, enter: int) -> tuple[str, int]:
    """One wide bar cut into named parts. An address into page number and offset."""
    parts = (frame.parts or [Cell()])[:MAX_PARTS]
    n = len(parts)
    height = 200
    top = (BODY_TOP + BODY_BOTTOM) / 2 - height / 2
    part_w = USABLE / n

    body = ""
    for i, part in enumerate(parts):
        x = MARGIN + i * part_w
        body += box(x, top, part_w, height, part.role, rx=0 if 0 < i < n - 1 else 16)
        # At 3 parts each is 320px, so labels fit inside at a real size.
        body += label_in_box(part.label, x, top, part_w, height, part.role, hi=52, lo=28)
    hero = any(p.role == "hero" for p in parts)
    out = group(body, enter, "focus" if hero else None)
    return out, enter + 1


def _flow(frame: Frame, enter: int) -> tuple[str, int]:
    """Steps top to bottom with arrows. A page fault, a request path."""
    steps = (frame.steps or [Cell()])[:MAX_STEPS]
    n = len(steps)
    width = 640
    x = (VIEW - width) / 2
    gap = 58
    avail = BODY_BOTTOM - BODY_TOP
    h = min(150, (avail - (n - 1) * gap) / n)
    total = n * h + (n - 1) * gap
    top = BODY_TOP + (avail - total) / 2

    out = ""
    for i, step in enumerate(steps):
        y = top + i * (h + gap)
        out += group(box(x, y, width, h, step.role)
                     + label_in_box(step.label, x, y, width, h, step.role, hi=46, lo=26),
                     enter, "focus" if step.role == "hero" else None)
        enter += 1
        if i < n - 1:
            # The arrow sits in the gap and nothing else is ever placed there.
            out += group(arrow(VIEW / 2, y + h + 10, VIEW / 2, y + h + gap - 6, role=""),
                         enter, "flow")
            enter += 1
    return out, enter


def _table(frame: Frame, enter: int) -> tuple[str, int]:
    """A header row and rows, one of them the hero. Page tables, comparisons."""
    columns = frame.columns[:3] or ["", ""]
    rows = (frame.rows or [TableRow(cells=[""] * len(columns))])[:MAX_ROWS]
    cols = len(columns)
    col_w = USABLE / cols
    head_h = 84
    gap = 12
    avail = BODY_BOTTOM - BODY_TOP - head_h - gap
    row_h = min(130, (avail - (len(rows) - 1) * gap) / len(rows))
    total = head_h + gap + len(rows) * row_h + (len(rows) - 1) * gap
    top = BODY_TOP + (BODY_BOTTOM - BODY_TOP - total) / 2

    head = ""
    for i, name in enumerate(columns):
        x = MARGIN + i * col_w
        lines, size = fit(name, col_w - 20, 38, 26, max_lines=1)
        head += text_block(lines, x + col_w / 2, top + head_h / 2, size, MUTED, 700)
    out = group(head, enter)
    enter += 1

    y = top + head_h + gap
    for row in rows:
        body = ""
        for i in range(cols):
            x = MARGIN + i * col_w
            body += box(x, y, col_w, row_h, row.role, rx=0)
            value = row.cells[i] if i < len(row.cells) else ""
            body += label_in_box(value, x, y, col_w, row_h, row.role, hi=42, lo=24)
        out += group(body, enter, "focus" if row.role == "hero" else None)
        enter += 1
        y += row_h + gap
    return out, enter


def _stat(frame: Frame, enter: int) -> tuple[str, int]:
    """One number or term, as large as it will go, with a caption beneath it."""
    value = frame.value or frame.title or ""
    mid = (BODY_TOP + BODY_BOTTOM) / 2
    lines, size = fit(value, USABLE, 190, 60, max_lines=2)
    out = group(text_block(lines, VIEW / 2, mid - 40, size, INK, 700), enter, "focus")
    enter += 1
    if frame.caption:
        lines, size = fit(frame.caption, USABLE, 48, 32, max_lines=2)
        out += group(text_block(lines, VIEW / 2, mid + 150, size, MUTED, 600), enter)
        enter += 1
    return out, enter


def _takeaway(frame: Frame, enter: int) -> tuple[str, int]:
    """The last frame. One sentence, set large, nothing else competing with it."""
    statement = frame.caption or frame.value or frame.note or frame.title or ""
    mid = (BODY_TOP + BODY_BOTTOM) / 2
    lines, size = fit(statement, USABLE - 40, 84, 44, max_lines=4)
    rule = (f'<line x1="{VIEW / 2 - 90:.0f}" y1="{BODY_TOP + 10:.0f}" '
            f'x2="{VIEW / 2 + 90:.0f}" y2="{BODY_TOP + 10:.0f}" '
            f'stroke="{AMBER}" stroke-width="9"/>')
    out = group(rule, enter, "focus")
    out += group(text_block(lines, VIEW / 2, mid + 10, size, INK, 700), enter + 1)
    return out, enter + 2


# ------------------------------------------------------------------ pictograms
#
# DRAWN THINGS, which is the point. Every other template on this list communicates
# with a rounded rectangle holding a word, and a viewer told "the visuals are just
# text" is not wrong about that: a box saying "Browser" is the word "browser" with a
# border. A drawn browser window is a picture, read at a glance and in any language.
#
# Deliberately built from primitives — rect, circle, line, a short path — rather
# than lifted from an icon set. They have to sit in the project's palette, take a
# role colour, scale to whatever box the layout gives them, and stay legible at
# phone size; a 24px-grid icon path does none of that when blown up to 200px. These
# are simple on purpose: at this size and this duration, recognisable beats detailed.
#
# Each takes a UNIT BOX and returns markup filling it. The layout owns position and
# size; a pictogram only knows how to draw itself inside the square it is handed.


def _pict_browser(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A window with a title bar and three dots. Anything to do with a browser."""
    bar = s * 0.22
    return (f'<rect x="{x}" y="{y}" width="{s}" height="{s * 0.82}" rx="{s * 0.07}" '
            f'fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
            f'<line x1="{x}" y1="{y + bar}" x2="{x + s}" y2="{y + bar}" '
            f'stroke="{ink}" stroke-width="{s * 0.045}"/>'
            + "".join(f'<circle cx="{x + s * (0.14 + i * 0.13):.1f}" '
                      f'cy="{y + bar / 2:.1f}" r="{s * 0.035}" fill="{ink}"/>'
                      for i in range(3))
            + f'<rect x="{x + s * 0.12}" y="{y + bar + s * 0.14}" width="{s * 0.5}" '
              f'height="{s * 0.09}" rx="{s * 0.03}" fill="{accent}"/>'
              f'<rect x="{x + s * 0.12}" y="{y + bar + s * 0.32}" width="{s * 0.72}" '
              f'height="{s * 0.06}" rx="{s * 0.02}" fill="{ink}" opacity="0.4"/>')


def _pict_file(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A page with a folded corner. A file, a document, a stylesheet."""
    w, h, fold = s * 0.74, s * 0.92, s * 0.24
    left = x + (s - w) / 2
    return (f'<path d="M{left} {y + h} L{left} {y} L{left + w - fold} {y} '
            f'L{left + w} {y + fold} L{left + w} {y + h} Z" fill="none" '
            f'stroke="{ink}" stroke-width="{s * 0.055}" stroke-linejoin="round"/>'
            f'<path d="M{left + w - fold} {y} L{left + w - fold} {y + fold} '
            f'L{left + w} {y + fold}" fill="none" stroke="{ink}" '
            f'stroke-width="{s * 0.045}" stroke-linejoin="round"/>'
            + "".join(f'<line x1="{left + w * 0.16:.1f}" '
                      f'y1="{y + h * (0.52 + i * 0.15):.1f}" '
                      f'x2="{left + w * 0.84:.1f}" '
                      f'y2="{y + h * (0.52 + i * 0.15):.1f}" stroke="{accent if i == 0 else ink}" '
                      f'stroke-width="{s * 0.045}" opacity="{1 if i == 0 else 0.45}"/>'
                      for i in range(3)))


def _pict_page(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A rendered page: a heading bar and body lines. Structure, content, layout."""
    w, h = s * 0.82, s * 0.92
    left = x + (s - w) / 2
    out = (f'<rect x="{left}" y="{y}" width="{w}" height="{h}" rx="{s * 0.05}" '
           f'fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
           f'<rect x="{left + w * 0.1}" y="{y + h * 0.12}" width="{w * 0.55}" '
           f'height="{h * 0.13}" rx="{s * 0.025}" fill="{accent}"/>')
    for i in range(3):
        out += (f'<line x1="{left + w * 0.1:.1f}" y1="{y + h * (0.42 + i * 0.16):.1f}" '
                f'x2="{left + w * (0.9 if i < 2 else 0.62):.1f}" '
                f'y2="{y + h * (0.42 + i * 0.16):.1f}" stroke="{ink}" '
                f'stroke-width="{s * 0.04}" opacity="0.45"/>')
    return out


def _pict_screen(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A monitor on a stand. What the user actually sees."""
    h = s * 0.66
    return (f'<rect x="{x}" y="{y}" width="{s}" height="{h}" rx="{s * 0.06}" '
            f'fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
            f'<rect x="{x + s * 0.16}" y="{y + h * 0.24}" width="{s * 0.44}" '
            f'height="{h * 0.16}" rx="{s * 0.02}" fill="{accent}"/>'
            f'<line x1="{x + s * 0.5}" y1="{y + h}" x2="{x + s * 0.5}" '
            f'y2="{y + s * 0.86}" stroke="{ink}" stroke-width="{s * 0.055}"/>'
            f'<line x1="{x + s * 0.28}" y1="{y + s * 0.88}" x2="{x + s * 0.72}" '
            f'y2="{y + s * 0.88}" stroke="{ink}" stroke-width="{s * 0.055}" '
            f'stroke-linecap="round"/>')


def _pict_chip(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A chip with pins. A CPU, an MMU, anything that computes."""
    b, w = s * 0.2, s * 0.62
    out = (f'<rect x="{x + b}" y="{y + b}" width="{w}" height="{w}" rx="{s * 0.06}" '
           f'fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
           f'<rect x="{x + b + w * 0.26}" y="{y + b + w * 0.26}" width="{w * 0.48}" '
           f'height="{w * 0.48}" rx="{s * 0.03}" fill="{accent}"/>')
    for i in range(3):
        at = b + w * (0.24 + i * 0.26)
        out += (f'<line x1="{x + at:.1f}" y1="{y + b:.1f}" x2="{x + at:.1f}" '
                f'y2="{y:.1f}" stroke="{ink}" stroke-width="{s * 0.045}"/>'
                f'<line x1="{x + at:.1f}" y1="{y + b + w:.1f}" x2="{x + at:.1f}" '
                f'y2="{y + b + w + b:.1f}" stroke="{ink}" stroke-width="{s * 0.045}"/>'
                f'<line x1="{x + b:.1f}" y1="{y + at:.1f}" x2="{x:.1f}" '
                f'y2="{y + at:.1f}" stroke="{ink}" stroke-width="{s * 0.045}"/>'
                f'<line x1="{x + b + w:.1f}" y1="{y + at:.1f}" '
                f'x2="{x + b + w + b:.1f}" y2="{y + at:.1f}" stroke="{ink}" '
                f'stroke-width="{s * 0.045}"/>')
    return out


def _pict_memory(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A stack of equal bars. RAM, frames, slots."""
    out = ""
    for i in range(4):
        h = s * 0.17
        out += (f'<rect x="{x}" y="{y + i * s * 0.24:.1f}" width="{s}" height="{h}" '
                f'rx="{s * 0.03}" fill="{accent if i == 1 else "none"}" stroke="{ink}" '
                f'stroke-width="{s * 0.05}"/>')
    return out


def _pict_disk(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A cylinder. Disk, backing store, swap."""
    w, ry = s * 0.86, s * 0.15
    left, top = x + (s - w) / 2, y + s * 0.1
    bot = y + s * 0.74
    return (f'<ellipse cx="{left + w / 2}" cy="{top}" rx="{w / 2}" ry="{ry}" '
            f'fill="{accent}" stroke="{ink}" stroke-width="{s * 0.05}"/>'
            f'<path d="M{left} {top} L{left} {bot}" stroke="{ink}" '
            f'stroke-width="{s * 0.05}" fill="none"/>'
            f'<path d="M{left + w} {top} L{left + w} {bot}" stroke="{ink}" '
            f'stroke-width="{s * 0.05}" fill="none"/>'
            f'<ellipse cx="{left + w / 2}" cy="{bot}" rx="{w / 2}" ry="{ry}" '
            f'fill="none" stroke="{ink}" stroke-width="{s * 0.05}"/>')


def _pict_brush(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A brush. Styling, appearance, CSS as opposed to structure."""
    return (f'<rect x="{x + s * 0.34}" y="{y + s * 0.04}" width="{s * 0.32}" '
            f'height="{s * 0.34}" rx="{s * 0.05}" fill="none" stroke="{ink}" '
            f'stroke-width="{s * 0.055}"/>'
            f'<rect x="{x + s * 0.28}" y="{y + s * 0.38}" width="{s * 0.44}" '
            f'height="{s * 0.14}" rx="{s * 0.04}" fill="{accent}" stroke="{ink}" '
            f'stroke-width="{s * 0.05}"/>'
            f'<path d="M{x + s * 0.42} {y + s * 0.52} L{x + s * 0.42} {y + s * 0.76} '
            f'Q{x + s * 0.5} {y + s * 0.94} {x + s * 0.58} {y + s * 0.76} '
            f'L{x + s * 0.58} {y + s * 0.52}" fill="none" stroke="{ink}" '
            f'stroke-width="{s * 0.055}" stroke-linejoin="round"/>')


def _pict_code(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """Angle brackets. Markup, a tag, source."""
    return (f'<rect x="{x}" y="{y + s * 0.06}" width="{s}" height="{s * 0.78}" '
            f'rx="{s * 0.07}" fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
            f'<path d="M{x + s * 0.34} {y + s * 0.3} L{x + s * 0.2} {y + s * 0.45} '
            f'L{x + s * 0.34} {y + s * 0.6}" fill="none" stroke="{accent}" '
            f'stroke-width="{s * 0.06}" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<path d="M{x + s * 0.66} {y + s * 0.3} L{x + s * 0.8} {y + s * 0.45} '
            f'L{x + s * 0.66} {y + s * 0.6}" fill="none" stroke="{accent}" '
            f'stroke-width="{s * 0.06}" stroke-linejoin="round" stroke-linecap="round"/>')


def _pict_text(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A capital A. Type, a font, text itself."""
    return (f'<path d="M{x + s * 0.16} {y + s * 0.84} L{x + s * 0.5} {y + s * 0.06} '
            f'L{x + s * 0.84} {y + s * 0.84}" fill="none" stroke="{ink}" '
            f'stroke-width="{s * 0.09}" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<line x1="{x + s * 0.32}" y1="{y + s * 0.58}" x2="{x + s * 0.68}" '
            f'y2="{y + s * 0.58}" stroke="{accent}" stroke-width="{s * 0.09}" '
            f'stroke-linecap="round"/>')


def _pict_table(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A grid. A table, a lookup, a page table."""
    out = (f'<rect x="{x}" y="{y + s * 0.06}" width="{s}" height="{s * 0.78}" '
           f'rx="{s * 0.05}" fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
           f'<rect x="{x}" y="{y + s * 0.06}" width="{s}" height="{s * 0.2}" '
           f'fill="{accent}" opacity="0.9"/>')
    for i in (1, 2):
        out += (f'<line x1="{x}" y1="{y + s * (0.06 + i * 0.26):.1f}" x2="{x + s}" '
                f'y2="{y + s * (0.06 + i * 0.26):.1f}" stroke="{ink}" '
                f'stroke-width="{s * 0.045}"/>')
    out += (f'<line x1="{x + s * 0.5}" y1="{y + s * 0.06}" x2="{x + s * 0.5}" '
            f'y2="{y + s * 0.84}" stroke="{ink}" stroke-width="{s * 0.045}"/>')
    return out


def _pict_check(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A tick in a circle. Right, valid, allowed."""
    return (f'<circle cx="{x + s * 0.5}" cy="{y + s * 0.45}" r="{s * 0.39}" '
            f'fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
            f'<path d="M{x + s * 0.3} {y + s * 0.46} L{x + s * 0.44} {y + s * 0.6} '
            f'L{x + s * 0.71} {y + s * 0.3}" fill="none" stroke="{accent}" '
            f'stroke-width="{s * 0.085}" stroke-linejoin="round" stroke-linecap="round"/>')


def _pict_cross(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A cross in a circle. Wrong, invalid, rejected."""
    return (f'<circle cx="{x + s * 0.5}" cy="{y + s * 0.45}" r="{s * 0.39}" '
            f'fill="none" stroke="{ink}" stroke-width="{s * 0.055}"/>'
            f'<line x1="{x + s * 0.33}" y1="{y + s * 0.28}" x2="{x + s * 0.67}" '
            f'y2="{y + s * 0.62}" stroke="{accent}" stroke-width="{s * 0.085}" '
            f'stroke-linecap="round"/>'
            f'<line x1="{x + s * 0.67}" y1="{y + s * 0.28}" x2="{x + s * 0.33}" '
            f'y2="{y + s * 0.62}" stroke="{accent}" stroke-width="{s * 0.085}" '
            f'stroke-linecap="round"/>')


def _pict_warning(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """A triangle with a bang. A caveat, a mistake, a gotcha."""
    return (f'<path d="M{x + s * 0.5} {y + s * 0.06} L{x + s * 0.95} {y + s * 0.82} '
            f'L{x + s * 0.05} {y + s * 0.82} Z" fill="{accent}" stroke="{ink}" '
            f'stroke-width="{s * 0.055}" stroke-linejoin="round"/>'
            f'<line x1="{x + s * 0.5}" y1="{y + s * 0.34}" x2="{x + s * 0.5}" '
            f'y2="{y + s * 0.58}" stroke="{ink}" stroke-width="{s * 0.07}" '
            f'stroke-linecap="round"/>'
            f'<circle cx="{x + s * 0.5}" cy="{y + s * 0.7}" r="{s * 0.045}" fill="{ink}"/>')


def _pict_box(x: float, y: float, s: float, ink: str, accent: str) -> str:
    """The fallback, for an icon name the renderer does not know."""
    return (f'<rect x="{x + s * 0.08}" y="{y + s * 0.14}" width="{s * 0.84}" '
            f'height="{s * 0.62}" rx="{s * 0.07}" fill="none" stroke="{ink}" '
            f'stroke-width="{s * 0.055}"/>'
            f'<circle cx="{x + s * 0.5}" cy="{y + s * 0.45}" r="{s * 0.1}" fill="{accent}"/>')


#: Every pictogram an `icons` frame may name. Keep this list and the one in
#: SPEC_SYSTEM in step: a name the model invents renders as _pict_box, which is
#: honest but says nothing.
PICTOGRAMS = {
    "browser": _pict_browser, "file": _pict_file, "page": _pict_page,
    "screen": _pict_screen, "chip": _pict_chip, "memory": _pict_memory,
    "disk": _pict_disk, "brush": _pict_brush, "code": _pict_code,
    "text": _pict_text, "table": _pict_table, "check": _pict_check,
    "cross": _pict_cross, "warning": _pict_warning, "box": _pict_box,
}


def _icons(frame: Frame, enter: int) -> tuple[str, int]:
    """
    A row of drawn pictograms with names under them, optionally with arrows.

    The most literally "a picture" of any template here, and the answer to the
    complaint that every frame was a rectangle holding a word. "Browser reads the
    HTML file and paints the page" is three drawn objects and two arrows; the same
    sentence in three boxes is the sentence, re-set in a smaller font.
    """
    glyphs = (frame.glyphs or [])[:4]
    if not glyphs:
        glyphs = [Glyph(icon="box", label=frame.title)]
    n = len(glyphs)

    gap = 40 if n > 1 else 0
    cell = (USABLE - (n - 1) * gap) / n
    size = min(cell * 0.78, 230.0)
    label_h = 90
    mid = (BODY_TOP + BODY_BOTTOM) / 2 - label_h / 2
    top = mid - size / 2

    out = ""
    centres: list[float] = []
    for i, glyph in enumerate(glyphs):
        cx = MARGIN + i * (cell + gap) + cell / 2
        centres.append(cx)
        _, stroke, ink = ROLE_COLOURS[glyph.role]
        # The role picks the pictogram's own two colours, so emphasis works the same
        # way here as in every other template: the hero is the amber one.
        line, accent = (DEEP, AMBER) if glyph.role == "hero" else \
                       (CORAL, CORAL) if glyph.role == "lost" else \
                       (MUTED, MUTED) if glyph.role == "quiet" else (STROKE, FILL)
        draw = PICTOGRAMS.get(glyph.icon, _pict_box)
        body = draw(cx - size / 2, top, size, line, accent)
        if glyph.label:
            lines, fs = fit(glyph.label, cell, 40, 24, max_lines=2)
            body += text_block(lines, cx, top + size + label_h * 0.45, fs,
                               ink if glyph.role != "plain" else INK, 700)
        out += group(body, enter, "focus" if glyph.role == "hero" else None)
        enter += 1

    if frame.arrows and n > 1:
        shafts = "".join(
            arrow(centres[i] + size / 2 + 14, top + size / 2,
                  centres[i + 1] - size / 2 - 8, top + size / 2, role="")
            for i in range(n - 1))
        out += group(shafts, enter, "flow")
        enter += 1
    return out, enter


#: Font-family values a `preview` frame can HONESTLY render.
#:
#: The generic families are always available. The named ones are loaded by
#: web/index.html and nothing else — so a sample naming a face outside this set
#: renders in the fallback, and the frame then shows one typeface while its own
#: caption names another. That is worse than not drawing it: the viewer is being
#: pointed at a difference which is not on the screen.
#:
#: SPEC_SYSTEM offers exactly this list. Keep the three in step — this set, the
#: <link> in web/index.html, and the list in the brief.
WEB_SAFE_FONTS = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "Bree Serif", "Caveat", "Lobster", "Monoton", "Open Sans",
    "Playfair Display", "Roboto", "Source Sans 3", "Work Sans",
}

#: The families every browser resolves without loading anything.
_GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy",
                     "system-ui"}

#: Where an unavailable face falls back to, so the drawing stays honest-ish rather
#: than defaulting everything to the UI sans. A script face asked for and not found
#: at least still arrives as a script face.
_FONT_FALLBACK = {
    "lobster": "cursive", "caveat": "cursive", "monoton": "fantasy",
    "bree serif": "serif", "playfair display": "serif",
}


def _font_stack(name: str | None) -> str | None:
    """A usable font-family value for `name`, or None to leave the frame's default."""
    if not name:
        return None
    clean = name.strip().strip('"\'')
    # A generic family IS the stack — appending a fallback to "monospace" would
    # produce "monospace, sans-serif", and a browser that cannot find a monospace
    # face is not a browser this runs in.
    if clean.lower() in _GENERIC_FAMILIES:
        return clean.lower()
    if clean in WEB_SAFE_FONTS:
        generic = _FONT_FALLBACK.get(clean.lower(), "sans-serif")
        return f"{clean}, {generic}"
    # Not loaded. Land on the nearest generic rather than the UI sans, so a frame
    # comparing a script face with a plain one still shows two different shapes.
    return _FONT_FALLBACK.get(clean.lower(), "sans-serif")


#: CSS colour keywords a sample may name. Not the full 148: this is the set that
#: turns up in teaching material, and anything outside it — plus any hex value — is
#: handled by _colour() below.
CSS_COLOURS = {
    "black", "white", "red", "green", "blue", "yellow", "orange", "purple",
    "pink", "brown", "grey", "gray", "silver", "gold", "navy", "teal", "olive",
    "maroon", "lime", "aqua", "cyan", "magenta", "fuchsia", "violet", "indigo",
    "beige", "ivory", "khaki", "salmon", "coral", "crimson", "tomato",
    "lightblue", "lightgreen", "lightgrey", "lightgray", "lightyellow",
    "lightpink", "darkblue", "darkgreen", "darkgrey", "darkgray", "darkred",
    "skyblue", "steelblue", "seagreen", "forestgreen", "goldenrod", "chocolate",
    "transparent",
}

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB = re.compile(r"^rgba?\([\d\s.,%/]+\)$")


def _colour(value: str | None) -> str | None:
    """A CSS colour safe to put straight into an SVG attribute, or None.

    Whitelisted rather than passed through, because this string is written into
    markup by a model and the markup is injected into the page. A colour is also the
    one place a typo is invisible: `blu` silently renders as the default ink, so a
    frame claiming "blue" would show black and look deliberate. Returning None lets
    the caller keep the palette ink instead, and checks.check_samples_differ then
    catches the frame whose samples no longer differ.
    """
    if not value:
        return None
    clean = str(value).strip().lower()
    if clean in CSS_COLOURS or _HEX.match(clean) or _RGB.match(clean):
        return clean
    return None


def _preview(frame: Frame, enter: int) -> tuple[str, int]:
    """
    Sample text rendered IN the style being taught. The effect, not a description.

    For a typography lesson this is the only honest picture. A box reading
    "font-family sets the typeface" is a sentence about type; the word "Tourism" set
    in Lobster above the same word in Roboto IS the difference, and it needs no
    label to be understood.

    `scale` is relative, 1-5, and the renderer converts it — which is what makes a
    font-size comparison truthful. Handed pixel values the model picks numbers that
    look right in the document (36px, 28px) and are both a quarter of the height of
    a 1080 canvas, so the difference it is demonstrating disappears. Relative sizes
    get normalised so the biggest sample fills its band and the ratios survive.
    """
    samples = (frame.samples or [])[:3]
    if not samples:
        samples = [Sample(text=frame.value or frame.title or "", label=frame.caption or "")]
    n = len(samples)

    gap = 26
    area = BODY_BOTTOM - BODY_TOP
    band = (area - (n - 1) * gap) / n
    # A third of the band for the caption. At 0.28 the label sat close enough to the
    # sample to read as part of it, which matters here more than elsewhere: the
    # sample is set in a decorative face and the caption is not, so they must be
    # visibly separate things or the frame looks like one broken line of type.
    label_h = min(52.0, band * 0.33)
    top = BODY_TOP

    scales = [s.scale or 3 for s in samples]
    biggest = max(scales) or 3

    out = ""
    for i, sample in enumerate(samples):
        y = top + i * (band + gap)
        fill, stroke, ink = ROLE_COLOURS[sample.role]
        colour = _colour(sample.color)
        ground = _colour(sample.background)

        # WHEN A COLOUR IS THE SUBJECT, THE CARD GETS OUT OF THE WAY. A hero band is
        # normally amber, and amber behind the word "blue" set in blue distorts the
        # very thing the frame exists to show — the viewer cannot judge a colour
        # against a strong tint. So a sample carrying its own colour sits on paper
        # and states its role through the border alone.
        card_fill = ground or (PAPER if colour else fill)
        card = (f'<rect x="{MARGIN}" y="{y:.0f}" width="{USABLE}" height="{band:.0f}" '
                f'rx="16" fill="{card_fill}" stroke="{stroke}" stroke-width="'
                f'{6 if sample.role in ("hero", "lost") else 3}"/>')

        # The size that fits this band, then cut by the sample's share of the
        # largest scale so a "36px vs 28px" frame really shows two sizes.
        room = band - label_h - 18
        text = sample.text or "Sample"
        lines, fs = fit(text, USABLE - 80, int(room * 0.72), 22, max_lines=1)
        fs = max(20, int(fs * (scales[i] / biggest)))

        style = f'font-size="{fs}" fill="{colour or ink}"'
        stack = _font_stack(sample.font)
        style += f' font-family="{esc(stack)}"' if stack else ""
        style += f' font-weight="{sample.weight}"' if sample.weight else ' font-weight="600"'
        style += ' font-style="italic"' if sample.italic else ""
        style += f' text-decoration="{sample.decoration}"' if sample.decoration else ""
        body = (f'<text x="{VIEW / 2:.0f}" y="{y + (band - label_h) / 2 + fs * 0.35:.0f}" '
                f'text-anchor="middle" {style}>{esc(lines[0] if lines else text)}</text>')

        if sample.label:
            capt, cs = fit(sample.label, USABLE - 80, int(label_h * 0.72), 20, max_lines=1)
            body += text_block(capt, VIEW / 2, y + band - label_h * 0.42, cs, MUTED, 600)

        out += group(card + body, enter, "focus" if sample.role == "hero" else None)
        enter += 1
    return out, enter


def _code(frame: Frame, enter: int) -> tuple[str, int]:
    """
    The material's own snippet, on a dark panel, with one line lit.

    A code block is the one thing on this list that is already a picture of itself.
    The document being taught says

        .main-heading {
          font-family: "Roboto";
        }

    and no arrangement of boxes-with-words in it gets closer to that than showing
    it. So the words here are not labels the model composed — they are lines COPIED
    out of the reading material, and moving the hero down them from beat to beat is
    the same "one composition that builds" the other templates get from moving the
    accent around a shape.

    ONE FONT SIZE FOR EVERY LINE, and that is not a detail. A monospace block whose
    lines are each fitted to their own width has ragged indentation, and ragged
    indentation stops reading as code and starts reading as a list — which is the
    thing this template exists to avoid. So the size is computed from the LONGEST
    line and every line uses it; a line still too wide at the floor is truncated.
    """
    lines = [c for c in (frame.code_lines or []) if str(c.label).strip()][:MAX_CODE_LINES]
    if not lines:
        lines = [Cell(label=frame.value or frame.caption or frame.title or "")]

    pad = 32
    chrome_h = 58                      # the title bar: dots, and the file name
    inner = USABLE - 2 * pad

    text = [str(c.label).expandtabs(2).rstrip() for c in lines]
    widths = sorted(len(t) for t in text)

    # ONE OUTLIER MUST NOT SHRINK THE WHOLE BLOCK, which is what sizing from the
    # widest line did. Real documents contain lines like
    #
    #   @import url("https://fonts.googleapis.com/css2?family=Bree+Serif&family=...
    #
    # — 520 characters of font-loading boilerplate in the CSS section this project
    # is fed. Sized to fit that whole, every line lands at the 18px floor and a
    # frame whose subject is `font-family: "Roboto";` is unreadable on a phone
    # because of a line nobody is being asked to read.
    #
    # So the size is set by what MATTERS: the hero line, which must be legible in
    # full, and the median line, which stands in for the body of the snippet.
    # Anything wider than that is truncated with an ellipsis by draw() below — and
    # an elided import is exactly what a person would have put on the slide.
    hero_w = max((len(text[i]) for i, c in enumerate(lines) if c.role == "hero"),
                 default=0)
    sizing_w = max(1, hero_w, widths[len(widths) // 2])

    # Constrained by width AND by height, then rounded to an even size so the
    # baseline arithmetic stays on whole pixels.
    avail_h = BODY_BOTTOM - BODY_TOP - chrome_h - 2 * pad
    by_width = inner / (sizing_w * CHAR_W_MONO)
    by_height = (avail_h / len(lines)) / 1.62
    size = max(18, int(min(44.0, by_width, by_height)) // 2 * 2)
    char_w = size * CHAR_W_MONO
    limit = max(8, int(inner / char_w))
    line_h = size * 1.62

    height = chrome_h + 2 * pad + len(lines) * line_h
    top = (BODY_TOP + BODY_BOTTOM) / 2 - height / 2
    text_top = top + chrome_h + pad

    chrome = (f'<rect x="{MARGIN}" y="{top:.0f}" width="{USABLE}" height="{height:.0f}" '
              f'rx="22" fill="{INK}" stroke="{DEEP}" stroke-width="5"/>')
    chrome += (f'<line x1="{MARGIN}" y1="{top + chrome_h:.0f}" '
               f'x2="{MARGIN + USABLE}" y2="{top + chrome_h:.0f}" '
               f'stroke="{MUTED}" stroke-width="2" opacity="0.45"/>')
    # Three dots. Decoration, and it earns its pixels: it is what makes the panel
    # read as a screen showing code before a single word of it has been read.
    chrome += "".join(
        f'<circle cx="{MARGIN + pad + i * 28:.0f}" cy="{top + chrome_h / 2:.0f}" '
        f'r="7" fill="{MUTED}"/>' for i in range(3))
    if frame.code_caption:
        # Where a file name belongs, which is the other half of "this is code".
        cap, cap_size = fit(frame.code_caption, USABLE - 2 * pad - 120, 30, 20, max_lines=1)
        if cap:
            chrome += (f'<text x="{MARGIN + pad + 3 * 28 + 22:.0f}" '
                       f'y="{top + chrome_h / 2 + cap_size * 0.35:.0f}" '
                       f'font-size="{cap_size}" fill="{MUTED}" font-weight="600" '
                       f'font-family="{MONO}" text-anchor="start">{esc(cap[0])}</text>')

    def draw(i: int, raw: str, role: str) -> str:
        indent = len(raw) - len(raw.lstrip(" "))
        body = raw.strip()
        if len(body) + indent > limit:
            body = body[: max(1, limit - indent - 1)] + "\u2026"
        y = text_top + i * line_h + line_h / 2 + size * 0.35
        x = MARGIN + pad + indent * char_w
        weight = 700 if role == "hero" else 500
        return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" '
                f'fill="{CODE_INK[role]}" font-weight="{weight}" '
                f'font-family="{MONO}" text-anchor="start" '
                f'xml:space="preserve">{esc(body)}</text>')

    hero = next((i for i, c in enumerate(lines) if c.role == "hero"), None)

    base = chrome + "".join(draw(i, text[i], lines[i].role)
                            for i in range(len(lines)) if i != hero)
    out = group(base, enter)
    enter += 1

    if hero is not None:
        y = text_top + hero * line_h
        lit = (f'<rect x="{MARGIN + 10}" y="{y:.0f}" width="{USABLE - 20}" '
               f'height="{line_h:.0f}" rx="8" fill="{AMBER}" fill-opacity="0.16"/>'
               f'<rect x="{MARGIN + 10}" y="{y:.0f}" width="7" '
               f'height="{line_h:.0f}" rx="3" fill="{AMBER}"/>')
        out += group(lit + draw(hero, text[hero], "hero"), enter, "focus")
        enter += 1
    return out, enter


def _compare(frame: Frame, enter: int) -> tuple[str, int]:
    """
    Two worlds side by side, each a bounded card with its own small stack inside.

    This shape was previously forced through `table`, which is wrong in a way that
    contradicts the sentence being spoken: a table is a LOOKUP, so two columns of it
    claim a row-for-row correspondence, and "contiguous allocation versus paging" is
    not a correspondence — it is two alternatives, only one of which is in force at
    a time. Bounding each side in its own card says that; a shared grid says the
    opposite.

    The card's own role colours its BORDER, and its items keep their own roles
    inside it, so "this whole approach is the wasteful one" (role="lost" on the
    panel) and "this one box within it is wasted" (role="lost" on an item) are
    different statements that look different.
    """
    panels = (frame.panels or [])[:MAX_PANELS]
    if not panels:
        panels = [Panel(title=frame.title or "", items=frame.cells)]
    n = len(panels)
    gutter = 40 if n > 1 else 0
    card_w = (USABLE - (n - 1) * gutter) / n
    top, height = BODY_TOP, BODY_BOTTOM - BODY_TOP
    title_h, ipad = 78, 20

    out = ""
    for j, panel in enumerate(panels):
        x = MARGIN + j * (card_w + gutter)
        _, stroke, _ = ROLE_COLOURS[panel.role]
        # A hero or lost card is stated by its border, so it needs to be heavy
        # enough to read at phone size against a plain one.
        weight = 9 if panel.role in ("hero", "lost") else 4
        card = (f'<rect x="{x:.0f}" y="{top}" width="{card_w:.0f}" height="{height}" '
                f'rx="20" fill="{PAPER}" stroke="{stroke}" stroke-width="{weight}"/>')
        titled, size = fit(panel.title, card_w - 2 * ipad, 42, 26, max_lines=2)
        card += text_block(titled, x + card_w / 2, top + title_h / 2 + 4, size, stroke, 700)
        card += (f'<line x1="{x + ipad:.0f}" y1="{top + title_h:.0f}" '
                 f'x2="{x + card_w - ipad:.0f}" y2="{top + title_h:.0f}" '
                 f'stroke="{stroke}" stroke-width="3" opacity="0.45"/>')
        out += group(card, enter, "focus" if panel.role == "hero" else None)
        enter += 1

        items = panel.items[:MAX_PANEL_ITEMS]
        if not items:
            continue
        gap = 18
        area = height - title_h - 2 * ipad
        item_h = min(120, (area - (len(items) - 1) * gap) / len(items))
        total = len(items) * item_h + (len(items) - 1) * gap
        iy = top + title_h + ipad + (area - total) / 2
        iw = card_w - 2 * ipad
        for item in items:
            out += group(box(x + ipad, iy, iw, item_h, item.role, rx=12)
                         + label_in_box(item.label, x + ipad, iy, iw, item_h,
                                        item.role, hi=38, lo=20),
                         enter, "focus" if item.role == "hero" else None)
            enter += 1
            iy += item_h + gap
    return out, enter


_TEMPLATES = {
    "bar": _bar, "mapping": _mapping, "split": _split, "flow": _flow,
    "table": _table, "stat": _stat, "code": _code, "compare": _compare,
    "preview": _preview, "icons": _icons,
    # LEGACY. Not offered to the model any more — a frame whose whole content is a
    # sentence is the "visuals are just text" complaint in its purest form, and it
    # was landing on EVERY short because the brief made it the last beat's job.
    # Kept only so the units already in output/ still re-render.
    "takeaway": _takeaway,
}


def render(frame: Frame) -> str:
    """
    A Frame as a finished SVG string.

    Never raises on content: a frame with an empty template payload renders as its
    title alone rather than failing the build. The pipeline has enough ways to lose
    a diagram already.
    """
    parts = [
        f'<svg viewBox="0 0 {VIEW} {VIEW}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Inter, Helvetica, sans-serif">'
    ]

    enter = 1
    title = band_text(frame.title, TITLE_TOP, TITLE_BOTTOM, 64, 40, INK, 700, enter)
    if title:
        parts.append(title)
        enter += 1

    body, enter = _TEMPLATES[frame.template](frame, enter)
    parts.append(body)

    # frame.note IS DELIBERATELY NOT DRAWN, and the band it used to own is left
    # empty. The field asked for "the one supporting line under the diagram" and
    # what came back was the sentence being spoken: "Student: Contiguous allocation
    # forces one unbroken block per process." under a picture of exactly that,
    # inside a player that already flows the same line word by word beneath the
    # frame. So every short showed its narration twice and its subject once, which
    # is what "the visuals are just text" meant.
    #
    # A frame earns its place by drawing the thing. If an idea needs a sentence to
    # land, the sentence is the voice's job — it is already being said.

    parts.append("</svg>")
    return "".join(p for p in parts if p)
