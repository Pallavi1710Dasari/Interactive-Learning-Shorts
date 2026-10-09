// Reel chrome — REFERENCE_STYLE_ADDENDUM.md section 4.3: the step chip
// (walkthrough), the full-width progress segments (fix_story), and the small
// tracked-caps section labels above diagrams.

import { At } from "./Stage";
import { C, FONT, W, theme, type FieldName } from "./tokens";
import { clamp } from "./time";

/** Where the step chip's number sits — the chapter card's number flies here
 * when the card leaves (findings 8.2, "chip fly-in"). */
export const STEP_CHIP = { x: 60, y: 54, numberX: 150, numberY: 42, numberSize: 60 } as const;

export function StepChip({ n, of, field, p = 1, hideNumber = false, color }: {
  n: number; of: number; field: FieldName; p?: number; hideNumber?: boolean;
  /** The filled segments' colour — the reel's language tone (phase 3 badges). */
  color?: string;
}) {
  const th = theme(field);
  const q = clamp(p);
  return (
    <div style={{ position: "absolute", left: STEP_CHIP.x, top: STEP_CHIP.y, opacity: q,
                  transform: `translateY(${(1 - q) * -12}px)`, color: th.ink }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <span style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 24, letterSpacing: 3 }}>STEP</span>
        <span style={{ fontFamily: FONT.display, fontSize: STEP_CHIP.numberSize, lineHeight: 1,
                       opacity: hideNumber ? 0 : 1, width: 76 }}>
          {String(n).padStart(2, "0")}
        </span>
        <span style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 24, color: th.dark ? "rgba(255,255,255,0.6)" : C.sub }}>
          / {String(of).padStart(2, "0")}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        {Array.from({ length: of }, (_, i) => (
          <span key={i} style={{ width: 44, height: 7, borderRadius: 4,
                                 background: i < n ? (color ?? th.accent) : th.dark ? "rgba(255,255,255,0.22)" : "rgba(21,25,54,0.15)" }} />
        ))}
      </div>
    </div>
  );
}

/** fix_story's full-width progress segments: one per shot, the current one
 * filling with `progress`. */
export function ProgressSegments({ count, index, progress, field, color }: {
  count: number; index: number; progress: number; field: FieldName;
  /** The fill colour — the reel's language tone (phase 3 badges). */
  color?: string;
}) {
  const th = theme(field);
  return (
    <div style={{ position: "absolute", top: 58, left: 54, right: 54, display: "flex", gap: 12 }}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} style={{ flex: 1, height: 9, borderRadius: 6, overflow: "hidden",
                              background: th.dark ? "rgba(255,255,255,0.2)" : "rgba(21,25,54,0.13)" }}>
          <div style={{ height: "100%", background: color ?? (th.dark ? C.yellow : C.indigo),
                        width: `${i < index ? 100 : i === index ? clamp(progress) * 100 : 0}%` }} />
        </div>
      ))}
    </div>
  );
}

/** "THE SHELF", "BATCH", "FOLLOW ONE SENTENCE" — small tracked caps. */
export function SectionLabel({ text, x, y, field, p = 1, align = "left", accent = false }: {
  text: string; x: number; y: number; field: FieldName; p?: number; align?: "left" | "center"; accent?: boolean;
}) {
  const th = theme(field);
  return (
    <At x={x} y={y} style={{ opacity: clamp(p), transform: align === "center" ? "translateX(-50%)" : undefined }}>
      <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 27, letterSpacing: 5.4, whiteSpace: "nowrap",
                    color: accent ? th.accent : th.dark ? "rgba(255,255,255,0.85)" : C.ink }}>
        {text}
      </div>
    </At>
  );
}

/** The series mark in the corner (config.MOTION_SERIES — never the LLM). */
export function CornerMark({ text, field }: { text: string; field: FieldName }) {
  const th = theme(field);
  return (
    <div style={{ position: "absolute", right: W * 0.055, bottom: 1920 * 0.036, fontSize: 34, fontWeight: 700,
                  color: th.dark ? "rgba(255,255,255,0.75)" : C.indigo }}>{text}</div>
  );
}
