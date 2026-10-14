// Characters that TEACH (shorts/motion_teach.py directs them): the board
// staging, and the overlays laid on the rig's own pose after its life layer —
//
//   aim    an arm solved so the pointing finger points at the exact thing on
//          the board (shoulder angle from the shoulder pivot to the target,
//          a slight elbow bend, the hand in the "point" shape);
//   gaze   eyes and head turned to a thing on the board, or to the partner;
//   jaw    the mouth opened by the LOUDNESS of the recorded voice (the
//          track's envelope) on top of the word-timed mouth shapes;
//   count  a held finger count: the hand up beside the face, only the
//          fingers changing between counts (no wind-up through a sideways pose);
//   aha    a lightbulb over the head.
//
// Pure in t, like every other part of the player.

import type { Pose } from "../characters/rig/channels";
import { SHOULDER_Y } from "../characters/rig/Body";
import { HAND_POSES, handChannel, type HandPose } from "../characters/actions/handPoses";
import type { Skin } from "../characters/skins/types";
import library from "../library.json";
import { clamp, ease, lerp, seg } from "../time";
import type { CharacterTrack } from "./performance";
import type { Rect } from "../scene/types";

interface Spot { cx: number; top: number; scale: number }
export const BOARD = (library as unknown as {
  frame: { board: { src_placed: Rect; src_full: Rect; src_full_kind: Record<string, Rect>; dst: Rect; callout_right: number; explainer: Spot; asker: Spot; narrator: Spot; view_bottom: number;
                    chat: { top: number; bottom: number; font: number; line_h: number; chars: number; label_h: number; pad_y: number; gap: number } } }
}).frame.board;
const VIEW_TOP = 6;

/** How the visual's layout maps onto the board: frame point -> stage point.
 * A full-frame card maps the area its own content fills (src_full_kind), so
 * it is drawn as large as the board allows. */
export function boardMap(full: boolean | string): { s: number; x: number; y: number; src: Rect } {
  const src = typeof full === "string" ? (BOARD.src_full_kind[full] ?? BOARD.src_full) : full ? BOARD.src_full : BOARD.src_placed;
  const [dx, dy, dw, dh] = BOARD.dst;
  const s = Math.min(dw / src[2], dh / src[3]);
  return { s, x: dx + (dw - src[2] * s) / 2, y: dy, src };
}

export function toStage(full: boolean | string, px: number, py: number): [number, number] {
  const m = boardMap(full);
  return [m.x + (px - m.src[0]) * m.s, m.y + (py - m.src[1]) * m.s];
}

/** Where a track stands on the board stage. */
export function spotOf(track: CharacterTrack, n: number): Spot {
  if (n === 1) return BOARD.narrator;
  return track.side === "left" ? BOARD.asker : BOARD.explainer;
}

/** The rig-unit box a character occupies on the stage. */
export function placement(spot: Spot) {
  const w = 400 * spot.scale;
  return { left: spot.cx - w / 2, top: spot.top - VIEW_TOP * spot.scale, w, scale: spot.scale };
}

type Place = ReturnType<typeof placement>;

function toRig(p: Place, x: number, y: number): [number, number] {
  return [(x - p.left) / p.scale, (y - p.top) / p.scale];
}

function weight(t: number, t0: number, t1: number, inDur = 0.35, outDur = 0.45): number {
  return ease.inOutCubic(seg(t, t0, inDur)) * (1 - ease.inOutCubic(seg(t, t1, outDur)));
}

function setHand(pose: Pose, side: "L" | "R", hp: HandPose, w: number) {
  for (const f of Object.keys(hp) as (keyof HandPose)[]) {
    const ch = handChannel(side, f);
    (pose as Record<string, number>)[ch] = lerp((pose as Record<string, number>)[ch], hp[f], w);
  }
}

/** The frame point a stage-mapped rect's centre is at. */
function targetOf(rect: number[], full: boolean | string): [number, number] {
  return toStage(full, rect[0] + rect[2] / 2, rect[1] + rect[3] / 2);
}

/** The aim, gaze and jaw overlays at t. `partner`: the other character's
 * head on the stage. Returns the pose (a copy) and the lightbulb's progress. */
export function teach(pose: Pose, track: CharacterTrack, place: Place, skin: Skin, t: number,
                      partner: [number, number] | null): { pose: Pose; aha: number } {
  const out = { ...pose } as Pose;
  const o = out as Record<string, number>;
  let aha = 0;
  type Cue = { t: number; kind: string; name?: string; side?: "L" | "R" | null; until?: number | null; rect?: number[] | null; target?: string | null; full?: boolean | string };
  // looks at the partner first, so a look at the board (with a point) wins over them
  const cues = [...(track.cues as unknown as Cue[])].sort((a, b) =>
    Number(a.kind === "gaze" && a.target !== "partner") - Number(b.kind === "gaze" && b.target !== "partner"));
  for (const c of cues) {
    if (c.kind === "aim" && c.rect && t >= c.t - 0.05 && t <= (c.until ?? c.t) + 0.5) {
      const w = weight(t, c.t, c.until ?? c.t + 1.2);
      if (w <= 0) continue;
      const side = c.side ?? "L";
      const [tx, ty] = toRig(place, ...targetOf(c.rect, !!c.full));
      const px = side === "L" ? 200 - (skin.shoulderHalf - 6) : 200 + (skin.shoulderHalf - 6);
      const dx = tx - px, dy = ty - SHOULDER_Y;
      // the arm hangs along +y; a positive shoulder angle lifts it away from
      // the body (screen-left for L, screen-right for R, which is mirrored)
      const a = (Math.atan2(side === "L" ? -dx : dx, dy) * 180) / Math.PI;
      const elbow = 14;
      o[`shoulder${side}`] = lerp(o[`shoulder${side}`], a + elbow * 0.55, w);
      o[`elbow${side}`] = lerp(o[`elbow${side}`], elbow, w);
      o[`wrist${side}`] = lerp(o[`wrist${side}`], -elbow * 0.4, w);
      setHand(out, side, HAND_POSES.point, w);
      // the body turns a touch toward what it points at
      o.lean = lerp(o.lean, clamp(-dx / 60, -4, 4), w * 0.6);
    }
    if (c.kind === "gaze" && t >= c.t - 0.05 && t <= (c.until ?? c.t) + 0.4) {
      const w = weight(t, c.t, c.until ?? c.t + 1, 0.25, 0.3);
      if (w <= 0) continue;
      const head = [place.left + 200 * place.scale, place.top + 120 * place.scale];
      const tgt = c.target === "partner" || !c.rect ? partner : targetOf(c.rect, !!c.full);
      if (!tgt) continue;
      const dx = tgt[0] - head[0], dy = tgt[1] - head[1];
      o.lookX = lerp(o.lookX, clamp(dx / 330, -1, 1), w);
      o.lookY = lerp(o.lookY, clamp(dy / 420, -1, 1), w);
      o.headTurn = lerp(o.headTurn, clamp(dx / 900, -0.5, 0.5), w);
      o.headNod = lerp(o.headNod, clamp(dy / 2200, -0.14, 0.18), w);
    }
    if (c.kind === "count" && t >= c.t - 0.05 && t <= (c.until ?? c.t) + 0.5) {
      // the rig's own count pose (actions/hands.ts COUNT), held: the hand up
      // beside the face, only the fingers changing between counts
      const w = weight(t, c.t, c.until ?? c.t + 1.4, 0.32, 0.4);
      if (w > 0) {
        const side = c.side ?? "L";
        o[`shoulder${side}`] = lerp(o[`shoulder${side}`], 25, w);
        o[`elbow${side}`] = lerp(o[`elbow${side}`], -120, w);
        o[`wrist${side}`] = lerp(o[`wrist${side}`], 0, w);
        const fingers = (HAND_POSES as Record<string, HandPose>)[(c as unknown as { name: string }).name] ?? HAND_POSES.one;
        setHand(out, side, fingers, clamp(w * 1.6));
      }
    }
    if (c.kind === "aha" && t >= c.t && t <= c.t + 2.2) {
      aha = t - c.t;
    }
  }
  const env = (track as unknown as { env?: { t0: number; fps: number; v: number[] } | null }).env;
  if (env && env.v.length) {
    const i = (t - env.t0) * env.fps;
    const k = Math.floor(i);
    const v = k < 0 || k >= env.v.length - 1 ? 0 : lerp(env.v[k], env.v[k + 1], i - k);
    o.mouthOpen = o.mouthOpen * (0.45 + 0.85 * v);
  }
  return { pose: out, aha };
}

/** The lightbulb's look at `age` seconds after the aha (0 = none). */
export function bulbAt(age: number): { scale: number; glow: number; opacity: number } {
  if (age <= 0) return { scale: 0, glow: 0, opacity: 0 };
  const pop = ease.outBack(clamp(age / 0.35), 2.2);
  const out = 1 - seg(age, 1.7, 0.45);
  return { scale: pop, glow: 0.5 + 0.5 * Math.sin(age * 9), opacity: clamp(age / 0.12) * out };
}
