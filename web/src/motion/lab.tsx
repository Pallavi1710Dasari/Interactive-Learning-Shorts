// Midnight Lab's own pieces (designs.ts): the glowing night background with
// its grid floor, the 3D tilt a shot settles from, and the zoom-through
// transition. Pure in t, like everything the player draws.

import type { ReactNode } from "react";
import { Layer } from "./Stage";
import { FIELDS, H, LAB, W, type FieldName } from "./tokens";
import { clamp, ease, lerp, seg } from "./time";

/** Night blue with two slow light blooms and a perspective grid floor whose
 * lines flow toward the viewer. `t` is the reel's clock. */
export function LabBackground({ field, t }: { field: FieldName; t: number }) {
  const violet = field === "lab_violet";
  const drift = (a: number) => Math.sin(t * 0.5 + a) * 60;
  const flow = (t * 0.35) % 1;
  const rows = 12;
  const centre = violet ? "#241E6B" : "#1B2566";
  return (
    <Layer style={{ background: FIELDS[field] }}>
      <div style={{ position: "absolute", inset: 0,
                    background: `radial-gradient(1300px 1000px at 50% 28%, ${centre} 0%, ${FIELDS[field]} 55%, #05081A 100%)` }} />
      {/* soft blooms of light: radial gradients, not blur filters (a large
          blur is slow to draw and the capture renderer drew it black) */}
      <div style={{ position: "absolute", left: -320 + drift(0), top: -20, width: 1100, height: 1100,
                    background: `radial-gradient(closest-side, ${violet ? "rgba(140,123,255,0.26)" : "rgba(66,226,255,0.2)"}, transparent)` }} />
      <div style={{ position: "absolute", left: 360 + drift(2), top: 700 + drift(1), width: 1040, height: 1040,
                    background: "radial-gradient(closest-side, rgba(140,123,255,0.26), transparent)" }} />
      <svg width={W} height={H} style={{ position: "absolute", inset: 0, opacity: 0.16 }}>
        {Array.from({ length: 15 }, (_, i) => <line key={i} x1={540} y1={1240} x2={-1100 + i * 235} y2={H} stroke={LAB.violet} strokeWidth={2} />)}
        {Array.from({ length: rows }, (_, i) => {
          const d = (i + flow) / rows;
          const y = 1240 + 680 * d * d;
          return <line key={`h${i}`} x1={0} x2={W} y1={y} y2={y} stroke={LAB.violet} strokeWidth={2} opacity={d} />;
        })}
      </svg>
    </Layer>
  );
}

export const TILT_DUR = 1.0;

/** A shot's objects settling from a slight 3D tilt over its first second.
 * `local` is seconds since the shot started. At rest it is the identity
 * transform, so the layout is exactly where Python put it. */
export function LabCamera({ local, children }: { local: number; children: ReactNode }) {
  const s = ease.outCubic(seg(local, 0, TILT_DUR));
  if (s >= 1) return <>{children}</>;
  return (
    <div style={{ position: "absolute", inset: 0, perspective: 2200, perspectiveOrigin: "50% 35%" }}>
      <div style={{ position: "absolute", inset: 0, transformOrigin: "50% 35%",
                    transform: `rotateX(${lerp(9, 0, s)}deg) translateZ(${lerp(-120, 0, s)}px)` }}>
        {children}
      </div>
    </div>
  );
}

export const ZOOM_DUR = 0.85;

/** The camera flies into the outgoing shot (it grows, blurs and fades) and
 * out of the incoming one (it comes into focus from a little smaller). */
export function ZoomThrough({ t, outgoing, incoming }: { t: number; outgoing: ReactNode; incoming: ReactNode }) {
  const out = ease.inCubic(seg(t, 0, 0.5));
  const inn = ease.outCubic(seg(t, 0.3, ZOOM_DUR - 0.3));
  return (
    <>
      {out < 1 && (
        <Layer style={{ transform: `scale(${1 + 1.2 * out})`, transformOrigin: "50% 40%", filter: `blur(${14 * out}px)`, opacity: 1 - out }}>
          {outgoing}
        </Layer>
      )}
      {t > 0.3 && (
        <Layer style={{ transform: `scale(${lerp(0.78, 1, inn)})`, filter: inn < 1 ? `blur(${14 * (1 - inn)}px)` : undefined,
                        opacity: clamp(inn * 1.4) }}>
          {incoming}
        </Layer>
      )}
    </>
  );
}
