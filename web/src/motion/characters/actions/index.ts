/* The one place the runtime looks actions up. Each body part keeps its own
 * file so a wave and a wink can be worked on without reading each other;
 * this file only merges them and records which file each name came from,
 * so the playground can group its buttons without a second list to keep
 * in step. */
import type { Action } from '../rig/track'
import { EXPRESSIONS, FACE_ACTIONS } from './face'
import { HEAD_ACTIONS } from './head'
import { HAND_ACTIONS } from './hands'
import { BODY_ACTIONS } from './body'

export type { Action }
export { EXPRESSIONS }
export { HAND_POSES, handKeys } from './handPoses'

export const ACTIONS: Record<string, Action> = {
  ...FACE_ACTIONS,
  ...HEAD_ACTIONS,
  ...HAND_ACTIONS,
  ...BODY_ACTIONS,
}

export const ACTION_GROUPS: Record<'face' | 'head' | 'hands' | 'body', string[]> = {
  face: Object.keys(FACE_ACTIONS),
  head: Object.keys(HEAD_ACTIONS),
  hands: Object.keys(HAND_ACTIONS),
  body: Object.keys(BODY_ACTIONS),
}
