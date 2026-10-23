# Videos that teach in one watch: line-by-line code, no repeated pictures (2026-10-23)

Your feedback: the explanation wasn't good enough, the same picture repeated
through a whole concept, and a student should understand the concept from
the video alone. For code, every line should be explained: what it does and
why. For theory, even a one-line point should be explained properly.

**First, what you have seen so far.** Every video on this machine was made
in **stub mode**. The only real video attempt (runtime polymorphism) stopped
at the cost screen before its script was written. Stub mode has no AI
writing or drawing anything. Its words are filler and every picture is the
mechanical fallback. Part of what you saw comes from that. The causes below
are in the real path too, and all of them are fixed.

## What was wrong (in the real path, not just stubs)

| # | Cause | Effect | Fix |
|---|---|---|---|
| 1 | The video prompt said "explain every step fully" but gave no method. Short notes were read out, not taught. | One-line definitions stayed one line. | New **TEACH SO ONE WATCH IS ENOUGH** rules (below). |
| 2 | Code was capped at 4 lines per shot, and nothing asked for each line to be explained. | Code was shown but not walked through. | New **CODE, LINE BY LINE** rules and a new `code_focus` field, plus a free check that **every line is explained**. |
| 3 | Code lines were capped at 30 characters. | Most real code didn't fit. `System.out.println("This animal eats food.");` is 45. | A video allows **6 lines of up to 52 characters**, and the code window is drawn as wide as its longest line. |
| 4 | A video script allowed 4 code lines, but the scene check allowed only 3. | **Every 4-line code shot failed its scene check** and fell back to the default picture. | A video's scene check allows 6 lines. |
| 5 | The running example (chips) was the fallback picture of **every** chapter shot that carried it. The variety check ignored it. | "The same visual throughout": chips, chips, chips. | The chips appear **at most once per chapter** (a new check). The fallback turns through chips, flow, card, memory box and loop. |
| 6 | The timing step dropped shots that "repeat an earlier picture". | A code-walk shot (same code, new line lit) would be **dropped with its narration**. | Code-walk shots are never dropped (tested end to end). |
| 7 | The scenes AI got the video rules only when a video needed several batches, and never during repairs. | Rules were missed. | Every video scenes call, repairs included, gets the video rules. |

## The new rules the script AI gets (`SYSTEM_MOTION_VIDEO`)

**The goal:** a student watches once, with no book, notes or teacher, and can
explain the topic back afterwards.

**Teach so one watch is enough:**
- Never lean on anything not yet taught. Each chapter builds only on earlier ones and opens by linking to them.
- Each bullet or line in your notes is an idea to **teach**, never a line to read out. Every idea gets all three:
  1. **What** it says, in plain words.
  2. **What it looks like**: a small concrete case.
  3. **Why**: why it's true or needed, or what goes wrong without it.

  A one-line definition gets all three too.
- Cover every idea in the material, and add no new facts.
- Say what the computer actually *does* at each step.

**Code, line by line:**
- One shot shows the whole snippet and says what it does as a whole.
- Then **one shot per line**. Each shows the same snippet with its line lit, and says **what** the line does, **why** it's there, and **what changes** when it runs.
- Closing braces, blank lines and comments need no shot of their own. Every other line must be explained, or the script fails a free check and only that shot is rewritten.
- Then one shot runs the code from top to bottom and says what it prints, and why.
- A longer program is split into snippets of at most 6 lines.

**Visuals:**
- Never the same picture twice in a row. A code walk is the exception: there, the lit line moving is the picture.
- The example's chips appear at most once per chapter. The other shots show what the step *does* to the example.

## Where to look

1. **Frames from a stub video of your own inheritance notes** (`output/uploads/dbe1c6feffb7.md`), in this folder:
   - `05_code_whole.jpg`: the whole snippet.
   - `06_code_line1.jpg`: line 1 lit.
   - `07_code_line4.jpg`: line 4 (`class Child extends Parent {`) lit, with the mentor pointing at it.
   - `08_code_run.jpg`: running the code.
   - `01`–`04`: one chapter turning through flow, card, memory box and loop, instead of chips on every shot.

   These are stub frames, so the **words are filler and the labels are mechanical** (`03_ch1_memory_box.jpg` says "access / modifiers"). Judge the structure (line lit, line moving, pictures changing), not the words.
2. **Play it:** http://localhost:5173 → **Videos** → *stub_what_is_inheritance__video*. The code walk is in chapter 4, at about 2:43–3:10.
3. **Script step:** when a real video reaches the Script step, every code shot now shows its code under its first line, with the explained line marked ▶ and lit in amber. That is where you check that every line is explained before you pay for visuals. *(Type-checked and built. I haven't screenshotted it, because it needs a real script.)*

## What only a real run can show

How good the explanations actually are depends on the AI following these
rules. The free checks guarantee the structure: every code line gets a shot,
the line is lit, and chips appear once per chapter. They can't judge whether
the "why" is a good one. The real test is one paid video from your notes.
The script prompt is about 1,200 tokens longer, roughly 2 cents more per
script attempt. The cost screen shows the full estimate before anything runs.

## Checks run (all free, stub mode)

- 68 of 68 test modules pass. `motion_video_test` has 6 new tests: line-by-line coverage, the longer code limits, the lit line, chips once per chapter, walk shots never dropped, and the prompt rules.
- Evals: 212 passed, 0 failed, 12 skipped.
- Web: TypeScript clean, `npm run test:motion` passes, build OK.
- Nothing is committed. No paid calls were made.
