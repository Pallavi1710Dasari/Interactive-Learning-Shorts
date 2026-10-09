// Chapter transitions — REFERENCE_STYLE_ADDENDUM.md 4.6 A and findings 8.2-8.4.
//
// Every field transition is: an EXIT DIM (the old content and caption fade
// to ~50 % over 0.3 s), then 0.55 s of shapes on an ease-in-out curve that
// lead the new field in. Shapes use FIELD colours only — navy, blue, paper,
// yellow — never coral or mint (decision 2026-10-01). The reel uses a
// different one at each chapter change; planTransitions() rotates them and
// never repeats one twice in a row.
//
// Each takes the outgoing and incoming scenes as children, so a transition
// can blur, squeeze or clip either one. Field transitions are only for
// chapter and beat changes; inside a chapter use hard cuts.

import type { ReactNode } from "react";
import { Layer } from "./Stage";
import { C, FIELDS, FONT, H, W, theme, type FieldName } from "./tokens";
import { clamp, ease, hash3, lerp, seg, type Pt } from "./time";
import type { TitleWord } from "./objects/editorial";

export const EXIT_DIM = 0.3;
export const MOVE = 0.55;
export const TRANSITION_DUR = EXIT_DIM + MOVE;

export type TransitionKind = "iris" | "bar_wipe" | "double_bar_wipe" | "diagonal_stripes" | "stack_rise";
export const ROTATION: TransitionKind[] = ["iris", "bar_wipe", "double_bar_wipe", "diagonal_stripes", "stack_rise"];

/** One transition per chapter change, rotating, never the same twice in a row. */
export function planTransitions(count: number, offset = 0): TransitionKind[] {
  return Array.from({ length: count }, (_, i) => ROTATION[(i + offset) % ROTATION.length]);
}

/** The exit dim's opacity for the outgoing content at time t. */
export function exitDim(t: number): number {
  return 1 - 0.5 * ease.outQuad(seg(t, 0, EXIT_DIM));
}

/** The colour that leads the new field in: yellow, unless yellow is one of
 * the two fields, then the first of blue, navy, paper that is neither. */
export function leadColor(from: FieldName, to: FieldName): string {
  const pick = (["yellow", "blue", "navy", "paper"] as FieldName[]).find((f) => f !== from && f !== to)!;
  return FIELDS[pick];
}

/** The rectangle of the frame clipped to the half-plane x·n <= s. */
function halfPlane(n: Pt, s: number): Pt[] {
  const rect: Pt[] = [[0, 0], [W, 0], [W, H], [0, H]];
  const inside = (p: Pt) => p[0] * n[0] + p[1] * n[1] <= s;
  const out: Pt[] = [];
  for (let i = 0; i < rect.length; i++) {
    const a = rect[i], b = rect[(i + 1) % rect.length];
    const da = a[0] * n[0] + a[1] * n[1] - s, db = b[0] * n[0] + b[1] * n[1] - s;
    if (inside(a)) out.push(a);
    if ((da < 0) !== (db < 0)) {
      const k = da / (da - db);
      out.push([lerp(a[0], b[0], k), lerp(a[1], b[1], k)]);
    }
  }
  return out;
}
const poly = (pts: Pt[]) => (pts.length ? `polygon(${pts.map(([x, y]) => `${x}px ${y}px`).join(", ")})` : "polygon(0 0, 0 0, 0 0)");
const polyPoints = (pts: Pt[]) => pts.map(([x, y]) => `${x},${y}`).join(" ");

export function FieldTransition({ kind, from, to, t, outgoing, incoming, origin = [W / 2, H / 2] }: {
  kind: TransitionKind; from: FieldName; to: FieldName; t: number;
  outgoing: ReactNode; incoming: ReactNode; origin?: Pt;
}) {
  const p = ease.inOutCubic(seg(t, EXIT_DIM, MOVE));
  const lead = leadColor(from, to);
  const dim = exitDim(t);
  if (p >= 1) return <Layer style={{ background: FIELDS[to] }}>{incoming}</Layer>;

  let shapes: ReactNode = null;
  let clip = "inset(0 100% 0 0)";
  let outStyle: React.CSSProperties = {};

  if (kind === "iris") {
    const [ox, oy] = origin;
    const rMax = Math.max(Math.hypot(ox, oy), Math.hypot(W - ox, oy), Math.hypot(ox, H - oy), Math.hypot(W - ox, H - oy));
    // The ring holds for a few frames before the new field opens inside it
    // (findings 8.3): the inner edge lags the outer by a third of the move.
    const outer = rMax * 1.05 * ease.outCubic(clamp(p / 0.8));
    const inner = rMax * ease.inCubic(clamp((p - 0.35) / 0.65));
    shapes = <circle cx={ox} cy={oy} r={outer} fill={lead} />;
    clip = `circle(${inner}px at ${ox}px ${oy}px)`;
  } else if (kind === "bar_wipe") {
    const bw = W * 0.16;
    const left = lerp(-bw, W, p);
    shapes = <rect x={left} y={0} width={bw} height={H} fill={lead} />;
    clip = `inset(0 ${W - Math.max(0, left)}px 0 0)`;
  } else if (kind === "double_bar_wipe") {
    // Right to left, the way the reference runs it; the old content squeezes
    // into slivers and blurs as the bars pass (findings 8.3).
    const b1 = W * 0.11, b2 = W * 0.05;
    const front = lerp(W, -(b1 + b2), p);
    shapes = (
      <>
        <rect x={front} y={0} width={b1} height={H} fill={lead} />
        <rect x={front + b1} y={0} width={b2} height={H} fill={FIELDS[to]} />
        <rect x={front + b1} y={0} width={3} height={H} fill={theme(to).dark ? "rgba(255,255,255,0.25)" : "rgba(21,25,54,0.18)"} />
      </>
    );
    clip = `inset(0 0 0 ${Math.max(0, front + b1)}px)`;
    outStyle = { transform: `scaleX(${lerp(1, 0.82, p)})`, transformOrigin: "0 50%", filter: `blur(${8 * p}px)` };
  } else if (kind === "diagonal_stripes") {
    // Bands at ~30 degrees, sweeping from the top-left corner (decision
    // 2026-10-01: lead colour + the new field, no coral).
    const ang = (30 * Math.PI) / 180;
    const n: Pt = [Math.cos(ang), Math.sin(ang)];
    const sMax = W * n[0] + H * n[1];
    const b1 = 300, b2 = 160;
    const s = lerp(0, sMax + b1 + b2, p);
    const front = halfPlane(n, s);
    const mid = halfPlane(n, s - b1);
    shapes = (
      <>
        <polygon points={polyPoints(front)} fill={lead} />
        <polygon points={polyPoints(mid)} fill={FIELDS[to]} />
      </>
    );
    clip = poly(halfPlane(n, s - b1 - b2));
  } else if (kind === "stack_rise") {
    const band = H * 0.16 * (1 - 0.65 * p);
    const top = lerp(H, -band, p);
    shapes = (
      <>
        <rect x={0} y={top} width={W} height={band} fill={lead} />
        <rect x={0} y={top + band} width={W} height={H} fill={FIELDS[to]} />
      </>
    );
    clip = `inset(${Math.max(0, top + band + H * 0.04)}px 0 0 0)`;
  }

  return (
    <Layer style={{ background: FIELDS[from] }}>
      <Layer style={{ opacity: dim, ...outStyle }}>{outgoing}</Layer>
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>{shapes}</svg>
      <Layer style={{ clipPath: clip, background: FIELDS[to] }}>{incoming}</Layer>
    </Layer>
  );
}

// ------------------------------------------------------------ type_scatter

export const SCATTER = { punch: 0.0, scatterAt: 0.15, scatterDur: 0.45, flashAt: 0.3, answerAt: 0.38, answerDur: 0.3, dur: 1.0 } as const;

/** Hook only: the question's words rotate and scatter outward with a
 * one-frame flash, and the answer line punches in, its first word slightly
 * ahead (findings 8.3). The answer may be coral — a failure moment. */
export function TypeScatter({ question, answer, t, field, x = 54, y = 300, size = 168, answerY = 760,
                              answerColor = C.coral, seed = 3 }: {
  question: TitleWord[][]; answer: string; t: number; field: FieldName; x?: number; y?: number;
  size?: number; answerY?: number; answerColor?: string; seed?: number;
}) {
  const th = theme(field);
  const k = SCATTER;
  const sp = ease.inCubic(seg(t, k.scatterAt, k.scatterDur));
  const flash = t >= k.flashAt && t < k.flashAt + 1 / 30;
  const [first, ...rest] = answer.split(" ");
  const p1 = ease.outBack(seg(t, k.punch, 0.18), 2);
  const p2 = ease.outBack(seg(t, k.answerAt, k.answerDur), 1.6);
  let wi = 0;
  return (
    <>
      <div style={{ position: "absolute", left: x, top: y, fontFamily: FONT.display, fontSize: size, lineHeight: 0.92,
                    textTransform: "uppercase", color: th.ink }}>
        {question.map((line, li) => (
          <div key={li} style={{ whiteSpace: "nowrap" }}>
            {line.map((w, i) => {
              const r = hash3(seed, wi), r2 = hash3(seed, wi, 1);
              wi++;
              const rot = (r - 0.5) * 56 * sp;
              const dx = (r - 0.5) * 420 * sp, dy = (-0.4 - r2 * 0.8) * 260 * sp;
              return (
                <span key={i} style={{ display: "inline-block", marginRight: size * 0.22,
                                       color: w.accent ? th.accent : undefined, opacity: 1 - sp,
                                       transform: `translate(${dx}px, ${dy}px) rotate(${rot}deg)` }}>{w.text}</span>
              );
            })}
          </div>
        ))}
      </div>
      <div style={{ position: "absolute", left: x, top: answerY, fontFamily: FONT.display, fontSize: size * 0.95,
                    lineHeight: 1, color: answerColor, textTransform: "uppercase", whiteSpace: "nowrap" }}>
        <span style={{ display: "inline-block", opacity: clamp(p1 * 2), transform: `scale(${lerp(1.4, 1, clamp(p1))})`,
                       transformOrigin: "0 100%", marginRight: size * 0.2 }}>{first}</span>
        <span style={{ display: "inline-block", opacity: clamp(p2 * 2), transform: `scale(${lerp(1.5, 1, clamp(p2))})`,
                       transformOrigin: "0 100%" }}>{rest.join(" ")}</span>
      </div>
      {flash && <div style={{ position: "absolute", inset: 0, background: "#5E6378", opacity: 0.85 }} />}
    </>
  );
}
