"""
Story-mode frame renderer — RESTYLE_TO_STORY_REELS.md Steps 5 and 6.

    python -m shorts.story_frames <short_id> --dry-run       # prompts only
    python -m shorts.story_frames <short_id> --sample 5      # 5 diverse shots
    python -m shorts.story_frames <short_id> --all           # every image shot
    python -m shorts.story_frames <short_id> --all --yes     # actually generate
    python -m shorts.story_frames <short_id> --all --yes --no-judge
    python -m shorts.story_frames <short_id> --rejudge s0_reaction

Reads output/<short_id>.story.json (a StoryScript — see shorts/run.py's
build_story_shorts, which writes it), builds each shot's prompt via
skills.visuals.build_shot_prompt, and renders through shorts/imagegen.py —
inheriting its caching, IMAGE_MAX_CALLS_PER_REEL budget, retries, and
SHORTS_STUB=1 stub mode for free.

`text_card`/`recap` shots are never image shots (ReelStage draws them as
overlays — a later phase, not this one). `cta` is handled separately, always,
regardless of --sample/--all: it uses style.mascot_prompt() instead of
build_shot_prompt(), and since that prompt is the SAME string every reel,
shorts/imagegen.py's own content-addressed cache is what makes it "generated
once" — no separate bookkeeping needed here for that.

STEP 6 adds the free pre-checks (shorts/frame_checks.py) and the paid judge
(skills.vision.judge_story_frame) AFTER each generation, with a bounded
regenerate loop — see render_shot_with_judge's own docstring — and
output/<short_id>/frames/judge.json, which _render_shots below writes once
per run (and --rejudge updates for a single shot without spending an image
call).
"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import config, frame_checks, imagegen, preflight, style, usage
from .imagegen import ImageGenError
from .schema import Shot, StoryScript
from .skills.visuals import build_shot_prompt, cast_refs_for_shot
from .skills.vision import judge_story_frame


def load_story(short_id: str) -> StoryScript:
    path = config.OUTPUT_DIR / f"{short_id}.story.json"
    if not path.exists():
        raise SystemExit(f"no such story: {path} (run the story pipeline first)")
    return StoryScript.model_validate_json(path.read_text(encoding="utf-8"))


def _scene_shots(story: StoryScript) -> list[Shot]:
    return [s for s in story.shots if s.kind == "scene"]


def _cta_shot(story: StoryScript) -> Shot | None:
    return next((s for s in story.shots if s.kind == "cta"), None)


def select_sample(scene_shots: list[Shot], n: int) -> list[Shot]:
    """
    A diverse subset of `n` scene shots covering, IN THIS PRIORITY ORDER:
      1. the first `wide` shot (always included — it becomes the setting
         reference for every later shot, so it has to be in any sample that
         will actually be rendered).
      2. one shot of each remaining framing (close_up, two_shot).
      3. one shot featuring each cast member not already covered.
    then padded (in story order) up to `n` with whatever's left.

    These guarantees are non-negotiable — if satisfying all of them needs
    MORE than `n` shots (a real possibility on a short reel with many cast
    members), the guarantees win and MORE than `n` shots are returned; `n`
    is a target, not a hard cap that silently drops a required category.
    """
    selected: list[Shot] = []
    selected_ids: set[str] = set()

    def add(s: Shot) -> None:
        if s.shot_id not in selected_ids:
            selected.append(s)
            selected_ids.add(s.shot_id)

    first_wide = next((s for s in scene_shots if s.framing == "wide"), None)
    if first_wide:
        add(first_wide)

    covered_framings = {s.framing for s in selected}
    for framing in ("wide", "close_up", "two_shot"):
        if framing in covered_framings:
            continue
        match = next((s for s in scene_shots if s.framing == framing), None)
        if match:
            add(match)
            covered_framings.add(framing)

    covered_cast = {c for s in selected for c in s.characters}
    all_cast = {c for s in scene_shots for c in s.characters}
    for name in sorted(all_cast - covered_cast):
        match = next((s for s in scene_shots if name in s.characters), None)
        if match:
            add(match)
            covered_cast.update(match.characters)

    for s in scene_shots:
        if len(selected) >= n:
            break
        add(s)

    order = {s.shot_id: i for i, s in enumerate(scene_shots)}
    selected.sort(key=lambda s: order[s.shot_id])
    return selected


def _prompts_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "image_prompts.json"


def _judge_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "frames" / "judge.json"


def _load_judge_data(short_id: str) -> dict:
    path = _judge_path(short_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_judge_data(short_id: str, data: dict) -> Path:
    path = _judge_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _is_reveal(shot: Shot) -> bool:
    """A shot whose action changes the key object's visible state — this
    project's own established definition (see checks.check_shot_rhythm's
    docstring: "a close_up shot immediately follows every reveal — a shot
    whose story_beat is 'reaction' ... the moment being revealed"), reused
    here rather than invented fresh for Step 8 Part 1's own "never reuse
    across a reveal" rule."""
    return shot.story_beat == "reaction"


def _reveal_epochs(all_shots: list[Shot]) -> dict[str, int]:
    """shot_id -> reveal epoch, computed over the STORY'S OWN chronological
    order (story.shots — every shot, not just whichever subset a particular
    run() call is rendering) so the epoch boundary is the same regardless
    of --sample/--all or shot reordering elsewhere in run(). Every shot up
    to and including a reveal is epoch N; every shot after it is epoch
    N+1 — two shots can only ever land in the same reuse group when their
    epochs match, so nothing straddles a reveal even when every other
    grouping field happens to coincide."""
    epochs: dict[str, int] = {}
    epoch = 0
    for s in all_shots:
        epochs[s.shot_id] = epoch
        if _is_reveal(s):
            epoch += 1
    return epochs


def _reuse_key(shot: Shot, epoch: int) -> tuple:
    """RESTYLE_TO_STORY_REELS.md Step 8 Part 1: shots with the same
    characters + framing + emotion + key_prop (and never crossing a reveal
    — see epoch above) share one rendered image; `shot.camera` is
    DELIBERATELY excluded — it is an animation applied at render time
    (ReelStage), not baked into the generated PNG, and is exactly what is
    meant to differ between a shot and the ones that reuse its image."""
    return (tuple(sorted(shot.characters)), shot.framing, shot.emotion,
           shot.key_prop, epoch)


def render_shot_with_judge(short_id: str, shot: Shot, base_prompt: str,
                           cast_refs: list[Path], setting_ref: Path | None,
                           provider, no_judge: bool) -> dict:
    """
    Generate -> free pre-checks -> paid judge, with a bounded regenerate
    loop — RESTYLE_TO_STORY_REELS.md Step 6 Part 3.

    A PRE-CHECK FAILURE NEVER SPENDS A JUDGE CALL — frame_checks.run_pre_checks
    runs first every attempt, and only a frame that clears every pre-check
    is shown to judge_story_frame at all (Part 1's own reason for existing:
    catching a structural defect free code can already see, before paying a
    model to look at it).

    ON EITHER KIND OF FAILURE, the failure's reasons (pre-check reasons, or
    the judge's own `reasons`) are appended to the prompt as "FIX: ..." and
    the next attempt uses a NEW SEED — attempt 1 has none (the shot's plain,
    reproducible generation); attempt N>1 uses seed=N, which is what makes a
    retry an actual cache MISS instead of silently replaying attempt 1's
    identical, already-rejected image.

    EVERY ATTEMPT — including a failing one — still counts as one real
    generation against config.IMAGE_MAX_CALLS_PER_REEL, enforced by
    imagegen.render_frame itself; this function does nothing extra to cap
    attempts beyond config.STORY_FRAME_ATTEMPTS, and a budget error from
    imagegen propagates up and stops the whole reel, same as Step 5.

    Returns a dict: {"attempts": [...], "final_status": "PASS"|"NEEDS_REVIEW",
    "final_path": str}. NEVER RAISES ON A JUDGE VERDICT — a shot that fails
    every attempt is marked NEEDS_REVIEW with its BEST-SCORING attempt kept
    (ranked by judge total when the judge ran at all, else by how many
    pre-checks passed), and the caller moves on to the next shot; only an
    actual error (missing cast sheet, budget exceeded) stops the reel.

    KEEPING "the best attempt" MEANS KEEPING ITS ACTUAL PIXELS, not just
    remembering which attempt number scored highest — every attempt writes
    to the SAME destination path (short_id + shot_id are all render_frame's
    output path depends on), so attempt 2 overwrites attempt 1's file on
    disk regardless of which one judged better. This function reads each
    attempt's bytes back right after generating it and, if the loop
    exhausts, re-writes the best-scoring attempt's bytes to that path as
    the last step — otherwise "best attempt kept" would just mean "last
    attempt kept" whenever the best one wasn't also the last.
    """
    attempts: list[dict] = []
    best: tuple[float, dict, bytes] | None = None
    feedback: str | None = None
    final_path: Path | None = None
    final_status = "NEEDS_REVIEW"

    for attempt in range(1, max(1, config.STORY_FRAME_ATTEMPTS) + 1):
        prompt = base_prompt if not feedback else f"{base_prompt}\n\nFIX: {feedback}"
        seed = None if attempt == 1 else attempt
        refs = cast_refs + ([setting_ref] if setting_ref else [])
        path = imagegen.render_frame(short_id, shot.shot_id, prompt, refs=refs,
                                     seed=seed, provider=provider)
        frame_bytes = path.read_bytes()

        pre_results = frame_checks.run_pre_checks(path, shot)
        record = {"attempt": attempt, "seed": seed,
                 "pre_checks": [asdict(r) for r in pre_results],
                 "judge": None, "status": None}

        if not frame_checks.all_passed(pre_results):
            feedback = "; ".join(r.reason for r in pre_results if not r.passed)
            record["status"] = "PRECHECK_FAILED"
            attempts.append(record)
            rank = -1.0   # never reached the judge — the worst possible rank
            if best is None or rank > best[0]:
                best = (rank, record, frame_bytes)
            continue

        if no_judge:
            record["status"] = "PASS (no judge)"
            attempts.append(record)
            final_path, final_status = path, "PASS"
            break

        verdict = judge_story_frame(path, shot, cast_refs, setting_ref)
        record["judge"] = verdict.model_dump()
        record["status"] = "PASS" if verdict.passed else "FAIL"
        attempts.append(record)

        rank = float(verdict.total)
        if best is None or rank > best[0]:
            best = (rank, record, frame_bytes)

        if verdict.passed:
            final_path, final_status = path, "PASS"
            break
        feedback = "; ".join(verdict.reasons) or "scored below 3 on at least one axis"
    else:
        # Every attempt ran and none passed — restore the best-scoring
        # attempt's actual bytes (see this function's own docstring on why
        # that's not just `path`, which is always the LAST attempt's).
        final_status = "NEEDS_REVIEW"
        final_path = path
        final_path.write_bytes(best[2])

    return {"attempts": attempts, "final_status": final_status, "final_path": str(final_path)}


def _build_entries(shots: list[Shot], story: StoryScript, cta: Shot | None) -> list[dict]:
    """
    The prompt (and its CAST refs, in order) for every shot about to be
    generated — shared by the dry-run preview and the real run, so
    image_prompts.json always documents the exact prompts used, whichever
    mode wrote it. Deliberately WITHOUT the setting reference: that path
    doesn't exist yet at prompt-build time (it's the OUTPUT of rendering the
    first wide shot), so this file documents the base prompt + cast refs —
    the setting-ref augmentation is the fixed, documented rule applied at
    render time in `run()` below, not a second source of truth to keep synced.
    """
    entries = [{"shot_id": s.shot_id, "prompt": build_shot_prompt(s, story),
               "refs": [str(r) for r in cast_refs_for_shot(s)]}
              for s in shots]
    if cta:
        entries.append({"shot_id": cta.shot_id, "prompt": style.mascot_prompt(), "refs": []})
    return entries


def _print_summary(short_id: str, judge_data: dict, cost_totals: dict) -> None:
    passed = [sid for sid, r in judge_data.items() if r["final_status"] == "PASS"]
    needs_review = [sid for sid, r in judge_data.items() if r["final_status"] == "NEEDS_REVIEW"]

    # Judge calls are counted from judge_data itself (every attempt whose
    # "judge" field is non-null), NOT from usage.since() — under
    # SHORTS_STUB=1, llm.ask_json's stub path returns before usage.record()
    # ever runs (see usage.py's own module docstring on this), so the usage
    # ledger reports 0 judge calls even though the judge genuinely ran.
    # Image calls ARE reliable from usage.since(): imagegen.generate_bytes
    # calls usage.record_image() directly, unconditionally, including for
    # the stub provider.
    judge_calls = sum(1 for r in judge_data.values() for a in r["attempts"]
                      if a.get("judge") is not None)
    image_calls = sum(v["calls"] for k, v in cost_totals["by_label"].items()
                      if k.startswith("image:"))

    print(f"\n=== {short_id}: summary ===")
    print(f"passed: {len(passed)} {passed}")
    print(f"needs_review: {len(needs_review)} {needs_review}")
    print(f"total image calls: {image_calls}")
    print(f"total judge calls: {judge_calls}")
    print(f"estimated cost: ${cost_totals['cost']:.4f}")


def run(short_id: str, shots: list[Shot], story: StoryScript, dry_run: bool,
       yes: bool, include_cta: bool = True, no_judge: bool = False) -> int:
    provider = imagegen.select_provider()
    cta = _cta_shot(story) if include_cta else None
    # WORST CASE: every shot uses every one of its STORY_FRAME_ATTEMPTS
    # regenerates — the honest ceiling to show before a human types --yes,
    # not the (usually much lower) number of calls a clean run actually makes.
    max_attempts = max(1, config.STORY_FRAME_ATTEMPTS)
    total_calls = len(shots) * max_attempts + (1 if cta else 0)
    per_call = imagegen.estimate_cost(provider)

    print(f"Reel: {short_id}")
    print(f"Shots: {[s.shot_id for s in shots]}" + (" + mascot (cta)" if cta else ""))
    print(f"Planned calls: {total_calls} (worst case: {len(shots)} shot(s) x "
         f"{max_attempts} attempt(s){' + 1 mascot' if cta else ''})")
    print(f"Model: {provider.name}/{provider.model}")
    print(f"Estimated cost: {total_calls} call(s) x ${per_call:.4f} = "
         f"${total_calls * per_call:.4f}")

    entries = _build_entries(shots, story, cta)
    out = _prompts_path(short_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    if dry_run:
        print(f"wrote {len(entries)} prompt(s) to {out} — no provider called")
        return 0

    print(f"wrote {len(entries)} prompt(s) to {out}")

    # RESTYLE_TO_STORY_REELS.md Step 8 Part 0 #4: the shared pre-flight
    # gate — prints + persists a merged output/<short_id>/preflight.json
    # entry for THIS job ("frames"), on top of (not replacing) the
    # existing Reel/Shots/Planned calls/Model/Estimated cost block above,
    # then requires --yes exactly like the manual gate it replaces did.
    image_plan = preflight.ModelPlan(label=f"image:{provider.name}", model=provider.model,
                                     planned_calls=total_calls, cost_per_call=per_call)
    judge_plan = preflight.ModelPlan(
        label="story_frame_judge", model=config.MODEL_STORY_VISION_JUDGE,
        planned_calls=0 if no_judge else len(shots) * max_attempts,
        # RESTYLE_TO_STORY_REELS.md Step 9 Fixes round 14: 2900/600, not the
        # old 800/300 — this is a VISION call (a rendered PNG frame embedded
        # alongside the text prompt), not a plain text one, and a real
        # sample stage's own logged calls averaged 2861 input / 585 output
        # tokens (output/usage.json, 53 real gemini-3.8-flash rows) — the
        # 800/300 guess was sized for a text-only judge and under-counted
        # by roughly 2.6x on top of the (separately fixed) missing price-
        # table entry.
        cost_per_call=preflight.text_cost_per_call(config.MODEL_STORY_VISION_JUDGE, 2900, 600))
    if not preflight.run_preflight("frames", short_id, [image_plan, judge_plan], yes):
        return 1

    # RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #1: the per-reel image-call
    # budget is COMPUTED here (shots x attempts + mascot + headroom), not
    # left at imagegen's flat fallback — unless the environment set
    # IMAGE_MAX_CALLS_PER_REEL explicitly, which always wins.
    if not config.IMAGE_MAX_CALLS_PER_REEL_IS_EXPLICIT:
        budget = config.default_image_budget(len(shots), max_attempts, has_mascot=bool(cta))
        imagegen.set_reel_budget(short_id, budget)
        print(f"Image call budget for this reel: {budget} "
             f"({len(shots)} x {max_attempts} + {1 if cta else 0} mascot + "
             f"{config.IMAGE_CALLS_HEADROOM} headroom)")

    cursor = usage.mark()

    # THE SETTING REFERENCE. The first `wide` shot's rendered image is
    # generated first (regardless of where it sits in `shots`' own order —
    # every later shot needs it), then passed as an EXTRA reference, after
    # the cast refs, to every shot rendered after it.
    wide_first = next((s for s in shots if s.framing == "wide"), None)
    ordered = shots
    if wide_first:
        ordered = [wide_first] + [s for s in shots if s.shot_id != wide_first.shot_id]

    judge_data = _load_judge_data(short_id)
    setting_ref: Path | None = None
    # RESTYLE_TO_STORY_REELS.md Step 8 Part 1: shots sharing characters +
    # framing + emotion + key_prop (and never straddling a reveal — see
    # _reveal_epochs) render ONE image; every later shot in the same group
    # gets that image copied to its own output path instead of a fresh
    # provider call. epochs is computed over story.shots (full chronological
    # order), not `ordered` (which the setting-reference logic above may
    # have reshuffled) or `shots` (which may be a --sample subset).
    epochs = _reveal_epochs(story.shots)
    group_representative: dict[tuple, str] = {}
    unique_images = 0
    reused_shots = 0
    for s in ordered:
        key = _reuse_key(s, epochs.get(s.shot_id, 0))
        rep_shot_id = group_representative.get(key) if config.STORY_IMAGE_REUSE else None
        if rep_shot_id is not None:
            rep_result = judge_data[rep_shot_id]
            dest = imagegen._frame_path(short_id, s.shot_id)
            src = Path(rep_result["final_path"])
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())
            result = dict(rep_result)
            result["final_path"] = str(dest)
            result["reused_from"] = rep_shot_id
            judge_data[s.shot_id] = result
            reused_shots += 1
            print(f"  {s.shot_id}: REUSED from {rep_shot_id} "
                 f"({result['final_status']}) -> {dest}")
            continue

        prompt = build_shot_prompt(s, story)
        cast_refs = cast_refs_for_shot(s)
        result = render_shot_with_judge(short_id, s, prompt, cast_refs, setting_ref,
                                        provider, no_judge)
        judge_data[s.shot_id] = result
        unique_images += 1
        group_representative[key] = s.shot_id
        print(f"  {s.shot_id}: {result['final_status']} ({len(result['attempts'])} "
             f"attempt(s)) -> {result['final_path']}")
        if setting_ref is None and s.framing == "wide" and result["final_status"] == "PASS":
            setting_ref = Path(result["final_path"])

    new_cost = round(usage.since(cursor)["cost"], 4)
    print(f"\nImage reuse: {unique_images} unique image(s) for {len(ordered)} "
         f"image shot(s) ({reused_shots} reused" +
         ("" if config.STORY_IMAGE_REUSE else ", STORY_IMAGE_REUSE=0 — disabled") +
         f") — new cost so far: ${new_cost:.4f}")

    if cta:
        path = imagegen.render_frame(short_id, cta.shot_id, style.mascot_prompt(),
                                     provider=provider)
        print(f"  wrote {path} (mascot)")

    judge_path = _write_judge_data(short_id, judge_data)
    print(f"wrote {judge_path}")

    _print_summary(short_id, judge_data, usage.since(cursor))
    return 0


def cmd_rejudge(short_id: str, shot_id: str) -> int:
    """
    Re-check ONE shot's ALREADY-GENERATED frame — no new image call, so it
    costs nothing beyond (at most) one judge call. Useful after a prompt/
    rubric change, or to double-check a NEEDS_REVIEW shot by eye and then
    re-run the judge on the exact same pixels.
    """
    story = load_story(short_id)
    shot = next((s for s in story.shots if s.shot_id == shot_id), None)
    if shot is None:
        raise SystemExit(f"no such shot in {short_id}: {shot_id}")

    frame_path = config.OUTPUT_DIR / short_id / "frames" / f"shot_{shot_id}.png"
    if not frame_path.exists():
        raise SystemExit(f"no generated frame for {shot_id}: {frame_path} "
                         f"(render it first)")

    cast_refs = cast_refs_for_shot(shot)
    first_wide = next((s for s in _scene_shots(story) if s.framing == "wide"), None)
    setting_ref = None
    if first_wide and first_wide.shot_id != shot_id:
        wide_path = config.OUTPUT_DIR / short_id / "frames" / f"shot_{first_wide.shot_id}.png"
        if wide_path.exists():
            setting_ref = wide_path

    pre_results = frame_checks.run_pre_checks(frame_path, shot)
    record = {"attempt": "rejudge", "seed": None,
             "pre_checks": [asdict(r) for r in pre_results], "judge": None, "status": None}

    if not frame_checks.all_passed(pre_results):
        record["status"] = "PRECHECK_FAILED"
        final_status = "NEEDS_REVIEW"
    else:
        verdict = judge_story_frame(frame_path, shot, cast_refs, setting_ref)
        record["judge"] = verdict.model_dump()
        record["status"] = "PASS" if verdict.passed else "FAIL"
        final_status = "PASS" if verdict.passed else "NEEDS_REVIEW"

    data = _load_judge_data(short_id)
    existing = data.get(shot_id, {"attempts": []})
    data[shot_id] = {"attempts": existing.get("attempts", []) + [record],
                    "final_status": final_status, "final_path": str(frame_path)}
    path = _write_judge_data(short_id, data)
    print(f"{shot_id}: {final_status} — wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.story_frames",
        description="Render (or preview) one story reel's image frames.")
    p.add_argument("short_id", help="the reel's short_id — reads "
                                    "output/<short_id>.story.json")
    p.add_argument("--dry-run", action="store_true",
                   help="build prompts only and write them to disk; call no provider")
    p.add_argument("--sample", type=int, metavar="N",
                   help="render a diverse sample of N scene shots")
    p.add_argument("--all", action="store_true", help="render every scene shot")
    p.add_argument("--yes", action="store_true",
                   help="skip the cost confirmation and actually call a provider")
    p.add_argument("--no-judge", action="store_true",
                   help="skip skills.vision.judge_story_frame — pre-checks still run")
    p.add_argument("--rejudge", metavar="SHOT_ID",
                   help="re-check one already-generated shot's frame; no new image call")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.rejudge:
        try:
            return cmd_rejudge(args.short_id, args.rejudge)
        except ImageGenError as e:
            raise SystemExit(str(e))

    story = load_story(args.short_id)
    scene_shots = _scene_shots(story)

    if args.sample is not None:
        shots = select_sample(scene_shots, args.sample)
    elif args.all or args.dry_run:
        # bare --dry-run (no --sample/--all given) previews EVERYTHING —
        # the point of a dry run is seeing the whole reel's prompts at once.
        shots = scene_shots
    else:
        build_parser().print_help()
        return 1

    try:
        return run(args.short_id, shots, story, args.dry_run, args.yes,
                  no_judge=args.no_judge)
    except ImageGenError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    raise SystemExit(main())
