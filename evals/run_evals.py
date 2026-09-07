"""
The eval runner. Run this before every prompt change and after every fix.

    python -m evals.run_evals              # code graders only (free, instant)
    python -m evals.run_evals --judge      # also run LLM-judge cases (costs money)

Exit code is non-zero if any case fails, so you can wire it into CI later.
"""
import argparse, inspect, json, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shorts.schema import Script, ShortUnit, SectionUnderstanding
from shorts.parse import parse_markdown, find_section
from shorts import checks, revision

ROOT = Path(__file__).resolve().parent.parent

GRADERS = {
    "timing":         lambda s, src: checks.check_timing(s),
    "overlays":       lambda s, src: checks.check_overlays(s),
    "dialogue_shape": lambda s, src: checks.check_dialogue_shape(s),
    "grounding":      lambda s, src: checks.check_grounding(s, src),
    "source_quotes":  lambda s, src: checks.check_source_quotes(s, src),
    "no_refusal":     lambda s, src: checks.check_no_refusal(s),
    "on_topic":       lambda s, src: checks.check_answers_its_section(s, src),
    "no_repetition":  lambda s, src: checks.check_beats_develop(s),
}

#: Graders that read a whole ShortUnit — the FRAMES — rather than the script.
#:
#: These had no eval coverage at all, and that is not a coincidence: the harness
#: could only load a Script, so every grader that judges a picture was unrunnable
#: here. They were also the graders wired to nothing, and 11 of 15 shipped shorts
#: failed one. A grader with no case behind it drifts back to advisory.
UNIT_GRADERS = {
    "frames_develop":     checks.check_frames_develop,
    "frames_progress":    checks.check_frames_progress,
    "frames_are_visual":  checks.check_frames_are_visual,
    "icons_are_pictures": checks.check_icons_are_pictures,
    "samples_differ":     checks.check_samples_differ,
    "svg_quality":        checks.check_svg_quality,
    "frames_match_strategy": checks.check_frames_match_strategy,
    "one_hero_per_frame":    checks.check_one_hero_per_frame,
    "diagram_matches_narration": checks.check_diagram_matches_narration,
}

#: Graders that read a SCRIPT against the content understanding that produced it.
#:
#: These had no coverage here for the same reason the unit graders had none before
#: them: the harness could load a Script and nothing else, so every check added in
#: steps 5 to 9 — the ones that decide whether a short actually teaches — was
#: unrunnable in CI. A grader with no case behind it drifts back to advisory.
#:
#: The functions are the PRODUCTION ones, imported, not reimplemented. This file
#: decides what to feed them and what to expect; it never decides what they mean.
CONTENT_GRADERS = {
    "follows_sequence":   checks.check_follows_teaching_sequence,
    "uses_example":       checks.check_uses_planned_example,
    "handles_confusion":  checks.check_handles_confusion,
    "opening_hook":       checks.check_opening_follows_hook,
}

#: Graders that read the UNDERSTANDING alone — the validators that quarantine a
#: bad plan before any script is written.
UNDERSTANDING_GRADERS = {
    "teaching_sequence": checks.check_teaching_sequence,
    "example_plan":      checks.check_example_plan,
    "confusion_plan":    checks.check_confusion_plan,
    "hook_plan":         checks.check_hook_plan,
    "plan_depth":        checks.check_plan_depth,
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


def run_unit_case(case: dict, sections) -> tuple[bool, str]:
    """A frame-level case. The fixture is a whole ShortUnit, not a Script."""
    unit = ShortUnit(**json.loads((ROOT / case["fixture"]).read_text()))
    # Most frame graders read only the unit. check_diagram_matches_narration also
    # grounds labels against the section, so hand it the source when it asks for
    # one — by signature rather than by name, so the next such grader just works.
    grader = UNIT_GRADERS[case["grader"]]
    if "source_text" in inspect.signature(grader).parameters:
        result = grader(unit, source_for(case, sections))
    else:
        result = grader(unit)
    exp = case["expect"]

    if result.passed != exp["passed"]:
        return False, f"expected passed={exp['passed']}, got {result.passed} ({result.reason})"

    needle = exp.get("reason_contains")
    if needle and needle.lower() not in result.reason.lower():
        return False, f"reason missing {needle!r}; got: {result.reason}"

    return True, result.reason


def load_content(fixture: str):
    """A content fixture: an understanding, and usually the script written from it.

    One file rather than two, because the pair is the unit under test — a script is
    only right or wrong RELATIVE to the plan it was given, and splitting them makes
    it possible to freeze a case whose halves no longer belong together.
    """
    data = json.loads((ROOT / fixture).read_text(encoding="utf-8"))
    understanding = SectionUnderstanding(**data["understanding"])
    script = Script(**data["script"]) if data.get("script") else None
    return understanding, script


def _check_expectations(result, exp: dict) -> tuple[bool, str]:
    """The shared assertions: passed, skipped, and a substring of the reason."""
    if result.passed != exp["passed"]:
        return False, f"expected passed={exp['passed']}, got {result.passed} ({result.reason})"

    if "skipped" in exp:
        got = bool(result.details.get("skipped"))
        if got != exp["skipped"]:
            return False, f"expected skipped={exp['skipped']}, got {got} ({result.reason})"

    needle = exp.get("reason_contains")
    if needle and needle.lower() not in result.reason.lower():
        return False, f"reason missing {needle!r}; got: {result.reason}"

    return True, result.reason


def run_content_case(case: dict, sections) -> tuple[bool, str]:
    """A script graded against its own content understanding."""
    understanding, script = load_content(case["fixture"])
    source = source_for(case, sections)
    name = case["grader"]

    if name == "reaches_objective":
        result = checks.check_reaches_objective(script, understanding)
    elif name == "learning_outcome":
        result = checks.check_learning_outcome(script, understanding, source)
    else:
        result = CONTENT_GRADERS[name](script, understanding, source)

    ok, detail = _check_expectations(result, case["expect"])
    if not ok:
        return ok, detail

    # A learning_outcome case may also pin which requirement broke, so a future
    # change that fails the right short for the wrong reason is still caught.
    for flag, want in (case["expect"].get("requirements") or {}).items():
        got = result.details.get(flag)
        if got != want:
            return False, f"requirement {flag}: expected {want}, got {got}"
    return True, detail


def run_understanding_case(case: dict, sections) -> tuple[bool, str]:
    """A plan validated on its own, before any script exists."""
    understanding, _ = load_content(case["fixture"])
    grader = UNDERSTANDING_GRADERS[case["grader"]]
    return _check_expectations(grader(understanding, source_for(case, sections)),
                               case["expect"])


def run_revision_case(case: dict, sections) -> tuple[bool, str]:
    """The whole grader suite, routed into a revision brief.

    This is the only case type that runs every grader together, because that is
    what it is testing: not whether one check fires, but whether the failures and
    the SURVIVORS are sorted correctly for the retry. It reuses run_script_graders
    and revision.route verbatim.
    """
    understanding, script = load_content(case["fixture"])
    results = checks.run_script_graders(script, source_for(case, sections),
                                        understanding=understanding)
    plan = revision.route(results)
    exp = case["expect"]

    want_fix = exp.get("fix_areas")
    if want_fix is not None and plan.failed_areas != want_fix:
        return False, f"expected fix areas {want_fix}, got {plan.failed_areas}"

    want_keep = exp.get("preserve_areas")
    if want_keep is not None:
        got = [a for a, _ in plan.preserve]
        if got != want_keep:
            return False, f"expected preserved areas {want_keep}, got {got}"

    block = plan.as_feedback()
    for needle in exp.get("block_contains", []):
        if needle.lower() not in block.lower():
            return False, f"revision block missing {needle!r}"
    for needle in exp.get("block_excludes", []):
        if needle.lower() in block.lower():
            return False, f"revision block should not mention {needle!r}"

    return True, f"fix={plan.failed_areas} preserve={[a for a, _ in plan.preserve]}"


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


def _run_strategy_case(case: dict, sections) -> tuple[bool, str]:
    """Does the strategy step still classify this beat's claim correctly?

    `relationship` is the field the whole visual chain hangs off: it decides which
    templates check_frames_match_strategy will accept, so a mislabel is not a
    cosmetic error — it makes a correct drawing fail a grader. A comparison labelled
    `process` sent a two-column score frame to be redrawn as a flow three times.

    One real call, so it is gated behind --judge like every other golden case.
    """
    from shorts.skills.strategy import plan_strategy

    script = load_script(case["fixture"])
    # The case names its own document, because the beat under test need not come
    # from the suite's default source_doc — this one is CSS, the default is paging.
    own = case.get("input")
    doc_sections = parse_markdown(ROOT / own) if own else sections
    sid = case.get("section_id")
    section = find_section(doc_sections, sid) if sid else None
    strategy = plan_strategy(script, section)
    by_ref = strategy.by_ref()

    # A LIST OF ACCEPTABLE LABELS IS ALLOWED, and it is not laziness. Some beats
    # have two honest readings — "the OS locates the page, selects a frame, issues
    # the read" is a process if you look at the ordering and data_movement if you
    # look at the page travelling from disk into the frame, and both draw a
    # teachable picture. Pinning such a beat to one label freezes a coin toss and
    # the case goes red on a correct answer. Where a case cares about a boundary
    # rather than a value, it lists the labels that respect it.
    problems, seen = [], {}
    for ref, want in (case["expect"].get("relationship_by_ref") or {}).items():
        got = getattr(by_ref.get(ref), "relationship", None)
        seen[ref] = got
        allowed = want if isinstance(want, list) else [want]
        if got not in allowed:
            problems.append(f"{ref}: expected {' or '.join(allowed)}, got {got!r}")

    if problems:
        return False, "; ".join(problems)
    return True, ", ".join(f"{r}={g}" for r, g in seen.items())


def run_golden_case(case: dict, sections) -> tuple[bool, str]:
    """A real call to one skill, checked against a frozen expectation.

    DISPATCHES ON case["step"], which the schema always carried and this ignored —
    every golden case ran `select` whatever its step said, so a golden case for any
    other skill silently tested selection instead. E010 is the only one that
    predates the dispatch and it says `select`, so nothing changes for it.
    """
    if case.get("step") == "strategy":
        return _run_strategy_case(case, sections)

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
            elif kind == "unit_grader":
                ok, detail = run_unit_case(case, sections)
            elif kind == "content_grader":
                ok, detail = run_content_case(case, sections)
            elif kind == "understanding_grader":
                ok, detail = run_understanding_case(case, sections)
            elif kind == "revision":
                ok, detail = run_revision_case(case, sections)
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
