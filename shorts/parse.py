"""
Step 1 of the pipeline: turn a reading-material markdown file into Sections.

Pure Python, no AI. Every Section keeps its line range so that later steps can
prove a generated sentence came from a specific place in the source.
"""

import re
from pathlib import Path
from .schema import Section

# Matches "## 3.2 Address translation and the page table"
HEADING = re.compile(r"^(?P<hashes>#{2,3})\s+(?P<num>[\d.]+)?\s*(?P<title>.+?)\s*$")

#: The same shape at ANY heading depth, used only when the strict pass finds nothing.
#: A space after the hashes stays mandatory on purpose: without it "#!/bin/sh" and
#: "#include <stdio.h>" both read as headings.
HEADING_ANY = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<num>[\d.]+)?\s*(?P<title>.+?)\s*$")

#: Opening or closing line of a fenced code block.
_FENCE = re.compile(r"^\s*(```|~~~)")


def parse_markdown(path: str | Path) -> list[Section]:
    """
    Split the material into Sections whose ids are UNIQUE.

    Uniqueness is not a nicety, it is the whole contract. Every later step refers to
    a section by id, and find_section returns the first match — so two sections
    sharing an id means a topic can be handed the wrong source text, and a topic
    handed the wrong source text produces a short that either refuses to answer or
    invents. That is exactly what happened on a real HTML document:

        ## 1. Basic Structure  ## 2. Heading Element  ## 3. Paragraph Element
        ...
        ### 1. What is HTML?   ### 2. How do you...   ### 3. What are header and
                                                          heading elements?

    The FAQ subsections restart their numbering, so "### 3" collided with "## 3".
    Skill 1 correctly picked the head-vs-headings question and cited section 3;
    find_section handed the writer the paragraph-element section instead.

    Two ids come out of a heading now. A numbered subsection nested under a
    numbered section is qualified by its parent ("4" + "3" -> "4.3"), which is what
    the author meant anyway. Anything still colliding gets an occurrence suffix
    ("3" -> "3-2"). The suffix uses a dash, not a dot, so repair_section_ids cannot
    mistake it for an invented sub-id and trim it away.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    sections = _scan(lines, HEADING)
    if not sections:
        # NOTHING MATCHED "## " OR "### ", so rather than refuse the document, read
        # it at whatever depth its author actually used. This is a fallback and not
        # the rule, and the difference matters: promoting "####" to a section
        # boundary in general would shred a document that uses it properly. A page
        # with "## 2 Property access" over "#### 2.1 Dot" and "#### 2.2 Bracket"
        # means ONE section holding both examples, and splitting it there would hand
        # the writer half a comparison. So the strict pass wins whenever it finds
        # anything at all, and this runs only when the alternative is "no sections".
        sections = _scan(lines, HEADING_ANY)
    return [s for s in sections if s.text.strip()]


def _scan(lines: list[str], pattern: re.Pattern) -> list[Section]:
    """One pass over the lines, cutting a new Section at every heading match.

    Fenced code is skipped. Reading material is mostly code, and at the depths this
    tolerates a heading and a comment are the same characters: "# set the page size"
    inside a shell block is a comment, and treating it as a section start would slice
    the block in half and cite the halves separately.
    """
    sections: list[Section] = []
    current: dict | None = None
    parent_num: str | None = None       # id of the most recent top-level heading
    used: dict[str, int] = {}
    fenced = False

    for i, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            fenced = not fenced
            if current is not None:
                current["body"].append(line)
            continue

        m = None if fenced else pattern.match(line)
        if m:
            if current:
                current["end_line"] = i - 1
                sections.append(_close(current))

            depth = len(m.group("hashes"))
            num = (m.group("num") or "").strip(". ")
            title = m.group("title").strip()

            if depth <= 2:
                parent_num = num or None
                base = num or _slug(title)
            elif num and parent_num:
                base = f"{parent_num}.{num}"
            else:
                base = num or _slug(title)

            used[base] = used.get(base, 0) + 1
            section_id = base if used[base] == 1 else f"{base}-{used[base]}"

            current = {"section_id": section_id, "title": title,
                       "start_line": i, "body": []}
        elif current is not None:
            current["body"].append(line)

    if current:
        current["end_line"] = len(lines)
        sections.append(_close(current))

    return sections


def _close(cur: dict) -> Section:
    return Section(
        section_id=cur["section_id"],
        title=cur["title"],
        text="\n".join(cur["body"]).strip(),
        start_line=cur["start_line"],
        end_line=cur["end_line"],
    )


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40]


def sections_as_prompt_block(sections: list[Section]) -> str:
    """Format sections for injection into a prompt, with IDs the model must cite."""
    parts = []
    for s in sections:
        parts.append(f"[section_id: {s.section_id}] {s.title}\n{s.text}")
    return "\n\n---\n\n".join(parts)


def find_section(sections: list[Section], section_id: str) -> Section:
    for s in sections:
        if s.section_id == section_id:
            return s
    raise KeyError(f"no section with id {section_id!r}. Have: {[s.section_id for s in sections]}")


if __name__ == "__main__":
    import sys
    for s in parse_markdown(sys.argv[1]):
        print(f"{s.section_id:8} {s.title[:50]:52} lines {s.start_line}-{s.end_line}  {len(s.text)} chars")
