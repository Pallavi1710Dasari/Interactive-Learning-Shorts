import type { CSSProperties } from "react";

// The motion-reel design tokens — REFERENCE_STYLE_ADDENDUM.md section 4.1-4.2.
// Every component in web/src/motion draws in DESIGN UNITS: a 1080 x 1920
// frame, the size of the MP4. <Fit> scales the whole frame for any screen, so
// a component never measures the page it is on.
//
// COLOUR MEANINGS ARE FIXED for objects and text: coral only for failure,
// mint only for success, lavender only for system-added items. Fields (the
// full-bleed backgrounds) change per chapter, and transitions use field
// colours only, never coral or mint (decision 2026-10-01).

export const W = 1080;
export const H = 1920;
export const FPS = 30;

export const FIELDS = {
  navy: "#091025",
  blue: "#283EE6",
  paper: "#ECF0F7",
  yellow: "#FDD13E",
  // Midnight Lab (designs.ts): the night base and its violet variant. The
  // solid colour is what text contrast is measured on; the player draws the
  // design's glowing background over it.
  lab: "#0A0F2C",
  lab_violet: "#14123A",
} as const;
export type FieldName = keyof typeof FIELDS;
export const FIELD_NAMES = Object.keys(FIELDS) as FieldName[];

/** Midnight Lab's own colours (designs.ts). */
export const LAB = { cyan: "#42E2FF", violet: "#8C7BFF", amber: "#FFB547", dim: "#8A92C4" } as const;

export const C = {
  ink: "#151936",
  sub: "#6A6F8E",
  line: "#E2E4EF",
  surf: "#FFFFFF",
  indigo: "#5B4BF5",
  indigoSoft: "#ECEAFE",
  amber: "#FFB524",
  amberInk: "#9A6500",
  amberSoft: "#FFF3D9",
  coral: "#F2555A",
  coralSoft: "#FDE8E8",
  mint: "#17B27B",
  mintSoft: "#E2F6EE",
  grey: "#B7BBD0",
  code: "#1B1F3B",
  codeBar: "#242951",
  codeText: "#E8EAFF",
  codeKeyword: "#A99CFF",
  codeFn: "#7FE0B8",
  codeDim: "#5D6390",
  yellow: "#FDD13E",
  special: "#B9A8FF",
  specialSoft: "#EEE9FF",
  white: "#FFFFFF",
} as const;

/** What sits on a field: ink, dimmed ink, the accent (yellow on dark, blue on
 * light, deep blue on yellow), and the card surface (cards invert on dark). */
export interface Theme {
  field: FieldName;
  bg: string;
  dark: boolean;
  ink: string;
  dim: string;
  accent: string;
  surface: string;
  surfaceInk: string;
  surfaceLine: string;
  surfaceDim: string;
}

export function theme(field: FieldName): Theme {
  const bg = FIELDS[field];
  if (field === "lab" || field === "lab_violet") {
    // glass: cards are a light veil over the night, lit edges, cyan accent
    return {
      field, bg, dark: true,
      ink: "#F2F4FF", dim: "rgba(242,244,255,0.35)", accent: LAB.cyan,
      surface: "rgba(255,255,255,0.08)", surfaceInk: "#F2F4FF", surfaceLine: "rgba(255,255,255,0.16)",
      surfaceDim: "rgba(242,244,255,0.62)",
    };
  }
  if (field === "navy" || field === "blue") {
    return {
      field, bg, dark: true,
      ink: C.white, dim: "rgba(255,255,255,0.35)", accent: C.yellow,
      surface: field === "navy" ? "#141C3A" : "#1F31C4",
      surfaceInk: C.white, surfaceLine: "rgba(255,255,255,0.16)",
      surfaceDim: "rgba(255,255,255,0.55)",
    };
  }
  if (field === "yellow") {
    return {
      field, bg, dark: false,
      ink: C.ink, dim: "rgba(21,25,54,0.35)", accent: FIELDS.blue,
      surface: "#FFF8DE", surfaceInk: C.ink, surfaceLine: "rgba(21,25,54,0.18)",
      surfaceDim: C.sub,
    };
  }
  return {
    field, bg, dark: false,
    ink: C.ink, dim: "rgba(21,25,54,0.35)", accent: FIELDS.blue,
    surface: C.surf, surfaceInk: C.ink, surfaceLine: C.line, surfaceDim: C.sub,
  };
}

/** Body and mono are fixed; the display face is a CSS variable so the gallery
 * can show both candidates (section 4.2: "pick the closest and show me"). */
export const FONT = {
  body: "'Manrope Variable', Manrope, system-ui, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, Menlo, monospace",
  display: "var(--motion-display, 'Anton'), Impact, sans-serif",
} as const;

/** Display text: the face, weight, case, tracking and size come from the
 * reel's design (CSS variables set on the frame — designs.ts), so a classic
 * reel stays Anton caps and a Midnight Lab reel is heavy Manrope in sentence
 * case, scaled so a line takes about the same width. */
export function display(size: number): CSSProperties {
  return {
    fontFamily: FONT.display, fontSize: `calc(${size}px * var(--motion-display-scale, 1))`,
    fontWeight: "var(--motion-display-weight, 400)" as unknown as number,
    textTransform: "var(--motion-case, uppercase)" as CSSProperties["textTransform"],
    letterSpacing: "var(--motion-display-tracking, normal)",
  };
}

export const DISPLAY_FONTS = {
  anton: "'Anton'",
  archivo: "'Archivo Black'",
} as const;
export type DisplayFont = keyof typeof DISPLAY_FONTS;

/** Layout lines, in design units (section 4.4: captions in the 70-80 % band,
 * above the 82 % safe line, 6 % side margin). */
export const SAFE = {
  side: Math.round(W * 0.06),
  top: Math.round(H * 0.045),
  captionTop: Math.round(H * 0.70),
  captionBottom: Math.round(H * 0.80),
  bottomLine: Math.round(H * 0.82),
} as const;

/** Rough advance widths, so layouts are computed, never measured from the DOM
 * (measuring would make a frame depend on the page, not on t). */
export const MONO_ADVANCE = 0.6;   // JetBrains Mono: 0.6 em per character
export function monoWidth(text: string, size: number): number {
  return text.length * size * MONO_ADVANCE;
}
