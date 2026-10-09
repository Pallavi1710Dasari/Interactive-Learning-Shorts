/* A character is a config; the Skin the renderer draws is BUILT from it and
 * never written by hand. That is what keeps Arjun and Riya on one rig: the
 * same config shape produces either of them, or a third person, and every
 * action works unchanged because the rig underneath does not know who it is.
 *
 * This file owns the config type, the two presets, the colour derivations
 * (skin tone, hair, cloth) and buildSkin. The drawings live in hair.tsx
 * (sibling) and outfits.tsx.
 *
 * The presets are the two reference illustrations, reference/arjun.png and
 * reference/riya.png, read off the pixels; every number that came from a
 * reference says so beside it. Everything here is a table, so a new
 * character is a new row, not a new branch. */
import type { Palette, Skin } from './types'
import { hairBack, hairFront } from './hair'
import { faceExtras, legs, neckExtras, top } from './outfits'

export type SkinTone = 'fair' | 'wheatish' | 'medium' | 'dusky' | 'deep' | `#${string}`
export type HairColor = 'black' | 'darkBrown' | 'brown' | 'auburn' | 'grey' | `#${string}`
export type HairStyle =
  | 'short' | 'sidePart' | 'quiff' | 'curly' | 'buzz' // read as male by default
  | 'braid' | 'ponytail' | 'bob' | 'long' | 'bun' | 'wavy' // read as female by default
export type TopStyle = 'shirt' | 'shirtTie' | 'tshirt' | 'kurta' | 'hoodie' | 'blouse' | 'polo'
export type BottomStyle = 'trousers' | 'jeans' | 'skirt' | 'salwar' | 'shorts'
export type ArtStyle = 'soft' | 'line'
export type Shading = 'flat' | 'lit'

export type CharacterConfig = {
  name: string
  gender: 'male' | 'female' // base proportions: shoulder width, neck, jaw default
  /** 'soft': no outlines, flat fills with soft shadow shapes (Arjun). 'line': thin dark outlines on hands, collar, pockets (Riya) */
  art: ArtStyle
  /** 'flat' is the reference look and the default; 'lit' keeps the old specular filters */
  shading?: Shading
  skinTone: SkinTone
  hair: { style: HairStyle; color: HairColor }
  face: {
    jaw: 'round' | 'oval' | 'square'
    brows: 'thin' | 'medium' | 'thick'
    eyes: 'oval' | 'dot'
    mouth: 'full' | 'line'
    lip?: `#${string}`
    blush?: number
  }
  outfit: {
    top: TopStyle
    topColor: `#${string}`
    bottom: BottomStyle
    bottomColor: `#${string}`
    shoeColor?: `#${string}`
    /** the tie or the hair band; unset means the ACCENT table below */
    accentColor?: `#${string}`
  }
  accessories: {
    glasses?: 'none' | 'round' | 'rect'
    earrings?: boolean
    bindi?: boolean
    beard?: 'none' | 'stubble' | 'short'
    watch?: boolean
    flower?: boolean
    necklace?: boolean
    belt?: boolean
  }
  build: { height: number; shoulders: number } // multipliers, 0.9..1.1
}

/* The two reference characters, exactly as the Art direction section of
   CONTRACTS.md lists them. */
export const PRESETS: Record<'arjun' | 'riya', CharacterConfig> = {
  arjun: {
    name: 'Arjun',
    gender: 'male',
    art: 'soft',
    shading: 'flat',
    skinTone: '#F8C9A8',
    hair: { style: 'quiff', color: '#151515' },
    face: { jaw: 'square', brows: 'medium', eyes: 'oval', mouth: 'full' },
    outfit: { top: 'shirtTie', topColor: '#FFFFFF', bottom: 'trousers', bottomColor: '#1B2238', shoeColor: '#2A2F45' },
    accessories: { belt: true },
    build: { height: 1, shoulders: 1 },
  },
  riya: {
    name: 'Riya',
    gender: 'female',
    art: 'line',
    shading: 'flat',
    skinTone: '#F5A68E',
    hair: { style: 'bun', color: '#1A1F3D' },
    face: { jaw: 'oval', brows: 'thin', eyes: 'dot', mouth: 'line' },
    outfit: { top: 'blouse', topColor: '#5B6EE1', bottom: 'skirt', bottomColor: '#171A3B', shoeColor: '#1A1F3D' },
    accessories: {},
    build: { height: 1, shoulders: 1 },
  },
}

/* ---------- colour maths, HSL so a shade keeps its hue ---------- */

type Hsl = [number, number, number] // h 0..360, s 0..1, l 0..1

function hexToHsl(hex: string): Hsl {
  const n = parseInt(hex.slice(1), 16)
  const r = ((n >> 16) & 255) / 255
  const g = ((n >> 8) & 255) / 255
  const b = (n & 255) / 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  const h =
    max === r ? ((g - b) / d + (g < b ? 6 : 0)) * 60 : max === g ? ((b - r) / d + 2) * 60 : ((r - g) / d + 4) * 60
  return [h, s, l]
}

function hslToHex([h, s, l]: Hsl): string {
  const hue = ((h % 360) + 360) % 360
  const f = (n: number) => {
    const k = (n + hue / 30) % 12
    const c = l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(c * 255)
      .toString(16)
      .padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

/** Move a colour along lightness (and a little along saturation) without
    touching its hue. A shadow on blue cloth is a deeper blue, not a grey. */
function shift(hex: string, dl: number, ds = 0): string {
  const [h, s, l] = hexToHsl(hex)
  return hslToHex([h, clamp01(s + ds), clamp01(l + dl)])
}

/* ---------- skin ---------- */

type Tone = ReturnType<typeof resolveTone>

/* Five Indian skin tones. Wheatish is Riya's from the for-loop deck. The
   others sit on the same ramp: the shade is the colour where the form turns
   away, the light where it faces the lamp, blush is the cheek warmed, lip
   the natural lip. */
const TONES: Record<Exclude<SkinTone, `#${string}`>, Tone> = {
  fair: { skin: '#F6D5B8', skinShade: '#D9AE8A', skinLight: '#FFE9D6', blush: '#F4A6A6', lip: '#A4493E' },
  wheatish: { skin: '#F0C29B', skinShade: '#D09A6E', skinLight: '#FFDCBC', blush: '#F29B9B', lip: '#8A3B2E' },
  medium: { skin: '#D9A072', skinShade: '#B57A4D', skinLight: '#EFBF95', blush: '#D98C7A', lip: '#7E3528' },
  dusky: { skin: '#B87A4F', skinShade: '#91582F', skinLight: '#D4996E', blush: '#C27C6A', lip: '#6A2C22' },
  deep: { skin: '#8D5633', skinShade: '#68391C', skinLight: '#A96F4C', blush: '#A3634F', lip: '#4F2219' },
}

/* How the references derive a face from one skin colour. Measured on both:
   Arjun #F8C9A8 -> shade #E9A98A, cheek #F0A08A; Riya #F5A68E -> shade
   #E08E75, cheek #F08A7A. The shade keeps 88 percent of the lightness, loses
   some saturation and turns a few degrees toward red (a shadow on skin goes
   warm, never grey). The cheek is the skin pulled further toward red at a
   fixed saturation, so it reads as the same face flushed. The lip is a rosier
   pink, the lower lip of Arjun's laugh. */
const SKIN_RULE = {
  shade: { hue: -4, sat: -0.18, light: 0.88 },
  light: { light: +0.06 },
  blush: { hue: -8, minHue: 4, sat: 0.78, light: 0.9 },
  lip: { hue: -16, minHue: 2, sat: 0.7, light: 0.66 },
}

export function resolveTone(t: SkinTone): { skin: string; skinShade: string; skinLight: string; blush: string; lip: string } {
  if (!t.startsWith('#')) return TONES[t as keyof typeof TONES]
  const [h, s, l] = hexToHsl(t)
  const { shade, light, blush, lip } = SKIN_RULE
  return {
    skin: t,
    skinShade: hslToHex([h + shade.hue, clamp01(s + shade.sat), clamp01(l * shade.light)]),
    skinLight: hslToHex([h, s, clamp01(l + light.light)]),
    blush: hslToHex([Math.max(blush.minHue, h + blush.hue), blush.sat, clamp01(l * blush.light)]),
    lip: hslToHex([Math.max(lip.minHue, h + lip.hue), lip.sat, lip.light]),
  }
}

/* ---------- hair ---------- */

const HAIRS: Record<Exclude<HairColor, `#${string}`>, ReturnType<typeof resolveHair>> = {
  black: { hair: '#1C1A1C', hairShade: '#0E0C0E', hairLight: '#3F3A42' },
  darkBrown: { hair: '#2E1E1A', hairShade: '#1A100D', hairLight: '#4A3A33' },
  brown: { hair: '#5A3A26', hairShade: '#3A2316', hairLight: '#7E5A42' },
  auburn: { hair: '#7A3B22', hairShade: '#4E2314', hairLight: '#A65A3A' },
  grey: { hair: '#9A9A9C', hairShade: '#6E6E72', hairLight: '#C9C9CC' },
}

/* Arjun's reference hair is #151515 with a #2E2E2E sheen: a lightness step
   of 0.10. The shade step is smaller because near-black has nowhere to go. */
const HAIR_RULE = { shade: -0.06, light: +0.1 }

export function resolveHair(c: HairColor): { hair: string; hairShade: string; hairLight: string } {
  if (!c.startsWith('#')) return HAIRS[c as keyof typeof HAIRS]
  return { hair: c, hairShade: shift(c, HAIR_RULE.shade), hairLight: shift(c, HAIR_RULE.light) }
}

/* The line colour for art 'line' is the hair colour, pulled down to the
   navy-black of Riya's reference (#1A1F3D, lightness 0.17) when the hair is
   lighter than that. Darker hair is already its own outline. */
const OUTLINE_MAX_LIGHT = 0.17

function outlineFor(hair: string): string {
  const [h, s, l] = hexToHsl(hair)
  return hslToHex([h, s, Math.min(l, OUTLINE_MAX_LIGHT)])
}

/* ---------- cloth ---------- */

type Cloth = { top: string; topShade: string; topLight: string; sleeve: string }

/* Arjun's shirt is white at the collar grading to #DCE9F8 at the hem and
   sleeves: white cloth shades blue in this style, which no hue shift of
   white can produce, so near-white gets the reference tint outright. */
const WHITE_CLOTH: Cloth = { top: '#FFFFFF', topShade: '#DCE9F8', topLight: '#FFFFFF', sleeve: '#EDF3FB' }
const WHITE_FROM_LIGHT = 0.95

/* Coloured cloth: Riya's blouse #5B6EE1 shades to #4A5BCF, a 0.07 drop in
   lightness and 0.1 in saturation, far gentler than the lit draft's. The
   sleeve is a hair deeper than the body so a hanging arm separates from the
   torso without an outline. */
const CLOTH_RULE = { shade: { light: -0.07, sat: -0.1 }, light: +0.1, sleeve: -0.03 }

function clothFor(topColor: string): Cloth {
  const [, , l] = hexToHsl(topColor)
  if (l >= WHITE_FROM_LIGHT) return { ...WHITE_CLOTH, top: topColor }
  return {
    top: topColor,
    topShade: shift(topColor, CLOTH_RULE.shade.light, CLOTH_RULE.shade.sat),
    topLight: shift(topColor, CLOTH_RULE.light),
    sleeve: shift(topColor, CLOTH_RULE.sleeve),
  }
}

/* The accent is the tie (Arjun, navy #1E2B4F from the reference) or the
   hair band (Riya, the same periwinkle as her blouse). A top style that has
   neither falls back to the top colour so the band always matches. */
const TIE_NAVY = '#1E2B4F'
const ACCENT: Partial<Record<TopStyle, (topColor: string) => string>> = {
  shirtTie: () => TIE_NAVY,
}

function accentFor(c: CharacterConfig): string {
  return c.outfit.accentColor ?? (ACCENT[c.outfit.top] ?? ((t) => t))(c.outfit.topColor)
}

/* Trousers and skirts in this style carry one shade a touch darker; the
   stitch lines on Riya's pockets are the outfit's own colour, not a shade. */
const BOTTOM_RULE = { shade: { light: -0.06, sat: 0.04 } }

/* The inside of an open mouth: Arjun's reference laugh is #C9484B, a warm
   red at the lip's hue turned a little toward crimson. */
const MOUTH_RULE = { hue: -8, sat: 0.54, light: 0.53 }

/* ---------- the skin ---------- */

/* Long sleeves cover the forearm in cloth; short leave it skin. A kurta here
   is the short-sleeved summer cut. */
const SLEEVE: Record<TopStyle, 'long' | 'short'> = {
  shirt: 'long',
  shirtTie: 'long',
  hoodie: 'long',
  polo: 'long',
  tshirt: 'short',
  kurta: 'short',
  blouse: 'short',
}

/* Brow stroke width in px: Riya's are thin arcs, Arjun's a little heavier. */
const BROW_WEIGHT: Record<CharacterConfig['face']['brows'], number> = { thin: 2.2, medium: 3, thick: 3.8 }

/* Head outlines, head-local, origin at the skull centre: crown y=-56, sides
   x=+-50 level with the ears, chin y=56 (the new rig geometry, skull rx 50
   ry 56). The top half is shared; the jaw is what differs, and the jaw is
   most of what makes a face recognisable at 120 px. */
const CROWN = 'M0 -56 C28 -56 50 -34 50 -5'
const CROWN_BACK = 'C-50 -34 -28 -56 0 -56 Z'
const HEADS = {
  /* full cheeks, the chin a continuation of the curve */
  round: `${CROWN} C50 27 32 56 0 56 C-32 56 -50 27 -50 -5 ${CROWN_BACK}`,
  /* cheekbone, then a taper into a slightly pointed chin: Riya's reference */
  oval: `${CROWN} C50 19 37 46 12 55 Q0 57 -12 55 C-37 46 -50 19 -50 -5 ${CROWN_BACK}`,
  /* the same taper on a skull three px narrower each side: the female default */
  ovalNarrow: 'M0 -56 C27 -56 47 -34 47 -5 C47 19 35 46 11 55 Q0 57 -11 55 C-35 46 -47 19 -47 -5 C-47 -34 -27 -56 0 -56 Z',
  /* a rounded square with a soft jaw: the jaw runs down almost vertical and
     turns a corner before the chin. Arjun's reference */
  square: `${CROWN} C50 15 50 37 40 48 C30 55 15 56 0 56 C-15 56 -30 55 -40 48 C-50 37 -50 15 -50 -5 ${CROWN_BACK}`,
}

/* Male shoulders are wider than female at the same height: the one
   proportion that reads as gender from across a room. Rig geometry: Arjun
   76, Riya 58. */
const SHOULDER_HALF = { male: 76, female: 58 }

/* The female skull is a touch narrower; the jaw path does the rest. */
const HEAD_SCALE = { male: { x: 1, y: 1 }, female: { x: 0.96, y: 1 } }

/* The renderer's Skin.id is the two presets; a custom config borrows the id
   of the preset it is nearest to by gender, which is all the renderer uses
   it for. */
function skinId(c: CharacterConfig): Skin['id'] {
  const n = c.name.toLowerCase()
  if (n === 'arjun' || n === 'riya') return n
  return c.gender === 'female' ? 'riya' : 'arjun'
}

function paletteFor(c: CharacterConfig): Palette {
  const tone = resolveTone(c.skinTone)
  const hair = resolveHair(c.hair.color)
  const lip = c.face.lip ?? tone.lip
  const [lipHue] = hexToHsl(lip)
  return {
    ...tone,
    ...hair,
    ...clothFor(c.outfit.topColor),
    lip,
    mouth: hslToHex([lipHue + MOUTH_RULE.hue, MOUTH_RULE.sat, MOUTH_RULE.light]),
    /* almost every Indian iris is a dark brown; it stays the same across
       tones so the eyes do not drift colour when the skin does */
    iris: '#3B2416',
    brow: hair.hair,
    accent: accentFor(c),
    bottom: c.outfit.bottomColor,
    bottomShade: shift(c.outfit.bottomColor, BOTTOM_RULE.shade.light, BOTTOM_RULE.shade.sat),
    shoe: c.outfit.shoeColor ?? '#2B2521',
  }
}

/* Hair that falls to the waist is painted behind the torso, not behind the
   skull alone; a braid or a ponytail hangs over the shoulder and stays in
   front. hair.tsx draws both as hairBack, so the layer is decided here. */
const FALLING_HAIR: ReadonlySet<HairStyle> = new Set(['long', 'bun', 'wavy'])

export function buildSkin(config: CharacterConfig): Skin {
  const palette = paletteFor(config)
  const female = config.gender === 'female'
  const shoulderHalf = SHOULDER_HALF[config.gender] * config.build.shoulders
  const jaw = config.face.jaw === 'oval' && female ? 'ovalNarrow' : config.face.jaw
  const outline = outlineFor(palette.hair)
  return {
    id: skinId(config),
    label: config.name,
    palette,
    head: HEADS[jaw],
    sleeve: SLEEVE[config.outfit.top],
    shoulderHalf,
    headScale: HEAD_SCALE[config.gender],
    buildScale: config.build.height,
    art: config.art,
    shading: config.shading ?? 'flat',
    eyes: config.face.eyes,
    mouthStyle: config.face.mouth,
    browWeight: BROW_WEIGHT[config.face.brows],
    outline,
    belt: Boolean(config.accessories.belt),
    watch: Boolean(config.accessories.watch),
    hairBack: hairBack(config.hair.style, palette) ?? undefined,
    hairFalls: FALLING_HAIR.has(config.hair.style),
    hairFront: hairFront(config.hair.style, palette) ?? undefined,
    faceExtras: faceExtras(config, palette) ?? undefined,
    /* the outfit is drawn to this body's own shoulders, so the cloth and
       the base torso agree to the pixel and nothing is scaled afterwards */
    top: top(config.outfit.top, palette, { art: config.art, belt: config.accessories.belt, outline, shoulderHalf }),
    legs: legs(config.outfit.bottom, palette, { art: config.art, outline, shoulderHalf }),
    neckExtras: neckExtras(config, palette, { shoulderHalf }) ?? undefined,
  }
}
