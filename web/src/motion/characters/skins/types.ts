/* A skin is what makes Arjun Arjun and Riya Riya: palette, hair, clothes,
 * the shape of the jaw. The rig underneath is shared, so every action works
 * on both. A skin never animates anything; it hands the renderer static
 * fragments, and the renderer places them inside the groups that move.
 *
 * Coordinates: head fragments are in head-local space, origin at the centre
 * of the skull, chin at about y=66, crown at y=-66. Body fragments are in
 * body space, the 400x600 viewBox, hips at (200, 400). */
import type { ReactNode } from 'react'

export type Palette = {
  skin: string
  skinShade: string
  skinLight: string
  blush: string
  lip: string
  mouth: string
  hair: string
  hairShade: string
  hairLight: string
  iris: string
  brow: string
  top: string
  topShade: string
  topLight: string
  sleeve: string
  bottom: string
  bottomShade: string
  shoe: string
  /** the tie (Arjun, navy) or the hair band (Riya, the blouse periwinkle) */
  accent: string
}

export type Skin = {
  id: 'arjun' | 'riya'
  label: string
  palette: Palette
  /** path d for the skull/face outline, head-local */
  head: string
  /** 'long' sleeves cover the forearm in the top colour, 'short' leave it skin */
  sleeve: 'long' | 'short'
  /** the half-width of the shoulders, px; the renderer places the arm pivots here */
  shoulderHalf: number
  /** proportion tweaks from CharacterConfig.build and gender */
  headScale: { x: number; y: number }
  buildScale: number
  /* ART DIRECTION, from reference/arjun.png and reference/riya.png.
     'soft': no outlines, flat fills with soft shadow shapes and one gentle
     gradient on the top (Arjun). 'line': flat fills with thin dark outlines
     on hands, collar and pockets (Riya). */
  art: 'soft' | 'line'
  /** 'flat' is the reference look; 'lit' keeps the specular filters */
  shading: 'flat' | 'lit'
  /** 'oval': small dark ovals with a catchlight (Arjun). 'dot': tiny almond dots with a lash line (Riya) */
  eyes: 'oval' | 'dot'
  /** 'full': lips, teeth and tongue (Arjun). 'line': a drawn line that opens into a small dark shape (Riya) */
  mouthStyle: 'full' | 'line'
  /** brow stroke width in px, from config.face.brows */
  browWeight: number
  /** the outline colour for art 'line' */
  outline: string
  belt?: boolean
  /** a watch on the wrist; drawn by the renderer inside the arm group so it moves with the hand */
  watch?: boolean
  hairBack?: ReactNode
  /** hairBack reaches the waist, so the renderer paints it behind the torso
      and the neck, not only behind the skull; unset keeps it in the head group */
  hairFalls?: boolean
  hairFront?: ReactNode
  /** glasses, bindi, beard, earrings: head-local, drawn over the face */
  faceExtras?: ReactNode
  /** torso clothing, body space, drawn over the torso base */
  top: ReactNode
  /** trousers or skirt and shoes, body space */
  legs: ReactNode
  /** scarf, collar, necklace: body space, drawn after the head */
  neckExtras?: ReactNode
}
