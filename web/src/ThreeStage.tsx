import { useEffect, useRef } from "react";
import * as THREE from "three";

/**
 * The living backdrop behind the diagram — a WebGL depth field, not a gradient.
 *
 * WHAT IT IS FOR, AND WHAT IT MUST NOT DO
 * A vertical short is watched on a phone in a scrolling feed, and a flat dark
 * rectangle behind a static diagram reads as a screenshot. Real parallax makes the
 * frame feel like a place the diagram is sitting in, which is what buys the extra
 * second of attention before the viewer swipes.
 *
 * That is the whole brief. It carries no information, so it stays quiet: low
 * opacity, additive blending, nothing crossing the middle of the frame where the
 * labels are. Anything eye-catching enough to compete with the diagram is a bug —
 * the diagram is the thing the viewer is supposed to remember.
 *
 * IT ONLY RUNS WHILE THE REEL IS ON SCREEN
 * Browsers cap live WebGL contexts at around sixteen, and the feed can hold far
 * more shorts than that; the oldest context is silently killed when the cap is
 * passed. So the whole renderer is created on becoming active and disposed on
 * leaving, and the loop is stopped in between rather than left rendering off
 * screen into a battery.
 *
 * It reacts to the narration in two ways, both deliberately subtle:
 *   speaking     the field breathes a little wider while a voice is going
 *   beat change  one very soft pulse, so a new frame arriving is felt as well as
 *                seen. Barely: a loud transition is worse than none, because it
 *                pulls the eye off the diagram exactly when the diagram changed.
 */
export function ThreeStage({ hue, active, speaking, beat }: {
  hue: number;
  active: boolean;
  speaking: boolean;
  beat: number;
}) {
  const holder = useRef<HTMLDivElement | null>(null);
  // Read inside the animation loop, which is created once per activation — state
  // in refs keeps the loop from being torn down and rebuilt on every beat.
  const live = useRef({ speaking, beat, hue });
  live.current = { speaking, beat, hue };

  useEffect(() => {
    const mount = holder.current;
    if (!mount || !active) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true, antialias: false, powerPreference: "low-power",
      });
    } catch {
      return;                 // no WebGL: the CSS gradient behind this is enough
    }

    const width = mount.clientWidth || 414;
    const height = mount.clientHeight || 736;
    // HALF RESOLUTION WHEN THE RENDERER IS PHOTOGRAPHING THIS, and it is the
    // single biggest lever on how long a download takes. Headless Chrome has no
    // GPU, so SwiftShader rasterises this particle field in software on every one
    // of the ~400 frames of a short — measured, hiding this layer entirely took a
    // 75-frame capture from 30s to 19s, so it was over half the per-frame cost.
    //
    // It does not need the pixels. It is an out-of-focus depth field sitting at
    // 0.38 opacity behind a diagram card; a half-scale buffer stretched back up is
    // indistinguishable from the full one, and it quarters the fill cost. The
    // player still gets full resolution.
    //
    // SCALED DOWN FURTHER WHEN SEVERAL CAPTURE WORKERS RUN AT ONCE. shorts/video.py
    // launches DEFAULT_WORKERS headless Chrome instances in parallel, each
    // software-rasterising its own copy of this layer, so the aggregate cost is
    // the per-worker cost times however many run together. This was investigated
    // as the cause of a beat that once photographed as an empty card — it was the
    // dominant per-frame cost and a real live suspect — but forcing this scale
    // down did not clear that bug (nor did --workers 1, in the end: the bug was
    // concurrency-independent, see AnimatedSvg.tsx's arrivalOrder() for the actual
    // cause and fix). This scaling stays anyway: giving several concurrent
    // instances less each to rasterise is a plain efficiency win on its own
    // terms. video.py passes ?bgscale=<n> sized to its own worker count (see
    // _bg_scale_for); a bare load with no query keeps the 0.5 this was tuned at.
    const capturing = !!(window as unknown as Record<string, unknown>).__captureMode;
    const bgParam = new URLSearchParams(location.hash.split("?")[1] ?? "").get("bgscale");
    const bgScale = bgParam ? Number(bgParam) : 0.5;
    renderer.setPixelRatio(
      capturing ? (Number.isFinite(bgScale) && bgScale > 0 ? bgScale : 0.5)
                : Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.setClearAlpha(0);
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 100);
    camera.position.z = 14;

    const tint = new THREE.Color().setHSL(hue / 360, 0.62, 0.62);

    // ---------------------------------------------------------------- the field
    const COUNT = 1100;
    const positions = new Float32Array(COUNT * 3);
    const drift = new Float32Array(COUNT);
    for (let i = 0; i < COUNT; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 26;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 40;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 18 - 4;
      drift[i] = 0.2 + Math.random() * 0.8;
    }
    const cloud = new THREE.BufferGeometry();
    cloud.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const dots = new THREE.Points(cloud, new THREE.PointsMaterial({
      color: tint, size: 0.1, sizeAttenuation: true,
      transparent: true, opacity: 0.5,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    scene.add(dots);

    // ---------------------------------------------- a second layer, for parallax
    //
    // NO SOLID OBJECT LIVES HERE ANY MORE. This was a wireframe torus knot, low and
    // off-centre, meant to read as depth. It did not: a torus knot is a recognisable
    // pretzel-and-loop shape, and the beat-change pulse brightened it at exactly the
    // moment attention moved — so every slide change flashed what looked like an
    // infinity symbol behind the diagram. A backdrop that can be identified as an
    // object is a backdrop that competes.
    //
    // Parallax comes from a second field instead: fewer points, larger, slower, and
    // further back. Two planes drifting at different rates read as depth without
    // ever resolving into a thing.
    const FAR = 260;
    const farPos = new Float32Array(FAR * 3);
    const farDrift = new Float32Array(FAR);
    for (let i = 0; i < FAR; i++) {
      farPos[i * 3] = (Math.random() - 0.5) * 34;
      farPos[i * 3 + 1] = (Math.random() - 0.5) * 44;
      farPos[i * 3 + 2] = (Math.random() - 0.5) * 8 - 14;
      farDrift[i] = 0.1 + Math.random() * 0.3;
    }
    const farCloud = new THREE.BufferGeometry();
    farCloud.setAttribute("position", new THREE.BufferAttribute(farPos, 3));
    const far = new THREE.Points(farCloud, new THREE.PointsMaterial({
      color: tint, size: 0.26, sizeAttenuation: true,
      transparent: true, opacity: 0.22,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    scene.add(far);

    // --------------------------------------------------------------- the loop
    let frame = 0;
    let pulse = 0;
    let lastBeat = live.current.beat;
    let breath = 0;
    let lastCaptured: number | null = null;
    const clock = new THREE.Clock();

    const tick = () => {
      frame = requestAnimationFrame(tick);
      // CAPTURE OVERRIDE. shorts/video.py photographs this page one frame at a
      // time, which takes far longer in wall time than the short lasts — so a
      // clock reading the wall would drift the depth layer out of step with the
      // picture it sits behind. CaptureStage publishes the VIDEO time instead, and
      // when it is present that is the only clock this loop obeys.
      const captured = (window as unknown as Record<string, unknown>).__captureTime;
      const t = typeof captured === "number" ? captured : clock.getElapsedTime();

      // UNDER CAPTURE, RENDER ONCE PER VIDEO FRAME — not once per animation frame.
      //
      // The renderer spends most of its wall clock encoding a screenshot and
      // shipping it over the DevTools socket, and this loop kept running flat out
      // the whole time: rebuilding the particle buffer and re-rendering the scene
      // dozens of times for a single video frame that had not changed. In software
      // rasterisation on a headless box that is the most expensive thing on the
      // page, and it was competing for CPU with the very encode it was waiting on.
      //
      // The capture clock only moves when seek() is called, so comparing against it
      // collapses all that to exactly one render per frame. There is nothing to see
      // in between — the page is not being photographed then.
      if (typeof captured === "number" && captured === lastCaptured) return;
      lastCaptured = typeof captured === "number" ? captured : null;

      const state = live.current;

      if (state.beat !== lastBeat) { lastBeat = state.beat; pulse = 1; }
      pulse *= 0.94;
      breath += ((state.speaking ? 1 : 0) - breath) * 0.05;

      const pos = cloud.attributes.position as THREE.BufferAttribute;
      const array = pos.array as Float32Array;
      for (let i = 0; i < COUNT; i++) {
        // Rising, slowly, and wrapped rather than reset — a field that visibly
        // restarts draws the eye, which is the one thing this must not do.
        array[i * 3 + 1] += drift[i] * 0.012 * (1 + breath * 0.7);
        if (array[i * 3 + 1] > 20) array[i * 3 + 1] = -20;
      }
      pos.needsUpdate = true;

      dots.rotation.y = t * 0.02;
      (dots.material as THREE.PointsMaterial).size = 0.1 + breath * 0.02 + pulse * 0.02;
      (dots.material as THREE.PointsMaterial).opacity = 0.4 + breath * 0.06 + pulse * 0.06;

      const farArr = (farCloud.attributes.position as THREE.BufferAttribute)
        .array as Float32Array;
      for (let i = 0; i < FAR; i++) {
        farArr[i * 3 + 1] += farDrift[i] * 0.006 * (1 + breath * 0.4);
        if (farArr[i * 3 + 1] > 22) farArr[i * 3 + 1] = -22;
      }
      (farCloud.attributes.position as THREE.BufferAttribute).needsUpdate = true;
      far.rotation.y = -t * 0.012;
      // The pulse is deliberately tiny now. It marks the beat change; it does not
      // announce it.
      (far.material as THREE.PointsMaterial).opacity = 0.2 + pulse * 0.05;

      camera.position.x = Math.sin(t * 0.11) * 0.8;
      camera.position.y = Math.cos(t * 0.09) * 0.5;
      camera.lookAt(0, 0, -4);

      renderer.render(scene, camera);
    };

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) renderer.render(scene, camera);
    else tick();

    const onResize = () => {
      const w = mount.clientWidth || width;
      const h = mount.clientHeight || height;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(onResize);
    observer.observe(mount);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      cloud.dispose();
      (dots.material as THREE.Material).dispose();
      farCloud.dispose();
      (far.material as THREE.Material).dispose();
      renderer.dispose();
      // forceContextLoss frees the GPU context now rather than whenever the
      // canvas is eventually collected, which is what keeps a long feed from
      // hitting the browser's context limit.
      renderer.forceContextLoss();
      mount.removeChild(renderer.domElement);
    };
    // hue is stable per short; beat and speaking are read through the ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, hue]);

  return <div className="threestage" ref={holder} aria-hidden="true" />;
}
