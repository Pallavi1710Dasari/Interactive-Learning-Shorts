# Step 2 applied: camera + cursor, teaching avatars, the studio design, new themes and approaches (2026-10-13)

Reel: `variable_points_to_value__motion` (job `f64077e78448`). It was
re-planned from its approved scenes and recorded voice. Alignment, layout and
rendering all ran locally, with no model calls, so this cost $0.

Its `setup.json` now says `design: studio`. It said `midnight_lab`; the
original is kept in the session scratch folder.

| What | Where |
|---|---|
| The full reel (70.3 s) | `reel_full.mp4` (local, git-ignored), or in the app: `#motion-reel/variable_points_to_value__motion` |
| 21 moments, one sheet | `full_reel_sheet.png` (full size in `frames/`, the file name is the second) |
| Browser sweep | `sweep_full_reel.json`: 55 moments, 0 problems |
| Test clips and the proposals you approved | `../motion-step2-proposals/` |

## What applies to every new reel now

### 1. Camera + cursor (approved as shown)

The timing stage now runs the camera and cursor director on every reel, and
`motion_camera_safe` joins the timing checks. Two things changed since the
test clip:

- **The scenes step can direct them.** Two new actions any object accepts:
  `focus` (the camera zooms on the cue word) and `click` (the cursor clicks
  on the cue word). The scenes prompt explains both and says to use them
  sparingly. The director still covers code, memory slots, app screens and
  the CTA by itself.
- **On the board, the camera zooms inside the board.** Its viewport is the
  board's own area.

### 2. Teaching avatars (approved; the count fixed)

- **The sideways hand on "First" is fixed.** A count is now held:
  - the hand rises once beside the face, on the side facing the board;
  - between counts ("two things" → "First" → "Then") the arm stays up and
    only the fingers change.

  `motion.test.tsx` checks the arm never drops between two counts.
- **Board staging is the default** for reels with characters
  (`config.MOTION_STAGE`, default `board`; `band` is the old strip).
  Characters show on every shot except a full-frame title card or end card.
- **A reveal takes over the point.** When a reveal or state change happens
  while the arm is still pointing at something lesser, the point moves to
  it. This fixes a point that stayed on "Box" while "Name tag" was
  revealed.
- **New looks are the presets now** (`motion_character_presets.yaml`):
  - the student: curly hair, orange hoodie;
  - the CS mentor "Meera": bun, round glasses, watch;
  - every character uses the polished soft art with lit shading.

  One change from the test clip: the CS mentor wears the **CS signature
  colour (raspberry)**, not the clip's blue. Each language's character wears
  its language's colour, and a test enforces that.
- **The board was narrowed** to make room for the presenter beside it. On
  the board, code callouts stay left of where the presenter stands.

### 3. The studio design (replaces everything copied from the references)

The new default design for new reels is `studio`. Midnight Lab is still
selectable (`--design midnight_lab`). On new reels it keeps its night
background, tilt-in and zoom-through, and takes the new type, colours,
cards and chrome. Reels made before keep their exact look: plans before
rev 3 draw as they always did, and a test checks a palette never leaks into
them.

| Was (from the references) | Now (ours) |
|---|---|
| Ref 1 colours (indigo, amber, coral, mint, ink…) | 6 palettes: Chalkboard, Paper, Terminal amber, Deep teal, Plum & gold, Midnight. Each has fixed meanings: wrong red `#E5484D`, right green `#2BB673`, highlight marker yellow `#FFD43B`. |
| Manrope (and Anton) | **Bricolage Grotesque** for display, **Lexend** for body and captions (both OFL, bundled locally) |
| Glass cards, radius 48–54, deep shadow | Index cards: radius ≤ 22 and a short hard shadow. The cover card has a coloured top edge. |
| Icon tiles | Icons drawn plainly at text size; flow and cycle steps are outlined nodes |
| "// SECTION" labels | Section ribbon: a tab on the left edge with the step number |
| Segmented progress bar | Timeline thread down the left edge, one knot per shot |
| Iris, bar wipe, stripes, stack rise | Our own: focus pull, marker swipe, card stack, card flip |
| Grid floor, glow blooms, glowing key words | Matte palette background with fine grain and a soft vignette. Key words get a marker swipe as they are said. |
| Title card (series pill, giant title, icon tiles) | Cover card: the concept on an index card, the promise as a note, the language chip |
| Takeaway rows | Sticky-note recap with a marker tick on the note being said |
| Code window with traffic-light dots | Editor card with a file tab |
| Round pills | Tags with a pointed end and a punched hole |

**Which palette a reel gets.** It comes from its theme
(`library.json studio.palette_for_theme`; for example, mentor themes get
Chalkboard and interviews get Deep teal). Midnight Lab reels get Midnight.
This reel is mentor & student, so it is Chalkboard.

**Layouts.** Each shot gets an arrangement: column, inset left, inset right,
offset or split. Full-frame cards keep their own (cover, code, notes, end).
A deterministic chooser spreads them across the reel.

- **New check `motion_layout_variety`:** no layout on more than 40 % of the
  shots, and never three in a row with the same layout.
- It caught the first stub reel at 6 of 11 columns, which is why the inset
  arrangements exist.
- This reel: code 1, column 2, cover 1, end 1, inset left 2, inset right 1,
  notes 1, offset 1.

### 4. Themes and teaching approaches

**The 6 new themes** in `motion_themes.yaml` (20 in all):

- Live code-along
- Doubt clinic
- Whiteboard sketch
- Pause & predict
- Error decoder
- This or that

Each has its description, when it fits, speakers, template, hook, beats,
the approaches it works with or never with, and its tag. The theme step
offers them like the others, with a reason.

**A fix the new code-along exposed.** A walkthrough theme other than the
plain walkthrough never had its own format in the script prompt (walkthrough
themes got the generic prompt). It now gets the walkthrough prompt plus its
format block.

**The 7 new approaches** (14 in all):

- predict_then_reveal
- misconception_repair
- build_from_zero
- worked_example_then_try
- socratic_questions
- big_picture_then_zoom
- step_by_step_trace

Each one is added to:

- the schema;
- the AI's choice prompt (what it is, when it fits);
- the reviewer's one-line choices;
- the script guidance;
- the visual-strategy guidance;
- the web picker.

The step-by-step trace and build-from-zero approaches default to the
walkthrough template. Existing themes now list the new approaches they fit
(for example, mentor & student works with misconception_repair and
socratic_questions).

## What to check in the reel

| Time | What should happen |
|---|---|
| 0–3 s | Chalkboard background, the hook's `cart [?]` on the board, both characters. The student leans in. |
| 3–6 s | Cover card: "Variable" on an index card, the promise as a note, the Python chip. No characters on this card. |
| 6–12 s | Ribbon "1 The setup". The cursor types the line. The mentor points at the editor card. |
| 12–22 s | The memory slot `cart → [milk │ bread]`. The mentor points at it while the camera pushes in. |
| 22–30 s | The compare reveal. The point moves to "Name tag" as it slides in. |
| 30–40 s | "Two things", then "First", then "Then", on held fingers. The student's lightbulb, the mentor's thumbs up. |
| 40–50 s | Code map on the board, the camera on each token with its callout, clicks spaced out. |
| 50–57 s | Payoff: the arrow from `cart` draws to the list, green tick, lightbulb. |
| 57–66 s | Sticky-note recap, ticks on each note as it is said. No caption repeating them. |
| 66–70 s | End card: Follow pressed on "follow", Up next slides in, the hashtags. |

## Tests

- **New test modules:**
  - `motion_camera_test` (6)
  - `motion_teach_test` (4)
  - `motion_design_test` (5)
  - `motion_caption_glue_test` (3)
- **TS checks** (`npm run test:motion`): camera framing, cursor, aims landing
  on target, held counts, the voice-driven jaw, 6 palettes drawn pure, no
  palette leaking into an old reel.
- **Updated for intended changes:**
  - `motion_theme_test`: 20 themes, the new walkthrough theme;
  - `motion_choices_test`: studio is the default design;
  - `motion_step1_fixes_test`: plan rev 3.

## Known limits

- Neighbours of a zoomed target can be cropped at the viewport edge. The
  target itself is always whole; that's what the check enforces.
- The scenes step hasn't been run with the new `focus` / `click` actions
  yet. That needs a paid run. For this reel the deterministic director
  placed every move.
- The new themes haven't produced a real script yet, for the same reason.
  Every stub test passes with them.
