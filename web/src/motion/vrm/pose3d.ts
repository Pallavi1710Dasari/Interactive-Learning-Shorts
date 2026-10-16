// Posing a 3D VRM avatar at time t — a pure function of (track, plan, t):
// the same frame always gives the same pose. Nothing here reads a clock,
// and the spring-bone physics (which depends on the frames before) is never
// run.
//
// What drives what:
//   face, head, breathing — the 2D performance (cast/performance.ts) the
//     flat characters already use: its life layer's blinks, breathing and
//     sway, the word-timed mouth shapes, nods, head shakes and tilts;
//   mouth                 — those mouth shapes as VRM visemes (aa ee ih oh
//     ou), opened by the recorded voice's loudness (the track's envelope),
//     and shut whenever this character is not speaking;
//   expressions           — the director's cues, quiet and professional:
//     relaxed by default, a light smile at most, never a laugh;
//   arms and hands        — a 3D gesture set (below): point (bent elbow,
//     index out, the fingertip solved onto the target), present (palm up
//     toward the board), explain (both palms up at chest height, small beats
//     on the spoken words), shrug, thumbs up, a held finger count; relaxed,
//     slightly curled hands at rest; every change eased in and back out;
//   gaze                  — the eyes, and the head partly, on the element
//     being explained, on the other speaker, else on the camera.

import * as THREE from "three";
import type { VRM, VRMHumanBoneName } from "@pixiv/three-vrm";
import type { CharacterTrack } from "../cast/performance";
import type { Pose } from "../characters/rig/channels";
import { clamp, ease, lerp, seg } from "../time";

export type V3 = [number, number, number];
type Side = "left" | "right";
/** +1 for the character's left arm (it rests along +X), -1 for the right. */
const SIGN: Record<Side, number> = { left: 1, right: -1 };

export interface ArmShape {
  upper: V3; fore: V3;           // directions in the avatar's own frame, x for the LEFT arm (mirrored for the right)
  palm: V3;                      // where the palm faces
  fingers: [number, number, number, number]; // curl of index, middle, ring, little: 0 straight, 1 closed
  thumb: number;                 // 0 out, 1 tucked
  shoulder?: number;             // 0..1: the shoulder rises (a shrug)
}

/** The arm shapes, written for the character's LEFT arm (x outward). */
export const SHAPES: Record<string, ArmShape> = {
  // hanging by the side, elbow a little bent, palm toward the thigh, fingers softly curled
  rest: { upper: [0.16, -1, 0.04], fore: [0.1, -0.9, 0.38], palm: [-1, 0, 0.2], fingers: [0.32, 0.38, 0.42, 0.46], thumb: 0.25 },
  // both hands in front at chest height, palms up — "let me explain"
  explain: { upper: [0.36, -0.82, 0.48], fore: [-0.3, 0.42, 1], palm: [0.1, 1, 0.25], fingers: [0.12, 0.16, 0.2, 0.24], thumb: 0.15 },
  // one hand opens toward the thing being shown, palm up — "here's the idea"
  present: { upper: [0.4, -0.86, 0.32], fore: [0.62, 0.12, 0.78], palm: [0.15, 1, 0.2], fingers: [0.08, 0.1, 0.12, 0.15], thumb: 0.1 },
  // palms out and up, elbows in
  shrug: { upper: [0.22, -0.95, 0.22], fore: [0.72, 0.18, 0.62], palm: [0.35, 1, 0.25], fingers: [0.1, 0.12, 0.14, 0.16], thumb: 0.1, shoulder: 1 },
  // a fist at chest height, thumb up
  thumbsUp: { upper: [0.3, -0.9, 0.36], fore: [-0.38, 0.5, 0.78], palm: [-1, 0, 0], fingers: [1, 1, 1, 1], thumb: 0 },
  // the counting hand up in front of the shoulder, palm toward the viewer
  count: { upper: [0.3, -0.88, 0.46], fore: [-0.05, 0.72, 0.7], palm: [0, 0.1, 1], fingers: [1, 1, 1, 1], thumb: 0.9 },
  // pointing: index out, the others curled, thumb tucked (the direction is solved)
  point: { upper: [0.3, -0.6, 0.6], fore: [-0.5, 0.2, 0.85], palm: [0, -0.4, -1], fingers: [0, 1, 1, 1], thumb: 0.95 },
};
const COUNT_FINGERS: Record<string, [number, number, number, number]> = {
  one: [0, 1, 1, 1], two: [0, 0, 1, 1], three: [0, 0, 0, 1],
};

/** One cue in a track as the 3D layer reads it. */
type Cue = { t: number; kind: string; name?: string; side?: "L" | "R" | null; until?: number | null; rect?: number[] | null; target?: string | null; full?: boolean | string };

/** Which arm a cue's side means: the 2D "L" is the screen-left arm, which is
 * the character's RIGHT arm when it faces the viewer. */
const armOf = (s: "L" | "R" | null | undefined, fallback: Side): Side => (s === "L" ? "right" : s === "R" ? "left" : fallback);

/** Weight of a gesture held from t0 to t1: eased in over 0.35 s, out over 0.45 s. */
function held(t: number, t0: number, t1: number, inDur = 0.35, outDur = 0.45): number {
  return ease.inOutCubic(seg(t, t0, inDur)) * (1 - ease.inOutCubic(seg(t, t1, outDur)));
}

const GESTURE_DUR: Record<string, number> = { handsSpread: 2.0, presentLeft: 1.9, presentRight: 1.9, shrug: 1.5, thumbsUp: 1.4 };

export interface ArmProgram { shape: ArmShape; w: number; aim?: { stage: [number, number] } | null; beat: number }

/** What each arm is doing at t: a stack of shapes with weights, applied in
 * time order over the rest pose. `toStage` maps a cue's rect to stage pixels. */
export function armPrograms(track: CharacterTrack, t: number, words: { start: number; end: number }[], boardSide: Side,
                            toStage: (rect: number[], full: boolean | string) => [number, number]): Record<Side, ArmProgram[]> {
  const out: Record<Side, ArmProgram[]> = { left: [], right: [] };
  const outer: Side = boardSide === "left" ? "right" : "left";
  // a small beat on each word spoken while explaining
  const beat = words.reduce((b, w) => Math.max(b, t >= w.start && t <= w.start + 0.3 ? Math.sin(Math.PI * (t - w.start) / 0.3) : 0), 0);
  for (const c of track.cues as unknown as Cue[]) {
    if (c.kind === "aim" && c.rect) {
      const w = held(t, c.t, c.until ?? c.t + 1.2);
      if (w > 0) out[armOf(c.side, boardSide)].push({ shape: SHAPES.point, w, aim: { stage: toStage(c.rect, c.full ?? false) }, beat: 0 });
    } else if (c.kind === "count") {
      const w = held(t, c.t, c.until ?? c.t + 1.4, 0.32, 0.4);
      if (w > 0) out[armOf(c.side, boardSide)].push({ shape: { ...SHAPES.count, fingers: COUNT_FINGERS[c.name ?? "one"] ?? COUNT_FINGERS.one }, w, beat: 0 });
    } else if (c.kind === "gesture") {
      const dur = GESTURE_DUR[c.name ?? ""];
      if (!dur) continue;                     // nods, shakes, tilts: the head does those
      const w = held(t, c.t, c.t + dur);
      if (w <= 0) continue;
      if (c.name === "handsSpread") {
        out.left.push({ shape: SHAPES.explain, w, beat });
        out.right.push({ shape: SHAPES.explain, w, beat });
      } else if (c.name === "shrug") {
        out.left.push({ shape: SHAPES.shrug, w, beat: 0 });
        out.right.push({ shape: SHAPES.shrug, w, beat: 0 });
      } else if (c.name === "thumbsUp") {
        out[outer].push({ shape: SHAPES.thumbsUp, w, beat: 0 });
      } else {
        out[boardSide].push({ shape: SHAPES.present, w, beat: 0 });
      }
    }
  }
  return out;
}

// ------------------------------------------------------------------ solving

const tmpQ = new THREE.Quaternion();

function bone(vrm: VRM, name: VRMHumanBoneName): THREE.Object3D | null {
  return vrm.humanoid.getNormalizedBoneNode(name);
}

function worldQ(o: THREE.Object3D): THREE.Quaternion {
  o.updateWorldMatrix(true, false);
  return o.getWorldQuaternion(new THREE.Quaternion());
}

/** Turn a bone so its rest axis points along `dir` (world), with the palm
 * (the bone's rest -Y) turned as close to `palm` (world) as the axis allows. */
function aimBone(node: THREE.Object3D, rest: THREE.Vector3, dir: THREE.Vector3, palm: THREE.Vector3 | null) {
  const d = dir.clone().normalize();
  const q = new THREE.Quaternion().setFromUnitVectors(rest, d);
  if (palm) {
    const n = new THREE.Vector3(0, -1, 0).applyQuaternion(q);
    const want = palm.clone().sub(d.clone().multiplyScalar(palm.dot(d)));
    if (want.lengthSq() > 1e-6) {
      want.normalize();
      const angle = Math.atan2(n.clone().cross(want).dot(d), n.dot(want));
      q.premultiply(tmpQ.setFromAxisAngle(d, angle));
    }
  }
  const parent = worldQ(node.parent!);
  node.quaternion.copy(parent.invert().multiply(q));
  node.updateWorldMatrix(false, true);
}

/** The roll about the forearm `axis` (world) that turns the palm (the hand's
 * rest -Y, carried by the forearm) toward `palm` (world). */
function rollTo(lower: THREE.Object3D, axis: THREE.Vector3, palm: THREE.Vector3): number {
  const d = axis.clone().normalize();
  const n = new THREE.Vector3(0, -1, 0).applyQuaternion(worldQ(lower));
  const want = palm.clone().sub(d.clone().multiplyScalar(palm.dot(d)));
  if (want.lengthSq() < 1e-6) return 0;
  want.normalize();
  return Math.atan2(n.clone().cross(want).dot(d), n.dot(want));
}

/** Avatar-frame vector (x for the left arm) to world, for one side. */
function toWorld(v: V3, side: Side, root: THREE.Quaternion): THREE.Vector3 {
  return new THREE.Vector3(v[0] * SIGN[side], v[1], v[2]).normalize().applyQuaternion(root);
}

function mix(a: THREE.Vector3, b: THREE.Vector3, w: number): THREE.Vector3 {
  return a.clone().lerp(b, w).normalize();
}

export interface Solved { tip: THREE.Vector3 | null; hand: THREE.Vector3 | null }

/** Pose one arm: rest, then each program over it by its weight; an aimed
 * program solves the shoulder-elbow-fingertip chain onto its target (world). */
export function poseArm(vrm: VRM, side: Side, programs: ArmProgram[], root: THREE.Quaternion,
                        aimWorld: (stage: [number, number]) => THREE.Vector3, bodyLean: number): Solved {
  const L = side === "left" ? "left" : "right";
  const upper = bone(vrm, `${L}UpperArm` as VRMHumanBoneName)!;
  const lower = bone(vrm, `${L}LowerArm` as VRMHumanBoneName)!;
  const hand = bone(vrm, `${L}Hand` as VRMHumanBoneName)!;
  const rest = new THREE.Vector3(SIGN[side], 0, 0);
  let up = toWorld(SHAPES.rest.upper, side, root);
  let fo = toWorld(SHAPES.rest.fore, side, root);
  let palm = toWorld(SHAPES.rest.palm, side, root);
  let fingers = [...SHAPES.rest.fingers];
  let thumb = SHAPES.rest.thumb;
  let solved: Solved = { tip: null, hand: null };
  for (const p of programs) {
    let pu = toWorld(p.shape.upper, side, root);
    let pf = toWorld(p.shape.fore, side, root);
    const pp = toWorld(p.shape.palm, side, root);
    if (p.beat) pf = pf.clone().add(new THREE.Vector3(0, -0.22 * p.beat, 0)).normalize();
    if (p.aim) {
      const ik = solveAim(vrm, side, aimWorld(p.aim.stage), root);
      if (ik) { pu = ik.upper; pf = ik.fore; }
    }
    up = mix(up, pu, p.w);
    fo = mix(fo, pf, p.w);
    palm = mix(palm, pp, p.w);
    fingers = fingers.map((f, i) => lerp(f, p.shape.fingers[i], p.w));
    thumb = lerp(thumb, p.shape.thumb, p.w);
  }
  void bodyLean;
  const sh = bone(vrm, `${L}Shoulder` as VRMHumanBoneName);
  const rise = programs.reduce((r, p) => lerp(r, p.shape.shoulder ?? 0, p.w), 0);
  if (sh) { sh.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), SIGN[side] * 0.22 * rise); sh.updateWorldMatrix(false, true); }
  aimBone(upper, rest, up, null);
  aimBone(lower, rest, fo, null);
  // the palm turns at the wrist: a roll about the forearm, which the model's
  // own twist constraints spread along the forearm (no collapsing sleeve)
  hand.quaternion.setFromAxisAngle(rest, rollTo(lower, fo, palm));
  hand.updateWorldMatrix(false, true);
  curlFingers(vrm, side, fingers, thumb);
  // a held point: turn the forearm about the elbow until the line from the
  // elbow through the fingertip runs through the target (twice: converges)
  const pointing = programs.filter((p) => p.aim && p.w > 0.98).pop();
  if (pointing?.aim) {
    const target = aimWorld(pointing.aim.stage);
    for (let i = 0; i < 3; i++) {
      const tipN = bone(vrm, `${L}IndexDistal` as VRMHumanBoneName);
      if (!tipN) break;
      const elbow = lower.getWorldPosition(new THREE.Vector3());
      const tipP = tipN.getWorldPosition(new THREE.Vector3());
      const fix = new THREE.Quaternion().setFromUnitVectors(tipP.sub(elbow).normalize(), target.clone().sub(elbow).normalize());
      const parent = worldQ(lower.parent!);
      const world = worldQ(lower);
      lower.quaternion.copy(parent.invert().multiply(fix.multiply(world)));
      vrm.humanoid.normalizedHumanBonesRoot.updateMatrixWorld(true);
    }
  }
  const tipNode = bone(vrm, `${L}IndexDistal` as VRMHumanBoneName);
  if (tipNode) {
    const handPos = hand.getWorldPosition(new THREE.Vector3());
    const d = tipNode.getWorldPosition(new THREE.Vector3());
    const mid = bone(vrm, `${L}IndexIntermediate` as VRMHumanBoneName)!.getWorldPosition(new THREE.Vector3());
    solved = { tip: d.clone().add(d.clone().sub(mid).multiplyScalar(0.9)), hand: handPos };
  }
  return solved;
}

const FINGERS = ["Index", "Middle", "Ring", "Little"] as const;

export const TUNE = { curlSign: -1, thumbA: 0.35, thumbB: -0.45, thumbC: 0.7, thumbD: 0.8 };

function curlFingers(vrm: VRM, side: Side, curl: number[], thumb: number) {
  const L = side === "left" ? "left" : "right";
  const s = SIGN[side] * -TUNE.curlSign;
  FINGERS.forEach((f, i) => {
    const c = clamp(curl[i]);
    const angles = [c * 1.35, c * 1.6, c * 1.1];       // proximal, intermediate, distal (radians)
    ["Proximal", "Intermediate", "Distal"].forEach((j, k) => {
      const n = bone(vrm, `${L}${f}${j}` as VRMHumanBoneName);
      if (n) n.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), -s * angles[k]);
    });
  });
  // the thumb folds across the palm
  const tc = clamp(thumb);
  const meta = bone(vrm, `${L}ThumbMetacarpal` as VRMHumanBoneName);
  const prox = bone(vrm, `${L}ThumbProximal` as VRMHumanBoneName);
  const dist = bone(vrm, `${L}ThumbDistal` as VRMHumanBoneName);
  const ts = SIGN[side];
  if (meta) meta.quaternion.setFromEuler(new THREE.Euler(0, ts * TUNE.thumbA * tc, ts * TUNE.thumbB * tc));
  if (prox) prox.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), ts * TUNE.thumbC * tc);
  if (dist) dist.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), ts * TUNE.thumbD * tc);
  vrm.humanoid.normalizedHumanBonesRoot.updateMatrixWorld(true);
}

/** Two-bone aim: the shoulder-elbow-fingertip chain bent at the elbow (never
 * straight), the fingertip ON the target when it is in reach, else the
 * forearm pointing straight at it. */
function solveAim(vrm: VRM, side: Side, target: THREE.Vector3, root: THREE.Quaternion) {
  const L = side === "left" ? "left" : "right";
  const up = bone(vrm, `${L}UpperArm` as VRMHumanBoneName);
  const lo = bone(vrm, `${L}LowerArm` as VRMHumanBoneName);
  const ha = bone(vrm, `${L}Hand` as VRMHumanBoneName);
  const ix = bone(vrm, `${L}IndexDistal` as VRMHumanBoneName);
  if (!up || !lo || !ha || !ix) return null;
  const len = armLengths(vrm, side);
  const S = up.getWorldPosition(new THREE.Vector3());
  const toT = target.clone().sub(S);
  const dist = toT.length();
  const u = toT.clone().normalize();
  const reach = len.upper + len.fore;
  // never a straight arm: the chain is solved at most 86 % of its reach, so the
  // elbow always bends, down and a little back from the shoulder-target line
  const d = clamp(dist, Math.abs(len.upper - len.fore) + 0.02, reach * 0.86);
  const pole = new THREE.Vector3(0, -1, -0.25).applyQuaternion(root);
  const w = pole.sub(u.clone().multiplyScalar(pole.dot(u))).normalize();
  const cosA = clamp((len.upper ** 2 + d * d - len.fore ** 2) / (2 * len.upper * d), -1, 1);
  const a = Math.acos(cosA);
  const elbowDir = u.clone().multiplyScalar(Math.cos(a)).add(w.clone().multiplyScalar(Math.sin(a)));
  const E = S.clone().add(elbowDir.clone().multiplyScalar(len.upper));
  const fore = target.clone().sub(E).normalize();
  return { upper: elbowDir, fore };
}

const LENGTHS = new WeakMap<VRM, Record<Side, { upper: number; fore: number }>>();
/** Shoulder to elbow, and elbow to the index fingertip with the wrist and finger straight. */
function armLengths(vrm: VRM, side: Side): { upper: number; fore: number } {
  let m = LENGTHS.get(vrm);
  if (!m) {
    const h = vrm.humanoid;
    const rest = (n: VRMHumanBoneName) => {
      const node = h.getRawBoneNode(n) ?? h.getNormalizedBoneNode(n)!;
      return node.getWorldPosition(new THREE.Vector3());
    };
    const one = (L: "left" | "right") => {
      const sh = rest(`${L}UpperArm` as VRMHumanBoneName), el = rest(`${L}LowerArm` as VRMHumanBoneName);
      const wr = rest(`${L}Hand` as VRMHumanBoneName), tip = rest(`${L}IndexDistal` as VRMHumanBoneName);
      return { upper: sh.distanceTo(el), fore: el.distanceTo(wr) + wr.distanceTo(tip) * 1.18 };
    };
    m = { left: one("left"), right: one("right") };
    LENGTHS.set(vrm, m);
  }
  return m[side];
}

/** Record the rest lengths before any pose is applied (call once after load). */
export function measureRest(vrm: VRM) {
  vrm.scene.updateMatrixWorld(true);
  armLengths(vrm, "left");
}

// ------------------------------------------------------------------ face

/** The VRM expression weights for an expression cue: quiet and professional. */
export const FACE: Record<string, Partial<Record<string, number>>> = {
  // professional: relaxed and attentive; "happy" is a hint of a smile, never a laugh
  neutral: { relaxed: 0.25 }, listening: { relaxed: 0.35 }, happy: { relaxed: 0.25, happy: 0.15 },
  grin: { relaxed: 0.2, happy: 0.22 }, proud: { relaxed: 0.2, happy: 0.2 }, excited: { relaxed: 0.2, happy: 0.22 },
  laugh: { relaxed: 0.2, happy: 0.22 },
  surprised: { surprised: 0.55 }, shocked: { surprised: 0.55 }, confused: { sad: 0.3 }, worried: { sad: 0.3 },
  thinking: { relaxed: 0.2, sad: 0.08 }, skeptical: { sad: 0.15 }, sad: { sad: 0.3 },
};

export function faceAt(track: CharacterTrack, t: number): Record<string, number> {
  const cues = (track.cues as unknown as Cue[]).filter((c) => c.kind === "expression").sort((a, b) => a.t - b.t);
  let cur = FACE.listening, prev = FACE.listening, since = 99;
  for (const c of cues) {
    if (c.t > t) break;
    prev = cur;
    cur = FACE[c.name ?? ""] ?? FACE.listening;
    since = t - c.t;
  }
  const k = ease.inOutCubic(clamp(since / 0.35));
  const out: Record<string, number> = {};
  for (const n of ["relaxed", "happy", "surprised", "sad"]) out[n] = lerp(prev[n] ?? 0, cur[n] ?? 0, k);
  return out;
}

/** VRM visemes from the 2D mouth channels, opened by the voice's loudness. */
export function visemes(pose: Pose, env: number, speaking: boolean): Record<string, number> {
  if (!speaking) return { aa: 0, ee: 0, ih: 0, oh: 0, ou: 0 };
  const p = pose as unknown as Record<string, number>;
  const open = clamp(p.mouthOpen * (0.5 + 0.9 * env));
  const wide = clamp((p.mouthWide - 0.35) / 0.5);
  const pucker = clamp(p.pucker);
  return {
    aa: clamp(open * (1 - pucker) * (1 - 0.55 * wide)),
    ee: clamp(open * 0.75 * wide),
    ih: clamp(0.35 * wide * (1 - open)),
    oh: clamp(open * pucker * 1.1),
    ou: clamp(pucker * (1 - open) * 0.8),
  };
}
