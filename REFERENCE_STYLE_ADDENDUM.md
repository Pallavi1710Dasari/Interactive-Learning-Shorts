# Addendum to RESTYLE_TO_MOTION_REELS: second reference reel (tokenization)

> Read this together with `RESTYLE_TO_MOTION_REELS.md`. Where they disagree, **this addendum wins**.
> Files in `docs/reference/`:
> - `tokenization-reel.mp4`: the second reference (3 min 14 s, 1080×1920)
> - `tokenization_frames.png`: one frame every 4 s, read left to right, top to bottom
> - `tokenization_keyframes.png`: 12 key frames, larger
> - `tokenization_transitions.png`: 6 chapter transitions, each about 1 s at 12 fps (rows a–f, frames numbered)
> - `tokenization_animations.png`: 6 in-shot animations, each 6 s at 2 fps (rows g–l)
> - `reference_reel.html`: the first reference (useState), still valid

---

## 1. What changes, in one paragraph

**These are house-style rules for every motion reel on every topic.** Tokenization is only the example they were taken from. Never hard-code anything to tokenization or to a specific reel.


We keep everything from `reference_reel.html` (UI objects, fixed colour meanings, mirrored payoff, $0 drawing in React/SVG). We **add** the tokenization reel's editorial look: bold display type, full-bleed colour chapters, a step-progress chip, numbered chapter openers, karaoke captions, and a single running example carried through the whole reel. We also add a second script template for "how does X work" topics. **Hard length cap: every reel is 120 seconds or less.** The tokenization reel is 194 s, which is too long, so copy its style but not its length.

---

## 2. Length rules (override §2.2 of the spec)

| Rule | Value |
|---|---|
| Absolute maximum | **120 s** (hard fail above this) |
| `fix_story` reels | 40–75 s, 110–200 words |
| `walkthrough` reels | 60–120 s, 160–300 words |
| Chapters in a walkthrough | 2–4 (the tokenization reel has 6, which is too many) |
| Words per chapter | ≤ 60 |
| If the source needs more than 4 chapters | Split into a series ("Part 1 of 2") at topic selection time. Never compress one reel past readability. |

Measure duration from real Chatterbox audio in phase 3, plus an estimate of 2.6 words/s in phase 1 graders.

---

## 3. Two script templates (extends §2.1)

`teaching_approach` picks one; the reviewer can override it at the gate.

**A. `fix_story`** for "why does X fail / what's wrong with Y" (misconceptions, bugs). This is the existing 11-beat structure from the spec. No change.

**B. `walkthrough`** for "how does X work" (processes and pipelines, like tokenization, a DNS lookup, page-table translation or a request lifecycle):

| # | Beat | What happens |
|---|---|---|
| 1 | `hook` | A question in giant display type ("HOW DOES AI READ YOUR TEXT?"), then a surprising one-line answer ("It only reads NUMBERS."). ≤ 6 s total. |
| 2 | `name_it` | "This is called tokenization." The concept name, ≤ 3 s. |
| 3 | `example` | "Let's follow one sentence: …" introduces **one running example** that every chapter transforms. |
| 4… | `chapter` × 2–4 | Each opens with a **chapter card** (step number plus a title line, ≤ 2 s), then 1–3 shots showing what happens to the running example. |
| n-3 | `result` | The before and after of the running example ("two words became seven tokens") with a big counter. |
| n-2 | `takeaway` | One practical rule in display caps ("COUNT TOKENS WITH YOUR MODEL'S OWN TOKENIZER."). |
| n-1 | `recap` | A numbered grid of the chapter names ("Tokenization in 4 steps"), with the final state of the example underneath. |
| n | `cta` | Follow / up next, ≤ 3 s. |

Walkthrough rules: the running example must appear in every chapter, and its state must carry forward (the output of chapter k is the input of chapter k+1). A grader checks that the example's tokens or values are consistent across shots. Real numbers make it concrete ("about 1.2 lakh pieces", "768 numbers"), but each one must be taken from the source material.

---

## 4. Visual system additions (extends §3 of the spec)

### 4.1 Palette: add chapter fields, keep meanings

Sampled from the reel:

| Token | Hex | Use |
|---|---|---|
| `field.navy` | `#091025` | Hook, dramatic moments, closing |
| `field.blue` | `#283EE6` | Chapter openers and "big idea" beats |
| `field.paper` | `#ECF0F7` | Detail and diagram shots (replaces `#F3F4F9` as the default canvas) |
| `field.yellow` | `#FDD13E` | One chapter per reel at most, for emphasis |
| `accent.yellow` | `#FDD13E` | The key value/word on dark fields (same role as amber) |
| `ok` / `bad` | mint / coral | YES/NO tags, stamps (meanings unchanged) |
| `special` | lavender `#B9A8FF` | Special or system-added items (e.g. [CLS]/[SEP]) |

The background colour can change **per chapter**: navy, then blue, then paper, then yellow, then paper. Colour *meanings* for objects stay fixed, as in the spec. On dark fields, cards invert (dark surface, light text, same accents).

### 4.2 Typography

- **Display:** a heavy, tight grotesk in all caps for hooks, chapter numbers and takeaways. Use an OFL font bundled locally (e.g. Archivo Black or Anton; pick the closest to the reel and show me). Chapter numbers are huge (around 40 % of the frame width): "01", "02"…
- **Body/UI:** Manrope (unchanged).
- **Mono:** JetBrains Mono for tokens, IDs and code (unchanged).

### 4.3 New chrome

- **Step chip** at the top-left on every chapter shot: `STEP 02 / 04` with a small segmented progress bar. It replaces the full-width progress segments when the template is `walkthrough`.
- **Chapter card:** "STEP 3 OF 4" in small caps, the giant number, and a 1-line title, on a full colour field.
- **Small section labels** in tracked caps above diagrams ("THE SHELF", "BATCH", "ATTENTION MASK", "FOLLOW ONE SENTENCE").

### 4.4 Captions: replace the top pill

Follow the tokenization reel:
- **Position:** bottom-left, left-aligned, in a band at 70–80 % of the height (stays above the 82 % safe line), max 2 lines, about 6 % side margin.
- **Karaoke reveal:** words already spoken are full ink (white on dark, ink on light), words not yet spoken are dimmed to about 35 % opacity, and the line shows one sentence at a time. It is driven by faster-whisper word timings.
- **Highlights:** 1–2 keywords per sentence in the accent colour (yellow on dark, blue on light).
- **No background pill.** Contrast comes from the field colour.
- This replaces the 3–5 word chunk rule: a caption is now **one spoken sentence of ≤ 14 words**. Update `check_motion_caption_chunks` to match.

### 4.5 New scene objects (add to the library)

| Object | Seen in the reel | Generic use |
|---|---|---|
| `KineticTitle` | "HOW DOES AI READ YOUR TEXT?", "COUNT TOKENS…" | Hooks and takeaways in display caps, word-by-word reveal |
| `ChapterCard` | "STEP 3 OF 6 / 03 / Add two special tokens" | Every walkthrough chapter |
| `TokenRow` / `Chip` | `To` `##ken` `##ization` `matters` `.` | Tokens, list items, packets, words, bytes |
| `ChipState` tags | YES (mint) / NO (coral) on a chip | Match or miss, hit or fault |
| `Stamp` | "NOT ON THE SHELF" | One strong verdict per reel, max |
| `LookupGrid` | Vocabulary grid with a search bar | Vocabularies, hash buckets, caches, page tables |
| `LookupTable` | ID → token table with a highlighted row | Any key → value mapping |
| `MatrixGrid` | Batch grid, attention mask of 1/0 | Batches, matrices, memory frames, bitmaps |
| `BigCounter` | "5 TOKENS", "768", "2 → 7" | The result of a step |
| `Bracket` / `Callout` | "SUMMARY SEAT", the review bubble | Labelling part of a row |
| `RecapGrid` | "Tokenization in six steps" numbered grid | Walkthrough recap |
| `TextureBackground` | Falling digit matrix behind the hook | Hook only, low contrast, decorative |

Keep all objects from the first reference (DeviceMock, CodeWindow, EntityCard, SystemPanel, Connector, TriggerChip…). Both sets share the same tokens and the same time-driven player.

### 4.6 Motion and transitions (the most important part of this addendum)

Study `tokenization_transitions.png` and `tokenization_animations.png`, and scrub the MP4 itself around the timestamps below (extract frames with ffmpeg at 10–30 fps). Build every item below as a reusable, time-driven component, so any reel can use any of them.

**A. Chapter transitions (the cut between colour fields).** Each lasts 0.4–0.6 s, uses an ease-in-out curve, and accent-coloured shapes lead the new field in. The reel uses a different one at each chapter change, and so should we: rotate them and never repeat the same one twice in a row.

| Name | In the reel | What happens frame by frame |
|---|---|---|
| `iris` | 6.3 s (row b) | A ring in the accent colour grows out of the key word, and the new field fills its centre and then the whole frame. |
| `bar_wipe` | 17.8 s (row c) | A vertical accent bar sweeps left to right; the new field is revealed behind it. |
| `double_bar_wipe` | 50.0 s (row d) | Two bars (accent plus the new field colour) sweep left to right, with the old content blurring and squeezing as they pass. |
| `diagonal_stripes` | 117.0 s (row e) | Two diagonal bands (yellow plus the new field colour) sweep across at about 30°. |
| `stack_rise` | 160.0 s (row f) | Horizontal bands (accent, then the new field) rise from the bottom like a stack. |
| `type_scatter` | 2.3 s (row a) | The hook words rotate and scatter outward, with a one-frame flash, and are replaced by the answer line in the bad/accent colour ("IT CAN'T."). Hook only. |

Inside a chapter, use plain hard cuts or element-level animation only. Field transitions are only for chapter and beat changes.

**B. Chapter-card entrance.** After a field transition, the giant step number fades in from about 20 % to 100 % opacity while scaling from 0.92 to 1, over about 0.5 s. The title line then types in, followed by the small "STEP 3 OF 4" label. Hold it for about 1.5 s, then the step chip appears top-left and the content builds in.

**C. In-shot animations** (each one reusable, driven by timeline actions):

| Action | In the reel | What happens |
|---|---|---|
| `text_scramble` | 7–9 s (row g) | Random characters ("NUM9351") settle letter by letter into the real word ("NUMBERS"). |
| `type_assemble` | 10–12 s (row g) | Letters slide in one by one to build a word in display type, then an underline draws in. |
| `arrow_draw` | 8 s, 178 s | An arrow stroke draws from the start to the end of its path. |
| `typewriter_cursor` | 18–20 s | A blinking cursor types the running example. |
| `grid_cascade` | 30–34 s (row h) | Grid tiles flow in column by column with a slight zoom-out, so the grid grows denser to show scale. |
| `scan_window` | 58–64 s (row i) | A selection box sits over a word with a NO tag and shrinks from the right until it matches. The tag flips to a mint YES, a connector line draws to the matching shelf item, and the matched piece drops to the result row. |
| `slot_scroll` | 122–126 s (row k) | Table rows scroll like a slot machine and stop on the matching row, which then highlights. |
| `chip_insert` | 84–86 s (row j) | New chips (e.g. [CLS] and [SEP]) slide into the ends of a row and push the others apart. |
| `ghost_word` | 87–89 s (row j) | A huge outlined word ("WHY?") fades in behind the content and fades out as the explanation starts. |
| `counter_morph` | 178–181 s (row l) | A big number appears, an arrow draws, and the new number pops in using the accent colour ("2 → 7"). |
| `stagger_rows` | 181–184 s (row l) | Rows of a comparison appear one by one, about 120 ms apart. |
| `stamp` | ≈ 40 s | A rotated verdict stamp ("NOT ON THE SHELF") slams in with a slight overshoot and a tiny shake. At most one per reel. |
| `search_type` | ≈ 38 s | A search bar types a query and the matching grid cell lights up. |

**D. Pacing rules seen in the reel.** These replace or extend the spec where stated.

- Field or chapter transitions happen about every 12–30 s. Smaller element animations fill the time in between.
- Build-up order inside a shot is always: label, then object, then state change, then result. Each step is tied to the spoken word that names it (snap to whisper timings).
- Captions advance word by word in sync with the voice (karaoke, §4.4). This is the main thing that keeps a mostly still diagram feeling alive.
- The reel moves on screen only about 22 % of the time, and some shots hold for 3–4 s. **For our reels, keep the stricter rule: a visible change at least every 2.5 s.** Karaoke caption progress does not count as a change.

**E. Quality bar.** Every transition and animation must be checked frame by frame in the `#motion-gallery`, with a scrubber that steps through `t`. Show each one next to the matching frames cut from the reference MP4.

---

## 5. What not to copy from the tokenization reel

- The **194 s length** and **6 chapters**. Cap at 120 s and 4 chapters (§2).
- Shots that hold an unchanged diagram for 8–10 s while the caption reads out a long sentence. The "something changes every 2.5 s" rule still applies.
- Dense tables with 20+ tiny cells that can't be read on a phone. Show at most around 12 readable cells and fade the rest as texture.

---

## 6. Graders and evals to add or update

- `check_motion_duration_cap`: estimate ≤ 120 s (phase 1), real audio ≤ 120 s (phase 3). Hard fail above.
- `check_motion_template_beats`: the beat order for `fix_story` **or** `walkthrough`.
- `check_walkthrough_chapters`: 2–4 chapters, ≤ 60 words each, each chapter has a `ChapterCard`.
- `check_walkthrough_running_example`: the example appears in every chapter, and its state carries forward.
- `check_motion_caption_sentences`: ≤ 14 words, ≤ 2 highlights, never splits a code token (this replaces the chunk rule).
- `check_motion_numbers_sourced`: every number in the narration appears in the source section.
- Evals (each with a `why`): a 6-chapter walkthrough (fail), a 130 s script (fail), an example that changes between chapters (fail), an unsourced number (fail), a good 3-chapter walkthrough (pass), and a tokenization-style golden fixture **cut to ≤ 4 chapters and ≤ 120 s** (pass).

---

## 7. Impact on the phases

- **Phase 1 (done):** needs a small follow-up, **phase 1b**: add the `walkthrough` template, the duration cap, the sentence-caption rule and the new graders and evals. Keep the existing `fix_story` fixtures passing (re-cut their captions to sentences). Add a third golden fixture: a 4-chapter, ≤ 120 s tokenization walkthrough built from `content/` material if it exists, or from a short source `.md` you write from the reel's narration.
- **Phase 2:** build both object sets, the chapter fields, the new caption component, **all 6 chapter transitions, the chapter-card entrance and all 13 in-shot animations from §4.6**. The gallery shows each object on paper **and** on a dark field, plays every transition and animation with a frame scrubber, and shows each next to the matching frames cut from the reference MP4.
- **Phases 3–5:** unchanged, except that the karaoke captions need word timings and the duration cap is checked on real audio.

Before coding, reply with your plan for phase 1b and phase 2 and anything that conflicts with work already committed.

---

## 8. Findings (from scrubbing the MP4 frame by frame, 2026-10-01)

Frames were cut from `tokenization-reel.mp4` at 8–20 fps around every timestamp in §4.6. Where a finding here disagrees with §4.6, **this section wins**: it is what the file actually shows.

### 8.1 Corrected timestamps

| Item | §4.6 says | The MP4 shows |
|---|---|---|
| `typewriter_cursor` | 18–20 s | ≈ 14–16 s. 18–20 s is the `bar_wipe` into chapter card 01. |
| `grid_cascade` | 30–34 s | ≈ 33–35 s. 30–32 s is an `iris` out of "3 pieces" and then the chapter 02 card. |
| `search_type` | ≈ 38 s | ≈ 47–48 s |
| `stamp` | ≈ 40 s | ≈ 48–49 s, straight after the search finds nothing |
| `count_up` (new, 8.2) | — | ≈ 37–41 s |
| `slot_scroll` | 122–126 s | The table holds until ≈ 125.5 s; the scroll itself is ≈ 125.5–126.5 s. |

The others (`type_scatter` 2.3 s, `iris` 6.3 s, `bar_wipe` 17.8 s, `double_bar_wipe` 50.0 s, `diagonal_stripes` 117.0 s, `stack_rise` 160.0 s, `text_scramble`, `type_assemble`, `scan_window`, `chip_insert`, `ghost_word`, `counter_morph`, `stagger_rows`) are where §4.6 says. The machine-readable list is the gallery's timestamp manifest (phase 2), and it is the one place these times live in code.

### 8.2 Moves §4.6 does not list

These are house style too. Build each one as a reusable, time-driven piece.

- **Exit dim.** Before every field transition, the old content and its caption fade to about 50 % over ≈ 0.3 s, and only then do the transition shapes come in. Every transition starts with it.
- **Chip fly-in.** When a chapter card leaves, its giant number shrinks and flies to the top-left, where it becomes the number in the step chip (`STEP 02 / 06`). Copy it: the card's exit and the chip's entrance are one move.
- **`count_up`, the 14th animation.** A framed counter rolls from 0 up to its value over ≈ 3 s, easing out, with the digits grouped as the source writes them (Indian grouping "1,20,000" in this reel), while the content behind it dims. Its final number obeys `check_motion_numbers_sourced` like any spoken number.
- **Category highlight.** Grid cells light up by group (mint, then yellow) while small legend chips appear above the grid ("WHOLE WORDS", "## PIECES"). Each group lights on the word that names it.
- **Zoom into a cell.** The camera pushes into one grid cell; it grows to a readable chip with a state tag under it ("ON THE SHELF") while the rest of the grid blurs and dims.
- **Scan line.** While the search types, a thin accent line sweeps down the grid, showing the lookup is a search through every cell.

### 8.3 Smaller details of the listed moves

- **Chapter-card entrance.** In the reel the title fades in rather than typing, and the "STEP 2 OF 6" label arrives with it. We keep §4.6 B's order (number, then title, then label) but the title may fade or type.
- **`type_scatter`** has one full-frame grey flash frame, and the first word of the answer ("IT") punches in under the hook just before the hook words scatter.
- **`iris`** grows from a small solid accent disc on the key word; the new field opens as a hole inside it, so for a few frames the shape is a ring.
- **`double_bar_wipe`** squeezes the outgoing content into vertical slivers at the leading edge of the bars.
- **`stack_rise`**: the accent band rises with the new field directly under it, and the accent band thins as the new field pushes it off the top.

### 8.4 Decisions (2026-10-01)

| Topic | Decision |
|---|---|
| Coral and mint | Transitions use **field colours only** (navy, blue, paper, yellow), never coral or mint. The reel's coral diagonal band is not copied. The hook's answer line ("IT CAN'T.") may be coral, since it is a failure moment. |
| Questions | `walkthrough` chapters may ask at most **one** short rhetorical question per chapter, answered in the very next sentence. `fix_story` stays strict: only the hook asks. |
| Long words | Up to **2** extra terms over 4 syllables per reel, if the source uses them, they are shown on screen, and they are explained in plain words in the same sentence. |
| Series split | Deferred. A walkthrough with more than 4 chapters simply fails. |
| fix_story length | Both rules apply: 110–200 words **and** an estimate inside 40–75 s, so about 110–195 words at 2.6 words/s. |
| Numbers | Counts the grader can recompute from the running example's own states pass ("two words became seven tokens"). Step numbers on chapter cards pass. |
| Short beats | Word minimums are per beat: `name_it` and `chapter_card` may be 3 words. The walkthrough hook may be 6 s. |
| Visible change | Karaoke caption progress does not count as a visible change. |
| Walkthrough hook | A "how does / what happens" question plus an answer line that does not name the concept. No symptom word needed. |
| Recap and code | The 3-icon recap and the code-shot rules apply to `fix_story` only. A walkthrough's recap is the numbered `RecapGrid`, inside the same 24-word cap. |
| Reference MP4 | Not committed (`.gitignore`). The extracted reference frames and the timestamp manifest are committed instead. |
