# 3D VRM avatars: 15 s test clip (2026-10-14)

Reel: `variable_points_to_value__motion` (job `f64077e78448`). The clip runs
from 24.9 to 39.9 s of the reel and renders from a preview variant
(`output/<id>/plan.vrm.json`). The reel itself is unchanged. There were no
model calls, so this cost $0.

| What | Where |
|---|---|
| The clip (15.0 s, 1080×1920, with the voice) | `clip_vrm_avatars.mp4` (local, git-ignored) |
| 10 frames from it | `clip_frames.png` |
| Every gesture side by side | the app's `#motion-vrm-lab` page (`&close=1` for the hands) |
| The whole reel with 3D avatars | `#motion-reel/variable_points_to_value__motion?variant=vrm` |
| Sweep of the whole reel in 3D | `sweep_vrm_variant.json`: 55 moments, 0 overlaps, plus every fingertip reading |

## The models (placeholders)

`assets/avatars/mentor.vrm` and `student.vrm` are both pixiv's
**VRM1_Constraint_Twist_Sample.vrm** (VRM 1.0), from the three-vrm repo.

Its own licence metadata (read from the file, not assumed):

| Field | Value |
|---|---|
| `commercialUsage` | `corporation` |
| `allowRedistribution` | `true` |
| `modification` | `allowModificationRedistribution` |
| `creditNotation` | `unnecessary` |
| `licenseUrl` | https://vrm.dev/licenses/1.0/ |

`motion_vrm_test` checks that each avatar file is VRM 1.0 and allows
commercial use, so it will check your own files too.

The sample wears a white T-shirt; your models' professional outfits replace
it. **Replacing the two files needs no code change.** The server reads them
on every request (`/api/motion/avatars/<name>`). The framing is measured
from each model's own hips and head. The poses work through the VRM
standard bones and expressions.

## Libraries

- **Three.js `0.185.1`:** already installed, now pinned exactly.
- **`@pixiv/three-vrm` `3.5.5`:** new, pinned exactly.

Both are MIT, installed from npm, with no API key and no per-reel cost.

**No Mixamo.** Every gesture is posed directly on the VRM bones. Mixamo
clips need an Adobe login to download, and a retargeted clip couldn't have
its fingertip solved onto a target. The pose lab shows each gesture.

## How it works

- **Layer.** The avatars sit above the board and below the captions. Each
  is drawn on its own transparent canvas.
  - The mentor's canvas reaches left over the board, so a pointing hand
    shows there.
  - Every canvas ends above the chat band: the mentor's at 1180, the
    student's at 1330, the band at 1340.
- **Frame-exact.** Everything is computed from the frame's time:
  - blinks, breathing and sway (the existing life layer);
  - nods, shakes and tilts;
  - gestures and their beats;
  - the mouth.

  The spring-bone physics is never run: it depends on earlier frames, so
  the hair stays still. The capture waits until the models have loaded
  before it photographs a frame.
- **Mouth.** The VRM shapes aa / ee / ih / oh / ou come from the
  word-timed mouth shapes (wav2vec2 timings). They are opened by the
  recorded voice's loudness. The mouth is shut when that character isn't
  speaking.
- **Face.**
  - Relaxed and attentive by default.
  - "Happy" is a hint of a smile (at most 0.22), never a laugh.
  - Surprised for the "aha".
  - Confused is a little sad plus a head tilt.
  - The director no longer cues a grin.
- **Gaze.** The eyes look at the element being explained, at the other
  speaker during dialogue, and otherwise at the camera. The head turns part
  of the way with them.

**Gestures**

| Gesture | What it looks like |
|---|---|
| Point | A bent elbow (the arm is solved at most 78 % of its reach, so it is never straight), index out, the other fingers curled, thumb tucked. Then the forearm turns until the line through the fingertip runs through the target. |
| Present | Palm up toward the board, used on the idea beats (title, fix idea, code map, recap). |
| Explain | Both palms up at chest height, with a small beat on each spoken word. |
| Shrug | Palms up and out, shoulders raised. |
| Others | Nod, head shake, thumbs up, "aha" (lightbulb and surprised face), held finger counts. |
| Rest | Hands relaxed and softly curled. |

Every gesture eases in over 0.35 s and back to rest over 0.45 s.

**Framing.** Waist-up. The mentor stands beside the board with her head
level with its top, like a teacher at a whiteboard. The student is smaller,
lower left, turned toward the mentor.

## Checks

**Fingertip** (from `sweep_vrm_variant.json`): pixels between the target
and the line through the fingertip, at every held point in the reel.

| Where | Line to target | Fingertip to target |
|---|---|---|
| "Name tag" card, 26.1 s | 2 px | 4 px (it lands on it) |
| "where" pill, 30.2 s | 2 px | 4 px |
| flow step, 35.1 s | 1 px | 32 px |
| Code map tokens | 3–12 px | out of reach, points straight at it |
| Far-left cards (Box, memory slot, code line) | 6–15 px | 100–180 px short, points straight at them |
| One frame mid-handover between two points, 45.2 s | 58 px | — |

Targets on the far left of the board are beyond arm's reach.

**Captions.** No avatar covers a caption:
- `motion_caption_layout` passes with the 3D canvases, and fails a canvas
  pushed onto the chat band;
- the browser audit treats each 3D canvas as a character: 0 overlaps.

**Render time** for the 15 s clip:
- 3D avatars: 73.7 s;
- the same clip with the 2D characters: 51.5 s, so 3D is about 43 % slower;
- a full 70 s reel: about 5.7 min instead of about 4.

## What happens after you approve

- `MOTION_AVATARS` becomes `vrm` by default. It is `rig` (2D) today, and
  stays switchable.
- New reels get 3D avatars. Old reels keep their 2D characters: their plans
  carry no `avatars`.

Not done yet:
- **Gaze on the student.** It turns toward the mentor but is drawn smaller,
  so its look is subtle.
- **Hair physics.** It is off, to keep frames exact. A deterministic
  re-simulation per frame is possible if you want moving hair; it would make
  rendering slower.
