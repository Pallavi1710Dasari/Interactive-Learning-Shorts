# Motion reels in the original workspace, v3 (2026-10-12)

One UI, the original design. New reels are motion reels by default, and their
eight steps live in the same workspace, cards and sticky bar as the explainer
screens. Motion reels show up in the same reels feed.

All screenshots were taken by clicking through the real UI in headless Chrome,
in stub mode. The demo server uses a scratch output folder holding copies of
your existing reels; the real `output/` was not touched.

## What to open

| URL | What you'll find |
|---|---|
| http://localhost:5173/ | **Start here.** The original upload screen, with "Motion reel" selected. Upload a file (for example `evals/fixtures/motion/dynamic_web_app_material.md`) and click through to "Watch your reel". Free in stub mode. |
| http://localhost:5173/#reels | **The reels feed:** newest first. The stub motion reel from the complete run is first, then an explainer reel, then your real motion reel `plain_variable_no_rerender__motion`, then the older explainer. |
| http://localhost:5173/#motion/job/21091283e1f9 | The complete stub run (Mentor & student), finished, with "Watch your reel" |
| http://localhost:5173/#motion/job/baa188e537b5 | **A reel stopped by an error, left for you.** Press "Retry this step" in the sticky bar and it recovers |
| http://localhost:5173/#motion-reel/plain_variable_no_rerender__motion | Your real reel in the motion player, with its voice, Mute and Volume |

## 1. The old screens are back

- **Restored:** `StepMaterial`, `StepApprove`, `StepTeachingApproach`,
  `StepReview`, `StepBuild`, `App.tsx` and `api.ts` were restored from git.
  Before I changed anything, their content matched `HEAD` exactly.
- **Works end to end:** screens 50–55 run the explainer flow end to end:
  upload → approve → teaching approach → review narration → build → the reel
  in the feed.
- **What changed on those screens:** the upload screen gained the "What kind
  of reel?" choice (screen 50; Motion is the default). The explainer screens
  that follow are unchanged.

## 2. Motion steps in the old design

- **One screen:** the upload screen's **Make a motion reel →** opens the motion
  steps on one screen. Finished steps stay visible with what was chosen. The
  current step is open ("your turn", "working", "needs a retry" or "paused"),
  and the steps still to come are listed below it.
- **Step progress:** the top bar's crumbs become the motion steps: Upload ·
  Topic · Teaching approach · Template · Theme · Script · Scenes · Voice &
  timing · Done. Done steps have a check, the current step is highlighted, and
  later steps are dimmed. The heading says "Step N of 8: …".
- **Recommended choices:** at every choice (section, language, characters,
  character preset, topic, teaching approach, template, theme), the AI's pick
  comes first, marked "recommended" with a **Why**. Every alternative follows
  with a description. You can pick another, or regenerate, and your pick is
  used in every later step.
- **Sticky bar:** it always shows the reel's cost so far and the $2.00 limit
  per reel, plus the one big next action ("Start", "Continue with this topic
  →", "Write the script", "Approve the script →", "▶ Watch your reel").
  "Stop here for now" pauses.
- **Working:** while it works, the card says what is happening in plain words
  and shows a moving bar ("Recording every line … Line 5 of 17").
- **Problems:** they say what happened, whether anything was lost or charged,
  and what to do, with **Retry this step**; the details are behind "Show
  details".
- **One UI:** the separate v2 studio is gone.

## 3. One place for all reels

- **The feed (`#reels`):** it holds explainer and motion reels together,
  newest first.
- **Motion reels:** each shows a frame from the reel, a **MOTION** badge (and
  **STUB REEL: NO VOICE** for stub reels), the question, and **▶ Watch**,
  which opens the motion player.
- **When a reel finishes:** the page shows **▶ Watch your reel** (at the top
  and in the sticky bar) and **See it in the reels feed**.

## 4. Easy to use

- **Path:** a first-time user goes upload → Start → Continue at each step →
  Watch your reel.
- **Buttons:** every next step is one large green button in the same place.
  Nothing needed for that path is hidden or small.

## 5. Voice

**Findings for `plain_variable_no_rerender__motion` (the real reel):**
- **Files:** its voice clips exist: 27 Chatterbox clips and a 93.5 s mix at
  normal loudness.
- **Playback:** the player loads it and plays it, not muted, volume 1. I
  measured it playing in both the full player and the reel page.
- **Why you heard nothing:** the reels with no sound are **stub reels**. Stub
  mode records silence on purpose, and every reel from my demo runs is a stub
  reel.

**Fixed:**
- **Volume and mute:** the motion player has a **Mute** button and a
  **Volume** slider. They're remembered between visits (screen 21).
- **Stub notice:** a stub reel says **"Stub reel: no voice … the sound is not
  broken"** in the player (screen 18) and in the feed (screen 19).
- **Blocked playback:** if the browser blocks playback, the player now says so
  instead of staying silent.

## Screens

| File | Screen |
|---|---|
| 01–02 | Upload: Motion by default, file chosen |
| 03 | Step 1: the recommended setup |
| 04–06 | Step 2: topic, reword, look in another section |
| 07–08 | Step 3: teaching approach, a different pick |
| 09 | Step 4: template |
| 10–12 | Step 5: theme, before starting, recommended, changed to Mentor & student |
| 13–14 | Step 6: script, before starting, the review |
| 15–16 | Step 7: scenes, before starting, the review |
| 17 | Done: "Watch your reel" with every step's choice |
| 18 | Player: stub reel, "no voice" |
| 19, 20, 20b | Reels feed: newest motion reel first, your real motion reel, an explainer reel |
| 21 | Player: your real reel playing, with Mute and Volume |
| 30–31 | An error in plain words with Retry; details open |
| 32–33 | Recovered after Retry; paused with Resume |
| 34 | Cost limit reached before spending (a server started with a $0.50 limit) |
| 40–42 | Working: choosing the topic, writing the script, voice and timing "Line X of N" |
| 50–55 | The explainer flow: upload choice, approve, teaching approach, review, building, its reel in the feed |

**How the harness screens were taken.**
- **Error (30–33):** a test server that fails the script step once.
- **Working (40–42):** a test server that slows the stub.

Both are scratchpad test wrappers; the product code is unchanged.

## Tests

- `shorts/motion_jobs_test.py` (23 tests) adds the per-step summary, the
  stub-voice flag and the feed's creation times.
- All 57 `shorts/*_test.py` modules pass. Evals: 212 passed, 0 failed,
  12 skipped (the paid judge cases). `tsc --noEmit` is clean.
  `npm run test:motion` passes.
