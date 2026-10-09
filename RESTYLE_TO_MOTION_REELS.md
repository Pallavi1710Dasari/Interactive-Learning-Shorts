# Restyle: motion reels (`REEL_STYLE=motion`)

Status: **Phases 1, 1b, 2 and 2b done (script contract, both templates, scene library, themes and tags); 2b is awaiting review.** Built and verified with `SHORTS_STUB=1` only; no real LLM call has been made in motion mode yet.

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
| Walkthrough evidence | A walkthrough also sees **every section of the same numbered session** (filed under 1.1 → all 1.x), but only as SUPPORTING material. **The main explanation comes from the selected section's own evidence pool**; supporting sections may supply only numbers and defined terms (decision 2026-10-01, revised). `walkthrough_main_source` checks the concept, the running example and every chapter title's key words are in the main text, and the shot-list gate and report list every number and term with the section it came from (`output/<id>/fact_sources.json`). fix_story's pool is unchanged. |
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

## Phase 2: scene library

Everything is React in `web/src/motion/`, drawn in 1080 x 1920 design units, and **every component is a pure function of `t`**: no CSS animations or transitions, no timers, no `Math.random`. The capture renderer can therefore seek to any frame and get exactly that frame.

| File | What |
|---|---|
| `tokens.ts`, `time.ts` | Fields, colour meanings, fonts, safe lines; easing, spans, seeded random, polyline geometry. |
| `Stage.tsx`, `fonts.css` | `Frame`, `Fit` (scale to any width), `Icon` (from `icons.json`), `Overlay`. Fonts are OFL `@fontsource` packages, bundled — never fetched at render. |
| `objects/reference.tsx` | Set 1 (the useState reference): DeviceMock, EntityCard, SystemPanel, Connector, CodeWindow, TriggerChip, StatusPill, IconTile, TitleCard, CodeMapCard, TakeawayList, EndCard, DotGrid. |
| `objects/editorial.tsx` | Set 2 (the tokenization reference): KineticTitle, ChapterCard (entrance + chip fly-in), Chip/TokenRow/ChipTag, Stamp, LookupGrid + SearchBar, LookupTable, MatrixGrid, BigCounter, Bracket, Callout, RecapGrid, TextureBackground. |
| `chrome.tsx` | StepChip, ProgressSegments, SectionLabel, CornerMark. |
| `KaraokeCaption.tsx` | One sentence at a time, spoken words full ink, the rest 35 %. Even word timings until phase 3. |
| `transitions.tsx` | The 6 transitions, each an exit dim plus 0.55 s of field-colour shapes; `planTransitions` never repeats back to back. |
| `animations.tsx` | The 13 in-shot animations, `count_up` (14th), category highlight, zoom into a cell and the scan line. |
| `gallery/` | `#motion-gallery`: every entry with a frame scrubber beside the reference frames; `/fonts`, `/strip/<id>`, `/frame/<id>?t=`. |
| `motion.test.tsx` | `npm run test:motion`: every entry pure in `t` and moving; transition and number-format rules. |
| `shorts/reference_frames.py`, `web/public/reference/` | The timestamp manifest and the frames cut from the (git-ignored) reference MP4. |

Screenshots of every entry next to the reference are in `docs/reference/phase2/`.

Also in phase 2: every test suite now writes to a temp folder (`shorts/testing.py`, `SHORTS_OUTPUT_DIR` / `SHORTS_CAST_ASSETS_DIR`) instead of `output/` and `assets/cast/`.

Display font: **Anton** (approved with phase 2, 2026-10-09; `docs/reference/phase2/fonts_anton_vs_archivo_black.png`).

## Phase 2b: themes and tags

The **teaching approach** (the existing step, unchanged) is HOW the idea is explained: conceptual, analogy, comparison and so on. The **theme** (new) is the FORMAT of the reel: who speaks and what it feels like, such as an interview, a discussion or a story. The two combine. Themes apply to `REEL_STYLE=motion` only. Explainer and story modes, and every existing reel, are unchanged.

Pipeline: `setup (topic -> teaching_approach -> template) -> theme -> script -> scenes -> ...`. The runner's stages are now `setup -> theme -> script -> scenes -> voice -> timing -> render -> report`.

### The theme registry

The registry is `shorts/motion_themes.yaml`, loaded and validated by `shorts/motion_themes.py`. Adding a theme takes only a new entry, as long as it uses a template, hook style and avatar kind that already exist (`motion_themes.TEMPLATES`, `HOOK_STYLES`, `AVATAR_KINDS`). `motion_theme_test.test_a_new_theme_is_only_a_registry_entry` proves this.

| Theme | Tag | Template | Speakers (avatar) | Needs code | Works with | Incompatible with | Hook |
|---|---|---|---|---|---|---|---|
| classic_explainer | explainer | fix_story (own beats) | narrator | no | all but process_demonstration | — | symptom question |
| story | story | fix_story | narrator | no | real_world_example, analogy, conceptual_visual, direct_explanation, code | — | scene |
| interview | interview | fix_story | INTERVIEWER (host, asks) / CANDIDATE (language) | no | code, direct_explanation, comparison, conceptual_visual | — | question |
| interview_rapid_fire | rapidfire | fix_story | INTERVIEWER (host, asks) / CANDIDATE (language) | no | direct_explanation, code, comparison | process_demonstration, analogy | question |
| peer_discussion | discussion | fix_story | PEER_A (host, asks) / PEER_B (language, asks) | no | analogy, comparison, conceptual_visual, direct_explanation, code | — | question |
| mentor_student | mentor | fix_story | STUDENT (host, asks) / MENTOR (language, asks) | no | analogy, direct_explanation, conceptual_visual, code, real_world_example | — | question |
| bug_hunt | bughunt | fix_story | narrator | **yes** | code, process_demonstration, direct_explanation | analogy | claim (the bug report) |
| myth_vs_fact | mythvsfact | fix_story | narrator | no | comparison, direct_explanation, conceptual_visual, code | process_demonstration | claim (the myth) |
| common_mistakes | mistakes | fix_story | narrator | no | code, direct_explanation, comparison | analogy | claim |
| predict_the_output | predict | fix_story | narrator | **yes** | code, process_demonstration | analogy, real_world_example | question |
| under_the_hood | underthehood | fix_story | narrator | no | conceptual_visual, process_demonstration, direct_explanation, code | real_world_example | question |
| step_by_step_walkthrough | walkthrough | walkthrough (own beats) | narrator | no | process_demonstration, conceptual_visual, code, direct_explanation | — | how question |
| real_world_scenario | realworld | fix_story | narrator | no | real_world_example, analogy, direct_explanation, code | process_demonstration | scene |
| before_vs_after | beforeafter | fix_story | narrator | no | comparison, code, conceptual_visual | process_demonstration | question |

Each entry also has a description, the kinds of concepts it suits, hook openers and a brief, and its beat template.

- **Beat templates fit the existing contract.** Every fix_story theme maps all 11 fix_story beats: what each beat does in that format, who speaks (the first speaker named opens the beat), and whether it may ask. The beat order, shot count, word budgets, code beats and recap are unchanged.
- **No duplicated template.** The walkthrough template *is* `step_by_step_walkthrough` (`beats: walkthrough`), and `classic_explainer` *is* the original fix_story (`beats: fix_story`). Both use their template's own prompt and graders, unchanged.
- **Theme and template.** A theme names its template. The teaching approach still suggests one (walkthrough for process_demonstration). That suggestion now only pins the theme's template when a human chose it: `--template`, or the reviewer at the template gate (`setup.json` `template_source`). Otherwise the theme decides. A setup written before 2b counts as pinned.

### How the theme is chosen (`shorts/skills/theme.py`)

1. **Fixed rules first** (`motion_themes.theme_problems`), each logged with its rule name:
   - **requirement:** the theme needs code and the section has none (a fenced block, or an inline span with code punctuation; a bare `` `[CLS]` `` is not code), or the theme needs an avatar for the language.
   - **incompatible:** the approved teaching approach is in the theme's `incompatible_with`.
   - **template:** a human pinned the other template.
   - **variety:** the theme repeats the previous reel's theme, or would make more than 2 of the last 5 reels (the new one included). The history is the `tags.json` of earlier motion reels in the same language, ordered by `created_at`.
2. **Fit, by the LLM** (`SYSTEM_MOTION_THEME`, one call). It sees only the themes that passed step 1, plus the section, its candidate concept tags, the approved approach and the history, and returns `{theme, reason, concept_tags}`. With exactly one eligible theme no call is made (`only_candidate`).
3. **Validation.** The pick goes through step 1 again. A rejected pick gets **one retry**, with the reason. If both picks are rejected, or nothing was eligible, the template's fallback is used (**classic_explainer** for fix_story, step_by_step_walkthrough for a pinned walkthrough) and the reason is logged and saved.
4. **The pause.** The theme, its reason, source, cast, eligible list, fit check and tags are shown, with a money gate before the call. On approval they are saved as `output/<id>/theme.json` (`MotionThemeChoice`) and `output/<id>/tags.json` (`MotionTags`). Override with **`--theme <id>`**. A flag may relax variety (logged as an override) but never a requirement or an incompatibility. A resumed reel keeps its theme unless you pass `--force-stage theme`.

### Tags

Every motion reel gets one language tag, one theme tag and 1–3 concept tags, e.g. `#react #interview #plainvariable #rerender`.

- Tags are lowercase with no spaces: `#` plus letters and digits.
- Language tags come from a fixed list: `python javascript typescript react html css sql java c cpp cs` (`cs` covers material with no programming language). Theme tags come from the registry.
- Concept tags must be words, or adjacent word pairs, of the section. The LLM's tags are cleaned against the section, and if none survive the section's own candidates are used.
- The language comes from the section's fenced code, then the document's, then a language named in the document title, then the one named most often, else `cs`. Override with `--language`.
- Tags are saved in `tags.json` and printed in the report.

### Script by theme

- `write_motion_script(theme=, language=)`. A non-base theme replaces only the prompt's FORMAT and THE BEATS (`skills.script.motion_system_for`). LENGTH, WORDS, captions, CODE, VISUAL and ICONS are untouched, so the 2-minute cap (a cap, not a target), the source-scope rule and the topic-agnostic rules all still apply.
- Two-speaker themes write **speaker-labelled lines**: each caption, which is one sentence, carries `speaker` (`INTERVIEWER`, `CANDIDATE`). Labels never appear in `speech`. The hook repair has a themed prompt of its own.
- `MotionScript` gains `theme`, `language` and `speakers` (role → avatar → voice slot, set in Python). `CaptionChunk` gains `speaker`. All are optional, so phase 1 files load unchanged and are graded as their template's base theme.

### Avatars: contract only

`shorts/motion_avatars.yaml` holds one original character per course language, plus a shared **host**. Each has a name, a look note, a palette and a Chatterbox voice slot (`voices/motion/<slot>.wav`, recorded in phase 3).

- Only two-speaker themes use avatars: the asking role is the host and the answering role is the language's character, so a reel always has two characters and two voices.
- Palettes may not use coral, mint or lavender, which are reserved colour meanings. The loader rejects them.
- The rules for the artwork are in the file's header: no official logos or mascots or look-alikes, the professional flat motion style, and no stick figures.

### Graders and evals

| Grader | Rule |
|---|---|
| `motion_theme_speakers` (script, 17th motion grader) | One-narrator theme: no speaker labels, no cast. Two-speaker: every caption labelled with a theme role, each beat spoken only by its template's speakers and opened by the first, both roles speak, both are cast. The script's template is the theme's. |
| `motion_hook_curiosity` (themed) | A non-base theme's hook opens with one of its openers, asks when its style is `question`, and names a symptom when the theme requires one. Base themes are unchanged. |
| `motion_not_qa` (themed) | No speaker label in speech. Questions only in the hook, a beat marked `asks`, or a line by a role that `asks`. |
| `motion_theme_fit` | Registry entry, requirements met, approach not incompatible, pinned template respected. |
| `motion_theme_variety` | Not the previous reel's theme; at most 2 in the last 5. |
| `motion_tags` | Format, one language tag first, one theme tag second, 1–3 concept tags from the section. |

- `evals/cases.yaml` **E175–E197** (23 cases) cover all of these. The new case type `motion_theme_grader` is in `run_evals.run_motion_theme_case`.
- New golden fixtures, which are also the stubs for their themes: `usestate_interview_golden.json`, `usestate_peer_discussion_golden.json` and `usestate_bug_hunt_golden.json`. With the useState (classic_explainer) and tokenization (step_by_step_walkthrough) fixtures, five themes run end to end in stub mode.
- `shorts/motion_theme_test.py`: 34 tests.

```
SHORTS_STUB=1 python -m shorts.motion_reel content/react_usestate_basics.md --yes --theme interview
SHORTS_STUB=1 python -m shorts.motion_theme_test
python -m evals.run_evals
```

In stub mode the theme call picks the first eligible theme that has a golden fixture for the material, so consecutive stub runs rotate themes under the variety rule.

## Phases still to come

3. **Scenes and timing.** `MotionStage` (the player that lays a script's shots, transitions and captions on one timeline — moved here from phase 2 because SceneSpec defines what it plays), `SYSTEM_MOTION_SCENES`, SceneSpec validation and the `revision.py` loop, per-shot Chatterbox narration, and whisper-aligned timelines. Also adds the three scene graders. **Since phase 2b it also includes avatars, two-speaker scenes and two voices:** the avatar artwork (`shorts/motion_avatars.yaml`'s characters and host, as React components pure in `t`), scenes that place two speakers and show who is talking, and narration voiced per caption from each speaker's voice slot (two Chatterbox references per two-speaker reel).
4. **Render and QA.** Motion capture, MP4, frame checks (word count from the page, safe zones), motion judge rubrics, and the report.
5. **Polish.** A motion view in the web UI, `docs/RUNBOOK_MOTION.md`, and cleanup.
