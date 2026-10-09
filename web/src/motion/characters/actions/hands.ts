/* Arm and hand gestures. Each one is a few keyframes on the arm channels,
 * a hand shape from handPoses, and the face joining in, built from the same
 * small helpers so every gesture winds up, overlaps, overshoots and settles
 * the same way. Timing notes are in seconds.
 *
 * Geometry, so the numbers below can be checked: in the arm's own frame
 * (the screen-left drawing; the right arm is its mirror) the renderer does
 * rotate(shoulder) at the pivot and rotate(-elbow) at the elbow, so the
 * forearm points along (-sin(s - e), cos(s - e)) with -x away from the body.
 * A positive elbow therefore folds the forearm toward the body, and once the
 * upper arm is lifted it folds DOWN. A forearm that points up beside the head
 * needs a negative elbow value; that is how the wave, the counts and the
 * scratch are written. The two reference poses hold: 90/0 is a horizontal
 * arm and 20/110 folds the hand in front of the chest.
 *
 * Default one-handed gestures use the character's right hand, which is the
 * screen-RIGHT arm (channels ending in R). The runtime mirrors on request. */
import type { Channel } from '../rig/channels'
import type { Action, Ease, Key, Tracks } from '../rig/track'
import { HAND_POSES, handKeys, type HandPose } from './handPoses'

type Side = 'L' | 'R'
type Arm = { s: number; e: number; w: number }

const REST: Arm = { s: 8, e: 6, w: 0 }
/* overlapping action: the shoulder leads, the forearm follows, the hand last */
const LAG: Arm = { s: 0, e: 0.06, w: 0.11 }

const JOINT: Record<keyof Arm, string> = { s: 'shoulder', e: 'elbow', w: 'wrist' }
const joint = (side: Side, j: keyof Arm) => `${JOINT[j]}${side}` as Channel

/* ---- helpers ------------------------------------------------------------ */

/** Concatenate tracks, keeping each channel's keys in time order. */
function merge(...parts: Tracks[]): Tracks {
  const out: Tracks = {}
  for (const p of parts) {
    for (const ch in p) (out[ch as Channel] ??= []).push(...p[ch as Channel]!)
  }
  for (const ch in out) out[ch as Channel]!.sort((a, b) => a[0] - b[0])
  return out
}

/** One arm pose landing at t, the joints staggered by LAG. */
function armAt(side: Side, arm: Arm, t: number, e: Ease = 'overshoot', lag = LAG): Tracks {
  const out: Tracks = {}
  for (const j of ['s', 'e', 'w'] as const) out[joint(side, j)] = [[t + lag[j], arm[j], e]]
  return out
}

/** Move from `from` to `to` between t0 and t1 with the velocity shape of a
    real limb: it gathers speed over the first half ('in' to 55 % of the
    way), then brakes and overshoots into the pose. A single 'overshoot'
    segment would start at full speed, which reads as a snap. */
function moveTo(side: Side, from: Arm, to: Arm, t0: number, t1: number): Tracks {
  const mid: Arm = { s: 0, e: 0, w: 0 }
  for (const j of ['s', 'e', 'w'] as const) mid[j] = from[j] + (to[j] - from[j]) * 0.55
  return merge(armAt(side, mid, t0 + (t1 - t0) * 0.45, 'in'), armAt(side, to, t1, 'overshoot'))
}

/** Lift from rest to `arm`, landing at t0 + dur: a small counter-move first
    (the wind-up a real arm makes), then the lift. */
function raise(side: Side, arm: Arm, t0: number, dur: number): Tracks {
  const back: Arm = {
    s: REST.s - Math.sign(arm.s - REST.s) * 4,
    e: REST.e - Math.sign(arm.e - REST.e) * 5,
    w: REST.w - Math.sign(arm.w - REST.w) * 6,
  }
  return merge(armAt(side, REST, t0, 'linear'), armAt(side, back, t0 + 0.09, 'inOut'), moveTo(side, back, arm, t0 + 0.09, t0 + dur))
}

/** Hold `arm` from t1 to t2 without freezing: each joint drifts about a
    degree, peaking at a different moment so nothing lands together. */
function hold(side: Side, arm: Arm, t1: number, t2: number): Tracks {
  const span = t2 - t1
  const drift: Arm = { s: 1, e: -0.8, w: 1.2 }
  const peak: Arm = { s: 0.4, e: 0.55, w: 0.5 }
  const out: Tracks = {}
  for (const j of ['s', 'e', 'w'] as const) {
    out[joint(side, j)] = [
      [t1 + LAG[j], arm[j], 'overshoot'],
      [t1 + span * peak[j], arm[j] + drift[j], 'inOut'],
      [t2, arm[j] + drift[j] * 0.3, 'inOut'],
    ]
  }
  return out
}

/** Return to rest by t1: the arm gathers a little speed as it drops and
    slows into the hang; the shoulder goes first again. */
function lower(side: Side, t1: number): Tracks {
  return armAt(side, REST, t1, 'inOut', { s: -0.08, e: -0.03, w: 0 })
}

/** The common one-shot: wind-up, lift, breathing hold, slow return. */
function reach(side: Side, arm: Arm, lift: number, release: number, end: number): Tracks {
  return merge(raise(side, arm, 0, lift), hold(side, arm, lift, release), lower(side, end))
}

/** Keys at every extreme of a sine on one channel: `cycles` at `hz` about
    `centre`, from t0, with the last swing slightly smaller as the energy
    goes out of it. inOut between extremes is a sine to the eye. */
function oscillate(centre: number, amp: number, hz: number, cycles: number, t0: number, phase = 0): Key[] {
  const half = 0.5 / hz
  const keys: Key[] = [[t0 + phase, centre, 'inOut']]
  const n = cycles * 2
  for (let i = 1; i <= n; i++) {
    const damp = i === n ? 0.6 : 1
    keys.push([t0 + phase + (i - 0.5) * half, centre + (i % 2 ? amp : -amp) * damp, 'inOut'])
  }
  keys.push([t0 + phase + (n + 0.5) * half, centre, 'inOut'])
  return keys
}

/** Bring a hand to a shape at t and back to relaxed at tBack. The hand
    starts from relaxed: sampleKeys holds a track's first key before its
    time, so without that key the shape would show from t=0. */
function handShape(side: Side, pose: HandPose, t: number, tBack?: number, e: Ease = 'out'): Tracks {
  const there = handKeys(side, pose, t, e, HAND_POSES.relaxed)
  return tBack === undefined ? there : merge(there, handKeys(side, HAND_POSES.relaxed, tBack, 'out'))
}

/** A channel that goes to `v` at t1, lives there, and eases back by t2. The
    middle key keeps the hold alive with a touch of drift. */
function dip(ch: Channel, v: number, t1: number, t2: number, back = 0, e: Ease = 'out'): Tracks {
  const mid = t1 + (t2 - t1) * 0.55
  /* the channel rests at `back` until shortly before t1; without that key the
     sampler would hold the peak from t=0 */
  return { [ch]: [[Math.max(0, t1 - 0.14), back, 'linear'], [t1, v, e], [mid, v * 0.92 + back * 0.08, 'inOut'], [t2, back, 'out']] }
}

function action(name: string, duration: number, tracks: Tracks, extra: Partial<Action> = {}): Action {
  return { name, duration, group: 'hands', tracks, ...extra }
}

/* Gestures below are written for the right (screen-R) arm; two-handed ones
   land the second arm a few frames later because nobody is symmetric. */
const R: Side = 'R'
const L: Side = 'L'

/* ---- greetings -------------------------------------------------------- */

/* Forearm up beside the head, elbow swinging 3 times at 2.5 Hz, shoulder
   held, the hand trailing the elbow by 60 ms with its own smaller swing.
   Hand up at 0.42, waving 0.42..1.72, home by 2.05: the last swing ends at
   1.72 and the arm needs a third of a second to drop, not a frame. */
const WAVE_ARM: Arm = { s: 65, e: -120, w: 0 }
const wave = action('wave', 2.05, merge(
  raise(R, WAVE_ARM, 0, 0.36),
  { shoulderR: [[0.36, WAVE_ARM.s, 'overshoot'], [1.0, WAVE_ARM.s + 1.5, 'inOut'], [1.52, WAVE_ARM.s + 0.5, 'inOut']] },
  { elbowR: oscillate(WAVE_ARM.e, 25, 2.5, 3, 0.42) },
  { wristR: oscillate(0, 18, 2.5, 3, 0.42, 0.06) },
  lower(R, 2.05),
  handShape(R, HAND_POSES.open, 0.3, 1.9),
  /* the face: a smile that builds as the hand comes up, the head leaning
     3 deg toward the raised hand, a brow flash on the first swing */
  { smile: [[0.1, 0.2], [0.55, 0.65, 'out'], [1.7, 0.6, 'inOut'], [2.05, 0.4, 'out']] },
  { squint: [[0.2, 0], [0.6, 0.12, 'out'], [2.05, 0.02, 'out']] },
  { headTilt: [[0.15, 0], [0.5, 3, 'overshoot'], [1.75, 2.6, 'inOut'], [2.05, 0.5, 'out']] },
  { browL: [[0.3, 0], [0.42, 0.45, 'out'], [0.6, 0.1, 'inOut']] },
  { browR: [[0.3, 0], [0.43, 0.5, 'out'], [0.62, 0.12, 'inOut']] },
))

/* The whole arm overhead, swinging from the shoulder at 2 Hz, three times;
   the last swing ends at 2.25 and the arm is home by 2.5. */
const BIG_ARM: Arm = { s: 142, e: -25, w: -5 }
const waveBig = action('waveBig', 2.5, merge(
  raise(R, BIG_ARM, 0, 0.44),
  { shoulderR: oscillate(BIG_ARM.s, 14, 2, 3, 0.5) },
  { elbowR: oscillate(BIG_ARM.e, 12, 2, 3, 0.5, 0.07) },
  { wristR: oscillate(BIG_ARM.w, 14, 2, 3, 0.5, 0.12) },
  lower(R, 2.5),
  handShape(R, HAND_POSES.open, 0.35, 2.3),
  { smile: [[0.1, 0.2], [0.6, 0.75, 'out'], [2.1, 0.7, 'inOut'], [2.5, 0.45, 'out']] },
  { mouthOpen: [[0.3, 0], [0.6, 0.18, 'out'], [2.1, 0.14, 'inOut'], [2.5, 0, 'out']] },
  { squint: [[0.2, 0], [0.7, 0.18, 'out'], [2.5, 0.03, 'out']] },
  { headTilt: [[0.15, 0], [0.55, 4, 'overshoot'], [2.15, 3.5, 'inOut'], [2.5, 0.5, 'out']] },
  { browL: [[0.3, 0], [0.5, 0.5, 'out'], [2.1, 0.3, 'inOut'], [2.5, 0.05, 'out']] },
  { browR: [[0.3, 0], [0.52, 0.55, 'out'], [2.1, 0.35, 'inOut'], [2.5, 0.05, 'out']] },
  /* the body leans a touch away from the big arm, as a counterweight */
  { lean: [[0.2, 0], [0.6, -2, 'overshoot'], [2.1, -1.6, 'inOut'], [2.5, 0, 'out']] },
))

/* ---- pointing --------------------------------------------------------- */

/* Out and down at 45 deg, to something beside the character. The eyes and
   head go there first; a point narrows the eyes. 1.5 s. */
const point = action('point', 1.5, merge(
  reach(R, { s: 60, e: 25, w: -10 }, 0.34, 1.15, 1.5),
  handShape(R, HAND_POSES.point, 0.18, 1.3),
  { lookX: [[0.0, 0], [0.12, 0.6, 'out'], [1.15, 0.5, 'inOut'], [1.5, 0, 'out']] },
  { lookY: [[0.0, 0], [0.14, 0.3, 'out'], [1.15, 0.25, 'inOut'], [1.5, 0, 'out']] },
  { headTurn: [[0.06, 0], [0.3, 0.3, 'overshoot'], [1.15, 0.26, 'inOut'], [1.5, 0, 'out']] },
  dip('squint', 0.2, 0.35, 1.5),
  dip('browInnerL', -0.1, 0.35, 1.5),
  dip('browInnerR', -0.1, 0.38, 1.5),
))

/* Straight up over the head; the eyes go up and the brows follow. 1.6 s. */
const pointUp = action('pointUp', 1.6, merge(
  reach(R, { s: 150, e: -20, w: -5 }, 0.4, 1.2, 1.6),
  handShape(R, HAND_POSES.point, 0.2, 1.42),
  { lookY: [[0.0, 0], [0.14, -0.7, 'out'], [1.2, -0.6, 'inOut'], [1.6, 0, 'out']] },
  { headNod: [[0.08, 0], [0.4, -0.35, 'overshoot'], [1.2, -0.3, 'inOut'], [1.6, 0, 'out']] },
  { browL: [[0.1, 0], [0.4, 0.4, 'out'], [1.2, 0.35, 'inOut'], [1.6, 0, 'out']] },
  { browR: [[0.1, 0], [0.43, 0.45, 'out'], [1.2, 0.4, 'inOut'], [1.6, 0, 'out']] },
  dip('mouthOpen', 0.12, 0.4, 1.6),
))

/* At the viewer. The forearm folds in front of the chest and the hand is
   drawn facing the camera (palm 0.9) so the finger reads as foreshortened
   toward whoever is watching. Eyes narrow, chin drops a little. 1.6 s. */
const pointAtScreen = action('pointAtScreen', 1.6, merge(
  reach(R, { s: 42, e: 72, w: -25 }, 0.36, 1.25, 1.6),
  handShape(R, { ...HAND_POSES.point, palm: 0.9 }, 0.2, 1.45),
  dip('squint', 0.25, 0.36, 1.6),
  { headNod: [[0.05, 0], [0.36, 0.14, 'overshoot'], [1.25, 0.12, 'inOut'], [1.6, 0, 'out']] },
  { lean: [[0.05, 0], [0.4, 1.5, 'overshoot'], [1.25, 1.2, 'inOut'], [1.6, 0, 'out']] },
  dip('browInnerL', -0.12, 0.36, 1.6),
  dip('browInnerR', -0.08, 0.4, 1.6),
  dip('smile', 0.3, 0.4, 1.6, 0.15),
))

/* An open palm that starts at the chest and sweeps out toward the slide,
   the elbow unfolding after the shoulder so the hand draws an arc. 1.7 s. */
function present(side: Side, dir: 1 | -1): Action {
  const name = side === 'R' ? 'presentRight' : 'presentLeft'
  return action(name, 1.7, merge(
    raise(side, { s: 18, e: 95, w: 10 }, 0, 0.3),
    moveTo(side, { s: 18, e: 95, w: 10 }, { s: 62, e: 28, w: -20 }, 0.36, 0.66),
    hold(side, { s: 62, e: 28, w: -20 }, 0.66, 1.35),
    lower(side, 1.7),
    handShape(side, HAND_POSES.open, 0.3, 1.55),
    { lookX: [[0.0, 0], [0.14, 0.65 * dir, 'out'], [1.35, 0.55 * dir, 'inOut'], [1.7, 0, 'out']] },
    { headTurn: [[0.08, 0], [0.5, 0.4 * dir, 'overshoot'], [1.35, 0.35 * dir, 'inOut'], [1.7, 0, 'out']] },
    { headTilt: [[0.1, 0], [0.6, 2 * dir, 'overshoot'], [1.35, 1.8 * dir, 'inOut'], [1.7, 0, 'out']] },
    dip('smile', 0.4, 0.5, 1.7, 0.15),
    dip('browL', 0.2, 0.4, 1.7),
    dip('browR', 0.25, 0.44, 1.7),
  ))
}
const presentRight = present(R, 1)
const presentLeft = present(L, -1)

/* ---- verdicts --------------------------------------------------------- */

/* Fist in front of the chest, thumb up (the hand's thumb sits on its +x,
   which points up once the forearm points at the body). Grin, one brow. 1.5 s. */
const thumbsUp = action('thumbsUp', 1.5, merge(
  reach(R, { s: 30, e: 125, w: -5 }, 0.34, 1.15, 1.5),
  handShape(R, HAND_POSES.thumbsUp, 0.14, 1.32),
  { smile: [[0.1, 0.2], [0.45, 0.7, 'out'], [1.15, 0.65, 'inOut'], [1.5, 0.4, 'out']] },
  dip('squint', 0.2, 0.4, 1.5),
  dip('browR', 0.35, 0.3, 1.5),
  dip('browL', 0.1, 0.34, 1.5),
  { headNod: [[0.1, 0], [0.34, 0.15, 'overshoot'], [0.6, 0.02, 'inOut'], [1.5, 0, 'out']] },
  { headTilt: [[0.1, 0], [0.45, -2.5, 'overshoot'], [1.15, -2, 'inOut'], [1.5, 0, 'out']] },
))

/* Thumb down only happens when the fingers point away from the body, so the
   fist goes out to the side at waist height, wrist bent back. Mouth down,
   inner brows drop. 1.5 s. */
const thumbsDown = action('thumbsDown', 1.5, merge(
  reach(R, { s: 58, e: 32, w: -60 }, 0.36, 1.15, 1.5),
  handShape(R, HAND_POSES.thumbsUp, 0.16, 1.32),
  dip('smile', -0.4, 0.4, 1.5, 0.1),
  dip('browInnerL', -0.3, 0.36, 1.5),
  dip('browInnerR', -0.35, 0.4, 1.5),
  dip('squint', 0.3, 0.4, 1.5),
  { headNod: [[0.1, 0], [0.4, 0.18, 'overshoot'], [1.15, 0.15, 'inOut'], [1.5, 0, 'out']] },
  { headTurn: [[0.1, 0], [0.45, -0.12, 'overshoot'], [1.15, -0.1, 'inOut'], [1.5, 0, 'out']] },
))

/* Ring at chest height, hand facing out. A tilt and a half-wink. 1.4 s. */
const okSign = action('okSign', 1.4, merge(
  reach(R, { s: 10, e: 140, w: 0 }, 0.32, 1.05, 1.4),
  handShape(R, HAND_POSES.ok, 0.16, 1.22),
  dip('smile', 0.5, 0.4, 1.4, 0.15),
  dip('browR', 0.25, 0.3, 1.4),
  { blinkR: [[0.3, 0], [0.42, 0.75, 'out'], [0.62, 0.7, 'inOut'], [0.82, 0, 'out']] },
  { headTilt: [[0.1, 0], [0.42, 2.5, 'overshoot'], [1.05, 2.2, 'inOut'], [1.4, 0, 'out']] },
))

/* ---- two hands ----------------------------------------------------------- */

/* Palms meet in front of the chest four times. With 92/84 px links the
   hands can only reach the centreline from a low shoulder (about 24 deg)
   with the elbow folded past 90, so the contract's 35/95 would leave a gap;
   these numbers close it, and the palms overlap on contact as a real clap
   does from the front. Contacts at 0.46, 0.7, 0.94, 1.18. 1.4 s. */
const CLAP_MEET: Arm = { s: 24, e: 98, w: 15 }
const CLAP_PART: Arm = { s: 32, e: 85, w: 5 }
function clapArm(side: Side, offset: number): Tracks {
  const parts: Tracks[] = [raise(side, CLAP_PART, offset, 0.3)]
  for (let i = 0; i < 4; i++) {
    const hit = 0.46 + i * 0.24 + offset
    parts.push(armAt(side, CLAP_MEET, hit, 'in', { s: 0, e: 0.01, w: 0.02 }))
    if (i < 3) parts.push(armAt(side, CLAP_PART, hit + 0.12, 'out', { s: 0, e: 0.02, w: 0.04 }))
  }
  parts.push(armAt(side, { ...CLAP_MEET, s: CLAP_MEET.s + 1 }, 1.25 + offset, 'out'))
  parts.push(lower(side, 1.4))
  return merge(...parts)
}
const clap = action('clap', 1.4, merge(
  clapArm(R, 0),
  clapArm(L, 0.02),
  handShape(R, HAND_POSES.flat, 0.2, 1.3),
  handShape(L, HAND_POSES.flat, 0.22, 1.3),
  /* every clap bounces the body a touch and dips the head */
  { bodyY: [[0.4, 0], [0.46, -2, 'out'], [0.58, 0], [0.7, -2, 'out'], [0.82, 0], [0.94, -2, 'out'], [1.06, 0], [1.18, -2, 'out'], [1.34, 0, 'out']] },
  { headNod: [[0.4, 0], [0.47, 0.1, 'out'], [0.6, 0.02], [0.71, 0.1, 'out'], [0.84, 0.02], [0.95, 0.1, 'out'], [1.08, 0.02], [1.19, 0.1, 'out'], [1.4, 0, 'out']] },
  { smile: [[0.1, 0.2], [0.45, 0.65, 'out'], [1.2, 0.6, 'inOut'], [1.4, 0.4, 'out']] },
  dip('squint', 0.2, 0.45, 1.4),
  dip('browL', 0.3, 0.3, 1.4),
  dip('browR', 0.35, 0.33, 1.4),
), { blendOut: 0.3 })

/* Elbows out, hands cupped at the hips, the left landing a beat after the
   right. Chin up a little; the brows set. 1.8 s with a long hold. */
const HIPS: Arm = { s: 28, e: 73, w: 20 }
const handsOnHips = action('handsOnHips', 1.8, merge(
  reach(R, HIPS, 0.38, 1.45, 1.8),
  merge(raise(L, HIPS, 0.07, 0.38), hold(L, HIPS, 0.45, 1.5), lower(L, 1.8)),
  handShape(R, HAND_POSES.cup, 0.2, 1.62),
  handShape(L, HAND_POSES.cup, 0.27, 1.64),
  { headNod: [[0.1, 0], [0.45, -0.15, 'overshoot'], [1.45, -0.12, 'inOut'], [1.8, 0, 'out']] },
  dip('browInnerL', -0.12, 0.4, 1.8),
  dip('browInnerR', -0.1, 0.44, 1.8),
  dip('smile', 0.08, 0.4, 1.8, 0.15),
  dip('squint', 0.1, 0.45, 1.8),
  { lean: [[0.1, 0], [0.5, 1.2, 'overshoot'], [1.45, 1, 'inOut'], [1.8, 0, 'out']] },
))

/* Forearms folded across the chest, right over left (the right lands first
   and the left tucks under 90 ms later). Eyes narrow slightly. 1.9 s. */
const CROSS: Arm = { s: 10, e: 121, w: 10 }
const armsCrossed = action('armsCrossed', 1.9, merge(
  reach(R, CROSS, 0.4, 1.55, 1.9),
  merge(raise(L, { ...CROSS, e: 118 }, 0.09, 0.4), hold(L, { ...CROSS, e: 118 }, 0.49, 1.6), lower(L, 1.9)),
  handShape(R, HAND_POSES.cup, 0.22, 1.72),
  handShape(L, HAND_POSES.cup, 0.3, 1.74),
  dip('squint', 0.15, 0.45, 1.9),
  dip('browL', -0.1, 0.42, 1.9),
  dip('browR', -0.08, 0.46, 1.9),
  dip('smile', 0.02, 0.45, 1.9, 0.15),
  { headNod: [[0.1, 0], [0.45, 0.06, 'overshoot'], [1.55, 0.05, 'inOut'], [1.9, 0, 'out']] },
  { headTilt: [[0.1, 0], [0.5, -1.5, 'overshoot'], [1.55, -1.2, 'inOut'], [1.9, 0, 'out']] },
))

/* Both forearms turn out, palms up and open, brows go up, the mouth corners
   drop, the head tips. Up by 0.32, held to 0.85, down by 1.2. */
/* forearms UP and out, so the elbow is negative like every other raised forearm here */
const SHRUG: Arm = { s: 35, e: -95, w: -30 }
const shrug = action('shrug', 1.2, merge(
  reach(R, SHRUG, 0.32, 0.85, 1.2),
  merge(raise(L, { ...SHRUG, s: 33 }, 0.04, 0.32), hold(L, { ...SHRUG, s: 33 }, 0.36, 0.88), lower(L, 1.2)),
  handShape(R, HAND_POSES.open, 0.16, 1.05),
  handShape(L, HAND_POSES.open, 0.2, 1.06),
  { browL: [[0.05, 0], [0.3, 0.8, 'overshoot'], [0.85, 0.7, 'inOut'], [1.2, 0.05, 'out']] },
  { browR: [[0.05, 0], [0.33, 0.9, 'overshoot'], [0.85, 0.8, 'inOut'], [1.2, 0.05, 'out']] },
  { browInnerL: [[0.05, 0], [0.32, 0.25, 'out'], [0.85, 0.2, 'inOut'], [1.2, 0, 'out']] },
  { browInnerR: [[0.05, 0], [0.34, 0.2, 'out'], [0.85, 0.18, 'inOut'], [1.2, 0, 'out']] },
  { smile: [[0.05, 0.15], [0.32, -0.25, 'out'], [0.85, -0.2, 'inOut'], [1.2, 0.1, 'out']] },
  dip('mouthWide', 0.2, 0.32, 1.2, 0.35),
  { headTilt: [[0.05, 0], [0.34, 4, 'overshoot'], [0.85, 3.5, 'inOut'], [1.2, 0, 'out']] },
  { headY: [[0.05, 0], [0.3, 2, 'overshoot'], [0.85, 1.6, 'inOut'], [1.2, 0, 'out']] },
  { lookX: [[0.0, 0], [0.2, 0.3, 'out'], [0.85, 0.25, 'inOut'], [1.2, 0, 'out']] },
))

/* ---- the hand on the face ---------------------------------------------- */

/* The upper arm cannot foreshorten in a front view, so the hand reaches
   the jaw and lower face, not the forehead; the dropped head and closed
   eyes do the rest. The head drops after the hand arrives. 1.8 s. */
const facepalm = action('facepalm', 1.8, merge(
  reach(R, { s: -32, e: 152, w: -10 }, 0.4, 1.35, 1.8),
  handShape(R, { ...HAND_POSES.flat, palm: 0.9 }, 0.2, 1.62),
  { blinkL: [[0.25, 0], [0.42, 1, 'out'], [1.4, 1, 'hold'], [1.62, 0, 'out']] },
  { blinkR: [[0.27, 0], [0.44, 1, 'out'], [1.42, 1, 'hold'], [1.65, 0, 'out']] },
  { headNod: [[0.2, 0], [0.55, 0.7, 'overshoot'], [1.35, 0.65, 'inOut'], [1.8, 0, 'out']] },
  { browInnerL: [[0.2, 0], [0.5, 0.3, 'out'], [1.35, 0.25, 'inOut'], [1.8, 0, 'out']] },
  { browInnerR: [[0.2, 0], [0.52, 0.25, 'out'], [1.35, 0.22, 'inOut'], [1.8, 0, 'out']] },
  dip('smile', -0.3, 0.5, 1.8, 0.1),
  { bow: [[0.2, 0], [0.6, 0.12, 'overshoot'], [1.35, 0.1, 'inOut'], [1.8, 0, 'out']] },
))

/* Hand cupped at the chin, looking up and to the left, lips pursed, the
   index finger tapping. A loop: the entry rides on blendIn, the keys are
   cyclic so the 2.4 s cycle repeats without a seam. */
const CHIN: Arm = { s: -30, e: 150, w: 10 }
const CHIN_HAND: HandPose = { f1: 0.45, f2: 0.55, f3: 0.6, f4: 0.65, thumb: 0.3, spread: 0.15, palm: 0.4 }
const chinThink = action('chinThink', 2.4, merge(
  /* a cyclic drift, each joint on its own phase, so the hold lives and the
     loop point is invisible */
  { shoulderR: [[0, CHIN.s], [0.9, CHIN.s + 1, 'inOut'], [1.7, CHIN.s - 0.4, 'inOut'], [2.4, CHIN.s, 'inOut']] },
  { elbowR: [[0, CHIN.e], [1.1, CHIN.e - 0.8, 'inOut'], [1.9, CHIN.e + 0.3, 'inOut'], [2.4, CHIN.e, 'inOut']] },
  { wristR: [[0, CHIN.w], [0.7, CHIN.w + 1.2, 'inOut'], [1.5, CHIN.w - 0.5, 'inOut'], [2.4, CHIN.w, 'inOut']] },
  handKeys(R, CHIN_HAND, 0, 'out'),
  { fR1: [[0, 0.45], [0.5, 0.45], [0.62, 0.25, 'out'], [0.8, 0.45, 'inOut'], [0.95, 0.25, 'out'], [1.15, 0.45, 'inOut'], [1.9, 0.45], [2.02, 0.25, 'out'], [2.4, 0.45, 'inOut']] },
  { lookX: [[0, -0.6], [1.3, -0.5, 'inOut'], [1.6, -0.62, 'inOut'], [2.4, -0.6, 'inOut']] },
  { lookY: [[0, -0.5], [1.1, -0.42, 'inOut'], [2.4, -0.5, 'inOut']] },
  { headTurn: [[0, -0.15], [1.4, -0.12, 'inOut'], [2.4, -0.15, 'inOut']] },
  { headTilt: [[0, -3], [1.2, -2.4, 'inOut'], [2.4, -3, 'inOut']] },
  { pucker: [[0, 0.4], [0.9, 0.46, 'inOut'], [1.8, 0.36, 'inOut'], [2.4, 0.4, 'inOut']] },
  { mouthX: [[0, 0.2], [2.4, 0.2] ] },
  { browL: [[0, 0.25], [1.5, 0.3, 'inOut'], [2.4, 0.25, 'inOut']] },
  { browInnerR: [[0, -0.1], [2.4, -0.1]] },
  { squint: [[0, 0.1], [2.4, 0.1]] },
), { loop: true, blendIn: 0.45, blendOut: 0.35 })

/* Hand up beside the shoulder, fingers out to the top of the skull, and a
   scratch: wrist and fingers at 4 Hz. Eyes up at the hand, mouth to one
   side. 2 s. */
const SCRATCH: Arm = { s: 150, e: -60, w: 10 }
const scratchHead = action('scratchHead', 2, merge(
  raise(R, SCRATCH, 0, 0.42),
  { shoulderR: [[0.42, SCRATCH.s, 'overshoot'], [1.1, SCRATCH.s + 1, 'inOut'], [1.55, SCRATCH.s + 0.4, 'inOut']] },
  { elbowR: [[0.48, SCRATCH.e, 'overshoot'], [1.1, SCRATCH.e - 1, 'inOut'], [1.55, SCRATCH.e, 'inOut']] },
  { wristR: oscillate(SCRATCH.w, 8, 4, 4, 0.55) },
  lower(R, 2),
  handShape(R, HAND_POSES.cup, 0.25, 1.8),
  { fR1: oscillate(0.45, 0.15, 4, 4, 0.58) },
  { fR2: oscillate(0.5, 0.15, 4, 4, 0.6) },
  { fR3: oscillate(0.5, 0.12, 4, 4, 0.62) },
  { lookX: [[0, 0], [0.2, 0.4, 'out'], [1.55, 0.35, 'inOut'], [2, 0, 'out']] },
  { lookY: [[0, 0], [0.22, -0.4, 'out'], [1.55, -0.35, 'inOut'], [2, 0, 'out']] },
  { headTilt: [[0.1, 0], [0.5, -4, 'overshoot'], [1.55, -3.5, 'inOut'], [2, 0, 'out']] },
  dip('mouthX', 0.3, 0.45, 2),
  dip('pucker', 0.2, 0.45, 2),
  dip('browInnerL', 0.3, 0.45, 2),
  dip('browR', 0.2, 0.48, 2),
))

/* ---- counting and emphasis ----------------------------------------------- */

/* The hand up beside the shoulder, palm out, showing n fingers one at a
   time; every new finger gets a small nod. */
const COUNT: Arm = { s: 25, e: -120, w: 0 }
function count(name: string, n: 1 | 2 | 3): Action {
  const shapes = [HAND_POSES.one, HAND_POSES.two, HAND_POSES.three]
  const flipAt = (i: number) => 0.42 + i * 0.4
  const release = flipAt(n - 1) + 0.5
  const end = release + 0.4
  const parts: Tracks[] = [
    reach(R, COUNT, 0.36, release, end),
    handKeys(R, { ...HAND_POSES.fist, palm: 1 }, 0.18, 'out', HAND_POSES.relaxed),
  ]
  const nods: Key[] = [[0.3, 0]]
  for (let i = 0; i < n; i++) {
    parts.push(handKeys(R, shapes[i], flipAt(i), 'overshoot'))
    nods.push([flipAt(i) + 0.08, 0.12, 'out'], [flipAt(i) + 0.3, 0.02, 'inOut'])
  }
  nods.push([end, 0, 'out'])
  parts.push(handKeys(R, HAND_POSES.relaxed, end - 0.15, 'out'))
  parts.push(
    { headNod: nods },
    { lookX: [[0, 0], [0.2, 0.35, 'out'], [release, 0.3, 'inOut'], [end, 0, 'out']] },
    { lookY: [[0, 0], [0.22, -0.15, 'out'], [release, -0.12, 'inOut'], [end, 0, 'out']] },
    dip('browL', 0.3, 0.36, end),
    dip('browR', 0.35, 0.4, end),
    dip('smile', 0.3, 0.4, end, 0.15),
  )
  return action(name, end, merge(...parts))
}
const countOne = count('countOne', 1)
const countTwo = count('countTwo', 2)
const countThree = count('countThree', 3)

/* Arm swings out and down for the wind-up, then the fist pulls in to the
   collarbone in one fast arc (the elbow folds from 10 to 150 while the
   shoulder drops), with a bounce and a dip of the head. 1.2 s. */
const fistPump = action('fistPump', 1.2, merge(
  raise(R, { s: 35, e: 10, w: 0 }, 0, 0.28),
  armAt(R, { s: 8, e: 150, w: 15 }, 0.46, 'overshoot', { s: 0.03, e: 0, w: 0.05 }),
  hold(R, { s: 8, e: 150, w: 15 }, 0.5, 0.88),
  lower(R, 1.2),
  handShape(R, HAND_POSES.fist, 0.1, 1.05),
  { bodyY: [[0.3, 0], [0.4, 3, 'inOut'], [0.5, -5, 'out'], [0.75, 0, 'out']] },
  { lean: [[0.1, 0], [0.3, 1.5, 'inOut'], [0.5, -2, 'overshoot'], [0.9, -1.5, 'inOut'], [1.2, 0, 'out']] },
  { headNod: [[0.2, 0], [0.32, -0.12, 'inOut'], [0.5, 0.25, 'overshoot'], [0.9, 0.15, 'inOut'], [1.2, 0, 'out']] },
  { smile: [[0.1, 0.2], [0.5, 0.8, 'out'], [0.9, 0.75, 'inOut'], [1.2, 0.45, 'out']] },
  { squint: [[0.2, 0], [0.5, 0.35, 'out'], [0.9, 0.3, 'inOut'], [1.2, 0.05, 'out']] },
  { mouthOpen: [[0.3, 0], [0.5, 0.3, 'out'], [0.9, 0.2, 'inOut'], [1.2, 0, 'out']] },
  { browL: [[0.2, 0], [0.5, 0.3, 'out'], [1.2, 0, 'out']] },
  { browR: [[0.2, 0], [0.52, 0.35, 'out'], [1.2, 0, 'out']] },
), { blendOut: 0.3 })

/* Straight up, the way a student asks. Brows up, mouth slightly open, eyes
   lift as the hand goes. 1.7 s. */
const raiseHand = action('raiseHand', 1.7, merge(
  reach(R, { s: 165, e: -8, w: -5 }, 0.42, 1.3, 1.7),
  handShape(R, { ...HAND_POSES.open, palm: 0.8, spread: 0.4 }, 0.22, 1.5),
  { lookY: [[0, 0], [0.16, -0.3, 'out'], [1.3, -0.25, 'inOut'], [1.7, 0, 'out']] },
  dip('browL', 0.5, 0.4, 1.7),
  dip('browR', 0.55, 0.44, 1.7),
  dip('mouthOpen', 0.15, 0.42, 1.7),
  dip('smile', 0.3, 0.42, 1.7, 0.15),
  { headNod: [[0.1, 0], [0.42, -0.1, 'overshoot'], [1.3, -0.08, 'inOut'], [1.7, 0, 'out']] },
  { lean: [[0.1, 0], [0.45, -1.5, 'overshoot'], [1.3, -1.2, 'inOut'], [1.7, 0, 'out']] },
))

/* Palm out at the chest, fingers up (the wrist flexes 60 so the fingers
   point up from a forearm that points at the body). The face sets. 1.5 s. */
const stopHand = action('stopHand', 1.5, merge(
  reach(R, { s: 14, e: 128, w: 60 }, 0.3, 1.15, 1.5),
  handShape(R, HAND_POSES.stop, 0.14, 1.32),
  dip('browL', 0.2, 0.3, 1.5),
  dip('browR', 0.22, 0.33, 1.5),
  dip('browInnerL', -0.12, 0.3, 1.5),
  dip('browInnerR', -0.1, 0.33, 1.5),
  dip('squint', 0.15, 0.3, 1.5),
  dip('smile', -0.1, 0.3, 1.5, 0.15),
  { headNod: [[0.05, 0], [0.3, 0.06, 'overshoot'], [1.15, 0.05, 'inOut'], [1.5, 0, 'out']] },
  { lean: [[0.05, 0], [0.35, -1, 'overshoot'], [1.15, -0.8, 'inOut'], [1.5, 0, 'out']] },
))

/* Forearm toward the body at chest height, palm up, the fingers curling in
   twice at 2 Hz; the head nods with each curl and tips a little. 1.6 s. */
const comeHere = action('comeHere', 1.6, merge(
  reach(R, { s: 25, e: 110, w: -10 }, 0.32, 1.2, 1.6),
  handShape(R, { ...HAND_POSES.open, spread: 0.3 }, 0.16, 1.42),
  { fR1: [[0.4, 0], [0.55, 0.8, 'out'], [0.75, 0.1, 'out'], [0.95, 0.8, 'out'], [1.15, 0.1, 'out'], [1.42, 0.25, 'out']] },
  { fR2: [[0.42, 0], [0.57, 0.8, 'out'], [0.77, 0.1, 'out'], [0.97, 0.8, 'out'], [1.17, 0.1, 'out'], [1.44, 0.3, 'out']] },
  { fR3: [[0.44, 0], [0.59, 0.75, 'out'], [0.79, 0.1, 'out'], [0.99, 0.75, 'out'], [1.19, 0.1, 'out'], [1.46, 0.35, 'out']] },
  { fR4: [[0.46, 0], [0.61, 0.7, 'out'], [0.81, 0.1, 'out'], [1.01, 0.7, 'out'], [1.21, 0.1, 'out'], [1.48, 0.4, 'out']] },
  { wristR: [[0.43, -10, 'overshoot'], [0.56, 2, 'out'], [0.76, -10, 'out'], [0.96, 2, 'out'], [1.16, -10, 'out'], [1.6, 0, 'out']] },
  { headNod: [[0.4, 0], [0.56, 0.1, 'out'], [0.76, 0.02, 'inOut'], [0.96, 0.1, 'out'], [1.2, 0.02, 'inOut'], [1.6, 0, 'out']] },
  { headTilt: [[0.1, 0], [0.4, 2, 'overshoot'], [1.2, 1.8, 'inOut'], [1.6, 0, 'out']] },
  dip('smile', 0.4, 0.35, 1.6, 0.15),
  dip('browL', 0.3, 0.3, 1.6),
  dip('browR', 0.3, 0.34, 1.6),
))

/* Both hands flat in front of the chest sliding over each other, 3 Hz for
   about 1.5 s: the elbows swing in anti-phase. A scheming grin. 1.9 s. */
const RUB: Arm = { s: 18, e: 105, w: 10 }
const rubHands = action('rubHands', 1.9, merge(
  raise(R, RUB, 0, 0.3),
  raise(L, RUB, 0.03, 0.3),
  { shoulderR: [[0.3, RUB.s, 'overshoot'], [1.5, RUB.s + 1, 'inOut']] },
  { shoulderL: [[0.33, RUB.s, 'overshoot'], [1.5, RUB.s + 0.6, 'inOut']] },
  { elbowR: oscillate(RUB.e, 7, 3, 3.5, 0.38) },
  { elbowL: oscillate(RUB.e, 7, 3, 3.5, 0.38, 1 / 6) },
  { wristR: oscillate(RUB.w, 6, 3, 3.5, 0.38, 0.05) },
  { wristL: oscillate(RUB.w, 6, 3, 3.5, 0.38, 1 / 6 + 0.05) },
  lower(R, 1.9),
  lower(L, 1.9),
  handShape(R, { ...HAND_POSES.flat, palm: 0.2 }, 0.2, 1.72),
  handShape(L, { ...HAND_POSES.flat, palm: 0.2 }, 0.24, 1.74),
  { smile: [[0.1, 0.2], [0.5, 0.6, 'out'], [1.6, 0.55, 'inOut'], [1.9, 0.3, 'out']] },
  dip('squint', 0.3, 0.45, 1.9),
  dip('browInnerL', -0.15, 0.4, 1.9),
  dip('browInnerR', -0.2, 0.44, 1.9),
  dip('browL', 0.15, 0.4, 1.9),
  { headNod: [[0.1, 0], [0.45, 0.12, 'overshoot'], [1.6, 0.1, 'inOut'], [1.9, 0, 'out']] },
  { lookX: [[0, 0], [0.3, -0.3, 'out'], [1.0, 0.3, 'inOut'], [1.6, -0.1, 'inOut'], [1.9, 0, 'out']] },
))

/* Index up beside the shoulder, the wrist wagging 3 times at 3 Hz with the
   head shaking against it. Stern brows. 1.7 s. */
const WAG: Arm = { s: 25, e: -120, w: 0 }
const fingerWag = action('fingerWag', 1.7, merge(
  raise(R, WAG, 0, 0.34),
  { shoulderR: [[0.34, WAG.s, 'overshoot'], [1.3, WAG.s + 0.8, 'inOut']] },
  { elbowR: [[0.4, WAG.e, 'overshoot'], [1.3, WAG.e - 0.6, 'inOut']] },
  { wristR: oscillate(WAG.w, 18, 3, 3, 0.42) },
  lower(R, 1.7),
  handShape(R, { ...HAND_POSES.point, palm: 1 }, 0.18, 1.5),
  { headTurn: oscillate(0, 0.08, 3, 3, 0.46) },
  dip('browL', -0.15, 0.34, 1.7),
  dip('browR', -0.12, 0.37, 1.7),
  dip('browInnerL', -0.2, 0.34, 1.7),
  dip('browInnerR', -0.25, 0.37, 1.7),
  dip('squint', 0.2, 0.36, 1.7),
  dip('smile', -0.1, 0.36, 1.7, 0.15),
  { headNod: [[0.05, 0], [0.34, 0.08, 'overshoot'], [1.3, 0.06, 'inOut'], [1.7, 0, 'out']] },
))

/* Both forearms turn out at waist height, palms up, as when explaining a
   thing; the head tips and the brows lift, mouth slightly open. 1.7 s. */
const SPREAD: Arm = { s: 32, e: 55, w: -30 }
const handsSpread = action('handsSpread', 1.7, merge(
  reach(R, SPREAD, 0.34, 1.3, 1.7),
  merge(raise(L, { ...SPREAD, s: 30 }, 0.05, 0.34), hold(L, { ...SPREAD, s: 30 }, 0.39, 1.33), lower(L, 1.7)),
  handShape(R, HAND_POSES.open, 0.18, 1.52),
  handShape(L, HAND_POSES.open, 0.23, 1.54),
  dip('browL', 0.25, 0.34, 1.7),
  dip('browR', 0.3, 0.38, 1.7),
  dip('smile', 0.3, 0.4, 1.7, 0.15),
  dip('mouthOpen', 0.1, 0.4, 1.7),
  { headTilt: [[0.1, 0], [0.4, 2, 'overshoot'], [1.3, 1.7, 'inOut'], [1.7, 0, 'out']] },
  { lean: [[0.1, 0], [0.45, 1, 'overshoot'], [1.3, 0.8, 'inOut'], [1.7, 0, 'out']] },
))

/* Palms together at the chest, fingers up, and the head bows over them with
   soft eyes. The left hand lands a beat later and both wrists finish the
   fold last, so the hands meet rather than snap. 2.1 s. */
const NAMASTE: Arm = { s: 20, e: 110, w: 75 }
const namaste = action('namaste', 2.1, merge(
  merge(raise(R, NAMASTE, 0, 0.42), hold(R, NAMASTE, 0.42, 1.65), lower(R, 2.1)),
  merge(raise(L, NAMASTE, 0.05, 0.42), hold(L, NAMASTE, 0.47, 1.68), lower(L, 2.1)),
  handShape(R, { ...HAND_POSES.flat, palm: 0.05 }, 0.25, 1.9),
  handShape(L, { ...HAND_POSES.flat, palm: 0.05 }, 0.3, 1.92),
  { headNod: [[0.3, 0], [0.75, 0.25, 'overshoot'], [1.5, 0.22, 'inOut'], [2.1, 0, 'out']] },
  { bow: [[0.3, 0], [0.8, 0.15, 'overshoot'], [1.5, 0.13, 'inOut'], [2.1, 0, 'out']] },
  { blinkL: [[0.5, 0], [0.8, 0.5, 'inOut'], [1.5, 0.45, 'inOut'], [1.9, 0, 'out']] },
  { blinkR: [[0.52, 0], [0.82, 0.5, 'inOut'], [1.5, 0.45, 'inOut'], [1.92, 0, 'out']] },
  dip('smile', 0.4, 0.6, 2.1, 0.15),
  dip('squint', 0.1, 0.6, 2.1),
  dip('browL', 0.1, 0.6, 2.1),
  dip('browR', 0.12, 0.64, 2.1),
))

export const HAND_ACTIONS: Record<string, Action> = {
  wave, waveBig, point, pointUp, pointAtScreen, presentLeft, presentRight,
  thumbsUp, thumbsDown, okSign, clap, handsOnHips, armsCrossed, shrug, facepalm,
  chinThink, scratchHead, countOne, countTwo, countThree, fistPump, raiseHand,
  stopHand, comeHere, rubHands, fingerWag, handsSpread, namaste,
}
