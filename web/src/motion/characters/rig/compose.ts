/* Layers to a Pose. Bottom to top: default, idle, expression, gesture, talk.
 * Each layer samples its clip and is folded into the pose with a weight:
 * ADDITIVE channels add (a breath on top of a wave is still a breath), the
 * rest lerp toward the layer's value. Pure in (timeline, t), so a frame can
 * be re-asked and the recorder gets the same picture. */
import { ADDITIVE, CHANNEL_NAMES, defaultPose, type Channel, type Pose } from './channels'
import { sampleAction, type Action } from './track'
import { idlePose, type IdleOptions } from './idle'
import { applyLife, type LifeOptions } from './life'

export type Clip = { action: Action; start: number; stopAt?: number }

export type Timeline = {
  seed: number
  idle: IdleOptions
  /** the life layer (see life.ts); 0 shows the bare keyframes */
  life?: LifeOptions | 0
  expression?: Clip
  prevExpression?: Clip
  gesture?: Clip
  prevGesture?: Clip
  talk?: Clip
}

export const EXPRESSION_CROSSFADE = 0.35
export const DEFAULT_BLEND_IN = 0.18
export const DEFAULT_BLEND_OUT = 0.25

/* A lid is as closed as the most closed layer says. Lerping would let a
   half-lidded "bored" expression cancel every idle blink, and a face that
   never blinks is the first thing a viewer notices. */
const LIDS = new Set<Channel>(['blinkL', 'blinkR'])

/* What talk owns outright. Its head and brow emphasis ADD to whatever the
   expression and gesture set, so a nod of stress rides on top of a tilt. */
const TALK_REPLACES = new Set<Channel>(['mouthOpen', 'mouthWide', 'pucker', 'teeth', 'tongue'])

/* Channels a grouped action resets to default while it runs, so a gesture
   that lifts an arm also opens whatever hand shape it inherited. 'face' is
   deliberately absent: an expression is the layer under a face one-shot,
   not something to inherit, and a gasp must not erase a smile. */
const GROUPS: Partial<Record<NonNullable<Action['group']>, Channel[]>> = {
  hands: CHANNEL_NAMES.filter((c) => /^(shoulder|elbow|wrist|f[LR]\d|t[LR]|spread|palm)/.test(c)),
  head: ['headTilt', 'headTurn', 'headNod', 'headY'],
  body: ['bodyY', 'bodyX', 'bodyScale', 'lean', 'bow', 'twist', 'kneeL', 'kneeR', 'stance'],
}

const clamp01 = (u: number) => (u < 0 ? 0 : u > 1 ? 1 : u)
const lerp = (a: number, b: number, w: number) => a + (b - a) * w

function fold(pose: Pose, ch: Channel, v: number, w: number, add: boolean) {
  if (LIDS.has(ch)) pose[ch] = Math.max(pose[ch], v * w)
  else if (add || ADDITIVE.has(ch)) pose[ch] += v * w
  else pose[ch] = lerp(pose[ch], v, w)
}

/** Fold a sampled layer into the pose. `additive` forces ADD on channels that
    would otherwise lerp (talk's head and brow emphasis). */
function apply(pose: Pose, layer: Partial<Pose>, w: number, additive?: (ch: Channel) => boolean) {
  if (w <= 0) return
  for (const ch in layer) {
    const c = ch as Channel
    fold(pose, c, layer[c]!, w, additive ? additive(c) : false)
  }
}

/** Reset the group's unwritten channels toward default with the clip's weight. */
function applyGroupReset(pose: Pose, action: Action, w: number, rest: Pose) {
  const group = action.group && GROUPS[action.group]
  if (!group) return
  for (const ch of group) {
    if (ch in action.tracks || ADDITIVE.has(ch)) continue
    pose[ch] = lerp(pose[ch], rest[ch], w)
  }
}

/** Weight of a one-shot or looping clip at time t: ramps in over blendIn,
    holds, and ramps out over blendOut from its natural end (or from stopAt
    if that comes first). A loop has no natural end. */
export function clipWeight(clip: Clip, t: number): number {
  const { action, start, stopAt } = clip
  const local = t - start
  if (local < 0) return 0
  const blendIn = action.blendIn ?? DEFAULT_BLEND_IN
  const blendOut = action.blendOut ?? DEFAULT_BLEND_OUT
  const wIn = blendIn > 0 ? clamp01(local / blendIn) : 1
  let outAt = action.loop ? Infinity : action.duration
  if (stopAt !== undefined) outAt = Math.min(outAt, stopAt - start)
  const wOut = blendOut > 0 ? 1 - clamp01((local - outAt) / blendOut) : local < outAt ? 1 : 0
  return Math.min(wIn, wOut)
}

/** True once a clip can no longer contribute, so the runtime can drop it. */
export function clipDone(clip: Clip, t: number): boolean {
  const { action, start, stopAt } = clip
  const blendOut = action.blendOut ?? DEFAULT_BLEND_OUT
  let outAt = action.loop ? Infinity : start + action.duration
  if (stopAt !== undefined) outAt = Math.min(outAt, stopAt)
  return t >= outAt + blendOut
}

/* An expression crossfades from the previous one: for 0.35 s after its
   start, every channel either of them touches is a lerp between the two
   (the base pose standing in where one of them is silent). */
function applyExpression(pose: Pose, tl: Timeline, t: number) {
  const cur = tl.expression
  if (!cur) return
  const w = clamp01((t - cur.start) / EXPRESSION_CROSSFADE)
  const now = sampleAction(cur.action, t - cur.start)
  const prev = tl.prevExpression && w < 1 ? sampleAction(tl.prevExpression.action, t - tl.prevExpression.start) : undefined
  if (!prev) {
    apply(pose, now, w)
    return
  }
  const mixed: Partial<Pose> = {}
  for (const ch of new Set([...Object.keys(prev), ...Object.keys(now)] as Channel[])) {
    const base = ADDITIVE.has(ch) ? 0 : pose[ch]
    mixed[ch] = lerp(prev[ch] ?? base, now[ch] ?? base, w)
  }
  apply(pose, mixed, 1)
}

function applyGesture(pose: Pose, clip: Clip | undefined, t: number, rest: Pose) {
  if (!clip) return
  const w = clipWeight(clip, t)
  if (w <= 0) return
  applyGroupReset(pose, clip.action, w, rest)
  apply(pose, sampleAction(clip.action, t - clip.start), w)
}

function applyTalk(pose: Pose, clip: Clip | undefined, t: number) {
  if (!clip) return
  const w = clipWeight(clip, t)
  if (w <= 0) return
  apply(pose, sampleAction(clip.action, t - clip.start), w, (ch) => !TALK_REPLACES.has(ch))
}

/** The keyframe layers alone, exact at t. */
export function composeAt(tl: Timeline, t: number): Pose {
  const rest = defaultPose()
  const pose = defaultPose()
  apply(pose, idlePose(t, tl.seed, tl.idle), 1)
  applyExpression(pose, tl, t)
  applyGesture(pose, tl.prevGesture, t, rest)
  applyGesture(pose, tl.gesture, t, rest)
  applyTalk(pose, tl.talk, t)
  return pose
}

/** What the renderer draws: the layers, with the life layer on top unless
    the timeline switches it off. */
export function poseAt(tl: Timeline, t: number): Pose {
  if (tl.life === 0) return composeAt(tl, t)
  return applyLife(tl, t, (tt) => composeAt(tl, tt), tl.life ?? {})
}
