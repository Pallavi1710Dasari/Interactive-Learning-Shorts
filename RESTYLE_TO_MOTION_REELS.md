# Restyle: motion reels (`REEL_STYLE=motion`)

Status: **Phases 1, 1b, 2, 2b and 3 done and approved (script contract, both templates, scene library, themes and tags, scenes / timing / voices). Since approved: the phase 3 badge change (language identities replace the avatars), the optional character layer, and per-language characters with the designer.** Built and verified with `SHORTS_STUB=1`, plus one short real Chatterbox sample to check caption timing. No real LLM call has been made in motion mode yet.

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
| narrative (was `story`; renamed in the 2b review so it is not confused with `REEL_STYLE=story`) | narrative | fix_story | narrator | no | real_world_example, analogy, conceptual_visual, direct_explanation, code | — | scene |
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

Every motion reel gets one language tag, one theme tag and 1–3 concept tags, e.g. `#react #interview #usestate #rerender`.

- Tags are lowercase with no spaces: `#` plus letters and digits.
- Language tags come from a fixed list: `python javascript typescript react node django html css sql java c cpp docker os cs`. `node` covers Node.js and Express, `os` is operating systems, and `cs` covers material with no programming language (data structures, AI). Theme tags come from the registry.
- **Concept tags are searchable concepts** (2b review). They are taken from the material's headings (the document title and the reel's own section titles) and its defined terms (`**bold**`, "called X", "known as X"). Two-word concepts are joined: "page table" becomes `#pagetable`. A general list of filler words ("finds", "screen", "different") is never a concept.
- `motion_tag_concepts` rejects a code identifier from the example (`#setcount`, `#count`), unless a heading names it (`useState` in "How useState creates and updates state" gives `#usestate`), and rejects any stray word.
- The LLM's tags are cleaned by the same rule; if none survive, the material's own candidates are used.
- The language comes from the section's fenced code, then the document's (a framework the material names wins over its base language: ```python in a Django lesson is `django`), then a language named in the document title, then the one named most often, else `cs`. Override with `--language`.
- Tags are saved in `tags.json` and printed in the report.

### Script by theme

- `write_motion_script(theme=, language=)`. A non-base theme replaces only the prompt's FORMAT and THE BEATS (`skills.script.motion_system_for`). LENGTH, WORDS, captions, CODE, VISUAL and ICONS are untouched, so the 2-minute cap (a cap, not a target), the source-scope rule and the topic-agnostic rules all still apply.
- **Length** (2b review): every theme except classic_explainer gets **40–120 s** (110–312 words). 120 s is a cap, not a target: the prompt says to explain the concept fully, then stop, never pad. classic_explainer keeps fix_story's 40–75 s, and the walkthrough keeps 60–120 s.
- Two-speaker themes write **speaker-labelled lines**: each caption, which is one sentence, carries `speaker` (`INTERVIEWER`, `CANDIDATE`). Labels never appear in `speech`. The hook repair has a themed prompt of its own.
- `MotionScript` gains `theme`, `language` and `speakers` (role → avatar → voice slot, set in Python). `CaptionChunk` gains `speaker`. All are optional, so phase 1 files load unchanged and are graded as their template's base theme.

### Avatars: contract only

`shorts/motion_avatars.yaml` holds one original character per course language (15, including node, django, docker and os since the 2b review), plus a shared **host**. Each has a name, a look note, a palette and a Chatterbox voice slot (`voices/motion/<slot>.wav`, recorded in phase 3).

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
| `motion_tags` | Format: one language tag first, one theme tag second, 1–3 concept tags. |
| `motion_tag_concepts` | Each concept tag is a heading term or defined term; code identifiers and stray words are rejected. |

- `evals/cases.yaml` **E175–E201** (27 cases) cover all of these. The new case type `motion_theme_grader` is in `run_evals.run_motion_theme_case`.
- New golden fixtures, which are also the stubs for their themes: `usestate_interview_golden.json`, `usestate_peer_discussion_golden.json` and `usestate_bug_hunt_golden.json`. With the useState (classic_explainer) and tokenization (step_by_step_walkthrough) fixtures, five themes run end to end in stub mode.
- `shorts/motion_theme_test.py`: 36 tests.
- `shorts/evidence_grouping_test.py` reads `evals/fixtures/react_props.md` (a rebuilt React props lesson) instead of a local upload in `output/uploads/`, and patches the renamed `write_and_grade_script_for_workflow`.

```
SHORTS_STUB=1 python -m shorts.motion_reel content/react_usestate_basics.md --yes --theme interview
SHORTS_STUB=1 python -m shorts.motion_theme_test
python -m evals.run_evals
```

In stub mode the theme call picks the first eligible theme that has a golden fixture for the material, so consecutive stub runs rotate themes under the variety rule.

## Phase 3: scenes, timing, avatars, voices

> The avatars described in this section were retired by the phase 3 badge change below; they remain in git history (`257df1c`).

The runner now runs `setup -> theme -> script -> scenes -> voice -> timing -> render -> report`. Scenes, voice and timing are built; render is phase 4. Until then a reel plays in the browser at `#motion-reel/<short_id>` (from the API server), or at `#motion-reel?src=<plan url>`.

### The scene format

A scene says what one shot shows (`schema.MotionScene`):
- its **field** (navy, blue, paper or yellow);
- the **transition** into it (`cut`, or one of the five field transitions);
- an optional tracked-caps **label**;
- **objects**: kinds from the phase 2 library;
- **actions**: a timeline in which each action is cued on 1–3 words copied from the shot's captions.

The vocabulary is one file, `web/src/motion/library.json`, read by Python (validation and layout) and the player (drawing). It lists every object kind with its props, maximum lengths, height, layout class (full-frame, placed, overlay or link) and allowed actions; the actions (`enter`, `exit`, `state`, `pulse`, `highlight`, `type`, `count`, `scramble`, `stagger`, `stamp`); the transitions; and the avatar art vocabulary. A test fails if a kind has no renderer, or a renderer has no kind.

Cues resolve in speaking order: a repeated word means its next occurrence, and the same cue twice in a row means "at the same moment". The build-up order is the addendum's: label, then object, then state change, then result, each on the word that names it.

**Python lays out, the player only draws.** `motion_scenes.layout_scene` stacks placed objects in the region from the library's heights: the middle of the frame for a solo reel, above the avatars for a duo reel. Connectors run between neighbours, and stamps sit on the region's centre. The timing stage resolves every cue to seconds. So what the graders checked is exactly what the player draws.

**Beat → scene.** `motion_scenes.default_scene` maps every beat of both templates to library objects, using only the script's own words: captions, `<b>` highlights, code, icons, takeaways, chapters and the running example. It is the scenes call's stub answer, and the fallback for any shot the LLM can't get right.

| Beat | Default scene |
|---|---|
| hook | navy; kinetic title of the question + a coral status pill naming the symptom |
| title | title card (concept, promise, icon tiles) |
| setup (code) / chapter (code) | code window typing in, lines lit on their highlight words |
| setup / break_1 / break_2 | chips of the highlighted terms, a coral pill on the symptom, the last chip turning coral |
| fix_idea | blue; the concept in display caps + its highlighted terms |
| fix_flow | trigger chip → connector pulse → mint result pill |
| code_map | code map card, parts lit on their words (no code: an icon row) |
| payoff | navy; the hook's objects again, now mint (mirrors the hook) |
| recap | takeaway list (walkthrough: recap grid) |
| cta | end card |
| name_it / example / chapter_card / chapter / result / takeaway | kinetic title / token row / chapter card / token row of the example's state / count + final row / kinetic title |

Field transitions rotate and never repeat. A walkthrough changes field per chapter (blue, paper, yellow, paper). Where the estimated timing would leave the frame still, a small highlight or pulse is added, cued on the content word spoken at that moment.

### The scenes call (`shorts/skills/scenes.py`)

`SYSTEM_MOTION_SCENES` gives the LLM the library, the rules and the script (readable, plus exact JSON for cues). The graders then check every scene. Each shot that fails gets a **repair call for that shot alone**, with the reasons; passing shots are kept. This is the motion counterpart of `revision.py`'s narrow repair; `revision.py` itself stays explainer-only. Retries are capped by `MAX_MOTION_SCENE_RETRIES` (default 2). A shot still failing after that uses its default scene, and the fallback is logged. The scene gate shows every object and every cue before anything is voiced.

### Scene graders (free, deterministic)

| Grader | Rule |
|---|---|
| `motion_scene_valid` | Kinds, props, lengths and types; targets and allowed actions; every cue is a spoken word, in order; at most 4 placed objects, which fit their region; a full-frame object stands alone. A field change needs a field transition, a same-field shot is a cut, the same transition never runs twice in a row, `type_scatter` only leaves the hook, and there is at most one stamp per reel. |
| `motion_payoff_mirrors_hook` | fix_story: the payoff shows the hook's object kinds on the hook's field, with the hook's failure now a success. walkthrough: the result shows the running example's final state. |
| `motion_change_cadence` | A visible change at least every 2.5 s: transitions, actions, and full-frame cards' own entrance steps (`builtin` in the library). Karaoke progress doesn't count. Run on the estimated clock at the scenes stage, and again on the real audio at the timing stage. |
| `motion_color_semantics` | Coral only on failure beats (hook, setup, break_1/2; a walkthrough example or chapter), mint only where something works. A stamp counts as coral. |

### Voices (`shorts/motion_voice.py`)

- **One clip per caption**, since a caption is one sentence with one speaker, synthesized by local Chatterbox from the speaker's **voice slot**. The narrator uses `motion_narrator`; a two-speaker reel uses the host's slot and the language character's (`motion_host` + `motion_react`, for example), so two speakers get two voices.
- A slot's reference clip is `voices/motion/<slot>.wav`. None are recorded yet, so slots fall back to the project's existing Chatterbox clips: the host and narrator to the interviewer clip, a character to the student clip. Each fallback is logged and recorded in `audio/manifest.json`.
- Chatterbox writes 32-bit float WAV, which Python's `wave` module can't read; the real sample found this. Every clip is converted to 16-bit mono PCM at 24 kHz before it is cached.
- The clips are laid on the reel's clock and mixed to `audio/reel.wav`, normalised to -14 LUFS.
- In stub mode every clip is silence of the estimated length.

### Real caption timing (`shorts/motion_align.py`)

Word times come from the audio, best source first, all free and local:
1. **Forced alignment.** wav2vec2 (`torchaudio` `WAV2VEC2_ASR_BASE_960H`, downloaded once, ~360 MB) with `torchaudio.functional.forced_align`, against the words we know were said. It runs in a resident worker, `shorts/motion_align_worker.py`, inside `venv-chatterbox`, which already has torch.
2. **faster-whisper word boundaries**, paired with the known words when the counts match.
3. **An even split** of the caption's measured length.

Each caption records its source, and the plan records the weakest. A caption word standing for several spoken words (`useState(0)` ← "use State of zero") spans all of them.

`motion_timeline.shot_timings` puts everything on one clock from either estimated or real caption lengths. Each shot has a 0.35 s lead and a 0.45 s tail; gaps are 0.15 s between captions and 0.3 s on a speaker change; title, chapter-card and cta shots have minimum lengths. `build_plan` then writes `output/<id>/plan.json`, the player's only input.

**The real sample** was one interview exchange: Juno's question and Rae's answer, 17 words, two voices. Both captions were placed by forced alignment. Word starts were within 62–66 ms on average of faster-whisper's independent timings (worst word 161 ms), every word was in order and inside its clip, and the clips were 2.8 s and 3.2 s. Forced alignment is the tighter of the two: whisper starts both first words at 0.00 s.

### Avatars (`web/src/motion/avatars/`)

- `Avatar.tsx` draws each character from `motion_avatars.yaml`'s new `art` field: body shape, head, hair, skin and accessories, coloured by its palette.
- The style is original flat shapes, the same as the cards: no logos, mascots or stick figures.
- There are 16 characters: a host plus 15 languages. Three states, all pure in `t`:
  - **idle:** breathing, a slow bob, and blinks at fixed times;
  - **talking:** the mouth on a hashed syllable rhythm, nods, and a gesturing hand;
  - **reacting:** brows up, eyes wide, a head tilt, and accent ticks.
- A palette's body colour may never be a field colour, or the character would vanish on that field. The loader rejects it.
- The player's copy of the registry is `avatars.generated.json`, written by `python -m shorts.motion_themes export-avatars`; a test checks it is in sync.

### Two-speaker scenes

- In a duo reel, objects stack above the stage and the two avatars stand at the bottom: the asking role (host) on the left, the answering character on the right, facing each other.
- **Turn-taking comes from the captions.** The speaker of the caption being spoken is *talking*, scaled to full size with a lit name tag. The listener is idle, or *reacting* for 0.9 s after the other asks a question, or when a result lands (a state or stamp action with a tone).
- Full-frame cards (title, code map, recap, end) hide the stage; there a small tag above the caption names the speaker.

### The player (`web/src/motion/scene/`)

- `MotionStage` / `MotionFrame` lay a plan's shots, field transitions, chrome (fix_story progress segments, walkthrough step chip, section labels, corner mark), karaoke captions and the duo stage on one timeline.
- It is a pure function of `(plan, t)`. The TS checks render all three demo plans at every shot's start, middle and end, twice each.
- `MotionPlayer` (`#motion-reel/...`) adds play and pause with the audio as the clock, a scrubber, shot buttons, the current captions with their timing source, and `window.__capture.seek(t)` for phase 4.
- The server serves `GET /api/motion/<id>/plan` and `GET /api/motion/<id>/audio`.
- `python -m shorts.motion_demo` writes three stub plans (interview, classic, walkthrough) to `web/public/motion-demo/`, so the player runs with only Vite.

Phase 2 fixes found on the way:
- `At` centring was overwritten by `popStyle`'s transform, so every centred pill and chip sat off centre.
- `CodeMapCard` can now highlight a part on line 2.

### Files

| File | What |
|---|---|
| `web/src/motion/library.json` | The scene vocabulary both sides read |
| `shorts/schema.py` | `MotionScene`, `MotionSceneObject`, `MotionSceneAction`, `MotionScenesDraft`, timing and plan models, `MotionShot.scene` typed, avatar spec |
| `shorts/motion_scenes.py` | Validation, cues, layout, change events, the default mapping |
| `shorts/motion_timeline.py` | The clock and the plan |
| `shorts/skills/scenes.py` | The scenes call and its repair loop |
| `shorts/motion_voice.py`, `motion_align.py`, `motion_align_worker.py` | Voices, mix, word timing |
| `shorts/motion_reel.py` | The scenes, voice and timing stages |
| `shorts/server.py` | Plan and audio endpoints |
| `shorts/motion_demo.py` | Writes the demo plans |
| `web/src/motion/avatars/`, `web/src/motion/scene/` | Avatars and the player |
| `evals/cases.yaml` | E202–E217 (`motion_scene_grader`) |
| `shorts/motion_scene_test.py` | 32 tests |
| `web/src/motion/motion.test.tsx` | Avatars and the full-reel stage |

Screenshots are in `docs/reference/phase3/`: every avatar in every state, two two-speaker frames, a single-narrator fix_story frame and a walkthrough frame, and the player.

```
SHORTS_STUB=1 python -m shorts.motion_reel content/react_usestate_basics.md --yes --theme interview
SHORTS_STUB=1 python -m shorts.motion_scene_test
SHORTS_STUB=1 python -m shorts.motion_demo     # then: cd web && npm run dev, open #motion-reel?src=/motion-demo/interview.json
npm --prefix web run test:motion
python -m evals.run_evals
```

## Phase 3 review (2026-10-09)

**Length: 40–120 s for every reel.** This covers every theme (classic_explainer included) and both templates, at 110–312 words. 120 s is a cap, not a target: both script prompts say to explain the concept fully, then stop, and never pad. `checks.MOTION_SECONDS` and `MOTION_WORDS` are the one place it is set. It supersedes the earlier 40–75 s / 60–120 s windows mentioned above, and eval E145 now records it (a 76 s fix_story passes).

**Voices.** The proposal is in `docs/reference/phase3/voices.md`: four voices (narrator, host, and two character voices shared across the languages), the clip requirements, and free sources with licences. Nothing has been recorded or downloaded. The registry now lets characters share a voice slot; it only forbids a character sharing the host's.

**Models: one file, `shorts/motion_models.yaml`.**
- Each LLM call a motion reel makes is listed by its label, mapped to a tier:
  - `deliberate` = `anthropic/claude-opus-5.5`: select, understanding, teaching approach, theme, script, hook fix, scenes, scene repair, and the phase 4 judge;
  - `mechanical` = `anthropic/claude-sonnet-5.5`: framing and question rewording.
- Ids were checked against OpenRouter on 2026-10-09; prices are in `usage.PRICES`.
- Parsing, tags, variety, layout, cue timing and every grader are plain code with no LLM call.
- `motion_reel` switches the routing on for its own run only (`motion_models.use()` → `llm._LABEL_MODELS`). Explainer and story keep `config.MODEL_*`.

**Cost.**
- Before a real run starts, the runner prints the whole reel's estimate (per step: model, calls, $/call, typical and worst) and asks once. `--estimate` prints it and stops, for free.
- During the run, every LLM call prints a line: step, model, tokens, cost.
- After the run, `output/<id>/cost.json` keeps every run's calls, and the report prints this run's spend and the reel's total across runs.
- For the useState lesson the estimate is about $0.56 typical and $1.38 worst case, under `MAX_REEL_USD` ($2.00).

**One real reel (the user runs it, not Claude):**

```
python -m shorts.motion_reel content/react_usestate_basics.md --estimate   # free: the estimate only
python -m shorts.motion_reel content/react_usestate_basics.md              # the real reel, up to the playable plan
```

The second command has no `SHORTS_STUB`. It shows the estimate and asks before anything is spent, then stops at every gate (topic, teaching approach, theme, shot list, scenes) for your approval. Voice (Chatterbox) and timing (forced alignment) run locally for free. It ends with `output/<id>/plan.json`, `audio/reel.wav` and `cost.json`, playable at `#motion/reel/<id>`.

**Web UI: the Motion section** (`web/src/motion/MotionSection.tsx`). It is separate from the explainer screens, which are unchanged.
- `#motion` lists every motion reel: reels in `output/`, stub or real, from `GET /api/motion` (needs the API server), plus the stub demos in `web/public/motion-demo/` (Vite only).
- `#motion/reel/<id>` and `#motion/demo/<name>` show one reel:
  - the player;
  - the theme with its reason and fit check;
  - the teaching approach;
  - tags;
  - the script shot by shot, with speaker labels, highlights, code and visual brief;
  - fact sources;
  - cost (per step and per call).
- There are links to the scene library (`#motion-gallery`) and the language identities (`#motion/identities`; this replaced the avatars page in the badge change).
- `shorts/motion_bundle.py` builds the reel data (`GET /api/motion/<id>/bundle`), and `motion_demo` writes the same shape for the demos.

**Standing rules** are in `CLAUDE.md`: the user reviews everything, everything is viewable, no commit before approval, no push unless asked, and no paid calls unless the user runs them.

## Phase 3 badges: language identities replace avatars (2026-10-09)

**The 16 SVG avatars are retired** (`shorts/motion_avatars.yaml` and `web/src/motion/avatars/` are deleted; both are in git history at `257df1c`). No reel draws a person.

**The identity registry: `shorts/motion_identities.yaml`**, loaded and validated by `shorts/motion_identities.py`.
- Each of the 15 course languages has a display name, a signature colour, an original geometric symbol (1–8 rects, circles or stroked paths on a 100 × 100 grid), a code file name (the code tab shows `App.jsx`, `styles.css`, `kernel.c` …) and a voice (`character_1` or `character_2`).
- The **host** is a neutral grey identity (#6C6F7A, a mic symbol) and is the asking role in every two-speaker reel.
- **Colours are never drawn raw.** Each derives two tones by moving only its lightness: `on_dark` reaches ≥ 3:1 on navy and blue, `on_light` reaches ≥ 3:1 on paper and yellow.
- **Reserved colours stay free.** The colour and both tones stay ≥ 60 RGB units from coral, mint and lavender. A failing entry is refused with the reason.
- `python -m shorts.motion_identities export` writes the player's copy, `web/src/motion/identity/identities.generated.json`. A test checks it is current.
- **Voices:** the 4-slot plan belongs to identities: narrator, host, `motion_char_1`, `motion_char_2`. The mapping is in `docs/reference/phase3/voices.md`. The fallback clips stay until real clips are supplied.

**In every motion reel** (`web/src/motion/scene/MotionStage.tsx`, `web/src/motion/identity/Identity.tsx`):
- a language badge (symbol + name) in the top-right corner for the whole reel;
- a hook that opens with `identity_title`: the symbol large and a chip such as "REACT · INTERVIEW". `scene_valid` requires it on the hook and only there;
- progress segments (and the walkthrough step chip) in the language tone;
- tags as chips on the end card;
- an optional 1 s intro sting, **off by default** (`MOTION_INTRO_STING=1` adds it to plans written from then on; the shots are offset by `MOTION_INTRO_SECONDS`).

**Two-speaker reels: a chat, not captions.**
- Circular badges with role labels: the host is grey with its role's initial, on the left; the language speaker shows the symbol in the language colour, on the right.
- Bubbles hold the spoken line with karaoke highlighting. The newest bubble is at the bottom, and older ones dim.
- Only the active speaker's badge glows and shows a waveform. The listener's badge is still (a test checks this).
- The chat has its own region (`library.json` `frame.chat`, y 880–1560). Scene objects lay out above it (`frame.duo`, y 240–840), so a bubble never covers an object.
- On a full-frame shot (title, code map, recap, end card) there is no chat. A small badge and label name the speaker above the normal caption.

**Single-narrator reels** keep the normal karaoke captions, plus the badge, the hook mark and the coloured progress.

**Runner:** `--section <id>` pins topic selection to one section (used by the OS and CSS demos); an unknown id prints "no such section".

**Evals:** E218–E222 cover an OS mentor & student golden, a CSS interview golden, default scenes for both, and a hook without the language mark being rejected.

**Where to look:**
- `#motion/identities`: the registry, the sting strip, and each identity's symbol, tones with contrast ratios, badge on all four fields and hook chip.
- `#motion/demo/<name>` for `interview`, `peer_discussion`, `mentor_os`, `interview_css` (two speakers) and `classic`, `classic_os`, `walkthrough` (one narrator).
- `docs/reference/phase3-badges/`: hook, dialogue, narrator and end-card frames in React, OS, CSS and CS, plus the registry page and the player.

## Optional animated characters: Arjun and Riya (2026-10-09)

**Imported** from the characters lab (`Web-Slides`, branch `lab/characters`, `slide-kit/characters-lab`, commit `d7d512d`, by jeevansravanth) into `web/src/motion/characters/`: `skins/`, `rig/` (with `Actor.tsx`) and `actions/`. The playground, `shoot.mjs` and `record.mjs` were left out. `SOURCE.md` there records the source, the three small local changes and how to update.

**Pure in t.**
- The lab's `<Actor time>` starts each gesture whenever its React effect runs, so the reel does not use it.
- `characters/performance.ts` lays every clip on the reel clock up front and feeds the lab's own `composeAt` and life layer. The same t gives the same pose.
- A cold seek to the end of a 72 s reel costs about 110 ms per character. Playback costs about 0.1 ms per frame.

**Lip-sync.**
- `characters/lipsync.ts` places the lab's mouth shapes inside each word's own start and end, using the forced-alignment timings of the Chatterbox audio (even timings in stub mode).
- The lips close in pauses, and a listener's mouth stays shut.

**The switch, off by default.**
- Turn it on with `MOTION_CHARACTERS=1` or `motion_reel --characters`.
- It applies only to interview, peer_discussion and mentor_student.
- Arjun plays the asking speaker on the left, Riya the answering speaker on the right.

**Gestures.**
- `shorts/motion_characters.py` is a deterministic, rule-based director with no LLM call, so it costs $0. It cues gestures and expressions on spoken words, like scene actions: "why" → shrug, counting words → count gestures, highlighted words → explaining gestures, the last line → thumbs up.
- The listener nods at the end of statements.
- One-handed gestures are mirrored so they face the other speaker.
- The vocabulary is in `library.json` under `characters`. A TS test checks every name exists in the rig.

**Never over objects or captions.**
- The characters have their own region (`frame.characters`, y 852–1250), below the scene objects (which end at 840).
- With characters on, the chat moves down to y 1262–1560 and is clipped to that region.
- On full-frame shots (title, code map, recap, end card) the characters are hidden.
- Badges, bubbles and the language identity are unchanged.

**Where to look:** `#motion/characters` (every expression and gesture on both characters, plus a lip-sync sample), `#motion/demo/interview_characters` (the playable demo), and `docs/reference/phase3-characters/`.

## Characters v2: one per language, a designer, one per speaker (2026-10-09)

**Per-language characters.**
- `shorts/motion_character_presets.yaml` (ours, outside the copied rig) defines:
  - the shared **host**: Arjun, with the tie in the host's grey;
  - a **default for every language** in `motion_identities.yaml`, each a different person whose top is the language's signature colour;
  - the lab's original Arjun and Riya, as extras.
- `shorts/motion_character_presets.py` validates every preset against the rig's option lists, and requires a default for every language.
- `python -m shorts.motion_character_presets export` writes `web/src/motion/cast/presets.generated.json`. A test checks it is current.
- Our TS code moved from `web/src/motion/characters/` to `web/src/motion/cast/`, so the copied folder holds only the copy.

**Designer** (`#motion/characters/designer?preset=<id>`).
- Pick a preset, then edit skin tone, hair, face, top and bottom (style and colour, with the language's signature and field tones as swatches), shoes, tie or hair band, glasses, beard, other accessories and build.
- It previews live: a looping wave, a lip-synced line, a point up and a thumbs up, on any of the four fields, plus the character in the reel's band with the badge.
- **Save** sends `PUT /api/motion-characters/presets/<id>` and writes `shorts/motion_character_presets.saved.yaml`. **Reset to default** sends `DELETE` and removes that entry. Bad values are rejected with 422.
- Without the API server the page shows the defaults and cannot save.
- A plan embeds the config it was made with (`MotionCharacterTrack.config`), so a save changes the reels made after it and never one already made.

**Per-reel override.** `motion_reel --character <preset>` picks who plays the language for that reel only (for example `--character riya`). It implies `--characters`, and an unknown id exits with the list of presets.

**As many characters as speakers.**
- Every two-speaker theme (interview, interview_rapid_fire, peer_discussion, mentor_student) gets two: the host asking on the left, the language's character answering on the right.
- Every one-narrator reel gets one: the language's character, centred, with its gestures cued on the narrator's words.
- `MotionShotPlan.characters` says per shot whether they show:
  - never on a full-frame card;
  - on a one-narrator shot, only when its objects fit the upper region (y 240–840, the same region two-speaker reels use). They are then laid out there, and the characters stand below them and above the captions.

**Demos.** `interview_characters` (React), `interview_java_characters` (Java, from the new `content/java_string_equality.md` and golden `java_interview_golden.json`; evals E223–E224) and `classic_os_characters` (one narrator).

**Screenshots.** `docs/reference/phase3-characters-v2/`.

## Approval fixes (2026-10-09)

**Contrast.**
- Small text must reach **4.5:1** against what is behind it. That covers role labels, speaker tags, chat bubble words (spoken, upcoming and older), corner badge names and end-card tag chips.
- Large symbols and big titles stay at **3:1**: the identity symbol, waveforms, the hook chip and the host badge's initial.
- Each identity gains `text_on_dark` / `text_on_light` tones at 4.5:1 (`shorts/motion_identities.py`).
  - They are exempt from the reserved-colour rule, which covers fills and marks. To read on navy a tone must be pale, and every pale tint sits near lavender.
- Upcoming and older bubble words are now dimmed by colour, never by transparency (`identity/contrast.ts` `readableDim`), so they keep 4.5:1. Older bubbles recede by their badge and border.
- The language speaker's bubble on the blue field uses a navy veil, so yellow highlights reach 4.5:1 there.
- `identity/contrast.ts` holds the colour functions the player draws with. The table on `#motion/identities` and `motion.test.tsx` check those same functions: 222 checks.

**Backdrop.** Each character stands on a soft round backdrop: a navy tint on the light fields, a light one on the dark fields. It fades out inside the characters' region, so it is never cut.

**Characters = speakers.** Every two-speaker theme gets two characters, `interview_rapid_fire` included. A one-narrator reel gets one.

**Saved presets are tracked.** `shorts/motion_character_presets.saved.yaml` is committed (empty until the designer saves), and a test fails if it goes missing or a `.gitignore` rule hides it.

## Reasoning fix: the first real reel's 400 (2026-10-09)

**What failed.** The first real motion reel stopped on its first call (select). OpenRouter answered `anthropic/claude-opus-5.5` with `thinking={"type":"disabled"}` with a 400: "Reasoning is mandatory for this endpoint and cannot be disabled." `llm._reasoning()` sent thinking off to every Anthropic model.

**Fix.**
- **Per-model reasoning** in `shorts/motion_models.yaml` (`reasoning`), applied by `motion_models.use()` for a motion run only:
  - Opus 5.5: `thinking: "on"` with `effort: low` (a 1024-token budget, the API minimum). This sends `thinking={"type":"enabled","budget_tokens":1024}`.
  - Sonnet 5.5: `thinking: "on"`, `effort: low` too. (Briefly set to off on 2026-10-10; OpenRouter refused it with the same 400, "Reasoning is mandatory", so it is on for good.)
  - `effort` is low / medium / high (1024 / 4096 / 12000 tokens); or give a `budget` directly.
  - The budget is added to each call's `max_tokens`, so thinking never takes the room the JSON needs.
  - The YAML is validated: every model a run uses needs a setting.
- **Explainer and story are unchanged.** Outside a motion run the map is empty, so their requests are byte-for-byte as before. `llm_reasoning_test` checks this.
- **Thinking never reaches a parser.** `llm.visible_text()` reads only `text` blocks (not `thinking`, `redacted_thinking` or `reasoning`) and strips any `<thinking>`/`<think>`/`<reasoning>` text a gateway inlines. `ask_json` and `text_of` both use it.
- **The estimate counts thinking.** Thinking is billed as output: a typical call counts 60% of its budget (`typical_share`), the worst case all of it. For the useState lesson: **$0.63 typical, $1.77 worst** (was $0.56 / $1.38), under `MAX_REEL_USD` ($2.00).
- **Preflight.** `python -m shorts.motion_reel --check-models` makes ONE tiny call per model with its reasoning setting, and reports OK or the exact error, with its billed cost: at most about $0.02 in all. With `SHORTS_STUB=1` it is a dry run that shows what it would send.

## First real reel fixes (2026-10-10)

The first real reel (`what_state_means__motion`, 7.4 of `content/react_usestate_basics.md`) failed at scenes. Its script is the fixture `evals/fixtures/motion/what_state_means_script.json`. Its run folder stayed on the other machine, so the per-attempt s01 diagnosis and the cost backfill for its earlier runs were skipped.

- **Scenes.** The hook and the payoff fall back together, so a fallback never breaks the mirror. The scenes prompt carries every kind, prop, height, region and action, and says plainly that there is no side-by-side layout: two things are STACKED, the failing one above. The `before_vs_after` theme now says the same instead of "side by side". (`shorts/motion_scenes_fix_test.py`)
- **Cost.** `output/<id>/cost.json` is written after every call and when a run ends however it ends (a crash or Ctrl+C included). `MAX_REEL_USD` counts the reel's earlier runs, not only the current one.
- **Source scope** (user rule). The explanation and the running example come from the selected section; other sections may supply supporting numbers and defined terms, labelled with their section in the facts table (`7.2 (supporting)`). New grader `motion_example_from_selected` (fix_story): a name the example is built from (identifiers in its code, `backticked` code in captions, camelCase/PascalCase names) that another section states and the selected section never does fails. On the first reel: `count` (s03, s08) came from 7.2 and fails; its "zero" is a supporting number and passes. The script prompt shows the selected section as MATERIAL and the rest as SUPPORTING SECTIONS. Walkthroughs keep `walkthrough_main_source`. An **invented** example (its names are in no section of the document) is allowed, not a failure, but the shot list and the report print `WARNING — invented example: likes (s03, s08), … — not in any section, please review` (`checks.invented_example_warning`).
- **Teaching approach.** New grader `motion_respects_approach`: what the approved approach's rationale rules out ("how useState is called is out of scope") is listed in the script prompt as binding, and an identifier it names may not appear in any shot's code (nor in the narration, unless the exclusion is only about how it is written). On the first reel: s08's `useState(0)` fails.
- **Routing.** `screen` (topic screening) is in `shorts/motion_models.yaml`. During a motion run an `ask_json` label missing from the YAML is an error before anything is sent.
- **Reasoning.** Opus 5.5 and Sonnet 5.5 both think (`effort: low`, 1024 tokens): OpenRouter refuses thinking off for both.
- **Handle.** `BRAND_HANDLE` / `MOTION_SERIES` in `.env` (documented in `.env.example`); each motion run prints the handle it uses.

Tests: `SHORTS_STUB=1 python -m shorts.motion_first_reel_fixes_test` (cost, source scope, approach, routing, reasoning).

## Phases still to come

4. **Render and QA.** Motion capture of `#motion-reel` through `window.__capture.seek`, the MP4 with `audio/reel.wav`, frame checks (word count from the page, safe zones), motion judge rubrics, and the report. Record the real voice slot clips (`voices/motion/<slot>.wav`).
5. **Polish.** A motion view in the web UI, `docs/RUNBOOK_MOTION.md`, and cleanup.
