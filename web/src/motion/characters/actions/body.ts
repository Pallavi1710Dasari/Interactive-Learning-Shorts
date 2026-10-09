/* Body actions: the whole figure moving. Bounces and jumps, leans, a bow,
 * the loops that keep a body alive on a long slide, and a celebration.
 *
 * The order of events is the one a body keeps: knees before the rise, the
 * body before the arms, the arms before the hands, the eyes before the head
 * before the shoulders before the hips. A jump crouches first and squashes
 * on landing; a lean settles; a bow drops the eyes and raises them before
 * the head comes up. The face joins every one of them.
 *
 * Hands are keyed straight into the finger channels from HAND_POSES, with
 * each finger arriving a few ms after the last so a fist closes like a fist.
 * Keys are [time, value, ease-into-this-key]; omitted ease is inOut. */
import type { Action, Ease, Key, Tracks } from '../rig/track'
import { mirror } from '../rig/track'
import { HAND_POSES, handChannel } from './handPoses'
import type { HandPose, HandPoseName } from './handPoses'

const body = (name: string, duration: number, tracks: Tracks, extra: Partial<Action> = {}): Action => ({
  name,
  duration,
  group: 'body',
  tracks,
  ...extra,
})

const HAND_FIELDS: (keyof HandPose)[] = ['f1', 'f2', 'f3', 'f4', 'thumb', 'spread', 'palm']

/** One hand moving through named poses over time: every finger channel gets
    the same beats, staggered 12 ms per finger so the hand never snaps. The
    last step lands exactly on time so no key runs past the action's end. */
function hand(side: 'L' | 'R', steps: [number, HandPoseName, Ease?][]): Tracks {
  const out: Tracks = {}
  const last = steps.length - 1
  HAND_FIELDS.forEach((f, i) => {
    out[handChannel(side, f)] = steps.map(([t, name, e], s): Key => [s === last ? t : t + i * 0.012, HAND_POSES[name][f], e])
  })
  return out
}

export const BODY_ACTIONS: Record<string, Action> = {
  /* One happy hop. Knees dip, the body rises 22 px and stretches a hair,
     lands with a squash and settles. Arms swing up 60 ms behind the body,
     the head lags the same way: up at the top, down on the landing. */
  bounce: body('bounce', 0.9, {
    kneeL: [[0, 0], [0.16, 0.35], [0.38, 0, 'out'], [0.6, 0.3, 'in'], [0.9, 0, 'out']],
    kneeR: [[0, 0], [0.17, 0.32], [0.39, 0, 'out'], [0.61, 0.28, 'in'], [0.9, 0, 'out']],
    bodyY: [[0, 0], [0.16, 5], [0.4, -22, 'out'], [0.6, 2, 'in'], [0.72, -1], [0.9, 0, 'out']],
    bodyScale: [[0, 1], [0.16, 0.99], [0.4, 1.015, 'out'], [0.62, 1.03, 'in'], [0.9, 1, 'out']],
    shoulderL: [[0, 8], [0.2, 4], [0.46, 20, 'out'], [0.68, 10], [0.9, 8, 'out']],
    shoulderR: [[0, 8], [0.21, 5], [0.47, 18, 'out'], [0.69, 10], [0.9, 8, 'out']],
    elbowL: [[0, 6], [0.22, 5], [0.48, 14, 'out'], [0.9, 6, 'out']],
    elbowR: [[0, 6], [0.23, 5], [0.49, 13, 'out'], [0.9, 6, 'out']],
    headNod: [[0, 0], [0.2, 0.08], [0.46, -0.12, 'out'], [0.66, 0.14, 'in'], [0.9, 0, 'out']],
    browL: [[0, 0], [0.4, 0.3, 'out'], [0.9, 0, 'out']],
    browR: [[0, 0], [0.4, 0.25, 'out'], [0.9, 0, 'out']],
    smile: [[0, 0.15], [0.4, 0.45, 'out'], [0.9, 0.15, 'out']],
    mouthOpen: [[0, 0], [0.4, 0.1, 'out'], [0.9, 0, 'out']],
  }),

  /* A jump for joy. A real crouch with the knees, then 40 px of air with
     the arms thrown up a beat behind the body and the hands opening a beat
     behind the arms. The face looks up and opens. Lands with a squash, the
     arms float down last with a slow-out. */
  jumpJoy: body('jumpJoy', 1.4, {
    kneeL: [[0, 0], [0.22, 0.55], [0.44, 0, 'out'], [0.78, 0], [0.84, 0.4, 'in'], [1.2, 0, 'out']],
    kneeR: [[0, 0], [0.23, 0.5], [0.45, 0, 'out'], [0.79, 0], [0.85, 0.38, 'in'], [1.2, 0, 'out']],
    bodyY: [[0, 0], [0.22, 8, 'in'], [0.5, -40, 'out'], [0.78, 0, 'in'], [0.84, 4, 'out'], [1.1, 0, 'out']],
    bodyScale: [[0, 1], [0.22, 0.985], [0.5, 1.02, 'out'], [0.78, 1], [0.84, 1.03, 'out'], [1.15, 1, 'out']],
    shoulderL: [[0, 8], [0.24, 2], [0.56, 150, 'overshoot'], [0.9, 146], [1.4, 8, 'out']],
    shoulderR: [[0, 8], [0.26, 3], [0.6, 155, 'overshoot'], [0.92, 150], [1.4, 8, 'out']],
    elbowL: [[0, 6], [0.28, 12], [0.6, 20, 'overshoot'], [1.4, 6, 'out']],
    elbowR: [[0, 6], [0.3, 12], [0.64, 18, 'overshoot'], [1.4, 6, 'out']],
    ...hand('L', [[0.2, 'relaxed'], [0.62, 'open', 'out'], [1.1, 'open'], [1.4, 'relaxed', 'out']]),
    ...hand('R', [[0.2, 'relaxed'], [0.66, 'open', 'out'], [1.1, 'open'], [1.4, 'relaxed', 'out']]),
    headNod: [[0, 0], [0.22, 0.12], [0.52, -0.22, 'out'], [0.84, 0.1, 'in'], [1.0, -0.05], [1.4, 0, 'out']],
    browL: [[0, 0], [0.45, 0.6, 'out'], [1.1, 0.5], [1.4, 0, 'out']],
    browR: [[0, 0], [0.45, 0.5, 'out'], [1.1, 0.42], [1.4, 0, 'out']],
    smile: [[0, 0.15], [0.45, 0.7, 'out'], [1.1, 0.6], [1.4, 0.3, 'out']],
    mouthOpen: [[0, 0], [0.48, 0.5, 'out'], [0.9, 0.35], [1.4, 0, 'out']],
    mouthWide: [[0, 0.35], [0.48, 0.6, 'out'], [1.4, 0.35, 'out']],
    teeth: [[0, 0], [0.48, 1, 'out'], [1.4, 0, 'out']],
    blinkL: [[0.74, 0], [0.78, 1, 'out'], [0.9, 0]],
    blinkR: [[0.755, 0], [0.795, 1, 'out'], [0.905, 0]],
  }),

  /* Leaning toward the viewer. A hair of settle back first, then the torso
     bends a little and the figure grows 4 percent (closer to the camera).
     The chin holds against the bow so the eyes stay level on the viewer.
     Brows up, lids a touch narrowed: attention, not threat. */
  leanIn: body('leanIn', 1.2, {
    bodyScale: [[0, 1], [0.1, 0.995, 'out'], [0.5, 1.04, 'overshoot'], [0.85, 1.038], [1.2, 1, 'out']],
    bow: [[0, 0], [0.12, 0], [0.45, 0.2, 'overshoot'], [0.85, 0.19], [1.2, 0, 'out']],
    headNod: [[0, 0], [0.08, -0.04, 'out'], [0.48, -0.14], [1.2, 0, 'out']],
    lookY: [[0, 0], [0.06, -0.08, 'out'], [0.5, 0], [1.2, 0]],
    twist: [[0, 0], [0.2, 0], [0.55, 3], [1.2, 0, 'out']],
    browL: [[0, 0], [0.35, 0.3, 'out'], [1.2, 0, 'out']],
    browR: [[0, 0], [0.35, 0.25, 'out'], [1.2, 0, 'out']],
    squint: [[0, 0], [0.4, 0.15, 'out'], [1.2, 0, 'out']],
    mouthOpen: [[0, 0], [0.4, 0.08, 'out'], [1.2, 0, 'out']],
    smile: [[0, 0.15], [0.4, 0.25, 'out'], [1.2, 0.15, 'out']],
  }),

  /* Recoiling. The figure shrinks 3.5 percent (away from the camera), the
     head goes back, the weight lands on the back foot with a bent knee
     a beat after the head. Brows up, lids narrow, mouth pulls in: the
     skeptical read. The pupils look down to keep the viewer. */
  leanBack: body('leanBack', 1.3, {
    bodyScale: [[0, 1], [0.08, 1.008, 'out'], [0.42, 0.965, 'overshoot'], [0.85, 0.968], [1.3, 1, 'out']],
    headNod: [[0, 0], [0.06, 0.05, 'out'], [0.38, -0.3, 'overshoot'], [0.85, -0.28], [1.3, 0, 'out']],
    lookY: [[0, 0], [0.04, -0.05, 'out'], [0.4, 0.25, 'out'], [0.9, 0.22], [1.2, 0, 'out']],
    stance: [[0, 0], [0.14, 0], [0.5, 0.55, 'overshoot'], [1.3, 0, 'out']],
    kneeR: [[0, 0], [0.14, 0], [0.5, 0.2], [1.3, 0, 'out']],
    bodyX: [[0, 0], [0.14, 0], [0.5, 3], [1.3, 0, 'out']],
    lean: [[0, 0], [0.14, 0], [0.5, 1.5], [1.3, 0, 'out']],
    browL: [[0, 0], [0.3, 0.45, 'out'], [1.3, 0, 'out']],
    browR: [[0, 0], [0.3, 0.35, 'out'], [1.3, 0, 'out']],
    squint: [[0, 0], [0.35, 0.2, 'out'], [1.3, 0, 'out']],
    pucker: [[0, 0], [0.35, 0.2, 'out'], [1.3, 0, 'out']],
    smile: [[0, 0.15], [0.35, 0, 'out'], [1.3, 0.15, 'out']],
    mouthX: [[0, 0], [0.4, -0.1, 'out'], [1.3, 0, 'out']],
  }),

  /* A greeting bow. The hands meet at the chest first, then the torso bends
     to half and the head adds its own nod on top. The eyes drop with the
     bow, the lids close slowly at the bottom, and the eyes come back up to
     the viewer before the head lifts. The hands part only once upright. */
  bow: body('bow', 1.6, {
    shoulderL: [[0, 8], [0.1, 6, 'out'], [0.4, 24, 'overshoot'], [1.15, 23], [1.6, 8, 'out']],
    shoulderR: [[0, 8], [0.11, 6, 'out'], [0.42, 24, 'overshoot'], [1.15, 23], [1.6, 8, 'out']],
    elbowL: [[0, 6], [0.14, 8], [0.46, 105, 'overshoot'], [1.15, 104], [1.6, 6, 'out']],
    elbowR: [[0, 6], [0.15, 8], [0.48, 105, 'overshoot'], [1.15, 104], [1.6, 6, 'out']],
    wristL: [[0, 0], [0.5, 15, 'out'], [1.2, 15], [1.6, 0, 'out']],
    wristR: [[0, 0], [0.52, 15, 'out'], [1.2, 15], [1.6, 0, 'out']],
    ...hand('L', [[0.1, 'relaxed'], [0.46, 'flat', 'out'], [1.2, 'flat'], [1.6, 'relaxed', 'out']]),
    ...hand('R', [[0.1, 'relaxed'], [0.48, 'flat', 'out'], [1.2, 'flat'], [1.6, 'relaxed', 'out']]),
    bow: [[0, 0], [0.2, 0], [0.65, 0.5, 'overshoot'], [1.0, 0.48], [1.4, 0, 'out']],
    headNod: [[0, 0], [0.3, 0], [0.72, 0.2, 'overshoot'], [1.0, 0.18], [1.5, 0, 'out']],
    lookY: [[0, 0], [0.3, 0], [0.7, 0.45, 'out'], [1.05, 0.4], [1.3, -0.1, 'out'], [1.6, 0, 'out']],
    blinkL: [[0.7, 0], [0.82, 1], [1.0, 1], [1.18, 0]],
    blinkR: [[0.715, 0], [0.835, 1], [1.0, 1], [1.195, 0]],
    smile: [[0, 0.15], [0.5, 0.4, 'out'], [1.6, 0.3]],
  }),

  /* Standing and swaying, a 3.2 s loop. Weight moves side to side, the
     stance shifts a beat behind it, the head rolls against the body, the
     shoulders rise alternately. Nothing is quite symmetric. */
  sway: body(
    'sway',
    3.2,
    {
      bodyX: [[0, 0], [0.75, 4], [1.65, 0], [2.4, -4], [3.2, 0]],
      stance: [[0, -0.1], [0.95, 0.6], [1.75, -0.1], [2.55, -0.6], [3.2, -0.1]],
      lean: [[0, 0], [0.85, 1.5], [1.7, 0], [2.5, -1.5], [3.2, 0]],
      headTilt: [[0, 0], [1.0, -2.2], [1.8, 0], [2.6, 2.2], [3.2, 0]],
      headTurn: [[0, 0], [1.1, 0.06], [1.9, 0], [2.7, -0.06], [3.2, 0]],
      shoulderL: [[0, 8], [0.9, 9.5], [1.7, 8], [2.5, 6.5], [3.2, 8]],
      shoulderR: [[0, 8], [0.9, 6.5], [1.7, 8], [2.5, 9.5], [3.2, 8]],
    },
    { loop: true },
  ),

  /* Dancing, a 2.4 s loop at 100 bpm. The body dips on every beat and the
     weight changes foot on every beat; shoulders twist and the torso leans
     with the weight; the head bobs on the beat and rolls with the lean;
     the arms are up with the elbows pumping against each other. */
  dance: body(
    'dance',
    2.4,
    {
      stance: [[0, -0.7], [0.6, 0.7], [1.2, -0.7], [1.8, 0.7], [2.4, -0.7]],
      bodyX: [[0, -5.2], [0.08, -6, 'out'], [0.68, 6], [1.28, -6], [1.88, 6], [2.4, -5.2]],
      lean: [[0, -2.6], [0.08, -3, 'out'], [0.68, 3], [1.28, -3], [1.88, 3], [2.4, -2.6]],
      twist: [[0, 4], [0.1, 5, 'out'], [0.7, -5], [1.3, 5], [1.9, -5], [2.4, 4]],
      kneeL: [[0, 0.3], [0.3, 0.05, 'out'], [0.6, 0.3, 'in'], [0.9, 0.05, 'out'], [1.2, 0.3, 'in'], [1.5, 0.05, 'out'], [1.8, 0.3, 'in'], [2.1, 0.05, 'out'], [2.4, 0.3, 'in']],
      kneeR: [[0, 0.28], [0.3, 0.05, 'out'], [0.6, 0.28, 'in'], [0.9, 0.05, 'out'], [1.2, 0.28, 'in'], [1.5, 0.05, 'out'], [1.8, 0.28, 'in'], [2.1, 0.05, 'out'], [2.4, 0.28, 'in']],
      bodyY: [[0, 4], [0.3, -2, 'out'], [0.6, 4, 'in'], [0.9, -2, 'out'], [1.2, 4, 'in'], [1.5, -2, 'out'], [1.8, 4, 'in'], [2.1, -2, 'out'], [2.4, 4, 'in']],
      headNod: [[0, 0.15], [0.3, -0.05, 'out'], [0.6, 0.15, 'in'], [0.9, -0.05, 'out'], [1.2, 0.15, 'in'], [1.5, -0.05, 'out'], [1.8, 0.15, 'in'], [2.1, -0.05, 'out'], [2.4, 0.15, 'in']],
      headTilt: [[0, -3], [0.68, 3], [1.28, -3], [1.88, 3], [2.4, -3]],
      lookX: [[0, -0.15], [0.7, 0.15], [1.3, -0.15], [1.9, 0.15], [2.4, -0.15]],
      shoulderL: [[0, 32], [0.6, 48], [1.2, 32], [1.8, 48], [2.4, 32]],
      shoulderR: [[0, 48], [0.6, 32], [1.2, 48], [1.8, 32], [2.4, 48]],
      elbowL: [[0, 70], [0.6, 95], [1.2, 70], [1.8, 95], [2.4, 70]],
      elbowR: [[0, 95], [0.6, 70], [1.2, 95], [1.8, 70], [2.4, 95]],
      wristL: [[0, -8], [0.66, 8], [1.26, -8], [1.86, 8], [2.4, -8]],
      wristR: [[0, 8], [0.66, -8], [1.26, 8], [1.86, -8], [2.4, 8]],
      ...hand('L', [[0, 'cup']]),
      ...hand('R', [[0, 'cup']]),
      smile: [[0, 0.55], [2.4, 0.55]],
      mouthOpen: [[0, 0.12], [2.4, 0.12]],
      squint: [[0, 0.15], [2.4, 0.15]],
      browL: [[0, 0.2], [2.4, 0.2]],
      browR: [[0, 0.15], [2.4, 0.15]],
      blinkL: [[1.15, 0], [1.2, 1, 'out'], [1.34, 0]],
      blinkR: [[1.165, 0], [1.215, 1, 'out'], [1.355, 0]],
    },
    { loop: true },
  ),

  /* The win. Crouch with the arms tucked, launch 36 px, the right fist
     flies up and pumps twice at the top while the left fist comes to the
     chest, a full grin with teeth, head back. Squash on landing, blink on
     the impact, then the arms float down with a slow-out. */
  celebrate: body('celebrate', 1.6, {
    kneeL: [[0, 0], [0.2, 0.5], [0.44, 0, 'out'], [0.72, 0], [0.8, 0.4, 'in'], [1.05, 0, 'out']],
    kneeR: [[0, 0], [0.21, 0.46], [0.45, 0, 'out'], [0.73, 0], [0.81, 0.38, 'in'], [1.05, 0, 'out']],
    bodyY: [[0, 0], [0.2, 7, 'in'], [0.46, -36, 'out'], [0.72, 0, 'in'], [0.8, 3, 'out'], [1.05, 0, 'out']],
    bodyScale: [[0, 1], [0.2, 0.985], [0.46, 1.02, 'out'], [0.72, 1], [0.8, 1.03, 'out'], [1.1, 1, 'out']],
    shoulderR: [[0, 8], [0.2, 2], [0.5, 165, 'overshoot'], [1.1, 160], [1.6, 8, 'out']],
    elbowR: [[0, 6], [0.22, 40], [0.5, 55, 'out'], [0.62, 95], [0.78, 60, 'out'], [0.9, 88], [1.05, 70], [1.6, 6, 'out']],
    wristR: [[0, 0], [0.5, 12, 'out'], [1.1, 12], [1.6, 0, 'out']],
    shoulderL: [[0, 8], [0.2, 2], [0.55, 55, 'overshoot'], [1.1, 52], [1.6, 8, 'out']],
    elbowL: [[0, 6], [0.22, 30], [0.55, 110, 'overshoot'], [1.1, 106], [1.6, 6, 'out']],
    ...hand('R', [[0.1, 'relaxed'], [0.3, 'fist', 'out'], [1.2, 'fist'], [1.6, 'relaxed', 'out']]),
    ...hand('L', [[0.1, 'relaxed'], [0.34, 'fist', 'out'], [1.2, 'fist'], [1.6, 'relaxed', 'out']]),
    headNod: [[0, 0], [0.2, 0.15], [0.5, -0.25, 'out'], [0.82, 0.1, 'in'], [1.0, -0.1], [1.6, 0, 'out']],
    headTilt: [[0, 0], [0.55, 4], [1.6, 0, 'out']],
    smile: [[0, 0.15], [0.45, 0.85, 'out'], [1.2, 0.8], [1.6, 0.4, 'out']],
    mouthOpen: [[0, 0], [0.45, 0.45, 'out'], [1.0, 0.3], [1.6, 0, 'out']],
    mouthWide: [[0, 0.35], [0.45, 0.75, 'out'], [1.6, 0.35, 'out']],
    teeth: [[0, 0], [0.45, 1, 'out'], [1.6, 0, 'out']],
    squint: [[0, 0], [0.45, 0.35, 'out'], [1.6, 0, 'out']],
    cheeks: [[0, 0], [0.5, 0.4, 'out'], [1.6, 0, 'out']],
    browL: [[0, 0], [0.4, 0.55, 'out'], [1.6, 0, 'out']],
    browR: [[0, 0], [0.4, 0.45, 'out'], [1.6, 0, 'out']],
    blinkL: [[0.7, 0], [0.74, 1, 'out'], [0.86, 0]],
    blinkR: [[0.715, 0], [0.755, 1, 'out'], [0.875, 0]],
  }),

  /* A stretch. Arms go up with the elbows bending on the way and straight
     at the top (the arc), the body rises on its toes, the head goes back,
     the eyes close and the mouth opens. The torso leans into one side at
     the peak. Coming down: a sigh, the shoulders drop past rest, a smile. */
  stretch: body('stretch', 2.2, {
    shoulderL: [[0, 8], [0.15, 4, 'out'], [0.8, 165, 'overshoot'], [1.4, 163], [2.2, 8, 'out']],
    shoulderR: [[0, 8], [0.17, 4, 'out'], [0.84, 168, 'overshoot'], [1.4, 166], [2.2, 8, 'out']],
    elbowL: [[0, 6], [0.2, 12], [0.55, 45], [0.9, 18, 'overshoot'], [1.4, 16], [2.2, 6, 'out']],
    elbowR: [[0, 6], [0.22, 12], [0.58, 45], [0.94, 18, 'overshoot'], [1.4, 16], [2.2, 6, 'out']],
    wristL: [[0, 0], [0.9, -10], [1.4, -10], [2.2, 0, 'out']],
    wristR: [[0, 0], [0.94, -10], [1.4, -10], [2.2, 0, 'out']],
    ...hand('L', [[0.2, 'relaxed'], [0.9, 'flat', 'out'], [1.5, 'flat'], [2.1, 'relaxed', 'out']]),
    ...hand('R', [[0.2, 'relaxed'], [0.94, 'flat', 'out'], [1.5, 'flat'], [2.1, 'relaxed', 'out']]),
    bodyY: [[0, 0], [0.2, 1], [0.95, -4], [1.4, -3.5], [1.7, 1.5, 'in'], [2.2, 0, 'out']],
    bodyScale: [[0, 1], [0.95, 1.02], [1.4, 1.02], [2.2, 1, 'out']],
    lean: [[0, 0], [0.5, 0], [1.1, 3], [1.5, 2.5], [2.2, 0, 'out']],
    twist: [[0, 0], [0.5, 0], [1.1, 3], [2.2, 0, 'out']],
    headNod: [[0, 0], [0.3, 0.05, 'out'], [0.95, -0.35], [1.45, -0.3], [1.9, 0.08], [2.2, 0, 'out']],
    blinkL: [[0, 0], [0.7, 0], [1.0, 0.9], [1.45, 0.9], [1.7, 0, 'out']],
    blinkR: [[0, 0], [0.715, 0], [1.015, 0.9], [1.45, 0.9], [1.715, 0, 'out']],
    browL: [[0, 0], [0.9, 0.45], [1.5, 0.4], [2.2, 0, 'out']],
    browR: [[0, 0], [0.9, 0.38], [1.5, 0.34], [2.2, 0, 'out']],
    mouthOpen: [[0, 0], [0.9, 0.3], [1.45, 0.28], [1.75, 0.12, 'out'], [2.2, 0, 'out']],
    smile: [[0, 0.15], [1.0, 0.1], [1.8, 0.35, 'out'], [2.2, 0.2, 'out']],
  }),

  /* A side step to the viewer's left and back. The eyes and head look where
     the foot is going; the weight pushes onto the right foot first, then
     the left foot lifts, the body travels 14 px and the right foot closes.
     A pause, then the same step back the other way, right foot leading. */
  stepLeft: body('stepLeft', 1.6, {
    lookX: [[0, 0], [0.06, -0.4, 'out'], [0.5, -0.1], [0.9, -0.1], [0.98, 0.25, 'out'], [1.3, 0, 'out']],
    headTurn: [[0, 0], [0.1, 0.03, 'out'], [0.32, -0.3, 'overshoot'], [0.85, -0.25], [1.25, 0, 'out']],
    headTilt: [[0, 0], [0.5, -2], [1.1, -1.5], [1.6, 0, 'out']],
    lean: [[0, 0], [0.14, 2], [0.45, -4], [0.8, -1], [1.2, 2.5], [1.6, 0, 'out']],
    twist: [[0, 0], [0.2, 0], [0.5, -4], [1.0, -3], [1.3, 2], [1.6, 0, 'out']],
    stance: [[0, 0], [0.14, 0.5], [0.5, -0.9], [0.8, -0.2], [1.05, -0.2], [1.25, 0.8], [1.45, 0.3], [1.6, 0, 'out']],
    bodyX: [[0, 0], [0.14, 2], [0.52, -14], [0.9, -14], [1.05, -13.6], [1.4, 0], [1.6, 0]],
    kneeL: [[0, 0], [0.18, 0.1], [0.36, 0.4], [0.56, 0.05, 'out'], [1.25, 0.05], [1.45, 0.3], [1.6, 0, 'out']],
    kneeR: [[0, 0], [0.55, 0.1], [0.72, 0.35], [0.92, 0, 'out'], [1.05, 0.1], [1.22, 0.35], [1.42, 0, 'out']],
    bodyY: [[0, 0], [0.36, -3], [0.56, 1, 'in'], [0.72, -2], [0.92, 0.5, 'in'], [1.1, 0], [1.24, -2], [1.42, 0.5, 'in'], [1.6, 0, 'out']],
  }),
}

/* stepRight is stepLeft in a mirror: knees swap, travel and gaze flip. */
BODY_ACTIONS.stepRight = mirror(BODY_ACTIONS.stepLeft, 'stepRight')
