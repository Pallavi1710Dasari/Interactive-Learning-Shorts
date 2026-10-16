# Motion reels from the web UI (2026-10-12)

Uploading reading material in the web UI now makes a **motion** reel by
default. Every pause the CLI (`python -m shorts.motion_reel`) makes is a
review screen. The old explainer is still there as an option, and existing
explainer, story and motion reels open as before.

All screenshots here come from **one stub run through the real UI**: headless
Chrome clicked the buttons. Nothing was spent. The run used a demo output
folder, so the real `output/` was never written. That folder holds copies of
four existing reels, so you can see they still open.

## What to open

The stub demo server is running on the demo folder:

| URL | What to check |
|---|---|
| http://localhost:5173/ | Upload screen: **Motion (default)** is selected, Explainer (old) is the other option |
| http://localhost:5173/#motion/job/697acf451439 | The finished stub run: done screen with the player |
| http://localhost:5173/#motion-reel/stub_how_a_state_update_triggers_a_re_render__motion | The new reel in the full player |
| http://localhost:5173/#motion | Motion list: the new reel, plus **In progress** with a resumable job |
| http://localhost:5173/#motion/job/ed530b244c61 | A reel the CLI started (`what_state_means__motion`), resumed in the UI at its scenes pre-flight |
| http://localhost:5173/#reels | The existing explainer reel, still in the old feed |

To go through it yourself, open http://localhost:5173/, choose a `.md` file
(for example `content/react_usestate_basics.md`) and click **Set up the
motion reel**. The server is in stub mode, so nothing is spent.

To run on the real `output/` again, restart the server without the demo
folder: `python -m shorts.server` (add `SHORTS_STUB=1` to stay free).

## The flow, screen by screen

| # | Screen | File |
|---|---|---|
| 1 | Upload: Motion is the default, Explainer (old) is an option | `01_upload_motion_default.png`, `01b_upload_explainer_option.png` |
| 2 | **Options + whole-reel estimate**: section, language, theme, template, characters (**on**), character preset; typical $0.66, at most $1.81, cap $2.00. **Start** is the one confirmation | `02_options_and_estimate.png` |
| 3 | **Topic**: approve / regenerate (a reason is required) / skip | `03_topic.png`, `03b_topic_regenerate_reason.png`, `03c_topic_after_regenerate.png` |
| 4 | **Teaching approach**: approve / regenerate / skip | `04_teaching_approach.png` |
| 5 | **Template**: suggested from the approach; your choice **locks** it | `05_template.png` |
| 6 | **Theme pre-flight**: the fit call's cost before it is spent | `06_theme_preflight.png` |
| 7 | **Theme**: reason, format, speakers, language, tags and tag checks; approve / choose another / regenerate / skip. The template shows as locked; walkthrough themes are not offered | `07_theme.png` |
| 8 | **Shot list pre-flight** | `08_script_preflight.png` |
| 9 | **Shot list**: every shot's speech, captions, code and visual; the invented-example warning; check results (19 of 19); fact sources | `09_shot_list.png` |
| 9b | **Skip** leaves it pending and stops; **Resume** shows the same shot list again with no new call | `09b_shot_list_skipped_stopped.png`, `09c_shot_list_after_resume_no_cost.png` |
| 10 | **Scenes pre-flight** | `10_scenes_preflight.png` |
| 11 | **Scenes**: every shot's field, transition, objects and cued actions; scene checks | `11_scenes.png` |
| 12 | **Voice and timing on the server, with progress**: "clip 4 of 19", "clip aligned 4 of 19" | `12_voice_progress_clip_x_of_n.png`, `12_timing_progress_clip_x_of_n.png` |
| 13 | **Done**: links to the full player, the reel page, and the Motion list | `13_done_with_player.png` |
| 14 | The full player at shot s04, with the React character as narrator | `14_full_player.png` |
| 15 | The new reel in the Motion list and on its reel page | `15_motion_list_with_new_reel.png`, `15b_new_reel_page.png` |
| 16–17 | **Existing reels unchanged**: a real motion reel's page, and the explainer feed | `16_existing_real_motion_reel_opens.png`, `17_existing_explainer_and_story_reels_open.png` |
| 18–19 | **Resume a CLI reel**: **Resume in the UI** on the Motion list; it starts at the stage its files reached (scenes), with its earlier $0.41 counted against the cap | `18_cli_reel_adopted_stopped.png`, `19_cli_reel_resumed_at_scenes_preflight.png` |
| 20–21 | **Cap reached**: with a $0.50 cap, the shot list's $1.06 worst case is refused before any call; Stop leaves it resumable | `20_cap_reached_before_spending.png`, `21_stopped_at_cap_resumable.png` |
| 22 | **Explainer (old)** still goes to its own Approve step | `22_explainer_option_still_works_approve_step.png` |

The running cost bar ("This reel has spent $x of the $2.00 cap") is on every
job screen. In stub mode every call costs $0, so it stays at $0.0000. Screen
19 shows it with a real reel's earlier spend.

## How it works

- `shorts/motion_jobs.py` runs the CLI's stages for the UI. A job is saved to
  `output/_motion_jobs/<id>.json`, so a closed tab, an error, a cap stop or a
  server restart can all be resumed.
- Every artifact is written by the same `shorts/motion_reel.py` helpers the
  CLI uses, and only on approval. The CLI's stages were split into "compute"
  and "save on approval" for this. The CLI's output is unchanged: a stub CLI
  run writes the same plan as before.
- **Skip** means what it means in the CLI: leave it pending and stop.
- **Pre-flight**: theme, shot list and scenes stop before they spend, and
  refuse to start if the reel's spend plus this stage's worst case would pass
  `MAX_REEL_USD`. The reel's spend includes earlier runs (CLI or UI).
- **Resume** never pays for an approved stage. A review that was still
  pending shows again as it was. Rejected scripts saved by the CLI or the UI
  are reused when they now pass the checks.
- Characters are on by default in the UI: one per speaker (one narrator, or
  two on a two-speaker reel).

## Things to know

- **The voice and timing progress screenshots (12)** were taken with a test
  wrapper that pauses briefly per clip, because stub voice finishes in
  milliseconds. Product code is unchanged; with real Chatterbox each clip
  takes seconds, so the progress is visible on its own.
- **The cap screenshots (20–21)** were taken on a server started with
  `MAX_REEL_USD=0.50`. The default cap is $2.00.
- **The topic wording** ("How does how a state update…", and the reason
  text appended after a regeneration) is the stub's canned text, not the UI.
- One UI action runs at a time across the server (usage tracking and model
  routing are process-wide).

## Tests

- `SHORTS_STUB=1 python -m shorts.motion_jobs_test`: 11 tests. They cover a
  whole reel from upload to plan, every gate, skip + resume with no new
  call (counted at the stub), cap stop, a closed tab, reuse of rejected
  scripts, resuming a CLI reel, clip progress, and the HTTP routes.
- All 57 `shorts/*_test.py` modules pass. Evals: 212 passed, 0 failed,
  12 skipped (the paid judge cases). `tsc --noEmit` is clean.
  `npm run test:motion` passes.
