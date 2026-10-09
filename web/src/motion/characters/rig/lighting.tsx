/* How a character is painted. Two looks share one rig, chosen by skin.shading.
 *
 * 'flat', the default and the reference look (reference/arjun.png,
 * reference/riya.png): every form is one flat fill and every shadow is a flat
 * shape a shade darker. No filter, and no gradient except the one outfits
 * draws on the shirt. All this file adds to that look is the side the shade
 * falls on and the flat colour behind each paint name a part asks for.
 *
 * 'lit', the earlier draft kept as an option: one lamp, upper left and in
 * front, carried over from python/14_for_loop/src/decks/figures/lighting.tsx.
 * A gradient is a colour ramp and says nothing about the surface;
 * feSpecularLighting runs a real lighting model over the blurred alpha of the
 * form, so the highlight follows the form's own silhouette. A drop shadow
 * separates the layers: the fringe onto the forehead, an arm onto the torso.
 * Nothing under "lit" is mounted unless skin.shading === 'lit', which is how
 * a flat SVG ends up with no <filter> element at all. */
import type { JSX } from 'react'
import type { Palette } from '../skins/types'
import { shade } from './Body'

/** Upper left, in front. The one lamp for every character, both looks. */
export const LAMP = { x: -60, y: -90, z: 180 }

/** +1 puts a flat shade on the viewer's right, the side away from the lamp. */
export const SHADE_SIDE: 1 | -1 = LAMP.x < 0 ? 1 : -1

/* ---------- flat ---------- */

/** The ground shadow of the flat look: one colour, soft by opacity, never a gradient. */
export const GROUND_SHADOW = 'rgba(30, 58, 95, 0.14)'

/**
 * Parts ask the renderer for paint by name (`url('top')`, `url('armDrop')`).
 * In the lit look each name is a def; here it is the flat colour that stands
 * in for it, or `none` where the lit look had a filter or an occlusion wash.
 * Returning a colour from the same resolver is what lets Body and Arm draw
 * either look without a branch of their own.
 *
 * The neck is the shade colour outright: in both references the whole neck
 * sits in the chin's shadow, which is what seats the head on the body.
 */
export function flatPaints(p: Palette): Record<string, string> {
  return {
    face: p.skin,
    skin: p.skin,
    armSkinL: p.skin,
    armSkinR: p.skin,
    neck: p.skinShade,
    top: p.top,
    sleeveL: p.sleeve,
    sleeveR: p.sleeve,
    ground: GROUND_SHADOW,
    occ: 'none',
    lit: 'none',
    litBig: 'none',
    drop: 'none',
    armDrop: 'none',
  }
}

/* ---------- lit ---------- */

/**
 * Every gradient and filter of the lit look, keyed by the names above.
 * `headCy` restates the lamp relative to the head centre, because the skull
 * is filtered in head-local space; without it the lamp sits a hand's width
 * from the forehead.
 */
export function LitDefs({ id, p, headCy }: { id: (n: string) => string; p: Palette; headCy: number }): JSX.Element {
  return (
    <>
      <radialGradient id={id('face')} cx="0.38" cy="0.32" r="0.75">
        <stop offset="0%" stopColor={p.skinLight} />
        <stop offset="55%" stopColor={p.skin} />
        <stop offset="100%" stopColor={p.skinShade} />
      </radialGradient>
      <linearGradient id={id('skin')} x1="0.2" y1="0" x2="0.8" y2="1">
        <stop offset="0%" stopColor={p.skinLight} />
        <stop offset="100%" stopColor={p.skinShade} />
      </linearGradient>
      <linearGradient id={id('neck')} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={shade(p.skinShade, -0.12)} />
        <stop offset="100%" stopColor={p.skin} />
      </linearGradient>
      <linearGradient id={id('top')} x1="0.15" y1="0" x2="0.85" y2="1">
        <stop offset="0%" stopColor={p.topLight} />
        <stop offset="45%" stopColor={p.top} />
        <stop offset="100%" stopColor={p.topShade} />
      </linearGradient>
      {/* Arm paint is defined in the arm's own frame, so the right arm, which
          is mirrored, gets the stops swapped to keep its lit edge toward the lamp. */}
      {(['L', 'R'] as const).map((side) => {
        const [x1, x2] = side === 'L' ? [-12, 12] : [12, -12]
        return (
          <g key={side}>
            <linearGradient id={id('armSkin' + side)} gradientUnits="userSpaceOnUse" x1={x1} y1="0" x2={x2} y2="0">
              <stop offset="0%" stopColor={p.skinLight} />
              <stop offset="100%" stopColor={p.skinShade} />
            </linearGradient>
            <linearGradient id={id('sleeve' + side)} gradientUnits="userSpaceOnUse" x1={x1} y1="0" x2={x2} y2="0">
              <stop offset="0%" stopColor={shade(p.sleeve, 0.18)} />
              <stop offset="100%" stopColor={shade(p.sleeve, -0.3)} />
            </linearGradient>
          </g>
        )
      })}
      <radialGradient id={id('occ')} cx="0.5" cy="0.2" r="0.85">
        <stop offset="55%" stopColor={shade(p.topShade, -0.5)} stopOpacity="0" />
        <stop offset="100%" stopColor={shade(p.topShade, -0.5)} stopOpacity="0.4" />
      </radialGradient>
      <radialGradient id={id('ground')} cx="0.5" cy="0.5" r="0.5">
        <stop offset="0%" stopColor="#1E3A5F" stopOpacity="0.24" />
        <stop offset="100%" stopColor="#1E3A5F" stopOpacity="0" />
      </radialGradient>
      <SoftLight id={id('lit')} light={{ x: LAMP.x - 200, y: LAMP.y - headCy, z: LAMP.z }} />
      <SoftLight id={id('litBig')} blur={12} />
      <CastShadow id={id('drop')} dy={4} blur={3.5} opacity={0.34} />
      <CastShadow id={id('armDrop')} dy={6} blur={6} opacity={0.22} />
    </>
  )
}

/**
 * Matte skin and cloth: the surface turns, but the highlight is broad and low,
 * so nothing gleams. `surfaceScale` is how far the surface rises,
 * `specularExponent` how tight the highlight is (high is glazed, low is
 * matte). `blur` sets how wide the shaded rim is; a skull wants the default,
 * a torso twice as wide about 12. `light` restates the lamp when the filtered
 * element lives in a translated space, so it is still the same lamp.
 */
export function SoftLight({ id, blur = 7, light = LAMP }: { id: string; blur?: number; light?: { x: number; y: number; z: number } }) {
  return (
    <filter id={id} x="-25%" y="-25%" width="150%" height="150%">
      <feGaussianBlur in="SourceAlpha" stdDeviation={blur} result="blur" />
      <feSpecularLighting in="blur" surfaceScale="3" specularConstant="0.42" specularExponent="7" lightingColor="#FFF6EC" result="spec">
        <fePointLight x={light.x} y={light.y} z={light.z} />
      </feSpecularLighting>
      <feComposite in="spec" in2="SourceAlpha" operator="in" result="specClip" />
      <feComposite in="SourceGraphic" in2="specClip" operator="arithmetic" k1="0" k2="1" k3="1" k4="0" />
    </filter>
  )
}

/**
 * A form dropping a shadow onto the form behind it. Apply it OUTSIDE any
 * rotate or mirror so the shadow keeps falling down and to the right whatever
 * the limb is doing.
 */
export function CastShadow({ id, dy = 3, blur = 3, opacity = 0.35 }: { id: string; dy?: number; blur?: number; opacity?: number }) {
  return (
    <filter id={id} x="-30%" y="-30%" width="160%" height="170%">
      <feDropShadow dx="1.5" dy={dy} stdDeviation={blur} floodColor="#3A1B0B" floodOpacity={opacity} />
    </filter>
  )
}
