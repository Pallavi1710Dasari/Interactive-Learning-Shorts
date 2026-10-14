// The overlap audit: on a drawn frame, which pieces of text collide with
// text from another part of the frame (caption, label, badge, chat row, scene
// object — each tagged data-part in MotionStage), with a drawn character, or
// run off the frame. The player exposes it as window.__motionOverlaps() so a
// headless browser can sweep whole reels (docs/reference/ui-motion-v4).
//
// It measures the page, which a frame itself never does: this is a check run
// beside the player, never part of drawing.

export interface Overlap {
  kind: "text-text" | "text-character" | "text-box" | "off-frame"
    | "caption-character" | "caption-visual" | "caption-overlay" | "caption-unsafe";
  a: string; b: string;
  textA: string; textB: string;
  /** The overlapping area as a share of the smaller text box. */
  share: number;
}

interface Run { part: string; text: string; r: DOMRect }

function opacityOf(el: Element | null, root: Element): number {
  let o = 1;
  for (let e = el; e && e !== root.parentElement; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.display === "none" || cs.visibility === "hidden") return 0;
    o *= Number(cs.opacity);
  }
  return o;
}

/** The rect clipped by every ancestor that hides its overflow. */
function clipped(r: DOMRect, el: Element | null, root: Element): DOMRect | null {
  let x0 = r.left, y0 = r.top, x1 = r.right, y1 = r.bottom;
  for (let e = el; e && e !== root; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.overflow !== "visible" || cs.clipPath !== "none") {
      const c = e.getBoundingClientRect();
      x0 = Math.max(x0, c.left); y0 = Math.max(y0, c.top); x1 = Math.min(x1, c.right); y1 = Math.min(y1, c.bottom);
    }
  }
  return x1 - x0 > 1 && y1 - y0 > 1 ? new DOMRect(x0, y0, x1 - x0, y1 - y0) : null;
}

function inter(a: DOMRect, b: DOMRect): number {
  const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return w > 0 && h > 0 ? w * h : 0;
}

/** Every overlap on the frame under `root` (the 1080 x 1920 frame element). */
export function findOverlaps(root: HTMLElement, minShare = 0.12): Overlap[] {
  const frame = root.getBoundingClientRect();
  const runs: Run[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = (n.textContent ?? "").trim();
    if (!text) continue;
    const el = n.parentElement;
    const owner = el?.closest("[data-part]");
    if (!owner || opacityOf(el, root) < 0.25) continue;
    const cs = el ? getComputedStyle(el) : null;
    if (cs && (cs.color === "transparent" || cs.color === "rgba(0, 0, 0, 0)")) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of Array.from(range.getClientRects())) {
      const c = clipped(r, el, root);
      if (c) runs.push({ part: owner.getAttribute("data-part") ?? "?", text, r: c });
    }
  }
  const out: Overlap[] = [];
  const seen = new Set<string>();
  const add = (o: Overlap) => {
    const k = `${o.kind}|${o.a}|${o.b}|${o.textA}|${o.textB}`;
    if (!seen.has(k)) { seen.add(k); out.push(o); }
  };
  for (let i = 0; i < runs.length; i++) {
    const a = runs[i];
    if (a.r.left < frame.left - 2 || a.r.right > frame.right + 2 || a.r.top < frame.top - 2 || a.r.bottom > frame.bottom + 2) {
      add({ kind: "off-frame", a: a.part, b: "frame", textA: a.text, textB: "", share: 1 });
    }
    for (let j = i + 1; j < runs.length; j++) {
      const b = runs[j];
      if (a.part === b.part) continue;
      const area = inter(a.r, b.r);
      const share = area / Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
      if (share >= minShare) add({ kind: "text-text", a: a.part, b: b.part, textA: a.text, textB: b.text, share: +share.toFixed(2) });
    }
  }
  // text over another part's filled box (a card, a pill, a bubble): boxes
  // with a visible background, smaller than the frame
  const fw = frame.width;
  for (const el of Array.from(root.querySelectorAll("[data-part] *"))) {
    const cs = getComputedStyle(el);
    const filled = (cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent") || cs.backgroundImage !== "none";
    if (!filled || opacityOf(el, root) < 0.25) continue;
    const box = clipped(el.getBoundingClientRect(), el.parentElement, root);
    if (!box || box.width > fw * 0.97 || box.width * box.height < (fw / 1080) ** 2 * 900) continue;
    const owner = el.closest("[data-part]")?.getAttribute("data-part") ?? "?";
    for (const a of runs) {
      if (a.part === owner) continue;
      // a stamp is meant to sit on its card; only text-on-text counts for it
      if (/:stamp$/.test(a.part) && owner.startsWith("obj:")) continue;
      const share = inter(a.r, box) / (a.r.width * a.r.height);
      if (share >= 0.3) add({ kind: "text-box", a: a.part, b: owner, textA: a.text, textB: "", share: +share.toFixed(2) });
    }
  }
  // the drawn characters: their figures, not the whole band they stand in
  for (const fig of Array.from(root.querySelectorAll("[data-character] svg, [data-character] img, canvas[data-character]"))) {
    if (opacityOf(fig, root) < 0.25) continue;
    const f = clipped(fig.getBoundingClientRect(), fig.parentElement, root);
    if (!f) continue;
    // the figure's body: the middle 70 % of its box (the box has air around the
    // drawing); a 3D avatar's canvas is wider than its body: the body stands at
    // data-body-x, about 0.4 of the canvas height wide (the rest is room for a gesture)
    const bx = (fig as HTMLElement).dataset?.bodyX;
    const body = bx !== undefined
      ? new DOMRect(f.left + f.width * Number(bx) - f.height * 0.2, f.top + f.height * 0.05, f.height * 0.4, f.height * 0.95)
      : new DOMRect(f.left + f.width * 0.15, f.top + f.height * 0.05, f.width * 0.7, f.height * 0.95);
    for (const a of runs) {
      const share = inter(a.r, body) / (a.r.width * a.r.height);
      if (share >= minShare) add({ kind: "text-character", a: a.part, b: "character", textA: a.text, textB: "", share: +share.toFixed(2) });
    }
  }
  findCaptionBoxes(root, frame, add);
  return out;
}

/** The caption's BOXES (each chat bubble, the karaoke caption block), not
 * just its text: a bubble may not sit on a character, on the scene's visual
 * or on another overlay, and stays inside the safe zone (6 % sides, above
 * 82 % of the height). */
function findCaptionBoxes(root: HTMLElement, frame: DOMRect, add: (o: Overlap) => void) {
  const k = frame.width / 1080;
  const boxes: { part: string; text: string; r: DOMRect }[] = [];
  for (const el of Array.from(root.querySelectorAll("[data-bubble], [data-part='caption'] > *"))) {
    if (opacityOf(el, root) < 0.25) continue;
    const r = clipped(el.getBoundingClientRect(), el.parentElement, root);
    if (!r || r.width < 4 * k || r.height < 4 * k) continue;
    boxes.push({ part: el.closest("[data-part]")?.getAttribute("data-part") ?? "caption", text: (el.textContent ?? "").trim().slice(0, 40), r });
  }
  if (!boxes.length) return;
  const figures = Array.from(root.querySelectorAll("[data-character] svg, [data-character] img"))
    .filter((f) => opacityOf(f, root) >= 0.25)
    .map((f) => clipped(f.getBoundingClientRect(), f.parentElement, root))
    .filter((f): f is DOMRect => !!f)
    .map((f) => new DOMRect(f.left + f.width * 0.15, f.top + f.height * 0.05, f.width * 0.7, f.height * 0.95));
  const others = Array.from(root.querySelectorAll("[data-part]"))
    .filter((el) => !/^(chat|caption)/.test(el.getAttribute("data-part") ?? "") && opacityOf(el, root) >= 0.25)
    .flatMap((el) => {
      const part = el.getAttribute("data-part") ?? "?";
      // the part's drawn pieces: filled boxes and text, not its full-frame wrapper
      return Array.from(el.querySelectorAll("*")).filter((c) => {
        const cs = getComputedStyle(c);
        const filled = (cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent") || cs.backgroundImage !== "none";
        return filled || (c.childNodes.length === 1 && c.firstChild?.nodeType === Node.TEXT_NODE && (c.textContent ?? "").trim());
      }).map((c) => ({ part, r: clipped(c.getBoundingClientRect(), c.parentElement, root) }))
        .filter((x): x is { part: string; r: DOMRect } => !!x.r && x.r.width < frame.width * 0.97 && x.r.height < frame.height * 0.9);
    });
  const safe = { left: frame.left + 1080 * 0.06 * k - 12 * k, right: frame.right - 1080 * 0.06 * k + 12 * k, bottom: frame.top + 1920 * 0.82 * k };
  for (const b of boxes) {
    for (const f of figures) {
      if (inter(b.r, f) > 0) add({ kind: "caption-character", a: b.part, b: "character", textA: b.text, textB: "", share: +(inter(b.r, f) / (b.r.width * b.r.height)).toFixed(2) });
    }
    for (const o of others) {
      const a = inter(b.r, o.r);
      if (a <= 0) continue;
      const kind = o.part.startsWith("obj:") ? "caption-visual" : "caption-overlay";
      add({ kind, a: b.part, b: o.part, textA: b.text, textB: "", share: +(a / (b.r.width * b.r.height)).toFixed(2) });
    }
    if (b.r.left < safe.left || b.r.right > safe.right || b.r.bottom > safe.bottom) {
      add({ kind: "caption-unsafe", a: b.part, b: "safe zone", textA: b.text, textB: "", share: 1 });
    }
  }
}
