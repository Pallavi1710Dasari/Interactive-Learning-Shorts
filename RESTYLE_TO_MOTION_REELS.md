# Restyle: motion reels (`REEL_STYLE=motion`)

Status: **Phase 1 and phase 1b of 5 done (script contract, both templates).** Built and verified with `SHORTS_STUB=1` only; no real LLM call has been made in motion mode yet.

**Read `REFERENCE_STYLE_ADDENDUM.md` with this file. Where they disagree, the addendum wins.** It adds the second reference reel (tokenization), the `walkthrough` template, the 120 s cap, karaoke sentence captions, and the motion system phase 2 builds.

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

## Decisions (2026-10-01, phase 1b)

These follow the addendum and its section 8.4. Where one changes a decision above, it says so.

| Topic | Decision |
|---|---|
| Length | 120 s hard cap on every reel. fix_story is 110–200 words **and** 40–75 s (so about 195 words); walkthrough is 160–300 words and 60–120 s. Estimates use 2.6 words/s (was 2.8), so the fix_story hook is now ≤ 10 words. |
| Captions | One caption per spoken sentence, ≤ 14 words, ≤ 2 highlights (replaces the 3–5 word chunks). |
| Visible change | **Replaces the decision above:** karaoke caption progress does not count as a visible change. |
| Template choice | walkthrough when the approved teaching approach is `process_demonstration`, otherwise fix_story. The reviewer switches it right after the teaching-approach gate, or with `--template`. Stored on the motion artifacts only; `TeachingApproach` is unchanged. |
| Questions | Only the hook asks in fix_story. A walkthrough chapter may ask one question of ≤ 6 words, answered by the next sentence. |
| Long words | Up to 2 terms over 4 syllables per reel, besides the concept's name, if the source uses them, they are on screen, and the same sentence explains them. |
| Numbers | Every spoken number is in the source, except a chapter card's step number, the chapter count, and counts of the running example's own states. The word "one" is not checked (it is rarely a quantity); a digit 1 is. |
| Walkthrough evidence | A walkthrough's source is its evidence pool **plus every section of the same numbered session** (filed under 1.1 → all 1.x), because a process lesson gives each step its own heading. fix_story's pool is unchanged. |
| Series split | Deferred. More than 4 chapters fails. |
| Golden fixtures | The useState fixture says no number its source section does not: the payoff no longer counts "one, two, three" aloud, and the code map says "the value and its setter". |

## Where the repo differed from the change request

- `docs/reference/` did not exist at first. It was added later, and `tokenization-reel.mp4` is git-ignored (its extracted frames are committed in phase 2).
- `content/` had no tokenization material, so `content/tokenization_basics.md` was written from the reel's narration for the walkthrough golden fixture.
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

## Phase 1b: two templates

| File | Change |
|---|---|
| `shorts/schema.py` | `MotionTemplate`, the walkthrough beats, `MotionChapter`, `MotionExample`; `MotionScript.template` (default `fix_story`, so phase 1 files still load), `chapters`, `running_example`; `MotionShot.chapter` and `example`. `MOTION_WORDS_PER_SECOND` is 2.6. |
| `shorts/checks.py` | 15 graders (below). `check_motion_template_beats` replaces `beats_order`, `check_motion_caption_sentences` replaces `caption_chunks`. Every grader branches on the template where the two differ. |
| `shorts/skills/script.py` | `SYSTEM_MOTION` updated (75 s, sentence captions, sourced numbers); new `SYSTEM_MOTION_WALKTHROUGH` and `SYSTEM_MOTION_WALKTHROUGH_HOOK_FIX`; `write_motion_script(template=...)`. |
| `shorts/motion_reel.py` | `default_template`, the template gate, `--template`, the walkthrough evidence pool, chapters in the shot list. |
| `shorts/stubs.py` | Picks the golden fixture by concept **and** template. |
| `evals/fixtures/motion/` | fix_story fixtures re-cut to sentence captions; `tokenization_golden.json` (4 chapters, ~81 s) and `hash_table_golden.json` (3 chapters, ~69 s); `format_fixture.py` keeps their hand-written layout. |
| `evals/cases.yaml` | E137–E140, E144–E147 and E156 updated; E157–E172 added (16 cases). |
| `content/tokenization_basics.md` | Source for the tokenization fixture. |
| `shorts/motion_script_test.py` | 22 tests (10 new): walkthrough stub and prompts, template gate and flag, unknown templates, stub fixture errors, phase 1 files loading, the long-term cap, the walkthrough evidence pool. |

### The script graders

All free and deterministic, in `checks.run_motion_script_graders`:

| Grader | Rule |
|---|---|
| `motion_template_beats` | fix_story: fixed beat order, 10–11 shots, only `break_2` optional. walkthrough: hook > name_it > example, then each chapter's card plus 1–3 chapter shots, then result > takeaway > recap > cta. Ids `s01…` |
| `motion_duration_cap` | ≤ 120 s, hard fail (estimate now; real audio in phase 3) |
| `motion_has_fix_and_payoff` | `concept_name` is in the source and on screen. fix_story: `fix_idea`/`fix_flow`/`payoff` present, named during the fix, and in the `code_map` code when the material has code. walkthrough: named in name_it |
| `motion_hook_curiosity` | Never the concept's name. fix_story: curiosity opener, a question, a concrete symptom. walkthrough: a "how does / what happens" question, then an answer line |
| `motion_word_budget` | The template's words and seconds; 8–30 per shot (name_it and chapter_card ≥ 3); timed beats inside their budget |
| `motion_caption_sentences` | One whole sentence per caption, ≤ 14 words, ≤ 2 `<b>` highlights, no split code token |
| `motion_captions_match_speech` | Captions are the narration word for word (code tokens may stand for their spoken words) |
| `motion_speech_vs_caption` | No raw code in speech; captions keep real code |
| `motion_code_shots` | ≤ 2 code shots, ≤ 3 lines, ≤ 30 chars, on the template's code beats; fix_story's code_map shows code when the material has code |
| `motion_recap_icons` | fix_story: 3 drawable vocabulary icons, 3 takeaways reusing all of them. walkthrough: the RecapGrid of chapter titles. Recap ≤ 24 words |
| `motion_plain_words` | No spoken word over 4 syllables except the concept name and ≤ 2 explained source terms |
| `motion_not_qa` | No speaker labels; only the hook asks (plus one answered question per walkthrough chapter) |
| `walkthrough_chapters` | 2–4 chapters, numbered, titled (≤ 6 words), each opened by one card, ≤ 60 words each |
| `walkthrough_running_example` | One example, in every chapter, each chapter starting where the last ended; result shows the final state |
| `motion_numbers_sourced` | Every spoken number is in the source or recomputable from the running example |

Three graders need scenes and arrive in phase 3: `payoff_mirrors_hook`, `change_cadence` and `color_semantics`.

### Run it

```
SHORTS_STUB=1 python -m shorts.motion_reel content/react_usestate_basics.md --yes
SHORTS_STUB=1 python -m shorts.motion_reel content/tokenization_basics.md --yes --template walkthrough
SHORTS_STUB=1 python -m shorts.motion_script_test
python -m evals.run_evals
```

The stubs return a golden fixture, so a stub run works only on material that a fixture's `concept_name` appears in, in the template asked for (fix_story: useState, the TLB; walkthrough: tokenization, the hash table). Other material raises and names the fix: add a fixture.

## Phases still to come

2. **Scene library.** Tokens, icons, both object sets, chapter fields, karaoke captions, the 6 chapter transitions, the chapter-card entrance and the 14 in-shot animations (addendum 4.6 and 8), `MotionStage` driven only by `t`, and a `#motion-gallery` page with a frame scrubber beside the reference frames.
3. **Scenes and timing.** `SYSTEM_MOTION_SCENES`, SceneSpec validation and the `revision.py` loop, per-shot Chatterbox narration, and whisper-aligned timelines. Also adds the three scene graders.
4. **Render and QA.** Motion capture, MP4, frame checks (word count from the page, safe zones), motion judge rubrics, and the report.
5. **Polish.** A motion view in the web UI, `docs/RUNBOOK_MOTION.md`, and cleanup.
