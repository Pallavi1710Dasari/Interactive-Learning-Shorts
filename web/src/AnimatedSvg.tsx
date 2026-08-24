import { useEffect, useMemo, useRef } from "react";

/**
 * A generated diagram, drawn on screen instead of appearing finished.
 *
 * WHY THE ANIMATION LIVES HERE AND NOT IN THE SVG
 * The frames are model-generated. Asking the model for <animate> tags gave frames
 * where three things moved at once for no reason, and a broken animation is a
 * broken diagram — there is no way to see it from the markup. So the model draws a
 * still frame and, optionally, TAGS it (see SVG_SYSTEM in shorts/skills/visuals.py):
 *
 *   data-enter="1"        the order things should arrive in; same number = together
 *   data-role="focus"     the one element this beat is about  -> keeps breathing
 *   data-role="flow"      an arrow that should show movement  -> marching dashes
 *   data-role="base"      carried over from the previous beat -> already there
 *
 * Every rule below degrades to something sensible when the tags are absent, which
 * is what lets the shorts built before this change animate without being redrawn:
 * document order becomes the arrival order, amber becomes the focus, and any
 * unfilled stroke gets drawn rather than faded.
 *
 * WHAT THE MOTION IS FOR
 * Not decoration. The diagram is meant to read as one composition that assembles,
 * so arrival order carries the explanation: the thing being talked about lands
 * last and then holds the eye. A viewer who watches it build knows where to look
 * without the frame having to shout with colour.
 */

/**
 * PACING — the parts arrive ONE AT A TIME, across the beat that explains them.
 *
 * The first version crammed the whole build into 900ms with up to seven steps, so
 * everything was on screen inside a second and a first-time viewer saw a finished,
 * busy diagram flash into place — which is the same as no animation, except more
 * distracting. The build only helps if it is slow enough to follow.
 *
 * So the stagger is spread across most of the BEAT's own duration, which the
 * player knows, and each part gets a floor of MIN_STEP_MS to itself. A beat is
 * typically 4-7 seconds; four parts then land about a second apart, which is
 * roughly reading speed and lets the eye finish one before the next appears.
 *
 * The build stops short of the beat's end (BUILD_FRACTION) so the completed frame
 * is on screen, whole and still, while the sentence finishes.
 */
const BUILD_FRACTION = 0.66;
const MIN_STEP_MS = 420;
const MAX_STEP_MS = 1100;

/** Fallback when the beat's duration is unknown. */
const DEFAULT_BEAT_MS = 4500;

/** Never subdivide a frame into more arrivals than a viewer can follow. */
const MAX_STEPS = 5;

/** How long a stroke takes to draw itself along its own length. */
const DRAW_MS = 520;

/** The palette's amber — SVG_SYSTEM reserves it for the element under discussion. */
const AMBER = /#f2b14b/i;

export function AnimatedSvg({ svg, beatKey, composition, beatMs }: {
  svg: string;
  beatKey: string;
  /** Every frame of this short, so all of them can share one crop. */
  composition: string[];
  /** How long the narration spends on this beat, in ms. Paces the build. */
  beatMs?: number;
}) {
  const host = useRef<HTMLDivElement | null>(null);

  // Measured once per short, not once per beat. See cropFor().
  const crop = useMemo(() => cropFor(composition), [composition]);

  useEffect(() => {
    const wrap = host.current;
    if (!wrap) return;

    // Sanitised server-side in shorts/feed.py._clean_svg.
    wrap.innerHTML = svg;
    const root = wrap.querySelector("svg");
    if (!root) return;

    root.setAttribute("preserveAspectRatio", "xMidYMid meet");
    applyCrop(root, crop);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const running: Animation[] = [];

    if (reduced) {
      running.push(root.animate([{ opacity: 0 }, { opacity: 1 }],
                               { duration: 220, fill: "both" }));
      return () => running.forEach((a) => a.cancel());
    }

    const steps = arrivalOrder(root);
    const budget = (beatMs && beatMs > 400 ? beatMs : DEFAULT_BEAT_MS) * BUILD_FRACTION;
    const gap = steps.length > 1
      ? Math.min(MAX_STEP_MS, Math.max(MIN_STEP_MS, budget / (steps.length - 1)))
      : 0;

    steps.forEach((group, step) => {
      const delay = step * gap;
      for (const el of group) {
        const role = el.dataset.role;
        // "base" was already on screen in the previous frame, so it does not
        // enter at all — the markup is re-injected on every beat, so an element
        // with no entrance animation simply appears, which is exactly right for
        // something the viewer was already looking at. Animating it, even
        // briefly, is what makes four frames look like four pictures instead of
        // one drawing being added to.
        const base = role === "base";
        if (!base) running.push(...enter(el, delay));

        const flows = role === "flow" || (!role && isArrow(el));
        if (flows) running.push(...march(el, base ? 0 : delay));
        if (role === "focus" || (!role && isAmber(el))) running.push(...breathe(el, delay));
      }
    });

    return () => running.forEach((a) => a.cancel());
  }, [svg, beatKey, crop, beatMs]);

  return <div className="svgwrap animated" ref={host} />;
}

/**
 * Elements grouped into arrival steps.
 *
 * `data-enter` when the frame is tagged; otherwise the top-level children in
 * document order, which is the order the model drew them and therefore already
 * roughly the order it was thinking in.
 */
function arrivalOrder(root: SVGSVGElement): SVGElement[][] {
  const tagged = Array.from(root.querySelectorAll<SVGElement>("[data-enter]"));
  if (tagged.length) {
    const byStep = new Map<number, SVGElement[]>();
    for (const el of tagged) {
      const n = Number(el.dataset.enter) || 0;
      const group = byStep.get(n);
      if (group) group.push(el);
      else byStep.set(n, [el]);
    }
    // Anything untagged in a tagged frame arrives first: it is the backdrop the
    // tagged elements are being placed onto.
    const untagged = Array.from(root.children).filter(
      (c): c is SVGElement => c instanceof SVGElement && !c.hasAttribute("data-enter")
        && !c.querySelector("[data-enter]"),
    );
    let ordered = [...byStep.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v);
    if (untagged.length) ordered = [untagged, ...ordered];
    return merge(ordered, MAX_STEPS);
  }

  // Untagged: one element per step, but never more steps than a viewer can follow —
  // a 20-shape frame animated one shape at a time is a slideshow, not a build.
  const kids = Array.from(root.children).filter(
    (c): c is SVGElement => c instanceof SVGElement && c.tagName.toLowerCase() !== "defs",
  );
  const maxSteps = MAX_STEPS;
  if (kids.length <= maxSteps) return kids.map((k) => [k]);
  const per = Math.ceil(kids.length / maxSteps);
  const out: SVGElement[][] = [];
  for (let i = 0; i < kids.length; i += per) out.push(kids.slice(i, i + per));
  return out;
}

/**
 * Fold a long list of arrival steps down to at most `cap`, preserving order.
 *
 * A model that tags nine arrival steps has described the drawing order honestly;
 * it has not decided how long the viewer has. Nine arrivals at a followable pace
 * outlasts any beat, so neighbouring steps are combined until they fit.
 */
function merge(steps: SVGElement[][], cap: number): SVGElement[][] {
  if (steps.length <= cap) return steps;
  const per = Math.ceil(steps.length / cap);
  const out: SVGElement[][] = [];
  for (let i = 0; i < steps.length; i += per) out.push(steps.slice(i, i + per).flat());
  return out;
}

/**
 * The entrance itself: a stroke gets drawn, everything else fades up.
 *
 * Transform is only used on elements that do not already carry a `transform`
 * attribute. A CSS transform replaces the attribute rather than composing with
 * it, so animating one would fling a positioned element across the canvas.
 */
function enter(el: SVGElement, delay: number): Animation[] {
  const timing: KeyframeAnimationOptions = {
    duration: 440, delay, fill: "both",
    easing: "cubic-bezier(.22,.8,.24,1)",
  };

  if (isStroke(el)) {
    const drawn = draw(el, { ...timing, duration: DRAW_MS });
    if (drawn) return [drawn];
  }

  if (el.hasAttribute("transform"))
    return [el.animate([{ opacity: 0 }, { opacity: 1 }], timing)];

  el.style.transformBox = "fill-box";
  el.style.transformOrigin = "center";
  return [el.animate(
    [{ opacity: 0, transform: "translateY(10px) scale(.94)" },
     { opacity: 1, transform: "none" }],
    timing,
  )];
}

/** Draw a line or path along its own length. Returns null if it has no length. */
function draw(el: SVGElement, timing: KeyframeAnimationOptions): Animation | null {
  const geo = el as unknown as SVGGeometryElement;
  if (typeof geo.getTotalLength !== "function") return null;
  let length = 0;
  try { length = geo.getTotalLength(); } catch { return null; }
  if (!length || !isFinite(length)) return null;

  // A dasharray already on the element is a deliberate dashed line, so the
  // override is handed back when the draw finishes rather than left in place.
  const original = el.style.strokeDasharray;
  el.style.strokeDasharray = `${length}`;

  const anim = el.animate(
    [{ strokeDashoffset: length }, { strokeDashoffset: 0 }],
    { ...timing, fill: "both" },
  );
  anim.finished
    .then(() => { el.style.strokeDasharray = original; })
    .catch(() => {});      // cancelled on beat change; nothing to restore
  return anim;
}

/**
 * Dashes marching along an arrow, so the direction of flow is visible.
 *
 * The dash pattern is set INSIDE the keyframes rather than on el.style, because
 * the same element has usually just been drawn on by draw() — which owns
 * stroke-dasharray for the length of that animation. Writing the pattern directly
 * would overwrite it at setup time and cancel the draw before it was seen. In
 * keyframes with no backwards fill the pattern only applies once the delay is up,
 * which is after the draw has finished and handed the property back.
 */
function march(el: SVGElement, delay: number): Animation[] {
  const geo = el as unknown as SVGGeometryElement;
  if (typeof geo.getTotalLength !== "function") return [];
  return [el.animate(
    [{ strokeDasharray: "18 14", strokeDashoffset: 32 },
     { strokeDasharray: "18 14", strokeDashoffset: 0 }],
    { duration: 1100, delay: delay + DRAW_MS + 60, iterations: Infinity,
      easing: "linear", fill: "forwards" },
  )];
}

/** The focus element keeps a slow pulse, so the eye returns to it mid-beat. */
function breathe(el: SVGElement, delay: number): Animation[] {
  if (el.hasAttribute("transform")) return [];
  el.style.transformBox = "fill-box";
  el.style.transformOrigin = "center";
  return [el.animate(
    [{ transform: "scale(1)", opacity: 1 },
     { transform: "scale(1.035)", opacity: 0.94 },
     { transform: "scale(1)", opacity: 1 }],
    { duration: 2000, delay: delay + 460, iterations: Infinity, easing: "ease-in-out" },
  )];
}

type Box = { x: number; y: number; w: number; h: number };

/**
 * The declared drawing area. SVG_SYSTEM hands the model a 1080x1080 canvas but
 * reserves the bottom of it, so this is the most of it a frame should ever use.
 */
const CANVAS: Box = { x: 44, y: 44, w: 992, h: 912 };

/**
 * ONE crop for the whole short, measured from the ink of ALL its frames.
 *
 * The problem being solved is dead space. A frame legitimately uses the middle of
 * its 1080-square and leaves the title band and the bottom label band mostly
 * empty, so rendering the declared canvas scaled the drawing down to about half
 * the card — on a phone that is the difference between a readable label and a grey
 * smudge.
 *
 * The reason it is measured across every frame rather than per frame is the whole
 * point of the composition: the frames deliberately share coordinates so the
 * diagram looks like it is being added to. Cropping each frame to its own ink
 * rescales the shared objects between beats, and the table that was supposed to
 * sit still visibly grows and shifts as the short plays. One crop for all frames
 * fills the card AND holds the shared geometry exactly still.
 *
 * Measuring needs a laid-out SVG, so the frames go through a hidden container in
 * the document. It runs once per short — memoised on the frame list — not per
 * beat.
 */
function cropFor(frames: string[]): Box {
  if (typeof document === "undefined" || !frames.length) return CANVAS;

  const shed = document.createElement("div");
  shed.setAttribute("aria-hidden", "true");
  shed.style.cssText =
    "position:absolute;left:-9999px;top:0;width:1080px;height:1080px;" +
    "visibility:hidden;pointer-events:none";
  document.body.appendChild(shed);

  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  try {
    for (const frame of frames) {
      if (!frame) continue;
      shed.innerHTML = frame;
      const root = shed.querySelector("svg");
      if (!root) continue;
      root.setAttribute("width", "1080");
      root.setAttribute("height", "1080");
      let ink: DOMRect;
      try { ink = root.getBBox(); } catch { continue; }
      if (!ink.width || !ink.height) continue;
      x0 = Math.min(x0, ink.x);
      y0 = Math.min(y0, ink.y);
      x1 = Math.max(x1, ink.x + ink.width);
      y1 = Math.max(y1, ink.y + ink.height);
    }
  } finally {
    shed.remove();
  }

  if (!isFinite(x0) || !isFinite(y0) || x1 <= x0 || y1 <= y0) return CANVAS;

  const pad = 24;
  return { x: x0 - pad, y: y0 - pad, w: x1 - x0 + pad * 2, h: y1 - y0 + pad * 2 };
}

/**
 * Apply the short's crop, widened if THIS frame drew outside it.
 *
 * The crop is measured from every frame, so a frame should never exceed it — but a
 * measurement that failed (a frame that was not laid out yet) falls back to the
 * declared canvas, and some frames break the canvas rules and put a label at
 * y=990. Expanding rather than clipping means a rule-breaking frame is ugly, not
 * truncated.
 */
function applyCrop(root: SVGSVGElement, crop: Box): void {
  let x0 = crop.x, y0 = crop.y, x1 = crop.x + crop.w, y1 = crop.y + crop.h;

  try {
    const ink = root.getBBox();
    if (ink.width && ink.height) {
      const pad = 12;
      x0 = Math.min(x0, ink.x - pad);
      y0 = Math.min(y0, ink.y - pad);
      x1 = Math.max(x1, ink.x + ink.width + pad);
      y1 = Math.max(y1, ink.y + ink.height + pad);
    }
  } catch {
    // getBBox throws on a subtree that is not laid out; the short's crop stands.
  }

  const w = x1 - x0, h = y1 - y0;
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return;

  root.setAttribute("viewBox", `${round(x0)} ${round(y0)} ${round(w)} ${round(h)}`);
  root.removeAttribute("width");
  root.removeAttribute("height");
}

const round = (n: number) => Math.round(n * 10) / 10;

function isStroke(el: SVGElement): boolean {
  const tag = el.tagName.toLowerCase();
  if (!["path", "line", "polyline"].includes(tag)) return false;
  const fill = (el.getAttribute("fill") ?? "none").toLowerCase();
  return fill === "none" || fill === "transparent";
}

function isArrow(el: SVGElement): boolean {
  if (!isStroke(el)) return false;
  const w = parseFloat(el.getAttribute("stroke-width") ?? "0");
  return w >= 4;      // the palette draws arrows thick; hairlines are guides
}

function isAmber(el: SVGElement): boolean {
  return AMBER.test(el.getAttribute("fill") ?? "")
      || AMBER.test(el.getAttribute("stroke") ?? "");
}
