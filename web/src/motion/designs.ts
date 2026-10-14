// Motion reel DESIGNS: the look the player draws a reel in. A reel's plan
// names its design (plan.design, chosen when the reel was set up —
// shorts/config.MOTION_DESIGN); a plan without one is "classic", so reels made
// before designs existed keep their look. Add a design here (and to
// config.MOTION_DESIGNS) to make another style available.
//
//   classic        the phase 2-3 look: flat colour fields, Anton caps,
//                  field-colour transitions
//   midnight_lab   picked 2026-10-12 (#motion-gallery/directions, B): night
//                  blue with a glowing grid floor, glass cards, heavy Manrope
//                  in sentence case, cyan key words, a 3D tilt that settles,
//                  zoom-through transitions. On a rev 3 plan it keeps its night
//                  background, tilt and zoom-through, and takes the studio's
//                  type, colours, cards and chrome (palette "midnight").
//   studio         2026-10-13 (review of job f64077e78448): our own look,
//                  replacing everything copied from the reference reels —
//                  a palette per theme (library.json studio.palettes),
//                  Bricolage Grotesque display and Lexend body, index cards,
//                  a section ribbon and timeline thread, and our own
//                  transitions (transitions.tsx STUDIO_TRANSITIONS)
//
// A design changes how things are drawn, never where: the Python layout's
// boxes hold for every design (display text is scaled to take about the same
// width — tokens.display).

import type { CSSProperties } from "react";
import type { FieldName } from "./tokens";

export type DesignId = "classic" | "midnight_lab" | "studio";

export interface Design {
  id: DesignId;
  name: string;
  /** CSS variables set on the frame: display face, weight, case, size. */
  vars: Record<string, string>;
  /** The field a shot is drawn on, from the field the plan gave it. */
  field: (f: FieldName) => FieldName;
  /** Draw the design's own background behind each shot. */
  background: "flat" | "lab" | "studio";
  /** Every chapter change uses this transition instead of the plan's
   * ("studio": the plan's, drawn as the studio's own). */
  transition: "plan" | "zoom_through" | "studio";
  /** The 3D tilt-in at the start of each shot. */
  camera: boolean;
}

const LAB_FIELD: Partial<Record<FieldName, FieldName>> = {
  navy: "lab", paper: "lab", blue: "lab_violet", yellow: "lab_violet",
};
const STUDIO_FIELD: Partial<Record<FieldName, FieldName>> = {
  navy: "studio", paper: "studio", blue: "studio_alt", yellow: "studio_alt",
};
/** The studio's type (fonts.css): display and body, sentence case. */
const STUDIO_TYPE = {
  "--motion-display": "'Bricolage Grotesque Variable', 'Bricolage Grotesque'",
  "--motion-display-weight": "750",
  "--motion-case": "none",
  "--motion-display-scale": "0.84",
  "--motion-display-tracking": "-0.015em",
  "--motion-body": "'Lexend Variable', 'Lexend'",
};

export const DESIGNS: Record<DesignId, Design> = {
  classic: {
    id: "classic", name: "Classic", vars: {}, field: (f) => f,
    background: "flat", transition: "plan", camera: false,
  },
  midnight_lab: {
    id: "midnight_lab", name: "Midnight Lab",
    vars: {
      "--motion-display": "'Manrope Variable', 'Manrope'",
      "--motion-display-weight": "800",
      "--motion-case": "none",
      "--motion-display-scale": "0.8",
      "--motion-display-tracking": "-0.02em",
      "--motion-card-bg": "transparent",
      "--motion-glow": "0 0 34px rgba(66,226,255,0.55)",
    },
    field: (f) => LAB_FIELD[f] ?? f,
    background: "lab", transition: "zoom_through", camera: true,
  },
  studio: {
    id: "studio", name: "Studio",
    vars: { ...STUDIO_TYPE, "--motion-card-bg": "transparent", "--motion-glow": "none" },
    field: (f) => STUDIO_FIELD[f] ?? f,
    background: "studio", transition: "studio", camera: false,
  },
};

/** Midnight Lab on a rev 3 plan: its own background and moves, the studio's type. */
export const MIDNIGHT_STUDIO_VARS = { ...DESIGNS.midnight_lab.vars, ...STUDIO_TYPE, "--motion-display-weight": "750" };

export function designOf(id: string | null | undefined): Design {
  return DESIGNS[(id as DesignId)] ?? DESIGNS.classic;
}

export function designVars(d: Design): CSSProperties {
  return d.vars as CSSProperties;
}
