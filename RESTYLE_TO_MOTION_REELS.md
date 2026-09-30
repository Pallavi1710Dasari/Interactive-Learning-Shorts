# Restyle: motion reels (`REEL_STYLE=motion`)

Status: **Phase 1 of 5 done (script contract).** Built and verified with `SHORTS_STUB=1` only; no real LLM call has been made in motion mode yet.

Motion reels are a third style beside `explainer` and `story`. A single narrator talks in the second person over scenes drawn by our own React components, so image cost is $0. The target look is `docs/reference/reference_reel.html`. `docs/reference/current_reel_frames.png` shows what the explainer pipeline makes today.

Explainer and story are unchanged. Motion lives in its own models, graders, prompts, runner and output files (`<topic>__motion`), and nothing in `output/` is re-rendered or overwritten.

## Decisions (2026-09-30)

The reference reel breaks several of the change request's own rules. These decisions settle each conflict:

| Conflict | Decision |
|---|---|
| Reference is 178 words (~80 s), has 1–6 word caption chunks, paraphrases its narration in captions, and uses 7-word payoff/CTA | **Rules win.** The golden fixture keeps the reference's story and objects but is tightened to the rules (156 words, 3–5 word chunks that match the speech, payoff/CTA ≥ 8 words). |
| Reference uses coral for a liked (successful) heart and coloured editor dots | **Strict colour meanings.** Coral only on failure, mint only on success. The liked heart turns mint or amber, and the editor dots are grey. |
| Series label, corner mark and "Up next" are hard-coded React text | Series and mark come from `config.MOTION_SERIES` (default `BRAND_HANDLE`). "Up next" is the next unused section title of the source document. The LLM never writes them. |
| "9–11 shots" while 10 beats are required | 10–11 shots (only `break_2` is optional). |
| `reel_style`, `tts_provider`, `voice_ref` "on each unit JSON" | Recorded on motion artifacts only (`MotionScript`). Adding them to `ShortUnit` would change every explainer JSON. |
| 2.5 s change cadence | Caption changes count as a visible change. |
| Recap frame word count | The recap may show up to 24 words, heading included (the general cap is 18). |
| 4 evals already failing before this work (E041, E042, E068, E083) | Left alone. The baseline was 111 passed, 4 failed, 12 skipped. |

## Where the repo differed from the change request

- `docs/reference/` did not exist at first. It was added later.
- There is no `why_plain_variable_fails` reel in `output/`.
- `REEL_STYLE` was not validated before: unknown values ran as explainer.
- There is no `Unit` model: explainer reels use `ShortUnit` and story reels use `StoryScript`.
- `EDUCATIONAL_VISUAL_RULES` and the judge prompts are explainer-only, so motion gets its own constants and prompts rather than edits to those.
- `revision.py` is used by the explainer path only.
- OCR (`pytesseract` and the `tesseract` program) is not installed, so frame text will be counted from the page itself (phase 4).
- Per-shot audio, faster-whisper timing and `-14 LUFS` loudnorm already exist in `story_audio.py`, and phase 3 reuses them.
- Capture already uses `window.__capture.seek(t)`.
- Manrope and JetBrains Mono were not loaded anywhere.

## Phase 1: script contract

| File | Change |
|---|---|
| `shorts/config.py` | `REEL_STYLES` and validation; `MOTION_SERIES`, `MAX_MOTION_SCRIPT_RETRIES` (3), `MAX_MOTION_HOOK_FIX_RETRIES` (2). |
| `shorts/schema.py` | `MotionBeat`, `MOTION_BEAT_ORDER`, `MOTION_WORDS_PER_SECOND` (2.8), `CaptionChunk`, `IconRef`, `MotionTakeaway`, `MotionShot`, `MotionScriptDraft`, `MotionHookFix`, `MotionScript`. Added at the end of the file; no existing model changed. |
| `shorts/checks.py` | 11 motion script graders plus `run_motion_script_graders` and `motion_failures_are_hook_only`. |
| `shorts/skills/script.py` | `SYSTEM_MOTION`, `SYSTEM_MOTION_HOOK_FIX`, `write_motion_script`, `regenerate_motion_hook`. |
| `shorts/motion_library.py` | Python side of the scene library (icon names for now). |
| `web/src/motion/icons.json` | The one icon file: 7 icons from the reference and 16 topic-agnostic ones. |
| `shorts/motion_reel.py` | The runner: `setup → script → scenes → voice → timing → render → report`, with resume, `--from`, `--force-stage` and `--yes`. Setup and script are built; the other stages stop with "not built yet". |
| `shorts/run.py` | With `REEL_STYLE=motion`, stops before topic selection and points to `motion_reel`. |
| `shorts/stubs.py` | Motion stubs return the golden fixture whose `concept_name` the material teaches. |
| `evals/run_evals.py`, `evals/cases.yaml` | `motion_grader` case type with `patch` ops; E129–E156 (28 cases). |
| `evals/fixtures/motion/` | `usestate_golden.json` (the tightened reference) and `tlb_golden.json` (non-React, no code, 10 shots). |
| `shorts/motion_script_test.py` | 12 tests: retry and hook-only repair, the 2-attempt hook budget, runner stages and resume, declined gates, id namespace, no image or paid calls, `REEL_STYLE` validation. |

### The script graders

All free and deterministic, in `checks.run_motion_script_graders`:

| Grader | Rule |
|---|---|
| `motion_beats_order` | Fixed beat order, 10–11 shots, only `break_2` optional, ids `s01…` |
| `motion_has_fix_and_payoff` | `fix_idea`/`fix_flow`/`payoff` present; `concept_name` is in the source, named on screen during the fix, and in the `code_map` code when the material has code |
| `motion_hook_curiosity` | Curiosity opener, a question, a concrete symptom, never the concept's name |
| `motion_word_budget` | 110–170 words; 8–30 per shot; hook ≤ 4 s, title and CTA ≤ 3 s (estimated) |
| `motion_caption_chunks` | 3–5 words, ≤ 2 `<b>` highlights, no split code token, no dangling end |
| `motion_captions_match_speech` | Captions are the narration word for word (code tokens may stand for their spoken words) |
| `motion_speech_vs_caption` | No raw code in speech; captions keep real code |
| `motion_code_shots` | ≤ 2 code shots (setup, code_map), ≤ 3 lines, ≤ 30 chars; code_map shows code when the material has code |
| `motion_recap_icons` | 3 drawable vocabulary icons; 3 takeaways reusing all of them; recap ≤ 24 words |
| `motion_plain_words` | No spoken word over 4 syllables except the concept name |
| `motion_not_qa` | No speaker labels; only the hook asks a question |

Three graders need scenes and arrive in phase 3: `payoff_mirrors_hook`, `change_cadence` and `color_semantics`.

### Run it

```
SHORTS_STUB=1 python -m shorts.motion_reel content/react_usestate_basics.md --yes
SHORTS_STUB=1 python -m shorts.motion_script_test
python -m evals.run_evals
```

The stubs return a golden fixture, so a stub run works only on material that a fixture's `concept_name` appears in (useState, the TLB). Other material raises and names the fix: add a fixture.

## Phases still to come

2. **Scene library.** Tokens, icons, every scene object, `MotionStage` driven only by `t`, and a `#motion-gallery` page.
3. **Scenes and timing.** `SYSTEM_MOTION_SCENES`, SceneSpec validation and the `revision.py` loop, per-shot Chatterbox narration, and whisper-aligned timelines. Also adds the three scene graders.
4. **Render and QA.** Motion capture, MP4, frame checks (word count from the page, safe zones), motion judge rubrics, and the report.
5. **Polish.** A motion view in the web UI, `docs/RUNBOOK_MOTION.md`, and cleanup.
