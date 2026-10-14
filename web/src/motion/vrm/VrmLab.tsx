// #motion-vrm-lab — every 3D gesture side by side on one model, posed by the
// same code the reel uses (pose3d.ts), for checking the hands and arms.
//   #motion-vrm-lab?avatar=mentor&close=1   close-up on the hands
//   ...&curl=-1&ta=..&tb=..&tc=..&td=..      try other finger axes (tuning only)
// A dev page, like #motion-gallery; window.__labReady is true when drawn.

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { loadVrm } from "./load";
import { SHAPES, TUNE, measureRest, poseArm, type ArmProgram } from "./pose3d";

const TILE_W = 360, TILE_H = 520;
const POSES: { name: string; left: ArmProgram[]; right: ArmProgram[]; aim?: [number, number, number] }[] = [
  { name: "rest", left: [], right: [] },
  { name: "explain", left: [{ shape: SHAPES.explain, w: 1, beat: 0 }], right: [{ shape: SHAPES.explain, w: 1, beat: 0 }] },
  { name: "present", left: [], right: [{ shape: SHAPES.present, w: 1, beat: 0 }] },
  { name: "shrug", left: [{ shape: SHAPES.shrug, w: 1, beat: 0 }], right: [{ shape: SHAPES.shrug, w: 1, beat: 0 }] },
  { name: "thumbs up", left: [{ shape: SHAPES.thumbsUp, w: 1, beat: 0 }], right: [] },
  { name: "count 1", left: [], right: [{ shape: { ...SHAPES.count, fingers: [0, 1, 1, 1] }, w: 1, beat: 0 }] },
  { name: "count 2", left: [], right: [{ shape: { ...SHAPES.count, fingers: [0, 0, 1, 1] }, w: 1, beat: 0 }] },
  { name: "count 3", left: [], right: [{ shape: { ...SHAPES.count, fingers: [0, 0, 0, 1] }, w: 1, beat: 0 }] },
  { name: "point near", left: [], right: [{ shape: SHAPES.point, w: 1, beat: 0, aim: { stage: [0, 0] } }], aim: [-0.45, 0.05, 0.25] },
  { name: "point far up", left: [], right: [{ shape: SHAPES.point, w: 1, beat: 0, aim: { stage: [0, 0] } }], aim: [-1.6, 0.7, 0.2] },
];

export function VrmLab() {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(location.hash.split("?")[1] ?? "");
    TUNE.curlSign = Number(q.get("curl") ?? TUNE.curlSign);
    for (const [k, key] of [["ta", "thumbA"], ["tb", "thumbB"], ["tc", "thumbC"], ["td", "thumbD"]] as const)
      if (q.get(k) !== null) (TUNE as Record<string, number>)[key] = Number(q.get(k));
    const close = q.get("close") === "1";
    const cols = 5, rows = Math.ceil(POSES.length / cols);
    const canvas = ref.current!;
    canvas.width = cols * TILE_W; canvas.height = rows * TILE_H;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setScissorTest(true);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#1F3A34");
    const key = new THREE.DirectionalLight(0xffffff, Number(q.get("key") ?? 1.2));
    key.position.set(-1, 1.6, 2.2);
    scene.add(key, new THREE.AmbientLight(0xffffff, Number(q.get("amb") ?? 0.5)));
    loadVrm(q.get("avatar") ?? "mentor", "lab").then((vrm) => {
      scene.add(vrm.scene);
      measureRest(vrm);
      const hips = vrm.humanoid.getNormalizedBoneNode("hips")!.getWorldPosition(new THREE.Vector3());
      const head = vrm.humanoid.getNormalizedBoneNode("head")!.getWorldPosition(new THREE.Vector3());
      const top = close ? head.y - 0.1 : head.y + 0.24, bottom = close ? hips.y - 0.15 : hips.y - 0.02;
      const hgt = top - bottom, wid = hgt * TILE_W / TILE_H;
      const cam = new THREE.OrthographicCamera(-wid / 2, wid / 2, hgt / 2, -hgt / 2, 0.1, 20);
      cam.position.set(hips.x, (top + bottom) / 2, 6);
      // the pointing poses reach out: those tiles look wider, centred to the side
      const wide = new THREE.OrthographicCamera(-wid, wid, hgt, -hgt, 0.1, 20);
      wide.position.set(hips.x - wid * 0.6, (top + bottom) / 2 + hgt * 0.2, 6);
      const root = new THREE.Quaternion();
      POSES.forEach((pz, i) => {
        vrm.humanoid.resetNormalizedPose();
        vrm.scene.updateMatrixWorld(true);
        const sh = vrm.humanoid.getNormalizedBoneNode("rightUpperArm")!.getWorldPosition(new THREE.Vector3());
        const target = pz.aim ? sh.clone().add(new THREE.Vector3(...pz.aim)) : null;
        const aimWorld = () => target ?? new THREE.Vector3();
        poseArm(vrm, "left", pz.left, root, aimWorld, 0);
        poseArm(vrm, "right", pz.right, root, aimWorld, 0);
        vrm.expressionManager?.setValue("relaxed", 0.3);
        vrm.humanoid.update();
        vrm.nodeConstraintManager?.update();
        vrm.expressionManager?.update();
        const x = (i % cols) * TILE_W, y = (rows - 1 - Math.floor(i / cols)) * TILE_H;
        renderer.setViewport(x, y, TILE_W, TILE_H);
        renderer.setScissor(x, y, TILE_W, TILE_H);
        renderer.render(scene, pz.name.startsWith("point") ? wide : cam);
      });
      (window as unknown as { __labReady?: boolean }).__labReady = true;
    });
  }, []);
  return (
    <div style={{ background: "#0E1224", minHeight: "100vh", color: "#E9EBF7", fontFamily: "system-ui", padding: 0 }}>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(5, ${TILE_W}px)`, position: "absolute", top: 0, left: 0, zIndex: 1 }}>
        {POSES.map((p) => <div key={p.name} style={{ height: TILE_H, padding: 8, fontSize: 22, fontWeight: 700 }}>{p.name}</div>)}
      </div>
      <canvas ref={ref} style={{ display: "block" }} />
    </div>
  );
}
