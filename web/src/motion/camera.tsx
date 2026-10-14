// The virtual CAMERA and CURSOR (shorts/motion_camera.py writes the cues).
//
// Camera: a shot's visual is drawn in its viewport; a cue frames one rect in
// it (a code token, a memory slot, a button) at a zoom of 1.15-1.8. It eases
// in so the zoom LANDS on the cue word, holds with a slow push, and eases back
// out — or hands straight over to the next framing. Moves are slow and smooth
// (a cubic ease over 0.7 s, interpolated in log-zoom so the zoom speed feels
// even), with a slight motion blur only while it moves. The framing formula
// is motion_camera.framing: the rect always fits, the layer always covers the
// viewport.
//
// Cursor: a vector arrow drawn in SCREEN space (it never scales with the zoom),
// gliding along a curved path between its targets, pressing with a ripple on
// a click, and hiding behind a caret while it types into the code editor.
//
// Pure in t, like everything the player draws.

import type { ReactNode } from "react";
import type { CameraCue, CursorCue, PlanShot, Rect } from "./scene/types";
import { C } from "./tokens";
import { clamp, ease, lerp, seg } from "./time";

export const CAMERA = { move: 0.7, margin: 48, push: 0.035 } as const;

export interface Framing { s: number; fx: number; fy: number }

/** motion_camera.framing: the rect at about `zoom`, fitted and clamped. */
export function framingOf(rect: Rect, zoom: number, vp: Rect): Framing {
  const [x, y, w, h] = rect;
  const [vx, vy, vw, vh] = vp;
  const fit = Math.min((vw - 2 * CAMERA.margin) / Math.max(1, w), (vh - 2 * CAMERA.margin) / Math.max(1, h));
  const s = Math.max(1, Math.min(zoom, fit));
  const hw = vw / (2 * s), hh = vh / (2 * s);
  const fx = Math.min(Math.max(x + w / 2, vx + hw), vx + vw - hw);
  const fy = Math.min(Math.max(y + h / 2, vy + hh), vy + vh - hh);
  return { s, fx, fy };
}

function wide(vp: Rect): Framing {
  return { s: 1, fx: vp[0] + vp[2] / 2, fy: vp[1] + vp[3] / 2 };
}

function mix(a: Framing, b: Framing, p: number): Framing {
  // log-zoom so equal steps of p feel like equal zoom speed
  const s = Math.exp(lerp(Math.log(a.s), Math.log(b.s), p));
  return { s, fx: lerp(a.fx, b.fx, p), fy: lerp(a.fy, b.fy, p) };
}

/** The camera's framing at t (wide when the shot has no cue on). */
export function cameraAt(cues: CameraCue[] | undefined, vp: Rect, t: number): Framing {
  if (!cues?.length) return wide(vp);
  let k = -1;
  for (let i = 0; i < cues.length; i++) if (t >= cues[i].t0) k = i;
  if (k < 0) return wide(vp);
  const c = cues[k];
  const prev = k > 0 && cues[k - 1].t1 >= c.t0 - 1e-3 ? cues[k - 1] : null;
  const from = prev ? framingOf(prev.rect, prev.zoom, vp) : wide(vp);
  const to = framingOf(c.rect, c.zoom, vp);
  // the slow push while it holds
  const hold = seg(t, c.t0 + CAMERA.move, Math.max(0.1, c.t1 - c.t0 - CAMERA.move));
  const pushed = { ...to, s: to.s * (1 + CAMERA.push * ease.inOutQuad(hold)) };
  let f = mix(from, pushed, ease.inOutCubic(seg(t, c.t0, CAMERA.move)));
  const next = cues[k + 1];
  if (t >= c.t1 && !(next && next.t0 <= c.t1 + 1e-3)) f = mix(f, wide(vp), ease.inOutCubic(seg(t, c.t1, CAMERA.move)));
  return f;
}

/** A frame point after the framing (screen units). */
export function project(f: Framing, vp: Rect, x: number, y: number): [number, number] {
  return [vp[0] + vp[2] / 2 + (x - f.fx) * f.s, vp[1] + vp[3] / 2 + (y - f.fy) * f.s];
}

/** The shot's visual under the camera: clipped to its viewport, transformed,
 * with a slight blur only while the camera moves. */
export function CameraLayer({ shot, vp, t, children }: { shot: PlanShot; vp: Rect; t: number; children: ReactNode }) {
  if (!shot.camera?.length) return <>{children}</>;
  const f = cameraAt(shot.camera, vp, t);
  const g = cameraAt(shot.camera, vp, t + 1 / 30);
  // speed in screen px per frame: how far a point at the viewport centre moves
  const [ax, ay] = project(f, vp, f.fx, f.fy);
  const [bx, by] = project(g, vp, f.fx, f.fy);
  const speed = Math.hypot(bx - ax, by - ay) + Math.abs(g.s - f.s) * 400;
  // a hint of blur on a fast move only: never enough to soften text at rest
  const blur = speed > 6 ? Math.min(0.8, (speed - 6) * 0.04) : 0;
  const [vx, vy, vw, vh] = vp;
  const tx = vx + vw / 2 - f.fx * f.s, ty = vy + vh / 2 - f.fy * f.s;
  return (
    <div data-part="camera" style={{ position: "absolute", left: vx, top: vy, width: vw, height: vh, overflow: "hidden" }}>
      <div style={{ position: "absolute", left: -vx, top: -vy, width: 1080, height: 1920, transformOrigin: "0 0",
                    transform: `translate(${tx}px, ${ty}px) scale(${f.s})`, filter: blur > 0.15 ? `blur(${blur.toFixed(2)}px)` : undefined }}>
        {children}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------- cursor

const GLIDE = 0.65;      // seconds a glide takes
const PRESS = 0.12;      // the press lands this long after it arrives
const REST: [number, number] = [930, 1180];

/** Where the cursor's tip rests on a target: just under its bottom edge,
 * right of centre, so the arrow never covers the text it points at. */
function aim(r: Rect): [number, number] { return [r[0] + r[2] * 0.58, r[1] + r[3] + 6]; }

/** Where the cursor is at t, in FRAME units (before the camera), and what it does. */
export function cursorAt(cues: CursorCue[] | undefined, t: number):
  { x: number; y: number; on: number; press: number; ripple: number; typing: CursorCue | null } | null {
  if (!cues?.length) return null;
  const first = cues[0], last = cues[cues.length - 1];
  const end = last.do === "type" ? (last.t_end ?? last.t) : last.t;
  const on = clamp(Math.min((t - (first.t - GLIDE - 0.4)) / 0.3, (end + 1.0 - t) / 0.4));
  if (on <= 0) return null;
  // the anchor before t and the next one
  let k = -1;
  for (let i = 0; i < cues.length; i++) if (t >= cues[i].t - GLIDE) k = i;
  const target = (c: CursorCue): [number, number] => c.do === "type"
    ? [c.rect[0] + c.rect[2] - 8, c.rect[1] + c.rect[3] + 26] : aim(c.rect);
  let pos: [number, number];
  if (k < 0) pos = REST;
  else {
    const c = cues[k];
    const from = k > 0 ? target(cues[k - 1]) : REST;
    const to = target(c);
    const p = ease.inOutCubic(seg(t, c.t - GLIDE - PRESS, GLIDE));
    // a curve: the control point sits off the straight line, to one side
    const mx = (from[0] + to[0]) / 2, my = (from[1] + to[1]) / 2;
    const dx = to[0] - from[0], dy = to[1] - from[1];
    const cx = mx - dy * 0.22, cy = my + dx * 0.22;
    pos = [(1 - p) * (1 - p) * from[0] + 2 * (1 - p) * p * cx + p * p * to[0],
           (1 - p) * (1 - p) * from[1] + 2 * (1 - p) * p * cy + p * p * to[1]];
  }
  const click = [...cues].reverse().find((c) => c.do === "click" && t >= c.t - 0.05 && t <= c.t + 0.9);
  const press = click ? Math.sin(Math.PI * clamp((t - click.t + 0.05) / 0.22)) : 0;
  const ripple = click ? clamp((t - click.t) / 0.6) : 0;
  const typing = cues.find((c) => c.do === "type" && t >= c.t && t <= (c.t_end ?? c.t) + 0.3) ?? null;
  return { x: pos[0], y: pos[1], on, press, ripple: click && t >= click.t ? ripple : 0, typing };
}

/** How many characters of a typed cue are on screen at t: even, with a
 * small hash jitter so it reads as a person typing, finished by t_end. */
export function typedChars(c: CursorCue, t: number): number {
  const text = c.text ?? "";
  const p = clamp((t - c.t) / Math.max(0.2, (c.t_end ?? c.t) - c.t));
  return Math.floor(p * text.length + 1e-6);
}

/** The cursor, drawn in screen space over the shot (after the camera). */
export function CursorLayer({ shot, vp, t }: { shot: PlanShot; vp: Rect; t: number }) {
  const c = cursorAt(shot.cursor, t);
  if (!c) return null;
  const f = cameraAt(shot.camera, vp, t);
  const [x, y] = project(f, vp, c.x, c.y);
  const scale = 1 - 0.12 * c.press;
  return (
    <div data-part="cursor" style={{ position: "absolute", left: 0, top: 0, width: 1080, height: 1920, pointerEvents: "none", opacity: c.on }}>
      {c.ripple > 0 && c.ripple < 1 && (
        <div style={{ position: "absolute", left: x - 70, top: y - 70, width: 140, height: 140, borderRadius: 70,
                      border: `5px solid ${C.white}`, opacity: 0.85 * (1 - c.ripple), transform: `scale(${0.3 + 0.9 * c.ripple})`,
                      boxShadow: "0 0 24px rgba(255,255,255,0.45)" }} />
      )}
      {!c.typing && (
        <svg width={64} height={78} viewBox="0 0 32 39" style={{ position: "absolute", left: x - 6, top: y - 4,
                                                                 transform: `scale(${scale})`, transformOrigin: "6px 4px",
                                                                 filter: "drop-shadow(0 6px 10px rgba(0,0,0,0.45))" }}>
          <path d="M3 2 L3 30 L10.5 23.2 L15.4 35 L20.2 33 L15.4 21.6 L25.5 21.6 Z" fill={C.white} stroke="#0B1030" strokeWidth={2.2}
                strokeLinejoin="round" />
        </svg>
      )}
    </div>
  );
}
