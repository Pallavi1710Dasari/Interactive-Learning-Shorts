/* The autonomic layer: what a body does when nobody asked it to do anything.
 * Breath, blinks, the eyes flicking to a new spot, weight drifting from foot
 * to foot. Without this a held pose is a mannequin.
 *
 * Everything here is a pure function of (t, seed). No Math.random, no state:
 * the recorder asks for frame 300 after frame 299 but a scrub bar asks for
 * them in any order, and both must see the same blink. Randomness comes from
 * hashing (seed, stream, event index), so each event has its own stable dice. */
import type { Pose } from './channels'
import { ease } from './track'

export type IdleOptions = {
  breath?: boolean
  blink?: boolean
  saccades?: boolean
  sway?: boolean
  /** 0..1, scales every idle amplitude except the blink (a half blink is a squint). Default 1 */
  liveliness?: number
}

/* streams, so the blink dice never line up with the saccade dice */
const BLINK = 1
const SACCADE = 2
const SHIFT = 3
const PHASE = 4

/** 0..1 from integer parts, splitmix-style mixing so neighbouring inputs land far apart. */
function hash(...parts: number[]): number {
  let h = 0x9e3779b9
  for (const p of parts) {
    h ^= Math.imul((p | 0) + 0x7f4a7c15, 0x85ebca6b)
    h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35)
    h ^= h >>> 16
  }
  return (h >>> 0) / 4294967296
}

const TAU = Math.PI * 2
const clamp01 = (u: number) => (u < 0 ? 0 : u > 1 ? 1 : u)

/* The i-th event of a stream starts after i random gaps in [min, max]. We
   walk from zero every call: a ten-minute clip is a few hundred additions,
   and the alternative, remembering where we got to, would break seeking. */
function lastEvent(seed: number, stream: number, min: number, max: number, t: number): { i: number; at: number } {
  let i = -1
  let at = 0
  for (;;) {
    const next = at + min + (max - min) * hash(seed, stream, i + 1)
    if (next > t) return { i, at: i < 0 ? -Infinity : at }
    i++
    at = next
  }
}

/* One blink: 90 ms down, fast off the mark, 180 ms back up and gentle at the end. */
function lid(u: number): number {
  if (u <= 0) return 0
  if (u < 0.09) return ease.out(u / 0.09)
  if (u < 0.27) return 1 - ease.inOut((u - 0.09) / 0.18)
  return 0
}

function blinkAt(seed: number, t: number): { l: number; r: number } {
  const ev = lastEvent(seed, BLINK, 2.8, 5.5, t)
  if (ev.i < 0) return { l: 0, r: 0 }
  const double = hash(seed, BLINK, ev.i, 1) < 1 / 7
  const curve = (u: number) => (double ? Math.max(lid(u), lid(u - 0.19)) : lid(u))
  const u = t - ev.at
  /* the right lid trails by 15 ms: real eyes are never in perfect step */
  return { l: curve(u), r: curve(u - 0.015) }
}

/* Where the eyes are between saccades: a 60 ms jump to a small target, a
   dwell, then a slow return most of the way to centre. The head joins one
   large jump in five, 120 ms behind, and comes back more slowly than the eye. */
function gazeAt(seed: number, t: number, k: number): { x: number; y: number; headX: number; headY: number } {
  const ev = lastEvent(seed, SACCADE, 1.5, 4, t)
  if (ev.i < 0) return { x: 0, y: 0, headX: 0, headY: 0 }
  const target = (i: number) => ({
    x: (hash(seed, SACCADE, i, 1) * 2 - 1) * 0.35 * k,
    y: (hash(seed, SACCADE, i, 2) * 2 - 1) * 0.2 * k,
  })
  const to = target(ev.i)
  /* the previous saccade left the eye a third of the way to its own target */
  const prev = ev.i > 0 ? target(ev.i - 1) : { x: 0, y: 0 }
  const from = { x: prev.x * 0.3, y: prev.y * 0.3 }
  const dwell = 0.3 + hash(seed, SACCADE, ev.i, 3) * 0.6
  const u = t - ev.at

  /* jump: from -> to; dwell; return: to -> 0.3*to, which is exactly where
     the next saccade will start from, so no event ever snaps */
  let x: number
  let y: number
  if (u < 0.06 + dwell) {
    const p = u < 0.06 ? ease.out(u / 0.06) : 1
    x = from.x + (to.x - from.x) * p
    y = from.y + (to.y - from.y) * p
  } else {
    const r = ease.inOut(clamp01((u - 0.06 - dwell) / 0.25))
    x = to.x * (1 - 0.7 * r)
    y = to.y * (1 - 0.7 * r)
  }

  const large = Math.hypot(to.x, to.y) > 0.25 * k
  const follows = large && hash(seed, SACCADE, ev.i, 4) < 0.2
  let env = 0
  if (follows) {
    const h = u - 0.12
    if (h < 0.2) env = ease.inOut(clamp01(h / 0.2))
    else if (h < 0.06 + dwell) env = 1
    else env = 1 - ease.inOut(clamp01((h - 0.06 - dwell) / 0.35))
  }
  return { x, y, headX: to.x * 0.3 * env, headY: to.y * 0.25 * env }
}

/* Weight moves to the other foot every 9 to 14 s, over 0.9 s, never all the way. */
function stanceAt(seed: number, t: number): number {
  const ev = lastEvent(seed, SHIFT, 9, 14, t)
  if (ev.i < 0) return 0
  const side = (i: number) => (i % 2 ? 1 : -1) * (0.5 + 0.5 * hash(seed, SHIFT, i, 1))
  const from = ev.i > 0 ? side(ev.i - 1) : 0
  const to = side(ev.i)
  return from + (to - from) * ease.inOut(clamp01((t - ev.at) / 0.9))
}

/* 4.2 s per breath, 14 a minute. The inhale takes 40% of it; the exhale
   drifts out and rests a moment at the bottom. */
function breathAt(seed: number, t: number): number {
  const u = (t / 4.2 + hash(seed, PHASE, 0)) % 1
  if (u < 0.4) return ease.inOut(u / 0.4)
  return 1 - ease.inOut(clamp01((u - 0.4) / 0.55))
}

/* two slow sines with unrelated periods, so the motion never visibly repeats */
function drift(t: number, seed: number, slot: number, p1: number, p2: number): number {
  const a = hash(seed, PHASE, slot, 1) * TAU
  const b = hash(seed, PHASE, slot, 2) * TAU
  return 0.6 * Math.sin((TAU * t) / p1 + a) + 0.4 * Math.sin((TAU * t) / p2 + b)
}

/** The idle contribution at time t. Additive channels (bodyX, breathe) are
    deltas; the rest are absolute and sit at the bottom of the stack, so any
    expression or gesture that writes the same channel wins. */
export function idlePose(t: number, seed: number, opts: IdleOptions = {}): Partial<Pose> {
  const k = opts.liveliness ?? 1
  const out: Partial<Pose> = {}

  if (opts.breath !== false) {
    const b = breathAt(seed, t) * k
    out.breathe = b
    /* the chin lifts a hair on the inhale: a chest never rises alone */
    out.headNod = -0.02 * b
  }

  if (opts.blink !== false) {
    const { l, r } = blinkAt(seed, t)
    out.blinkL = l
    out.blinkR = r
  }

  if (opts.saccades !== false) {
    const g = gazeAt(seed, t, k)
    out.lookX = g.x
    out.lookY = g.y
    out.headTurn = g.headX
    out.headNod = (out.headNod ?? 0) + g.headY
  }

  if (opts.sway !== false) {
    const stance = stanceAt(seed, t) * k
    out.stance = stance
    out.bodyX = (2 * drift(t, seed, 1, 7.3, 11.7) + 1.5 * stance) * k
    out.headTilt = 1.2 * drift(t, seed, 2, 5.1, 8.9) * k
    out.lean = 0.4 * stance
    /* brows are never dead still; this is a twitch below conscious notice */
    out.browL = 0.04 * drift(t, seed, 3, 6.3, 9.7) * k
    out.browR = 0.04 * drift(t, seed, 4, 7.1, 10.3) * k
  }

  return out
}
