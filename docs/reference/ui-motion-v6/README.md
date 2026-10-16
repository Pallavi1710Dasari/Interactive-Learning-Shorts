# Motion reels v6: step 6 fixed, Characters step, change any step, faster (2026-10-13)

Everything below ran in stub (test) mode. Nothing is committed, and your real
`output/` folder was only read.

## First: restart your server

The server running on port 8000 (real mode) was started before these
changes, so it still runs the old code, while the page now expects the new
code. Stop it and start it again:

```
python -m shorts.server
```

Until then, the new Characters step and the step 6 fixes will not work on
http://localhost:5173.

## 1. Why step 6 failed, and the fix

Your reel *variable_points_to_value__motion* had its script written three
times, costing $0.33, and every attempt was rejected. Most of the reasons
were our checks being too strict, not real problems:

| Attempt | Rejected for | Real problem? |
|---|---|---|
| 1 | a caption shows code `["milk", …]`, which is said aloud as "a list with milk" | **No.** A check bug, now fixed. |
| 2 | the channel name `@learnthesimpleway` counted as a "hard word" | **No.** A check bug, now fixed. |
| 3 | the title "A variable is a name tied to a box." is 9 words, and the limit was 8; `[ ]` is said aloud as "brackets" | **No.** The title limit is now 9 words (3.6 s), and code written with brackets or quotes may be said in other words. |

**The checks still catch real mismatches.** A caption showing `0` while the
narration says "one" still fails.

**All 3 of your saved attempts pass now.** Step 6 has a new button,
**"Check the saved attempts again (free)"**. It re-checks the scripts
already written without calling the AI. When a step fails, it now also lists
the exact reasons.

**To rescue your reel:**
1. Restart the server.
2. Open http://localhost:5173/#motion/job/f64077e78448.
3. Confirm the Characters step.
4. On step 6, press **Check the saved attempts again (free)**.

## 2. The steps (screens 02–09)

**Upload → Topic → Teaching approach → Language → Theme → Characters → Script → Your reel**

- **No duplicate button:** the **Reels** button at the top left is gone;
  **existing reels** at the top right opens the feed.
- **"Your choices" panel:** a panel beside the steps shows what you picked
  at each step, with a **Change** link. Change reopens that step exactly as
  you saw it, with no new AI call (screen 08). Every step after it is
  decided again from there.
- **When choices lock:** after you approve the script and the reel starts
  being made, the choices are locked.
- **Earlier requests, all included:**
  - one step at a time;
  - scenes hidden;
  - the template is picked by the theme;
  - a cost on every paid button;
  - Language before Theme, because the theme step needs the language.

## 3. The Characters step: avatars and voices (screen 06)

- **Speaker count:** the theme decides how many speakers the reel has.
- **Two speakers** (interview, mentor and student, peer discussion) get
  **two avatars and two voices**. One narrator gets one of each.
- **Recommendations:** for each speaker, the language's own character and a
  voice are marked "recommended". You can pick another avatar (faces shown,
  "More avatars" for all of them) or the other voice (▶ plays it). You can
  also turn the avatars off.
- **Two speakers can never share a voice.**
- **Your picks are used** when the reel is recorded and drawn. A test reel
  made this way had two speakers with the host and React avatars, recorded
  in Voice 1 and Voice 2.
- **The voices** are your two recordings in `voices/` (interviewer and
  student). Add more as `voices/motion/<name>.wav`; they appear in the list
  automatically.
- **The recommendation is rule-based:** the speakers come from the AI's
  theme choice; the avatar is the language's own, and the voices are
  different by default. It needs no extra AI call, so it adds no cost or
  waiting.

## 4. Speed

- **The voice starts early.** It is now recorded while the AI draws the
  scenes, as soon as you approve the script, because it only needs the
  script. That removes about a minute of waiting at the end.
- **Fewer rewrites.** Fixing the over-strict checks means far fewer
  rewrites. A failed attempt cost about 40 seconds and $0.11 each time.
- **No parallel voice recording.** I tested two voice recorders in
  parallel, and it was much slower: each one already uses every CPU core.
  The voice is about 9–19 seconds per line on this computer. The real
  speed-up for the voice would be a GPU.

## Checks

- All 59 Python test modules pass, including a new test: two speakers, other
  avatars, swapped voices, one voice for both refused, Change back to the
  theme with no new AI call, and the picks reaching the finished reel.
- Evals: 212 passed, 0 failed, 12 skipped (the paid judge cases).
- TypeScript is clean, and the motion checks pass.
- A full click-through in the browser worked: two speakers, then Change back
  to the theme, then on to a finished reel.

## Update: second round (same day)

- **The step 7 error you saw** was your job's old result, saved before the
  fix. Now, when a failed script is opened again, it is re-checked for free
  automatically. Confirming the Characters step re-checks it too. Your job's
  script passes now.
- **Avatar advice from the AI.** The theme step's AI call (no extra call)
  now also says whether avatars help this reel, with a one-sentence reason.
  The Characters step shows it as the recommended choice: "Show two avatars"
  or "No avatars", plus the reason (screen 06).
- **Voice samples** play and pause: ▶ / ❚❚ on the same button. Starting
  another voice stops the one playing.
- **"Record or change a voice…"** in the Characters step opens the voice
  studio (the **your voice** button at the top). When you close it, the
  Characters step lists the voices again. A voice you record or keep there
  shows up immediately and is used for the next reels you make: each voice
  is re-recorded when its clip changes. Reels that are already made keep
  the voice they were recorded with.
- **The side panel is redesigned** as "Your reel so far": every step with
  ✓ and its choice, the current step highlighted, a **Change** button on
  each finished step, and a 🔒 note once the reel is being made.
- **Restart the server again** for these changes:
  `python -m shorts.server` (port 8000).
- **Checks:** all 59 test modules pass; evals 212 passed, 0 failed; TypeScript
  is clean; the motion checks pass.
