// Loading the 3D avatars (VRM 1.0, @pixiv/three-vrm). A model is fetched
// from /api/motion/avatars/<name> (assets/avatars/<name>.vrm on the server,
// read on every request, so replacing the file needs no code change) and
// kept per name. The capture renderer waits for every model a frame needs
// before it photographs it: window.__motionAssets() resolves when all
// pending loads have finished.

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils, type VRM } from "@pixiv/three-vrm";

const CACHE = new Map<string, Promise<VRM>>();
const PENDING = new Set<Promise<unknown>>();

declare global {
  interface Window { __motionAssets?: () => Promise<void> }
}
if (typeof window !== "undefined") {
  window.__motionAssets = async () => { while (PENDING.size) await Promise.allSettled([...PENDING]); };
}

/** A fresh VRM instance per (name, slot): two characters wearing the same
 * file are two separate models. */
export function loadVrm(name: string, slot: string): Promise<VRM> {
  const key = `${name}:${slot}`;
  let p = CACHE.get(key);
  if (!p) {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    p = loader.loadAsync(`/api/motion/avatars/${encodeURIComponent(name)}`).then((gltf) => {
      const vrm = gltf.userData.vrm as VRM;
      VRMUtils.removeUnnecessaryVertices(gltf.scene);
      VRMUtils.combineSkeletons(gltf.scene);
      vrm.scene.traverse((o) => { o.frustumCulled = false; });
      return vrm;
    });
    const tracked = p.finally(() => PENDING.delete(tracked));
    PENDING.add(tracked);
    CACHE.set(key, p);
  }
  return p;
}

export { THREE };
