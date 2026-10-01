"""
Rewrite a motion fixture in the hand-written layout every fixture here uses:
top-level fields one per line, list items one per line, and each shot as a
short block (id and beat, then one line per field). json.dumps(indent=2)
spreads a shot over thirty lines, which makes a one-word caption fix an
unreadable diff.

    python -m evals.fixtures.motion.format_fixture evals/fixtures/motion/*_golden.json
"""
import json
import sys
from pathlib import Path


def _j(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _shot(shot: dict) -> str:
    head = {k: shot[k] for k in ("id", "beat") if k in shot}
    if "chapter" in shot:
        head["chapter"] = shot["chapter"]
    first = "{" + ", ".join(f"{_j(k)}: {_j(v)}" for k, v in head.items()) + ","
    rest = [f"     {_j(k)}: {_j(v)}" for k, v in shot.items() if k not in head]
    return "    " + first + "\n" + ",\n".join(rest) + "}"


def format_fixture(data: dict) -> str:
    lines = ["{"]
    items = list(data.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if key == "shots":
            body = ",\n".join(_shot(s) for s in value)
            lines.append(f'  "shots": [\n{body}\n  ]{comma}')
        elif isinstance(value, list) and value:
            body = ",\n".join(f"    {_j(v)}" for v in value)
            lines.append(f"  {_j(key)}: [\n{body}\n  ]{comma}")
        else:
            lines.append(f"  {_j(key)}: {_j(value)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(paths: list[str]) -> int:
    for p in paths:
        path = Path(p)
        data = json.loads(path.read_text(encoding="utf-8"))
        text = format_fixture(data)
        assert json.loads(text) == data, f"{p}: formatting changed the data"
        path.write_text(text, encoding="utf-8")
        print(f"formatted {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
