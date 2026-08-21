"""
The eval runner. Run this before every prompt change and after every fix.

    python -m evals.run_evals              # code graders only (free, instant)
    python -m evals.run_evals --judge      # also run LLM-judge cases (costs money)

Exit code is non-zero if any case fails, so you can wire it into CI later.
"""
import argparse, json, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shorts.schema import Script
from shorts.parse import parse_markdown, find_section
from shorts import checks

ROOT = Path(__file__).resolve().parent.parent

GRADERS = {
    "timing":         lambda s, src: checks.check_timing(s),
    "overlays":       lambda s, src: checks.check_overlays(s),
    "dialogue_shape": lambda s, src: checks.check_dialogue_shape(s),
    "grounding":      lambda s, src: checks.check_grounding(s, src),
    "source_quotes":  lambda s, src: checks.check_source_quotes(s, src),
    "no_refusal":     lambda s, src: checks.check_no_refusal(s),
    "on_topic":       lambda s, src: checks.check_answers_its_section(s, src),
}

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def load_script(fixture: str) -> Script:
    data = json.loads((ROOT / fixture).read_text())
    return Script(**data)


def source_for(case: dict, sections) -> str:
    sid = case.get("section_id")
    return find_section(sections, sid).text if sid else ""


def run_code_case(case: dict, sections) -> tuple[bool, str]:
    script = load_script(case["fixture"])
    grader = GRADERS[case["grader"]]
    result = grader(script, source_for(case, sections))
    exp = case["expect"]

    if result.passed != exp["passed"]:
        return False, f"expected passed={exp['passed']}, got {result.passed} ({result.reason})"

    needle = exp.get("reason_contains")
    if needle and needle.lower() not in result.reason.lower():
        return False, f"reason missing {needle!r}; got: {result.reason}"

    return True, result.reason


def run_judge_case(case: dict, sections) -> tuple[bool, str]:
    from shorts.skills.audit import judge_script          # imported lazily: needs an API key
    script = load_script(case["fixture"])
    report = judge_script(script, source_for(case, sections))
    exp = case["expect"]

    if "faithfulness_max" in exp and report.faithfulness > exp["faithfulness_max"]:
        return False, f"faithfulness {report.faithfulness} > max {exp['faithfulness_max']}"
    if "faithfulness_min" in exp and report.faithfulness < exp["faithfulness_min"]:
        return False, f"faithfulness {report.faithfulness} < min {exp['faithfulness_min']}"
    if "passed" in exp and report.passed != exp["passed"]:
        return False, f"expected passed={exp['passed']}, got {report.passed}: {report.problems}"

    return True, f"faithfulness={report.faithfulness} clarity={report.clarity} pace={report.pace}"


def run_golden_case(case: dict, sections) -> tuple[bool, str]:
    from shorts.skills.select import select_topics
    result = select_topics(sections)
    exp = case["expect"]
    got_sections = {t.source_section_id for t in result.topics}

    missing = set(exp.get("must_include_sections", [])) - got_sections
    if missing:
        return False, f"selection dropped required sections: {sorted(missing)}"

    lo, hi = exp.get("topic_count_between", [1, 99])
    if not lo <= len(result.topics) <= hi:
        return False, f"{len(result.topics)} topics, expected {lo}-{hi}"

    return True, f"{len(result.topics)} topics covering {sorted(got_sections)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", action="store_true", help="also run llm_judge and golden cases (costs API calls)")
    ap.add_argument("--only", help="run a single case id, e.g. E004")
    args = ap.parse_args()

    spec = yaml.safe_load((ROOT / "evals" / "cases.yaml").read_text())
    sections = parse_markdown(ROOT / spec["source_doc"])

    cases = spec["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]

    passed = failed = skipped = 0
    print(f"\n{'':4} {'ID':6} {'CASE':52} RESULT")
    print("-" * 96)

    for case in cases:
        kind = case["type"]
        if kind in ("llm_judge", "golden") and not args.judge:
            print(f"{DIM}  ·  {case['id']:6} {case['name'][:52]:52} skipped (needs --judge){RESET}")
            skipped += 1
            continue
        try:
            if kind == "code_grader":
                ok, detail = run_code_case(case, sections)
            elif kind == "llm_judge":
                ok, detail = run_judge_case(case, sections)
            else:
                ok, detail = run_golden_case(case, sections)
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"

        colour, mark = (GREEN, "PASS") if ok else (RED, "FAIL")
        print(f"{colour} {mark} {RESET}{case['id']:6} {case['name'][:52]:52} {detail[:80]}")
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"       {YELLOW}why this case exists:{RESET} {case['why']}")

    print("-" * 96)
    print(f"{passed} passed, {failed} failed, {skipped} skipped\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
