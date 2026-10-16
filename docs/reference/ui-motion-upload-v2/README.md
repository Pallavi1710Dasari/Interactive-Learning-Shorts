# Motion upload UI, v2 (2026-10-12)

All 32 screenshots here were taken by clicking through the real UI in
headless Chrome, in stub mode. Nothing was spent and the real `output/` was
never written: the demo server uses a scratch output folder that holds copies
of four existing reels.

## What to open

The stub demo server is running.

| URL | What you'll find |
|---|---|
| http://localhost:5173/ | **Start here.** Upload a file (try `evals/fixtures/motion/dynamic_web_app_material.md`, your own material) and click through every step yourself. It's free in stub mode. |
| http://localhost:5173/#motion/job/e7613c89bcdb | The complete stub run (your material, mentor_student theme): done, with the player |
| http://localhost:5173/#motion/job/bf1b8796c865 | **A reel stopped by an error, left for you.** Press **Retry this step** and it recovers |
| http://localhost:5173/#motion/job/e269ff0523b4 | The error run after its recovery: waiting at the script review |
| http://localhost:5173/#motion | Motion reels list: the new reels, plus **In progress** with the unfinished ones |
| http://localhost:5173/#reels | Older reels: the explainer feed, unchanged |

## 1. The error at the shot list

**Cause.** The stopped run was your own upload ("What is a dynamic web
application?") with the `mentor_student` theme. Stub mode answered the
script call only from hand-written sample scripts (`evals/fixtures/motion/*_golden.json`),
and none is about this material in this theme. So the stub raised
`NotImplementedError: no fix_story motion stub fixture teaches this material as mentor_student`,
which `output/_motion_jobs/fd72b8247fc7.json` recorded. Your material
and the pipeline were fine; the stub had nothing to answer with.

**Fix.** `shorts/stub_motion.py` writes a stub script from any material,
in any template and theme. The concept is the section's most-used code name or
bold term, the code map uses the section's own code, a few of its short plain
sentences carry the explanation, and two-speaker themes get their speakers in
the order each beat requires. It passes the same 19 checks as a real script.
The sample scripts still win when one fits. I checked every section of 8
documents against all 14 themes: **560 of 560 pass**.

A second stub bug turned up along the way. A sample script was reused for a
section that never states its numbers ("stuck at zero" in a section without 0),
so the check failed. Sample scripts now give way to the generated one in that
case.

**Tests.**
- `test_a_stub_run_on_any_upload_reaches_the_player` in
  `shorts/motion_jobs_test.py` is the regression test. It uses your document
  and the same options; it failed exactly as reported before the fix.
- `test_stub_writes_the_template_asked_for_when_no_golden_fits` in
  `shorts/motion_script_test.py` replaces the old test that expected the stub
  to raise.

**Errors in plain words.** Every problem screen says what happened, whether
anything was lost or charged, and what to do next. It has one clear button
(**Retry this step**, **Run this step again**, **OK, stop here**), and the
technical details sit behind **Show details**. AI-service failures (busy, bad
key, spending limit, no connection, timeout) each get their own wording. A
server restart mid-step is reported the same way. Screens 30–35.

## 2. The old approach is gone from upload

- **Upload:** the home page is now the motion upload; there is no style choice
  any more.
- **Removed:** the explainer's upload, approve, teaching-approach, review and
  build screens (`StepMaterial`, `StepApprove`, `StepTeachingApproach`,
  `StepReview`, `StepBuild`) are deleted. The explainer pipeline runs from the
  command line only (`python -m shorts.run`).
- **Older reels:** explainer reels still play in their feed at `#reels`
  (screen 22).
- **Story reels:** there was never a list of story reels in the UI. They open
  at `#capture/<short_id>` (for example `#capture/why_plain_variable_fails__story`),
  which is unchanged.

## 3. Obvious steps

- **Step bar:** on every screen: Upload → Topic → Teaching approach → Template
  → Theme → Script → Scenes → Voice & timing → Done. Finished steps are green
  with a check, the current step is yellow, and the steps still to come are
  grey.
- **Step headings:** each step opens with "Step N of 8", a plain heading, why
  the step matters, and what to do.
- **While working:** the screen says what is happening in plain words, with
  which model and how long it usually takes, and shows a moving bar and the
  seconds so far. In real mode that reads "Writing the script with Claude Opus
  5.5… Usually takes about 2 minutes"; in stub mode it says "the stub (free,
  instant)". Voice and timing count lines ("Line 12 of 19"). Screens 40–42.

## 4. The AI recommends, you decide

At every step the AI's choice comes first, marked **Recommended** with a
one-line **Why**. Every alternative follows, each with a short description.
You can pick another or ask the AI again, and your pick is the one used later:

| Step | Recommended | You can |
|---|---|---|
| Section | let the AI pick from all sections | pick one section here, or "Look in a different section" at the topic |
| Topic | the strongest question (3 come from the same one call) | pick one of the others, or reword it |
| Language | detected from the material's code | pick any language |
| Characters | on, one per speaker | turn them off |
| Character preset | the language's own character | pick any preset |
| Teaching approach | the AI's choice and rationale | pick any of the 7, or ask it to reconsider |
| Template | follows the approach | pick the other; it locks the theme and script |
| Theme | the AI's fit pick | pick any theme that fits the locked template, or ask again |

Tests prove each pick carries forward: topic → approach → template →
theme → script.

## 5. Clean, large, calm

- **Look:** one stylesheet (`web/src/motion/studio/studio.css`) with one type
  scale, one spacing scale and one set of colours. Body text is 17 px, the main
  button is large and yellow, and it's built for a laptop screen. It's scoped,
  so the feed and the player are untouched.
- **Upload:** starts with just the file drop. The recommendations then appear
  as four short cards, each with a **Change** button.
- **Cost:** shown as "This step: up to $X · This reel so far: $Y · Limit per
  reel: $2.00", with a thin bar.
- **Design guidance:** there is no "frontend-design" guide in this project or
  in my available skills, so I followed standard practice (consistent tokens,
  large targets, clear hierarchy, plain language) rather than a named guide.

## Also fixed

**Double clicks.** Two clicks on the same step at the same moment could
both act, because the server answers on several threads. Clicks on one reel
now run one at a time, and a click made on a screen the reel has already left
is refused with a plain message. `test_a_double_click_is_applied_once`
covers it; without the fix it fails with `[200, 200]`.

## Screens

| File | Screen |
|---|---|
| 01–02 | Upload: empty, then a file chosen |
| 03–05 | Recommended setup; Change open for language and for character |
| 06–08 | Topic: recommended and alternatives, reword, look in a different section |
| 09–10 | Teaching approach: recommended, then a different pick |
| 11 | Template |
| 12–14 | Theme: before starting, recommended, changed to Mentor & student |
| 15–16 | Script: before starting, the review (19 of 19 checks) |
| 17–18 | Scenes: before starting, the review |
| 19–20 | Done with the player; full player with both characters |
| 21–22 | Motion reels list; older reels feed |
| 30–31 | An error in plain words; Show details open |
| 32–33 | After Retry; recovered, script ready |
| 34 | Paused ("Stop here for now"), with Resume |
| 35 | Cost limit reached before spending (a server started with a $0.50 limit) |
| 40–41 | Working: choosing the topic, writing the script |
| 42 | Voice & timing: "Line X of N" |

**How the harness screens were taken.**
- **Error (30–33):** taken on a test server that fails the script step once,
  with an error named like the AI service's rate-limit error.
- **Working (40–42):** taken on a test server that slows the stub so the
  screen stays up long enough to photograph.

Both are scratchpad test wrappers. No product code changed for them.
