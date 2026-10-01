// Time helpers for the motion library. EVERY motion component is a pure
// function of `t` (seconds): no CSS animations, no transitions, no timers, no
// Math.random. That is what lets the capture renderer seek to any frame and
// get exactly that frame, and what the purity check (purity.test.tsx)
// enforces.

import { FPS } from "./tokens";

export const clamp = (x: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));
export const lerp = (a: number, b: number, p: number) => a + (b - a) * p;

/** Progress 0..1 of a span that starts at `start` and lasts `dur`. */
export function seg(t: number, start: number, dur: number): number {
  if (dur <= 0) return t >= start ? 1 : 0;
  return clamp((t - start) / dur);
}

/** The i-th of a row of staggered spans. */
export function stagger(t: number, start: number, i: number, gap: number, dur: number) {
  return seg(t, start + i * gap, dur);
}

export const ease = {
  linear: (p: number) => p,
  inQuad: (p: number) => p * p,
  outQuad: (p: number) => 1 - (1 - p) * (1 - p),
  inOutQuad: (p: number) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2),
  inCubic: (p: number) => p * p * p,
  outCubic: (p: number) => 1 - Math.pow(1 - p, 3),
  inOutCubic: (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
  outExpo: (p: number) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
  /** Overshoot then settle — pops and stamps. */
  outBack: (p: number, s = 1.70158) => 1 + (s + 1) * Math.pow(p - 1, 3) + s * Math.pow(p - 1, 2),
};

/** 0 -> 1 -> 0 over the span: a pulse. */
export function pulse(t: number, start: number, dur: number): number {
  const p = seg(t, start, dur);
  return p <= 0 || p >= 1 ? 0 : Math.sin(Math.PI * p);
}

/** A deterministic random stream (mulberry32). Same seed, same numbers, every
 * render — so text_scramble and the digit texture are frame-exact. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let x = a;
    x = Math.imul(x ^ (x >>> 15), x | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

/** One random number for (seed, a, b) without carrying a stream. */
export function hash3(seed: number, a: number, b = 0): number {
  return rng(seed * 73856093 ^ a * 19349663 ^ b * 83492791)();
}

/** Snap a time to the frame grid the MP4 is cut on. */
export const toFrame = (t: number) => Math.round(t * FPS) / FPS;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Colour between two hex colours. */
export function mix(a: string, b: string, p: number): string {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  const q = clamp(p);
  const c = (x: number, y: number) => Math.round(lerp(x, y, q));
  return `rgb(${c(r1, r2)}, ${c(g1, g2)}, ${c(b1, b2)})`;
}

/** Points along a polyline: the position at fraction p of its length, and
 * the total length. Pure geometry, so a connector pulse or an arrow draw
 * never asks the DOM where a path is. */
export type Pt = [number, number];
export function polylineLength(pts: Pt[]): number {
  let L = 0;
  for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return L;
}
export function pointAt(pts: Pt[], p: number): Pt {
  const L = polylineLength(pts);
  let want = clamp(p) * L;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const d = Math.hypot(x1 - x0, y1 - y0);
    if (want <= d || i === pts.length - 1) {
      const q = d === 0 ? 0 : clamp(want / d);
      return [lerp(x0, x1, q), lerp(y0, y1, q)];
    }
    want -= d;
  }
  return pts[pts.length - 1];
}
export const pathD = (pts: Pt[]) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
