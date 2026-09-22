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


# ---------------------------------------------------- evidence grouping (Step 4)
#
# WHY THIS EXISTS. parse_markdown cuts a new Section at every heading, which is
# right for keeping unrelated material apart and wrong for a very common
# authoring style: a concept stated in one or two sentences under its own
# heading, then elaborated under separate sibling headings — "## Example",
# "## How It Works", "## Script" — each individually too thin to cite for a
# multi-beat script even though the concept, read as the small cluster it
# actually is, plainly is not. checks.check_section_richness, check_source_
# quotes and check_answers_its_section all judge exactly one Section's raw
# text, and write_script's own prompt is explicit that it may not borrow from
# "elsewhere in the document" — so a topic filed under the thin heading alone
# can never see its own document's best evidence, however adjacent it is.
#
# THE FIX IS NOT "MERGE THIN NEIGHBOURS" — that was tried and rejected. Two
# short, unrelated concept sections sitting next to each other ("## What are
# Props?" then "## What is State?") must never be pooled just because both are
# thin: that is exactly the cross-topic contamination check_answers_its_section
# exists to stop. Thinness is not a relevance signal.
#
# THE SIGNAL USED INSTEAD is the heading's own ROLE. "Example", "How It Works"
# and "Script" do not name a subject a reader would look up on its own — they
# name a generic part a chunk of material plays FOR WHATEVER CONCEPT CAME RIGHT
# BEFORE IT, in any document, on any topic. A heading that names an actual
# concept is never in this set, however short its own body is.

#: Normalized (lowercase, punctuation stripped) headings that elaborate the
#: concept named by the section immediately before them, rather than
#: introducing a concept of their own. Deliberately generic and deliberately
#: short: every entry is a role a section can play in ANY subject's write-up,
#: never a word tied to one topic or document.
_ELABORATION_TITLES = {
    "example", "examples", "sample", "sample code", "code", "code example",
    "demo", "demonstration",
    "how it works", "how does it work", "how this works", "under the hood",
    "walkthrough", "step by step",
    "explanation", "explained",
    "output", "result", "results",
    "summary", "recap", "in practice",
    "script", "narration",
}


def _normalize_title(title: str) -> str:
    """"6.2 Example", "Example:" and "EXAMPLE" all reduce to "example", so the
    lookup above matches on the heading's wording, not its numbering or case."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _is_elaboration_title(title: str) -> bool:
    return _normalize_title(title) in _ELABORATION_TITLES


def group_sections_by_concept(sections: list[Section]) -> dict[str, list[Section]]:
    """
    Map every section id to the small cluster of CONSECUTIVE sections that
    together hold one concept's evidence: the section itself, plus any run of
    sections right after it whose heading is a generic elaboration of what
    came before (see _ELABORATION_TITLES), chained for as long as that holds.

    CONSERVATIVE BY CONSTRUCTION. A section whose own title is not a
    recognised elaboration role always starts a NEW group, however short its
    body is — so two thin, adjacent, unrelated concepts are never pooled
    together; only a heading that names a generic role (not a subject)
    attaches backward. A document that elaborates a concept under an
    idiosyncratically-worded heading ("## What that looks like in code") is
    simply not recognised, and that section is graded on its own, exactly as
    every section was graded before this function existed. That is a missed
    merge, not a wrong one — the safe failure direction for something guarding
    against citing unrelated material.

    A leading elaboration-titled section (nothing before it to attach to)
    stands alone rather than being dropped, so it is still addressable.

    Every section id appears exactly once as a key. A section with no
    elaborating neighbours maps to a single-element list containing only
    itself, so evidence_text below is byte-identical to plain section.text
    for every document that does not use this authoring pattern.
    """
    groups: list[list[Section]] = []
    for s in sections:
        if groups and _is_elaboration_title(s.title):
            groups[-1].append(s)
        else:
            groups.append([s])

    by_id: dict[str, list[Section]] = {}
    for group in groups:
        for s in group:
            by_id[s.section_id] = group
    return by_id


def evidence_text(sections: list[Section], section_id: str) -> str:
    """
    The text a topic filed under `section_id` may honestly cite from: its own
    section, plus any sections group_sections_by_concept groups with it.

    THE ONE RESOLVER, SHARED BY EVERY CONSUMER THAT NEEDS TO AGREE ON WHAT
    "THE SECTION" MEANS FOR A TOPIC — check_section_richness (before a script
    is even attempted), write_script's own prompt (what it may cite from),
    check_source_quotes and check_answers_its_section (what a citation is
    verified against). Computing it once here rather than in each caller is
    what keeps those four from silently drifting into judging different text.
    """
    section = find_section(sections, section_id)
    group = group_sections_by_concept(sections).get(section_id, [section])
    if len(group) == 1:
        return section.text
    return "\n\n".join(s.text for s in group)


def evidence_section_ids(sections: list[Section], section_id: str) -> list[str]:
    """Which section ids contributed to evidence_text(sections, section_id) —
    for traceability: showing a reviewer, or a test, which headings a short's
    grounding actually drew on."""
    group = group_sections_by_concept(sections).get(section_id)
    return [s.section_id for s in group] if group else [section_id]


if __name__ == "__main__":
    import sys
    for s in parse_markdown(sys.argv[1]):
        print(f"{s.section_id:8} {s.title[:50]:52} lines {s.start_line}-{s.end_line}  {len(s.text)} chars")
