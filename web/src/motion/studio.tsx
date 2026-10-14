// The STUDIO design's own pieces (designs.ts, 2026-10-13): everything here
// replaces something the reference reels had — the background (no grid floor,
// no glow), the section label ("// SECTION" -> a section ribbon), the progress
// bar (segments -> a timeline thread down the left edge) and the field
// transitions (iris / bar wipe / stripes -> card flip, marker swipe, focus
// pull, card stack). Colours come from the frame's palette (tokens.ts
// applyPalette). Pure in t.

import type { ReactNode } from "react";
import { Layer } from "./Stage";
import { C, FIELDS, FONT, H, LOOK, W, display, theme, type FieldName } from "./tokens";
import { clamp, ease, hash3, lerp, seg } from "./time";

/** The palette's base, a fine paper/chalk grain and a soft vignette. */
export function StudioBackground({ field }: { field: FieldName }) {
  const th = theme(field);
  const grain = LOOK.palette?.grain ?? 0.05;
  const dots = [];
  for (let i = 0; i < 70; i++) {
    dots.push(<circle key={i} cx={hash3(11, i) * 96} cy={hash3(23, i) * 96} r={0.6 + hash3(37, i) * 1.1}
                      fill={th.dark ? "#FFFFFF" : "#3B2F1E"} opacity={0.35 + 0.65 * hash3(41, i)} />);
  }
  return (
    <Layer style={{ background: FIELDS[field] }}>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0, opacity: grain }}>
        <defs><pattern id={`grain-${field}`} width={96} height={96} patternUnits="userSpaceOnUse">{dots}</pattern></defs>
        <rect width={W} height={H} fill={`url(#grain-${field})`} />
      </svg>
      <div style={{ position: "absolute", inset: 0,
                    background: `radial-gradient(1400px 1100px at 50% 38%, transparent 55%, ${th.dark ? "rgba(0,0,0,0.32)" : "rgba(80,60,30,0.10)"} 100%)` }} />
    </Layer>
  );
}

/** "Why it fails" — the beat's step number in a round knot and its name, on a
 * tab that hangs from the left edge. Replaces the tracked-caps label. */
export function SectionRibbon({ text, n, field, p = 1, y = 150 }: { text: string; n: number; field: FieldName; p?: number; y?: number }) {
  const th = theme(field);
  const words = text.toLowerCase();
  const label = words.charAt(0).toUpperCase() + words.slice(1);
  const q = ease.outCubic(clamp(p));
  return (
    <div data-part="label" style={{ position: "absolute", left: 0, top: y, display: "flex", alignItems: "center", gap: 16,
                  padding: "10px 26px 10px 22px", borderRadius: "0 18px 18px 0", background: th.surface,
                  boxShadow: th.dark ? "0 4px 0 rgba(0,0,0,0.3)" : "0 4px 0 rgba(60,45,20,0.12)",
                  transform: `translateX(${(1 - q) * -260}px)` }}>
      <div style={{ width: 44, height: 44, borderRadius: 22, background: th.accent, color: th.dark ? "#14120E" : "#FFFFFF",
                    display: "grid", placeItems: "center", fontFamily: FONT.body, fontWeight: 700, fontSize: 24 }}>{n}</div>
      <div style={{ ...display(40), color: th.surfaceInk, lineHeight: 1, whiteSpace: "nowrap" }}>{label}</div>
    </div>
  );
}

/** The reel's progress as a thread down the left edge, one knot per shot: the
 * shots done are filled, the one playing fills as it plays. */
export function TimelineThread({ count, index, progress, field, color }: {
  count: number; index: number; progress: number; field: FieldName; color?: string;
}) {
  const th = theme(field);
  const x = 18, top = 300, bottom = 1500;
  const step = (bottom - top) / Math.max(1, count - 1);
  const ink = color ?? th.accent;
  const filledTo = top + step * (index + clamp(progress));
  return (
    <svg data-part="progress" width={40} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
      <line x1={x} y1={top} x2={x} y2={bottom} stroke={th.dark ? "rgba(255,255,255,0.16)" : "rgba(40,30,15,0.16)"} strokeWidth={3}
            strokeLinecap="round" />
      <line x1={x} y1={top} x2={x} y2={Math.min(bottom, filledTo)} stroke={ink} strokeWidth={3} strokeLinecap="round" />
      {Array.from({ length: count }, (_, i) => {
        const y = top + i * step;
        const done = i < index, now = i === index;
        return <circle key={i} cx={x} cy={y} r={now ? 7.5 : 5} fill={done || now ? ink : FIELDS[field]}
                       stroke={done || now ? ink : th.dark ? "rgba(255,255,255,0.3)" : "rgba(40,30,15,0.3)"} strokeWidth={2.5} />;
      })}
    </svg>
  );
}

// ---------------------------------------------------------------- transitions

export type StudioTransitionKind = "card_flip" | "marker_swipe" | "focus_pull" | "card_stack";
/** The plan names its transitions from the old rotation (Python keeps it);
 * the studio draws each as one of its own, never the same twice in a row. */
export const STUDIO_TRANSITIONS: Record<string, StudioTransitionKind> = {
  iris: "focus_pull", bar_wipe: "marker_swipe", double_bar_wipe: "card_stack",
  diagonal_stripes: "card_flip", stack_rise: "marker_swipe", type_scatter: "focus_pull",
};
export const STUDIO_DUR = 0.8;

export function StudioTransition({ kind, to, t, outgoing, incoming }: {
  kind: StudioTransitionKind; to: FieldName; t: number; outgoing: ReactNode; incoming: ReactNode;
}) {
  const p = clamp(t / STUDIO_DUR);
  if (p >= 1) return <>{incoming}</>;
  const base = <div style={{ position: "absolute", inset: 0, background: FIELDS[to] }} />;
  if (kind === "card_flip") {
    // the shot turns over like an index card: out to edge-on, the next one in
    const a = ease.inOutCubic(p);
    const out = a < 0.5;
    const deg = out ? lerp(0, 90, a * 2) : lerp(-90, 0, (a - 0.5) * 2);
    return <Layer>{base}
      <div style={{ position: "absolute", inset: 0, perspective: 2400 }}>
        <div style={{ position: "absolute", inset: 0, transform: `rotateY(${deg}deg)`, transformOrigin: "50% 50%",
                      filter: `brightness(${1 - Math.abs(deg) / 300})` }}>{out ? outgoing : incoming}</div>
      </div>
    </Layer>;
  }
  if (kind === "marker_swipe") {
    // a highlighter stroke sweeps across; behind it is the next shot
    const s = ease.inOutCubic(p);
    const x = lerp(-W * 0.9, W * 1.25, s);
    const band = W * 0.9;
    return <Layer>
      <div style={{ position: "absolute", inset: 0, clipPath: `polygon(0 0, ${x}px 0, ${x - 260}px ${H}px, 0 ${H}px)` }}>{incoming}</div>
      <div style={{ position: "absolute", inset: 0, clipPath: `polygon(${x}px 0, ${W * 3}px 0, ${W * 3}px ${H}px, ${x - 260}px ${H}px)` }}>{outgoing}</div>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        <path d={`M${x - band * 0.25} -40 L${x + band * 0.12} -40 L${x - 260 + band * 0.12} ${H + 40} L${x - 260 - band * 0.25} ${H + 40} Z`}
              fill={C.yellow} opacity={0.82} />
      </svg>
    </Layer>;
  }
  if (kind === "focus_pull") {
    // focus racks from the old shot to the new: a short blur, never a long one
    const a = ease.inOutCubic(p);
    return <Layer>{base}
      <div style={{ position: "absolute", inset: 0, opacity: 1 - a, transform: `scale(${1 + 0.04 * a})`,
                    filter: `blur(${(4 * a).toFixed(2)}px)` }}>{outgoing}</div>
      <div style={{ position: "absolute", inset: 0, opacity: a, transform: `scale(${0.97 + 0.03 * a})`,
                    filter: `blur(${(4 * (1 - a)).toFixed(2)}px)` }}>{incoming}</div>
    </Layer>;
  }
  // card_stack: the next shot slides up over the last, like a card dealt on top
  const a = ease.outCubic(seg(p, 0, 1));
  return <Layer>{base}
    <div style={{ position: "absolute", inset: 0, transform: `scale(${1 - 0.06 * a})`, transformOrigin: "50% 40%",
                  filter: `brightness(${1 - 0.35 * a})` }}>{outgoing}</div>
    <div style={{ position: "absolute", inset: 0, transform: `translateY(${(1 - a) * H}px)`,
                  boxShadow: "0 -30px 60px rgba(0,0,0,0.35)", borderRadius: `${lerp(40, 0, a)}px ${lerp(40, 0, a)}px 0 0`, overflow: "hidden" }}>
      {incoming}
    </div>
  </Layer>;
}
