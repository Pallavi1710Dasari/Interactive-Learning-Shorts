// Contrast for the motion player's identity-coloured parts
// (RESTYLE_TO_MOTION_REELS.md, phase 3 badges, contrast fix).
//
// Two bars (WCAG):
//   4.5:1  small text — role labels, chat bubble words (spoken, upcoming and
//          older), badge names, speaker tags, end-card tag chips;
//   3:1    large symbols and big titles — the identity symbol, the hook chip,
//          the host badge's initial, waveforms.
//
// The player draws with the colour functions here, and the identities page
// (#motion/identities) and motion.test.tsx check the SAME functions, so the
// table cannot disagree with what is drawn.

import { C, FIELDS, FIELD_NAMES, theme, type FieldName } from "../tokens";
import type { IdentitySpec } from "./Identity";

export const SMALL_TEXT = 4.5;
export const LARGE = 3;

/* ------------------------------------------------------------ colour maths */

function rgb(c: string): [number, number, number] {
  const n = parseInt(c.slice(1, 7), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const hex = ([r, g, b]: number[]) =>
  "#" + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("").toUpperCase();

/** A colour (hex, or rgba(r,g,b,a)) composited over a solid background. */
export function over(fg: string, bg: string): string {
  const m = fg.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)/);
  if (!m) return fg.toUpperCase();
  const a = m[4] === undefined ? 1 : Number(m[4]);
  const b = rgb(bg);
  return hex([Number(m[1]), Number(m[2]), Number(m[3])].map((v, i) => v * a + b[i] * (1 - a)));
}

export function mix(a: string, b: string, k: number): string {
  const x = rgb(a), y = rgb(b);
  return hex(x.map((v, i) => v + (y[i] - v) * k));
}

function luminance(c: string): number {
  const ch = (v: number) => { const s = v / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
  const [r, g, b] = rgb(c);
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

export function contrastRatio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

/** The ink pulled toward the background as far as it can go while still
 * reading as small text: a "dim" that keeps >= 4.5:1 (a little margin). */
export function readableDim(ink: string, bg: string, min = SMALL_TEXT + 0.15): string {
  let best = ink;
  for (let k = 0.05; k <= 0.95; k += 0.05) {
    const c = mix(ink, bg, k);
    if (contrastRatio(c, bg) >= min) best = c; else break;
  }
  return best;
}

/* ------------------------------------------------------------ what is drawn */

/** The identity's colour for SMALL TEXT on a field (>= 4.5:1). Plans written
 * before text tones existed fall back to the 3:1 tone. */
export function textToneOn(spec: IdentitySpec, field: FieldName): string {
  const t = theme(field).dark ? spec.text_on_dark : spec.text_on_light;
  return t || (theme(field).dark ? spec.on_dark : spec.on_light);
}

export interface BubbleColours { bg: string; ink: string; dim: string; accent: string }

/** A chat bubble's colours: its solid background, the spoken words, the
 * upcoming / older words (dim, still >= 4.5:1), and a highlighted word. */
export function bubbleColours(host: boolean, field: FieldName): BubbleColours {
  const th = theme(field);
  /* the language speaker's bubble on a dark field: a light veil on navy, but a
     navy veil on blue — a light veil there leaves a yellow highlight under 4.5:1 */
  const veil = field === "blue" ? "rgba(9,16,37,0.25)" : "rgba(255,255,255,0.10)";
  const bg = host ? over(th.surface, FIELDS[field]) : th.dark ? over(veil, FIELDS[field]) : over(C.surf, FIELDS[field]);
  const ink = host ? th.surfaceInk : th.ink;
  return { bg, ink, dim: readableDim(ink, bg), accent: th.accent };
}

/** The corner badge's name: its ink on its surface. */
export function badgeNameColours(field: FieldName): { bg: string; ink: string } {
  const th = theme(field);
  return { bg: over(th.surface, FIELDS[field]), ink: th.surfaceInk };
}

/** The end card's tag chips, over the indigo gradient where the chips sit. */
export const END_CARD = { top: "#5B4BF5", bottom: "#4234D6", chipsAt: 1290 / 1920 };
export function endChipColours(done: boolean): { bg: string; ink: string } {
  const card = mix(END_CARD.top, END_CARD.bottom, END_CARD.chipsAt);
  return done ? { bg: over("rgba(255,255,255,0.95)", card), ink: C.indigo } : { bg: over("rgba(255,255,255,0.14)", card), ink: C.white };
}

/* ------------------------------------------------------------ the checks */

export interface ContrastCheck { element: string; who: string; field: FieldName | "end card"; fg: string; bg: string; ratio: number; min: number }

/** Every identity-coloured or chat text the player draws, on every field. */
export function contrastChecks(identities: { key: string; spec: IdentitySpec }[]): ContrastCheck[] {
  const out: ContrastCheck[] = [];
  const add = (element: string, who: string, field: ContrastCheck["field"], fg: string, bg: string, min: number) =>
    out.push({ element, who, field, fg, bg, ratio: contrastRatio(fg, bg), min });
  for (const field of FIELD_NAMES) {
    const bg = FIELDS[field];
    for (const { key, spec } of identities) {
      add("role label / speaker tag", key, field, textToneOn(spec, field), bg, SMALL_TEXT);
      add("symbol, waveform, badge ring", key, field, theme(field).dark ? spec.on_dark : spec.on_light, bg, LARGE);
      const tone = theme(field).dark ? spec.on_dark : spec.on_light;
      add("hook chip text / badge initial (on the tone)", key, field, theme(field).dark ? C.ink : C.white, tone, LARGE);
    }
    for (const host of [true, false]) {
      const b = bubbleColours(host, field);
      const who = host ? "host bubble" : "language bubble";
      add("bubble text, spoken", who, field, b.ink, b.bg, SMALL_TEXT);
      add("bubble text, upcoming / older", who, field, b.dim, b.bg, SMALL_TEXT);
      add("bubble text, highlighted", who, field, b.accent, b.bg, SMALL_TEXT);
    }
    const n = badgeNameColours(field);
    add("corner badge name", "all", field, n.ink, n.bg, SMALL_TEXT);
  }
  for (const done of [false, true]) {
    const c = endChipColours(done);
    add(done ? "end-card tag chip (done)" : "end-card tag chip", "all", "end card", c.ink, c.bg, SMALL_TEXT);
  }
  return out;
}
