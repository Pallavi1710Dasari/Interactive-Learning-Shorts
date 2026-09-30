"""
shorts/story_reel.py — RESTYLE_TO_STORY_REELS.md Step 9. One-command story
reel runner.

    python -m shorts.story_reel <markdown_path> [--topic <short_id>]
        [--from <stage>] [--force-stage <stage>] [--yes] [--base-url URL]

Runs every story-mode stage, in order, for ONE reel:

    1. setup    parse, select ONE topic, understanding_for.
    2. mapping  plan_story_mapping (+ its own metaphor-judge gate).
    3. shots    write_story_shots + run_story_graders + audit_story.
    4. sample   story_frames --sample 5 (with judge).
    5. frames   story_frames --all (with judge, Step 8's image reuse).
    6. audio    story_audio (Chatterbox -> Kokoro fallback, Step 8).
    7. render   shorts/video.py -> output/<short_id>/reel_STORY.mp4 (see
                video.mp4_path — the _STORY suffix is what makes a story
                reel's mp4 unmistakable from an explainer one's reel.mp4).
    8. report   real spend per stage/model + NEEDS_REVIEW -> run_report.json.

RESUMABLE: each stage's own output on disk (a marker file for sample/frames,
the real artifact for the rest) is checked before running it — an already-
done stage is skipped and its saved output is loaded instead, unless
--force-stage names it (which also forces every stage AFTER it, since their
inputs would otherwise be stale) or --from starts the loop past it (which
trusts everything before that point without even checking).

MONEY STAGES (2/3/4/5, per this step's own spec — "setup" also spends on
topic selection + understanding_for, but is not gated the same way; see
docs/RUNBOOK_STORY.md) each print shorts/preflight.py's own summary and
require confirmation BEFORE the spend — --yes answers every prompt
automatically but never skips a preflight printout. config.MAX_REEL_USD is
checked against REAL usage.py totals (this reel's own running total, not
the whole project's) before every one of those stages: a stage whose own
worst-case pre-flight cost would push the reel over the cap is refused
before a single call.

Stage 1 (setup) covers explainer mode's own "parse, select, understanding,
teaching_approach" list MINUS teaching_approach — that step is explainer-
only (see run.py's own --gate-teaching-approach docstring: "Only wired into
the fresh-selection path... reels are not built for these"); story mode's
build_one_story (run.py) never calls it either, so this runner does not
invent a call that does not exist elsewhere in the pipeline.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from . import cast_sheets, checks, config, imagegen, preflight, story_audio, story_frames, story_voices, usage, video
from .parse import find_section, parse_markdown, story_evidence_pool
from .schema import ConceptMappingSet, SectionUnderstanding, StoryScript, Topic
from .skills.audit import audit_story
from .skills.script import (MAX_HOOK_FIX_RETRIES, MAX_STORY_JUDGE_RETRIES,
                            MAX_STORY_MAPPING_RETRIES, plan_story_mapping,
                            regenerate_hook_line, write_story_shots)
from .skills.select import select_topics_with_selections
from .skills.understanding import understanding_for
from .skills.visuals import build_shot_prompt, cast_refs_for_shot

STAGE_ORDER = ["setup", "mapping", "shots", "sample", "frames", "audio", "render", "report"]
MONEY_STAGES = {"mapping", "shots", "sample", "frames"}


# ============================================================ prerequisites

def check_prerequisites() -> tuple[list[str], list[str]]:
    """
    (blocking, warnings) — this step's own checklist, run once before stage
    1. Blocking items are skipped entirely under SHORTS_STUB=1 (nothing real
    is ever called there, so there is nothing to be missing). Cast sheets
    are NOT a blocking item here — see ensure_cast_sheets (Part 2), which
    offers to build them rather than just stopping. Voice refs, the logo,
    and BRAND_HANDLE are warn-only: Step 8's own Chatterbox->Kokoro
    fallback and logo-placeholder both already degrade gracefully.
    """
    blocking: list[str] = []
    warnings: list[str] = []

    if not config.STUB:
        if not config.ANTHROPIC_API_KEY:
            blocking.append(
                "ANTHROPIC_API_KEY is not set (text/LLM calls — mapping, shots, "
                "judges — all go through this, including via an OpenRouter-style "
                "gateway set as ANTHROPIC_BASE_URL). Copy .env.example to .env.")
        if config.IMAGE_PROVIDER == "gemini" and not config.GEMINI_API_KEY:
            blocking.append(
                "GEMINI_API_KEY is not set (IMAGE_PROVIDER=gemini, the default). "
                "Set it, or switch IMAGE_PROVIDER to cloudflare.")
        elif config.IMAGE_PROVIDER == "cloudflare" and not (
                config.CF_ACCOUNT_ID and config.CF_API_TOKEN):
            blocking.append(
                "CF_ACCOUNT_ID/CF_API_TOKEN are not both set (IMAGE_PROVIDER=cloudflare).")

    missing_sheets = [n for n in cast_sheets.CAST_ORDER
                      if not cast_sheets._approved_path(n).exists()]
    if missing_sheets:
        warnings.append(f"no approved cast sheet yet for: {missing_sheets} "
                        f"(this runner will offer to build them)")

    missing_voices = [n for n in story_voices.CAST_ROLES
                      if not (config.CAST_VOICE_DIR / f"{n.lower()}.wav").exists()]
    if missing_voices:
        warnings.append(
            f"no Chatterbox reference clip in assets/voices/ for: {missing_voices} "
            f"— falls back to Kokoro automatically (Step 8); run "
            f"`python -m shorts.voice_refs --from-kokoro` for a cloned voice instead")

    logo = config.ROOT / "assets" / "brand" / "logo.png"
    if not logo.exists():
        warnings.append(f"{logo} is missing — the reel will show a placeholder logo")

    if config.BRAND_HANDLE == "@learnthesimpleway":
        warnings.append("BRAND_HANDLE is still the default placeholder "
                        "'@learnthesimpleway' — set a real one in .env")

    if shutil.which("tesseract") is None:
        warnings.append("tesseract is not on PATH — the on-screen-text pre-check "
                        "will skip (frames are not checked for stray on-screen text)")

    return blocking, warnings


def print_checklist(blocking: list[str], warnings: list[str]) -> None:
    print("\n=== Prerequisite checklist ===")
    if not blocking and not warnings:
        print("  all checks passed.")
        return
    for w in warnings:
        print(f"  ! {w}")
    for b in blocking:
        print(f"  X {b}")


# =================================================================== part 2

def ensure_cast_sheets(yes: bool) -> bool:
    """
    RESTYLE_TO_STORY_REELS.md Step 9 Part 2. Offers to build any missing
    cast sheet: compare (optional, skipped under --yes — it is the most
    expensive option and this step's own money-stage list never includes
    it) -> candidates -> show paths -> ask which number -> approve. Rahul
    first, then Riya/System (which reference rahul.png — see
    cast_sheets._reference_for), matching CAST_ORDER's own fixed order.
    """
    missing = [n for n in cast_sheets.CAST_ORDER if not cast_sheets._approved_path(n).exists()]
    if not missing:
        return True

    print(f"\n=== Cast sheets missing: {missing} ===")
    if not _confirm("Build the missing cast sheet(s) now?", yes):
        print("  skipping — a later stage that needs a sheet will fail clearly, naming it.")
        return False

    for name in cast_sheets.CAST_ORDER:
        if cast_sheets._approved_path(name).exists():
            continue
        lower = name.lower()
        print(f"\n--- {name} ---")

        # compare — optional, extra cost, always declined under --yes (batch
        # runs get the default provider's candidates only, not a comparison).
        if _confirm(f"Compare providers for {name} first (extra cost)?", False):
            cast_sheets.cmd_compare(lower, dry_run=False, yes=False)   # prints its own cost
            if _confirm("Proceed with that comparison?", yes):
                cast_sheets.cmd_compare(lower, dry_run=False, yes=True)
                print(f"  see {cast_sheets.COMPARE_DIR}/ for the compared images")

        cast_sheets.cmd_candidates(3, lower, dry_run=False, yes=False)   # prints its own cost
        if not _confirm(f"Generate 3 candidate sheet(s) for {name}?", yes):
            return False
        if cast_sheets.cmd_candidates(3, lower, dry_run=False, yes=True) != 0:
            return False

        paths = [cast_sheets._candidate_path(name, i) for i in range(1, 4)]
        print(f"  candidates: {[str(p) for p in paths]}")
        choice = "1" if yes else (input(f"  which number to approve for {name}? [1-3] ").strip() or "1")
        if cast_sheets.cmd_approve(lower, choice) != 0:
            return False
    return True


# ======================================================================= io

def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        print(f"{prompt} [y/N] y   (--yes)")
        return True
    if not sys.stdin.isatty():
        print(f"{prompt} [y/N] — non-interactive session, defaulting to N. "
             f"Pass --yes to proceed automatically.")
        return False
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


def _money_gate(stage: str, short_id: str, plan: list, yes: bool, reel_cursor: int) -> bool:
    """The shared pre-spend gate every money stage (2/3/4/5) uses: print +
    persist the pre-flight plan (ALWAYS, even under --yes), refuse if it
    would push this reel's running total past config.MAX_REEL_USD, then
    ask for confirmation."""
    built = preflight.build_plan(stage, short_id, plan)
    preflight.print_plan(built)
    preflight.write_preflight_json(short_id, built)

    spent = usage.since(reel_cursor)["cost"]
    projected = round(spent + built["total_cost"], 4)
    if projected > config.MAX_REEL_USD:
        print(f"  MAX_REEL_USD (${config.MAX_REEL_USD:.2f}) would be exceeded: "
             f"${spent:.4f} spent on this reel so far + ${built['total_cost']:.4f} "
             f"for {stage} = ${projected:.4f}. Stopping before any call.")
        return False
    return _confirm(f"Proceed with the {stage} stage (est. ${built['total_cost']:.4f})?", yes)


def _frames_plan(shots: list, has_cta: bool) -> list:
    provider = imagegen.select_provider()
    max_attempts = max(1, config.STORY_FRAME_ATTEMPTS)
    total_calls = len(shots) * max_attempts + (1 if has_cta else 0)
    per_call = imagegen.estimate_cost(provider)
    return [
        preflight.ModelPlan(f"image:{provider.name}", provider.model, total_calls, per_call),
        preflight.ModelPlan("story_frame_judge", config.MODEL_STORY_VISION_JUDGE,
                            len(shots) * max_attempts,
                            preflight.text_cost_per_call(config.MODEL_STORY_VISION_JUDGE, 800, 300)),
    ]


# ================================================================== stage 1

def _run_setup(sections: list, short_id: str | None) -> tuple[Topic, "Section", SectionUnderstanding | None]:
    topic_list, _notes, _selections = select_topics_with_selections(sections, target=1)
    topic = topic_list.topics[0]
    section = find_section(sections, topic.source_section_id)
    understanding = understanding_for(section, source_text=section.text)
    return topic, section, understanding


def _reel_exists(short_id: str) -> bool:
    """RESTYLE_TO_STORY_REELS.md Step 9 Fix 4: does ANY reel — explainer or
    story — already occupy this id? Checked against every shape either mode
    persists under: an explainer ShortUnit (<id>.json), a story StoryScript
    (<id>.story.json), or either mode's own output/<id>/ directory (frames,
    audio, reel.mp4, ...)."""
    return ((config.OUTPUT_DIR / f"{short_id}.json").exists()
           or (config.OUTPUT_DIR / f"{short_id}.story.json").exists()
           or (config.OUTPUT_DIR / short_id).exists())


def _next_free_story_id(base_id: str) -> str:
    """Story reels live in their OWN id namespace, <short_id>__story,
    separate by construction from any explainer reel that happens to share
    the same underlying topic id — Step 9 Fix 4's own rule. If THAT id is
    already taken too (a previous story run on the very same topic), a
    numbered suffix is appended until a genuinely free id is found. Never
    returns an id _reel_exists() says is already occupied, by either mode."""
    candidate = f"{base_id}__story"
    if not _reel_exists(candidate):
        return candidate
    n = 2
    while _reel_exists(f"{candidate}_{n}"):
        n += 1
    return f"{candidate}_{n}"


def _setup_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "setup.json"


def _save_setup(short_id: str, topic: Topic, section, understanding) -> None:
    path = _setup_path(short_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "topic": topic.model_dump(),
        "section_id": section.section_id,
        "understanding": understanding.model_dump() if understanding else None,
    }, indent=2), encoding="utf-8")


def _load_setup(short_id: str, sections: list):
    state = json.loads(_setup_path(short_id).read_text(encoding="utf-8"))
    topic = Topic(**state["topic"])
    section = find_section(sections, state["section_id"])
    understanding = (SectionUnderstanding(**state["understanding"])
                     if state.get("understanding") else None)
    return topic, section, understanding


def _fix_stale_hook_line(short_id: str, mapping: ConceptMappingSet, topic: Topic, section,
                         understanding, pool_text: str, yes: bool,
                         reel_cursor: int) -> ConceptMappingSet | None:
    """
    A RESUMED mapping (loaded from output/<short_id>.mapping.json rather than
    freshly generated this run) was approved under WHATEVER checks.check_hook
    rule existed at approval time. If that rule has since tightened (e.g. the
    4-opener rule), the mapping's hook_line can now permanently fail
    checks.run_story_graders — and since write_story_shots only ever COPIES
    mapping.hook_line onto the shots verbatim (never regenerates it), NO
    number of `--force-stage shots` retries can ever fix it; the same stale
    line would fail check_hook identically every single time.

    Caught HERE, before stage_shots ever runs a single (paid) shots call, by
    validating the resumed mapping's hook_line against the CURRENT check_hook
    the moment it's loaded. skills.script.regenerate_hook_line is a narrow,
    single-field repair — see its own docstring for why that's safe here
    (check_hook never inspects the rest of the mapping) and cheaper than
    re-running the whole paid mapping+judge gate over one sentence. Gated by
    the same money-gate + human-approval pattern every other paid step in
    this runner uses; a decline leaves the mapping file untouched on disk
    (same "declining means try again, not skip ahead" contract as
    stage_mapping/stage_shots).
    """
    hook_verdict = checks.check_hook(mapping.hook_line, technical_term=mapping.technical_term)
    if hook_verdict.passed:
        return mapping

    print(f"\n  hook_line {mapping.hook_line!r} on the resumed mapping no "
         f"longer passes check_hook ({hook_verdict.reason}) — it was likely "
         f"approved under an older rule. write_story_shots never regenerates "
         f"this field, so shots would fail identically no matter how many "
         f"times it's retried. Regenerating ONLY hook_line; the rest of the "
         f"approved mapping (cast, setting, entries) is untouched.")
    plan = [preflight.ModelPlan("story_hook_fix", config.MODEL_GENERATOR, MAX_HOOK_FIX_RETRIES,
                                preflight.text_cost_per_call(config.MODEL_GENERATOR, 1500, 100))]
    if not _money_gate("hook_fix", short_id, plan, yes, reel_cursor):
        return None

    new_hook = regenerate_hook_line(mapping, topic, section, understanding, pool_text)
    if new_hook is None:
        print("  GIVING UP — no replacement hook_line passed check_hook.")
        return None

    print(f"  new hook_line: {new_hook!r}")
    if not _confirm("Approve corrected hook_line?", yes):
        print(f"  Stopped after hook_line fix — {short_id}.mapping.json was NOT "
             f"changed; rerun with --topic {short_id} to try again.")
        return None

    mapping.hook_line = new_hook
    (config.OUTPUT_DIR / f"{short_id}.mapping.json").write_text(
        mapping.model_dump_json(indent=2), encoding="utf-8")
    return mapping


# ================================================================== stage 2

def stage_mapping(short_id: str, topic: Topic, section, understanding,
                  pool_text: str, yes: bool, reel_cursor: int) -> ConceptMappingSet | None:
    plan = [
        preflight.ModelPlan("story_mapping", config.MODEL_GENERATOR,
                            MAX_STORY_MAPPING_RETRIES * (MAX_STORY_JUDGE_RETRIES + 1),
                            preflight.text_cost_per_call(config.MODEL_GENERATOR, 2500, 1500)),
        preflight.ModelPlan("story_judge", config.MODEL_STORY_JUDGE, MAX_STORY_JUDGE_RETRIES + 1,
                            preflight.text_cost_per_call(config.MODEL_STORY_JUDGE, 800, 600)),
    ]
    if not _money_gate("mapping", short_id, plan, yes, reel_cursor):
        return None

    mapping = plan_story_mapping(topic, section, understanding=understanding, source_text=pool_text)
    if mapping is None:
        print("  GIVING UP — no mapping passed checks.check_mapping / the metaphor judge.")
        return None

    print(f"\n=== PAUSE: mapping for {short_id} ===")
    print(f"hook_line: {mapping.hook_line!r}")
    print(f"setting: {mapping.setting}   system_name: {mapping.system_name}")
    print(f"candidates ({len(mapping.candidates)}):")
    for c in mapping.candidates:
        flag = " <- chosen" if c.chosen else ""
        print(f"  - {c.name}: familiarity={c.familiarity} faithfulness={c.faithfulness} "
             f"drawability={c.drawability} drama={c.drama} total={c.total}{flag}")
    print(f"mapping ({len(mapping.mapping)} entries):")
    for m in mapping.mapping:
        print(f"  - actor={m.actor}  {m.concept_rule}")
        print(f"      event: {m.metaphor_event}")
        print(f"      lesson: {m.lesson_line}")

    if not _confirm("Approve mapping?", yes):
        print(f"Stopped after mapping — rerun with --topic {short_id} to continue "
             f"(the mapping was NOT saved — declining means try again, not skip ahead).")
        return None

    # Written ONLY on approval — a DECLINED mapping must not look "already
    # done" to a later resume (see _needs's own exists-check): the whole
    # point of "N = stop (rerun later)" is that a rerun shows this SAME
    # pause again, not silently treats a rejected mapping as final.
    (config.OUTPUT_DIR / f"{short_id}.mapping.json").write_text(
        mapping.model_dump_json(indent=2), encoding="utf-8")
    return mapping


# ================================================================== stage 3

def stage_shots(short_id: str, mapping: ConceptMappingSet, topic: Topic, section,
                understanding, pool_text: str, yes: bool, reel_cursor: int) -> StoryScript | None:
    plan = [preflight.ModelPlan("story_shots", config.MODEL_GENERATOR, 1,
                                preflight.text_cost_per_call(config.MODEL_GENERATOR, 4000, 6000))]
    if not _money_gate("shots", short_id, plan, yes, reel_cursor):
        return None

    story = write_story_shots(mapping, topic, section, understanding=understanding,
                              source_text=pool_text, session_id=short_id)
    # STEP 9 FIX 4: write_story_shots sets StoryScript.short_id from
    # topic.id (correct for run.py's own unnamespaced flow) — this
    # runner's `short_id` can be topic.id PLUS a __story suffix (or a
    # numbered one), so the persisted story must carry THAT id, matching
    # the file it is about to be saved as (output/<short_id>.story.json)
    # and the directory every later stage reads/writes under.
    story.short_id = short_id
    # STEP 9 FIX 2: technical_term comes from the story's OWN mapping
    # (story.technical_term), not topic.concept — see run.py's own note.
    results, report = audit_story(story, pool_text, technical_term=story.technical_term)
    failed = [r for r in results if not r.passed]
    judge_ran = report is not None   # audit_story only judges once every free check passed
    judge_failed = judge_ran and not report.passed
    if failed or judge_failed:
        # STEP 9 FIXES ROUND 5: a real run had every one of the 15 free
        # checks in `results` print PASS, so the ONLY thing that could have
        # failed was judge_story_metaphors — but its own StoryEvalReport
        # (verdicts + per-entry problem text) was never printed or
        # persisted anywhere, so there was no way to see WHY it rejected
        # the script short of re-instrumenting the code and paying for
        # another real call. Printing it here, unconditionally whenever
        # the judge is the thing that failed, is the fix; results is still
        # printed too so a free-check failure remains visible alongside a
        # judge failure if both happen in the same run.
        reason = ("the metaphor judge" if judge_failed and not failed else
                  "the free story graders" if failed and not judge_failed else
                  "the free story graders AND the metaphor judge")
        print(f"  GIVING UP — the final shots failed {reason}:")
        for r in results:
            print(f"    {r}")
        if judge_failed:
            print("  metaphor judge verdicts:")
            for v in report.verdicts:
                verdict = "PASS" if v.faithful else "REJECT"
                print(f"    [{verdict}] {v.concept_rule}"
                     + (f" — {v.problem}" if not v.faithful and v.problem else ""))
        return None

    print(f"\n=== PAUSE: read-aloud script for {short_id} "
         f"({story.estimated_seconds:.1f}s) ===")
    for shot in story.shots:
        text = story_audio.spoken_text(shot)
        if text:
            print(f"  {checks.shot_speaker(shot)}: {text}")
    print("check results:")
    for r in results:
        print(f"  {r}")
    print(f"  metaphor judge: {'PASS' if report.passed else 'REJECT'}")

    if not _confirm("Approve shots?", yes):
        print(f"Stopped after shots — rerun with --topic {short_id} to continue "
             f"(the shots were NOT saved — declining means try again, not skip ahead).")
        return None

    # Written ONLY on approval — same reasoning as stage_mapping's own note.
    (config.OUTPUT_DIR / f"{short_id}.story.json").write_text(
        story.model_dump_json(indent=2), encoding="utf-8")
    return story


# ================================================================== stage 4

def stage_sample(short_id: str, story: StoryScript, yes: bool, reel_cursor: int) -> bool:
    scene_shots = story_frames._scene_shots(story)
    sample_shots = story_frames.select_sample(scene_shots, 5)
    cta = story_frames._cta_shot(story)
    plan = _frames_plan(sample_shots, has_cta=bool(cta))
    if not _money_gate("sample", short_id, plan, yes, reel_cursor):
        return False

    code = story_frames.main([short_id, "--sample", "5", "--yes"])
    if code != 0:
        return False

    data = story_frames._load_judge_data(short_id)
    print(f"\n=== PAUSE: sample frames for {short_id} ===")
    for shot_id, rec in data.items():
        judge = rec["attempts"][-1].get("judge") if rec["attempts"] else None
        score = judge.get("total") if judge else None
        print(f"  {shot_id}: {rec['final_status']} (score={score}) -> {rec['final_path']}")

    if not _confirm("Approve sample?", yes):
        print(f"Stopped after sample — rerun with --topic {short_id} to continue "
             f"(not marked done — a rerun regenerates the sample; identical prompts "
             f"are a free cache hit in imagegen.py, so this rarely re-spends).")
        return False
    # Written ONLY on approval — same "decline means try again" reasoning as
    # stage_mapping/stage_shots.
    (config.OUTPUT_DIR / short_id / "sample.done").write_text("ok", encoding="utf-8")
    return True


# ================================================================== stage 5

def _regenerate_shot(short_id: str, story: StoryScript, shot_id: str) -> None:
    shot = next((s for s in story.shots if s.shot_id == shot_id), None)
    if shot is None:
        print(f"  no such shot: {shot_id}")
        return
    provider = imagegen.select_provider()
    per_call = imagegen.estimate_cost(provider)
    max_attempts = max(1, config.STORY_FRAME_ATTEMPTS)
    print(f"  regenerating {shot_id}: up to {max_attempts} call(s) @ ${per_call:.4f} "
         f"= ${max_attempts * per_call:.4f} (worst case)")

    prompt = build_shot_prompt(shot, story)
    cast_refs = cast_refs_for_shot(shot)
    scene_shots = story_frames._scene_shots(story)
    wide_first = next((s for s in scene_shots if s.framing == "wide"), None)
    setting_ref = None
    if wide_first and wide_first.shot_id != shot_id:
        p = config.OUTPUT_DIR / short_id / "frames" / f"shot_{wide_first.shot_id}.png"
        if p.exists():
            setting_ref = p

    result = story_frames.render_shot_with_judge(short_id, shot, prompt, cast_refs,
                                                 setting_ref, provider, no_judge=False)
    data = story_frames._load_judge_data(short_id)
    data[shot_id] = result
    story_frames._write_judge_data(short_id, data)
    print(f"  {shot_id}: {result['final_status']} -> {result['final_path']}")


def stage_frames(short_id: str, story: StoryScript, yes: bool, reel_cursor: int) -> bool:
    scene_shots = story_frames._scene_shots(story)
    cta = story_frames._cta_shot(story)
    plan = _frames_plan(scene_shots, has_cta=bool(cta))
    if not _money_gate("frames", short_id, plan, yes, reel_cursor):
        return False

    code = story_frames.main([short_id, "--all", "--yes"])
    if code != 0:
        return False

    while True:
        data = story_frames._load_judge_data(short_id)
        needs_review = [sid for sid, rec in data.items() if rec["final_status"] == "NEEDS_REVIEW"]
        print(f"\n=== PAUSE: frames for {short_id} ===")
        print(f"  {len(data) - len(needs_review)} PASS, {len(needs_review)} NEEDS_REVIEW")
        if needs_review:
            print(f"  NEEDS_REVIEW: {needs_review}")

        if not needs_review:
            break
        if yes or not sys.stdin.isatty():
            print("  auto-approving (--yes / non-interactive) despite NEEDS_REVIEW shots.")
            break

        choice = input("  approve / rejudge <id> / regenerate <id> / stop: ").strip()
        if choice == "approve":
            break
        if choice == "stop":
            print(f"Stopped in frames — rerun with --topic {short_id} to continue.")
            return False
        if choice.startswith("rejudge "):
            try:
                story_frames.cmd_rejudge(short_id, choice.split(" ", 1)[1].strip())
            except SystemExit as e:
                print(f"  {e}")
            continue
        if choice.startswith("regenerate "):
            _regenerate_shot(short_id, story, choice.split(" ", 1)[1].strip())
            continue
        print("  not understood — try 'approve', 'rejudge <id>', 'regenerate <id>', or 'stop'.")

    (config.OUTPUT_DIR / short_id / "frames.done").write_text("ok", encoding="utf-8")
    return True


# ================================================================== stage 6

def stage_audio(short_id: str) -> bool:
    # Free (local Kokoro/Chatterbox) — no money gate; audio is deliberately
    # not in MONEY_STAGES (this step's own spec only lists 2/3/4/5).
    return story_audio.run(short_id) == 0


# ================================================================== stage 7

def _start_local_server(base_url: str, timeout: float = 60.0) -> subprocess.Popen:
    """
    RESTYLE_TO_STORY_REELS.md Step 9 Fix 3. `python -m shorts.server`,
    started as a real subprocess on the port `base_url` names, blocked on
    until /api/health actually answers (not just until the process starts —
    FastAPI/uvicorn takes a moment to bind and finish its own startup, and a
    render that begins capturing before that would just fail the same
    "server not up" check video.render() already does). The caller (stage_
    render) is responsible for stopping this — see that function's own
    "only stop it if THIS RUNNER started it" rule.
    """
    parsed = urllib.parse.urlparse(base_url)
    port = parsed.port or 8000
    proc = subprocess.Popen(
        [sys.executable, "-m", "shorts.server", "--port", str(port)],
        cwd=str(config.ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if video._server_is_up(base_url):
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"local server exited early (code {proc.returncode}) "
                               f"before ever answering {base_url}/api/health")
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"local server did not answer {base_url}/api/health "
                       f"within {timeout:.0f}s")


def stage_render(short_id: str, base_url: str | None) -> bool:
    """
    RESTYLE_TO_STORY_REELS.md Step 9 Fix 3: the render stage needs a live
    `shorts/server.py` (shorts/video.py's own capture protocol photographs
    the REAL running app, not a static mock) — this used to be a manual,
    undocumented prerequisite ("start a server yourself first"). Now: if
    nothing is already answering at base_url, this runner starts one
    itself, waits for it, renders, and stops ONLY the server IT started —
    a server the user already had running (their own dev server, or one
    from an earlier `python -m shorts.server` they're still using) is
    NEVER touched, detected simply by whether _server_is_up was already
    true before this stage did anything.
    """
    base = (base_url or config.VIDEO_BASE_URL).rstrip("/")
    started_server = None
    if video._server_is_up(base):
        print(f"  server already answering at {base} — using it as-is "
             f"(this runner will not stop it)")
    else:
        print(f"  no server answering at {base} — starting `python -m "
             f"shorts.server --port {urllib.parse.urlparse(base).port or 8000}` ...")
        try:
            started_server = _start_local_server(base)
        except Exception as e:
            print(f"  could not start a local server: {type(e).__name__}: {e}")
            return False
        print(f"  server is up at {base} (started by this runner)")

    try:
        mp4 = video.render(short_id, force=False, base_url=base)
    except Exception as e:
        print(f"  render failed: {type(e).__name__}: {e}")
        return False
    finally:
        if started_server is not None:
            started_server.terminate()
            try:
                started_server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                started_server.kill()
                started_server.wait(timeout=10)
            print(f"  stopped the server this runner started (pid {started_server.pid})")

    print(f"  wrote {mp4}")
    return True


# ================================================================== stage 8

def stage_report(short_id: str, stage_usage: dict, reel_cursor: int) -> dict:
    frames_dir = config.OUTPUT_DIR / short_id / "frames"
    data = story_frames._load_judge_data(short_id) if frames_dir.exists() else {}
    needs_review = [sid for sid, rec in data.items() if rec.get("final_status") == "NEEDS_REVIEW"]

    by_model: dict[str, dict] = {}
    for call in usage.calls_since(reel_cursor):
        row = by_model.setdefault(call["model"], {"calls": 0, "cost": 0.0})
        row["calls"] += 1
        row["cost"] = round(row["cost"] + call["cost"], 6)

    total = usage.since(reel_cursor)
    mp4_path = video.mp4_path(short_id)

    report = {
        "short_id": short_id,
        "total_cost": round(total["cost"], 4),
        "total_calls": total["calls"],
        "by_stage": {stage: {"cost": round(t["cost"], 4), "calls": t["calls"]}
                    for stage, t in stage_usage.items()},
        "by_model": by_model,
        "needs_review": needs_review,
        "reel_mp4": str(mp4_path) if mp4_path.exists() else None,
    }
    out = config.OUTPUT_DIR / short_id / "run_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n=== PAUSE: report for {short_id} (wrote {out}) ===")
    print(json.dumps(report, indent=2))
    return report


# ======================================================================= run

#: RESTYLE_TO_STORY_REELS.md Step 9 Fixes round 9: "I keep accidentally
#: generating explainer-mode reels instead of story mode" — this runner
#: (shorts/story_reel.py) and the explainer pipeline (shorts/run.py) look
#: similar enough on a terminal that it was easy to lose track of which
#: one is running. A fixed-width, all-caps banner, printed FIRST (before
#: even the prerequisite checklist — nothing else about this run matters
#: if the wrong pipeline was started), is a much harder thing to miss
#: scrolling past than the ordinary "=== setup complete ===" printouts
#: further down. See video.mp4_path for this run's other half of the same
#: fix (the reel_STORY.mp4 filename itself).
_STORY_MODE_BANNER = (
    "\n"
    "############################################################\n"
    "#                                                          #\n"
    "#                >>> STORY MODE <<<                        #\n"
    "#                                                          #\n"
    "#   shorts/story_reel.py — NOT shorts/run.py (explainer).  #\n"
    "#   Every reel this produces gets a __story short_id and   #\n"
    "#   a reel_STORY.mp4 file. See docs/RUNBOOK_STORY.md.      #\n"
    "#                                                          #\n"
    "############################################################\n"
)


def print_story_mode_banner() -> None:
    print(_STORY_MODE_BANNER)


def run(doc_path: str, topic_short_id: str | None, from_stage: str | None,
       force_stage: str | None, yes: bool, base_url: str | None = None,
       overwrite_id: str | None = None) -> int:
    print_story_mode_banner()
    blocking, warnings = check_prerequisites()
    print_checklist(blocking, warnings)
    if blocking:
        print("\nCannot proceed — fix the item(s) marked X above.")
        return 1

    sections = parse_markdown(doc_path)
    force_idx = STAGE_ORDER.index(force_stage) if force_stage else len(STAGE_ORDER)
    start_idx = STAGE_ORDER.index(from_stage) if from_stage else 0

    reel_cursor = usage.mark()
    stage_usage: dict[str, dict] = {}

    def _needs(stage: str, output_exists: bool) -> bool:
        idx = STAGE_ORDER.index(stage)
        if idx < start_idx:
            return False   # --from skips it entirely, trusted as already done
        return idx >= force_idx or not output_exists

    # ---------------------------------------------------------------- setup
    short_id = topic_short_id
    if start_idx <= STAGE_ORDER.index("setup"):
        already = bool(short_id) and _setup_path(short_id).exists()
        if short_id and not already:
            print(f"\nno such reel in progress: {short_id} "
                 f"({_setup_path(short_id)} does not exist). "
                 f"Omit --topic to start a new reel.")
            return 1
        if already and not _needs("setup", True):
            topic, section, understanding = _load_setup(short_id, sections)
            print(f"\n=== setup: resumed {short_id} from {_setup_path(short_id)} ===")
        else:
            c = usage.mark()
            topic, section, understanding = _run_setup(sections, short_id)
            stage_usage["setup"] = usage.since(c)

            # RESTYLE_TO_STORY_REELS.md Step 9 Fix 4: story reels get their
            # OWN id namespace, never silently landing on (and overwriting)
            # whatever id the topic-selection LLM happened to produce — that
            # id might already be an EXISTING explainer reel's own short_id,
            # or an earlier story run's. Only applies on a genuinely FRESH
            # start (topic_short_id was None coming in — --topic itself
            # already names an exact, trusted target, so it is never
            # reassigned here). --overwrite <id> is the one explicit,
            # opt-in way to target a specific existing id anyway.
            if topic_short_id is None:
                if overwrite_id:
                    if (config.OUTPUT_DIR / f"{overwrite_id}.json").exists():
                        print(f"\n--overwrite {overwrite_id} refused — that id "
                             f"belongs to an EXPLAINER reel "
                             f"({overwrite_id}.json), which this runner never "
                             f"touches. Pick a different id.")
                        return 1
                    short_id = overwrite_id
                    print(f"\n=== setup complete: short_id={short_id} "
                         f"(--overwrite; existing files under this id, if "
                         f"any, will be replaced by THIS run only) ===")
                else:
                    short_id = _next_free_story_id(topic.id)
                    if short_id != f"{topic.id}__story":
                        print(f"\n  note: {topic.id}__story already exists "
                             f"(an earlier story run on this same topic) — "
                             f"using {short_id} instead. Existing files "
                             f"under that id were NOT touched.")
                    print(f"\n=== setup complete: short_id={short_id} ===")
            else:
                short_id = topic.id
                print(f"\n=== setup complete: short_id={short_id} ===")
            _save_setup(short_id, topic, section, understanding)
    else:
        if not short_id:
            print("--from past setup requires --topic <short_id>")
            return 1
        if not _setup_path(short_id).exists():
            print(f"no setup state for {short_id} at {_setup_path(short_id)} — "
                 f"run setup first (omit --from)")
            return 1
        topic, section, understanding = _load_setup(short_id, sections)

    pool_text, _pool_ids = story_evidence_pool(
        sections, topic.source_section_id,
        teaching_sequence=understanding.teaching_sequence if understanding else None)

    if not ensure_cast_sheets(yes):
        print("\nStopped — cast sheets are required before frames can render.")
        return 1

    # -------------------------------------------------------------- mapping
    mapping_path = config.OUTPUT_DIR / f"{short_id}.mapping.json"
    mapping = None
    if _needs("mapping", mapping_path.exists()):
        c = usage.mark()
        mapping = stage_mapping(short_id, topic, section, understanding, pool_text, yes, reel_cursor)
        stage_usage["mapping"] = usage.since(c)
        if mapping is None:
            return 1
    elif STAGE_ORDER.index("mapping") >= start_idx:
        mapping = ConceptMappingSet.model_validate_json(mapping_path.read_text(encoding="utf-8"))
        print(f"\n=== mapping: resumed from {mapping_path} ===")
        c = usage.mark()
        mapping = _fix_stale_hook_line(short_id, mapping, topic, section, understanding,
                                       pool_text, yes, reel_cursor)
        stage_usage["hook_fix"] = usage.since(c)
        if mapping is None:
            return 1

    # ---------------------------------------------------------------- shots
    story_path = config.OUTPUT_DIR / f"{short_id}.story.json"
    story = None
    if _needs("shots", story_path.exists()):
        c = usage.mark()
        story = stage_shots(short_id, mapping, topic, section, understanding, pool_text, yes, reel_cursor)
        stage_usage["shots"] = usage.since(c)
        if story is None:
            return 1
    elif STAGE_ORDER.index("shots") >= start_idx:
        story = StoryScript.model_validate_json(story_path.read_text(encoding="utf-8"))
        print(f"\n=== shots: resumed from {story_path} ===")
    if story is None:
        story = StoryScript.model_validate_json(story_path.read_text(encoding="utf-8"))

    # --------------------------------------------------------------- sample
    sample_marker = config.OUTPUT_DIR / short_id / "sample.done"
    if _needs("sample", sample_marker.exists()):
        c = usage.mark()
        ok = stage_sample(short_id, story, yes, reel_cursor)
        stage_usage["sample"] = usage.since(c)
        if not ok:
            return 1
    elif STAGE_ORDER.index("sample") >= start_idx:
        print(f"\n=== sample: already done ({sample_marker}) ===")

    # --------------------------------------------------------------- frames
    frames_marker = config.OUTPUT_DIR / short_id / "frames.done"
    if _needs("frames", frames_marker.exists()):
        c = usage.mark()
        ok = stage_frames(short_id, story, yes, reel_cursor)
        stage_usage["frames"] = usage.since(c)
        if not ok:
            return 1
    elif STAGE_ORDER.index("frames") >= start_idx:
        print(f"\n=== frames: already done ({frames_marker}) ===")

    # ---------------------------------------------------------------- audio
    timings_path = config.OUTPUT_DIR / short_id / "timings.json"
    if _needs("audio", timings_path.exists()):
        c = usage.mark()
        ok = stage_audio(short_id)
        stage_usage["audio"] = usage.since(c)
        if not ok:
            print("  audio stage failed.")
            return 1
    elif STAGE_ORDER.index("audio") >= start_idx:
        print(f"\n=== audio: already done ({timings_path}) ===")

    # --------------------------------------------------------------- render
    mp4_path = video.mp4_path(short_id)
    if _needs("render", mp4_path.exists()):
        c = usage.mark()
        ok = stage_render(short_id, base_url)
        stage_usage["render"] = usage.since(c)
        if not ok:
            return 1
    elif STAGE_ORDER.index("render") >= start_idx:
        print(f"\n=== render: already done ({mp4_path}) ===")

    # --------------------------------------------------------------- report
    stage_report(short_id, stage_usage, reel_cursor)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.story_reel",
        description="Run one story reel end to end: setup -> mapping -> shots -> "
                    "sample -> frames -> audio -> render -> report.")
    p.add_argument("markdown_path")
    p.add_argument("--topic", dest="topic_short_id", default=None,
                   help="resume an in-progress reel by its short_id "
                       "(output/<short_id>/setup.json must already exist)")
    p.add_argument("--from", dest="from_stage", choices=STAGE_ORDER, default=None,
                   help="start the stage loop here, trusting everything before "
                       "it is already done without checking")
    p.add_argument("--force-stage", dest="force_stage", choices=STAGE_ORDER, default=None,
                   help="redo this stage (and every stage after it) even if its "
                       "output already exists")
    p.add_argument("--overwrite", dest="overwrite_id", default=None, metavar="ID",
                   help="on a FRESH start only (no --topic): use this exact id "
                       "instead of auto-picking <topic>__story or a numbered "
                       "suffix. Refused if ID belongs to an existing EXPLAINER "
                       "reel — this runner never touches those.")
    p.add_argument("--yes", action="store_true",
                   help="answer every confirmation automatically (still prints "
                       "every pre-flight summary and every pause screen)")
    p.add_argument("--base-url", default=None,
                   help=f"where the app is served for the render stage "
                       f"(default {config.VIDEO_BASE_URL})")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.markdown_path, args.topic_short_id, args.from_stage,
              args.force_stage, args.yes, args.base_url, args.overwrite_id)


if __name__ == "__main__":
    raise SystemExit(main())
