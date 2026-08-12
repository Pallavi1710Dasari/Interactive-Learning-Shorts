"""
Step 1 of the pipeline: turn a reading-material markdown file into Sections.

Pure Python, no AI. Every Section keeps its line range so that later steps can
prove a generated sentence came from a specific place in the source.
"""

import re
from pathlib import Path
from .schema import Section

# Matches "## 3.2 Address translation and the page table"
HEADING = re.compile(r"^(#{2,3})\s+(?P<num>[\d.]+)?\s*(?P<title>.+?)\s*$")


def parse_markdown(path: str | Path) -> list[Section]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    sections: list[Section] = []
    current: dict | None = None

    for i, line in enumerate(lines, start=1):
        m = HEADING.match(line)
        if m and line.startswith("##"):
            if current:
                current["end_line"] = i - 1
                sections.append(_close(current))
            num = (m.group("num") or "").strip(". ")
            current = {
                "section_id": num or _slug(m.group("title")),
                "title": m.group("title").strip(),
                "start_line": i,
                "body": [],
            }
        elif current is not None:
            current["body"].append(line)

    if current:
        current["end_line"] = len(lines)
        sections.append(_close(current))

    return [s for s in sections if s.text.strip()]


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
