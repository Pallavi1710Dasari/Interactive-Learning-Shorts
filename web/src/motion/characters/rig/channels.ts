/* The rig is a flat set of numeric channels. Every action, expression and
 * idle behaviour writes numbers into these; the renderer reads them and
 * draws. Nothing else crosses that boundary, which is what lets a head
 * shake, a smile and a wave all run at once without knowing about each
 * other: they touch different channels, and where they touch the same one
 * the layer order (see compose.ts) decides.
 *
 * Units: angles in degrees, blends 0..1, signed blends -1..1, offsets in
 * viewBox px. Arms: 0 hangs straight down, positive lifts away from the
 * body, the same for both sides (the renderer mirrors). */

export const CHANNELS = {
  /* whole body */
  bodyY: 0, // bounce, px, negative is up
  bodyX: 0, // weight shift, px
  bodyScale: 1,
  lean: 0, // torso rotate about the hips, deg, positive leans to viewer's right
  bow: 0, // torso bends forward: 0..1
  breathe: 0, // 0..1, chest rise
  twist: 0, // shoulders slide, px

  /* head */
  headTilt: 0, // deg, roll
  headTurn: 0, // -1..1, yaw, negative looks to viewer's left
  headNod: 0, // -1..1, pitch, positive looks down
  headY: 0, // px, extra lift/drop

  /* eyes */
  blinkL: 0,
  blinkR: 0,
  lookX: 0, // -1..1
  lookY: 0, // -1..1, positive looks down
  squint: 0, // 0..1, lower lids rise (laugh, suspicion)
  pupil: 1, // pupil size, 1 normal

  /* brows: raise lifts the whole brow, inner lifts just the inner end
     (sad) or drops it (angry) */
  browL: 0, // -1..1
  browR: 0,
  browInnerL: 0, // -1..1, positive lifts inner end
  browInnerR: 0,

  /* mouth */
  mouthOpen: 0, // 0..1 jaw drop
  mouthWide: 0.35, // 0..1 corner spread
  smile: 0.15, // -1..1 corners up/down
  pucker: 0, // 0..1, pulls corners in and lips forward
  teeth: 0, // 0..1 upper teeth visibility when open
  tongue: 0,
  mouthX: 0, // -1..1, smirk, mouth slides sideways
  cheeks: 0, // 0..1 blush
  jawX: 0, // sideways jaw, for thinking

  /* arms, viewer's left is the character's right arm; we name by screen side */
  shoulderL: 8,
  elbowL: 6,
  wristL: 0,
  shoulderR: 8,
  elbowR: 6,
  wristR: 0,
  /* hands: fingers 1..4 index to pinky, 0 straight, 1 curled; thumb 0 out,
     1 tucked; spread 0..1; palm 0 side-on, 1 facing viewer */
  fL1: 0.25, fL2: 0.3, fL3: 0.35, fL4: 0.4, tL: 0.2, spreadL: 0.3, palmL: 0.3,
  fR1: 0.25, fR2: 0.3, fR3: 0.35, fR4: 0.4, tR: 0.2, spreadR: 0.3, palmR: 0.3,

  /* legs */
  kneeL: 0, // 0..1 bend
  kneeR: 0,
  stance: 0, // -1..1 weight on one foot

  /* secondary motion, -1..1, DERIVED by the life layer from how fast the
     head and body are moving; actions never write these. The renderer
     swings hairBack and the bun from hairSway, a braid from braidSway, a
     dupatta or long skirt from clothSway. */
  hairSway: 0,
  braidSway: 0,
  clothSway: 0,
} as const

export type Channel = keyof typeof CHANNELS
export type Pose = Record<Channel, number>

export const CHANNEL_NAMES = Object.keys(CHANNELS) as Channel[]

export function defaultPose(): Pose {
  return { ...CHANNELS }
}

/* Channels that stack rather than replace: a breath on top of a wave is
   still a breath. Everything else is a target the top layer wins. */
export const ADDITIVE = new Set<Channel>(['bodyY', 'bodyX', 'breathe', 'headY', 'twist'])
