# Videos (16:9, 6–12 min) beside reels, and the 3D avatar as the reel default (2026-10-16)

## Update: fixes for a real video (same day, after the first review)

The first test video looked repetitive and its words were placeholders.
That's stub mode: no AI designs anything, every shot gets the mechanical
fallback scene, and the words are filler. Checking the real path before your
first real video found five problems. All are fixed:

| # | Problem | What would have happened | Fix |
|---|---|---|---|
| 1 | The video's script call asked for 24,000 output tokens. | The Anthropic SDK refuses a non-streaming request over about 21,300, so the **first real script call would have crashed** before sending anything. | 18,000 for a video's script; every request is now capped at 21,000 (`llm.MAX_NONSTREAMING_TOKENS`); a retry never shrinks the budget. |
| 2 | The variety check allows each object kind on at most 3 shots per reel. | A 55-shot video can't pass that with about 12 kinds, so the AI's real scenes would always fail, and **many shots would drop to the same fallback picture**: what you saw. | For a video, the cap holds within every 11 shots in a row (a reel's length). One stamp per chapter instead of one per video. |
| 3 | Each scenes batch wasn't told which shots are its own. | The AI could answer all 55 shots in one batch and run out of room. | Each batch is told "ONLY these shots", and what the shot before it shows, so it can vary from it. Other shots in an answer are ignored. Repairs go in batches too. |
| 4 | One bad caption meant a full rewrite. | About $0.36 per rewrite of the whole 6–12 minutes, and a rewrite can break another line. | **Targeted repair:** only the failing shots are rewritten (new call `motion_shot_fix`, about $0.13), up to 2 rounds after each attempt. A video gets 2 full attempts. |
| 5 | The video explained from the selected section only. | Thin notes can't fill 6 minutes, so the script fails "too short". | A video's material is its section and its numbered session, or, with no numbered sessions, the rest of the document. |

Also, the fallback scenes (used only when the AI's scene for a shot still
fails after repairs) now vary within each chapter: chips, a flow, a card
whose value changes, a memory box.

Checks after these fixes: 68 of 68 test modules pass (`motion_video_test` now
has 9 tests); evals 212 passed, 0 failed, 12 skipped; TypeScript is clean; the
motion checks pass.

Everything here ran in **stub mode** at **$0**. Nothing is committed. Your real
`output/` folder was only read.

## First: restart your server

Your server on port 8000 was started before these changes:

```
python -m shorts.server
```

Then open http://localhost:5173.

## 1. Reel or video: the first choice (screen 01)

The upload screen now starts with **What do you want to make?**

| | Reel | Video |
|---|---|---|
| Shape | vertical 9:16, 1080×1920 | landscape 16:9, 1920×1080 |
| Length | 40 s – 2 min | **6 – 12 min** |
| Content | one question, answered fast | one topic **in depth**: the problem it solves, the core idea, how it works step by step, a second worked example, common mistakes, when to use it |
| Structure | fix_story or walkthrough | always a walkthrough, with **5–10 chapters** of 2–8 shots each |
| Presenter | 3D avatars (new default) | the 3D mentor beside the board |
| Where it plays | the reels feed | the new **Videos** page |

**Same steps for both.** Upload, Topic, Teaching approach, Language, Theme,
Characters, Script, then Your reel or Your video (screens 02–06). For a video:
- Every screen says "video".
- The Theme step offers walkthrough themes only.
- The Characters step recommends the presenter.
- The Script step groups the lines by chapter (screen 05).

## 2. What a video looks like (screens 08, 09, 09b)

Every scene object, animation and highlight is the reel's own. Each shot is
drawn onto a landscape board:

- **Presenter on** (most shots): the visual is on a board at the left, and the
  3D mentor stands at the right. She points at what changes, as in a reel.
- **Presenter off:** the visual gets a wider board in the middle. This happens
  for title and chapter cards, code maps, panels, app screens and tables.
- **Subtitles** run along the bottom. The words light up as they are said, and
  the subtitles never sit under the mentor.
- **Top left:** "CHAPTER 3 / 6 · How it starts".
- **Bottom:** a progress bar with a tick at each chapter.
- **Shot changes:** a short cross-fade.

**The player** is `#motion-video/<id>` (screen 08). It has:
- the 16:9 stage;
- a chapter list you can jump to, with the current chapter highlighted;
- the time shown as mm:ss.

**The Videos page** is the new **Videos** button at the top, `#videos`
(screen 07). Each video shows as a card with a still, its length and its
chapters. Videos do not appear in the vertical reels feed.

**The MP4** is rendered at 1920×1080 by the same renderer as reels. A stub
video is in `video_stub.mp4`: 5:13, 1920×1080, H.264, silent because it is a
stub (local, git-ignored).

## 3. What the AI is asked for

There is a new script prompt, `SYSTEM_MOTION_VIDEO` (`shorts/skills/script.py`):
- **Length:** 936–1872 spoken words (6–12 minutes).
- **Chapters:** 5–10.
- **Arc to follow:** problem, core idea, how it works, a second example,
  mistakes, when to use it.
- **Allowed additions:** the AI may add its own small worked examples,
  everyday comparisons and the mistakes beginners make. These must agree with
  your material and add no new facts, numbers, names or rules.

The running example only has to chain through the chapters that use it. A
"Common mistakes" chapter may use its own example.

**Limits** are in `checks.MOTION_VIDEO`. All other rules are the reel's:
beginner words, one caption per sentence, grounding and the reading level.
The video values are:
- a hard cap of 12.5 min;
- 2–8 shots per chapter;
- at most 300 words per chapter;
- 8–45 words per shot;
- up to 10 code shots;
- up to 8 extra terms.

**Scenes** are asked in batches of up to 14 shots (whole chapters together).
Each batch reads the whole script, so one answer never runs out of room.

## 4. Cost: please read before your first real video

A video's script is about 3× a reel's, and its scenes take about 5 calls.

| | typical | worst (every retry) |
|---|---|---|
| Reel (16k-character document) | $0.67 | $1.83 |
| **Video** (same document) | **$2.69** | **$4.99** |

- **Cap:** there is a separate cap, `MAX_VIDEO_USD`, default **$6.00**. Reels
  keep `MAX_REEL_USD` = $2.00. The footer of each step shows the right cap.
- **Free steps:** voice and timing are free, but slow. Chatterbox takes about
  9–19 s per line, and a video has about 120–200 lines, so expect about
  20–50 min of voice recording.
- **Render time:** the 5 min 13 s stub video took 25 min to render at
  1920×1080, about 5 min per minute of video (with the test suite running at
  the same time).
- **Thin material:** if your section has only a few bullet points, a 6-minute
  video may not have enough to say. The script check then fails as "too
  short", and each full rewrite costs about $0.36. If that happens, pick a
  richer section, or tell me and I'll lower the minimum length.

To make your first real video: restart the server, open http://localhost:5173,
choose **Video**, and upload your material. Each paid button shows its price
before it spends anything.

## 5. Reels: the 3D avatar is now the default

- **New reels use the 3D VRM avatars** (`MOTION_AVATARS` now defaults to
  `vrm`), with the on/off timing from round 2. `MOTION_AVATARS=rig` in `.env`
  brings back the 2D characters. Reels made before keep their look.
- **The 26 s glitch is fixed** (screen 10, before | while it enters | at rest).
  Today it no longer passed behind the mentor's head, but the "Name tag" card
  slid in from beyond the board's edge and was cut off mid-word, and its ✓
  badge was clipped at rest. On the board, the card now rises into place, and
  board layouts keep a 24-unit margin at the right edge. This applies to new
  plans; your reel's saved plans are unchanged until they are re-timed.
- **The end card on light palettes:** its white words sat on the cream field
  and were almost unreadable. This was true for reels too. The card now keeps
  its indigo background there. Dark palettes, like your real reel's, are
  unchanged.

## 6. Checks

- **Python:** 68 of 68 test modules pass. This includes the new
  `shorts/motion_video_test.py`:
  - a video from upload to its landscape plan;
  - a reel is still a portrait reel;
  - a video is always a walkthrough;
  - the limits follow the format;
  - scenes in chapter batches;
  - views never over-enlarge.
- **Evals:** 212 passed, 0 failed, 12 skipped (the paid judge cases).
- **TypeScript** is clean, and the motion checks (`npm run test:motion`) pass.
- **In the browser:** a full click-through of a video, from upload to the
  player, worked (screens 01–08).
- **Video layout checks:**
  - `motion_video_layout`: every object lands inside the frame, above the
    subtitles and clear of the mentor;
  - `motion_video_presence`: the presenter rules.

## Known issues

- **The Characters step still shows the 2D faces** (Arjun, React, Riya). The
  3D presenter is always `assets/avatars/mentor.vrm` / `student.vrm`, so
  picking a face changes only the 2D look (`MOTION_AVATARS=rig`). This is true
  for reels too. A fix would show the 3D presenters there instead.
- **Videos have one narrator.** Both walkthrough themes are one-narrator, so a
  video has the mentor only, with no student.
- **Stub videos repeat themselves.** Their filler lines repeat, so the timing
  stage merges some repeated shots. A real script will not do this.
- **Videos are made from the web UI only.** The command-line runner
  (`python -m shorts.motion_reel`) still makes reels only.
