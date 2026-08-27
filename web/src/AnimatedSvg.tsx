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
 *   data-role="focus"     the one element this beat is about  -> one arrival beat
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
 * is on screen, whole and still, while the sentence finishes — and ENTER_TAIL_MS is
 * held back from the budget so that "whole" includes the last arrival's own
 * animation, not just the moment it was told to start.
 */
// 0.55, DOWN FROM 0.72, because the reviewer's complaint flipped direction:
// "the visuals coming late after the text came". Both failure modes described in
// the pacing comment below are real, and this sits between them — at 0.72 the
// picture only finished about three quarters of the way through the sentence
// explaining it, so for most of every beat the viewer was reading a caption
// against a half-drawn diagram. At 0.55 the frame completes a little past the
// midpoint and then HOLDS, whole and still, for the rest of the line.
//
// This is the knob to turn if it still feels wrong in either direction: lower
// means the picture leads the voice, higher means it trails.
const BUILD_FRACTION = 0.55;
const MIN_STEP_MS = 420;

/**
 * The longest any single arrival animation runs — `enter`'s stroke-draw case, plus
 * `breathe`'s one-shot emphasis, whichever is worse.
 *
 * Reserved out of the build budget so the LAST element's own animation finishes
 * inside the beat that explains it. Without the reserve the final arrival started
 * at the end of the budget and was still moving when the beat ended, so the closing
 * frame of a short was replaced — or, on the last beat, frozen by playback
 * stopping — while it was still assembling. Watched back, the short "ends half
 * way".
 */
const ENTER_TAIL_MS = 1120;

/** Fallback when the beat's duration is unknown. */
const DEFAULT_BEAT_MS = 4500;

/** Never subdivide a frame into more arrivals than a viewer can follow. */
const MAX_STEPS = 5;

/** How much larger than the short's shared crop a sparse frame may be drawn. */
const ZOOM_CAP = 1.6;

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

    // PACING, AND BOTH WAYS IT USED TO BE WRONG.
    //
    // This was one line: gap = clamp(budget / (steps - 1), MIN_STEP_MS, MAX_STEP_MS),
    // and each clamp caused a different complaint.
    //
    // Clamping UP overran the beat. Five arrivals in a 1.5s beat gives 247ms each,
    // raised to the 420ms floor, so the build ran 1680ms inside a 1500ms beat and
    // the frame was still assembling when the beat ended — on the last beat, when
    // playback stops, it simply froze part-drawn. That is the short that "feels
    // like it is cut in half".
    //
    // Clamping DOWN made the picture lead the narration. Two arrivals in a 7s beat
    // wants 4.6s of spread; capped at 1100ms the whole diagram was finished 1.1s
    // in — 16% of the way through the sentence that explains it. The viewer sees the
    // answer, then waits for the voice to catch up, which is "the visuals come
    // before the context".
    //
    // So neither clamp survives. The gap is whatever spreads the arrivals across
    // the budget, and when that would be faster than a viewer can follow the fix is
    // FEWER STEPS, not a longer build: merge arrivals until they fit. The build then
    // always occupies the same share of its beat, whatever the frame contains.
    const beatLength = beatMs && beatMs > 400 ? beatMs : DEFAULT_BEAT_MS;
    const budget = Math.max(0, beatLength * BUILD_FRACTION - ENTER_TAIL_MS);
    const followable = Math.max(1, Math.floor(budget / MIN_STEP_MS) + 1);
    const steps = arrivalOrder(root, Math.min(MAX_STEPS, followable));
    const gap = steps.length > 1 ? budget / (steps.length - 1) : 0;

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
function arrivalOrder(root: SVGSVGElement, cap: number = MAX_STEPS): SVGElement[][] {
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
    return merge(ordered, cap);
  }

  // Untagged: one element per step, but never more steps than a viewer can follow —
  // a 20-shape frame animated one shape at a time is a slideshow, not a build.
  const kids = Array.from(root.children).filter(
    (c): c is SVGElement => c instanceof SVGElement && c.tagName.toLowerCase() !== "defs",
  );
  const maxSteps = cap;
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

/**
 * The focus element lands with ONE emphasis and then holds perfectly still.
 *
 * IT USED TO PULSE FOREVER, AND IT READ AS SHAKING. The animation was an infinite
 * scale(1.035) with transform-box: fill-box, which is tolerable on a big rectangle
 * and is not tolerable on text: glyph rasterisation snaps to the pixel grid, so a
 * 3.5% scale applied to a line of type does not look like breathing, it looks like
 * the letters are vibrating. On a code line — the whole point of the "code"
 * template — it was the first thing anyone noticed about the frame, and they
 * noticed it for twelve straight seconds because it never stopped.
 *
 * Two things were wrong and both are fixed by making it one-shot. Infinite motion
 * under a voice that is explaining something competes with the explanation: the eye
 * cannot settle on a thing that will not sit still, which is the opposite of what
 * "send the eye here" is supposed to do. An arrival is enough. It says "this one"
 * at the moment the sentence reaches it, and then it gets out of the way.
 *
 * Scale is also dropped for anything containing text, which is most focus elements
 * — a shape and its own label are always in one group (see layout.group). Those get
 * the emphasis as opacity alone, which no rasteriser can turn into a wobble.
 */
function breathe(el: SVGElement, delay: number): Animation[] {
  if (el.hasAttribute("transform")) return [];

  const holdsText = el.tagName.toLowerCase() === "text" || !!el.querySelector("text");
  if (holdsText) {
    return [el.animate(
      [{ opacity: 0.55 }, { opacity: 1 }],
      { duration: 520, delay: delay + 200, easing: "ease-out", fill: "backwards" },
    )];
  }

  el.style.transformBox = "fill-box";
  el.style.transformOrigin = "center";
  return [el.animate(
    [{ transform: "scale(1)" },
     { transform: "scale(1.045)" },
     { transform: "scale(1)" }],
    { duration: 900, delay: delay + 200, iterations: 1, easing: "ease-in-out" },
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

      // A SPARSE FRAME IS ALLOWED TO COME FORWARD, up to ZOOM_CAP.
      //
      // The short's crop is the UNION of every frame's ink, which is what keeps the
      // scale stable from beat to beat — and it is also why a thin frame is drawn
      // tiny. Measured across six shorts, most frames fill 60-89% of the shared box
      // and the sparse ones collapse: what_is_a_component beat 2 is a one-line code
      // panel filling 25% of it, marooned in white. That is the "the white block
      // seems empty" complaint, and it is arithmetic rather than taste.
      //
      // So the box shrinks toward THIS frame's own ink, but never below
      // shared/ZOOM_CAP. A frame that already fills the union is untouched; a thin
      // one grows until it is reasonable and then stops, so the eye still reads
      // successive beats as one composition at one scale rather than a slideshow
      // that zooms. 1.6 is about the largest step that does not read as a jump.
      // SOLVED FOR HEIGHT, KEEPING THE BOX'S ASPECT — not by scaling both axes by
      // one ratio, which was the first attempt and clipped. Shrinking a 4:3 box by
      // the ratio that fits a tall thin drawing makes the box narrower than the
      // drawing, and the measurement said so: frames came back at 105% and 122% of
      // their crop, meaning the picture was being cut off at the edges.
      //
      // So: pick the smallest height that (a) fits the ink on BOTH axes at this
      // box's aspect ratio and (b) is no less than shared/ZOOM_CAP, then derive the
      // width from it. Containment is arithmetic rather than hope.
      const boxW = x1 - x0, boxH = y1 - y0;
      const aspect = boxW / boxH;
      const needH = Math.max(
        (ink.width + pad * 2) / aspect,   // wide enough once width is derived
        ink.height + pad * 2,             // tall enough on its own
        boxH / ZOOM_CAP,                  // never more than ZOOM_CAP closer in
      );
      if (needH < boxH) {
        const cx = ink.x + ink.width / 2, cy = ink.y + ink.height / 2;
        const hh = needH / 2, hw = (needH * aspect) / 2;
        x0 = cx - hw; x1 = cx + hw;
        y0 = cy - hh; y1 = cy + hh;
      }
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
