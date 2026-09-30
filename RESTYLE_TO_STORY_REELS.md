# Restyle: code-slide explainer → illustrated character-story reels

Status: **Phase 1 implemented, unrun on a real LLM call except where noted below.**
Nothing in the existing explainer pipeline changed behaviour — see "Compatibility" below.

## Why

The shipped pipeline (`REEL_STYLE=explainer`, the default) is a single narrator
over SVG diagrams — see `ARCHITECTURE_OVERVIEW.md`. This document tracks an
alternate style: a fixed cast of illustrated characters acting out a short
scene whose events physically dramatize the technical rule, instead of a
narrator describing it over a diagram.

This is a **switch, not a rewrite** — same pattern as `config.REEL_THEME`
("paper" vs "neon"). `REEL_STYLE=explainer` (the default) is byte-identical to
before this document existed. Nothing about story mode touches the explainer
prompt, its checks, or its renderer.

## Phase 1 — script generation (mapping + shots). No rendering.

Scope: prove out the METAPHOR MAPPING step and the shots that dramatize it, as
plain JSON on disk. No TTS, no illustration, no video. `python -m shorts.run`
with `REEL_STYLE=story` stops after writing `output/<short_id>.story.json`.

### What changed, file by file

| File | Change |
|---|---|
| `shorts/schema.py` | Added `Character`, `ConceptMapping`, `ConceptMappingSet`, `Shot`, `StoryScript`, `StoryShotsSet`, `MetaphorVerdict`, `StoryEvalReport`. |
| `shorts/config.py` | Added `REEL_STYLE` (`"explainer"` default / `"story"`), `CAST` (fixed character roster, JSON-overridable via `CAST` env var), `BRAND` (one-line illustration style). |
| `shorts/skills/script.py` | Renamed `SYSTEM` → `SYSTEM_EXPLAINER` (no behaviour change, nothing else imports it by name). Added `SYSTEM_STORY` (STEP 1 cast/setting + STEP 1b metaphor mapping), `SYSTEM_STORY_SHOTS`, `plan_story_mapping()`, `write_story_shots()`. |
| `shorts/checks.py` | Added `check_mapping()` (free, no LLM) and `run_story_graders()`. |
| `shorts/skills/audit.py` | Added `METAPHOR_JUDGE_SYSTEM`, `judge_story_metaphors()`, `audit_story()`. |
| `shorts/run.py` | Added `build_one_story()`, `build_story_shorts()`, and one branch in `main()` on `config.REEL_STYLE == "story"`, placed after every human gate (topic/framing/teaching-approach) and before the explainer-only build loop. |
| `shorts/stubs.py` | Added offline stubs for `ConceptMappingSet`, `StoryShotsSet`, `StoryEvalReport` so the whole path is testable with `SHORTS_STUB=1` at zero cost. |

### The two-call design (why mapping and shots are separate LLM calls)

The change request asked for mapping to be filled "before any shot is
written" and for a checkpoint to review it before shots exist. Rather than one
call producing a `StoryScript` with `mapping` computed before `shots` inside
the same JSON response, this is **two separate calls**:

1. `plan_story_mapping()` → `ConceptMappingSet` (mapping only). Gated by
   `checks.check_mapping()` in its mapping-only mode (count 2-4, every
   `source_quote` grounded in the section) before returning. Retries up to
   `MAX_STORY_MAPPING_RETRIES` (3) on failure, returns `None` on exhaustion —
   same nullable-on-failure contract as `understanding_for()`.
2. `write_story_shots()` → takes the **approved** mapping as fixed context,
   asks only for `shots`/`cast`/`lessons`, and assembles the final
   `StoryScript` in Python (the mapping is copied through, never re-asked of
   the model).

This mirrors the existing pipeline's own "cheap check before the expensive
call" shape (`understanding_for()` runs once, outside `write_script`'s retry
loop) and is what makes "show me the mapping before generating shots" a real
checkpoint rather than a comment in the prompt.

### check_mapping's rules

Free, no LLM call. Two modes, same function:

- **Mapping-only** (`shots=None`, called right after `plan_story_mapping`):
  - `2 ≤ len(mapping) ≤ 4`
  - every `source_quote` is a real substring of the section (reuses
    `checks._flatten`, the same normalizer `check_source_quotes` uses)
- **Full** (`shots` and `lessons` given, called on the assembled `StoryScript`
  via `run_story_graders`), everything above plus:
  - every mapping entry is dramatized by ≥ 3 shots via `concept_ref`
  - no shot's `concept_ref` points at a rule missing from the mapping
  - every `lesson_line` appears as some shot's own `line`, AND in the
    top-level `lessons` list

Not mechanically checked (judgment calls, left to the prompt's own
self-rejection instructions and to the judge): "a rule has no metaphor_event
that visibly happens", "the metaphor implies a behavior the source does not
state", "two rules map to the same event", "visible_proof needs words on
screen".

### The judge

`skills.audit.judge_story_metaphors()` asks, per mapping entry: *does
metaphor_event behave exactly like concept_rule, with nothing extra implied?*
Any single `faithful: false` fails the whole reel — `StoryEvalReport.passed`
is `all(v.faithful for v in verdicts)`, not a majority or an average, matching
the change request's "any 'no' fails the reel" instruction exactly.
`audit_story()` only calls the judge once `check_mapping` (on the full
`StoryScript`) has already passed — same "don't pay for a judge on known-bad
output" order `audit()` already uses for explainer scripts.

### Compatibility

`REEL_STYLE` defaults to `"explainer"`. Every existing test in `shorts/*_test.py`
still passes unmodified. `SYSTEM` was renamed to `SYSTEM_EXPLAINER`; nothing
outside `skills/script.py` imported it by that name (checked before renaming).
No existing shipped reel is affected — see the project's own redraw policy:
new logic applies to new reels only.

### What Phase 1 is deliberately silent on

These are real open questions, not decided yet:

- **Rendering.** How a `Shot` becomes an actual illustrated frame or video —
  a completely different renderer than `layout.py`'s SVG diagrams or
  `video.py`'s Playwright capture of the React player. Not designed.
- **Voice.** Whether shots get per-character dialogue audio (multiple voices)
  or a single narrator voice over illustrated action, and how that maps onto
  `providers.py`'s existing TTS backends.
- **CAST governance.** `config.CAST` is two placeholder characters
  (`rahul`, `priya`) invented for this scaffold, not a real, art-directed
  cast. Replace before anything downstream depends on the names.
- **Cost.** Two extra paid calls per short (`story_mapping`, `story_shots`,
  plus `story_judge`) on top of whatever Phase 1's eventual rendering adds —
  not yet measured against a real run, unlike every cost figure elsewhere in
  this codebase's comments (see `config.DESIGN_ATTEMPTS`'s own "MEASURED, NOT
  GUESSED" note for the standard this project holds itself to).

## Phase 2+ — not designed yet

Rendering, voice, and a real (non-placeholder) cast are Phase 2 and later.
Nothing in this document commits to an approach for any of them.
