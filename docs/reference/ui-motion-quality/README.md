# Motion reel quality round (2026-10-12)

Five parts: layout fixes, design directions (waiting for your pick), simple
language, scene variety and match, and small fixes. Everything ran in stub
mode, and no paid call was made. Nothing is committed. Your real reel in
`output/` was only read, never changed.

## What to open

| Where | What to check |
|---|---|
| http://localhost:5173/#motion-gallery/directions | **The design directions. Pick one.** The same five shots in today's look and in A / B / C, playing together. You can pause, scrub, or click a frame to see it full size. The last row shows each direction's transition. |
| `directions/side_by_side_settled.png`, `directions/side_by_side_mid.png` | The same comparison as still images: shots settled (4.2 s) and mid-animation (1.8 s) |
| `directions/transitions.png` | Each direction's code → how-it-works transition at 25 / 50 / 75 % |
| `layout/before__<context>.png` vs `layout/after__<context>.png` | Every scene type before and after the layout fixes, for each context (solo, narrator, duo, duo_characters) |
| `layout/stamp_and_chat_before_after.png` | The clearest single before/after |
| http://localhost:5173/#motion-reel?src=/motion-audit/duo_characters.json | The audit reel playing live (swap in `solo`, `narrator` or `duo`) |

## 1. Layout: every scene type audited

**How I checked.** `SHORTS_STUB=1 python -m shorts.motion_audit` builds one
reel per context through the real layout and plan code:
- 17 scene types (hook, kinetic statement, code window, token row, entity +
  stamp, entity → panel, trigger, icon row, big counter, callout, lookup
  table, and six full-frame cards).
- Four contexts: solo, narrator, duo, duo with characters.
- Together the scene types use every object kind in the library. A test
  checks that.

**Fixed:**
- **Stamp covering the card's words.** "BUG" sat over "On screen 0". The stamp
  component shifted itself to centre twice, so it landed up and left of its
  anchor. It now sits in the card's empty right half.
- **Characters drawn over the objects (two-speaker reels).** On tall shots
  like entity → panel and the hook, both characters stood on top of the
  panel. They now appear only where the objects fit above them; otherwise
  they step aside for that shot. This already applied to one-narrator reels.
- **Chat running into objects.** The chat now always starts below the
  shot's lowest object.
- **Clipped chat bubbles.** The newest bubble's badge and glowing ring were
  cut off. The row now reserves room for the badge, and older rows (small,
  still badges) use their bubble height. Both speakers' last lines fit.
- **Sizes that were too small for a phone:**

  | Element | Before | After |
  |---|---|---|
  | Status pill | 80 | 104 |
  | Trigger chip | 84 | 110 |
  | Token row | 76 | 96 |
  | Callout | 150 | 200 |
  | Big counter | 300 | 360 |
  | Gap between objects | 48 | 60 |

  The token row now shrinks to fit when it has many tokens.

**Checks.** All 840 stub combinations (every content section × every theme)
still place their scenes without errors. Your real reel's 4-object hook
still fits (994 of 1000 units).

## 2. Design directions: waiting for your pick

**What I built.** Three original directions, only inspired by the reference
reels: no copied frames, no Anton all-caps. They live on a proposal page
(`web/src/motion/gallery/directions.tsx`). **Nothing is applied to reels.**
The real renderer is unchanged.

**What they share.** All three show the same five shots with the same words
as the audit: hook, code, how it works, key idea, takeaway.

**What differs.** Each direction differs in layout, depth, type, colour,
transitions, camera moves, morphs and how key words animate. The full list
is on the page; the short version:

| | A · Notebook | B · Midnight Lab | C · Colour Block |
|---|---|---|---|
| Mood | Warm paper, ink, highlighter. Calm and human. | Night blue, glass, glow. "Inside the machine." | Big colour blocks, chunky type. Bold and playful. |
| Depth | Flat cards, ink outline, hard offset shadow | Frosted glass, glows, parallax layers | Long soft shadows; stickers overlap edges |
| Type | Manrope ExtraBold, sentence case | Thin + heavy Manrope, lit key words, mono labels | Archivo Black, sentence case, key words in pills |
| Transition | Page slides up over the last one | Zoom-through with blur | Circle wipe from the object you were looking at |
| Camera | Slow push-in on the part being explained | 3D tilt that settles, then drifts | Quick punch-in with a bounce on the key moment |
| Morph | The value flies along a drawn arc into React's memory | The card reshapes into the memory panel | The value tile grows into a big memory block |
| Key words | Highlighter swipe, hand-drawn circle | Come into focus from a blur, then glow | Pop in one by one; a pill slides under the key word |

**Fonts.** The directions use only fonts already bundled with the project.
Once you pick one, a dedicated typeface for it could be added (free, an npm
font package).

**What I need from you.** Pick A, B or C, or a mix (for example "A's
layout with C's transitions"). After that I'll apply it to the real
renderer, for new reels only.

## 3. Simple language

**Two new checks.** Both are in the script graders, which now number 21.
- **Reading level** (`check_motion_reading_level`):
  - The whole narration must read at Flesch-Kincaid grade 7 or below.
  - Any sentence of 10 or more words above grade 10 is named.
  - The concept's own name and glossary terms don't count against it.
- **Terms explained** (`check_motion_terms_explained`):
  - The first time a technical term is said, that sentence or the one next
    to it must explain it.
  - The terms are listed in `shorts/motion_terms.yaml`: render, state,
    component, prop, hook, setter, variable, function, JSX, DOM, cache,
    token, TLB, selector, and more.
  - A failure quotes the plain meaning to use.

**Changes to the writer and stub.**
- **Script writer:** the prompt now asks for a beginner viewer, short
  sentences and grade 7. It also lists the plain meaning of every
  technical term the uploaded material uses.
- **Goldens:** the golden fixtures were updated so they all pass.
- **Stub writer:** it explains its terms and skips long, hard sentences.

**Your real reel `plain_variable_no_rerender__motion`:**
- **Reading level:** grade 4.2, a pass.
- **Terms:** a fail. "variable" (s01) and "render" (s02) are never
  explained.

## 4. Scene variety and match

**Two new scene checks.** The scene graders now number 6.
- **Variety** (`check_motion_scene_variety`): no two shots in a row with the
  same main objects. No object kind as the main object on more than 3
  shots, and at least 4 different kinds per reel.
- **Match** (`check_motion_scene_matches_narration`): a shot's on-screen
  words must be said in its narration.

**Changes to the writers.**
- **Scene writer:** the prompt has a new "variety and match" section.
- **Default scenes:** these come from the free stub writer. They now use
  more of the library: callout and token row on setup, an entity card with
  a status pill on the second break, a token row on "name it". All golden
  default scene sets pass all 6 checks.

**Your real reel fails both checks.** I left it unchanged:
- **Variety:** an entity card is the main object on 7 of 11 shots, and s04
  and s05 show the same thing. This is the "clumsy" repetition you saw.
- **Match:** s01 shows "0, button, counter, frozen, tap", but its narration
  says none of them.

## 5. Small fixes

**Pacing (code only, no paid rerun).**
- **The fix:** after the forced aligner times each line, every voice clip
  is cut to its speech (0.06 s before the first word, 0.15 s after the
  last). The mix and captions use the cut clips. Lines without real word
  timing are left whole.
- **Measured on a scratch copy of your real reel:**

  | | Before | After |
  |---|---|---|
  | Length | 93.4 s | 86.2 s |
  | Mean silence between lines | 0.88 s | 0.60 s |
  | Longest silence | 1.40 s | 1.01 s |

- **To apply it to the real reel (free: local aligner, no API calls):**
  ```
  python -m shorts.motion_reel content/react_usestate_basics.md --topic plain_variable_no_rerender__motion --force-stage timing
  ```
  It redoes timing, render and report. It reuses the recorded voice and
  overwrites that reel's `plan.json` and mix, so copy the folder first if
  you want the old one. I have not run it.

**Invented-example warning.**
- **The bug:** it read words in code comments and strings as code names.
  `// no re-render asked` in s08 made "asked" look like an invented name.
- **The fix:** comments (`//`, `/* */`, `#`) and string literals are now
  removed first.

**Duplicate `_stem`.**
- **The bug:** `checks.py` had two `_stem` functions, and the second one
  silently replaced the first.
- **The fix:** there is now one, the suffix-list version.
- **Words affected:** 173 of 855 content words now stem differently.
- **Two eval results changed** (both still pass):
  - **E007 grounding:** 73 % → 76 % content-word overlap.
  - **E045 recap restate:** now cites "beat 2 restates beat 1 (67 % / 33 %)"
    instead of "beat 4 restates beat 1 (75 % / 12 %)".

## Tests

- **New test file:** `shorts/motion_quality_test.py` has 15 tests covering
  the stamp placement, characters stepping aside, audit coverage, clip
  cutting, comment words, reading level, terms, variety and match.
- **Test files updated:** `motion_scenes_fix_test` (new heights),
  `motion_script_test` and `motion_walkthrough_agreement_test` (21
  graders).
- **Full run results:**
  - All 58 `shorts/*_test.py` modules pass.
  - Evals: 212 passed, 0 failed, 12 skipped (the paid judge cases).
  - `tsc --noEmit` is clean, and `npm run test:motion` passes.
