/* One arm: shoulder, elbow and wrist as nested rotations, the sleeve over it,
 * the watch, and the Hand at the end of the chain.
 *
 * An arm's local frame hangs +y down the arm with +x toward the body; the
 * right arm is the left one mirrored about x=200, which is why the right arm's
 * lit-mode gradients (defined in Character) have their stops swapped.
 *
 * Geometry from the reference: pivot 6 px inside the shoulder tip at y=205,
 * upper arm 95 and forearm 85 as chunky capsules, 30 and 26 wide. A long
 * sleeve covers both and ends in a cuff; a short sleeve is a cap with a
 * straight hem over a bare arm. Neither reference outlines the arm, so
 * 'line' art leaves it plain and puts its lines on the hand only. */
import type { JSX } from 'react'
import type { Pose } from './channels'
import type { Skin } from '../skins/types'
import { Hand } from './Hand'
import { handPoseOf } from '../actions/handPoses'
import { SHOULDER_Y, clamp, shade, type Url } from './Body'

const UPPER = 95
const FORE = 85
const UPPER_W = 30
const FORE_W = 26
const SHOULDER_IN = 8
const CUFF_H = 11
const SHORT_SLEEVE = 40

const CAP = { fill: 'none', strokeLinecap: 'round' as const }

export function Arm({ side, pose, skin, url }: { side: 'L' | 'R'; pose: Pose; skin: Skin; url: Url }): JSX.Element {
  const shoulder = pose[`shoulder${side}`]
  const elbow = pose[`elbow${side}`]
  const wrist = pose[`wrist${side}`]
  const long = skin.sleeve === 'long'
  const flat = skin.shading !== 'lit'
  const p = skin.palette
  const pivotX = 200 - (skin.shoulderHalf - 6)
  const skinFill = flat ? p.skin : url('armSkin' + side)
  const sleeveFill = flat ? p.sleeve : url('sleeve' + side)
  const upper = long ? sleeveFill : skinFill
  const elbowCrease = clamp(elbow / 120, 0, 1) * 0.16
  return (
    <g data-part={`arm-${side}`} filter={flat ? undefined : url('armDrop')} transform={side === 'R' ? 'translate(400 0) scale(-1 1)' : undefined}>
      <g transform={`translate(${pivotX} ${SHOULDER_Y}) rotate(${shoulder})`}>
        {/* The capsule starts 5 px down the bone so its round cap meets the
            torso's shoulder slope as a deltoid bump, not a ball above it. */}
        <line x1="0" y1={SHOULDER_IN} x2="0" y2={UPPER} stroke={upper} strokeWidth={UPPER_W} {...CAP} />
        {!long && (
          <>
            {/* A short sleeve: a cap that rounds over the shoulder (high enough
                to cover the capsule's cap) and ends in a straight hem, a touch
                wider than the arm it covers. */}
            <path d={`M-17 6 C-17 -18 17 -18 17 6 L17 ${SHORT_SLEEVE} L-17 ${SHORT_SLEEVE} Z`} fill={sleeveFill} />
            {/* the hem's flat shadow on the arm below it */}
            <rect x="-15" y={SHORT_SLEEVE} width="30" height="4" fill={p.skinShade} opacity="0.5" />
          </>
        )}
        <g transform={`translate(0 ${UPPER}) rotate(${-elbow})`}>
          <line x1="0" y1="0" x2="0" y2={FORE} stroke={upper} strokeWidth={FORE_W} {...CAP} />
          {/* The inside of the elbow creases as the joint closes: one flat darker shape. */}
          <ellipse cx="6" cy="0" rx="3.5" ry="6" fill={long ? p.topShade : p.skinShade} opacity={elbowCrease} />
          {long && (
            /* The cuff: a band a little lighter than the sleeve with a seam
               line where the sleeve meets it, as on the reference shirt. */
            <g transform={`translate(0 ${FORE - CUFF_H + 1})`}>
              <rect x={-FORE_W / 2} y="0" width={FORE_W} height={CUFF_H} rx="1.5" fill={shade(p.sleeve, 0.3)} />
              <line x1={-FORE_W / 2 + 1} y1="0.6" x2={FORE_W / 2 - 1} y2="0.6" stroke={shade(p.sleeve, -0.18)} strokeWidth="1.2" strokeLinecap="round" />
            </g>
          )}
          {/* The watch sits on the character's left wrist (screen right), between the cuff and the palm. */}
          {skin.watch && side === 'R' && (
            <g transform={`translate(0 ${FORE - 5})`}>
              <rect x="-12" y="-3.2" width="24" height="6.4" rx="2.4" fill="#2A2E3A" />
              <circle r="5" fill="#DDE2EA" stroke="#2A2E3A" strokeWidth="1.6" />
              <circle r="0.9" fill="#2A2E3A" />
            </g>
          )}
          <g transform={`translate(0 ${FORE}) rotate(${-wrist})`}>
            <Hand pose={handPoseOf(pose, side)} palette={p} art={skin.art} outline={skin.outline} shading={skin.shading} />
          </g>
        </g>
      </g>
    </g>
  )
}
