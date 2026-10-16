// A still 3D portrait of one avatar (assets/avatars/<name>.vrm): head and
// shoulders, turned a little, smiling — what the Characters step shows for
// each 3D avatar a speaker can wear. It is drawn once (no animation loop) on
// its own small canvas, and the student is recoloured exactly as the reel
// draws it (looks.ts) while it is the same file as the mentor.

import { useEffect, useId, useRef, useState } from "react";
import * as THREE from "three";
import { fingerprintOf, loadVrm } from "./load";
import { STUDENT_LOOK, applyLook } from "./looks";

export function VrmPortrait({ name, width = 150, height = 170, background = "#1B2140" }: {
  name: string; width?: number; height?: number; background?: string;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const slot = useId();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let gone = false;
    const renderer = new THREE.WebGLRenderer({ canvas: canvas.current!, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(width, height, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(-1, 1.6, 2.2);
    scene.add(key, new THREE.AmbientLight(0xffffff, 0.55));
    (async () => {
      const vrm = await loadVrm(name, `portrait:${slot}`);
      if (name !== "mentor") {
        const [mine, mentor] = await Promise.all([fingerprintOf(name), fingerprintOf("mentor").catch(() => "")]);
        if (mine === mentor && !vrm.scene.userData.looked) { applyLook(vrm, STUDENT_LOOK); vrm.scene.userData.looked = true; }
      }
      if (gone) return;
      scene.add(vrm.scene);
      vrm.scene.rotation.y = -0.25;
      // a relaxed pose: arms down, a small smile
      const h = vrm.humanoid;
      h.resetNormalizedPose();
      h.getNormalizedBoneNode("leftUpperArm")?.rotation.set(0, 0, -1.32);
      h.getNormalizedBoneNode("rightUpperArm")?.rotation.set(0, 0, 1.32);
      vrm.expressionManager?.setValue("happy", 0.35);
      h.update();
      vrm.expressionManager?.update();
      vrm.scene.updateMatrixWorld(true);
      // head and shoulders: from the chest to just above the head
      const head = h.getNormalizedBoneNode("head")!.getWorldPosition(new THREE.Vector3());
      const chest = (h.getNormalizedBoneNode("upperChest") ?? h.getNormalizedBoneNode("chest") ?? h.getNormalizedBoneNode("spine"))!
        .getWorldPosition(new THREE.Vector3());
      const top = head.y + 0.2, bottom = chest.y - 0.12;
      const hgt = top - bottom, wid = hgt * (width / height);
      const camera = new THREE.OrthographicCamera(-wid / 2, wid / 2, hgt / 2, -hgt / 2, 0.1, 20);
      camera.position.set(head.x, (top + bottom) / 2, 6);
      camera.lookAt(head.x, (top + bottom) / 2, 0);
      renderer.render(scene, camera);
      setState("ready");
    })().catch(() => { if (!gone) setState("error"); });
    return () => { gone = true; renderer.dispose(); };
  }, [name, width, height, slot]);

  return (
    <div style={{ position: "relative", width, height, borderRadius: 12, overflow: "hidden", background }}>
      <canvas ref={canvas} width={width} height={height} style={{ width, height, display: "block" }} />
      {state !== "ready" && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 12, color: "#9AA0C0" }}>{state === "error" ? "could not load" : "loading…"}</div>
      )}
    </div>
  );
}
