"""
Rewrite the SCRIPT of a unit already on disk, then redesign its frames and re-judge.

    python -m shorts.rescript                 # every unit a grader or the judge fails
    python -m shorts.rescript <short_id>      # just one
    python -m shorts.rescript --check         # say what would be rewritten, spend nothing

WHY THIS EXISTS, AND WHY redraw --redesign COULD NOT DO IT
redraw --redesign re-runs the visual step against the same beats. That is the right
tool when the words are fine and the pictures are not. It is the wrong tool for the
two failures that were left after three cycles of it, and running it again on those
units cost money and changed nothing:

  A FAITHFULNESS FAILURE IS IN THE WORDS. Six units were held with the judge naming
  the same defect each time — a beat sourced from outside its own section. "beat 2
  states 'A' = 65 … that sentence does not appear in the permitted source section".
  Redrawing that beat produces a faithful picture of a false sentence, which is
  worse than a bad picture of a true one. The beat has to go.

  A REPEATED FRAME IS USUALLY A BEAT TOO MANY. The other pattern was three units
  whose frame 4 was frame 2 again, each surviving three redesign attempts. The
  common shape: a FOUR-beat script whose last beat adds no new object, so there is
  nothing left to draw and the design step reuses. No amount of re-rolling the
  pictures fixes a script with nothing in its last beat — the honest fix is three
  beats. That is a script edit, so it belongs here.

So this module treats the graders' and the judge's own complaints as the feedback
for a rewrite. write_script already knows how to act on "your previous attempt was
rejected, fix exactly this" — it is the same channel the human reviewer uses in the
web flow — and check_source_quotes now holds every new beat to the unit's own
section.

COST: up to 3 script calls (only on grader failure), 1 design call (up to 3 on
design-grader failure), and 1 judge call, per unit. Nothing is written unless the
result is an improvement.
"""
import argparse, json, sys
from pathlib import Path

from . import checks, config, feed, revision
from .redraw import _section_for, _units
from .schema import Script, ShortUnit, Topic

MAX_SCRIPT_ATTEMPTS = 3


def _problems(unit: ShortUnit, section) -> list[str]:
    """
    Everything wrong with this unit that a REWRITE could plausibly fix.

    The judge's problems come first because they are the ones that matter — they are
    the only check that reads a claim against its source — and they are already
    phrased as instructions ("beat 3 introduces 'GET /index.html', which does not
    appear in the source section").
    """
    out: list[str] = []
    if unit.eval is not None and not unit.eval.passed:
        out.append(f"The reviewer scored this short faithfulness={unit.eval.faithfulness}, "
                   f"clarity={unit.eval.clarity}, pace={unit.eval.pace} and REJECTED it.")
        out += [f"{p}" for p in unit.eval.problems]

    script = Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)
    for r in checks.run_script_graders(script, section.text):
        if not r.passed:
            out.append(f"{r.name}: {r.reason}")

    # The visual failures a SCRIPT can fix. A frame that repeats an earlier frame,
    # or that prints most of its own spoken line, is nearly always a beat with no
    # object in it — see the module docstring.
    for r in (checks.check_frames_develop(unit), checks.check_frames_are_visual(unit)):
        if not r.passed:
            out.append(
                f"{r.name}: {r.reason}. This is a SCRIPT problem: a beat whose line "
                f"names no object gives the diagram nothing new to draw, so the "
                f"picture repeats. Cut that beat, or rewrite it around a concrete "
                f"thing from the section.")
    return out


def _needs_work(unit: ShortUnit, section) -> bool:
    return bool(_problems(unit, section))


def rescript(path: Path, write: bool = True) -> tuple[str, bool]:
    """Rewrite one unit. Returns (message, changed)."""
    from .skills.script import write_script
    from .skills.understanding import understanding_for
    from .skills.visuals import design_visuals
    from .skills.audit import judge_script

    unit = ShortUnit(**json.loads(path.read_text()))
    section = _section_for(unit)
    if section is None:
        return "no source document on disk — cannot re-script or verify", False

    problems = _problems(unit, section)
    if not problems:
        return "nothing to fix", False

    before = unit.eval
    current = Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)
    topic = Topic(id=unit.short_id, topic=unit.question,
                  why_it_matters="held back by the reviewer; being rewritten",
                  source_section_id=section.section_id, difficulty="medium")

    feedback = ("\n".join(f"  - {p}" for p in problems) + """

Rewrite the script so none of the above is true. Two rules override everything else:
  * EVERY beat must quote a sentence from THIS SHORT'S OWN SECTION, verbatim. A
    sentence from elsewhere in the document is not allowed, however true it is.
  * FEWER BEATS IS BETTER THAN A BEAT WITH NOTHING IN IT. If the section supports
    two solid answer beats, write two. Do not pad to three.
If the section cannot support the question as asked, narrow the question and make
beat 1 ask the narrower one.""")

    # The script graders first, and free. Up to three attempts, carrying each
    # failure forward — the same loop run.py and server.py use.
    fixed = None
    fb = feedback
    # Read once, outside the loop, like every other retry loop in the project. A
    # unit is being rewritten because its beats drifted off the section, so what
    # the section does and does not answer is the useful thing to have in hand.
    understanding = understanding_for(section)
    for attempt in range(1, MAX_SCRIPT_ATTEMPTS + 1):
        try:
            candidate = write_script(topic=topic, section=section, feedback=fb,
                                    current=current, understanding=understanding)
        except Exception as e:
            return f"script call failed: {type(e).__name__}: {e}", False
        results = checks.run_script_graders(candidate, section.text,
                                            understanding=understanding)
        if checks.all_passed(results):
            fixed = candidate
            break
        failures = [f"{r.name}: {r.reason}" for r in results if not r.passed]
        print(f"    script {attempt}/{MAX_SCRIPT_ATTEMPTS} for {unit.short_id}: "
              + "; ".join(f[:110] for f in failures[:2]))
        # The rewrite instruction stays on top as the prefix — it is why this unit
        # is being re-scripted at all — and the routed block follows it.
        fb = revision.feedback_for(results, prefix=feedback)
    if fixed is None:
        return (f"no script passed the graders in {MAX_SCRIPT_ATTEMPTS} attempts — the "
                f"section probably cannot answer this question; drop the topic or "
                f"re-file it under the section that does"), False

    # New words mean the old frames are for beats that no longer exist.
    visuals, design_problems = design_visuals(fixed, section)

    candidate_unit = unit.model_copy(update={
        "question": fixed.question, "beats": fixed.beats,
        "estimated_seconds": fixed.estimated_seconds, "visuals": visuals})
    try:
        candidate_unit.eval = judge_script(fixed, section.text, candidate_unit)
    except Exception as e:
        return f"judge failed after a good rewrite: {type(e).__name__}: {e}", False

    after = candidate_unit.eval

    # NEVER TURN A SHORT THAT SHIPS INTO ONE THAT DOES NOT. This is checked first
    # and it overrides every other notion of "better".
    #
    # The first version of this test compared faithfulness alone, and what_is_a_component
    # is what it cost: the rewrite scored f=4 -> f=5 and was kept, but the judge
    # rejected its NEW diagrams, so overall it went passed=True -> passed=False and
    # left the reel. Faithfulness went up and the student lost a short. A single axis
    # is not the goal; EvalReport.passed is.
    if before is not None and before.passed and not after.passed:
        return (f"rewrite would drop this short OUT of the reel "
                f"(f={before.faithfulness}->{after.faithfulness} but diagram_correct="
                f"{after.diagram_correct}, answered={after.question_answered}) — "
                f"keeping the original"), False

    # KEEP ONLY AN IMPROVEMENT. A rewrite that trades a faithfulness defect for a
    # clarity one is not progress, and the version on disk at least had a human's
    # approval behind its wording.
    better = (after.passed and not (before and before.passed)) or (
        before is not None and after.faithfulness > before.faithfulness) or (
        before is None and after.passed)
    if not better:
        return (f"rewrite was not an improvement "
                f"(was f={before.faithfulness if before else '-'} -> now "
                f"f={after.faithfulness}) — keeping the original"), False

    candidate_unit.status = "audited" if after.passed else "rejected"
    if write:
        path.write_text(json.dumps(candidate_unit.model_dump(), indent=2))
    msg = (f"f={before.faithfulness if before else '-'}->{after.faithfulness} "
           f"c={before.clarity if before else '-'}->{after.clarity} "
           f"beats {len(unit.beats)}->{len(fixed.beats)} "
           f"status={candidate_unit.status}")
    if design_problems:
        msg += "\n       frames still: " + "; ".join(p[:110] for p in design_problems[:2])
    return msg, True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("short_id", nargs="?", help="one unit, default every failing one")
    ap.add_argument("--check", action="store_true",
                    help="list what would be rewritten and why. Spends nothing.")
    args = ap.parse_args()

    paths = _units(args.short_id)
    if not paths:
        print(f"no unit in {config.OUTPUT_DIR}"
              + (f" matching {args.short_id!r}" if args.short_id else ""))
        return 1

    todo = []
    for path in paths:
        try:
            unit = ShortUnit(**json.loads(path.read_text()))
        except Exception as e:
            print(f"  ! {path.stem}: {type(e).__name__}: {e}")
            continue
        section = _section_for(unit)
        if section is None:
            continue
        problems = _problems(unit, section)
        if problems:
            todo.append(path)
            if args.check:
                print(f"\n{path.stem}")
                for p in problems[:6]:
                    print(f"    {p[:150]}")

    if not todo:
        print("nothing to re-script — every unit passes its graders and its judge")
        return 0

    if args.check:
        print(f"\n{len(todo)} unit(s) would be re-scripted. Drop --check to run.")
        return 0

    print(f"re-scripting {len(todo)} unit(s) — up to "
          f"{len(todo) * (MAX_SCRIPT_ATTEMPTS + 4)} paid calls, usually far fewer:")
    changed = 0
    for path in todo:
        try:
            msg, did = rescript(path, write=True)
        except Exception as e:
            print(f"  {path.stem:42} ! {type(e).__name__}: {e}")
            continue
        changed += did
        print(f"  {path.stem:42} {msg}")

    if changed:
        out = feed.build_json()
        print(f"\n{changed} of {len(todo)} rewritten; rebuilt {out}")
    else:
        print(f"\nnothing improved on — all {len(todo)} originals kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
