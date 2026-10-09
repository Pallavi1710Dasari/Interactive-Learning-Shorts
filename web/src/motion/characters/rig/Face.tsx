/* The face: eyes, brows, nose, mouth, cheeks and ears, plus the physics that
 * ties them together. A smile lifts the cheeks and narrows the eyes, a turned
 * head slides the features more than the skull, an open smiling mouth shows
 * teeth. Actions do not have to know any of that, which is why one wave looks
 * right on both characters.
 *
 * Drawn to reference/arjun.png and reference/riya.png: flat vector, no
 * filters, no gradients. Every shade is a flat shape a tone darker. The skin
 * picks the feature style (oval eyes and a full mouth for Arjun, dot eyes and
 * a line mouth for Riya) and every style still reads the same channels.
 *
 * Everything here is head-local: the origin is the head centre, skull rx 50
 * ry 56, chin at y=56. Features: eyes (+-20, -2), brows y=-18 from x=+-8 to
 * +-32, nose about (4, 12), mouth centre (0, 30), cheeks (+-30, 18), ears
 * (+-50, 2). The skull, hair and ear placement are composed in Character. */
import { useId, type JSX } from 'react'
import type { Pose } from './channels'
import type { Palette, Skin } from '../skins/types'

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t

/* ---------- derived physiology ---------- */

export type FacePhysiology = {
  smileUp: number
  squint: number
  /** Head pitch, with a bow folded in: the head drops as the torso does. */
  nod: number
  turn: number
  /** The transform the features ride on; `faceExtras` in a skin share it. */
  faceXf: string
  teethVis: number
}

/** Facts about faces, not choices an action makes. */
export function facePhysiology(pose: Pose): FacePhysiology {
  const smileUp = Math.max(0, pose.smile)
  const squint = clamp(pose.squint + smileUp * 0.3, 0, 1)
  const nod = clamp(pose.headNod + pose.bow * 0.6, -1, 1)
  const turn = pose.headTurn
  const teethVis = Math.max(pose.teeth, clamp((pose.mouthOpen - 0.12) / 0.1, 0, 1) * clamp((pose.smile - 0.2) / 0.15, 0, 1))
  /* Features ride the front of the skull, so they travel further than the
     skull does when the head yaws; the nose, nearest the viewer, furthest.
     The pitch squash pivots at y=12, the middle of the feature block. */
  const faceXf = `translate(${turn * 16} ${nod * 9 + 12}) scale(1 ${1 - Math.abs(nod) * 0.04}) translate(0 -12)`
  return { smileUp, squint, nod, turn, faceXf, teethVis }
}

/* ---------- the features ---------- */

export function Face({ pose, phys, skin }: { pose: Pose; phys: FacePhysiology; skin: Skin }): JSX.Element {
  const p = skin.palette
  const { smileUp, squint, nod, turn, faceXf, teethVis } = phys
  const line = skin.art === 'line'
  const mouth = mouthGeom(pose, skin.mouthStyle)
  /* Arjun's cheeks are solid discs; Riya's a faint wash. The blush channel
     brings either up to full. */
  const cheekBase = line ? 0.35 : 0.9
  return (
    <>
      <g transform={faceXf}>
        {[-1, 1].map((s) => (
          <circle key={s} cx={s * 30} cy={18 - smileUp * 3} r={line ? 8.5 : 7} fill={p.blush} opacity={cheekBase + pose.cheeks * (1 - cheekBase)} />
        ))}
        {(['L', 'R'] as const).map((side) =>
          skin.eyes === 'oval' ? (
            <OvalEye key={side} side={side} blink={side === 'L' ? pose.blinkL : pose.blinkR} squint={squint} lookX={pose.lookX} lookY={pose.lookY} pupil={pose.pupil} turn={turn} p={p} />
          ) : (
            <DotEye key={side} side={side} blink={side === 'L' ? pose.blinkL : pose.blinkR} squint={squint} lookX={pose.lookX} lookY={pose.lookY} turn={turn} color={skin.outline} />
          ),
        )}
        <Brow side="L" raise={pose.browL} inner={pose.browInnerL} color={line ? skin.outline : p.brow} weight={skin.browWeight} />
        <Brow side="R" raise={pose.browR} inner={pose.browInnerR} color={line ? skin.outline : p.brow} weight={skin.browWeight} />
        <g transform={`translate(${pose.mouthX * 4 + pose.jawX * 3} 30)`}>
          {skin.mouthStyle === 'full' ? (
            <FullMouth m={mouth} open={mouth.open} pucker={pose.pucker} teeth={teethVis} tongue={pose.tongue} p={p} />
          ) : (
            <LineMouth m={mouth} color={skin.outline} />
          )}
        </g>
      </g>
      <g transform={`translate(${turn * 20} ${nod * 9})`}>
        <Nose color={line ? skin.outline : p.skinShade} width={line ? 1.6 : 2.2} />
      </g>
    </>
  )
}

/** One simple shape with one inner curve. `line` is the curve's colour: the
    shade for Arjun, the outline for Riya. Drawn as the viewer's right ear;
    Character mirrors the left with flip=-1. */
export function Ear({ x, flip, fill, p, line }: { x: number; flip: 1 | -1; fill: string; p: Palette; line?: string }): JSX.Element {
  return (
    <g transform={`translate(${x} 2) scale(${flip} 1)`}>
      <ellipse rx="7.5" ry="9.5" fill={fill} />
      {/* the fold of the ear, bulging toward the face */}
      <path d="M1.5 -5 C-3.5 -3 -3.5 3.5 0.5 5.5" fill="none" stroke={line ?? p.skinShade} strokeWidth="1.8" strokeLinecap="round" />
    </g>
  )
}

/** A bent stroke shaped like a "<": the bridge runs from brow level down
    and a little left, then the base turns back down and right. Both
    references draw the nose this way, and the slight lean is what makes a
    front view read as a face with a side. */
function Nose({ color, width }: { color: string; width: number }) {
  return <path d="M8 -5 C7 2 4 9.5 0.5 14.5 C-0.2 15.8 0.6 17.6 2.6 17.8 Q4.4 18 5.8 17.2" fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />
}

/* ---------- eyes ---------- */

/** Arjun's eye: a dark vertical oval with one catchlight and no white. The
    lids are a clip, not skin painted over the oval: the eye is cropped to
    the band between the upper lid (down with blink) and the lower lid (up
    with squint), so no anti-aliased edge of the oval shows through a lid. */
function OvalEye({ side, blink, squint, lookX, lookY, pupil, turn, p }: { side: 'L' | 'R'; blink: number; squint: number; lookX: number; lookY: number; pupil: number; turn: number; p: Palette }) {
  const u = useId().replace(/:/g, '')
  const x = side === 'L' ? -20 : 20
  /* The eye on the far side of a turn foreshortens, the near one opens a touch. */
  const far = side === 'L' ? turn > 0 : turn < 0
  const sx = far ? 1 - Math.abs(turn) * 0.18 : 1 + Math.abs(turn) * 0.06
  const rx = 3.8
  const ry = 5.4 * (0.85 + pupil * 0.15)
  const top = -ry + clamp(blink, 0, 1) * 2 * ry
  const bottom = ry - clamp(squint, 0, 1) * 0.3 * 2 * ry
  /* With no white there is nothing to roll, so a glance is the whole oval sliding. */
  return (
    <g transform={`translate(${x + lookX * 3} ${-2 + lookY * 2.5}) scale(${sx} 1)`}>
      <clipPath id={`eye-${u}`}>
        <rect x="-6" y={top} width="12" height={Math.max(0, bottom - top)} />
      </clipPath>
      <g clipPath={`url(#eye-${u})`}>
        <ellipse rx={rx} ry={ry} fill={p.iris} />
        <circle cx="-1.3" cy="-2.2" r="1.1" fill="#FFFFFF" />
      </g>
      {/* a shut eye reads as a short lid line, not a blank patch of skin */}
      <path d={`M${-rx} ${top} Q0 ${top + 1.6} ${rx} ${top}`} fill="none" stroke={p.iris} strokeWidth="1.4" strokeLinecap="round" opacity={clamp((blink - 0.55) / 0.45, 0, 1)} />
    </g>
  )
}

/** Riya's eye: a tiny dark dot, taller than wide and leaning outward at the
    top, with a short lash flicking out from its upper corner. It closes by
    flattening, which is how a dot eye blinks in this style. Drawn as the
    viewer's right eye and mirrored for the left. */
function DotEye({ side, blink, squint, lookX, lookY, turn, color }: { side: 'L' | 'R'; blink: number; squint: number; lookX: number; lookY: number; turn: number; color: string }) {
  const s = side === 'L' ? -1 : 1
  const far = side === 'L' ? turn > 0 : turn < 0
  const sx = far ? 1 - Math.abs(turn) * 0.18 : 1 + Math.abs(turn) * 0.06
  const open = clamp(1 - clamp(blink, 0, 1) - clamp(squint, 0, 1) * 0.35, 0.14, 1)
  return (
    <g transform={`translate(${s * 20 + lookX * 2} ${-2 + lookY * 1.5}) scale(${sx * s} ${open})`}>
      <ellipse rx="2.4" ry="3.6" transform="rotate(16)" fill={color} />
      <path d="M1.6 -3 L3.6 -4.6" fill="none" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
    </g>
  )
}

/* ---------- brows ---------- */

/** A thin friendly arc, inner end level at rest, `weight` px thick at the
    middle and tapering to the ends as both references' brows do: a lens
    between two arcs, plus a thin round-capped stroke that softens its tips.
    Drawn as the viewer's right brow (inner end x=8, tail x=32) and mirrored
    for the left. `inner` rotates about the tail so only the inner end lifts
    (sad) or drops (angry). */
function Brow({ side, raise, inner, color, weight }: { side: 'L' | 'R'; raise: number; inner: number; color: string; weight: number }) {
  const w = weight * 0.7
  return (
    <g transform={`scale(${side === 'L' ? -1 : 1} 1) translate(0 ${-raise * 6}) rotate(${inner * 14} 32 -18)`}>
      <path d={`M8 -18 C12 -23.5 24 -25 32 -19 C24 ${-25 + w} 12 ${-23.5 + w} 8 -18 Z`} fill={color} stroke={color} strokeWidth={weight * 0.4} strokeLinejoin="round" strokeLinecap="round" />
    </g>
  )
}

/* ---------- mouth ---------- */

type MouthGeom = { hw: number; cy: number; uy: number; ly: number; open: number; d: string }

/** One closed path for the mouth opening, mouth-local, corners at y=cy.
    Shut, the two edges coincide in one bowed line. Opening drops the lower
    edge and, past half open, straightens the upper edge into the D of a
    laugh; with no smile to pull the corners up it bows upward instead, the
    O of a talking mouth. Riya's line mouth is the same geometry at two
    thirds the size. */
function mouthGeom(pose: Pose, style: Skin['mouthStyle']): MouthGeom {
  const open = clamp(pose.mouthOpen + pose.pucker * 0.18 * (1 - pose.mouthOpen), 0, 1)
  const smileUp = Math.max(0, pose.smile)
  const size = style === 'line' ? 0.62 : 1
  const hw = (13 + pose.mouthWide * 10) * (1 - pose.pucker * 0.4) * size
  const cy = -pose.smile * 7 * size
  const shut = pose.smile * 5 * size
  const uy = lerp(shut, cy - 4 * (1 - smileUp), clamp(open / 0.5, 0, 1))
  const ly = shut + open * 24 * size
  const d = `M${-hw} ${cy} C${-hw * 0.5} ${uy} ${hw * 0.5} ${uy} ${hw} ${cy} C${hw * 0.5} ${ly} ${-hw * 0.5} ${ly} ${-hw} ${cy} Z`
  return { hw, cy, uy, ly, open, d }
}

/** Arjun's mouth. Open: a warm interior, a white row of upper teeth under
    the top edge, a pinker lower lip along the bottom. Shut: the lip line and
    the lower lip, which is the same lower-lip band with nothing above it.
    The lower lip is the cheek pink, as in the reference, not the lip red. */
function FullMouth({ m, open, pucker, teeth, tongue, p }: { m: MouthGeom; open: number; pucker: number; teeth: number; tongue: number; p: Palette }) {
  const u = useId().replace(/:/g, '')
  const { hw, cy, uy, ly, d } = m
  const band = 3.5 + pucker * 2.5
  const gap = ly - uy
  const teethH = Math.min(7, 2 + gap * 0.3) * teeth
  const lower = `M${-hw} ${cy} C${-hw * 0.5} ${ly} ${hw * 0.5} ${ly} ${hw} ${cy} C${hw * 0.55} ${ly + band} ${-hw * 0.55} ${ly + band} ${-hw} ${cy} Z`
  return (
    <g data-part="mouth">
      <clipPath id={`mouth-${u}`}>
        <path d={d} />
      </clipPath>
      {/* the lower lip goes under the opening so the interior covers its top edge */}
      <path d={lower} fill={p.blush} />
      {gap > 0.5 && (
        <g clipPath={`url(#mouth-${u})`}>
          <path d={d} fill={p.mouth} />
          {/* the tongue is the floor of the mouth; the channel lifts it into view */}
          <ellipse cx="0" cy={ly + 5 - tongue * 10} rx={hw * 0.5} ry="5" fill={p.blush} />
          {teethH > 0.2 && <path d={`M${-hw} ${cy - 2} H${hw} V${cy + teethH} Q0 ${cy + teethH + 2.5} ${-hw} ${cy + teethH} Z`} fill="#FFFFFF" />}
        </g>
      )}
      {/* the shut smile is a lip line; it fades as the mouth opens, since the open laugh has no outline */}
      <path d={d} fill="none" stroke={p.lip} strokeWidth={2 + pucker * 2} strokeLinejoin="round" strokeLinecap="round" opacity={1 - clamp(open / 0.25, 0, 1)} />
    </g>
  )
}

/** Riya's mouth: a smile line that opens into a small dark rounded shape. */
function LineMouth({ m, color }: { m: MouthGeom; color: string }) {
  const { hw, cy, uy, ly, d } = m
  const gap = ly - uy
  return (
    <g data-part="mouth">
      {gap > 0.5 ? (
        <path d={d} fill={color} stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
      ) : (
        <path d={`M${-hw} ${cy} C${-hw * 0.5} ${uy} ${hw * 0.5} ${uy} ${hw} ${cy}`} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      )}
    </g>
  )
}
