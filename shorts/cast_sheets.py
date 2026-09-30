"""
Cast character sheets — RESTYLE_TO_STORY_REELS.md Step 4 Part 3/4.

    python -m shorts.cast_sheets --candidates 3            # generate candidates
    python -m shorts.cast_sheets --approve rahul 2          # promote candidate 2
    python -m shorts.cast_sheets --dry-run                  # prompts only, no calls
    python -m shorts.cast_sheets --compare --character rahul --yes

Generates the drawn cast's (Rahul, Riya, System — never Narrator, see
config.CAST_LOOK) reference sheets: front/three-quarter/side view plus four
expressions, landscape, against shorts/style.py's STYLE_BIBLE. Every real
call goes through shorts/imagegen.py's generate_bytes(), so caching, the
per-reel budget cap, retries and SHORTS_STUB=1 are inherited, not
reimplemented here.

ORDER: Rahul first. Once assets/cast/rahul.png exists, it is passed as a
STYLE REFERENCE when generating Riya and System, so all three match — see
_next_character()/_reference_for().
"""
import argparse
import json
import sys
from pathlib import Path

from . import config, imagegen, preflight, style

#: The DRAWN cast, in the fixed generation order — Narrator has no sheet
#: (config.CAST_LOOK has no entry for it either; see that dict's own note).
CAST_ORDER = ["Rahul", "Riya", "System"]

CANDIDATES_DIR = config.OUTPUT_DIR / "cast_candidates"
COMPARE_DIR = config.OUTPUT_DIR / "provider_compare"
ASSETS_DIR = config.CAST_ASSETS_DIR
SHEET_SIZE = (1920, 1080)   # landscape — Step 4's own override of the 9:16 rule


def _resolve_name(raw: str) -> str:
    for name in CAST_ORDER:
        if name.lower() == raw.strip().lower():
            return name
    raise SystemExit(f"unknown character {raw!r} — must be one of {CAST_ORDER}")


def _approved_path(name: str) -> Path:
    return ASSETS_DIR / f"{name.lower()}.png"


def _candidate_path(name: str, n: int) -> Path:
    return CANDIDATES_DIR / f"{name.lower()}_{n}.png"


def _next_character() -> str | None:
    """The first character in CAST_ORDER with no approved sheet yet, or None
    once all three are approved."""
    for name in CAST_ORDER:
        if not _approved_path(name).exists():
            return name
    return None


def _reference_for(name: str) -> list[Path]:
    """Rahul's approved sheet, passed as a style reference for Riya/System —
    Step 4's own "so all three match" instruction. Empty for Rahul himself
    (nothing to match yet) and empty if Rahul isn't approved yet either
    (candidates can still be generated out of order; they just won't match
    a Rahul that doesn't exist on disk)."""
    if name == "Rahul":
        return []
    rahul = _approved_path("Rahul")
    return [rahul] if rahul.exists() else []


def _sheet_prompt(name: str, refs: list[Path]) -> str:
    look = config.CAST_LOOK.get(name, "")
    parts = [
        style.style_bible(landscape=True),
        f"\nCharacter: {name}. Look: {look}.",
        "Character reference sheet: front view, three-quarter view, side view, "
        "and four expressions (neutral, confused, delighted, frustrated), plain "
        "off-white background, evenly spaced, no text, no labels.",
    ]
    if refs:
        parts.append(f"Match the character design of the attached reference "
                     f"image exactly — same proportions, same colors, same look.")
    return "\n".join(parts)




def _write_prompts_json(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


# --------------------------------------------------------------------- candidates

def cmd_candidates(n: int, character: str | None, dry_run: bool, yes: bool) -> int:
    name = _resolve_name(character) if character else _next_character()
    if name is None:
        print("All cast members already have an approved sheet — nothing to do.")
        print(f"(Use --character to regenerate one anyway: {CAST_ORDER})")
        return 0

    refs = _reference_for(name)
    prompt = _sheet_prompt(name, refs)
    print(f"Next up: {name}" + (f" (reference: {refs[0]})" if refs else ""))

    if dry_run:
        entries = [{"character": name, "candidate": i, "prompt": prompt,
                   "refs": [str(r) for r in refs]} for i in range(1, n + 1)]
        out = CANDIDATES_DIR / "prompts.json"
        _write_prompts_json(out, entries)
        print(f"wrote {len(entries)} prompt(s) to {out} — no provider called")
        return 0

    provider = imagegen.select_provider()
    per_call = imagegen.estimate_cost(provider)
    print(f"About to generate {n} candidate sheet(s) for {name} using "
         f"{provider.name}/{provider.model}")
    print(f"Estimated cost: {n} call(s) x ${per_call:.4f} = ${per_call * n:.4f}")

    # RESTYLE_TO_STORY_REELS.md Step 8 Part 0 #4's shared pre-flight gate.
    # Cast sheets have no single short_id (one sheet is shared across every
    # reel, not built per-reel) — pointed at its own shared
    # output/cast_candidates/preflight.json instead of a reel's.
    image_plan = preflight.ModelPlan(label=f"image:{provider.name}", model=provider.model,
                                     planned_calls=n, cost_per_call=per_call)
    if not preflight.run_preflight("cast_sheets", name, [image_plan], yes,
                                   path=CANDIDATES_DIR / "preflight.json"):
        return 1

    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        item_id = f"{name.lower()}_{i}"
        # seed=i, NOT left as the default None: every candidate shares the
        # IDENTICAL prompt (that's what makes them candidates for the same
        # sheet) — without a per-candidate seed they'd also share a cache
        # key, and candidate 2 would silently come back as a copy of
        # candidate 1 instead of a genuinely different option to choose from.
        png = imagegen.generate_bytes(f"cast:{name.lower()}", item_id, prompt,
                                      refs=refs, size=SHEET_SIZE, seed=i, provider=provider)
        path = _candidate_path(name, i)
        path.write_bytes(png)
        print(f"  wrote {path}")
    return 0


# ----------------------------------------------------------------------- approve

def cmd_approve(name_raw: str, n_raw: str) -> int:
    name = _resolve_name(name_raw)
    try:
        n = int(n_raw)
    except ValueError:
        raise SystemExit(f"--approve's second argument must be a candidate number, got {n_raw!r}")

    src = _candidate_path(name, n)
    if not src.exists():
        print(f"no such candidate: {src}")
        print(f"(generate candidates first: python -m shorts.cast_sheets --candidates N "
             f"--character {name.lower()})")
        return 1

    dst = _approved_path(name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())   # overwrites — the whole point of --approve
    print(f"approved: {src} -> {dst}")
    return 0


# ----------------------------------------------------------------------- compare

def _compare_providers() -> list:
    """Every configured provider/model for --compare — Step 4 Part 4's own
    3-way set. A provider whose credentials are missing is SKIPPED with a
    printed reason, not a crash; --compare is meant to show whichever are
    actually usable, and a missing key for one is not a reason to refuse the
    other two."""
    specs = [
        lambda: imagegen.GeminiImageProvider(model=config.IMAGE_MODEL_FULL),
        lambda: imagegen.GeminiImageProvider(model=config.IMAGE_MODEL_LITE),
        lambda: imagegen.CloudflareImageProvider(),
    ]
    if config.STUB:
        # Under SHORTS_STUB=1 there is exactly one real "provider": the
        # stub. Comparing 3 copies of it would be noise, not a comparison.
        return [imagegen.StubImageProvider()]
    providers = []
    for make in specs:
        try:
            providers.append(make())
        except imagegen.ImageGenError as e:
            print(f"  skipping: {e}")
    return providers


def cmd_compare(character: str | None, dry_run: bool, yes: bool) -> int:
    name = _resolve_name(character) if character else "Rahul"
    refs = _reference_for(name)
    prompt = _sheet_prompt(name, refs)
    providers = _compare_providers()

    if not providers:
        print("No provider is usable (check .env credentials) — nothing to compare.")
        return 1

    if dry_run:
        entries = [{"character": name, "provider": p.name, "model": p.model,
                   "prompt": prompt, "refs": [str(r) for r in refs]}
                  for p in providers]
        out = COMPARE_DIR / "prompts.json"
        _write_prompts_json(out, entries)
        print(f"wrote {len(entries)} prompt(s) to {out} — no provider called")
        return 0

    print(f"Comparing {len(providers)} provider/model(s) for {name}:")
    total = 0.0
    for p in providers:
        cost = imagegen.estimate_cost(p)
        total += cost
        print(f"  {p.name}/{p.model}: ${cost:.4f}")
    print(f"Total estimated cost: ${total:.4f}")
    if not yes:
        print("Re-run with --yes to proceed.")
        return 1

    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    for p in providers:
        item_id = f"{name.lower()}_{p.name}_{p.model}"
        png = imagegen.generate_bytes(f"cast:compare:{name.lower()}", item_id, prompt,
                                      refs=refs, size=SHEET_SIZE, provider=p)
        path = COMPARE_DIR / f"{item_id}.png"
        path.write_bytes(png)
        print(f"  wrote {path}")
    return 0


# -------------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shorts.cast_sheets",
        description="Generate and manage cast character reference sheets.")
    p.add_argument("--candidates", type=int, metavar="N",
                   help="generate N candidate sheets for the next un-approved "
                        "character (or --character, if given)")
    p.add_argument("--approve", nargs=2, metavar=("NAME", "N"),
                   help="promote candidate N to assets/cast/<name>.png")
    p.add_argument("--compare", action="store_true",
                   help="generate one sheet per configured provider/model side by side")
    p.add_argument("--character", metavar="NAME",
                   help="override the auto-selected character (--candidates), or "
                        "pick which one to compare (--compare)")
    p.add_argument("--dry-run", action="store_true",
                   help="build prompts only and write them to disk; call no provider")
    p.add_argument("--yes", action="store_true",
                   help="skip the cost confirmation and actually call a provider")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.approve:
        return cmd_approve(*args.approve)
    if args.compare:
        return cmd_compare(args.character, args.dry_run, args.yes)
    if args.candidates is not None or args.dry_run:
        return cmd_candidates(args.candidates or 3, args.character, args.dry_run, args.yes)

    build_parser().print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
