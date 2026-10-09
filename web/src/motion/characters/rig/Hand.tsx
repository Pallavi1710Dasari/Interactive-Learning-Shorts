/* A procedural hand: palm, four two-segment fingers and a thumb, drawn from
 * seven numbers so any two poses blend by lerping the numbers. There is no
 * drawing per pose; a fist and an open hand are the same code at different
 * curls.
 *
 * Local frame: wrist at (0,0), fingers extend toward +y, thumb on +x. The
 * renderer rotates and mirrors this group, so nothing here knows which arm
 * it is on or which way is up.
 *
 * The look is the reference's big chunky hand: a 30 x 28 palm with a rounded
 * heel, fat fingers of radius 4.5 that overlap and are told apart only by a
 * line where they meet. 'soft' draws that line a shade darker than the skin
 * (Arjun); 'line' draws it in the outline colour (Riya), whose reference has
 * no outline around the hand itself, only the finger lines and a palm crease.
 *
 * The curl is modelled in three dimensions and projected, not faked in two.
 * A finger curls around its knuckle axis; `palm` says where that axis points.
 * Side-on (palm 0) the finger folds across the picture plane and we see the
 * whole arc. Facing the viewer (palm 1) it folds toward us, so it only
 * shortens, and past 90 deg the fingertip comes back down over the palm. */
import { useId } from 'react'
import type { HandPose } from '../actions/handPoses'
import type { Palette } from '../skins/types'

type Pt = { x: number; y: number }

export type HandProps = {
  pose: HandPose
  palette: Palette
  /** 'soft': seams a shade darker (default). 'line': seams and crease in `outline`. */
  art?: 'soft' | 'line'
  /** the line colour for art 'line' */
  outline?: string
  /** 'flat' is one skin tone (default); 'lit' keeps the lamp gradient */
  shading?: 'flat' | 'lit'
}

/* Knuckle positions and lengths, index to pinky, from the reference: the
   middle knuckle sits highest, the pinky lowest and shortest. The fingers
   are 9 wide on 7 px centres, so neighbours overlap and read as one chunky
   mass with a seam, not four sausages. */
const FINGERS = [
  { x: 10.5, y: 27, len: 16, r: 4.5 },
  { x: 3.5, y: 28, len: 18, r: 4.5 },
  { x: -3.5, y: 27.5, len: 17, r: 4.5 },
  { x: -10.5, y: 25, len: 13, r: 4.5 },
]
const PROXIMAL = 0.55 // share of the finger length before the middle joint
const CURL_PROXIMAL = 55 // deg at full curl
const CURL_DISTAL = 70 // deg further at full curl
const FAN = 14 // deg, outermost fingers at full spread
const AXIS_MIN = 45 // deg, how far the curl axis leans toward the viewer at palm 0
const THUMB = { baseY: 8, meta: 9, tip: 6.5, r: 4.5 } // 15.5 long in two segments

const DEG = Math.PI / 180
const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const pt = (p: Pt) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`

/** Rotate a +y-pointing frame by `deg` toward +x. */
function rotate(v: Pt, deg: number): Pt {
  const s = Math.sin(deg * DEG)
  const c = Math.cos(deg * DEG)
  return { x: v.x * c + v.y * s, y: -v.x * s + v.y * c }
}

/** One finger segment of length `len` curled by `phi` deg about an axis that
    `palm` swings from 45 deg off the view normal (0, a three-quarter curl)
    to +x (1, curl straight toward the viewer), projected onto the picture
    plane. The axis never lies flat in the picture: a fully in-plane curl
    draws each finger as a hook, while the reference fist is four short
    stacked bumps, which is what a mostly foreshortened curl gives. */
function segment(len: number, phi: number, palm: number): Pt {
  const axis = (AXIS_MIN + (90 - AXIS_MIN) * palm) * DEG
  return { x: len * Math.sin(phi * DEG) * Math.cos(axis), y: len * Math.cos(phi * DEG) }
}

type FingerGeom = { k: Pt; p: Pt; t: Pt; r: number; curl: number }

function fingerGeom(i: number, curl: number, spread: number, palm: number, widthScale: number): FingerGeom {
  const f = FINGERS[i]
  const fan = ((1.5 - i) / 1.5) * FAN * spread
  const v1 = rotate(segment(f.len * PROXIMAL, curl * CURL_PROXIMAL, palm), fan)
  const v2 = rotate(segment(f.len * (1 - PROXIMAL), curl * (CURL_PROXIMAL + CURL_DISTAL), palm), fan)
  const k = { x: f.x * widthScale, y: f.y }
  const p = { x: k.x + v1.x, y: k.y + v1.y }
  return { k, p, t: { x: p.x + v2.x, y: p.y + v2.y }, r: f.r, curl }
}

/* The thumb sweeps in an arc across the palm: out and up beside the index at
   tuck 0 (the thumbs-up), then lying over the curled fingers at tuck 1. Its
   last joint flexes as it goes, so a tucked thumb hooks rather than lies like
   a stick. It roots on the palm's edge so its round end is the thenar bulge. */
function thumbGeom(tuck: number, wristHalf: number) {
  const base = { x: wristHalf + 0.5, y: THUMB.baseY }
  const a0 = 75 - 100 * tuck
  const a1 = a0 - (8 + 60 * tuck)
  const m = { x: base.x + THUMB.meta * Math.sin(a0 * DEG), y: base.y + THUMB.meta * Math.cos(a0 * DEG) }
  const t = { x: m.x + THUMB.tip * Math.sin(a1 * DEG), y: m.y + THUMB.tip * Math.cos(a1 * DEG) }
  return { base, m, t }
}

const CAP = { fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

/** A capsule chain: a seam band under a skin stroke. The band only shows
    where it pokes out past the fill over something already drawn, which is
    the line that keeps two neighbouring fingers from merging into one shape.
    The whole hand is masked to its own silhouette, so the band never shows
    against the background as an outline. */
function Capsule({ points, r, fill, seam }: { points: string; r: number; fill: string; seam: Seam }) {
  return (
    <>
      <polyline points={points} stroke={seam.color} strokeOpacity={seam.opacity} strokeWidth={r * 2 + seam.width * 2} {...CAP} />
      <polyline points={points} stroke={fill} strokeWidth={r * 2} {...CAP} />
    </>
  )
}

/** The crease a bent joint makes: a short dark line across the segment
    that ends at the joint. Fades in past 0.6 curl so a relaxed hand is smooth. */
function Crease({ at, along, r, strength, seam }: { at: Pt; along: Pt; r: number; strength: number; seam: Seam }) {
  if (strength <= 0) return null
  const len = Math.hypot(along.x, along.y) || 1
  const n = { x: (along.y / len) * r * 0.75, y: (-along.x / len) * r * 0.75 }
  return (
    <line
      x1={at.x - n.x}
      y1={at.y - n.y}
      x2={at.x + n.x}
      y2={at.y + n.y}
      stroke={seam.color}
      strokeOpacity={seam.opacity * 0.8 * strength}
      strokeWidth={seam.width}
      strokeLinecap="round"
    />
  )
}

type Seam = { color: string; opacity: number; width: number }

export function Hand({ pose, palette, art = 'soft', outline = '#1A1F3D', shading = 'flat' }: HandProps) {
  const gid = useId().replace(/[^a-zA-Z0-9_-]/g, '') + '-hand'
  const lit = shading === 'lit'
  const fill = lit ? `url(#${gid})` : palette.skin
  const seam: Seam = art === 'line' ? { color: outline, opacity: 1, width: 1.3 } : { color: palette.skinShade, opacity: 0.6, width: 1 }

  const palm = clamp01(pose.palm)
  const spread = clamp01(pose.spread)
  const tuck = clamp01(pose.thumb)
  const curls = [pose.f1, pose.f2, pose.f3, pose.f4].map(clamp01)
  const avgCurl = (curls[0] + curls[1] + curls[2] + curls[3]) / 4

  /* Side-on the hand is an edge, so the fingers stack a little closer and the
     palm narrows; the reference hand is chunky from every angle, so only a
     little. Curled fingers thicken the palm: a fist is a block, not a plate. */
  const widthScale = (0.86 + 0.14 * palm) * (1 + 0.06 * avgCurl)
  const knuckleHalf = 15 * widthScale + 2 * avgCurl
  const wristHalf = 12 * (0.9 + 0.1 * palm) + 1.5 * avgCurl
  const fistShade = clamp01((avgCurl - 0.6) / 0.4)

  const fingers = curls.map((c, i) => fingerGeom(i, c, spread, palm, widthScale))
  const thumb = thumbGeom(tuck, wristHalf)
  const thumbOver = tuck > 0.5
  const thumbPoints = `${pt(thumb.base)} ${pt(thumb.m)} ${pt(thumb.t)}`

  /* 30 wide at the knuckles, 28 tall, the heel rounded and tucked 4 px into
     the forearm so the wrist never shows a gap. */
  const palmPath = [
    `M ${-wristHalf},-4`,
    `C ${-wristHalf - 3},8 ${-knuckleHalf - 2},16 ${-knuckleHalf},26`,
    `C ${-knuckleHalf * 0.6},31 ${knuckleHalf * 0.6},31 ${knuckleHalf},26`,
    `C ${knuckleHalf + 2},16 ${wristHalf + 3},8 ${wristHalf},-4`,
    `C ${wristHalf * 0.5},-7 ${-wristHalf * 0.5},-7 ${-wristHalf},-4`,
    'Z',
  ].join(' ')
  /* The reference's palm crease: a curve across an open palm, gone side-on. */
  const creasePath = `M ${-knuckleHalf * 0.5},13 Q ${knuckleHalf * 0.05},19 ${knuckleHalf * 0.62},11`

  const thumbNode = (
    <>
      <Capsule points={thumbPoints} r={THUMB.r} fill={fill} seam={seam} />
      <Crease at={thumb.m} along={{ x: thumb.m.x - thumb.base.x, y: thumb.m.y - thumb.base.y }} r={THUMB.r} strength={clamp01((tuck - 0.5) / 0.5)} seam={seam} />
    </>
  )

  return (
    <g>
      <defs>
        {/* The silhouette, as a mask: seams may only show inside it. */}
        <mask id={gid + '-sil'} maskUnits="userSpaceOnUse" x="-50" y="-30" width="100" height="90">
          <path d={palmPath} fill="#fff" />
          <polyline points={thumbPoints} stroke="#fff" strokeWidth={THUMB.r * 2} {...CAP} />
          {fingers.map((f, i) => (
            <polyline key={i} points={`${pt(f.k)} ${pt(f.p)} ${pt(f.t)}`} stroke="#fff" strokeWidth={f.r * 2} {...CAP} />
          ))}
        </mask>
        {lit && (
          /* One lamp, upper left, shared by palm, fingers and thumb so the
             hand reads as one form. User-space so a straight finger (zero
             width bounding box) still gets painted. */
          <linearGradient id={gid} gradientUnits="userSpaceOnUse" x1={-14} y1={-4} x2={16} y2={46}>
            <stop offset="0" stopColor={palette.skinLight} />
            <stop offset="0.45" stopColor={palette.skin} />
            <stop offset="1" stopColor={palette.skinShade} />
          </linearGradient>
        )}
      </defs>

      <g mask={`url(#${gid}-sil)`}>
        {!thumbOver && thumbNode}

        <path d={palmPath} fill={fill} />
        <path d={creasePath} fill="none" stroke={seam.color} strokeOpacity={seam.opacity * clamp01((palm - 0.45) / 0.4) * (1 - fistShade)} strokeWidth={seam.width} strokeLinecap="round" />
        {/* The knuckle row darkens as the fingers close over it. */}
        <ellipse cx={0} cy={25} rx={knuckleHalf * 0.8} ry={3.5} fill={palette.skinShade} opacity={0.35 * fistShade * (0.4 + 0.6 * palm)} />

        {/* Pinky first so the index lands on top, as it does on a real hand
            seen from the thumb side. */}
        {[...fingers].reverse().map((f, j) => {
          const i = fingers.length - 1 - j
          const k = clamp01((f.curl - 0.6) / 0.4)
          return (
            <g key={i}>
              <Capsule points={`${pt(f.k)} ${pt(f.p)} ${pt(f.t)}`} r={f.r} fill={fill} seam={seam} />
              {/* The joint crease belongs to a finger seen bending across the
                  picture; a bump facing us has none, so it fades fast with palm. */}
              <Crease at={f.p} along={{ x: f.p.x - f.k.x, y: f.p.y - f.k.y }} r={f.r} strength={k * 0.6 * (1 - palm) * (1 - palm)} seam={seam} />
              {/* Under the lamp a curled knuckle facing it catches the light. */}
              {lit && <circle cx={f.k.x - 0.8} cy={f.k.y - 0.6} r={1.4} fill={palette.skinLight} opacity={0.4 * k * palm} />}
            </g>
          )
        })}

        {thumbOver && thumbNode}
      </g>
    </g>
  )
}
