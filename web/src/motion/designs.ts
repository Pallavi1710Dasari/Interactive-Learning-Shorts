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
//                  zoom-through transitions
//
// A design changes how things are drawn, never where: the Python layout's
// boxes hold for every design (display text is scaled to take about the same
// width — tokens.display).

import type { CSSProperties } from "react";
import type { FieldName } from "./tokens";

export type DesignId = "classic" | "midnight_lab";

export interface Design {
  id: DesignId;
  name: string;
  /** CSS variables set on the frame: display face, weight, case, size. */
  vars: Record<string, string>;
  /** The field a shot is drawn on, from the field the plan gave it. */
  field: (f: FieldName) => FieldName;
  /** Draw the design's own background behind each shot. */
  background: "flat" | "lab";
  /** Every chapter change uses this transition instead of the plan's. */
  transition: "plan" | "zoom_through";
  /** The 3D tilt-in at the start of each shot. */
  camera: boolean;
}

const LAB_FIELD: Partial<Record<FieldName, FieldName>> = {
  navy: "lab", paper: "lab", blue: "lab_violet", yellow: "lab_violet",
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
};

export function designOf(id: string | null | undefined): Design {
  return DESIGNS[(id as DesignId)] ?? DESIGNS.classic;
}

export function designVars(d: Design): CSSProperties {
  return d.vars as CSSProperties;
}
