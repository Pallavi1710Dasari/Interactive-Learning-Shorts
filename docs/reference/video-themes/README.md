# Videos can use every theme (2026-10-17)

**Asked for:** on step 5 (Theme) a video showed only *Walkthrough*. Keep
Walkthrough as the recommended theme, but let the user pick any other theme,
including the two-speaker ones (Interview, Mentor & student, Peer discussion,
Rapid fire, Doubt clinic).

## What changed

**The rule.** A video keeps its own structure whatever the theme: hook,
name it, the running example, then 5 to 10 numbered chapters, result,
takeaway, recap and the call to action. The theme decides the voice:

| Theme kind | What the video becomes |
|---|---|
| Walkthrough (recommended) | unchanged: one mentor, step by step |
| One-narrator themes (Myth vs fact, Common mistakes, Under the hood, Real world, ...) | one mentor, each chapter told in that theme's style. The hook stays the video's "Why / What / How ...?" question. |
| Two-speaker themes (Mentor & student, Interview, ...) | a dialogue. The asker (student or interviewer) opens with the question and keeps the viewer's side: short questions, guesses, reactions. The explainer (mentor or candidate) does the teaching in every chapter. Every line is labelled with its speaker. |

**Theme step.** When the format is Video, the AI still recommends a walkthrough
theme, and it comes first with the *recommended* badge. Every other theme that
fits the material is listed after it ("Show N more"). Themes that need code
(Bug hunt, Predict the output, Error decoder, Live code-along) only appear
when the section has code.

**Two speakers on the 16:9 frame.** The asker (student) stands on the left and
the mentor on the right, with the board between them (`board_duo`). Subtitles
sit under the board and start with the speaker's name, in that speaker's
colour. The layout check (`motion_video_layout`) now keeps the board clear of
both presenters, not just the mentor.

## Where to look

1. **The Theme step in the app.** Open http://localhost:5173, upload any
   material and choose **Video**, then go through to step 5. You should see
   Walkthrough recommended first, then the other themes, including the
   two-speaker ones. A video job that was already sitting on step 5 before
   this change still shows its old one-item list. Go back to the
   **Language** step and continue (the theme step is then built again, free
   in stub mode), or start a new upload.
2. **Screenshots** (stub runs: placeholder script text, silent voice):
   - `mentor_student/` is a two-speaker video:
     - `t002.81.png`: the hook, asked by the STUDENT with both avatars on.
     - `t018.30.png`: a chapter card. Presenters are off and the subtitle is still labelled.
     - `t023.02.png`: a chapter line by the STUDENT.
     - `t025.85.png`: a chapter line by the MENTOR, pointing at the board.
   - `myth_vs_fact/` is a one-narrator theme. It keeps the usual one-mentor
     layout, with no speaker label on the subtitles.

## What to check

- Does a two-speaker video *read* well? The stub script just alternates
  placeholder lines between the two speakers. The real dialogue quality (does
  the student ask good questions, does the mentor carry the teaching) can only
  be judged on a real run, which costs money (see below).
- The student's name label in the subtitle is a pale grey on the dark band.
  It comes from that character's identity colour. Say if you want it
  brighter.
- With the student on screen the board is narrower (860 px, was 1176 px), so
  long subtitles wrap to two lines more often.

## A real run (paid; run it yourself)

Upload, pick **Video**, choose **Mentor & student** at step 5, and run with
`SHORTS_STUB` unset. The cost is the same as any video: one script call
(plus repairs) and the scene batches. The pre-flight screen shows the estimate
before anything is spent. The spend cap is `MAX_VIDEO_USD`.

## Tests

`SHORTS_STUB=1 PYTHONUTF8=1 ./venv/Scripts/python.exe -m shorts.motion_video_test`.
Two tests are new:
- `test_a_video_in_a_one_narrator_theme_keeps_its_chapters`
- `test_a_two_speaker_video`

`_make` now also checks that a video offers both template families and at
least one two-speaker theme, with the walkthrough recommended first.

## Files

- `shorts/motion_jobs.py`: a video's theme options are no longer limited to the walkthrough template.
- `shorts/motion_reel.py`: a picked theme is accepted for a video, and the video's script is always written as a walkthrough.
- `shorts/skills/script.py`: the video prompt gets a dialogue format for two-speaker themes (speaker on every caption), and speakers are kept in the hook and shot repairs.
- `shorts/checks.py`: for a video, the hook keeps the walkthrough rule, either speaker may open a chapter shot (the asker opens the hook), and only the asking role may ask questions.
- `shorts/motion_video.py`, `web/src/motion/library.json`, `web/src/motion/video/VideoFrame.tsx`: the two-presenter layout and the speaker name on subtitles.
- `shorts/motion_video_test.py`: the tests above.
