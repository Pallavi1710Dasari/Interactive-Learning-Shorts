/* The body: the ground shadow, the legs, the torso and the neck, and the
 * transforms that make them one figure: breathing, lean, weight shift, bow.
 *
 * The head and the arms are not drawn here. They arrive as children and are
 * placed in the shoulder group, so they rise with each breath and drop with a
 * bow without knowing that either happened.
 *
 * Space: viewBox 0 0 400 600, ground y=580, hips (200,360), shoulders y=205,
 * neck base (200,196), head centre (200,120) so the chin sits at y=176.
 *
 * The torso and the legs are drawn here as skin-coloured bases in the exact
 * silhouette the outfits follow (`torsoOutline`, `legOutline`), so a short
 * sleeve shows an upper arm and a skirt shows calves without the outfit
 * drawing any skin itself. */
import type { JSX, ReactNode } from 'react'
import type { Pose } from './channels'
import type { Skin } from '../skins/types'

export const GROUND = 580
export const HIP = 360
export const SHOULDER_Y = 205
export const NECK_Y = 196
export const KNEE_Y = 470
export const ANKLE_Y = 562
const CHIN_Y = 176
const TORSO_H = HIP - SHOULDER_Y

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Mix a hex colour toward white (k>0) or black (k<0). Non-hex input passes through. */
export function shade(hex: string, k: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const ch = (shift: number) => {
    const c = (n >> shift) & 255
    const t = k < 0 ? 0 : 255
    return Math.round(c + (t - c) * Math.abs(k))
  }
  return `#${((ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).padStart(6, '0')}`
}

/** Resolves a def name to `url(#…)` for this Character instance. */
export type Url = (n: string) => string

/* ---------- silhouette ---------- */

export type TorsoMetrics = { shoulderHalf: number; neckHalf: number; waistY: number; waistHalf: number; hipHalf: number }

/** The numbers the torso is built from. Only shoulderHalf comes from the
    skin; the waist follows it so a build slider changes one thing and the
    whole figure stays in proportion. The two presets land on the contract
    exactly: Arjun (76) waist 56 at y=345, Riya (58) waist 40 at y=335. */
export function torsoMetrics(skin: Pick<Skin, 'shoulderHalf'>): TorsoMetrics {
  const sh = skin.shoulderHalf
  const t = clamp((sh - 58) / 18, -0.5, 1.5)
  const waistHalf = Math.round(40 + 16 * t)
  return { shoulderHalf: sh, neckHalf: sh > 66 ? 15 : 12, waistY: Math.round(335 + 10 * t), waistHalf, hipHalf: waistHalf + 2 }
}

/** Torso silhouette in body space (absolute x about 200): the neck base,
    shoulders sloping to the tip, a deltoid bulge, the chest down to the
    waist, straight across. It stops at the waist because every bottom
    starts above it (outfits' WAIST_TOP is 333) and is drawn first: a torso
    that ran on to the hips painted a band of cloth over the trousers and
    made a tucked top look untucked. */
export function torsoOutline(skin: Pick<Skin, 'shoulderHalf'>): string {
  const { shoulderHalf: sh, neckHalf: nh, waistY, waistHalf: wh } = torsoMetrics(skin)
  const l = (dx: number) => 200 - dx
  const r = (dx: number) => 200 + dx
  return [
    `M${l(nh)} 196`,
    /* down the left: shoulder slope, deltoid, chest to waist */
    `C${l(nh + 14)} 197 ${l(sh - 18)} 198 ${l(sh - 4)} 203`,
    `C${l(sh + 4)} 207 ${l(sh + 6)} 224 ${l(sh - 1)} 244`,
    `C${l(sh - 5)} 275 ${l(wh + 6)} 312 ${l(wh)} ${waistY}`,
    `L${r(wh)} ${waistY}`,
    /* up the right, the same curves read backwards */
    `C${r(wh + 6)} 312 ${r(sh - 5)} 275 ${r(sh - 1)} 244`,
    `C${r(sh + 6)} 224 ${r(sh + 4)} 207 ${r(sh - 4)} 203`,
    `C${r(sh - 18)} 198 ${r(nh + 14)} 197 ${r(nh)} 196`,
    'Z',
  ].join(' ')
}

/** One leg in body space from the hip (y=360) to the ankle (y=562): thigh,
    knee, calf, ankle. 'L' is screen left. Shoes are the outfit's. */
export function legOutline(skin: Pick<Skin, 'shoulderHalf'>, side: 'L' | 'R'): string {
  const s = side === 'L' ? -1 : 1
  const H = torsoMetrics(skin).hipHalf
  const x = (dx: number) => 200 + s * dx
  return [
    `M200 ${HIP}`,
    `L${x(H)} ${HIP}`,
    `C${x(H + 1)} 400 ${x(36)} 440 ${x(34)} ${KNEE_Y}`,
    `C${x(34)} 486 ${x(35)} 500 ${x(32)} 518`,
    `C${x(29)} 538 ${x(27)} 552 ${x(26)} ${ANKLE_Y}`,
    `L${x(9)} ${ANKLE_Y}`,
    `C${x(10)} 548 ${x(8)} 526 ${x(7)} 505`,
    `C${x(6)} 490 ${x(6)} 475 ${x(8)} 466`,
    `C${x(7)} 440 ${x(4)} 410 200 392`,
    'Z',
  ].join(' ')
}

/* ---------- the figure ---------- */

/** `behind` is drawn in the shoulder group's frame but before the torso, so
    hair that falls to the waist sits behind both the cloth and the neck
    while still rising with the breath and dropping with a bow. */
export function Body({ pose, skin, nod, url, behind, children }: { pose: Pose; skin: Skin; nod: number; url: Url; behind?: ReactNode; children: ReactNode }): JSX.Element {
  const p = skin.palette
  const flat = skin.shading !== 'lit'
  const m = torsoMetrics(skin)
  const sh = m.shoulderHalf
  const b = pose.breathe
  const lift = Math.max(0, -pose.bodyY)
  const groundScale = clamp(1 - lift / 140, 0.45, 1)
  const torso = torsoOutline(skin)
  const chinY = CHIN_Y + pose.headY + nod * 5
  /* Shoulders: the neck, head and arms rise with the breath and drop with a bow. */
  const shoulderXf = `translate(${pose.twist} ${-b * 2 + pose.bow * 26})`

  return (
    <>
      {/* Contact shadow. It shrinks and fades as the figure leaves the ground. */}
      <ellipse
        cx={200 + pose.bodyX + pose.stance * 3}
        cy={GROUND}
        rx={74 * groundScale * pose.bodyScale * skin.buildScale}
        ry={9 * groundScale}
        fill={url('ground')}
        opacity={groundScale}
      />

      <g transform={`translate(${200 + pose.bodyX} ${GROUND + pose.bodyY}) scale(${pose.bodyScale * skin.buildScale}) translate(-200 ${-GROUND})`}>
        <g transform={`translate(${pose.stance * 1.5} 0)`}>
          <Legs skin={skin} flat={flat} kneeL={pose.kneeL} kneeR={pose.kneeR} url={url} />
        </g>

        {/* Everything above the hips leans and shifts weight together. */}
        <g transform={`rotate(${pose.lean} 200 ${HIP}) translate(${pose.stance * 3} 0)`}>
          {behind && <g transform={shoulderXf}>{behind}</g>}
          {/* The chest swells about the hips with each breath; a bow folds the torso down. */}
          <g transform={`translate(200 ${HIP}) scale(${1 + b * 0.015} ${(1 + b * 0.015) * (1 - (pose.bow * 26) / TORSO_H)}) translate(-200 ${-HIP})`}>
            <g filter={flat ? undefined : url('litBig')}>
              <path d={torso} fill={flat ? p.top : url('top')} />
              {skin.top}
            </g>
            {flat ? (
              /* The arms shade the cloth beside them: one flat shape a tone
                 darker down each side, where the sleeve meets the chest. */
              <>
                <path d={underArm(sh, -1)} fill={p.topShade} opacity="0.5" />
                <path d={underArm(sh, 1)} fill={p.topShade} opacity="0.5" />
              </>
            ) : (
              <>
                <path d={torso} fill={url('occ')} />
                <path
                  d={`M${200 - sh - 2} 222 C${200 - sh - 6} 250 ${200 - sh + 2} 290 ${200 - m.waistHalf + 2} ${m.waistY}`}
                  fill="none"
                  stroke={shade(p.topLight, 0.45)}
                  strokeWidth="3"
                  strokeLinecap="round"
                  opacity="0.55"
                />
              </>
            )}
          </g>

          <g transform={shoulderXf}>
            <rect x={200 - m.neckHalf} y="166" width={m.neckHalf * 2} height="40" rx={m.neckHalf * 0.6} fill={flat ? p.skin : url('neck')} />
            {/* The chin's shadow lands ON THE NECK and follows the head. It is
                what makes the head sit on the body instead of beside it. */}
            <path
              d={`M${200 - m.neckHalf} ${chinY - 6} q${m.neckHalf} 10 ${m.neckHalf * 2} 0 v14 q${-m.neckHalf} 5 ${-m.neckHalf * 2} 0 z`}
              fill={flat ? p.skinShade : shade(p.skinShade, -0.3)}
              opacity={flat ? 1 : 0.5}
            />
            {children}
          </g>
        </g>
      </g>
    </>
  )
}

/* A crescent on the chest just inside the hanging upper arm (whose inner
   edge is 21 px inside the shoulder tip), where the arm shades the cloth. */
function underArm(sh: number, s: 1 | -1): string {
  const x = (dx: number) => 200 + s * (dx - sh)
  return `M${x(20)} 214 C${x(17)} 240 ${x(19)} 270 ${x(26)} 300 C${x(30)} 272 ${x(32)} 242 ${x(34)} 216 Z`
}

/** Skin-coloured legs under the outfit's legs; a knee bend shortens its half about the hip. */
function Legs({ skin, flat, kneeL, kneeR, url }: { skin: Skin; flat: boolean; kneeL: number; kneeR: number; url: Url }) {
  const bend = (k: number) => `translate(200 ${HIP}) scale(1 ${1 - k * 0.06}) translate(-200 ${-HIP})`
  const p = skin.palette
  const fill = flat ? p.skin : url('skin')
  const base = (
    <>
      {(['L', 'R'] as const).map((side) => (
        <path key={side} d={legOutline(skin, side)} fill={fill} />
      ))}
      {/* the inner calves turn away from each other: one flat sliver each */}
      {flat &&
        ([-1, 1] as const).map((s) => (
          <path
            key={s}
            d={`M${200 + s * 7} 505 C${200 + s * 8} 526 ${200 + s * 10} 548 ${200 + s * 9} ${ANKLE_Y} L${200 + s * 15} ${ANKLE_Y} C${200 + s * 15} 548 ${200 + s * 13} 526 ${200 + s * 12} 505 Z`}
            fill={p.skinShade}
            opacity="0.7"
          />
        ))}
    </>
  )
  const both = (
    <>
      {base}
      {skin.legs}
    </>
  )
  /* Same bend both sides: draw once, no seam down the middle. */
  if (Math.abs(kneeL - kneeR) < 0.004) return <g transform={bend(kneeL)}>{both}</g>
  return (
    <>
      <g clipPath={url('legL')}>
        <g transform={bend(kneeL)}>{both}</g>
      </g>
      <g clipPath={url('legR')}>
        <g transform={bend(kneeR)}>{both}</g>
      </g>
    </>
  )
}
