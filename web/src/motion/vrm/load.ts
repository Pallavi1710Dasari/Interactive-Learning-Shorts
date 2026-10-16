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
    p = bytesOf(name)
      .then((buf) => loader.parseAsync(buf.slice(0), "").then((gltf) => {
        const vrm = gltf.userData.vrm as VRM;
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.combineSkeletons(gltf.scene);
        vrm.scene.traverse((o) => { o.frustumCulled = false; });
        // which file this is, by content: the student is recoloured only while it
        // is the very same file as the mentor (looks.ts)
        vrm.scene.userData.fingerprint = fingerprint(buf);
        return vrm;
      }));
    const tracked = p.finally(() => PENDING.delete(tracked));
    PENDING.add(tracked);
    CACHE.set(key, p);
  }
  return p;
}

const BYTES = new Map<string, Promise<ArrayBuffer>>();
/** A model file's bytes, fetched once however many characters wear it. */
function bytesOf(name: string): Promise<ArrayBuffer> {
  let b = BYTES.get(name);
  if (!b) {
    b = fetch(`/api/motion/avatars/${encodeURIComponent(name)}`)
      .then((r) => { if (!r.ok) throw new Error(`avatar ${name}: ${r.status}`); return r.arrayBuffer(); });
    BYTES.set(name, b);
    track(b);
  }
  return b;
}

/** A model file's content fingerprint. */
export function fingerprintOf(name: string): Promise<string> {
  return bytesOf(name).then(fingerprint);
}

/** The capture waits for this too (a model being recoloured, say). */
export function track<T>(p: Promise<T>): Promise<T> {
  const t = p.finally(() => PENDING.delete(t));
  PENDING.add(t);
  return p;
}

/** A content fingerprint: the length and an FNV-1a hash of every 97th byte. */
export function fingerprint(buf: ArrayBuffer): string {
  const b = new Uint8Array(buf);
  let h = 0x811c9dc5;
  for (let i = 0; i < b.length; i += 97) { h ^= b[i]; h = Math.imul(h, 0x01000193) >>> 0; }
  return `${b.length}:${h.toString(16)}`;
}


export { THREE };
