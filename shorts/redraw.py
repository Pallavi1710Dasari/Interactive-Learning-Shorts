"""
Re-render every stored frame after a layout change. Free, offline, no LLM calls.

    python -m shorts.redraw              # every unit in output/
    python -m shorts.redraw <short_id>   # just one
    python -m shorts.redraw --check      # say what would change, write nothing

WHY THIS EXISTS
A ShortUnit keeps the Frame each diagram was rendered from, not just the finished
SVG, and schema.Frame says why: "so a frame can be re-rendered after a layout fix
without spending another LLM call." Nothing actually did it. Every improvement to
skills/layout.py reached new shorts only, and the ones already in output/ kept
whatever markup the renderer emitted on the day they were built — so a fix to a
band, a colour or a label rule looked like it had not worked.

The change that prompted writing it: layout.render stopped drawing frame.note,
because what the model put there was the sentence being spoken. Every unit built
before that carries the echo in its SVG and none of them needed a model to lose it.

WHAT THE DEFAULT PASS CANNOT DO, and the distinction matters when reading its
output. It re-runs the DRAWING, not the DESIGN. A frame that chose the wrong
template — a "takeaway" card whose whole content is one sentence, or the same code
panel three times with the accent moved — is a bad decision faithfully redrawn, and
no local pass can fix it.

    python -m shorts.redraw --redesign      # ask the model for new frames. COSTS.

--redesign is the fix for those: it throws the stored frames away and runs the
visual step again, against the current brief and the section the short came from.
One model call per short, and by default only for the shorts that actually fail a
design grader — a unit whose frames are already good is left alone rather than
re-rolled. The scripts and the audio are untouched; only the pictures change.

    python -m shorts.redraw --redesign --all       # every unit, passing or not
    python -m shorts.redraw --redesign --judge     # and re-grade what changed

--all exists for the case the default deliberately skips: the brief or the model
changed, so frames that PASS every grader are still worse than the ones the current
setup would produce. Graders catch defects, not mediocrity.

--judge re-runs the LLM judge on each unit afterwards and stores the verdict. It is
the only check that reads a frame against the source and forms an opinion — the code
graders are structural, so they cannot see a diagram that is well-formed, on
vocabulary, and about the wrong thing. A second paid call per short.
"""
import argparse, json, pathlib, sys
from pathlib import Path

from . import checks, config, feed
from .parse import parse_markdown, find_section
from .schema import ShortUnit
from .skills.layout import render


def _is_unit(path: Path) -> bool:
    """Is this a ShortUnit, as opposed to one of the bookkeeping files beside it?

    By SHAPE, not by name. output/ also holds manifest.json, topics.json, usage.json
    and whatever a stub run left behind, and a name blocklist has to be extended
    every time something new lands there — which it silently is not, so the sweep
    ends in a wall of pydantic errors about a topics file that was never a unit.
    """
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(doc, dict) and "beats" in doc and "visuals" in doc


def _units(only: str | None) -> list[Path]:
    paths = sorted(p for p in config.OUTPUT_DIR.glob("*.json") if _is_unit(p))
    return [p for p in paths if only is None or p.stem == only]


def _design_problems(unit: ShortUnit) -> list[str]:
    """
    The graders that judge the DESIGN rather than the drawing.

    Everything a redraw cannot fix and a redesign can: the wrong template, a frame
    that repeats its neighbour, a caption the picture does not support, a code line
    that is not in the material. Deliberately the same list this module reports and
    the one --redesign selects on, so "needs a regenerate" and "will be regenerated"
    cannot drift apart.

    The source-reading graders are included only when the material can be found;
    a unit whose document has been deleted is judged on what is checkable.
    """
    section = _section_for(unit)
    # THE SAME LIST skills/visuals.py retries on, and it has to stay the same list.
    # It was missing one_hero_per_frame and frames_match_strategy, so `--redesign`
    # reported "frames already pass" for a unit whose accent was on every element of
    # a group — a failure the generator itself would have retried. A repair pass
    # that judges by a weaker standard than the generator cannot repair what the
    # generator now rejects.
    results = [checks.check_frames_are_visual(unit), checks.check_frames_develop(unit),
               checks.check_frames_progress(unit),
               checks.check_frames_match_strategy(unit),
               checks.check_one_hero_per_frame(unit),
               checks.check_samples_differ(unit), checks.check_svg_quality(unit),
               checks.check_icons_are_pictures(unit)]
    if section is not None:
        results.append(checks.check_code_frames_quote_source(unit, section.text))
    return [f"{r.name}: {r.reason}" for r in results if not r.passed]


#: Where a unit's source document might live, by session_id.
#:
#: TWO CONVENTIONS, because there are two entry points. The web flow stores uploads
#: as output/uploads/<hash>.md and sets session_id to that hash. The CLI sets
#: session_id to the stem of whatever path it was given, which is usually a file in
#: content/ — so looking only in uploads/ found nothing for every CLI-built unit,
#: and those were silently redesigned from the dialogue alone and skipped by the
#: judge. Both are one glob apart; there was no reason to support only one.
def _source_candidates(session_id: str) -> list[pathlib.Path]:
    return [config.OUTPUT_DIR / "uploads" / f"{session_id}.md",
            config.ROOT / "content" / f"{session_id}.md",
            config.ROOT / f"{session_id}.md"]


def _section_for(unit: ShortUnit):
    """The material this short came from, or None if it cannot be found.

    Without it a redesign has only the dialogue to work from — which is the
    condition that made frames come out as text in the first place — and the judge
    has nothing to grade against, so it is skipped rather than guessed at.
    """
    for doc in _source_candidates(unit.session_id):
        if not doc.exists():
            continue
        try:
            return find_section(parse_markdown(str(doc)), unit.source_section_id)
        except Exception:
            continue
    return None


def redesign(path: Path, write: bool) -> tuple[int, list[str]]:
    """
    Ask the model for NEW frames for one unit. One paid call. Returns (frames, problems).

    Imported inside the function because it needs an API key: `redraw` with no flags
    must keep working offline, and a module-level import of the visual skill would
    make the free path depend on the paid one.
    """
    from .skills.visuals import design_visuals
    from .schema import Script

    unit = ShortUnit(**json.loads(path.read_text()))
    section = _section_for(unit)
    script = Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)

    # design_visuals grades its own answer and asks again, so a redesign that comes
    # back with the same repeated-frame defect is caught here rather than written to
    # disk and rediscovered by the next sweep. It draws unconditionally: rendering is
    # local and free, and the graders need the frames, not the markup.
    visuals, _ = design_visuals(script, section, previous=unit.visuals)

    # Every beat must still resolve, or the unit will not validate. If the model
    # renamed a ref, keep the old frame for it rather than losing the short.
    for ref, old in unit.visuals.items():
        visuals.setdefault(ref, old)
    unit.visuals = visuals

    problems = _design_problems(unit)
    if write:
        path.write_text(json.dumps(unit.model_dump(), indent=2))
    return len(visuals), problems


def redraw(path: Path, write: bool) -> tuple[int, int, list[str]]:
    """Re-render one unit. Returns (frames redrawn, frames changed, design problems)."""
    unit = ShortUnit(**json.loads(path.read_text()))

    drawn = changed = 0
    for visual in unit.visuals.values():
        if visual.frame is None:
            continue
        svg = render(visual.frame)
        drawn += 1
        if svg != visual.svg:
            changed += 1
            visual.svg = svg

    # The graders that judge the DESIGN, so a unit this pass cannot fix is named
    # rather than quietly re-saved as if it were now fine.
    problems = _design_problems(unit)

    if write and changed:
        path.write_text(json.dumps(unit.model_dump(), indent=2))
    return drawn, changed, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("short_id", nargs="?", help="one unit, default all of them")
    ap.add_argument("--check", action="store_true",
                    help="report what would change and write nothing")
    ap.add_argument("--redesign", action="store_true",
                    help="ask the model for new frames on units that fail a design "
                         "grader. ONE PAID CALL PER SHORT. Implies a redraw.")
    ap.add_argument("--all", action="store_true",
                    help="with --redesign: redesign every unit, including ones whose "
                         "frames already pass. Use after changing the brief or the model.")
    ap.add_argument("--judge", action="store_true",
                    help="with --redesign: re-run the LLM judge afterwards and store "
                         "the verdict. A SECOND PAID CALL PER SHORT.")
    args = ap.parse_args()

    paths = _units(args.short_id)
    if not paths:
        print(f"no unit to redraw in {config.OUTPUT_DIR}"
              + (f" matching {args.short_id!r}" if args.short_id else ""))
        return 1

    if args.redesign and args.check:
        # --check means "write nothing", and a paid call whose result is thrown away
        # is the one combination of these flags that can only ever waste money.
        print("--redesign cannot be combined with --check: the call costs money and "
              "--check would discard the result.")
        return 2

    if args.redesign:
        return _redesign_all(paths, every=args.all, judge=args.judge)

    if args.all or args.judge:
        print("--all and --judge only mean something with --redesign.")
        return 2

    total_changed = 0
    needs_regen: list[str] = []

    for path in paths:
        try:
            drawn, changed, problems = redraw(path, write=not args.check)
        except Exception as e:
            # One malformed unit must not stop the sweep. This runs over a directory
            # that has accumulated units across every schema version the project has
            # had, and the point of the pass is the other twenty.
            print(f"  ! {path.stem}: {type(e).__name__}: {e}")
            continue

        total_changed += changed
        mark = "would redraw" if args.check else "redrew"
        note = f"  {path.stem:44} {mark} {changed}/{drawn} frame(s)"
        print(note if changed else f"  {path.stem:44} unchanged ({drawn} frame(s))")
        for problem in problems:
            print(f"       needs a regenerate: {problem[:150]}")
        if problems:
            needs_regen.append(path.stem)

    if args.check:
        print(f"\n{total_changed} frame(s) would change. Drop --check to write them.")
        return 0

    if total_changed:
        out = feed.build_json()
        print(f"\n{total_changed} frame(s) redrawn; rebuilt {out}")
    else:
        print("\nnothing to redraw — every frame already matches the current layout")

    if needs_regen:
        print(f"\n{len(needs_regen)} unit(s) carry a frame no redraw can fix — the "
              f"template itself is wrong, so they need the visuals designed again:")
        for short_id in needs_regen:
            print(f"  {short_id}")
        print("That costs one model call per short. Rebuild them from the web flow, "
              "or with:\n  python -m shorts.run <doc.md> --topics <n>")
    return 0


def _judge_one(path: Path) -> str:
    """Re-grade one unit with the LLM judge and store the verdict. One paid call."""
    from .schema import Script
    from .skills.audit import judge_script

    unit = ShortUnit(**json.loads(path.read_text()))
    section = _section_for(unit)
    if section is None:
        return "no source on disk — cannot judge"

    script = Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)
    report = judge_script(script, section.text, unit)
    unit.eval = report
    # Same status rule run.py uses, so a unit graded here and a unit graded during a
    # build cannot end up meaning different things.
    unit.status = "audited" if report.passed else "rejected"
    path.write_text(json.dumps(unit.model_dump(), indent=2))

    verdict = "PASS" if report.passed else "REJECT"
    detail = (f"faith={report.faithfulness} clarity={report.clarity} "
              f"pace={report.pace} diagram={report.diagram_correct}")
    out = f"{verdict}  {detail}"
    for problem in report.problems[:3]:
        out += f"\n       ! {problem[:150]}"
    return out


def _redesign_all(paths: list[Path], every: bool = False, judge: bool = False) -> int:
    """Redesign units, then optionally re-grade them."""
    todo = []
    for path in paths:
        try:
            unit = ShortUnit(**json.loads(path.read_text()))
        except Exception as e:
            print(f"  ! {path.stem}: {type(e).__name__}: {e}")
            continue
        if every or _design_problems(unit):
            todo.append(path)
        else:
            print(f"  {path.stem:44} frames already pass — left alone")

    if not todo:
        print("\nnothing to redesign — every unit's frames pass the design graders")
        return 0

    calls = len(todo) * (2 if judge else 1)
    print(f"\nredesigning {len(todo)} unit(s) — {calls} paid call(s) total:")
    fixed = still_bad = reverted = 0
    for path in todo:
        # THE OLD VERDICT AND THE OLD FILE, BOTH KEPT, so a redesign that the judge
        # likes LESS can be undone.
        #
        # This is not hypothetical. In one sweep three units came back clean on every
        # code grader and were rejected by the judge for their NEW frames — one had
        # been passing before with diagram_correct=True. redesign() writes
        # unconditionally, so all three left the reel, and the sweep reported them as
        # progress. Code graders measure whether a frame is structurally a picture;
        # only the judge reads it against the source. When they disagree about a
        # replacement, the version a human already had is the safer one to keep.
        was = path.read_text()
        try:
            before = ShortUnit(**json.loads(was)).eval
        except Exception:
            before = None
        try:
            count, problems = redesign(path, write=True)
        except Exception as e:
            print(f"  ! {path.stem}: {type(e).__name__}: {e}")
            continue
        if problems:
            still_bad += 1
            print(f"  {path.stem:44} {count} frame(s), STILL failing:")
            for problem in problems:
                print(f"       {problem[:150]}")
        else:
            fixed += 1
            print(f"  {path.stem:44} {count} frame(s), clean")

        if judge:
            try:
                print(f"       judge: {_judge_one(path)}")
                after = ShortUnit(**json.loads(path.read_text())).eval
                if (before is not None and after is not None
                        and before.passed and not after.passed):
                    path.write_text(was)
                    reverted += 1
                    if problems:
                        still_bad -= 1
                    else:
                        fixed -= 1
                    print(f"       REVERTED — the judge passed the old frames "
                          f"(f={before.faithfulness} diag={before.diagram_correct}) and "
                          f"rejects the new ones (f={after.faithfulness} "
                          f"diag={after.diagram_correct}); keeping what was there")
            except Exception as e:
                # A judge that has a bad minute must not lose the redesigned frames,
                # which are already written and already paid for.
                print(f"       judge failed: {type(e).__name__}: {e}")

    out = feed.build_json()
    print(f"\n{fixed} clean, {still_bad} still failing a code grader, "
          f"{reverted} reverted as worse; rebuilt {out}")
    if still_bad:
        print("A unit that fails twice usually has a script the pictures cannot "
              "follow — one beat with nothing concrete in it. Rewrite the script "
              "from the review step rather than re-rolling the frames again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
