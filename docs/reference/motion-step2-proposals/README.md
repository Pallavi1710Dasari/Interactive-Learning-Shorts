# Step 2 proposals: camera + cursor, avatars, design audit, themes (2026-10-13)

Reel: `variable_points_to_value__motion` (job `f64077e78448`). Both test clips
render from **preview variants** of the reel's plan:

- `output/<id>/plan.camera.json` (camera and cursor)
- `output/<id>/plan.avatar.json` (avatars)

The reel's own `plan.json` and `reel.mp4` are unchanged. Nothing here has been
applied to the pipeline for new reels yet. That waits for your approval.
There were no model calls, so this cost $0.

| What | Where |
|---|---|
| Clip 1: camera + cursor, 14.4 s (reel 6.0 to 20.4 s) | `clip1_camera_cursor.mp4`, frames in `clip1_frames.png` |
| Camera on the code map and the CTA (stills) | `camera_stills_sheet.png` (full size in `camera_stills/`) |
| Clip 2: avatars, 14.9 s (reel 25.0 to 39.9 s) | `clip2_avatars.mp4`, frames in `clip2_frames.png` |
| Avatars on more shots, incl. code map and recap | `avatar_stills_sheet.png` (full size in `avatar_stills/`) |
| In the browser | `#motion-reel/variable_points_to_value__motion?variant=camera` or `?variant=avatar`. The app server needs the new code to serve `?variant=`; the clips were made on a preview server on port 8002. |

The mp4s are git-ignored. They are local files in this folder.

---

## 1. Virtual camera + cursor

### Library choice: built in our stack, no new dependency

Every frame we render must be a pure function of time, so the capture can
seek to any frame and get exactly that frame.

| Option | Why not |
|---|---|
| Framer Motion | Runs on its own clock, not seekable that way. |
| GSAP | Same problem. |
| Remotion | Would replace our renderer, and needs a paid company licence for teams over 3 people. |
| Screen Studio, Cursorful | Screen-recording apps, not libraries. |

Our stack already had what this needs: easing helpers (`time.ts`), path math
(the connector's curves) and the Midnight Lab tilt camera. The new code is
about 450 lines, with nothing new to install:

- `web/src/motion/camera.tsx` (player)
- `shorts/motion_camera.py` (director, geometry, check)

### What it does

**Camera**
- It zooms 1.15× to 1.8× onto the exact thing being explained: a code
  token with its callout, a memory slot, a card, a button.
- The move starts 0.35 s before the word, so the zoom *lands on* the word.
- It holds with a slow 3.5 % push. When the narration moves on, it eases
  back out or hands over straight to the next framing.
- Moves are 0.7 s cubic ease-in-out, interpolated in log-zoom so the zoom
  speed feels even. A hint of blur appears only on fast moves.
- **Only the visual zooms**, inside its own viewport, like zooming inside a
  screen recording. Captions, characters and the progress bar stay put, and
  zoomed content is clipped to the viewport, so it never slides under a
  caption.

**Cursor**
- A vector arrow that keeps its size at every zoom.
- It glides on a curved path, rests just under what it points at (never on
  the text), presses with a ripple on its cue word, and types code one
  character at a time behind a blinking caret.

**Timed to words.** Every cue comes from the wav2vec2 word times already in
the plan.

**Where it is used.** Only where it fits:

| Shot type | Camera | Cursor |
|---|---|---|
| Code window | zoom on the line | types the line |
| Code map | zoom on each token | clicks each token |
| Memory slot / panel | zoom when it is described | clicks the name when it is named |
| App screen | zoom on the screen | — |
| CTA | push in on Follow | clicks Follow on "follow" |

On this reel it makes 7 framings and 6 cursor actions. Other shots stay wide.

**Checks**
- **`motion_camera_safe` (new).** It fails if a framed target would not fit
  whole inside its viewport with a 48 px margin, if the zoom is outside
  1.15 to 1.8, if a framing holds under 0.8 s, or if two moves overlap.
  - It caught two real problems during the build: a memory row too wide to
    reach 1.15×, and a code-map zoom that pushed the callouts over the
    caption band. Both are fixed.
- **The browser sweep** of the camera variant found 0 problems in 55
  moments (`sweep_camera_variant.json`).

### What to check in clip 1

| Time | What should happen |
|---|---|
| 7.0 s | The cursor types `cart = ["milk", "bread"]` while the student says it. The camera holds on the line. |
| 15 s | The camera pushes in on `cart → [milk │ bread]` on "The list is the box". |
| 19.8 s | The cursor clicks `cart` on "cart is just a tag". |

On the stills sheet: the token zooms on the code map (`cart`, `=`, `[ ]`,
each framed with its callout) and the Follow button pressed on "follow".

### Known limits

- Things next to the target can be cut at the viewport edge, like the
  "not a box" pill at 15–20 s. The target itself is always whole.
- The first 0.8 s of clip 1 is still inside Midnight Lab's zoom-through
  transition from the title (the blur there isn't the camera).
- When the narration goes back to a part less than 1.5 s later, the camera
  stays where it is instead of jumping back.

### When applied to the pipeline

The scenes step may also name camera and cursor moves itself (`focus`,
`click`, `type` actions on a cue word). The deterministic director fills in
the rest.

---

## 2. Avatars that teach

### Does the characters-lab rig work? Yes.

It is channel-based: head, eyes, brows, mouth, both arms, each finger,
breathing and sway are all separate channels. It already has:

- blinks, breathing and sway (its life layer);
- 66 gestures, including `point`, `shrug`, `thumbsUp`, `countOne/Two/Three`,
  `handsSpread`, `chinThink`, `leanIn`, `nod` and `tiltCurious`;
- 17 expressions, including `confused`, `surprised`, `happy` and `thinking`;
- word-timed mouth shapes.

So no switch to Rive or Lottie. New code:

- `shorts/motion_teach.py` (director)
- `web/src/motion/cast/teach.ts` (overlays, staging)
- `BoardCharacters` in `ReelCharacters.tsx`

### What is new

**Staging ("board")**
- The visual is a board, upper left.
- The explainer stands beside it, half-body, 1.45× (about 1.55× bigger
  than now), cut softly at the waist.
- The asker is smaller, lower left.
- The chat has its own band at the bottom, never over anyone.
- No halo circles.
- **Characters stay on every explanation shot,** including the code map
  and the recap: full-frame cards are drawn onto the board from their own
  content area, so code stays readable. Only the title and the CTA are
  shown without them.

**Pointing that lands**
- The arm is solved from the shoulder pivot to the exact rect a scene
  action changes (the revealed "Name tag" card, the "where" pill, a flow
  step).
- The finger points straight at it and the body leans a touch.
- The eyes and head look at it too.

**Gaze**
- When not pointing, the explainer turns to the student at the start of
  each line.
- The student looks at the board when something on it is pointed at, and
  at the speaker during a dialogue.

**Lip-sync from the voice.** The jaw follows the loudness of the recorded
voice (30 fps envelope from `audio/reel.wav`), on top of the word-timed
mouth shapes. The mouth is closed in silence.

**Gestures on cue words**

| Cue | Gesture |
|---|---|
| "two things" | 2 fingers |
| "First" | 1 finger |
| "Then" | 2 fingers |
| Wrong idea (failure beat + "not / isn't") | shrug, skeptical face |
| Highlighted word | open palms |
| The student gets it | nod, then thumbs up |
| The hook | the asker leans in |

**Expressions and listener reactions**
- **The student:** curious tilt on a question, confused while the wrong
  idea is taken apart, slow nods along the explanation, and **"aha"** (a
  lightbulb pops, surprised → happy) on "So the variable just points to
  it".
- **The mentor:** grins.

**Look**
- **Mentor:** bun, round glasses, watch, Python-blue shirt, smiling.
- **Student:** curly hair, warm orange hoodie, jeans.
- Both use the rig's "lit" shading (the polished one).
- This variant carries the new looks inside the plan. Per-language
  defaults and the designer would be updated once you approve.

**Checks.** The browser sweep of the avatar variant found 0 problems in
55 moments: no text under a character, no caption overlap
(`sweep_avatar_variant.json`).

### What to check in clip 2

| Time | What should happen |
|---|---|
| 25.5 s | Points at the board. |
| 26 s | Points at the "Name tag" card as it slides in. |
| 28 s | Points at "where". |
| 31.3 s | Two fingers on "two things". |
| 32.2 s | One finger on "First". |
| 35 s | Two fingers on "Then". |
| 38.1 s | The student's lightbulb. |
| 38.3–39 s | The mentor nods, then thumbs up. |
| Throughout | Blinks, breathing, lips with the voice. |

### Known limits / next steps

- On "First", the counting hand passes briefly through a sideways position
  on its way up (the rig's own count motion).
- A point aims at the target from the arm's length: the finger points *at*
  it, it does not touch it.
- Mouth shapes come from the words' letters plus the voice's loudness, not
  recognised phonemes. A free local phoneme aligner (a wav2vec2 phoneme
  model) could make them exact, if you want that.

---

## 3. Design audit (list only, nothing restyled yet)

**Sources**

| Name | Means |
|---|---|
| Ref 1 | The first reference reel (`docs/reference/reference_reel.html`), redrawn in `objects/reference.tsx` |
| Ref 2 | The tokenization reel (`REFERENCE_STYLE_ADDENDUM.md`), redrawn in `objects/editorial.tsx` and `transitions.tsx` |
| Ours | Made in this project |

| # | Element in the current reel | Source | Replace with (proposal) |
|---|---|---|---|
| 1 | Colour set: indigo `#5B4BF5`, amber `#FFB524`, coral `#F2555A`, mint `#17B27B`, ink `#151936`, code colours | **Ref 1, exact hex values** | The palette system below. Keep fixed *meanings*, not these hues. |
| 2 | Manrope body and display type | **Ref 1** | An original pairing: a rounded geometric sans for display, a humanist sans for captions, JetBrains Mono for code only |
| 3 | Glass cards (radius 48–54, full width, inset light edge, deep shadow) | card shape **Ref 1**, glass finish ours | **Index cards:** radius 18, a coloured top tab that names the category, slight paper grain, a short hard shadow |
| 4 | Icon tile (rounded square with tinted fill and line icon) on cards, rows and the title | **Ref 1** | Icons inline at text size inside the card's tab. No tile. |
| 5 | Perspective grid floor | ours (Midnight Lab), reads as the references' tech look | **Removed.** Matte background with soft grain, or a lamp vignette. |
| 6 | Blue/violet glow blooms, cyan glow on key words | ours (Midnight Lab) | Removed. Key words get a marker-highlight sweep in the palette's highlight colour. |
| 7 | Halo circles behind characters | ours | Removed (already gone in board staging) |
| 8 | "// SECTION" mono tracked labels | tracked caps **Ref 2**, "//" ours | **Section ribbon:** a short vertical tab on the board's left edge with the beat's step number and one word |
| 9 | Segmented progress bar (full width, top) | **Ref 2** | **Timeline thread:** a thin line down the ribbon edge, one knot per beat, the current knot filling |
| 10 | Step chip (walkthrough) | **Ref 2** | Folded into the section ribbon |
| 11 | Field transitions: iris, bar wipe, double bar, diagonal stripes, stack rise | **Ref 2** | Our own: **index-card flip**, **marker swipe** (a highlighter stroke reveals the next shot), **focus pull** (blur to sharp, using the camera), **card stack slide** |
| 12 | Zoom-through transition, 3D tilt-in | ours (Midnight Lab) | Kept for Midnight Lab only |
| 13 | Title card (series pill, giant title, amber promise, 3 icon tiles) | **Ref 1** | **Cover card:** the concept on an index card held on the board, the mentor presenting it, the promise as a handwritten-style note |
| 14 | Takeaway list (heading and 3 icon rows) | **Ref 1** | **Sticky-note recap:** 3 notes pinned to the board one by one, each with a marker tick |
| 15 | Code window (traffic-light dots, file bar) | **Ref 1** (and a common macOS trope) | **Editor card:** our own frame with a file tab, line gutter and caret. No traffic lights. |
| 16 | Status pills, trigger chip, connector with travelling dot, system panel, entity card | **Ref 1** | Same jobs, redrawn in the index-card language: tag-shaped pills, string-like connectors |
| 17 | Token rows and chips, lookup grid, big counter, bracket, callout, stamp, recap grid, chapter card, kinetic title | **Ref 2** | Redrawn in the new language. Kinetic title becomes a marker-written headline. |
| 18 | Action objects (app screen, memory box, flow, compare, cycle) | ours, drawn in Ref 1's card language | Keep the behaviour, redraw in the new language |
| 19 | Karaoke caption (words light as spoken) | **Ref 2** | Keep the idea (it is standard), restyled. Chat bubbles are ours. |
| 20 | Annotated code callouts, pointer slot / box, word-cued end card | ours (step 1) | Keep, restyle |
| 21 | Language identity (symbol, title chip, sting) | ours | Keep |
| 22 | Characters | rig from the internal characters lab; look ours | Keep (item 2) |
| 23 | Dot grid | **Ref 1** (not used in Midnight Lab) | Removed |

### Palette system (proposal)

Every palette keeps three fixed meanings, checked for contrast by
`identity/contrast.ts`:

| Meaning | Colour | Hex |
|---|---|---|
| Wrong | red | `#E5484D` |
| Right | green | `#2BB673` |
| Highlight | marker yellow | `#FFD43B` |

The palettes:

| Palette | Base / ink / accent | Mood, fits |
|---|---|---|
| Chalkboard | deep green `#1F3A34`, chalk `#F3F1EA`, sky `#8FD3FF` | whiteboard sketch, doubt clinic, mentor themes |
| Paper | warm paper `#F6F1E7`, ink `#1D1B16`, blue pen `#2457C5` | the light option: explainer, myth vs fact, recap-heavy reels |
| Terminal amber | charcoal `#16181D`, off-white `#ECE9E1`, amber `#FFB000` | live code-along, bug hunt, error decoder |
| Deep teal | teal `#0F3D44`, white, coral accent `#FF7A59` | interviews, real-world scenarios |
| Plum & gold | plum `#2A1730`, cream, gold `#F2C14E` | myth vs fact, predict-and-pause quizzes |
| Midnight Lab | as today | switchable style, kept as one option |

**How a reel gets its palette.** The theme picks the mood (table above).
The course language adds its accent (Python blue, JavaScript yellow, and
so on, from `motion_identities.yaml`) as the secondary colour. The design
stays switchable per reel, as `design` is today.

### Layout variety (proposal)

**Layouts**
- board + presenter (item 2)
- full-bleed object
- camera close-up
- split stacked (before above after)
- list rail
- big number
- code focus (editor card + callouts)
- cover card

**New check `motion_layout_variety`:** no single layout on more than 40 %
of a reel's shots, and never three shots in a row with the same layout.
The current reel would fail it: 8 of its 10 shots stack full-width cards
in one centred column.

---

## 4. Themes and teaching approaches (list only)

### The current themes (14, not 10)

Your job listed 10 because 4 others did not fit its section or approach.
All 14 are in `shorts/motion_themes.yaml`.

| Theme | Tag | Speakers | Template | Needs code | Recommended when (its `suits`) | Works with / never with |
|---|---|---|---|---|---|---|
| Explainer | #explainer | 1 narrator | fix_story | no | why X fails, a fix to apply, any concept | analogy, real-world, code, visual, comparison, direct |
| Narrative | #narrative | 1 narrator | fix_story | no | a problem with a clear moment it bites, everyday bugs | real-world, analogy, visual, direct, code |
| Interview | #interview | 2 (interviewer, candidate) | fix_story | no | classic interview questions, crisp answers | code, direct, comparison, visual |
| Rapid fire | #rapidfire | 2 (interviewer, candidate) | fix_story | no | facts, definitions, revision | direct, code, comparison / never process, analogy |
| Peer discussion | #discussion | 2 peers | fix_story | no | confusing behaviour, wrong mental models | analogy, comparison, visual, direct, code |
| Mentor & student | #mentor | 2 (student, mentor) | fix_story | no | foundational concepts, beginner confusion | analogy, direct, visual, code, real-world |
| Bug hunt | #bughunt | 1 narrator | fix_story | **yes** | a bug a beginner writes | code, process, direct / never analogy |
| Myth vs fact | #mythvsfact | 1 narrator | fix_story | no | a common wrong belief | comparison, direct, visual, code / never process |
| Common mistakes | #mistakes | 1 narrator | fix_story | no | typical misuse, classic traps | code, direct, comparison / never analogy |
| Predict the output | #predict | 1 narrator | fix_story | **yes** | code whose result surprises | code, process / never analogy, real-world |
| Under the hood | #underthehood | 1 narrator | fix_story | no | mechanisms behind familiar behaviour | visual, process, direct, code / never real-world |
| Walkthrough | #walkthrough | 1 narrator | walkthrough | no | how X works, ordered steps | process, visual, code, direct |
| Real world | #realworld | 1 narrator | fix_story | no | concepts with a real product use | real-world, analogy, direct, code / never process |
| Before & after | #beforeafter | 1 narrator | fix_story | no | small change, big effect | comparison, code, visual / never process |

Several of your ideas already exist:

| Your idea | Existing theme |
|---|---|
| bug hunt | Bug hunt |
| myth vs fact | Myth vs fact |
| rapid-fire interview | Rapid fire |
| "mistake of the day" | Common mistakes |
| pause-and-predict | Predict the output (code only) |

### The current teaching approaches (7)

| Approach | What it is | The AI recommends it when (from its prompt) |
|---|---|---|
| analogy | explained by something familiar | the mechanism is abstract and hard to picture (what a stack, a cache or a lock IS) |
| real_world_example | a concrete everyday case | the concept's value is best seen in a situation the learner knows |
| code | read the actual code | only when the concept IS syntax or a language rule ("code is not the default") |
| conceptual_visual | a diagram of structure or state | the concept is defined by structure or by something changing over time |
| process_demonstration | walk the steps in order | an operation or algorithm: what happens, in order |
| comparison | two things side by side | the concept IS the difference between A and B |
| direct_explanation | stated plainly | a definition or plain rule needing no device |

### Proposed new themes (6)

They don't overlap the 14 above. Each would be one new entry in
`motion_themes.yaml`. The AI picks among themes from that file, with a
reason, so they would show in the UI exactly like the existing ones.

| Theme | Tag | Speakers | Template | Needs code | Description | AI recommends it when (reason) | Preferred scene types | Works with |
|---|---|---|---|---|---|---|---|---|
| Live code-along | #codealong | 1 narrator | walkthrough | yes | The narrator writes the code live (the cursor types it), runs it, reads the result, changes one thing, runs again | the concept is learned by **writing** it: syntax plus an immediate visible result (a loop's output, a function's return) | code_window (typed), terminal output (new), camera on the line, token_row for output | code, build_from_zero, worked_example_then_try |
| Doubt clinic | #doubtclinic | 2 (student, mentor) | fix_story | no | The student asks the doubt in their own words; the mentor repeats it, names the hidden wrong assumption, clears it in one picture, then checks with a quick follow-up the student now answers right | the material answers a **question learners actually ask** ("why does…", "isn't it the same as…"). Question-led, not problem-led like Mentor & student. | compare, memory_box, status_pill, characters (confused → aha) | misconception_repair, socratic_questions, analogy |
| Whiteboard sketch | #whiteboard | 1 narrator | fix_story | no | The idea is drawn stroke by stroke on a board: boxes, arrows, labels appear as they are said (Chalkboard palette) | the concept is a **structure**: memory, references, trees, networks, layers | flow, cycle, memory_box, connector (drawn on), camera big-picture → zoom | conceptual_visual, big_picture_then_zoom, build_from_zero |
| Pause & predict quiz | #quiz | 1 narrator | fix_story | no | A multiple-choice question with 3 options, a 3-second "pause now" countdown, the reveal, why the wrong options are wrong | the outcome is **predictable from what was taught but often guessed wrong**. Unlike Predict the output, it needs no code. | token_row (options), big_counter (countdown), compare (reveal), stamp | predict_then_reveal, misconception_repair |
| Error decoder | #errordecoded | 1 narrator | fix_story | yes (an error message) | A real error message is read part by part (type, line, the clue), the cause is found, the fix applied, the error gone | the section shows or explains an **error message** beginners hit | code_window, callouts on the message, camera, cursor clicks | code, step_by_step_trace, direct_explanation |
| This or that | #thisorthat | 1 or 2 | fix_story | no | Two valid options face off over 3 rounds (when each wins), then a verdict rule. Unlike Before & after, both are correct. | the concept is a **choice** between two valid tools (list vs tuple, let vs const, == vs is) | compare, token_row, stamp (verdict) | comparison, real_world_example |

Two alternates if you want to swap any:

- **Cheat-sheet recap** (#cheatsheet): 5 rules in 30 s, for revision.
- **Exam answer** (#examanswer): how to answer a placement or exam
  question, step by step.

### Proposed new teaching approaches (7, for 14 in all)

Three of your ideas already exist: everyday analogy is `analogy`,
side-by-side compare is `comparison`, real-world scenario is
`real_world_example`.

The "Speakers" column is the number of speakers each works best with. Every
one of them also works with 1 speaker.

| Approach | Description | AI recommends it when (reason) | Speakers | Preferred scene types | Tags |
|---|---|---|---|---|---|
| predict_then_reveal | Ask the viewer to commit to a guess, hold a beat, then show the real result | the result is **surprising yet predictable** from what the viewer already knows; the commitment makes the correction stick | 1 or 2 | code_window, compare (reveal), stamp, status_pill | #predict #quiz |
| misconception_repair | Name the wrong mental model, show exactly where it breaks, replace it with the right one | the material **contradicts a common belief**, or learners reliably hold a wrong picture (box vs name tag) | 2 (student voices it) | compare, memory_box, stamp, characters confused → aha | #myth #doubtclinic |
| build_from_zero | Start from nothing and add one piece at a time until the whole thing exists | the concept is **composite** (a class, a function, a request, a data structure) and each piece only makes sense after the last | 1 | flow, token_row, code_window typed, camera | #codealong #whiteboard |
| worked_example_then_try | Solve one example fully, then pose a near-identical one for the viewer, answered at the end | the skill is **procedural**: a calculation, a syntax pattern, a rule applied to new input | 1 | code_window, token_row, big_counter | #practice |
| socratic_questions | A chain of 3–4 questions, each answer leading to the next, until the learner reaches the idea | the concept is a **reasoning chain** ("why… then why…") best discovered rather than told | 2 | characters, status_pill, compare | #mentor #doubtclinic |
| big_picture_then_zoom | Show the whole system first, then zoom (the camera) into the one part this reel is about | the concept is **a part of a larger system** and only makes sense in place (the TLB in address translation) | 1 | flow, cycle, camera close-up | #underthehood #whiteboard |
| step_by_step_trace | Follow the values line by line in a small trace table as the code runs | the concept is about **how state changes** as code executes (loops, recursion, aliasing) | 1 | code_window highlight per line, lookup_table (trace), memory_box | #trace #codealong |

**How they would be recommended.** The approach list lives in one prompt
block (`skills/teaching_approach.py`, the same rules for first decision and
regeneration) and one schema type. Each new approach gets its definition
and its "fits when" rule there, and each new theme lists which approaches
it works with. So the AI recommends them with a specific reason, and they
show in the UI the same way as the existing ones.

---

## What happens after you approve

1. **Camera + cursor:**
   - the director runs at the timing stage for every new reel;
   - `motion_camera_safe` joins the timing checks;
   - the scenes prompt learns the `focus` / `click` / `type` actions;
   - the app server picks up `?variant=` on restart.
2. **Avatars:**
   - board staging and the teaching director become the default for
     reels with characters;
   - the new looks go into `motion_character_presets.yaml`, one per
     language, still changeable in the designer;
   - the old band layout stays available.
3. **Design:** after you pick from the audit, the new visual language is
   built as a switchable design next to Midnight Lab, with
   `motion_layout_variety`.
4. **Themes and approaches:** after you approve the lists, they are added
   to the theme registry, the approach schema and the prompts, with tests.
5. The full reel is re-rendered with what you approve. Each change gets its
   own commit.

Also changed for these previews:

- `?variant=` on the plan endpoint and the player;
- `python -m shorts.motion_clip` to render a slice of a reel;
- `--variant` for `motion_sweep`.

None of this is committed.
