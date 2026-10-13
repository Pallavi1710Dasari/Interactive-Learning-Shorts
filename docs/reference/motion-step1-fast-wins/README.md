# Step 1: caption layout, CTA timing, bugs and removals (2026-10-13)

Reel: `variable_points_to_value__motion` (job `f64077e78448`).

The plan was rebuilt from the reel's approved scenes and recorded voice clips.
Forced alignment, mixing, layout and rendering all ran locally. There were no
model calls, so this cost $0.

## Where to look

| What | Where |
|---|---|
| Before vs after, 8 matched moments | `before_after.png` |
| The new reel (70.3 s, same as before) | `reel_after.mp4` (local only: mp4s in docs/reference are git-ignored), or in the app: `#motion-reel/variable_points_to_value__motion` |
| The old reel | `before/reel_before.mp4`, `before/contact_sheet_before.png` |
| Full-size frames of the new reel | `after/t*.png` (the file name is the second), all on one sheet: `contact_sheet_after.png` |
| Browser layout sweep of the new reel | `sweep_real_reel.json`: 55 moments, 0 problems |

Old reels are unchanged. Every change below applies only to plans written
with `rev: 2`, which the timing stage now stamps on every new plan. A plan
with no `rev` is drawn as before. The one exception is the code-map highlight
bug fix, which applies to every plan.

## 1. Caption / speaker box layout

- When characters are on screen, the chat now has its own zone. It starts
  48 px below the characters (`library.json` `frame.chat.bubble.avatar_gap`)
  and ends at the safe line (y 1574).
- Student bubbles are anchored to the left edge and mentor bubbles to the
  right edge, each with a 65 px side margin (6 %). A bubble is at most 756 px
  wide (70 %).
- Only whole bubbles are shown. The newest bubble sits at the bottom, and
  older ones are dimmed.
- **New check `motion_caption_layout`** (Python, on the plan). It fails when a
  caption zone:
  - overlaps a character, an object box, the section label or the progress bar;
  - leaves the safe zone;
  - is too short for one of its bubbles.
- **The browser audit** (`overlap.ts`, run by `python -m shorts.motion_sweep`)
  now measures caption *boxes* too, not just text. It reports:
  `caption-character`, `caption-visual`, `caption-overlay`, `caption-unsafe`.
- I proved the audit can fail by moving the chat onto the characters, onto
  the memory panel, and below the safe line. It reported each case.

## 2. Timing check failure and its cause

- **The failure.** The CTA had two actions: enter, and a pulse at 1.5 s. Its
  built-in animation ended at 1.24 s, so nothing moved for the last 2.6 s.
- **The CTA fix.** The end card is now cued on its own words (`motion_tidy.cta_actions`):

  | Step | Cue word |
  |---|---|
  | Follow button pressed, with a ripple, then "Following ✓" | "Follow" |
  | Up next card slides in | "Next" |
  | Hashtags pop in | one per following word |
  | Final settle | the last word |

  Hashtags that run out of words pop in with the settle. The shot already ends
  0.45 s after the last word, so it doesn't hold still at the end.
- **The cause, for every template.**
  - The timing stage now runs a cadence repair on the *real* audio clock for
    every shot. Wherever the frame would hold still too long, it adds an
    action cued on a word spoken there.
  - The repair re-flashes the item being talked about. It never moves a
    highlight to a different item.
  - Count-ups, travels and typing now count as motion for their whole
    duration, not just their first frame.
  - A test plays every scene of all 10 golden fixtures 1.5× slower than
    estimated. This covers every full-frame card kind, and none holds still
    over 2.5 s.
- On this reel the longest still stretch is now 1.9 s (it was 2.6 s).

## 7. Removals and bugs

| Item | Now |
|---|---|
| Grey "S" badge, duplicate speaker labels, audio-wave icons | gone when characters are on screen. The role label above the bubble is the one speaker indicator. |
| `@learnthesimpleway` on every scene and on the title card | shown once, on the end card |
| "PYTHON" chip in every corner | shown once, as a chip on the title card (it replaces the handle there). Also in the tags. |
| Highlight sliding off "cart" (`# ca  :`) | **cause:** a part whose code wasn't literally in the lines (`[ ]`) was placed at column 0. Parts are now located on real code lines, and a bracket pair matches its whole span. A part that can't be found gets no highlight. Fixed for old plans too. |
| `# cart: the variable` comment used as a label | removed (`motion_tidy.strip_comment_labels`). The code map is now real code, with a callout and a leader line to each token. A part's callout appears when the narration first reaches it, and stays. |
| Memory panel "tag \| cart" | turned round to `cart → [milk │ bread]`. The name tag is on the left, an arrow points to the list box, and the value comes from the reel's own code. |
| "cart → list" scene (s08) | **kept with a new picture** (review round 2). The student's "Now I get it…" line now shows `cart` with an arrow that draws onto `[milk │ bread]` and turns green with a ✓ on "…the list that does". This mirrors the hook's `cart [?]`, and the value comes from the reel's own code. **Rule:** a shot whose objects all repeat an earlier shot's objects, and which only relabels them (no tap, travel, count, reveal, type or reset), is low value. It gets a picture that shows something new when one exists. Otherwise it is dropped. |
| Recap caption repeating the cards | when the cards are on screen there is no caption. The narration still plays. |
| Empty-looking "Name tag" card before the reveal | the revealed side now slides in solid from the right. The old pop-in was translucent for its first frames, which read as an empty slot. |
| Glowing halos behind the avatars, grid floor | **not changed.** These go with the step 6 restyle, as you asked. |

**New checks**

- `motion_redundant_overlays`: a caption that repeats an on-screen card's
  words (80 % or more of a 3+ word label). Code read aloud doesn't count.
- `motion_decorative_elements`: an object with no words that no action
  makes do anything.

The scenes prompt now asks for these too:

- no comment labels in code;
- slots read name → value;
- the payoff must show the fix working, not relabel the hook.

## Things to check when you watch

- s03 to s06: the bubbles sit on their speaker's side, below the characters,
  with a clear gap.
- s07 (41 to 50 s): the code has callouts. The highlight stays on its token.
- s09: the recap has no caption under the cards.
- s10: Follow is pressed on "follow", Up next slides in on "next", then the
  hashtags.
- s08 (51 to 57 s): the arrow from `cart` draws onto the list, which turns
  green on "…the list that does".

## Review round 2 fixes

- **"The= sign" and "The[] on the right" in captions** (old reel too). Fixed.
  - **Cause:** `motion_timeline.caption_words` attached every word with no
    letters to the word before it.
  - Now only closing punctuation joins the previous word, and a code symbol
    is a word of its own.
  - **A second bug in the same captions:** the spoken "brackets" had no shown
    word, so every later word in that caption took the time of the spoken
    word before it ("on" lit on "brackets").
  - **Fix:** a symbol now takes the spoken word that names it
    (`motion_voice._names_symbol`). On the real reel, `[ ]` lights on
    "brackets" (46.77 s) and "on" on "on" (47.21 s).
  - **Checked:** every shown word of every golden fixture now lines up with
    its speech (2,166 words, 0 mismatches). The old code had 2 on this reel.
- **Job record:** the stale "timing checks did not pass" message is cleared,
  with a history entry saying the timing stage was rerun locally. The job
  page now shows no warning.
- **mp4s:** `docs/reference/**/*.mp4` is in `.gitignore`.

## Tests

- `SHORTS_STUB=1 python -m shorts.motion_step1_fixes_test`: 12 tests. It
  replays the real CTA failure on the reel's recorded word times.
- `SHORTS_STUB=1 python -m shorts.motion_caption_glue_test`: 3 tests
  (symbol words, spoken-word mapping, the fixture-wide alignment scan).
- A full stub reel run into a temp folder passes every grader, at $0.

## Files

- **New:**
  - `shorts/motion_tidy.py`
  - `shorts/motion_plan_checks.py`
  - `shorts/motion_sweep.py`
  - `shorts/motion_step1_fixes_test.py`
  - `web/src/motion/objects/annotated.tsx`
  - fixtures: `evals/fixtures/motion/variable_points_to_value_*`
- **Changed:**
  - `motion_reel.stage_timing`
  - `motion_scenes` (cadence repair, change events)
  - `checks` (payoff check knows about a dropped payoff)
  - `schema` (`MotionPlan.rev`)
  - `motion_timeline` (`PLAN_REV`)
  - `skills/scenes.py` prompt
  - `library.json` (bubble zone, end-card actions, slot length)
  - `MotionStage.tsx`, `Identity.tsx`, `scene/objects.tsx`, `reference.tsx`,
    `action.tsx`, `overlap.ts`, `types.ts`
