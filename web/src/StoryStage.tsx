import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChunkCaption } from "./ChunkCaption";
import type { StoryReel, StoryShot } from "./types";

/**
 * Story mode's stage — RESTYLE_TO_STORY_REELS.md Step 8 Part 2. A SEPARATE
 * render tree from ReelStage's explainer branch (see ReelStage.tsx's own
 * top-level "branch on the story JSON"), not a variant of it: no navy
 * gradient, no Three.js depth layer, no progress segments, no Focus/
 * Context legend (that one never existed here to begin with — it is baked
 * into explainer mode's SVG strings by shorts/skills/layout.py, which story
 * mode's PNG shots never go through), no framed diagram box.
 *
 * `time` is ABSOLUTE SECONDS FROM THE START OF THE WHOLE REEL — the same
 * clock story.shots' own start/end (shorts/story_audio.py's real measured
 * timings.json) are already expressed in, so nothing here re-derives or
 * offsets it.
 */

function currentShotIndex(shots: StoryShot[], time: number): number {
  // THE LAST SHOT THAT HAS STARTED — the same "hold what's on screen
  // through a gap" rule CaptureStage.tsx's own beatIndex uses for
  // explainer mode (STORY_SHOT_AUDIO_GAP puts real silence between shots,
  // so a containment test would return "no shot" during every gap).
  let idx = 0;
  for (let i = 0; i < shots.length; i++) {
    if (shots[i].start <= time) idx = i;
    else break;
  }
  return idx;
}

const CAMERA_KEYFRAMES: Partial<Record<StoryShot["camera"], Keyframe[]>> = {
  zoom_in: [{ transform: "scale(1.00)" }, { transform: "scale(1.08)" }],
  zoom_out: [{ transform: "scale(1.08)" }, { transform: "scale(1.00)" }],
  push_left: [{ transform: "translateX(0%)" }, { transform: "translateX(-3%)" }],
  push_right: [{ transform: "translateX(0%)" }, { transform: "translateX(3%)" }],
};

/** One scene shot's full-bleed image, animated per shot.camera via the Web
 *  Animations API (RESTYLE_TO_STORY_REELS.md's own instruction) — NOT CSS
 *  @keyframes, for the same reason AnimatedSvg.tsx isn't either (see
 *  CaptureStage.tsx's own docstring): shorts/video.py's frame-exact capture
 *  freezes every animation by writing its `currentTime`, which only exists
 *  on a WAAPI Animation object. Re-created fresh on every mount — the
 *  parent keys this by shot.shot_id, so a shot change is a full remount,
 *  never a re-animation of a stale Animation instance. */
function StoryFrame({ shot }: { shot: StoryShot }) {
  const ref = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const durationMs = Math.max(200, (shot.end - shot.start) * 1000);
    if (shot.camera === "shake") {
      // "3 quick +-6px jitters at line start" — a short burst at the
      // shot's own beginning, not stretched across its whole duration.
      const jitterMs = Math.min(500, durationMs);
      el.animate([
        { transform: "translate(0px, 0px)" },
        { transform: "translate(6px, -6px)" },
        { transform: "translate(-6px, 6px)" },
        { transform: "translate(6px, 6px)" },
        { transform: "translate(-6px, -6px)" },
        { transform: "translate(0px, 0px)" },
      ], { duration: jitterMs, easing: "ease-in-out", fill: "forwards" });
      return;
    }
    const keyframes = CAMERA_KEYFRAMES[shot.camera];
    if (keyframes) {
      el.animate(keyframes, { duration: durationMs, easing: "linear", fill: "forwards" });
    }
    // "static" — no animation at all.
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps -- remount-scoped, see docstring

  if (!shot.image_url) return null;
  return <img ref={ref} className="story-frame" src={shot.image_url} alt="" />;
}

/** Shot 1 only: the reel's own title, bold black on a white highlight box,
 *  top-center, for its first 3 seconds — RESTYLE_TO_STORY_REELS.md's own
 *  "Title" rule. Fades out via WAAPI (not display:none) so a capture at
 *  exactly the 3s boundary still freezes a coherent in-between frame
 *  rather than a hard pop. */
function StoryTitle({ title }: { title: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.animate([
      { opacity: 1, offset: 0 },
      { opacity: 1, offset: 0.85 },
      { opacity: 0, offset: 1 },
    ], { duration: 3000, easing: "linear", fill: "forwards" });
  }, []);
  return (
    <div className="story-title" ref={ref}>
      <span>{title}</span>
    </div>
  );
}

/** A `code`-like backtick span inside overlay_text, split from the plain
 *  prose around it — RESTYLE_TO_STORY_REELS.md's "code in a light code
 *  box" rule. No structured code field exists on Shot (overlay_text is
 *  plain prose — see skills/script.py's SYSTEM_STORY_SHOTS prompt, which
 *  never asks for backtick-delimited code), so this is the one place that
 *  convention is invented: a backtick span containing code-shaped
 *  punctuation ( ( ) { } ; = . ) or more than 3 words becomes its own code
 *  box; a SHORT backtick span (a bare keyword/term) is instead highlighted
 *  purple INLINE, in the heading text itself — the "purple keyword
 *  highlight" rule. Plain overlay_text with no backticks at all (the
 *  common case — see the stub fixture's own text_card shots) renders as a
 *  heading with no highlight and no code box. */
function splitTextCard(overlay: string): { heading: React.ReactNode; code: string | null } {
  const match = overlay.match(/`([^`]+)`/);
  if (!match) return { heading: overlay, code: null };
  const span = match[1];
  const isCodeShaped = /[(){};=.]/.test(span) || span.trim().split(/\s+/).length > 3;
  if (isCodeShaped) {
    const heading = overlay.slice(0, match.index).trim() +
      (match.index === 0 ? "" : " ") + overlay.slice((match.index ?? 0) + match[0].length).trim();
    return { heading: heading.trim() || overlay, code: span };
  }
  const before = overlay.slice(0, match.index);
  const after = overlay.slice((match.index ?? 0) + match[0].length);
  return {
    heading: <>{before}<span className="story-keyword">{span}</span>{after}</>,
    code: null,
  };
}

function StoryTextCard({ shot }: { shot: StoryShot }) {
  const { heading, code } = useMemo(
    () => splitTextCard(shot.overlay_text || ""), [shot.overlay_text]);
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // "Pop-in scale 0.9 -> 1.0 over 200ms."
    el.animate([{ transform: "scale(0.9)", opacity: 0 },
               { transform: "scale(1.0)", opacity: 1 }],
              { duration: 200, easing: "ease-out", fill: "forwards" });
  }, []);
  return (
    <div className="story-card story-text-card" ref={ref}>
      <div className="story-brand-shapes"><BrandShapes /></div>
      <h2 className="story-heading">
        {heading}
        <span className="story-underline" />
      </h2>
      {code && <pre className="story-code-box"><code>{code}</code></pre>}
    </div>
  );
}

function StoryRecap({ shot, systemName, lessons }: {
  shot: StoryShot; systemName: string; lessons: string[];
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.animate([{ transform: "scale(0.9)", opacity: 0 },
               { transform: "scale(1.0)", opacity: 1 }],
              { duration: 200, easing: "ease-out", fill: "forwards" });
    // Staggered lesson lines, 150ms apart.
    const items = el.querySelectorAll<HTMLElement>(".story-lesson");
    items.forEach((item, i) => {
      item.animate([{ opacity: 0, transform: "translateY(8px)" },
                    { opacity: 1, transform: "translateY(0)" }],
                   { duration: 250, delay: 200 + i * 150, easing: "ease-out",
                     fill: "backwards" });
    });
  }, []);
  const cardLines = shot.card_lines.length ? shot.card_lines : lessons;
  return (
    <div className="story-card story-recap" ref={ref}>
      <div className="story-brand-shapes"><BrandShapes /></div>
      <h2 className="story-heading">
        {systemName || "This system"} teaches more than code <span className="story-heart">♥</span>
      </h2>
      <ul className="story-lessons">
        {cardLines.map((line, i) => (
          <li className="story-lesson" key={i}>{line.toUpperCase()}</li>
        ))}
      </ul>
    </div>
  );
}

function StoryCta({ shot, handle, systemName }: {
  shot: StoryShot; handle: string; systemName: string;
}) {
  const dimRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const card = cardRef.current, dim = dimRef.current;
    if (!card || !dim) return;
    card.animate([{ transform: "scale(0.9)", opacity: 0 },
                  { transform: "scale(1.0)", opacity: 1 }],
                 { duration: 200, easing: "ease-out", fill: "forwards" });
    // "last 1.5s dims to 60% and shows the handle large" — a dark scrim
    // fades in to 60% opacity over the final 1.5s of this shot's own
    // duration, staying off (0%) for everything before that.
    const totalMs = Math.max(200, (shot.end - shot.start) * 1000);
    const dimStartFrac = Math.max(0, 1 - 1500 / totalMs);
    dim.animate([
      { opacity: 0, offset: 0 },
      { opacity: 0, offset: dimStartFrac },
      { opacity: 0.6, offset: 1 },
    ], { duration: totalMs, easing: "linear", fill: "forwards" });
  }, []);
  return (
    <div className="story-card story-cta">
      {shot.image_url && <img className="story-frame story-cta-mascot" src={shot.image_url} alt="" />}
      <div className="story-cta-dim" ref={dimRef} />
      <div className="story-brand-shapes"><BrandShapes /></div>
      <div className="story-cta-copy" ref={cardRef}>
        <h2 className="story-cta-handle">Follow {handle}</h2>
        <p className="story-cta-subtitle">To learn {systemName || "this"} in a simple way</p>
      </div>
    </div>
  );
}

/** Purple corner triangle, yellow stroke, small "+"/dots — text_card, recap
 *  and cta ONLY (RESTYLE_TO_STORY_REELS.md's own scoping); never on a
 *  scene/image shot, which is already full-bleed art. Plain decorative
 *  SVG/div shapes, not brought in from anywhere else. */
function BrandShapes() {
  return (
    <>
      <svg className="story-shape-triangle" viewBox="0 0 200 200" aria-hidden="true">
        <polygon points="0,0 200,0 0,200" fill="var(--brand-accent-1)" />
      </svg>
      <svg className="story-shape-stroke" viewBox="0 0 300 20" aria-hidden="true">
        <path d="M0,10 Q75,0 150,10 T300,10" stroke="var(--brand-accent-2)"
             strokeWidth="6" fill="none" strokeLinecap="round" />
      </svg>
      <span className="story-shape-plus">+</span>
      <span className="story-shape-dot story-shape-dot-1" />
      <span className="story-shape-dot story-shape-dot-2" />
    </>
  );
}

/** Persistent logo, bottom-right, ~14% of frame width, 24px margin — from
 *  assets/brand/logo.png (served at /story-assets/brand/logo.png). Falls
 *  back to a plain drawn placeholder (and a one-time console warning) when
 *  the file is missing, which it is in a fresh checkout (no assets/brand/
 *  directory exists yet — see RESTYLE_TO_STORY_REELS.md Step 8 Part 2's
 *  own "if missing, render a neutral placeholder and warn" rule). */
function StoryLogo() {
  return (
    <img className="story-logo" src="/story-assets/brand/logo.png" alt=""
        onError={(e) => {
          const img = e.currentTarget;
          if (img.dataset.fallback) return;
          img.dataset.fallback = "1";
          console.warn("story mode: assets/brand/logo.png is missing — "
                       + "showing a placeholder. Add a real logo there to replace it.");
          img.style.display = "none";
          const placeholder = document.createElement("div");
          placeholder.className = "story-logo story-logo-placeholder";
          placeholder.textContent = "●";
          img.parentElement?.appendChild(placeholder);
        }} />
  );
}

/** Faint handle watermark, top-right, 25% opacity — persistent on every
 *  shot, scene shots included (unlike BrandShapes, which is text_card/
 *  recap/cta only). */
function StoryWatermark({ handle }: { handle: string }) {
  return <div className="story-watermark">{handle}</div>;
}

export function StoryStage({ story, time }: { story: StoryReel; time: number }) {
  const idx = useMemo(() => currentShotIndex(story.shots, time), [story.shots, time]);
  const shot = story.shots[idx];
  if (!shot) return <div className="story-stage" />;

  return (
    <div className="story-stage">
      <div className="story-bg" />
      {shot.kind === "scene" && (
        <div className="story-scene" key={shot.shot_id}>
          <StoryFrame shot={shot} />
          {idx === 0 && <StoryTitle title={story.hook_line} />}
          <ChunkCaption line={shot.line || ""} words={shot.words} time={time} />
        </div>
      )}
      {shot.kind === "text_card" && <StoryTextCard shot={shot} key={shot.shot_id} />}
      {shot.kind === "recap" && (
        <StoryRecap shot={shot} systemName={story.system_name}
                   lessons={story.lessons} key={shot.shot_id} />
      )}
      {shot.kind === "cta" && (
        <StoryCta shot={shot} handle={getBrandHandle()}
                 systemName={story.system_name} key={shot.shot_id} />
      )}
      <StoryLogo />
      <StoryWatermark handle={getBrandHandle()} />
    </div>
  );
}

/** config.BRAND_HANDLE, read fresh on every call from the data attribute
 *  main.tsx's own /api/health fetch sets on <html> (the same mechanism
 *  `theme`/brand colors use — see that file's own comment) — read inline
 *  at render time, not memoized, so a StoryStage re-render after the
 *  (async) health fetch resolves always sees the current value with no
 *  extra state or effect needed. Falls back to config.py's own documented
 *  default so the page still reads correctly before that fetch resolves,
 *  or if it fails — the same "failing open" rule main.tsx's own comment
 *  states for `theme`. */
function getBrandHandle(): string {
  return document.documentElement.dataset.brandHandle || "@learnthesimpleway";
}

/**
 * The story-mode counterpart to CaptureStage.tsx — same `window.__capture`
 * contract (duration, seek, shortId), same frame-exact freeze mechanism
 * (double-rAF, then write every WAAPI animation's own `currentTime`), just
 * driven off story.shots' own start/end (real measured timings) instead of
 * unit.beats. shorts/video.py's capture loop (`_capture_slice`) does not
 * know or care which of the two mounted this contract — it only ever calls
 * `window.__capture.seek(t)`.
 */
export function StoryCaptureStage({ story }: { story: StoryReel }) {
  const [t, setT] = useState(0);
  const pending = useRef<(() => void) | null>(null);

  const shotIndex = useMemo(() => currentShotIndex(story.shots, t), [story.shots, t]);

  useLayoutEffect(() => {
    let a = 0, b = 0;
    a = requestAnimationFrame(() => {
      const shot = story.shots[shotIndex];
      const local = shot ? Math.max(0, (t - shot.start) * 1000) : 0;
      for (const anim of document.getAnimations()) {
        try {
          anim.currentTime = local;
          anim.pause();
        } catch {
          /* an animation whose effect has been torn down; nothing to freeze */
        }
      }
      b = requestAnimationFrame(() => {
        const done = pending.current;
        pending.current = null;
        done?.();
      });
    });
    return () => { cancelAnimationFrame(a); cancelAnimationFrame(b); };
  }, [t, shotIndex, story.shots]);

  useEffect(() => {
    const api = {
      duration: story.total,
      beats: story.shots.length,
      shortId: story.short_id,
      seek: (seconds: number) =>
        new Promise<void>((resolve) => {
          pending.current = resolve;
          setT((prev) => (prev === seconds ? seconds + 1e-6 : seconds));
        }),
    };
    const w = window as unknown as Record<string, unknown>;
    w.__capture = api;
    w.__captureMode = true;
    return () => { delete w.__capture; delete w.__captureMode; };
  }, [story]);

  return (
    <div className="reel live capture">
      <StoryStage story={story} time={t} />
    </div>
  );
}
