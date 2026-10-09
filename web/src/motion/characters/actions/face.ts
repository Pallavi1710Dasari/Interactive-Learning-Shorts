/* The face: held expressions and the short things a face does on its own.
 *
 * Two kinds of action live here. An EXPRESSION is a held face, looped so
 * compose can crossfade from one to the next. A FACE one-shot is a real
 * event with real timing: a blink is 90 ms down and 180 ms up, a brow
 * flash is a sixth of a second, a yawn takes 2.4 s. The numbers come from
 * how people actually move, because a blink that takes half a second reads
 * as drowsy and a smile that arrives all at once reads as a mask.
 *
 * Every expression is a little lopsided on purpose. Faces are not symmetric
 * and a symmetric one looks drawn, so one brow sits 0.05 to 0.1 higher and
 * the mouth slides a few px to one side. The renderer derives the rest of a
 * smile (cheek apples, lower lids, teeth) from `smile` itself, so a smile
 * here is mostly the corners and a little mouth width. */
import type { Channel, Pose } from '../rig/channels'
import { delay, mirror, type Action, type Key, type Tracks } from '../rig/track'

type Face = Partial<Pose>

/* One key per channel holds the value for the whole 1 s loop. Only the
   channels that make the expression are written: what is left out keeps
   the idle layer's life underneath, which is why a happy face still
   blinks and glances about on its own. `blink` and `look` appear only in
   the few expressions where the lids or the gaze ARE the expression. */
function held(name: string, face: Face): Action {
  const tracks: Tracks = {}
  for (const ch in face) tracks[ch as Channel] = [[0, face[ch as Channel]!]]
  return { name, duration: 1, loop: true, group: 'face', tracks }
}

/* A one-shot. Fast events get a short blendIn so compose does not soften
   the very thing that makes them read; the default 0.18 s would put a
   blink at half weight at the moment it closes. */
function shot(name: string, duration: number, tracks: Tracks, blend: { in?: number; out?: number } = {}): Action {
  return { name, duration, group: 'face', blendIn: blend.in ?? 0.08, blendOut: blend.out ?? 0.2, tracks }
}

/* The right eye closes about 15 ms after the left; both eyes blinking on
   the same frame is one of the things that makes a face look animated. */
const EYE_LAG = 0.015
const eyes = (left: Key[]) => ({ blinkL: left, blinkR: delay(left, EYE_LAG) })

/* ----------------------------------------------------------------------
   Expressions
   ---------------------------------------------------------------------- */

export const EXPRESSIONS: Record<string, Action> = {
  /* Not blank: a resting face has a hint of a smile and brows that do not
     quite match, or it reads as a mannequin. */
  neutral: held('neutral', {
    browL: 0.02, browR: -0.03, browInnerL: 0, browInnerR: 0,
    smile: 0.12, mouthWide: 0.35, mouthOpen: 0, pucker: 0, teeth: 0, mouthX: 0.02,
    squint: 0, cheeks: 0, jawX: 0, pupil: 1,
  }),

  happy: held('happy', {
    browL: 0.12, browR: 0.05, browInnerL: 0.05, browInnerR: 0.02,
    smile: 0.65, mouthWide: 0.5, mouthOpen: 0.08, pucker: 0, teeth: 0.3, mouthX: 0.04,
    squint: 0.12, cheeks: 0.25, jawX: 0, pupil: 1.05,
  }),

  /* Wider and more open than happy, so the renderer shows the upper teeth. */
  grin: held('grin', {
    browL: 0.18, browR: 0.1, browInnerL: 0.05, browInnerR: 0,
    smile: 0.85, mouthWide: 0.75, mouthOpen: 0.2, pucker: 0, teeth: 1, mouthX: 0.06,
    squint: 0.3, cheeks: 0.35, jawX: 0, pupil: 1.05,
  }),

  /* Held mid-laugh: head back, eyes nearly shut by the cheeks, jaw open. */
  laugh: held('laugh', {
    browL: 0.22, browR: 0.14, browInnerL: 0.1, browInnerR: 0.05,
    smile: 0.9, mouthWide: 0.65, mouthOpen: 0.55, pucker: 0, teeth: 1, mouthX: 0.05,
    squint: 0.6, blinkL: 0.35, blinkR: 0.4, cheeks: 0.45, jawX: 0, pupil: 1,
    headNod: -0.15, headTilt: 2,
  }),

  /* Inner brows up and the lids heavy; the gaze drops and the head with it. */
  sad: held('sad', {
    browL: -0.05, browR: -0.1, browInnerL: 0.6, browInnerR: 0.5,
    smile: -0.45, mouthWide: 0.25, mouthOpen: 0, pucker: 0.1, teeth: 0, mouthX: -0.03,
    squint: 0, blinkL: 0.2, blinkR: 0.24, cheeks: 0, jawX: 0, pupil: 0.95,
    lookY: 0.3, headNod: 0.2, headTilt: -1.5,
  }),

  /* Brows raised AND pulled up in the middle, lips pressed: fear's small cousin. */
  worried: held('worried', {
    browL: 0.25, browR: 0.15, browInnerL: 0.5, browInnerR: 0.45,
    smile: -0.2, mouthWide: 0.3, mouthOpen: 0.05, pucker: 0.15, teeth: 0, mouthX: 0.03,
    squint: 0.05, cheeks: 0, jawX: 0, pupil: 1.1,
    lookX: -0.1,
  }),

  /* Brows high, jaw dropped, lips rounded into an O. Pupils open. */
  surprised: held('surprised', {
    browL: 0.8, browR: 0.7, browInnerL: 0.1, browInnerR: 0.05,
    smile: 0, mouthWide: 0.15, mouthOpen: 0.45, pucker: 0.35, teeth: 0, mouthX: 0,
    squint: 0, cheeks: 0, jawX: 0, pupil: 1.2,
    headNod: -0.05,
  }),

  /* Surprise without the pleasantness: wider, mouth corners down, head pulled back. */
  shocked: held('shocked', {
    browL: 1, browR: 0.9, browInnerL: 0.2, browInnerR: 0.15,
    smile: -0.15, mouthWide: 0.25, mouthOpen: 0.8, pucker: 0.2, teeth: 0, mouthX: 0.03,
    squint: 0, cheeks: 0, jawX: 0, pupil: 1.35,
    headNod: -0.15, headTilt: -1,
  }),

  /* Eyes up and away, one brow up, the jaw slid sideways, lips pursed. */
  thinking: held('thinking', {
    browL: 0.15, browR: -0.05, browInnerL: 0.1, browInnerR: 0,
    smile: 0.05, mouthWide: 0.25, mouthOpen: 0, pucker: 0.3, teeth: 0, mouthX: -0.12,
    squint: 0.1, cheeks: 0, jawX: 0.3, pupil: 1,
    lookX: 0.45, lookY: -0.5, headTilt: -3, headNod: -0.08,
  }),

  /* The most asymmetric face here: one brow up, the other down, head cocked. */
  confused: held('confused', {
    browL: 0.35, browR: -0.15, browInnerL: -0.1, browInnerR: 0.2,
    smile: -0.1, mouthWide: 0.3, mouthOpen: 0.08, pucker: 0.1, teeth: 0, mouthX: -0.1,
    squint: 0.2, cheeks: 0, jawX: -0.15, pupil: 1,
    lookX: 0.15, headTilt: 5, headNod: 0.04,
  }),

  /* Brows down and together, lids tight, lip raised off the teeth, chin down so
     the eyes look out from under the brow. */
  angry: held('angry', {
    browL: -0.45, browR: -0.5, browInnerL: -0.8, browInnerR: -0.7,
    smile: -0.3, mouthWide: 0.45, mouthOpen: 0.1, pucker: 0, teeth: 0.6, mouthX: 0.02,
    squint: 0.4, cheeks: 0.1, jawX: 0, pupil: 0.85,
    lookY: -0.1, headNod: 0.12,
  }),

  /* One brow up, the other eye narrowed, mouth pulled to the side. */
  skeptical: held('skeptical', {
    browL: 0.5, browR: -0.2, browInnerL: 0, browInnerR: -0.2,
    smile: -0.05, mouthWide: 0.35, mouthOpen: 0, pucker: 0.15, teeth: 0, mouthX: 0.2,
    squint: 0.3, blinkR: 0.15, cheeks: 0, jawX: 0.05, pupil: 1,
    lookX: 0.1, headTilt: -3, headNod: 0.03,
  }),

  /* Half-closed lids, gaze drifted off to a corner, everything slightly down. */
  bored: held('bored', {
    browL: -0.08, browR: -0.12, browInnerL: 0, browInnerR: 0,
    smile: -0.1, mouthWide: 0.3, mouthOpen: 0, pucker: 0.05, teeth: 0, mouthX: -0.03,
    squint: 0, blinkL: 0.4, blinkR: 0.45, cheeks: 0, jawX: 0, pupil: 1,
    lookX: 0.3, lookY: 0.1, headTilt: 2.5, headNod: 0.05,
  }),

  /* Chin up, lids a touch lowered so the eyes look down the nose, a closed smile. */
  proud: held('proud', {
    browL: 0.1, browR: 0, browInnerL: 0, browInnerR: 0,
    smile: 0.4, mouthWide: 0.35, mouthOpen: 0, pucker: 0.08, teeth: 0, mouthX: 0.04,
    squint: 0.2, blinkL: 0.12, blinkR: 0.1, cheeks: 0.1, jawX: 0, pupil: 1,
    lookY: 0.15, headNod: -0.25, headTilt: 1.5,
  }),

  /* Blush, a pressed little smile, eyes down and away, head dipped and tilted. */
  shy: held('shy', {
    browL: 0.1, browR: 0.2, browInnerL: 0.25, browInnerR: 0.3,
    smile: 0.4, mouthWide: 0.25, mouthOpen: 0, pucker: 0.15, teeth: 0, mouthX: -0.05,
    squint: 0.1, blinkL: 0.1, blinkR: 0.12, cheeks: 0.7, jawX: 0, pupil: 1.05,
    lookX: -0.35, lookY: 0.35, headTilt: 4, headNod: 0.18,
  }),

  /* Surprise and a grin at once: brows up, mouth open on the teeth, pupils wide. */
  excited: held('excited', {
    browL: 0.55, browR: 0.45, browInnerL: 0.1, browInnerR: 0.05,
    smile: 0.8, mouthWide: 0.6, mouthOpen: 0.4, pucker: 0, teeth: 1, mouthX: 0.04,
    squint: 0.1, cheeks: 0.3, jawX: 0, pupil: 1.2,
    headNod: -0.08,
  }),

  /* Attentive: brows a little up, head cocked toward the speaker, mouth closed. */
  listening: held('listening', {
    browL: 0.2, browR: 0.12, browInnerL: 0.05, browInnerR: 0.05,
    smile: 0.2, mouthWide: 0.35, mouthOpen: 0, pucker: 0, teeth: 0, mouthX: 0.02,
    squint: 0.05, cheeks: 0, jawX: 0, pupil: 1.05,
    lookX: 0.05, headTilt: 3.5, headNod: 0.06,
  }),
}

/* ----------------------------------------------------------------------
   Face one-shots
   ---------------------------------------------------------------------- */

/* 90 ms down, 180 ms up. The brows dip a hair with it, as they do. */
const blink = shot('blink', 0.3, {
  ...eyes([[0, 0], [0.09, 1, 'in'], [0.27, 0, 'out']]),
  browL: [[0, 0], [0.09, -0.04, 'in'], [0.27, 0, 'out']],
  browR: [[0, 0], [0.1, -0.03, 'in'], [0.28, 0, 'out']],
}, { in: 0.03, out: 0.05 })

/* The second blink starts before the first has fully opened and is a touch
   quicker, which is how a double blink differs from two blinks. */
const doubleBlink = shot('doubleBlink', 0.56, {
  ...eyes([[0, 0], [0.09, 1, 'in'], [0.25, 0.1, 'out'], [0.33, 1, 'in'], [0.52, 0, 'out']]),
  browL: [[0, 0], [0.09, -0.04, 'in'], [0.52, 0, 'out']],
}, { in: 0.03, out: 0.05 })

/* The screen-left eye closes; the other narrows in sympathy, that cheek
   rises, the mouth pulls toward the wink, the head tips the same way. */
const wink = shot('wink', 0.7, {
  blinkL: [[0, 0], [0.1, 1, 'in'], [0.38, 1], [0.6, 0, 'out']],
  blinkR: [[0, 0], [0.12, 0.15, 'in'], [0.38, 0.15], [0.62, 0, 'out']],
  squint: [[0, 0], [0.14, 0.3, 'out'], [0.4, 0.3], [0.65, 0, 'out']],
  smile: [[0, 0.15], [0.16, 0.5, 'out'], [0.42, 0.5], [0.7, 0.15, 'inOut']],
  mouthX: [[0, 0], [0.16, 0.12, 'out'], [0.42, 0.12], [0.7, 0, 'inOut']],
  browL: [[0, 0], [0.12, -0.15, 'out'], [0.4, -0.15], [0.65, 0, 'out']],
  browR: [[0, 0], [0.12, 0.1, 'out'], [0.4, 0.1], [0.65, 0, 'out']],
  headTilt: [[0, 0], [0.04, -0.5, 'in'], [0.22, 3, 'overshoot'], [0.45, 3], [0.7, 0, 'inOut']],
}, { in: 0.05 })

/* Eyes sweep up and across under half-lowered lids; the head tips back a
   beat later, the brows go up and one stays up: the gesture is contempt
   kept small. */
const eyeRoll = shot('eyeRoll', 1.12, {
  lookX: [[0, 0], [0.15, -0.5, 'out'], [0.45, 0.5, 'inOut'], [0.75, 0.2, 'inOut'], [1.1, 0, 'out']],
  lookY: [[0, 0], [0.15, -0.6, 'out'], [0.45, -0.9, 'inOut'], [0.75, -0.3, 'inOut'], [1.1, 0, 'out']],
  ...eyes([[0, 0], [0.3, 0.35, 'inOut'], [0.75, 0.4], [1.1, 0, 'out']]),
  browL: [[0, 0], [0.3, 0.3, 'out'], [0.8, 0.25], [1.1, 0, 'out']],
  browR: [[0, 0], [0.3, 0.2, 'out'], [0.8, 0.1], [1.05, 0, 'out']],
  headNod: [[0, 0], [0.12, 0], [0.4, -0.12, 'out'], [0.8, -0.1], [1.1, 0, 'inOut']],
  headTilt: [[0, 0], [0.12, 0], [0.45, 3, 'out'], [0.8, 3], [1.1, 0, 'inOut']],
  smile: [[0, 0.15], [0.3, -0.1, 'out'], [0.8, -0.1], [1.1, 0.15, 'inOut']],
  pucker: [[0, 0], [0.3, 0.15, 'out'], [0.8, 0.15], [1.1, 0, 'inOut']],
})

/* A deliberate glance: the eyes jump in 70 ms, the head follows a third of
   the way 100 ms later, both dwell, then the return is slow. */
const lookLeft = shot('lookLeft', 1, {
  lookX: [[0, 0], [0.07, -1, 'out'], [0.55, -0.9], [0.95, 0, 'inOut']],
  headTurn: [[0, 0], [0.1, 0], [0.32, -0.35, 'out'], [0.6, -0.35], [1, 0, 'inOut']],
})
const lookRight = mirror(lookLeft, 'lookRight')

/* Looking up lifts the brows and tips the chin; looking down drops the lids
   with the gaze, because the upper lid follows the eye. */
const lookUp = shot('lookUp', 1, {
  lookY: [[0, 0], [0.07, -1, 'out'], [0.55, -0.9], [0.95, 0, 'inOut']],
  headNod: [[0, 0], [0.1, 0], [0.32, -0.25, 'out'], [0.6, -0.25], [1, 0, 'inOut']],
  browL: [[0, 0], [0.12, 0], [0.34, 0.25, 'out'], [0.6, 0.25], [1, 0, 'inOut']],
  browR: [[0, 0], [0.12, 0], [0.34, 0.18, 'out'], [0.6, 0.18], [1, 0, 'inOut']],
})
const lookDown = shot('lookDown', 1, {
  lookY: [[0, 0], [0.07, 1, 'out'], [0.55, 0.9], [0.95, 0, 'inOut']],
  headNod: [[0, 0], [0.1, 0], [0.32, 0.3, 'out'], [0.6, 0.3], [1, 0, 'inOut']],
  ...eyes([[0, 0], [0.1, 0.22, 'out'], [0.6, 0.22], [0.95, 0, 'inOut']]),
  browL: [[0, 0], [0.12, 0], [0.34, -0.08, 'out'], [0.6, -0.08], [1, 0, 'inOut']],
})

/* Both brows up and held for a beat; the lips part a little, the chin lifts. */
const browRaise = shot('browRaise', 0.92, {
  browL: [[0, 0], [0.18, 0.75, 'out'], [0.6, 0.7], [0.9, 0, 'inOut']],
  browR: [[0, 0], [0.2, 0.65, 'out'], [0.6, 0.6], [0.92, 0, 'inOut']],
  mouthOpen: [[0, 0], [0.2, 0.06, 'out'], [0.6, 0.06], [0.9, 0, 'inOut']],
  headNod: [[0, 0], [0.2, -0.06, 'out'], [0.6, -0.06], [0.9, 0, 'inOut']],
})

/* The greeting flash: up in 80 ms, back down by a sixth of a second, with
   a chin lift and a flicker of a smile. Fast on purpose; slowed down it
   becomes a question. */
const browFlash = shot('browFlash', 0.22, {
  browL: [[0, 0], [0.08, 0.85, 'out'], [0.17, 0.05, 'inOut'], [0.22, 0, 'out']],
  browR: [[0, 0], [0.085, 0.75, 'out'], [0.18, 0.05, 'inOut'], [0.22, 0, 'out']],
  headNod: [[0, 0], [0.09, -0.08, 'out'], [0.22, 0, 'inOut']],
  smile: [[0, 0.15], [0.1, 0.35, 'out'], [0.22, 0.15, 'inOut']],
}, { in: 0.03, out: 0.1 })

/* A smile builds over half a second: one corner moves first so the mouth
   slides a few px before it centres, then the lower lids and the cheeks
   join 100 ms behind the corners. That delay is what makes it felt. */
const smileBuild = shot('smileBuild', 1.65, {
  smile: [[0, 0.15], [0.5, 0.7, 'out'], [1.2, 0.7], [1.6, 0.15, 'inOut']],
  mouthWide: [[0, 0.35], [0.5, 0.55, 'out'], [1.2, 0.55], [1.6, 0.35, 'inOut']],
  mouthOpen: [[0, 0], [0.5, 0.1, 'out'], [1.2, 0.1], [1.6, 0, 'inOut']],
  mouthX: [[0, 0], [0.25, 0.08, 'out'], [0.5, 0.03, 'inOut'], [1.2, 0.03], [1.6, 0, 'inOut']],
  squint: [[0, 0], [0.1, 0], [0.6, 0.25, 'out'], [1.2, 0.25], [1.6, 0, 'inOut']],
  cheeks: [[0, 0], [0.1, 0], [0.6, 0.3, 'out'], [1.2, 0.3], [1.65, 0, 'inOut']],
  browL: [[0, 0], [0.4, 0.1, 'out'], [1.2, 0.1], [1.6, 0, 'inOut']],
  browR: [[0, 0], [0.42, 0.04, 'out'], [1.2, 0.04], [1.6, 0, 'inOut']],
})

/* One corner only. The brow on that side goes up, the head tips the other
   way, and the chin lifts a touch: knowing, not warm. */
const smirk = shot('smirk', 1.4, {
  smile: [[0, 0.15], [0.3, 0.35, 'out'], [1, 0.35], [1.4, 0.15, 'inOut']],
  mouthX: [[0, 0], [0.3, 0.25, 'overshoot'], [1, 0.25], [1.4, 0, 'inOut']],
  mouthWide: [[0, 0.35], [0.3, 0.3, 'out'], [1, 0.3], [1.4, 0.35, 'inOut']],
  squint: [[0, 0], [0.36, 0.15, 'out'], [1, 0.15], [1.4, 0, 'inOut']],
  browL: [[0, 0], [0.28, 0.3, 'out'], [1, 0.3], [1.4, 0, 'inOut']],
  browR: [[0, 0], [0.3, -0.05, 'out'], [1, -0.05], [1.4, 0, 'inOut']],
  headTilt: [[0, 0], [0.05, 0.4, 'in'], [0.34, -2, 'overshoot'], [1, -2], [1.4, 0, 'inOut']],
  headNod: [[0, 0], [0.34, -0.05, 'out'], [1, -0.05], [1.4, 0, 'inOut']],
})

/* Upper teeth over the lower lip, inner brows up, eyes slid away: the face
   of someone who is not sure they should have said that. */
const lipBite = shot('lipBite', 1.4, {
  mouthOpen: [[0, 0], [0.22, 0.1, 'out'], [1, 0.1], [1.4, 0, 'inOut']],
  teeth: [[0, 0], [0.22, 1, 'out'], [1, 1], [1.4, 0, 'inOut']],
  pucker: [[0, 0], [0.22, 0.2, 'out'], [1, 0.2], [1.4, 0, 'inOut']],
  mouthWide: [[0, 0.35], [0.22, 0.3, 'out'], [1, 0.3], [1.4, 0.35, 'inOut']],
  smile: [[0, 0.15], [0.22, 0.05, 'out'], [1, 0.05], [1.4, 0.15, 'inOut']],
  mouthX: [[0, 0], [0.22, 0.08, 'out'], [1, 0.08], [1.4, 0, 'inOut']],
  browInnerL: [[0, 0], [0.3, 0.25, 'out'], [1, 0.25], [1.4, 0, 'inOut']],
  browInnerR: [[0, 0], [0.32, 0.3, 'out'], [1, 0.3], [1.4, 0, 'inOut']],
  browL: [[0, 0], [0.3, 0.12, 'out'], [1, 0.12], [1.4, 0, 'inOut']],
  lookX: [[0, 0], [0.12, 0.3, 'out'], [1, 0.3], [1.35, 0, 'inOut']],
  lookY: [[0, 0], [0.12, 0.2, 'out'], [1, 0.2], [1.35, 0, 'inOut']],
  headTilt: [[0, 0], [0.3, 2.5, 'out'], [1, 2.5], [1.4, 0, 'inOut']],
})

/* A sharp intake: the jaw drops and the lips round in 80 ms, brows shoot up,
   pupils open, the head pulls back, and the chest fills (breathe is
   additive, so this stacks on the idle breath). */
const gasp = shot('gasp', 0.92, {
  mouthOpen: [[0, 0], [0.08, 0.6, 'out'], [0.45, 0.5], [0.9, 0, 'inOut']],
  pucker: [[0, 0], [0.08, 0.4, 'out'], [0.45, 0.35], [0.9, 0, 'inOut']],
  mouthWide: [[0, 0.35], [0.08, 0.15, 'out'], [0.45, 0.15], [0.9, 0.35, 'inOut']],
  smile: [[0, 0.15], [0.08, 0, 'out'], [0.45, 0], [0.9, 0.15, 'inOut']],
  browL: [[0, 0], [0.08, 0.9, 'out'], [0.45, 0.8], [0.9, 0, 'inOut']],
  browR: [[0, 0], [0.09, 0.8, 'out'], [0.45, 0.7], [0.92, 0, 'inOut']],
  pupil: [[0, 1], [0.1, 1.3, 'out'], [0.5, 1.25], [0.9, 1, 'inOut']],
  breathe: [[0, 0], [0.1, 0.8, 'out'], [0.5, 0.7], [0.9, 0, 'in']],
  headNod: [[0, 0], [0.1, -0.2, 'out'], [0.5, -0.15], [0.9, 0, 'inOut']],
}, { in: 0.04 })

/* A sigh: a slow fill, a held beat, then the chest drops, the shoulders
   drop with it (headY, additive) and the brows and lids come down on the
   exhale through parted lips. The gaze ends slightly down. */
const sigh = shot('sigh', 2.2, {
  breathe: [[0, 0], [0.7, 0.9, 'inOut'], [1, 0.9], [1.6, -0.2, 'out'], [2.2, 0, 'inOut']],
  headY: [[0, 0], [0.7, -2, 'inOut'], [1, -2], [1.6, 4, 'out'], [2.2, 0, 'inOut']],
  browL: [[0, 0], [0.7, 0.25, 'inOut'], [1, 0.25], [1.6, -0.2, 'out'], [2.2, 0, 'inOut']],
  browR: [[0, 0], [0.72, 0.18, 'inOut'], [1, 0.18], [1.62, -0.15, 'out'], [2.2, 0, 'inOut']],
  browInnerL: [[0, 0], [1, 0], [1.6, 0.2, 'out'], [2.2, 0, 'inOut']],
  browInnerR: [[0, 0], [1, 0], [1.6, 0.25, 'out'], [2.2, 0, 'inOut']],
  ...eyes([[0, 0], [0.9, 0.1, 'inOut'], [1.2, 0.8, 'inOut'], [1.5, 0.8], [1.9, 0, 'out']]),
  mouthOpen: [[0, 0], [0.9, 0.05, 'inOut'], [1.1, 0.3, 'out'], [1.6, 0.15, 'inOut'], [2.2, 0, 'inOut']],
  pucker: [[0, 0], [0.9, 0], [1.1, 0.3, 'out'], [1.6, 0.2, 'inOut'], [2.2, 0, 'inOut']],
  smile: [[0, 0.15], [1, 0.1, 'inOut'], [1.6, -0.1, 'out'], [2.2, 0.15, 'inOut']],
  headNod: [[0, 0], [0.7, -0.05, 'inOut'], [1, -0.05], [1.6, 0.2, 'out'], [2.2, 0.05, 'inOut']],
  lookY: [[0, 0], [1.2, 0], [1.7, 0.3, 'out'], [2.2, 0.1, 'inOut']],
})

/* 2.4 s. The jaw drops slowly and the lips round; the eyes squeeze shut
   as it peaks, the brows go up then knit, the head tips back and comes
   forward again on the way out. One deep breath under all of it. */
const yawn = shot('yawn', 2.4, {
  mouthOpen: [[0, 0], [0.9, 0.95, 'inOut'], [1.5, 0.95], [2.4, 0, 'inOut']],
  mouthWide: [[0, 0.35], [0.9, 0.2, 'inOut'], [1.5, 0.2], [2.4, 0.35, 'inOut']],
  pucker: [[0, 0], [0.9, 0.35, 'inOut'], [1.5, 0.35], [2.4, 0, 'inOut']],
  smile: [[0, 0.15], [0.9, 0, 'inOut'], [1.5, 0], [2.4, 0.15, 'inOut']],
  mouthX: [[0, 0], [0.9, 0.03, 'inOut'], [2.4, 0, 'inOut']],
  teeth: [[0, 0], [0.9, 0.3, 'inOut'], [1.5, 0.3], [2.4, 0, 'inOut']],
  tongue: [[0, 0], [0.9, 0.2, 'inOut'], [1.5, 0.2], [2.4, 0, 'inOut']],
  blinkL: [[0, 0], [0.3, 0.1, 'inOut'], [1, 0.85, 'inOut'], [1.6, 0.9], [2.3, 0, 'out']],
  blinkR: [[0, 0], [0.3, 0.12, 'inOut'], [1.05, 0.9, 'inOut'], [1.6, 0.95], [2.32, 0, 'out']],
  squint: [[0, 0], [1, 0.6, 'inOut'], [1.6, 0.6], [2.3, 0, 'out']],
  browL: [[0, 0], [0.5, 0.4, 'inOut'], [1.2, -0.1, 'inOut'], [1.6, -0.1], [2.4, 0, 'inOut']],
  browR: [[0, 0], [0.52, 0.32, 'inOut'], [1.22, -0.14, 'inOut'], [1.6, -0.14], [2.4, 0, 'inOut']],
  browInnerL: [[0, 0], [1.2, 0.3, 'inOut'], [1.6, 0.3], [2.4, 0, 'inOut']],
  browInnerR: [[0, 0], [1.2, 0.25, 'inOut'], [1.6, 0.25], [2.4, 0, 'inOut']],
  headNod: [[0, 0], [1, -0.3, 'inOut'], [1.5, -0.3], [2.2, 0.1, 'inOut'], [2.4, 0, 'out']],
  headTilt: [[0, 0], [1, 2, 'inOut'], [1.6, 2], [2.4, 0, 'inOut']],
  breathe: [[0, 0], [1.1, 1, 'inOut'], [1.5, 1], [2.3, 0, 'out']],
})

/* Laughter is pulses: the head tips back and bobs, the jaw and the chest
   pump at about five a second ("ha ha ha"), eyes crinkled nearly shut by
   the cheeks, then it all fades out together. bodyY is additive, so the
   little bounces stack on whatever the body is doing. */
const laughBurst = shot('laughBurst', 1.8, {
  headNod: [[0, 0], [0.1, 0.08, 'in'], [0.3, -0.3, 'out'], [0.5, -0.15, 'inOut'], [0.68, -0.3, 'inOut'], [0.86, -0.12, 'inOut'], [1.04, -0.25, 'inOut'], [1.4, -0.05, 'inOut'], [1.8, 0, 'out']],
  headTilt: [[0, 0], [0.3, 3, 'out'], [1.3, 3], [1.8, 0, 'inOut']],
  mouthOpen: [[0, 0], [0.1, 0.1, 'in'], [0.25, 0.7, 'out'], [0.38, 0.4, 'inOut'], [0.5, 0.75, 'inOut'], [0.63, 0.45, 'inOut'], [0.75, 0.7, 'inOut'], [0.88, 0.4, 'inOut'], [1, 0.6, 'inOut'], [1.15, 0.3, 'inOut'], [1.4, 0.15, 'inOut'], [1.8, 0, 'out']],
  breathe: [[0, 0], [0.25, 0.6, 'out'], [0.38, 0.2, 'inOut'], [0.5, 0.6, 'inOut'], [0.63, 0.2, 'inOut'], [0.75, 0.5, 'inOut'], [0.88, 0.2, 'inOut'], [1, 0.4, 'inOut'], [1.15, 0.1, 'inOut'], [1.8, 0, 'out']],
  bodyY: [[0, 0], [0.25, -3, 'out'], [0.38, 0, 'inOut'], [0.5, -3, 'inOut'], [0.63, 0, 'inOut'], [0.75, -2.5, 'inOut'], [0.88, 0, 'inOut'], [1, -2, 'inOut'], [1.15, 0, 'inOut'], [1.8, 0]],
  smile: [[0, 0.15], [0.25, 0.9, 'out'], [1.3, 0.9], [1.8, 0.3, 'inOut']],
  mouthWide: [[0, 0.35], [0.25, 0.65, 'out'], [1.3, 0.65], [1.8, 0.4, 'inOut']],
  mouthX: [[0, 0], [0.25, 0.04, 'out'], [1.8, 0, 'inOut']],
  teeth: [[0, 0], [0.2, 1, 'out'], [1.4, 1], [1.8, 0, 'inOut']],
  squint: [[0, 0], [0.3, 0.65, 'out'], [1.3, 0.65], [1.8, 0, 'inOut']],
  ...eyes([[0, 0], [0.3, 0.5, 'out'], [1.3, 0.5], [1.75, 0, 'inOut']]),
  cheeks: [[0, 0], [0.35, 0.4, 'out'], [1.4, 0.4], [1.8, 0, 'inOut']],
  browL: [[0, 0], [0.25, 0.3, 'out'], [1.3, 0.3], [1.8, 0, 'inOut']],
  browR: [[0, 0], [0.27, 0.22, 'out'], [1.3, 0.22], [1.8, 0, 'inOut']],
})

export const FACE_ACTIONS: Record<string, Action> = {
  blink, doubleBlink, wink, eyeRoll,
  lookLeft, lookRight, lookUp, lookDown,
  browRaise, browFlash, smileBuild, smirk, lipBite,
  gasp, sigh, yawn, laughBurst,
}
