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
from ..schema import Frame, Cell, TableRow

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

# The palette. checks and SVG_SYSTEM describe it; here it is the only thing that
# assigns it, which is why a short cannot end up with three amber elements.
FILL = "#E1F5EE"
STROKE = "#1D9E75"
DEEP = "#0F6E56"
AMBER = "#F2B14B"
CORAL = "#E8735A"
INK = "#2C2C2A"
MUTED = "#8A8880"

#: fill, stroke, ink for each role.
ROLE_COLOURS: dict[str, tuple[str, str, str]] = {
    "plain": (FILL, STROKE, INK),
    "hero":  (AMBER, DEEP, INK),
    "lost":  ("#FBE3DE", CORAL, INK),
    "quiet": ("#F4F5F3", MUTED, MUTED),
}

#: Hard caps. Past these a frame is not a diagram, it is a spreadsheet — and the
#: renderer would have to shrink type below legibility to fit it.
MAX_CELLS = 10
MAX_COLUMN = 4
MAX_PARTS = 3
MAX_STEPS = 4
MAX_ROWS = 4


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


_TEMPLATES = {
    "bar": _bar, "mapping": _mapping, "split": _split, "flow": _flow,
    "table": _table, "stat": _stat, "takeaway": _takeaway,
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

    # A takeaway carries its sentence in the body, so a note under it would be a
    # second sentence competing with the one thing to remember.
    body, enter = _TEMPLATES[frame.template](frame, enter)
    parts.append(body)

    if frame.template != "takeaway":
        parts.append(band_text(frame.note, NOTE_TOP, NOTE_BOTTOM, 42, 32, INK, 600, enter))

    parts.append("</svg>")
    return "".join(p for p in parts if p)
