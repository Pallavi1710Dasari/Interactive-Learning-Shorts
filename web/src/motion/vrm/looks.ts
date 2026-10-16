// Telling the mentor and the student apart while both wear the same model
// (the placeholder: both assets/avatars files are pixiv's sample). When
// student.vrm is the very same file as mentor.vrm, the student is recoloured
// through its materials — darker hair, an orange top, denim, a warmer skin,
// darker eyes — and drawn a little smaller. As soon as the two files differ
// (your own VRoid models), nothing is recoloured: each model is drawn as made.
//
// VRoid names its materials by part (Hair_00_HAIR, Tops_01_CLOTH,
// Bottoms_01_CLOTH, Body_00_SKIN, EyeIris_00_EYE), so the tint finds them by
// that name. MToon's colour multiplies its texture, so a tint keeps the
// shading and the drawn detail.

import * as THREE from "three";
import type { VRM } from "@pixiv/three-vrm";

export interface Look { scale: number; tint: { match: RegExp; lit: string; shade?: string }[] }

export const STUDENT_LOOK: Look = {
  scale: 0.93,
  tint: [
    { match: /_HAIR$/i, lit: "#4A3A33", shade: "#2A2020" },
    { match: /^Tops_.*_CLOTH$/i, lit: "#F28C4B", shade: "#C25A28" },
    { match: /^Bottoms_.*_CLOTH$/i, lit: "#5B78A8", shade: "#3A4F78" },
    { match: /^Shoes_.*_CLOTH$/i, lit: "#3A3A44" },
    { match: /_SKIN$/i, lit: "#E9C2A6", shade: "#C98F78" },
    { match: /^EyeIris_/i, lit: "#5A4636" },
  ],
};

/** Recolour a model by its material names, and scale it. */
export function applyLook(vrm: VRM, look: Look): void {
  vrm.scene.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    mesh.material = (Array.isArray(mesh.material) ? mats : mats[0]) as THREE.Material;
    mats.forEach((m, i) => {
      const name = (m as THREE.Material).name.replace(/ \(Outline\)$/, "");
      const t = look.tint.find((x) => x.match.test(name));
      if (!t) return;
      // a copy: the same material is shared with nobody else, but keep the model's own untouched
      const c = (m as THREE.Material).clone() as THREE.Material & { color?: THREE.Color; shadeColorFactor?: THREE.Color };
      c.color?.set(t.lit);
      if (t.shade) c.shadeColorFactor?.set(t.shade);
      if (Array.isArray(mesh.material)) (mesh.material as THREE.Material[])[i] = c; else mesh.material = c;
    });
  });
  vrm.scene.scale.setScalar(look.scale);
}
