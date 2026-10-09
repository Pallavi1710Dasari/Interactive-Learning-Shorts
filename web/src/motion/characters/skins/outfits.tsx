/* Clothes and accessories. Static SVG fragments the renderer places inside
 * the groups that move; nothing here animates.
 *
 * Flat, as in reference/arjun.png and reference/riya.png: solid fills, a
 * shadow is a flat shape a shade darker, the only gradient is the one
 * vertical ramp on the tie shirt. No filters: when a skin asks for
 * `shading: 'lit'` the renderer puts its lamp over these fills itself.
 *
 * Body space is the 400x600 viewBox, drawn in a translate(200 0) frame so
 * the spine is x=0. Neck base y=196, shoulders y=205, the shoulder tip at
 * x=+-shoulderHalf (76 Arjun, 58 Riya), the torso tapering to the waist
 * half-width (56 at y=345, 40 at y=335), hips y=360, knees y=470, ankles
 * y=560, ground y=580. Head-local pieces (glasses, beard, flower) have their
 * origin at the skull centre: crown y=-56, chin y=56, ears at (+-50, 2).
 *
 * Sleeves are NOT here: Arm.tsx draws them from palette.sleeve so they move
 * with the arm. A top is the body of the garment plus whatever sits on it
 * (collar, placket, tie, belt). */
import { isValidElement, useId, type ReactNode } from 'react'
import type { Palette } from './types'
import type { BottomStyle, CharacterConfig, TopStyle } from './config'

/* ---------- options every exported drawer accepts ---------- */

/** Third argument of top/legs/faceExtras/neckExtras. Every field is
    optional so the old two-argument calls still compile. */
export type OutfitOpts = {
  /** 'soft': no outlines (Arjun). 'line': 1.3 px dark outlines on collar and pockets (Riya). */
  art?: 'soft' | 'line'
  /** a belt and buckle at the waist, on tucked-in tops */
  belt?: boolean
  /** the outline colour for art 'line' */
  outline?: string
  /** the shoulder tip x the top is drawn to; defaults by style (blouse 58, else 76) */
  shoulderHalf?: number
  /** the waist half-width a top tapers to and a bottom starts from; defaults by style */
  waistHalf?: number
}

const DEFAULTS: Required<Pick<OutfitOpts, 'art' | 'belt' | 'outline'>> = { art: 'soft', belt: false, outline: '#1A1F3D' }
const LINE_W = 1.3

/* The reference colours that are not in the palette: the belt, the buckle,
   the skirt pocket stitch, the earring gold, the flower. */
const BELT = '#8B5A2B'
const BUCKLE = '#C9A24A'
const POCKET_STITCH = '#8A8FB8'
const GOLD = '#D9A441'
const TIE_FALLBACK = '#1E2B4F'

/* The tie is palette.accent; the reference navy stands in if a hand-built
   palette leaves it empty. */
const accentOf = (p: Palette) => p.accent || TIE_FALLBACK

/* ---------- colour helpers, no HSL needed for a flat shade ---------- */

function mix(hex: string, toward: 0 | 255, k: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const ch = (s: number) => {
    const c = (n >> s) & 255
    return Math.round(c + (toward - c) * k)
  }
  return `#${((ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).padStart(6, '0')}`
}
const darken = (hex: string, k: number) => mix(hex, 0, k)
const lighten = (hex: string, k: number) => mix(hex, 255, k)

function useIds() {
  const u = useId().replace(/:/g, '')
  return (n: string) => `${n}-${u}`
}

/* ---------- the torso silhouette ---------- */

/* Which body a top is cut for. The male cut is the reference Arjun, the
   female cut the reference Riya; any other shoulder width interpolates. */
type Fit = { sh: number; wh: number; waistY: number; neckHalf: number }
const FIT = {
  male: { sh: 76, wh: 56 },
  female: { sh: 58, wh: 40 },
}

/* The waist the renderer's base torso derives from the shoulders (the same
   line as torsoMetrics in rig/Body.tsx), so cloth and body agree to the
   pixel: 58 gives 40 at y=335, 76 gives 56 at y=345. */
function waistFor(sh: number) {
  const t = Math.min(1.5, Math.max(-0.5, (sh - 58) / 18))
  return { wh: Math.round(40 + 16 * t), waistY: Math.round(335 + 10 * t) }
}

function fitFor(style: TopStyle | 'shirtTie', o: OutfitOpts): Fit {
  const base = style === 'blouse' ? FIT.female : FIT.male
  const sh = o.shoulderHalf ?? base.sh
  const w = waistFor(sh)
  return { sh, wh: o.waistHalf ?? w.wh, waistY: w.waistY, neckHalf: sh > 66 ? 15 : 12 }
}

/* One silhouette for every top: a shallow shoulder slope from the neck to
   the tip, a rounded cap under the arm, then a taper to the waist and a hem.
   Tops differ in the hem and in what sits on the cloth. */
function torso(f: Fit, { hem, hemHalf, neck }: { hem: number; hemHalf?: number; neck?: string }) {
  const { sh, wh, neckHalf: nh, waistY } = f
  const hh = hemHalf ?? wh
  /* the shoulder is one continuous curve from the neck out and down into
     the sleeve, as on the reference, not a corner */
  return [
    `M-${nh} 200`,
    `C-${nh + 22} 201 -${sh - 18} 204 -${sh} 216`,
    `C-${sh + 2} 228 -${sh - 1} 240 -${sh - 6} 252`,
    `C-${sh - 10} 290 -${wh + 6} 318 -${wh} ${waistY}`,
    `L-${hh} ${hem} L${hh} ${hem}`,
    `L${wh} ${waistY}`,
    `C${wh + 6} 318 ${sh - 10} 290 ${sh - 6} 252`,
    `C${sh - 1} 240 ${sh + 2} 228 ${sh} 216`,
    `C${sh - 18} 204 ${nh + 22} 201 ${nh} 200`,
    neck ?? `C${nh * 0.5} 206 -${nh * 0.5} 206 -${nh} 200`,
    'Z',
  ].join(' ')
}

/** A flat sliver of shade down the right side of the torso, where the body
    turns away from the lamp. */
function SideShade({ f, to, color, opacity = 1 }: { f: Fit; to: number; color: string; opacity?: number }) {
  const { sh, wh } = f
  return <path d={`M${sh - 6} 252 C${sh - 10} 290 ${wh + 6} 318 ${wh} ${to} L${wh - 9} ${to} C${wh - 4} 318 ${sh - 18} 290 ${sh - 15} 252 Z`} fill={color} opacity={opacity} />
}

/* ---------- collars, tie, belt ---------- */

/** Two pointed wings from the neck base, meeting in a V on the chest, over
    a flat shadow of themselves dropped 4 px onto the cloth. */
function Collar({ f, fill, shadow, line }: { f: Fit; fill: string; shadow: string; line?: string }) {
  const nh = f.neckHalf
  const wing = (s: 1 | -1) => `M${s * (nh - 1)} 196 L${s * (nh + 15)} 224 L${s * 4} 214 L0 206 Z`
  const stroke = line ? { stroke: line, strokeWidth: LINE_W, strokeLinejoin: 'round' as const } : {}
  return (
    <g>
      <path d={wing(-1)} transform="translate(0 4)" fill={shadow} />
      <path d={wing(1)} transform="translate(0 4)" fill={shadow} />
      {/* the stand, behind the neck */}
      <path d={`M-${nh + 2} 190 Q0 186 ${nh + 2} 190 L${nh + 1} 200 Q0 197 -${nh + 1} 200 Z`} fill={fill} {...stroke} />
      <path d={wing(-1)} fill={fill} {...stroke} />
      <path d={wing(1)} fill={fill} {...stroke} />
    </g>
  )
}

/** A long tie: the knot in the collar V, the blade widening to a point at
    the belt, a darker stripe down one edge as on the reference. */
function Tie({ color, tip }: { color: string; tip: number }) {
  const dark = darken(color, 0.3)
  const blade = `M-6 226 L6 226 L14 ${tip - 70} L16 ${tip - 20} L0 ${tip} L-16 ${tip - 20} L-14 ${tip - 70} Z`
  return (
    <g>
      <path d={blade} fill={color} />
      {/* the darker stripe down the right edge, about a third of the width */}
      <path d={`M6 226 L14 ${tip - 70} L16 ${tip - 20} L0 ${tip} L8 ${tip - 22} L8 ${tip - 70} L3 226 Z`} fill={dark} />
      {/* the knot, a soft trapezoid wider at the bottom, with its own shade */}
      <path d="M-9 203 Q0 199 9 203 L11 226 Q0 230 -11 226 Z" fill={color} />
      <path d="M3 203 L9 203 L11 226 Q7 228 3 228 Z" fill={dark} />
    </g>
  )
}

function Belt({ f }: { f: Fit }) {
  const { wh, waistY } = f
  return (
    <g>
      <path d={`M-${wh + 1} ${waistY - 6} L${wh + 1} ${waistY - 6} L${wh + 1} ${waistY + 7} L-${wh + 1} ${waistY + 7} Z`} fill={BELT} />
      <path d={`M-${wh + 1} ${waistY + 4} L${wh + 1} ${waistY + 4} L${wh + 1} ${waistY + 7} L-${wh + 1} ${waistY + 7} Z`} fill={darken(BELT, 0.3)} />
      <rect x="-9" y={waistY - 8} width="18" height="17" rx="2.5" fill={BUCKLE} />
      <rect x="-5.5" y={waistY - 4.5} width="11" height="10" rx="1.5" fill={BELT} />
      <rect x="-1" y={waistY - 8} width="2" height="17" fill={BUCKLE} />
    </g>
  )
}

/* ---------- tops ---------- */

/* Arjun's shirt: white at the collar grading to the hem tint, tucked into
   the belt, the tie down the placket. */
function ShirtTie({ p, f, belt }: { p: Palette; f: Fit; belt: boolean }) {
  const g = useIds()
  /* tucked in: the hem runs under the belt when there is one, otherwise
     it stops at the waist so no band of shirt shows over the trousers */
  const d = torso(f, { hem: belt ? f.waistY + 10 : f.waistY + 2 })
  return (
    <g transform="translate(200 0)">
      <defs>
        {/* white at the collar grading to the hem tint, which the palette
            carries as topShade for a white top */}
        <linearGradient id={g('shirt')} x1="0" y1="200" x2="0" y2="356" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor={p.topLight} />
          <stop offset="100%" stopColor={p.topShade} />
        </linearGradient>
      </defs>
      <path d={d} fill={`url(#${g('shirt')})`} />
      <SideShade f={f} to={f.waistY + 10} color={darken(p.topShade, 0.1)} opacity={0.7} />
      {/* placket: two faint lines, the tie covers the buttons */}
      <path d={`M-8 222 L-8 ${f.waistY + 4}`} stroke={p.topShade} strokeWidth="1" opacity="0.5" />
      <path d={`M8 222 L8 ${f.waistY + 4}`} stroke={p.topShade} strokeWidth="1" opacity="0.5" />
      <Collar f={f} fill="#FFFFFF" shadow={p.topShade} />
      <Tie color={accentOf(p)} tip={f.waistY + 4} />
      {belt && <Belt f={f} />}
    </g>
  )
}

/* A plain shirt: the top colour, a placket with buttons, a collar in the
   same cloth, a chest pocket. */
function Shirt({ p, f, belt, line }: { p: Palette; f: Fit; belt: boolean; line?: string }) {
  const d = torso(f, { hem: f.waistY + 10 })
  return (
    <g transform="translate(200 0)">
      <path d={d} fill={p.top} />
      <SideShade f={f} to={f.waistY + 10} color={p.topShade} />
      <path d={`M-7 212 L7 212 L7 ${f.waistY + 4} L-7 ${f.waistY + 4} Z`} fill={p.topLight} opacity="0.35" />
      {[246, 276, 306, 336].map((y) => (
        <circle key={y} cx="0" cy={y} r="2.6" fill={p.topShade} />
      ))}
      <path d="M-44 246 L-20 246 L-20 272 L-44 272 Z" fill="none" stroke={p.topShade} strokeWidth="1.2" />
      <Collar f={f} fill={p.topLight} shadow={p.topShade} line={line} />
      {belt && <Belt f={f} />}
    </g>
  )
}

function Polo({ p, f, line }: { p: Palette; f: Fit; line?: string }) {
  const d = torso(f, { hem: 372, hemHalf: f.wh + 2 })
  return (
    <g transform="translate(200 0)">
      <path d={d} fill={p.top} />
      <SideShade f={f} to={372} color={p.topShade} />
      <path d="M-6 208 L6 208 L6 250 L-6 250 Z" fill={p.topShade} />
      <circle cx="0" cy="230" r="2.4" fill={p.topLight} />
      <circle cx="0" cy="243" r="2.4" fill={p.topLight} />
      <Collar f={f} fill={p.topLight} shadow={p.topShade} line={line} />
    </g>
  )
}

function TShirt({ p, f }: { p: Palette; f: Fit }) {
  const d = torso(f, { hem: 375, hemHalf: f.wh + 3 })
  return (
    <g transform="translate(200 0)">
      <path d={d} fill={p.top} />
      <SideShade f={f} to={375} color={p.topShade} />
      {/* the ribbed crew neck, a band in the shade colour */}
      <path d={`M-${f.neckHalf + 5} 198 C-${f.neckHalf} 210 ${f.neckHalf} 210 ${f.neckHalf + 5} 198`} fill="none" stroke={p.topShade} strokeWidth="5" strokeLinecap="round" />
      {/* the hem band */}
      <path d={`M-${f.wh + 3} 368 L${f.wh + 3} 368 L${f.wh + 3} 375 L-${f.wh + 3} 375 Z`} fill={p.topShade} opacity="0.6" />
    </g>
  )
}

/* Riya's kurta from the for-loop deck: the V, the placket, a long hem over
   the hips with a side slit. */
function Kurta({ p, f }: { p: Palette; f: Fit }) {
  const nh = f.neckHalf
  const d = torso(f, { hem: 420, hemHalf: f.wh + 10, neck: `L${nh} 200 L0 236 L-${nh} 200` })
  return (
    <g transform="translate(200 0)">
      <path d={d} fill={p.top} />
      <SideShade f={f} to={f.waistY} color={p.topShade} />
      <path d={`M-${nh} 200 L0 236 L${nh} 200 L${nh + 4} 198 L0 242 L-${nh + 4} 198 Z`} fill={p.topLight} />
      <path d="M0 242 L0 420" stroke={p.topShade} strokeWidth="2" />
      <path d={`M-${f.wh + 9} 396 L-${f.wh + 10} 420`} stroke={p.topShade} strokeWidth="2" />
      <path d={`M${f.wh + 9} 396 L${f.wh + 10} 420`} stroke={p.topShade} strokeWidth="2" />
      <path d={`M-${f.wh + 10} 414 L${f.wh + 10} 414`} stroke={p.topLight} strokeWidth="1.4" opacity="0.6" />
    </g>
  )
}

function Hoodie({ p, f }: { p: Palette; f: Fit }) {
  const d = torso(f, { hem: 378, hemHalf: f.wh + 4 })
  const nh = f.neckHalf
  return (
    <g transform="translate(200 0)">
      {/* the hood hangs behind the neck; the head and neck draw over it */}
      <path d={`M-${nh + 22} 212 C-${nh + 24} 184 -20 172 0 172 C20 172 ${nh + 24} 184 ${nh + 22} 212 Z`} fill={p.topShade} />
      <path d={d} fill={p.top} />
      <SideShade f={f} to={378} color={p.topShade} />
      <path d={`M-${nh + 8} 198 C-${nh + 2} 214 ${nh + 2} 214 ${nh + 8} 198`} fill="none" stroke={p.topShade} strokeWidth="5" strokeLinecap="round" />
      <path d="M-9 212 C-11 234 -12 248 -10 262" fill="none" stroke={p.topLight} strokeWidth="2" strokeLinecap="round" />
      <path d="M9 212 C11 232 12 244 11 256" fill="none" stroke={p.topLight} strokeWidth="2" strokeLinecap="round" />
      {/* kangaroo pocket */}
      <path d={`M-${f.wh - 10} 310 L${f.wh - 10} 310 L${f.wh - 8} 368 L-${f.wh - 8} 368 Z`} fill={p.topShade} opacity="0.5" />
      <path d={`M-${f.wh + 4} 368 L${f.wh + 4} 368 L${f.wh + 4} 378 L-${f.wh + 4} 378 Z`} fill={p.topShade} opacity="0.6" />
    </g>
  )
}

/* Riya's blouse: periwinkle, a straight hem at the waist, a white pointed
   collar outlined in the line colour. */
function Blouse({ p, f, line }: { p: Palette; f: Fit; line?: string }) {
  const d = torso(f, { hem: f.waistY, hemHalf: f.wh + 2 })
  return (
    <g transform="translate(200 0)">
      <path d={d} fill={p.top} />
      <SideShade f={f} to={f.waistY} color={p.topShade} />
      <Collar f={f} fill="#FFFFFF" shadow={p.topShade} line={line} />
    </g>
  )
}

export function top(style: TopStyle | 'shirtTie', p: Palette, opts: OutfitOpts = {}): ReactNode {
  const o = { ...DEFAULTS, ...opts }
  const f = fitFor(style, o)
  const line = o.art === 'line' ? o.outline : undefined
  const node = (() => {
    switch (style) {
      case 'shirtTie':
        return <ShirtTie p={p} f={f} belt={o.belt} />
      case 'shirt':
        return <Shirt p={p} f={f} belt={o.belt} line={line} />
      case 'polo':
        return <Polo p={p} f={f} line={line} />
      case 'tshirt':
        return <TShirt p={p} f={f} />
      case 'kurta':
        return <Kurta p={p} f={f} />
      case 'hoodie':
        return <Hoodie p={p} f={f} />
      case 'blouse':
        return <Blouse p={p} f={f} line={line} />
    }
  })()
  /* the drawn width rides on the node so fitToShoulders knows it */
  return <g data-shoulder-half={f.sh}>{node}</g>
}

/** Kept for the old call sites. Tops are now drawn to the shoulder width in
    `opts.shoulderHalf` (or the style's default), so this scales only when
    the asked-for width differs from the one the node was drawn at, about
    the spine, x only. Pass `shoulderHalf` through `opts` instead. */
export function fitToShoulders(node: ReactNode, shoulderHalf: number): ReactNode {
  const drawn = isValidElement(node) ? Number((node.props as { 'data-shoulder-half'?: number })['data-shoulder-half']) : NaN
  if (!drawn || Math.abs(shoulderHalf / drawn - 1) < 0.001) return node
  return <g transform={`translate(200 0) scale(${(shoulderHalf / drawn).toFixed(3)} 1) translate(-200 0)`}>{node}</g>
}

/* ---------- legs ---------- */

type Side = 1 | -1
const ANKLE = 560
const GROUND = 580
/* every bottom starts here, under the hem of whatever top is worn */
const WAIST_TOP = 333

/* a full-length trouser leg: the outer edge from the waist over the hip to
   the ankle, the inner edge back up to the crotch */
function trouserLeg(s: Side, wh: number, ankle = 30) {
  return `M0 ${WAIST_TOP} L${s * wh} ${WAIST_TOP} C${s * (wh + 4)} 362 ${s * 46} 420 ${s * 38} 470 C${s * 34} 505 ${s * 31} 535 ${s * ankle} ${ANKLE + 2} L${s * 8} ${ANKLE + 2} C${s * 7} 530 ${s * 6} 480 ${s * 6} 445 C${s * 5} 425 ${s * 3} 405 0 395 Z`
}

/* a bare lower leg, from under a skirt or shorts to the shoe */
function bareLeg(s: Side, from: number) {
  return `M${s * 34} ${from} C${s * 35} 500 ${s * 29} 538 ${s * 26} ${ANKLE + 2} L${s * 9} ${ANKLE + 2} C${s * 8} 526 ${s * 6} 490 ${s * 8} ${from} Z`
}

/** A dark shoe with a sole: the toe points out a little. */
function Shoe({ s, p, flat = false }: { s: Side; p: Palette; flat?: boolean }) {
  const toe = flat ? 38 : 43
  const rise = flat ? 562 : ANKLE
  return (
    <g>
      <path d={`M${s * 5} ${rise} L${s * 29} ${rise} C${s * (toe - 4)} ${rise + 1} ${s * (toe + 2)} ${GROUND - 8} ${s * toe} ${GROUND - 3} L${s * 5} ${GROUND - 3} Z`} fill={p.shoe} />
      <path d={`M${s * 5} ${GROUND - 4} L${s * toe} ${GROUND - 4} L${s * (toe - 1)} ${GROUND} L${s * 5} ${GROUND} Z`} fill={darken(p.shoe, 0.35)} />
    </g>
  )
}

function Trousers({ p, wh, jeans = false }: { p: Palette; wh: number; jeans?: boolean }) {
  const sides: Side[] = [-1, 1]
  const crease = lighten(p.bottom, 0.14)
  return (
    <g transform="translate(200 0)">
      {sides.map((s) => (
        <g key={s}>
          <Shoe s={s} p={p} />
          <path d={trouserLeg(s, wh)} fill={p.bottom} />
          {jeans ? (
            <>
              <path d={`M${s * 40} 400 C${s * 40} 450 ${s * 32} 510 ${s * 30} 556`} fill="none" stroke="#E8D9A8" strokeWidth="1.4" opacity="0.7" />
              <path d={`M${s * 29} 556 L${s * 8} 556`} stroke={p.bottomShade} strokeWidth="1.5" />
            </>
          ) : (
            /* the pressed crease down the front of each leg */
            <path d={`M${s * 22} 400 C${s * 23} 450 ${s * 19} 510 ${s * 19} 558`} fill="none" stroke={crease} strokeWidth="1.3" opacity="0.6" />
          )}
        </g>
      ))}
      {/* the inner thigh turns away from the lamp: one flat shade on each leg */}
      <path d="M0 395 C6 410 8 460 8 500 L14 500 C14 460 12 420 6 398 Z" fill={p.bottomShade} />
      <path d="M0 395 C-6 410 -8 460 -8 500 L-14 500 C-14 460 -12 420 -6 398 Z" fill={p.bottomShade} />
      <path d={`M-${wh} ${WAIST_TOP} L${wh} ${WAIST_TOP} L${wh} ${WAIST_TOP + 9} L-${wh} ${WAIST_TOP + 9} Z`} fill={p.bottomShade} />
      {jeans && <path d="M0 342 L0 395" stroke={p.bottomShade} strokeWidth="1.5" />}
    </g>
  )
}

function Shorts({ p, wh }: { p: Palette; wh: number }) {
  const sides: Side[] = [-1, 1]
  const leg = (s: Side) => `M0 ${WAIST_TOP} L${s * wh} ${WAIST_TOP} C${s * (wh + 4)} 362 ${s * 40} 410 ${s * 38} 440 L${s * 6} 440 C${s * 5} 420 ${s * 3} 405 0 395 Z`
  return (
    <g transform="translate(200 0)">
      {sides.map((s) => (
        <g key={s}>
          <Shoe s={s} p={p} />
          <path d={bareLeg(s, 432)} fill={p.skin} />
          <ellipse cx={s * 19} cy="472" rx="7" ry="4" fill={p.skinShade} />
          <path d={leg(s)} fill={p.bottom} />
          <path d={`M${s * 38} 434 L${s * 6} 434`} stroke={p.bottomShade} strokeWidth="2" />
        </g>
      ))}
      <path d={`M-${wh} ${WAIST_TOP} L${wh} ${WAIST_TOP} L${wh} ${WAIST_TOP + 9} L-${wh} ${WAIST_TOP + 9} Z`} fill={p.bottomShade} />
    </g>
  )
}

/* Riya's skirt: A-line from the waist to below the knee at y=500, two curved
   pocket stitch lines, salmon calves and flats below. */
function Skirt({ p, wh, line }: { p: Palette; wh: number; line?: string }) {
  const sides: Side[] = [-1, 1]
  /* the hem flares 22 past the waist: 62 for the reference's 40 */
  const hh = wh + 22
  const d = `M-${wh} ${WAIST_TOP} L${wh} ${WAIST_TOP} C${wh + 4} 380 ${hh - 6} 450 ${hh} 500 Q0 509 -${hh} 500 C-${hh - 6} 450 -${wh + 4} 380 -${wh} ${WAIST_TOP} Z`
  return (
    <g transform="translate(200 0)">
      {sides.map((s) => (
        <g key={s}>
          <Shoe s={s} p={p} flat />
          <path d={bareLeg(s, 470)} fill={p.skin} />
        </g>
      ))}
      <path d={d} fill={p.bottom} />
      {sides.map((s) => (
        <path key={s} d={`M${s * (wh - 11)} 348 C${s * (wh - 11)} 372 ${s * (wh - 10)} 388 ${s * (wh - 1)} 391`} fill="none" stroke={line ? POCKET_STITCH : lighten(p.bottom, 0.3)} strokeWidth={LINE_W} strokeLinecap="round" />
      ))}
    </g>
  )
}

/* A salwar: loose through the thigh, gathered into a cuff at the ankle. */
function Salwar({ p, wh }: { p: Palette; wh: number }) {
  const sides: Side[] = [-1, 1]
  const leg = (s: Side) =>
    `M0 ${WAIST_TOP} L${s * wh} ${WAIST_TOP} C${s * (wh + 10)} 400 ${s * 44} 480 ${s * 27} 546 L${s * 27} ${ANKLE + 2} L${s * 8} ${ANKLE + 2} L${s * 8} 546 C${s * 6} 500 ${s * 3} 440 0 395 Z`
  return (
    <g transform="translate(200 0)">
      {sides.map((s) => (
        <g key={s}>
          <Shoe s={s} p={p} flat />
          <path d={leg(s)} fill={p.bottom} />
          <path d={`M${s * 27} 546 L${s * 8} 546`} stroke={p.bottomShade} strokeWidth="2" />
          <path d={`M${s * 32} 470 Q${s * 25} 510 ${s * 20} 544`} fill="none" stroke={p.bottomShade} strokeWidth="1.3" />
        </g>
      ))}
    </g>
  )
}

export function legs(style: BottomStyle, p: Palette, opts: OutfitOpts = {}): ReactNode {
  const o = { ...DEFAULTS, ...opts }
  const line = o.art === 'line' ? o.outline : undefined
  /* the waist follows the shoulders when given; a skirt alone defaults to
     the female waist, everything else to the male */
  const wh = o.waistHalf ?? (o.shoulderHalf ? waistFor(o.shoulderHalf).wh : style === 'skirt' ? FIT.female.wh : FIT.male.wh)
  switch (style) {
    case 'trousers':
      return <Trousers p={p} wh={wh} />
    case 'jeans':
      return <Trousers p={p} wh={wh} jeans />
    case 'shorts':
      return <Shorts p={p} wh={wh} />
    case 'skirt':
      return <Skirt p={p} wh={wh} line={line} />
    case 'salwar':
      return <Salwar p={p} wh={wh} />
  }
}

/* ---------- face extras, head-local ---------- */

function Glasses({ kind, p }: { kind: 'round' | 'rect'; p: Palette }) {
  const frame = p.hairShade
  /* lenses on the eyes at (+-20, -2); a flat pale fill so they read as glass */
  const lens = (x: number) =>
    kind === 'round' ? <circle cx={x} cy="-2" r="13" fill="#FFFFFF" fillOpacity="0.14" stroke={frame} strokeWidth="2" /> : <rect x={x - 14} y="-13" width="28" height="22" rx="4" fill="#FFFFFF" fillOpacity="0.14" stroke={frame} strokeWidth="2" />
  return (
    <g>
      {lens(-20)}
      {lens(20)}
      <path d={kind === 'round' ? 'M-7 -4 Q0 -9 7 -4' : 'M-6 -6 Q0 -9 6 -6'} fill="none" stroke={frame} strokeWidth="2" />
      <path d={kind === 'round' ? 'M-33 -4 L-48 0' : 'M-34 -6 L-48 0'} stroke={frame} strokeWidth="2" strokeLinecap="round" />
      <path d={kind === 'round' ? 'M33 -4 L48 0' : 'M34 -6 L48 0'} stroke={frame} strokeWidth="2" strokeLinecap="round" />
    </g>
  )
}

/* Stubble: one flat tint over the lower face, the mouth left clear. */
function Stubble({ p }: { p: Palette }) {
  return <path d="M-47 8 C-42 34 -27 52 0 56 C27 52 42 34 47 8 C36 20 20 22 0 22 C-20 22 -36 20 -47 8 Z" fill={p.hairShade} opacity="0.18" />
}

/* A short beard along the jaw with a moustache; the mouth stays clear so an
   open mouth never fights it. */
function ShortBeard({ p }: { p: Palette }) {
  return (
    <g>
      <path d="M-49 0 C-50 26 -34 52 0 60 C34 52 50 26 49 0 L39 8 C37 30 26 46 0 52 C-26 46 -37 30 -39 8 Z" fill={p.hair} />
      <path d="M-17 23 C-8 20 8 20 17 23 C10 28 -10 28 -17 23 Z" fill={p.hair} />
    </g>
  )
}

function Earrings() {
  /* small hoops hanging from the lobes, the ears being at (+-50, 2) */
  const hoop = (x: number) => (
    <g>
      <circle cx={x} cy="15" r="3.5" fill="none" stroke={GOLD} strokeWidth="1.8" />
      <circle cx={x} cy="21" r="2.2" fill={GOLD} />
    </g>
  )
  return (
    <g>
      {hoop(-51)}
      {hoop(51)}
    </g>
  )
}

/* A flower above the right ear, over the hair: five petals and a centre. */
function Flower() {
  const petals = [0, 72, 144, 216, 288]
  return (
    <g transform="translate(42 -38)">
      {petals.map((a) => (
        <ellipse key={a} cx="0" cy="-5" rx="3.6" ry="5" fill="#F25C8A" transform={`rotate(${a})`} />
      ))}
      <circle cx="0" cy="0" r="2.8" fill="#FFD36E" />
    </g>
  )
}

export function faceExtras(cfg: CharacterConfig, p: Palette, _opts: OutfitOpts = {}): ReactNode | null {
  const a = cfg.accessories
  const parts: ReactNode[] = []
  if (a.beard === 'stubble') parts.push(<Stubble key="beard" p={p} />)
  if (a.beard === 'short') parts.push(<ShortBeard key="beard" p={p} />)
  if (a.glasses && a.glasses !== 'none') parts.push(<Glasses key="glasses" kind={a.glasses} p={p} />)
  /* between the brows, which sit at y=-18 */
  if (a.bindi) parts.push(<circle key="bindi" cx="0" cy="-21" r="2.8" fill="#C0243A" />)
  if (a.earrings) parts.push(<Earrings key="earrings" />)
  if (a.flower) parts.push(<Flower key="flower" />)
  return parts.length ? <g>{parts}</g> : null
}

/* ---------- neck extras, body space ---------- */

function Necklace() {
  return (
    <g transform="translate(200 0)">
      <path d="M-13 200 C-8 226 8 226 13 200" fill="none" stroke={GOLD} strokeWidth="1.6" />
      <path d="M0 220 L-4 227 L0 234 L4 227 Z" fill={GOLD} />
    </g>
  )
}

/* A dupatta over the left shoulder, across the chest to the right hip, the
   tail behind the shoulder. A pale tint of the top with a border line. */
function Dupatta({ p, sh }: { p: Palette; sh: number }) {
  const x = sh - 4
  return (
    <g transform="translate(200 0)">
      <path d={`M-${x} 246 C-${x + 4} 230 -${x} 212 -${x - 8} 206 L-${x - 28} 210 C-${x - 32} 250 -8 300 20 330 C30 342 40 350 44 356 L40 372 C18 358 -6 334 -24 304 C-38 282 -${x - 6} 268 -${x} 246 Z`} fill={lighten(p.top, 0.6)} />
      <path d={`M-${x - 28} 210 C-${x - 32} 250 -8 300 20 330 C30 342 40 350 44 356`} fill="none" stroke={p.topShade} strokeWidth="1.4" />
    </g>
  )
}

export function neckExtras(cfg: CharacterConfig, p: Palette, opts: OutfitOpts = {}): ReactNode | null {
  const parts: ReactNode[] = []
  const t = cfg.outfit.top
  const sh = opts.shoulderHalf ?? (cfg.gender === 'female' ? FIT.female.sh : FIT.male.sh)
  /* the dupatta goes under the necklace, so it is first */
  if (t === 'kurta' && cfg.gender === 'female') parts.push(<Dupatta key="dupatta" p={p} sh={sh} />)
  if (cfg.accessories.necklace) parts.push(<Necklace key="necklace" />)
  /* collars are part of their tops now; the watch is drawn by the arm so it
     moves with the hand */
  return parts.length ? <g>{parts}</g> : null
}
