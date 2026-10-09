"""
The stub demo reels (RESTYLE_TO_MOTION_REELS.md phase 3): three stub reels
run end to end in a TEMP folder — never output/ — and copied to
web/public/motion-demo/: each one's plan (<name>.json, for the player), its
bundle (<name>.bundle.json: script, theme, approach, tags, facts, cost — what
the web UI's Motion section shows) and an index.json listing them. They play
with only the Vite server running.

    SHORTS_STUB=1 python -m shorts.motion_demo

Stub mode only: the scripts are the golden fixtures, the scenes the default
mapping, the audio silence (left out of the demo plans), the timing even.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "web" / "public" / "motion-demo"
DEMOS = [
    ("interview", "content/react_usestate_basics.md", ["--theme", "interview"]),
    ("classic", "content/react_usestate_basics.md", ["--theme", "classic_explainer"]),
    ("walkthrough", "content/tokenization_basics.md", ["--template", "walkthrough"]),
]


def main() -> int:
    if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
        raise SystemExit("run this with SHORTS_STUB=1")
    with tempfile.TemporaryDirectory() as d:
        os.environ["SHORTS_OUTPUT_DIR"] = d
        from . import motion_reel
        from .motion_bundle import bundle
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        index: list[dict] = []
        for name, doc, args in DEMOS:
            before = set(Path(d).glob("*/plan.json"))
            with contextlib.redirect_stdout(io.StringIO()):
                code = motion_reel.main([str(ROOT / doc), "--yes", *args])
            new = set(Path(d).glob("*/plan.json")) - before
            if code != 0 or len(new) != 1:
                print(f"{name}: the stub run failed (exit {code})", file=sys.stderr)
                return 1
            plan_file = new.pop()
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
            plan["audio"] = None
            (DEMO_DIR / f"{name}.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
            data = bundle(Path(d), plan_file.parent.name, plan_url=f"/motion-demo/{name}.json")
            data["demo"] = name
            (DEMO_DIR / f"{name}.bundle.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
            index.append({**{k: v for k, v in data.items()
                             if k in ("short_id", "topic", "stub", "theme", "template",
                                      "teaching_approach", "tags", "language", "duration",
                                      "cost", "stage", "has_plan")},
                          "demo": name, "bundle_url": f"/motion-demo/{name}.bundle.json"})
            print(f"wrote {DEMO_DIR / f'{name}.json'} + bundle ({plan['duration']:.1f}s, {plan['theme']})")
        (DEMO_DIR / "index.json").write_text(json.dumps({"reels": index}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
