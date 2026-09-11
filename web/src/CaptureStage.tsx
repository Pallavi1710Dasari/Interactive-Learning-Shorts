import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ReelStage, beatFill, hueFor } from "./ReelStage";
import type { Unit } from "./types";

/**
 * The reel, frozen at an arbitrary instant, for shorts/video.py to photograph.
 *
 * WHY A SEEKABLE COPY EXISTS AT ALL. The renderer needs frame N of the short, and
 * the player cannot give it one: the player's clock is an <audio> element, which
 * runs in real time, only reports itself about four times a second, and in a
 * headless browser may not decode at all. Photographing a page that plays normally
 * would give a video whose frame rate is whatever the capture loop happened to
 * achieve, with the WebGL layer and the build animation sampled at random.
 *
 * So capture does not play anything. It seeks. `window.__capture.seek(t)` puts the
 * short in the state it would be in exactly t seconds in and resolves once that
 * state has painted — then one screenshot is exactly one frame, and 30 of them are
 * exactly one second, by construction rather than by luck.
 *
 * WHAT MAKES THAT POSSIBLE is that the build animation is Web Animations API, not
 * CSS keyframes: every animation on the page has a `currentTime` that can be
 * written. AnimatedSvg chose WAAPI for unrelated reasons (see its header) and it is
 * the reason this renderer can be frame-exact instead of approximate.
 *
 * The audio is NOT played here. voice.synthesize already wrote audio.mp3 and ffmpeg
 * muxes it against the same feed._timeline spans these frames are seeked to, so
 * picture and sound cannot drift.
 */
export function CaptureStage({ unit }: { unit: Unit }) {
  const [t, setT] = useState(0);
  const pending = useRef<(() => void) | null>(null);
  const hue = useMemo(() => hueFor(unit.short_id), [unit.short_id]);

  const beatIndex = useMemo(() => {
    // THE LAST BEAT THAT HAS STARTED — not the beat whose span CONTAINS t, and
    // the difference is a real defect rather than a nicety.
    //
    // tts.synthesize puts VOICE_BEAT_GAP (0.45s) of silence between beats, so the
    // spans feed._timeline reports are NOT contiguous: css_color_property runs
    // 0.00-2.56, then 3.01-7.08, then 7.54-12.42. A containment test returns
    // "no beat" for every instant in those two gaps, and the first version of this
    // clamped that to `beats.length - 1` — so at t=2.8 the picture cut to the
    // FINAL beat for a third of a second and then cut back. Fourteen frames of the
    // wrong diagram, twice per short.
    //
    // Holding the beat that is already on screen is also what the player does: its
    // beat only advances when a span claims the time, so silence looks like the
    // sentence that just finished, which is what silence sounds like.
    let idx = 0;
    for (let i = 0; i < unit.beats.length; i++) {
      if (t >= unit.beats[i].start) idx = i;
      else break;
    }
    return idx;
  }, [t, unit.beats]);

  // AFTER the paint for this t, freeze every animation at its t and let the
  // renderer know the frame is ready.
  //
  // Two rAFs, not one, and both are load-bearing. React has committed by the time
  // a layout effect runs, but a freshly mounted AnimatedSvg creates its animations
  // in its OWN effect — so the first frame is when those exist to be seeked, and
  // the second is when the seeked state has actually been painted. Resolving any
  // earlier photographs the previous beat.
  useLayoutEffect(() => {
    let a = 0, b = 0;
    a = requestAnimationFrame(() => {
      const beat = unit.beats[beatIndex];
      const local = Math.max(0, (t - beat.start) * 1000);
      for (const anim of document.getAnimations()) {
        try {
          anim.currentTime = local;
          anim.pause();
        } catch {
          /* an animation whose effect has been torn down; nothing to freeze */
        }
      }
      // The WebGL layer runs off its own THREE.Clock, which would otherwise
      // advance in WALL time while the renderer spends a minute taking 450
      // screenshots — the background would drift out of step with the picture.
      (window as unknown as Record<string, unknown>).__captureTime = t;
      b = requestAnimationFrame(() => {
        const done = pending.current;
        pending.current = null;
        done?.();
      });
    });
    return () => { cancelAnimationFrame(a); cancelAnimationFrame(b); };
  }, [t, beatIndex, unit.beats]);

  useEffect(() => {
    const api = {
      duration: unit.seconds,
      beats: unit.beats.length,
      shortId: unit.short_id,
      seek: (seconds: number) =>
        new Promise<void>((resolve) => {
          pending.current = resolve;
          // Same t twice would not re-render, so the promise would never settle.
          setT((prev) => (prev === seconds ? seconds + 1e-6 : seconds));
        }),
    };
    const w = window as unknown as Record<string, unknown>;
    w.__capture = api;
    // Announced separately from __capture, and BEFORE the first seek, because
    // ThreeStage reads it when it builds its renderer — which happens on mount,
    // long before any frame is asked for. See its setPixelRatio call.
    w.__captureMode = true;
    return () => { delete w.__capture; delete w.__captureMode; };
  }, [unit]);

  return (
    <div className="reel live capture" style={{ ["--hue" as string]: hue }}>
      <ReelStage
        unit={unit}
        beatIndex={beatIndex}
        time={t}
        speaking
        hue={hue}
        progressPct={beatFill(t / Math.max(unit.seconds, 0.001), beatIndex,
                              unit.beats.length)}
      />
    </div>
  );
}
