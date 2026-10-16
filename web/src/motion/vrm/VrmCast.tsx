// The 3D avatars (plan.avatars = "vrm"): each character a VRM model drawn
// waist-up on its own transparent canvas, in the board staging — the mentor
// beside the board, the student a little smaller, turned toward the mentor —
// above the board and below the captions (library.json frame.board.vrm keeps
// every canvas above the chat band). Pure in t: the pose comes from
// pose3d.ts, applied and rendered synchronously for the frame being drawn.
// Each canvas reports where its pointing fingertip landed (data-aim-*), which
// shorts/motion_sweep.py collects for the fingertip check.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { VRM } from "@pixiv/three-vrm";
import type { MotionPlan } from "../scene/types";
import type { CharacterTrack } from "../cast/performance";
import { poseOf } from "../cast/performance";
import { PRESENCE_SLIDE, performanceFor } from "../cast/ReelCharacters";
import { toStage } from "../cast/teach";
import { bulbAt } from "../cast/teach";
import { fingerprintOf, loadVrm, track as trackAsset } from "./load";
import { STUDENT_LOOK, applyLook } from "./looks";
import { armPrograms, faceAt, measureRest, poseArm, visemes } from "./pose3d";
import library from "../library.json";
import { clamp, ease, lerp, seg } from "../time";

type Box = { x: number; y: number; w: number; h: number; yaw: number; body_x?: number };
const FRAMES = (library as unknown as { frame: { board: { vrm: Record<string, Box> }; video: { vrm: Record<string, Box> } } }).frame;
const VRM_STAGE = FRAMES.board.vrm;
/** a VIDEO's canvases (library.json frame.video.vrm): the mentor right of the board */
const VRM_VIDEO = FRAMES.video.vrm;

/** Which model a track wears and where it stands. */
function slotOf(track: CharacterTrack, n: number, video = false): { file: string; box: Box; boardSide: "left" | "right" } {
  const t = track as unknown as { vrm?: string };
  const boxes = video ? VRM_VIDEO : VRM_STAGE;
  if (n === 1 || track.side !== "left") return { file: t.vrm ?? "mentor", box: boxes.explainer, boardSide: "right" };
  return { file: t.vrm ?? "student", box: boxes.asker, boardSide: "left" };
}

/** Where a point of the reel layout is drawn on the stage at t: a reel's
 * board (cast/teach.ts toStage); a video's shot view (shorts/motion_video.py),
 * the shot playing at t. */
function stageOf(plan: MotionPlan, t: number): (full: boolean | string, x: number, y: number) => [number, number] {
  if (plan.format !== "video") return toStage;
  let k = 0;
  for (let i = 0; i < plan.shots.length; i++) if (t >= plan.shots[i].start) k = i;
  const v = plan.shots[k].view;
  if (!v) return toStage;
  return (_full, x, y) => [v.dst[0] + (x - v.src[0]) * v.s, v.dst[1] + (y - v.src[1]) * v.s];
}

/** `presence`: how far on screen the cast is (0 gone: nothing is drawn, but
 * the models stay loaded). `slide`: it also slides out toward its own edge
 * as it fades (rev 4 plans). */
export function VrmCast({ plan, t, presence = 1, slide = false }: { plan: MotionPlan; t: number; presence?: number; slide?: boolean }) {
  if (!plan.characters?.length) return null;
  const n = plan.characters.length;
  const slots = plan.characters.map((tr) => slotOf(tr, n, plan.format === "video"));
  return (
    <div data-part="characters" style={{ position: "absolute", inset: 0, opacity: presence, pointerEvents: "none",
                                         visibility: presence > 0 ? "visible" : "hidden" }}>
      {plan.characters.map((track, i) => (
        <VrmView key={`${track.side}:${track.role ?? ""}`} plan={plan} track={track} t={t} slot={slots[i]}
                 partner={n > 1 ? slots[1 - i].box : null} shown={presence > 0}
                 dx={slide ? (1 - presence) * PRESENCE_SLIDE * (slots[i].boardSide === "right" ? 1 : -1) : 0} />
      ))}
    </div>
  );
}

interface View {
  renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.OrthographicCamera; vrm: VRM;
  look: THREE.Object3D; headY: number; hair: HairBone[];
}

interface HairBone { node: THREE.Object3D; rest: THREE.Quaternion; depth: number; phase: number }

/** The hair's bones (VRoid names them J_Sec_Hair…): their rest pose, how deep
 * each is in its strand, and a phase per strand. */
function hairChains(vrm: VRM): HairBone[] {
  const out: HairBone[] = [];
  let strand = 0;
  vrm.scene.traverse((o) => {
    if (!/hair/i.test(o.name) || !(o as THREE.Bone).isBone) return;
    const parentIsHair = o.parent && /hair/i.test(o.parent.name) && (o.parent as THREE.Bone).isBone;
    if (!parentIsHair) strand += 1;
    let depth = 0;
    for (let p = o.parent; p && /hair/i.test(p.name); p = p.parent) depth += 1;
    out.push({ node: o, rest: o.quaternion.clone(), depth, phase: strand * 0.7 });
  });
  return out;
}

/** A gentle sway of the hair from the frame's time alone (no physics: the
 * same frame always draws the same hair). Deeper bones in a strand sway more. */
function swayHair(hair: HairBone[], t: number, motion: number) {
  for (const h of hair) {
    const a = (0.018 + 0.012 * motion) * (1 + h.depth * 0.6);
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(
      a * 0.5 * Math.sin(t * 1.3 + h.phase), 0, a * Math.sin(t * 0.9 + h.phase * 1.3)));
    h.node.quaternion.copy(h.rest).multiply(q);
  }
}

function VrmView({ plan, track, t, slot, partner, shown = true, dx = 0 }: {
  plan: MotionPlan; track: CharacterTrack; t: number; slot: ReturnType<typeof slotOf>; partner: Box | null;
  shown?: boolean; dx?: number;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const view = useRef<View | null>(null);
  const [ready, setReady] = useState(false);
  const [aim, setAim] = useState<{ target: [number, number]; tip: [number, number]; miss: number } | null>(null);
  const { box } = slot;

  useEffect(() => {
    let gone = false;
    const renderer = new THREE.WebGLRenderer({ canvas: canvas.current!, alpha: true, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.setSize(box.w, box.h, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(-1, 1.6, 2.2);
    scene.add(key, new THREE.AmbientLight(0xffffff, 0.5));
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 20);
    // the student, while it wears the very same file as the mentor (the
    // placeholder), is recoloured and drawn a little smaller (looks.ts)
    const prepared = loadVrm(slot.file, `${track.side}:${track.role ?? ""}`).then(async (vrm) => {
      // whoever wears the student file (the asker, or a narrator who picked it)
      if (slot.file !== "mentor") {
        const [mine, mentor] = await Promise.all([fingerprintOf(slot.file), fingerprintOf("mentor").catch(() => "")]);
        if (mine === mentor && !vrm.scene.userData.looked) { applyLook(vrm, STUDENT_LOOK); vrm.scene.userData.looked = true; }
      }
      return vrm;
    });
    trackAsset(prepared).then((vrm) => {
      if (gone) return;
      scene.add(vrm.scene);
      measureRest(vrm);
      // waist-up: from just below the hips to above the head, centred on the body
      const hips = vrm.humanoid.getNormalizedBoneNode("hips")!.getWorldPosition(new THREE.Vector3());
      const head = vrm.humanoid.getNormalizedBoneNode("head")!.getWorldPosition(new THREE.Vector3());
      // framed as if at full size, so a smaller look really draws smaller
      const k = vrm.scene.scale.y || 1;
      const top = head.y / k + 0.24, bottom = hips.y / k - 0.02;
      const hgt = top - bottom, wid = hgt * (box.w / box.h);
      camera.left = -wid / 2; camera.right = wid / 2; camera.top = hgt / 2; camera.bottom = -hgt / 2;
      // the body stands at body_x across the canvas (the rest of it is room for a gesture)
      const cx = hips.x - (( box.body_x ?? 0.5) - 0.5) * wid;
      camera.position.set(cx, (top + bottom) / 2, 6);
      camera.lookAt(cx, (top + bottom) / 2, 0);
      camera.updateProjectionMatrix();
      vrm.scene.rotation.y = box.yaw;
      const look = new THREE.Object3D();
      scene.add(look);
      if (vrm.lookAt) vrm.lookAt.target = look;
      view.current = { renderer, scene, camera, vrm, look, headY: head.y, hair: hairChains(vrm) };
      setReady(true);
    });
    return () => { gone = true; renderer.dispose(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const v = view.current;
    if (!v || !ready) return;
    if (!shown) { if (aim) setAim(null); return; }
    const out = drawAt(v, plan, track, t, slot, partner);
    const prev = aim;
    if ((out && (!prev || out.tip[0] !== prev.tip[0])) || (!out && prev)) setAim(out);
  });

  return <>
    <canvas ref={canvas} data-character={track.preset} data-side={track.side} data-vrm={slot.file}
            data-body-x={box.body_x ?? 0.5}
            data-aim-target={aim ? aim.target.map(Math.round).join(",") : undefined}
            data-aim-tip={aim ? aim.tip.map(Math.round).join(",") : undefined}
            data-aim-miss={aim ? Math.round(aim.miss) : undefined}
            width={box.w} height={box.h}
            style={{ position: "absolute", left: box.x + dx, top: box.y, width: box.w, height: box.h,
                     WebkitMaskImage: "linear-gradient(to bottom, #000 86%, transparent 100%)",
                     maskImage: "linear-gradient(to bottom, #000 86%, transparent 100%)" }} />
    {shown && <Bulb track={track} t={t} box={box} />}
  </>;
}

/** The "aha" lightbulb over the character's head. */
function Bulb({ track, t, box }: { track: CharacterTrack; t: number; box: Box }) {
  const c = (track.cues as unknown as { t: number; kind: string }[]).filter((q) => q.kind === "aha" && q.t <= t).pop();
  const b = bulbAt(c ? t - c.t : 0);
  if (b.opacity <= 0) return null;
  return (
    <svg data-part="aha" width={110} height={140} viewBox="0 0 60 75"
         style={{ position: "absolute", left: box.x + box.w * (box.body_x ?? 0.5) - 55, top: box.y - 70, opacity: b.opacity,
                  transform: `scale(${b.scale})`, transformOrigin: "50% 100%", overflow: "visible" }}>
      {[0, 1, 2, 3, 4].map((k) => {
        const a = (-150 + k * 30) * Math.PI / 180;
        return <line key={k} x1={30 + Math.cos(a) * 24} y1={26 + Math.sin(a) * 24} x2={30 + Math.cos(a) * (31 + 3 * b.glow)}
                     y2={26 + Math.sin(a) * (31 + 3 * b.glow)} stroke="#FFD43B" strokeWidth={3.5} strokeLinecap="round" />;
      })}
      <circle cx={30} cy={26} r={17} fill="#FFE066" stroke="#F2B705" strokeWidth={2.5} />
      <path d="M24 42 h12 v6 h-12 z M25 50 h10" stroke="#5B6178" strokeWidth={3} fill="#9AA0B8" strokeLinecap="round" />
    </svg>
  );
}

/** Stage pixels -> world, on this view's camera, at depth z. */
function stageToWorld(v: View, box: Box, px: number, py: number, z: number): THREE.Vector3 {
  const c = v.camera;
  const x = c.position.x + c.left + ((px - box.x) / box.w) * (c.right - c.left);
  const y = c.position.y + c.top - ((py - box.y) / box.h) * (c.top - c.bottom);
  return new THREE.Vector3(x, y, z);
}

function worldToStage(v: View, box: Box, p: THREE.Vector3): [number, number] {
  const c = v.camera;
  return [box.x + ((p.x - c.position.x - c.left) / (c.right - c.left)) * box.w,
          box.y + ((c.position.y + c.top - p.y) / (c.top - c.bottom)) * box.h];
}

/** Pose and draw one frame; returns where the pointing fingertip landed. */
function drawAt(v: View, plan: MotionPlan, track: CharacterTrack, t: number, slot: ReturnType<typeof slotOf>, partner: Box | null) {
  const { vrm, box } = { vrm: v.vrm, box: slot.box };
  const pose = poseOf(performanceFor(plan, track), t) as unknown as Record<string, number>;
  const h = vrm.humanoid;
  h.resetNormalizedPose();
  const root = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, box.yaw, 0));
  const set = (name: Parameters<typeof h.getNormalizedBoneNode>[0], x: number, y: number, z: number) => {
    const n = h.getNormalizedBoneNode(name);
    if (n) n.quaternion.setFromEuler(new THREE.Euler(x, y, z));
  };
  // breathing and sway (the life layer), the lean toward what is shown
  const breathe = pose.breathe ?? 0;
  set("spine", -0.02 * breathe, 0, (pose.lean ?? 0) * Math.PI / 180 * 0.35);
  set("chest", -0.03 * breathe, 0, 0);
  // the speaker's words: when it is talking, and the beats of its gestures
  const role = track.role ?? null;
  const caps = plan.shots.flatMap((s) => s.captions).filter((c) => (c.speaker ?? null) === role);
  const speaking = caps.some((c) => t >= c.start - 0.05 && t <= c.end + 0.05);
  const words = caps.flatMap((c) => c.words);
  // gaze: the element being explained, the other speaker, else the camera
  const head = h.getNormalizedBoneNode("head")!;
  vrm.scene.updateMatrixWorld(true);
  const headPos = head.getWorldPosition(new THREE.Vector3());
  let target = new THREE.Vector3(v.camera.position.x, v.headY, 6);
  let gw = 0;
  let gazeTarget: THREE.Vector3 | null = null;
  for (const c of track.cues as unknown as { t: number; kind: string; until?: number | null; rect?: number[] | null; target?: string | null; full?: boolean | string }[]) {
    if (c.kind !== "gaze" || t < c.t - 0.05 || t > (c.until ?? c.t) + 0.4) continue;
    const w = ease.inOutCubic(seg(t, c.t, 0.25)) * (1 - ease.inOutCubic(seg(t, c.until ?? c.t + 1, 0.3)));
    if (w <= 0) continue;
    let p: [number, number] | null = null;
    if (c.target === "partner" || !c.rect) p = partner ? [partner.x + partner.w * (partner.body_x ?? 0.5), partner.y + partner.h * 0.22] : null;
    else p = stageOf(plan, c.t)(c.full ?? false, c.rect[0] + c.rect[2] / 2, c.rect[1] + c.rect[3] / 2);
    if (!p) continue;
    gazeTarget = stageToWorld(v, box, p[0], p[1], headPos.z + 0.6);
    gw = Math.max(gw, w);
  }
  if (gazeTarget) target = target.clone().lerp(gazeTarget, gw);
  // the head turns part of the way to what the eyes look at, plus nods, shakes and tilts
  const dir = target.clone().sub(headPos).normalize();
  const local = dir.clone().applyQuaternion(root.clone().invert());
  const yaw = clamp(Math.atan2(local.x, local.z) * 0.45, -0.55, 0.55) + (pose.headTurn ?? 0) * 0.35 * (1 - gw);
  const pitch = clamp(-Math.asin(clamp(local.y)) * 0.4, -0.3, 0.3) + (pose.headNod ?? 0) * 0.35;
  set("neck", pitch * 0.4, yaw * 0.4, 0);
  set("head", pitch * 0.6, yaw * 0.6, -(pose.headTilt ?? 0) * Math.PI / 180);
  v.look.position.copy(target);
  // arms
  // the hand never covers the words it points at: a tall target (a card) is
  // pointed at low on it, under its label; a short one (a pill, a token) from
  // just under its bottom edge
  const map = stageOf(plan, t);
  const toStageRect = (rect: number[], full: boolean | string) =>
    map(full, rect[0] + rect[2] / 2, rect[3] > 150 ? rect[1] + rect[3] * 0.82 : rect[1] + rect[3] + 8);
  const programs = armPrograms(track, t, words, slot.boardSide, toStageRect);
  const aimWorld = (st: [number, number]) => stageToWorld(v, box, st[0], st[1], headPos.z + 0.18);
  let report: { target: [number, number]; tip: [number, number]; miss: number } | null = null;
  for (const side of ["left", "right"] as const) {
    const solved = poseArm(vrm, side, programs[side], root, aimWorld, pose.lean ?? 0);
    const aimed = programs[side].filter((p) => p.aim && p.w > 0.9).pop();
    if (aimed?.aim && solved.tip && solved.hand) {
      const tip = worldToStage(v, box, solved.tip);
      const hand = worldToStage(v, box, solved.hand);
      const tg = aimed.aim.stage;
      // how far the target is from the pointing ray (hand -> fingertip, extended)
      const dx = tip[0] - hand[0], dy = tip[1] - hand[1];
      const L = Math.hypot(dx, dy) || 1;
      const along = ((tg[0] - hand[0]) * dx + (tg[1] - hand[1]) * dy) / L;
      const miss = along > 0 ? Math.abs((tg[0] - hand[0]) * dy - (tg[1] - hand[1]) * dx) / L : Math.hypot(tg[0] - tip[0], tg[1] - tip[1]);
      report = { target: tg, tip, miss };
    }
  }
  // face: the director's expression, the mouth on the voice, the blinks
  const face = faceAt(track, t);
  const env = (track as unknown as { env?: { t0: number; fps: number; v: number[] } | null }).env;
  let e = 0;
  if (env && env.v.length) {
    const i = (t - env.t0) * env.fps, k = Math.floor(i);
    e = k < 0 || k >= env.v.length - 1 ? 0 : lerp(env.v[k], env.v[k + 1], i - k);
  }
  const mouth = visemes(pose as never, e, speaking);
  const em = vrm.expressionManager;
  if (em) {
    for (const [k, w] of Object.entries(face)) em.setValue(k, w);
    for (const [k, w] of Object.entries(mouth)) em.setValue(k, w);
    em.setValue("blinkLeft", clamp(pose.blinkL ?? 0));
    em.setValue("blinkRight", clamp(pose.blinkR ?? 0));
  }
  h.update();
  // the hair sways a little more while the head moves (a nod, a turn)
  swayHair(v.hair, t, clamp(Math.abs(pose.headNod ?? 0) * 3 + Math.abs(pose.headTurn ?? 0)));
  vrm.nodeConstraintManager?.update();
  vrm.lookAt?.update(0);
  em?.update();
  v.renderer.render(v.scene, v.camera);
  return report;
}
