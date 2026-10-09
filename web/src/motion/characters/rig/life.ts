/* The life layer. The user's words: "the motion animation is too mechanical".
 *
 * Keyframes describe where a joint should be. A body never quite gets there
 * on time: it has mass, so it starts late and settles past the mark; its
 * far parts trail its near parts; it never holds perfectly still; its hair
 * and clothes keep moving after it stops; and it leans to balance whatever
 * it lifts. This layer adds all of that to the composed pose, so every
 * action gets it without being rewritten, and takes it away with one option
 * when a keyframe needs to be seen bare.
 *
 * It is still a pure function of (timeline, t). The springs are stepped at
 * a fixed 240 Hz from t=0, and a cache keyed by the timeline object lets
 * a monotonic clock continue from the last step instead of starting over.
 * A seek backwards starts over, which costs about a millisecond per second
 * of timeline. */
import { CHANNEL_NAMES, type Channel, type Pose } from './channels'

export type LifeOptions = {
  /** springs: inertia and settle. 0 turns them off */
  mass?: number
  /** distal joints trail proximal ones */
  lag?: number
  /** a held pose keeps moving a little */
  drift?: number
  /** hair and cloth swing from head and body motion */
  secondary?: number
  /** the body leans away from a lifted arm, the head toward the hand */
  balance?: number
}

export const STEP = 1 / 240
const RING = 32 // 133 ms of history for the lag

type Cls = 'lid' | 'mouth' | 'face' | 'eye' | 'head' | 'arm' | 'hand' | 'body' | 'sway'

function classOf(ch: Channel): Cls {
  if (/^blink/.test(ch)) return 'lid'
  if (/^(mouth|pucker|teeth|tongue|jawX)/.test(ch)) return 'mouth'
  if (/^(brow|smile|cheeks|squint|pupil)/.test(ch)) return 'face'
  if (/^look/.test(ch)) return 'eye'
  if (/^head/.test(ch)) return 'head'
  if (/^(shoulder|elbow|wrist)/.test(ch)) return 'arm'
  if (/^(f[LR]\d|t[LR]|spread|palm)/.test(ch)) return 'hand'
  if (/Sway$/.test(ch)) return 'sway'
  return 'body'
}

/* Natural frequency (rad/s) and damping ratio per class. Settling time is
   about 4/(z*w): an arm settles in 300 ms with a 2 to 3 percent overshoot;
   the mouth is near-critical and fast so lip sync stays crisp. */
const SPRING: Record<Cls, { w: number; z: number }> = {
  lid: { w: 0, z: 1 },
  mouth: { w: 70, z: 1 },
  face: { w: 40, z: 0.9 },
  eye: { w: 55, z: 0.9 },
  head: { w: 20, z: 0.75 },
  arm: { w: 18, z: 0.75 },
  hand: { w: 28, z: 0.8 },
  body: { w: 14, z: 0.85 },
  sway: { w: 0, z: 1 },
}

/* Lag in seconds before the parent joint. Fingers trail the wrist trails
   the elbow trails the shoulder. */
function lagOf(ch: Channel): number {
  if (/^elbow/.test(ch)) return 0.03
  if (/^wrist/.test(ch)) return 0.06
  if (/^(f[LR]\d|t[LR]|spread|palm)/.test(ch)) return 0.09
  if (/^head/.test(ch)) return 0.012
  return 0
}

/* How much a held channel wanders, in its own units. Nothing on the mouth
   or the lids: a lip or a blink that wanders reads as a tic. */
function driftOf(ch: Channel): number {
  switch (classOf(ch)) {
    case 'head': return ch === 'headTilt' ? 0.6 : ch === 'headY' ? 0.4 : 0.01
    case 'arm': return /^elbow/.test(ch) ? 0.6 : 0.8
    case 'hand': return /^(palm|spread)/.test(ch) ? 0.01 : 0.02
    case 'face': return /^brow/.test(ch) ? 0.03 : ch === 'squint' || ch === 'smile' ? 0.01 : 0
    case 'eye': return 0.03
    case 'body':
      if (ch === 'bodyX') return 1
      if (ch === 'bodyY') return 0.4
      if (ch === 'lean') return 0.3
      if (ch === 'twist') return 0.5
      if (ch === 'stance') return 0.02
      if (/^knee/.test(ch)) return 0.005
      return 0
    default: return 0
  }
}

/* A seeded phase per channel, so two characters with different seeds never
   wander in step. */
function hash(seed: number, i: number): number {
  let h = (seed * 374761393 + i * 668265263) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296
}

/* Three incommensurate sines: smooth, never periodic within a reel. */
function drift(t: number, seed: number, i: number): number {
  const p1 = hash(seed, i) * 6.283, p2 = hash(seed, i + 101) * 6.283, p3 = hash(seed, i + 202) * 6.283
  return 0.5 * Math.sin(6.283 * 0.11 * t + p1) + 0.3 * Math.sin(6.283 * 0.29 * t + p2) + 0.2 * Math.sin(6.283 * 0.67 * t + p3)
}

const N = CHANNEL_NAMES.length
const CLS = CHANNEL_NAMES.map(classOf)
const LAG_STEPS = CHANNEL_NAMES.map((c) => Math.round(lagOf(c) / STEP))
const DRIFT = CHANNEL_NAMES.map(driftOf)
const IDX = Object.fromEntries(CHANNEL_NAMES.map((c, i) => [c, i])) as Record<Channel, number>

type State = {
  n: number // substeps taken
  x: Float64Array
  v: Float64Array
  ring: Float64Array // RING rows of N raw values
  /* the two secondary springs: position and velocity */
  hair: [number, number]
  cloth: [number, number]
}

const cache = new WeakMap<object, State>()

function fresh(raw0: Pose): State {
  const x = new Float64Array(N), v = new Float64Array(N), ring = new Float64Array(RING * N)
  CHANNEL_NAMES.forEach((c, i) => {
    x[i] = raw0[c]
    for (let r = 0; r < RING; r++) ring[r * N + i] = raw0[c]
  })
  return { n: 0, x, v, ring, hair: [0, 0], cloth: [0, 0] }
}

const clamp = (u: number, lo: number, hi: number) => (u < lo ? lo : u > hi ? hi : u)

/* Lifting an arm moves the rest of the body. Applied to the raw target, so
   the springs smooth it like everything else. */
function balance(raw: Pose, k: number) {
  if (k <= 0) return
  const liftL = clamp((raw.shoulderL - 8) / 90, 0, 1)
  const liftR = clamp((raw.shoulderR - 8) / 90, 0, 1)
  const d = liftL - liftR
  raw.bodyX += 3 * d * k
  raw.lean += 1.5 * d * k
  raw.headTilt -= 2 * d * k
}

function spring(x: number, v: number, target: number, w: number, z: number): [number, number] {
  const a = w * w * (target - x) - 2 * z * w * v
  v += a * STEP
  x += v * STEP
  return [x, v]
}

/**
 * The composed pose with life on top. `rawAt` is the keyframe composition
 * (idle, expression, gesture, talk) at any time.
 */
export function applyLife(key: object, t: number, rawAt: (t: number) => Pose, o: LifeOptions): Pose {
  const mass = o.mass ?? 1, lag = o.lag ?? 1, dr = o.drift ?? 1, sec = o.secondary ?? 1, bal = o.balance ?? 1
  const n = Math.max(0, Math.floor(t / STEP))
  let s = cache.get(key)
  if (!s || s.n > n) {
    s = fresh(rawAt(0))
    cache.set(key, s)
  }
  const { x, v, ring } = s
  while (s.n < n) {
    s.n++
    const time = s.n * STEP
    const raw = rawAt(time)
    balance(raw, bal)
    const row = (s.n % RING) * N
    for (let i = 0; i < N; i++) ring[row + i] = raw[CHANNEL_NAMES[i]]
    for (let i = 0; i < N; i++) {
      const cls = CLS[i]
      if (cls === 'lid' || cls === 'sway') {
        x[i] = raw[CHANNEL_NAMES[i]]
        continue
      }
      const back = Math.min(RING - 1, Math.round(LAG_STEPS[i] * lag))
      const target = ring[(((s.n - back) % RING) + RING) % RING * N + i]
      const { w, z } = SPRING[cls]
      const r = spring(x[i], v[i], target, w, z)
      x[i] = r[0]
      v[i] = r[1]
    }
    /* secondary motion: hair from the head, cloth from the body, each an
       underdamped spring pulled by the parent's velocity */
    const vTurn = v[IDX.headTurn], vTilt = v[IDX.headTilt], vX = v[IDX.bodyX], vY = v[IDX.bodyY], vLean = v[IDX.lean]
    const hairTarget = -(0.06 * vTurn + 0.004 * vX + 0.0015 * vY + 0.004 * vTilt) * sec
    s.hair = spring(s.hair[0], s.hair[1], hairTarget, 14, 0.3)
    const clothTarget = -(0.006 * vX + 0.0025 * vY + 0.02 * vLean) * sec
    s.cloth = spring(s.cloth[0], s.cloth[1], clothTarget, 9, 0.25)
  }
  /* output: raw at the last substep blended toward the spring by mass, plus drift */
  const time = s.n * STEP
  const raw = rawAt(time)
  balance(raw, bal)
  const out = { ...raw }
  const seed = (key as { seed?: number }).seed ?? 1
  for (let i = 0; i < N; i++) {
    const c = CHANNEL_NAMES[i]
    const cls = CLS[i]
    if (cls !== 'lid' && cls !== 'sway') out[c] = raw[c] + (x[i] - raw[c]) * mass
    if (DRIFT[i] > 0 && dr > 0) out[c] += DRIFT[i] * dr * drift(time, seed, i)
  }
  out.hairSway = clamp(s.hair[0], -1, 1)
  out.braidSway = clamp(s.cloth[0] * 1.3, -1, 1)
  out.clothSway = clamp(s.cloth[0], -1, 1)
  return out
}
