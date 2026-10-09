/* Head actions: the yeses, the noes, the tilts and the turns.
 *
 * Every one follows the same order of events a real head does: the eyes go
 * first, the head follows a few frames later, the shoulders (twist, lean) a
 * few frames after that. A move winds up a little the other way before it
 * goes, overshoots into its hold, drifts while it holds, and returns with a
 * slow-out. The face joins in: a nod warms the smile, a shake tightens the
 * mouth, a curious tilt lifts the brows.
 *
 * Keys are [time, value, ease-into-this-key]; omitted ease is inOut. */
import type { Action, Key, Tracks } from '../rig/track'
import { mirror } from '../rig/track'

const head = (name: string, duration: number, tracks: Tracks, extra: Partial<Action> = {}): Action => ({
  name,
  duration,
  group: 'head',
  tracks,
  ...extra,
})

/** The same beats with every value multiplied, for a channel that follows
    another in lockstep (a tilt countering a turn, pupils opposing the head). */
const follow = (keys: Key[], factor: number): Key[] => keys.map(([t, v, e]) => [t, v * factor, e])

/* The shake's turn beats, shared by three channels below. Full amplitude
   on the first two cycles, then it dies down: a real no does not stop dead. */
const SHAKE_TURN: Key[] = [
  [0, 0],
  [0.06, 0.08, 'out'], // the wind-up, a touch the wrong way
  [0.2, -0.35],
  [0.37, 0.35],
  [0.53, -0.35],
  [0.7, 0.35],
  [0.87, -0.28],
  [1.03, 0.16],
  [1.3, 0, 'out'],
]

export const HEAD_ACTIONS: Record<string, Action> = {
  /* A yes. Two small nods at 2.6 Hz, biased downward: the chin drops 0.35
     and barely rises past level. The eyes drop a beat ahead of the head and
     a blink lands on the second nod, which is where people blink. */
  nod: head('nod', 1.0, {
    headNod: [[0, 0], [0.08, -0.06, 'out'], [0.27, 0.35], [0.46, -0.05], [0.65, 0.3], [1.0, 0, 'out']],
    lookY: [[0, 0], [0.2, 0.25, 'out'], [0.4, 0.05], [0.58, 0.22], [0.85, 0, 'out']],
    lean: [[0, 0], [0.32, 1.2], [0.7, 0.9], [1.0, 0, 'out']],
    smile: [[0, 0.15], [0.4, 0.3, 'out'], [1.0, 0.15, 'out']],
    blinkL: [[0.6, 0], [0.64, 1, 'out'], [0.74, 0]],
    blinkR: [[0.615, 0], [0.655, 1, 'out'], [0.755, 0]],
  }),

  /* One deep, considered nod: a chin-lift first, a long drop with overshoot,
     a hold that keeps settling, and a slow return. The brows come down a
     touch as it lands, the way agreement looks when it is thought about. */
  nodSlow: head('nodSlow', 1.1, {
    headNod: [[0, 0], [0.12, -0.1, 'out'], [0.45, 0.6, 'overshoot'], [0.68, 0.55], [1.1, 0, 'out']],
    lookY: [[0, 0], [0.06, -0.05, 'out'], [0.34, 0.35, 'out'], [0.62, 0.3], [0.9, 0, 'out']],
    lean: [[0, 0], [0.5, 2], [0.75, 1.8], [1.1, 0, 'out']],
    browL: [[0, 0], [0.5, -0.15, 'out'], [1.1, 0, 'out']],
    browR: [[0, 0], [0.5, -0.1, 'out'], [1.1, 0, 'out']],
    smile: [[0, 0.15], [0.55, 0.28, 'out'], [1.1, 0.15, 'out']],
    blinkL: [[0.4, 0], [0.45, 1, 'out'], [0.6, 0]],
    blinkR: [[0.415, 0], [0.465, 1, 'out'], [0.615, 0]],
  }),

  /* A no. Three cycles of yaw at about 3 Hz. The head rolls 2 degrees
     against each turn, and the pupils swing the other way so the eyes stay
     on the viewer while the head moves under them. The mouth closes and
     pulls in; the brows drop a little. */
  shake: head('shake', 1.3, {
    headTurn: SHAKE_TURN,
    headTilt: follow(SHAKE_TURN, -2 / 0.35),
    lookX: follow(SHAKE_TURN, -0.3 / 0.35),
    browL: [[0, 0], [0.25, -0.2, 'out'], [1.0, -0.15], [1.3, 0, 'out']],
    browR: [[0, 0], [0.25, -0.15, 'out'], [1.0, -0.1], [1.3, 0, 'out']],
    browInnerL: [[0, 0], [0.3, -0.12, 'out'], [1.3, 0, 'out']],
    browInnerR: [[0, 0], [0.3, -0.1, 'out'], [1.3, 0, 'out']],
    smile: [[0, 0.15], [0.3, 0.02, 'out'], [1.3, 0.15, 'out']],
    pucker: [[0, 0], [0.3, 0.15, 'out'], [1.3, 0, 'out']],
  }),

  /* A plain tilt to the viewer's right. The eyes flick that way first, the
     head rolls after them and turns a hair in the same direction, since a
     tilt is never a pure roll. One brow lifts more than the other. */
  tilt: head('tilt', 1.2, {
    headTilt: [[0, 0], [0.1, -1.5, 'out'], [0.42, 10, 'overshoot'], [0.8, 9.4], [1.2, 0, 'out']],
    lookX: [[0, 0], [0.06, 0.2, 'out'], [0.5, 0.08], [0.95, 0, 'out']],
    headTurn: [[0, 0], [0.45, 0.08], [1.2, 0, 'out']],
    browL: [[0, 0], [0.4, 0.15, 'out'], [1.2, 0, 'out']],
    browR: [[0, 0], [0.4, 0.05, 'out'], [1.2, 0, 'out']],
    smile: [[0, 0.15], [0.45, 0.25, 'out'], [1.2, 0.15, 'out']],
  }),

  /* The puzzled tilt. Brows go up first (brows are the fastest thing on a
     face), eyes flick toward the tilt side, then the head rolls 12 degrees
     with overshoot and the mouth parts. The brows stay up through the hold
     and are the last thing to settle on the way back. */
  tiltCurious: head('tiltCurious', 1.2, {
    browL: [[0, 0], [0.16, 0.5, 'out'], [0.75, 0.45], [0.9, 0.42], [1.2, 0, 'out']],
    browR: [[0, 0], [0.17, 0.42, 'out'], [0.75, 0.38], [0.9, 0.36], [1.2, 0, 'out']],
    squint: [[0, 0], [0.16, 0, 'out'], [1.2, 0]],
    lookX: [[0, 0], [0.05, 0.25, 'out'], [0.45, 0.1], [0.85, 0, 'out']],
    headTilt: [[0, 0], [0.1, -1.5, 'out'], [0.45, 12, 'overshoot'], [0.75, 11.3], [1.2, 0, 'out']],
    headNod: [[0, 0], [0.12, 0.03, 'out'], [0.5, -0.08], [1.2, 0, 'out']],
    headTurn: [[0, 0], [0.5, 0.1], [1.2, 0, 'out']],
    mouthOpen: [[0, 0], [0.4, 0.12, 'out'], [0.8, 0.1], [1.2, 0, 'out']],
    smile: [[0, 0.15], [0.4, 0.08, 'out'], [1.2, 0.15, 'out']],
  }),

  /* A turn to the viewer's left. The eyes get there in 80 ms; the head sets
     off as they arrive and takes 350 ms; the shoulders slide 120 ms after
     the head. Once the head arrives the pupils relax back toward centre,
     because the eyes no longer need to hold the angle alone. Coming back,
     the eyes flick to the viewer first and the head follows them home. */
  turnLeft: head('turnLeft', 1.4, {
    lookX: [[0, 0], [0.08, -0.6, 'out'], [0.44, -0.25], [0.9, -0.2], [0.98, 0.3, 'out'], [1.4, 0, 'out']],
    headTurn: [[0, 0], [0.08, 0.05, 'out'], [0.44, -0.6, 'overshoot'], [0.85, -0.56], [1.4, 0, 'out']],
    headTilt: [[0, 0], [0.48, 2.5], [1.4, 0, 'out']],
    twist: [[0, 0], [0.2, 0], [0.58, -6, 'overshoot'], [0.9, -5.6], [1.4, 0, 'out']],
    lean: [[0, 0], [0.22, 0], [0.62, -1.5], [1.4, 0, 'out']],
    browL: [[0, 0], [0.4, 0.1, 'out'], [1.4, 0, 'out']],
    browR: [[0, 0], [0.4, 0.06, 'out'], [1.4, 0, 'out']],
  }),

  /* Eyes go up and to the side, the head lifts after them and rolls a
     little, the brows rise with the inner ends up, the mouth purses and the
     jaw shifts. Mid-hold the eyes make one more small jump, which is what a
     searching gaze does. The eyes come home before the head does. */
  lookUpThink: head('lookUpThink', 1.8, {
    lookX: [[0, 0], [0.08, 0.45, 'out'], [0.7, 0.45], [0.78, 0.55, 'out'], [1.2, 0.5], [1.45, 0, 'out']],
    lookY: [[0, 0], [0.08, -0.7, 'out'], [1.3, -0.65], [1.45, 0, 'out']],
    headNod: [[0, 0], [0.1, 0.04, 'out'], [0.45, -0.3, 'overshoot'], [1.3, -0.27], [1.8, 0, 'out']],
    headTilt: [[0, 0], [0.5, 4], [1.8, 0, 'out']],
    headTurn: [[0, 0], [0.5, 0.15], [1.8, 0, 'out']],
    browL: [[0, 0], [0.3, 0.3, 'out'], [1.8, 0, 'out']],
    browR: [[0, 0], [0.3, 0.22, 'out'], [1.8, 0, 'out']],
    browInnerL: [[0, 0], [0.3, 0.2, 'out'], [1.8, 0, 'out']],
    browInnerR: [[0, 0], [0.3, 0.2, 'out'], [1.8, 0, 'out']],
    pucker: [[0, 0], [0.4, 0.3, 'out'], [1.8, 0, 'out']],
    jawX: [[0, 0], [0.5, 0.4], [1.1, 0.3], [1.8, 0, 'out']],
    smile: [[0, 0.15], [0.4, 0.05, 'out'], [1.8, 0.15, 'out']],
  }),

  /* Chin up: a small dip first, then the head goes back and lifts, the
     chest rises with it, the lids narrow and one corner of the mouth
     lifts. The pupils look down to keep the viewer as the head goes back. */
  chinUp: head('chinUp', 1.2, {
    headNod: [[0, 0], [0.1, 0.06, 'out'], [0.4, -0.35, 'overshoot'], [0.8, -0.32], [1.2, 0, 'out']],
    headY: [[0, 0], [0.42, -3], [1.2, 0, 'out']],
    lookY: [[0, 0], [0.06, -0.1, 'out'], [0.4, 0.3, 'out'], [0.8, 0.28], [1.1, 0, 'out']],
    squint: [[0, 0], [0.4, 0.25, 'out'], [1.2, 0, 'out']],
    browL: [[0, 0], [0.4, -0.1, 'out'], [1.2, 0, 'out']],
    browR: [[0, 0], [0.4, -0.05, 'out'], [1.2, 0, 'out']],
    smile: [[0, 0.15], [0.45, 0.3, 'out'], [1.2, 0.15, 'out']],
    mouthX: [[0, 0], [0.45, 0.1, 'out'], [1.2, 0, 'out']],
    bodyScale: [[0, 1], [0.45, 1.01], [1.2, 1, 'out']],
  }),

  /* Nodding to music, 120 bpm, four beats per pass. The head drops on the
     beat and floats up between beats; the roll swings every two beats,
     the shoulders and body follow a touch late, and a blink lands on beat
     three. Loops, so the first and last keys agree. */
  headBob: head(
    'headBob',
    2.0,
    {
      headNod: [[0, -0.08], [0.18, 0.2, 'out'], [0.5, -0.08], [0.68, 0.2, 'out'], [1.0, -0.08], [1.18, 0.2, 'out'], [1.5, -0.08], [1.68, 0.2, 'out'], [2.0, -0.08]],
      headTilt: [[0, 3], [1.0, -3], [2.0, 3]],
      twist: [[0, 2], [1.05, -2], [2.0, 2]],
      bodyY: [[0, 0], [0.22, 2, 'out'], [0.5, 0], [0.72, 2, 'out'], [1.0, 0], [1.22, 2, 'out'], [1.5, 0], [1.72, 2, 'out'], [2.0, 0]],
      lookX: [[0, 0.1], [1.0, -0.1], [2.0, 0.1]],
      smile: [[0, 0.35], [2.0, 0.35]],
      blinkL: [[0.95, 0], [1.0, 1, 'out'], [1.14, 0]],
      blinkR: [[0.965, 0], [1.015, 1, 'out'], [1.155, 0]],
    },
    { loop: true },
  ),
}

/* turnRight is turnLeft in a mirror: yaw, roll, gaze, twist and lean flip. */
HEAD_ACTIONS.turnRight = mirror(HEAD_ACTIONS.turnLeft, 'turnRight')
