# 3D avatars, round 2: two looks, on and off, the far cards (2026-10-16)

Reel: `variable_points_to_value__motion` (job `f64077e78448`), rendered from
the preview variant `output/<id>/plan.vrm.json`. The reel's own `plan.json`
and `reel.mp4` are unchanged. There were no model calls, so this cost $0.

| What | Where |
|---|---|
| The whole reel (70.3 s, 1080×1920, with the voice) | `reel_vrm_full.mp4` (local, git-ignored) |
| The same reel for VS Code's preview, which plays no AAC sound | `reel_vrm_full_voice.webm` (Opus voice; local, git-ignored) |
| Key moments (each enter and exit, the points, the aha, the end card) | `frames.png` |
| In the app | `#motion-reel/variable_points_to_value__motion?variant=vrm` |
| Sweep of every moment, with each fingertip reading | `sweep.json` |

## 1. The mentor and the student look different

- **Placeholders today.** Both files are still the same pixiv sample, so the
  player recolours the student while the two files are identical:
  - orange top and blue trousers;
  - dark brown hair;
  - warmer skin and brown eyes;
  - drawn at 93 % size.
- **Your own files.** When your `mentor.vrm` and `student.vrm` differ, both
  are drawn exactly as they are. Nothing in the code changes.
  `web/src/motion/vrm/looks.ts` holds the recolour.
- **No second free model was used.** The only other one I found was
  Seed-san (VRM Consortium). It needs a credit line and has a robot / sci-fi
  look, so it isn't a professional student.
- **Hair.** It sways gently, worked out from the frame's time alone (no
  physics), so every frame stays exact. Deeper strands sway more, and a
  little more when the head moves.

## 2. Avatars come and go

**Pattern on this reel** (`+` = on, `.` = off): `+...+..+++`

| Shot | Beat | Avatars | Why |
|---|---|---|---|
| s01 0.0–3.2 | hook | on | the opening; the student asks |
| s02 3.2–6.2 | title | off | the title card fills the frame |
| s03 6.2–12.3 | setup | off | code |
| s04 12.3–21.8 | break_1 | off | memory panel |
| s05 21.8–30.3 | fix_idea | **on** | the main idea |
| s06 30.3–39.8 | fix_flow | off | flow |
| s07 39.8–50.5 | code_map | off | code map |
| s08 50.5–57.0 | payoff | **on** | the aha ("Now I get it", with the lightbulb) |
| s09 57.0–66.2 | recap | on | recap |
| s10 66.2–70.3 | cta | on | end card |

**The rules** (`library.json` → `avatars`, `motion_teach.avatar_presence`):
- **Always off:** a shot showing code, a code map, a flow, a panel, a table,
  an app screen, a token row, a cycle or a title card. Its visual is laid
  out at full size, never shrunk onto the board, and nothing stands over it.
- **Otherwise:**
  - the scene's own choice, from the new optional `avatars: "on" | "off"`
    field in the scenes step;
  - if the scene doesn't choose, on for the hook, the main idea, the aha, a
    student's question, the recap and the end card, and off elsewhere.
- **Minimum time.** Every on run and every off run lasts at least 2 s. A
  shorter run takes its neighbours' state.
- **Enter and exit.**
  - The avatars slide in from their own side over 0.55 s, once the on
    shot's transition has brought the board in. They never stand over the
    outgoing visual.
  - They slide out over 0.45 s at the end of their last on shot, before the
    next transition starts.
- **While they're off:**
  - the voice goes on;
  - the chat bubbles stay, each labelled STUDENT or MENTOR;
  - on a full-frame shot the caption carries the role label under it.
- **The end card and the recap** keep the avatars beside the board. To leave
  room for them, these two cards are drawn smaller than full size.

**Check: `motion_avatar_presence`.** It fails if any of these happens:
- a visual-heavy shot has avatars, so its visual would be shrunk;
- a shot without avatars is laid out for the board;
- the hook, the recap or the end card has no avatars;
- any on or off run is shorter than 2 s.

`shorts/motion_presence_test.py` covers the rules and the check.

## 3. The far-left cards

When the avatars are on, a shot's cards are laid out against the board's
right edge, the mentor's side:
- compact cards are 620 wide;
- wide objects, like a memory box with an arrow, keep 820, so their
  content still fits.

Two other changes:
- **Reach.** The arm may now reach 86 % of its length; it was 78 %. The
  elbow still bends.
- **Aim point.** The hand never covers the words it points at:
  - a card is pointed at low down, under its label;
  - a pill or a token is pointed at from just under its bottom edge.

**Fingertip** (`sweep.json`):

| Target | Before | Now |
|---|---|---|
| "Box" card (far left) | 100–180 px short | **on the card** (5 px from the aim point, 1 px off the line) |
| "Name tag" card | 4 px | on the card (2 px off the line) |
| "where the box is" pill | 4 px | just under it (2 px off the line) |
| end card | — | 1 px off the line |

## Known issue

At about 26.0 s the "Name tag" card slides in from the right and passes
behind the mentor's head for about a quarter of a second, before it settles
clear of her.

## Render time

The full 70.3 s reel took 263 s (about 4.4 min) to render.

## Still to do after you approve

- `MOTION_AVATARS=vrm` becomes the default for new reels.
- Old reels keep their look: their plans are rev ≤ 3, so they keep the old
  staging and fades.
- 2D stays switchable (`MOTION_AVATARS=rig`).
- Separate commits:
  1. avatar looks;
  2. on/off timing;
  3. cleanup.
