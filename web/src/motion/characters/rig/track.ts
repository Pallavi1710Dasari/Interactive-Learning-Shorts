/* Keyframes, easing and sampling. Pure functions of time, so a frame can be
 * asked for twice and come back identical: the recorder depends on that. */
import type { Channel, Pose } from './channels'

export type Ease = 'linear' | 'in' | 'out' | 'inOut' | 'anticipate' | 'overshoot' | 'bounce' | 'hold'

/* [time (s), value, ease into this key] */
export type Key = [number, number, Ease?]
export type Tracks = Partial<Record<Channel, Key[]>>

export type Action = {
  name: string
  /** seconds, the length of one pass */
  duration: number
  loop?: boolean
  /** seconds to blend in from whatever came before, default 0.18 */
  blendIn?: number
  /** seconds to blend back out at the end, default 0.25 */
  blendOut?: number
  tracks: Tracks
  /** channels the action resets to the pose default while it runs, so a
      gesture that lifts an arm also opens the hand it inherited */
  group?: 'face' | 'head' | 'hands' | 'body' | 'talk'
}

export const ease: Record<Ease, (u: number) => number> = {
  linear: (u) => u,
  in: (u) => u * u * u,
  out: (u) => 1 - Math.pow(1 - u, 3),
  inOut: (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2),
  /* pulls back before it goes: the wind-up a real arm makes */
  anticipate: (u) => {
    const c = 1.70158
    return u * u * ((c + 1) * u - c)
  },
  /* goes past and settles: the follow-through a real arm makes */
  overshoot: (u) => {
    const c = 1.70158
    return 1 + (u - 1) * (u - 1) * ((c + 1) * (u - 1) + c)
  },
  bounce: (u) => {
    const n = 7.5625
    const d = 2.75
    if (u < 1 / d) return n * u * u
    if (u < 2 / d) return n * (u -= 1.5 / d) * u + 0.75
    if (u < 2.5 / d) return n * (u -= 2.25 / d) * u + 0.9375
    return n * (u -= 2.625 / d) * u + 0.984375
  },
  hold: (u) => (u >= 1 ? 1 : 0),
}

export function sampleKeys(keys: Key[], t: number): number {
  if (keys.length === 0) return 0
  if (t <= keys[0][0]) return keys[0][1]
  const last = keys[keys.length - 1]
  if (t >= last[0]) return last[1]
  for (let i = 1; i < keys.length; i++) {
    const [t1, v1, e = 'inOut'] = keys[i]
    const [t0, v0] = keys[i - 1]
    if (t <= t1) {
      const u = t1 === t0 ? 1 : (t - t0) / (t1 - t0)
      return v0 + (v1 - v0) * ease[e](u)
    }
  }
  return last[1]
}

/** Samples every track of an action at local time t (seconds). */
export function sampleAction(action: Action, t: number): Partial<Pose> {
  const local = action.loop ? ((t % action.duration) + action.duration) % action.duration : t
  const out: Partial<Pose> = {}
  for (const ch in action.tracks) {
    const keys = action.tracks[ch as Channel]
    if (keys) out[ch as Channel] = sampleKeys(keys, local)
  }
  return out
}

/** Time-scale an action's keys, for a slower or quicker read of the same move. */
export function retime(action: Action, factor: number): Action {
  const tracks: Tracks = {}
  for (const ch in action.tracks) {
    tracks[ch as Channel] = action.tracks[ch as Channel]!.map(([t, v, e]) => [t * factor, v, e])
  }
  return { ...action, duration: action.duration * factor, tracks }
}

/** Shift a set of keys later in time. */
export function delay(keys: Key[], by: number): Key[] {
  return keys.map(([t, v, e]) => [t + by, v, e])
}

/** Mirror an action from the left arm to the right, or play it on both. */
export function mirror(action: Action, name = action.name + 'R'): Action {
  const swap = (ch: string) => (ch.endsWith('L') ? ch.slice(0, -1) + 'R' : ch.endsWith('R') ? ch.slice(0, -1) + 'L' : ch)
  const tracks: Tracks = {}
  for (const ch in action.tracks) tracks[swap(ch) as Channel] = action.tracks[ch as Channel]
  const flipped: Channel[] = ['headTilt', 'headTurn', 'lookX', 'lean', 'bodyX', 'twist', 'mouthX', 'jawX', 'stance']
  for (const ch of flipped) if (tracks[ch]) tracks[ch] = tracks[ch]!.map(([t, v, e]) => [t, -v, e])
  return { ...action, name, tracks }
}

/** Scale how far an action departs from the rest pose: 0.5 is a half-hearted
    wave, 1.3 an emphatic one. Timing is untouched; use retime for that. */
export function scaleAction(action: Action, amplitude: number, rest: Pose): Action {
  const tracks: Tracks = {}
  for (const ch in action.tracks) {
    const base = rest[ch as Channel]
    tracks[ch as Channel] = action.tracks[ch as Channel]!.map(([t, v, e]) => [t, base + (v - base) * amplitude, e])
  }
  return { ...action, tracks }
}

export function both(action: Action, name = action.name + 'Both'): Action {
  const m = mirror(action)
  return { ...action, name, tracks: { ...m.tracks, ...action.tracks } }
}
