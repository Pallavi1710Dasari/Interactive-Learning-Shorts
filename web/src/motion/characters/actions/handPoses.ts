/* Named hand shapes as finger-curl vectors, so a hand can blend from one to
 * the next instead of swapping drawings. Written by actions, read by the
 * renderer through the fL1..fL4, tL, spreadL, palmL channels (and R). */
import type { Channel, Pose } from '../rig/channels'
import type { Ease, Key, Tracks } from '../rig/track'

export type HandPose = { f1: number; f2: number; f3: number; f4: number; thumb: number; spread: number; palm: number }

export const HAND_POSES = {
  relaxed: { f1: 0.25, f2: 0.3, f3: 0.35, f4: 0.4, thumb: 0.2, spread: 0.3, palm: 0.3 },
  open: { f1: 0, f2: 0, f3: 0, f4: 0, thumb: 0, spread: 0.6, palm: 1 },
  flat: { f1: 0, f2: 0, f3: 0, f4: 0, thumb: 0.3, spread: 0.1, palm: 0.1 },
  fist: { f1: 1, f2: 1, f3: 1, f4: 1, thumb: 0.9, spread: 0, palm: 0.4 },
  point: { f1: 0, f2: 1, f3: 1, f4: 1, thumb: 0.6, spread: 0, palm: 0.2 },
  thumbsUp: { f1: 1, f2: 1, f3: 1, f4: 1, thumb: 0, spread: 0, palm: 0.2 },
  one: { f1: 0, f2: 1, f3: 1, f4: 1, thumb: 0.8, spread: 0.5, palm: 1 },
  two: { f1: 0, f2: 0, f3: 1, f4: 1, thumb: 0.8, spread: 0.5, palm: 1 },
  three: { f1: 0, f2: 0, f3: 0, f4: 1, thumb: 0.8, spread: 0.5, palm: 1 },
  ok: { f1: 0.7, f2: 0.1, f3: 0, f4: 0, thumb: 0.7, spread: 0.4, palm: 0.9 },
  cup: { f1: 0.45, f2: 0.5, f3: 0.5, f4: 0.55, thumb: 0.3, spread: 0.2, palm: 0.6 },
  stop: { f1: 0, f2: 0, f3: 0, f4: 0, thumb: 0.1, spread: 0.35, palm: 1 },
  /* a loose fist resting under the chin, knuckles toward the viewer */
  chinRest: { f1: 0.45, f2: 0.55, f3: 0.6, f4: 0.65, thumb: 0.3, spread: 0.15, palm: 0.4 },
} satisfies Record<string, HandPose>

export type HandPoseName = keyof typeof HAND_POSES

const FIELDS: (keyof HandPose)[] = ['f1', 'f2', 'f3', 'f4', 'thumb', 'spread', 'palm']

export function handChannel(side: 'L' | 'R', field: keyof HandPose): Channel {
  const map: Record<keyof HandPose, string> = { f1: 'f', f2: 'f', f3: 'f', f4: 'f', thumb: 't', spread: 'spread', palm: 'palm' }
  const n = field.startsWith('f') ? field.slice(1) : ''
  return `${map[field]}${side}${n}` as Channel
}

/* Arrival order, in ms after t. A closing hand curls pinky first and index
   last; an opening hand releases index first. The thumb settles after the
   fingers, and the palm turn rides along with the fingers. The user's
   directive: mind the finger position and movement. */
const CLOSE_ORDER: Record<keyof HandPose, number> = { f4: 0, f3: 0.015, f2: 0.03, f1: 0.045, thumb: 0.06, spread: 0.02, palm: 0.02 }
const OPEN_ORDER: Record<keyof HandPose, number> = { f1: 0, f2: 0.015, f3: 0.03, f4: 0.045, thumb: 0.06, spread: 0.02, palm: 0.02 }

/** Keys that bring one hand to a pose at time t, each finger arriving in
    the order a real hand uses. `from` is where the hand starts; without it
    the first key holds the target from t=0, which is a hand already posed. */
export function handKeys(side: 'L' | 'R', pose: HandPose, t: number, e: Ease = 'out', from?: HandPose): Tracks {
  const out: Tracks = {}
  const start = from ?? HAND_POSES.relaxed
  const closing = pose.f1 + pose.f2 + pose.f3 + pose.f4 >= start.f1 + start.f2 + start.f3 + start.f4
  const order = closing ? CLOSE_ORDER : OPEN_ORDER
  for (const f of FIELDS) {
    const keys: Key[] = []
    if (from) keys.push([Math.max(0, t - 0.16), from[f]])
    keys.push([t + order[f], pose[f], e])
    out[handChannel(side, f)] = keys
  }
  return out
}

export function handPoseOf(pose: Pose, side: 'L' | 'R'): HandPose {
  const p = {} as HandPose
  for (const f of FIELDS) p[f] = pose[handChannel(side, f)]
  return p
}
