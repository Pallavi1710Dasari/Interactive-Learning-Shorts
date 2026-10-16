# Motion reels v4: Midnight Lab, one feed, no overlaps (2026-10-13)

Everything ran in stub mode, and no paid call was made. Nothing is committed.

- **Your real `output/` folder was read, never written.** I checked: no file
  in it changed during this work.
- **The new demo reel was made in a scratch copy:** your real reels linked
  read-only, plus a new stub reel.

## Which server for which URL

| Stack | Start it with | What it shows |
|---|---|---|
| **Real**: http://localhost:5173 | `python -m shorts.server` (port 8000, your real `output/`) and `cd web && npm run dev` | your ~70 old reels and your real motion reel |
| **Stub demo**: http://localhost:5175 | `SHORTS_STUB=1 SHORTS_OUTPUT_DIR=<copy of output/> python -m shorts.server --port 8001` and `cd web && SHORTS_API=http://127.0.0.1:8001 npx vite --port 5175` | the same reels **plus a new stub reel on top, in Midnight Lab** |

Both stacks are running now. I started the real server with `SHORTS_STUB=1`
as a safety net; that only blocks paid calls. The feed, the reels and the
voice are read from disk exactly as without it.

`web/vite.config.ts` gained an optional `SHORTS_API` variable for the
second dev server. Without it, nothing changes.

## What to open

| URL | Server | What to check |
|---|---|---|
| http://localhost:5173/#reels | real | **Your feed.** 71 reels: your real motion reel `plain_variable_no_rerender__motion` first, then your 70 old reels, newest first. The motion reel plays by itself with its voice. Scroll for the old ones. |
| http://localhost:5175/#reels | stub demo | **The same feed with a new stub reel on top**, in Midnight Lab, labelled **Stub: no voice**. Your real motion reel is second, then the old reels. |
| http://localhost:5175/ | stub demo | **The upload screen:** no "What kind of reel?" choice any more. |
| http://localhost:5173/#motion-gallery/directions | either | The design directions page (B is the one now applied). |
| http://localhost:5173/#motion-reel?src=/motion-audit/lab_duo_characters.json | either | Every scene type in Midnight Lab, two speakers with characters. Swap in `lab_solo`, `lab_narrator`, `lab_duo`, or the classic `solo`, `narrator`, `duo`, `duo_characters`. |
| http://localhost:5173/#motion-reel?src=/motion-audit/lab_real_preview.json | either | **A preview only:** your real reel's content drawn in Midnight Lab. Your reel itself stays classic. |

## Screenshots (this folder)

| File | Screen |
|---|---|
| `01_real_feed_top.png` | Real server: your motion reel first, playing, rail with cost **$1.57 · 110.7k tok** |
| `01_real_feed_second.png`, `01_real_feed_third.png` | Real server: your old reels, unchanged |
| `10_upload_motion_only.png` | The upload screen, motion only |
| `11_done_watch_your_reel.png` | A stub reel made through the UI, finished |
| `20_demo_feed_top.png` | Stub demo: the new Midnight Lab reel on top, **Stub: no voice**, $0.00 |
| `20_demo_feed_second.png`, `20_demo_feed_third.png` | Stub demo: your real motion reel second, then your old reels |
| `30_stub_reel_midnight_lab.png` | Every shot of that stub reel in Midnight Lab |
| `40_lab_solo.png`, `40_lab_duo_characters.png` | Every scene type in Midnight Lab: one narrator, and two speakers with characters |
| `40_lab_real_preview.png` | Your real reel's content in Midnight Lab (preview only) |
| `40_duo_characters.png` | The classic design after the overlap fixes |

## 1. Existing reels and tokens

**What the real server lists.** I checked with the real server on the real
`output/` folder.
- **Old reels:** all **70** are in the feed (`GET /api/shorts`, and 70 cards
  in the browser).
- **8 held reels** are kept out on purpose, as before: the judge scored them
  under the bar. They are `address_translation_mechanism`,
  `font_family_property`, `html_document_structure`,
  `reading_crows_foot_symbols`, `representing_information_in_binary`,
  `system_call_definition`, `tls_handshake_definition` and
  `what_is_a_computer_network`. Say if you want them shown.
- **35 archived reels** in `output/archive/` were never in the feed. I left
  them there.
- **Nothing failed to load.** Every file the feed skips is a story, mapping
  or motion file, or a sidecar, not a broken reel.
- **One motion reel is not in the feed:** `what_state_means__motion`. It was
  a paid run that stopped before its timing step, so it has no plan to play.

**What was wrong: the order.** The motion reel arrived a moment after the
old reels and went on top. The feed stayed snapped to the old first reel,
so it opened on reel 2.
- **Fix:** the feed now waits for both lists. It opens on the newest reel.
  New motion reels are newest, so they come first.

**Cost and tokens.** Every card's rail ends with a cost cell.
- **Motion reels** show what they cost and their tokens, from their own cost
  log. Your real reel shows **$1.57 · 110.7k tok**.
- **Old reels show "—".** Their cost was never recorded one by one: the
  usage log has no reel id. The `$` button in the top bar still shows the
  total spend for everything, as the old feed did.

## 2. Motion reels look and open like the old reels

**In the feed**, a motion reel is now drawn and played like an old reel:
- **Plays inline:** it plays by itself when it is the reel on screen, and
  clicking pauses it.
- **Same controls:** the same round ▶ / ↻ button, and the same keys (space,
  ←/→ shot, r replay).
- **Same rail:** the same speaker avatar and the same icons: unclear, mp4,
  redraw, replay, sound.
- **Rail placement:** the rail has its own dark column beside the frame, so
  it never covers the reel's captions or objects.
- **Not available yet:** mp4 and redraw are greyed out for motion reels.
  There is no motion MP4 export yet, and redraw is an explainer action.

**No separate page.** The "Watch" buttons in the motion steps now open the
feed at that reel (`#reels/<id>`), not the separate player page.

## 3. Voice and overlapping text

**Voice: your real reel plays its voice in the feed.** I measured it in the
browser on the real server:
- **The audio:** the reel's `<audio>` is `/api/motion/plain_variable_no_rerender__motion/audio`
  (93.5 s). It is not muted, volume is 1, and it is playing: its time went
  from 4.1 s to 8.4 s over the check.
- **Stub reels:** they show a yellow **Stub: no voice** tag on the reel and
  **STUB** in the rail.

**Overlapping text.** A new check, `web/src/motion/overlap.ts`, finds:
- text touching text from another part of the frame (caption, label, badge,
  chat row, scene object);
- text on another part's card;
- text under a character;
- text off the frame.

**Fixed:**
- **Stamp covering the value.** In your real reel, s05's "THROWN AWAY" stamp
  covered the card's "count". A long stamp is now set smaller and kept in
  the card's right side.
- **Code map into the captions.** In your real reel, s08's code map had 3
  part rows, and the third ran into the caption. Three rows now move the
  code up and shorten the rows.
- **Unreadable highlight.** The code map's amber highlight made "let"
  unreadable; code under it is now ink.
- **Stray backticks.** Captions and chat bubbles no longer show
  `` `backticks` ``.
- **Rail over captions.** In the feed, the rail used to sit over the reel's
  captions (see section 2).

**Swept** every shot (after it settles, middle, end) and every caption:

| Plan | Moments | Overlaps |
|---|---|---|
| Your real reel (classic) | 60 | 0 |
| Your real reel in Midnight Lab (preview) | 60 | 0 |
| The new stub reel (Midnight Lab) | 52 | 0 |
| 8 audit contexts: 4 classic + 4 Midnight Lab, every scene type, solo / narrator / duo / duo with characters | 496 | 0 |

## 4. The upload screen

- **The choice is gone:** "What kind of reel?" was removed, and an upload
  always makes a motion reel.
- **The top bar** now shows **Upload · Reels**.
- **Old reels and the old pipeline:** old reels still play in the feed. The
  old pipeline is CLI-only (`python -m shorts.run …`).

## 5. Clear explanations and non-recommended choices

**Simple language.** The reading-level check (about grade 7) and the
terms-explained check run in the script step's checks. Every run below
passed both, shown in its script review.

**Non-recommended choices.** `shorts/motion_choices_test.py` runs the UI's
motion runner from upload to a playable plan with picks the AI did not
recommend. For each run it checks:
- every pick is used in every later step;
- the finished plan matches the picks;
- the reel is in Midnight Lab.

| Run | Material | Topic | Teaching approach | Template | Theme | Speakers | Characters | Result |
|---|---|---|---|---|---|---|---|---|
| A | React useState | **other** | **other** (analogy) | **other** (walkthrough) | step_by_step_walkthrough (walkthrough's only theme) | 1 | **off** | 13 shots, 62.6 s ✓ |
| B | React useState | recommended | **other** (analogy) | recommended (fix_story) | **interview** (two-speaker) | 2 | on, preset **riya** | host + riya, 75.4 s ✓ |
| C | Dynamic web apps | recommended | **other** (analogy) | recommended (fix_story) | **interview** (two-speaker) | 2 | **off** | 61.3 s ✓ |
| D | Dynamic web apps | **other** | **other** (analogy) | **other** (walkthrough) | step_by_step_walkthrough | 1 | on, preset **arjun** | 61.5 s ✓ |
| E | React useState | recommended | recommended | **other** (walkthrough) | recommended | 1 | on (default) | 65.3 s ✓ |
| F | React useState | recommended | **other** (analogy) | recommended (fix_story) | **narrative** (another one-narrator theme) | 1 | on (default) | 59.3 s ✓ |

Run it with `SHORTS_STUB=1 python -m shorts.motion_choices_test`. It is free.

**Also fixed:** stub topics used to read "How does what Is React? work?".
A title that already asks a question is now kept as one: "What is React?".

## Midnight Lab: how it is applied and switched

- **New reels only.** A reel's design is chosen when it is set up and
  saved in its `setup.json`, then copied into its plan.
  - New reels get `midnight_lab`.
  - Reels set up before have none saved and stay **classic**. That includes
    your real reel, even if its timing step is rerun.
- **Switchable.**
  - **The registry:** designs are listed in `web/src/motion/designs.ts`
    and in `config.MOTION_DESIGNS`.
  - **One reel:** `python -m shorts.motion_reel <doc> --design classic`
    picks the design for that reel.
  - **All new reels:** `MOTION_DESIGN=classic` sets the default.
  - **Another style later** is one more entry in each registry.
- **What it changes:**
  - night-blue background with a glowing grid floor;
  - glass cards with lit edges;
  - heavy Manrope in sentence case, with key words in glowing cyan;
  - `// LABEL` section labels;
  - a 3D tilt that settles at the start of each shot;
  - zoom-through transitions.
- **What it does not change:** where things go. The layout boxes are the
  same, so both designs pass the same checks.
- **Kinetic titles** now keep the writer's own case ("useState"). Classic
  still draws them in capitals; Midnight Lab draws them in sentence case.

## Tests

- **New test files:**
  - `shorts/motion_choices_test.py`: the six runs above. Their results are
    in `choices_runs.json`.
  - `web/src/motion/overlap.ts`: the overlap check. Its sweep results are in
    `overlaps_real_and_audit.json` and `overlaps_stub_reel.json`.
- **Changed tests:**
  - `motion_scenes_fix_test`: the default hook title is now in the writer's
    case.
  - `motion.test.tsx`: the role-label check counts the design fields from
    the list instead of assuming 4.
- **Full run results:**
  - All **59** `shorts/*_test.py` modules pass.
  - Evals: **212 passed, 0 failed, 12 skipped** (the paid judge cases).
  - `tsc --noEmit` is clean, and `npm run test:motion` passes.

**Not done, or worth knowing:**
- **Before pictures:** the machine restarted during this round and cleared
  `/tmp`. The before pictures of the stamp and code-map overlaps were lost,
  so this folder has after pictures and the sweep results only.
- **mp4 for motion reels:** no export exists yet, so the button is greyed
  out.
- **Old reels' cost:** it can't be shown per reel, because it was never
  recorded per reel.
- **Pacing:** your real reel still has the old pacing. Re-timing it is free
  (local), but it overwrites its plan and mix, so I left it for you:
  `python -m shorts.motion_reel content/react_usestate_basics.md --topic plain_variable_no_rerender__motion --force-stage timing`.
  It stays in the classic design.
