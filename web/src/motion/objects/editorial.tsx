// OBJECT SET 2 — the editorial objects of the second reference reel,
// docs/reference/tokenization-reel.mp4 (REFERENCE_STYLE_ADDENDUM.md 4.5).
// Every one is generic: a TokenRow is tokens, list items, packets or bytes; a
// LookupGrid is a vocabulary, hash buckets, a cache or a page table. Nothing
// here knows about tokenization.
//
// These draw STATE from props. The motion — cascades, scans, scrolls, pops —
// lives in ../animations.tsx, which turns a `t` into these props.

import type { ReactNode } from "react";
import { At, Icon, Overlay } from "../Stage";
import { STEP_CHIP } from "../chrome";
import { C, FONT, H, MONO_ADVANCE, W, display, theme, type FieldName } from "../tokens";
import { clamp, ease, hash3, lerp, seg } from "../time";

// ------------------------------------------------------------------ chips

export type ChipTone = "plain" | "ok" | "bad" | "special" | "key" | "ghost";

export const CHIP = { size: 34, padX: 20, padY: 12, gap: 14, border: 3 } as const;

export function chipWidth(text: string, size: number = CHIP.size): number {
  return text.length * size * MONO_ADVANCE + CHIP.padX * 2 * (size / CHIP.size) + CHIP.border * 2;
}
export function chipHeight(size: number = CHIP.size): number {
  return size * 1.25 + CHIP.padY * 2 * (size / CHIP.size) + CHIP.border * 2;
}

/** Left x of every chip in a row of `texts`, laid out from `x0`. */
export function rowLayout(texts: string[], x0: number, size: number = CHIP.size, gap: number = CHIP.gap): number[] {
  const xs: number[] = [];
  let x = x0;
  for (const t of texts) { xs.push(x); x += chipWidth(t, size) + gap; }
  return xs;
}
export function rowWidth(texts: string[], size: number = CHIP.size, gap: number = CHIP.gap): number {
  return texts.reduce((a, t) => a + chipWidth(t, size), 0) + gap * Math.max(0, texts.length - 1);
}

function chipColors(tone: ChipTone, field: FieldName) {
  const th = theme(field);
  switch (tone) {
    case "ok": return { bg: C.mint, fg: C.white, border: C.mint };
    case "bad": return { bg: th.dark ? "rgba(242,85,90,0.15)" : C.surf, fg: th.dark ? C.white : C.ink, border: C.coral };
    case "special": return { bg: C.special, fg: C.ink, border: C.special };
    case "key": return { bg: C.yellow, fg: C.ink, border: field === "yellow" ? C.ink : C.yellow };
    case "ghost": return { bg: "transparent", fg: th.dim, border: th.dark ? "rgba(255,255,255,0.2)" : "rgba(21,25,54,0.2)" };
    default: return th.dark
      ? { bg: th.surface, fg: C.white, border: "rgba(255,255,255,0.35)" }
      : { bg: C.surf, fg: C.ink, border: C.ink };
  }
}

export function Chip({ text, tone = "plain", field, size = CHIP.size, style }: {
  text: string; tone?: ChipTone; field: FieldName; size?: number; style?: React.CSSProperties;
}) {
  const k = size / CHIP.size;
  const c = chipColors(tone, field);
  return (
    <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", whiteSpace: "pre",
                  height: chipHeight(size), padding: `0 ${CHIP.padX * k}px`, borderRadius: 14 * k,
                  border: `${CHIP.border}px solid ${c.border}`, background: c.bg, color: c.fg,
                  fontFamily: FONT.mono, fontWeight: 700, fontSize: size, boxSizing: "border-box",
                  width: chipWidth(text, size), ...style }}>
      {text}
    </div>
  );
}

/** A YES / NO tag on a chip's top-right corner (match or miss, hit or fault).
 * `flip` 0..1 turns a NO into a YES with a squash, the way scan_window does. */
export function ChipTag({ kind, x, y, p = 1, flip = 0 }: {
  kind: "yes" | "no"; x: number; y: number; p?: number; flip?: number;
}) {
  const yes = kind === "yes" || flip >= 0.5;
  const squash = flip > 0 && flip < 1 ? Math.abs(Math.cos(Math.PI * flip)) : 1;
  const q = ease.outBack(clamp(p), 2);
  return (
    <At x={x} y={y} center style={{ opacity: clamp(p * 2), transform: `translate(-50%,-50%) scale(${q}, ${q * squash})` }}>
      <div style={{ padding: "4px 14px", borderRadius: 10, background: yes ? C.mint : C.coral, color: C.white,
                    fontFamily: FONT.mono, fontWeight: 700, fontSize: 24, letterSpacing: 1 }}>
        {yes ? "YES" : "NO"}
      </div>
    </At>
  );
}

export interface RowItem { text: string; tone?: ChipTone }

/** A row of chips at fixed positions. `xs` overrides the computed layout
 * (chip_insert interpolates between two layouts); `alpha` fades items. */
export function TokenRow({ items, x, y, field, size = CHIP.size, xs, alpha, center = false }: {
  items: RowItem[]; x: number; y: number; field: FieldName; size?: number;
  xs?: number[]; alpha?: number[]; center?: boolean;
}) {
  const texts = items.map((i) => i.text);
  const x0 = center ? x - rowWidth(texts, size) / 2 : x;
  const pos = xs ?? rowLayout(texts, x0, size);
  return (
    <>
      {items.map((it, i) => (
        <At key={`${i}-${it.text}`} x={pos[i]} y={y} style={{ opacity: alpha ? alpha[i] : 1 }}>
          <Chip text={it.text} tone={it.tone} field={field} size={size} />
        </At>
      ))}
    </>
  );
}

// ------------------------------------------------------------------ titles

export interface TitleWord { text: string; accent?: boolean; color?: string }

/** Hooks and takeaways in display caps, revealed word by word: each word
 * rises and fades in at start + i * gap. */
export function KineticTitle({ lines, x, y, size, t, start = 0, gap = 0.12, field, lineHeight = 0.92 }: {
  lines: TitleWord[][]; x: number; y: number; size: number; t: number; start?: number; gap?: number;
  field: FieldName; lineHeight?: number;
}) {
  const th = theme(field);
  let i = 0;
  return (
    <At x={x} y={y}>
      <div style={{ ...display(size), lineHeight, color: th.ink }}>
        {lines.map((line, li) => (
          <div key={li} style={{ whiteSpace: "nowrap" }}>
            {line.map((w, wi) => {
              const p = ease.outCubic(seg(t, start + gap * i++, 0.22));
              return (
                <span key={wi} style={{ display: "inline-block", marginRight: size * 0.22, opacity: p,
                                        transform: `translateY(${(1 - p) * size * 0.35}px)`,
                                        color: w.color ?? (w.accent ? th.accent : undefined),
                                        textShadow: w.accent ? "var(--motion-glow, none)" : undefined }}>
                  {w.text}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </At>
  );
}

// ------------------------------------------------------------- chapter card

export const CHAPTER_CARD = {
  numberX: 54, numberY: 330, numberSize: 420,
  labelY: 300, titleY: 790, titleSize: 64,
  /** Entrance (addendum 4.6 B): number 0-0.5 s, title 0.5-0.9 s, label
   * 0.9-1.1 s, hold, then exitAt -> exitAt + FLY: the number flies into the
   * step chip (findings 8.2). */
  numberIn: 0.5, titleAt: 0.5, titleDur: 0.4, labelAt: 0.9, labelDur: 0.2, exitAt: 2.6, fly: 0.45,
} as const;

/** "STEP 3 OF 4", the giant number and a one-line title on a full field.
 * After exitAt the number shrinks and flies to the step chip's number slot;
 * draw <StepChip hideNumber={t < exitAt + fly}> beside it to complete the
 * hand-off. */
export function ChapterCard({ n, of, title, field, t, exitAt = CHAPTER_CARD.exitAt, titleMode = "type" }: {
  n: number; of: number; title: string; field: FieldName; t: number; exitAt?: number; titleMode?: "type" | "fade";
}) {
  const th = theme(field);
  const k = CHAPTER_CARD;
  const inP = ease.outCubic(seg(t, 0, k.numberIn));
  const fly = ease.inOutCubic(seg(t, exitAt, k.fly));
  const restOut = 1 - seg(t, exitAt, k.fly * 0.6);
  const titleP = seg(t, k.titleAt, k.titleDur);
  const shownTitle = titleMode === "type" ? title.slice(0, Math.round(title.length * titleP)) : title;
  const size = lerp(k.numberSize, STEP_CHIP.numberSize, fly);
  const nx = lerp(k.numberX, STEP_CHIP.numberX, fly);
  // The display face's cap height sits ~0.12 em below its box top.
  const ny = lerp(k.numberY, STEP_CHIP.numberY + STEP_CHIP.y - STEP_CHIP.numberSize * 0.12, fly);
  const done = t >= exitAt + k.fly;
  return (
    <>
      <At x={k.numberX} y={k.labelY} style={{ opacity: seg(t, k.labelAt, k.labelDur) * restOut }}>
        <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 27, letterSpacing: 5.4, color: th.ink }}>
          STEP {n} OF {of}
        </div>
      </At>
      {!done && (
        <At x={nx} y={ny} style={{ opacity: lerp(0.2, 1, inP),
                                   transform: `scale(${fly > 0 ? 1 : lerp(0.92, 1, inP)})`, transformOrigin: "0 0" }}>
          <div style={{ ...display(size), lineHeight: 1, color: th.accent }}>
            {String(n).padStart(2, "0")}
          </div>
        </At>
      )}
      <At x={k.numberX + 6} y={k.titleY} style={{ opacity: (titleMode === "fade" ? titleP : 1) * restOut }}>
        <div style={{ fontWeight: 800, fontSize: k.titleSize, color: th.ink, whiteSpace: "nowrap" }}>
          {shownTitle}
          {titleMode === "type" && titleP > 0 && titleP < 1 && <span style={{ opacity: 0.6 }}>|</span>}
        </div>
      </At>
    </>
  );
}

// ------------------------------------------------------------------ stamp

/** One strong verdict per reel ("NOT ON THE SHELF"). `p` 0..1 is the slam:
 * from 1.7x down past 1 (overshoot) and a small shake once it lands. */
export function Stamp({ text, x, y, rotate = -8, p, t = 0, size = 84 }: {
  text: string; x: number; y: number; rotate?: number; p: number; t?: number; size?: number;
}) {
  const q = clamp(p);
  const scale = q < 0.6 ? lerp(1.7, 0.94, ease.inCubic(q / 0.6)) : lerp(0.94, 1, ease.outCubic((q - 0.6) / 0.4));
  const shake = q >= 0.6 && q < 1 ? Math.sin(t * 90) * 6 * (1 - q) : 0;
  return (
    // At centres it (and composes this transform after its own centring): a
    // second translate(-50%,-50%) here put every stamp half its size up and
    // left of its anchor — onto the card text it was meant to sit beside
    <At x={x} y={y} center style={{ opacity: clamp(q * 3),
                                    transform: `translateX(${shake}px) rotate(${rotate}deg) scale(${scale})` }}>
      <div style={{ padding: "14px 36px", border: `7px solid ${C.coral}`, borderRadius: 18, color: C.coral,
                    ...display(size), lineHeight: 1, whiteSpace: "nowrap",
                    background: "rgba(242,85,90,0.12)" }}>
        {text}
      </div>
    </At>
  );
}

// ------------------------------------------------------------ lookup grid

export interface GridState {
  /** 0..1 per cell — how far in it is (grid_cascade). Default all 1. */
  reveal?: (i: number) => number;
  /** cell index -> tone, for highlighted cells. */
  tone?: (i: number) => ChipTone | null;
  /** 0..1, how dim everything not highlighted is. */
  dimRest?: number;
}

/** A grid of cells — vocabularies, hash buckets, caches, page tables. At most
 * `readable` cells (default 12, addendum section 5) are drawn at full
 * strength; the rest are faded texture, so a phone screen never shows 20+
 * tiny unreadable cells. */
export function LookupGrid({ cells, cols, x, y, w, cellH = 66, gap = 12, field, readable, state = {},
                             scale = 1, origin }: {
  cells: string[]; cols: number; x: number; y: number; w: number; cellH?: number; gap?: number;
  field: FieldName; readable?: number[]; state?: GridState; scale?: number; origin?: [number, number];
}) {
  const th = theme(field);
  const cw = (w - gap * (cols - 1)) / cols;
  const sharp = new Set(readable ?? cells.map((_, i) => i).slice(0, 12));
  const ox = origin ? origin[0] - x : w / 2;
  const oy = origin ? origin[1] - y : 0;
  return (
    <At x={x} y={y} style={{ transform: `scale(${scale})`, transformOrigin: `${ox}px ${oy}px` }}>
      {cells.map((text, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        const r = state.reveal ? state.reveal(i) : 1;
        if (r <= 0) return null;
        const tone = state.tone ? state.tone(i) : null;
        const isSharp = sharp.has(i) || tone !== null;
        const dim = tone === null ? 1 - 0.75 * (state.dimRest ?? 0) : 1;
        const c = chipColors(tone ?? "plain", field);
        return (
          <div key={i} style={{
            position: "absolute", left: col * (cw + gap), top: row * (cellH + gap), width: cw, height: cellH,
            borderRadius: 12, display: "grid", placeItems: "center", overflow: "hidden",
            background: tone ? c.bg : th.dark ? "rgba(255,255,255,0.06)" : "rgba(21,25,54,0.05)",
            border: `2px solid ${tone ? c.border : th.dark ? "rgba(255,255,255,0.12)" : "rgba(21,25,54,0.1)"}`,
            color: tone ? c.fg : th.ink, fontFamily: FONT.mono, fontWeight: 600,
            fontSize: isSharp ? Math.min(30, cellH * 0.42) : Math.min(20, cellH * 0.3),
            opacity: ease.outCubic(r) * (isSharp ? 1 : 0.32) * dim,
            transform: `scale(${lerp(0.6, 1, ease.outBack(r, 1.4))})`,
          }}>
            {text}
          </div>
        );
      })}
    </At>
  );
}

/** Where cell i's centre is, for a grid laid out as LookupGrid lays it out. */
export function gridCellCenter(i: number, cols: number, x: number, y: number, w: number,
                               cellH = 66, gap = 12): [number, number] {
  const cw = (w - gap * (cols - 1)) / cols;
  return [x + (i % cols) * (cw + gap) + cw / 2, y + Math.floor(i / cols) * (cellH + gap) + cellH / 2];
}

/** The search bar over a LookupGrid: `typed` characters of `query`. */
export function SearchBar({ query, typed, x, y, w, field, p = 1, found }: {
  query: string; typed: number; x: number; y: number; w: number; field: FieldName; p?: number; found?: boolean | null;
}) {
  const th = theme(field);
  const shown = query.slice(0, Math.round(clamp(typed) * query.length));
  return (
    <At x={x} y={y} style={{ opacity: clamp(p), transform: `translateY(${(1 - clamp(p)) * -16}px)` }}>
      <div style={{ width: w, height: 96, borderRadius: 48, background: C.surf, display: "flex", alignItems: "center",
                    gap: 24, padding: "0 36px", boxShadow: th.dark ? "0 18px 40px rgba(0,0,0,0.4)" : "0 18px 40px rgba(21,25,54,0.15)",
                    border: found === false ? `4px solid ${C.coral}` : found ? `4px solid ${C.mint}` : "4px solid transparent" }}>
        <Icon name="search" size={42} color={C.ink} stroke={2.6} />
        <span style={{ fontFamily: FONT.mono, fontWeight: 600, fontSize: 38, color: C.ink, whiteSpace: "pre" }}>{shown}</span>
      </div>
    </At>
  );
}

// ------------------------------------------------------------ lookup table

/** A key -> value table with a highlighted middle row. `offset` is the
 * (fractional) row index centred in the window — slot_scroll animates it. */
export function LookupTable({ header, rows, offset, x, y, w, field, visible = 5, rowH = 78, highlight = 1 }: {
  header: [string, string]; rows: [string, string][]; offset: number; x: number; y: number; w: number;
  field: FieldName; visible?: number; rowH?: number; highlight?: number;
}) {
  const th = theme(field);
  const mid = Math.floor(visible / 2);
  const winH = visible * rowH;
  return (
    <At x={x} y={y}>
      <div style={{ width: w, borderRadius: 30, background: th.surface, border: `5px solid ${C.ink}`, padding: "18px 36px 24px",
                    color: th.surfaceInk, boxSizing: "border-box" }}>
        <div style={{ display: "flex", fontFamily: FONT.mono, fontSize: 22, letterSpacing: 3, color: th.surfaceDim, marginBottom: 12 }}>
          <span style={{ width: "38%" }}>{header[0]}</span><span>{header[1]}</span>
        </div>
        <div style={{ position: "relative", height: winH, overflow: "hidden" }}>
          <div style={{ position: "absolute", left: -12, right: -12, top: mid * rowH + 4, height: rowH - 8, borderRadius: 14,
                        border: `4px solid ${FIELDS_BLUE}`, opacity: clamp(highlight), background: "rgba(40,62,230,0.08)" }} />
          {rows.map(([k, v], i) => {
            const top = (i - offset + mid) * rowH;
            if (top < -rowH || top > winH) return null;
            return (
              <div key={i} style={{ position: "absolute", left: 0, right: 0, top, height: rowH, display: "flex", alignItems: "center",
                                    fontFamily: FONT.mono, fontWeight: 600, fontSize: 34 }}>
                <span style={{ width: "38%" }}>{k}</span><span>{v}</span>
              </div>
            );
          })}
        </div>
      </div>
    </At>
  );
}
const FIELDS_BLUE = "#283EE6";

// ------------------------------------------------------------ matrix grid

export type CellTone = "plain" | "key" | "special" | "pad" | "ok" | "bad" | "empty";
export interface MatrixCell { text?: string; tone: CellTone }

/** A rows x cols grid of cells — batches, matrices, memory frames, bitmaps.
 * Optional row labels and a bracket on the left; `reveal(r, c)` 0..1. */
export function MatrixGrid({ cells, x, y, cell = 78, gap = 10, field, rowLabels, bracket = false, label, reveal }: {
  cells: MatrixCell[][]; x: number; y: number; cell?: number; gap?: number; field: FieldName;
  rowLabels?: string[]; bracket?: boolean; label?: string; reveal?: (r: number, c: number) => number;
}) {
  const th = theme(field);
  const rows = cells.length;
  const h = rows * cell + (rows - 1) * gap;
  const lx = rowLabels ? 70 : 0;
  const bx = bracket ? 30 : 0;
  return (
    <At x={x} y={y}>
      {label && <div style={{ position: "absolute", left: lx + bx, top: -60, ...display(40),
                             color: th.dark ? C.yellow : FIELDS_BLUE,
                             whiteSpace: "nowrap" }}>{label}</div>}
      {rowLabels?.map((l, r) => (
        <div key={l} style={{ position: "absolute", left: 0, top: r * (cell + gap) + cell / 2 - 14, fontFamily: FONT.mono,
                              fontSize: 24, fontWeight: 700, color: th.dark ? "rgba(255,255,255,0.7)" : C.sub }}>{l}</div>
      ))}
      {bracket && <div style={{ position: "absolute", left: lx, top: -8, width: 18, height: h + 16, borderLeft: `6px solid ${FIELDS_BLUE}`,
                                borderTop: `6px solid ${FIELDS_BLUE}`, borderBottom: `6px solid ${FIELDS_BLUE}`, borderRadius: "6px 0 0 6px" }} />}
      {cells.map((row, r) => row.map((c, ci) => {
        const p = reveal ? reveal(r, ci) : 1;
        if (p <= 0 || c.tone === "empty") return null;
        const look = matrixLook(c.tone, field);
        return (
          <div key={`${r}-${ci}`} style={{
            position: "absolute", left: lx + bx + ci * (cell + gap), top: r * (cell + gap), width: cell, height: cell,
            borderRadius: 14, background: look.bg, border: `4px ${c.tone === "pad" ? "dashed" : "solid"} ${look.border}`,
            color: look.fg, display: "grid", placeItems: "center", fontFamily: FONT.mono, fontWeight: 700,
            fontSize: c.text && c.text.length > 2 ? cell * 0.24 : cell * 0.36, boxSizing: "border-box",
            opacity: ease.outCubic(clamp(p)), transform: `scale(${lerp(0.7, 1, ease.outBack(clamp(p), 1.5))})`,
          }}>{c.text ?? ""}</div>
        );
      }))}
    </At>
  );
}

function matrixLook(tone: CellTone, field: FieldName) {
  const th = theme(field);
  switch (tone) {
    case "key": return { bg: C.yellow, fg: C.ink, border: C.ink };
    case "special": return { bg: C.special, fg: C.ink, border: C.ink };
    case "pad": return { bg: "transparent", fg: th.dark ? "rgba(255,255,255,0.4)" : C.grey, border: th.dark ? "rgba(255,255,255,0.3)" : C.grey };
    case "ok": return { bg: C.mintSoft, fg: "#0E7D56", border: C.mint };
    case "bad": return { bg: C.coralSoft, fg: C.coral, border: C.coral };
    default: return { bg: th.dark ? th.surface : C.surf, fg: th.surfaceInk, border: th.dark ? "rgba(255,255,255,0.4)" : C.ink };
  }
}

// ------------------------------------------------------------- big counter

/** The result of a step: a big number, a small label under it. `framed`
 * draws the rounded frame count_up uses. */
export function BigCounter({ value, label, x, y, size = 300, field, accent = true, framed = false, p = 1, center = true }: {
  value: string; label?: string; x: number; y: number; size?: number; field: FieldName; accent?: boolean;
  framed?: boolean; p?: number; center?: boolean;
}) {
  const th = theme(field);
  const q = ease.outBack(clamp(p), 1.6);
  return (
    // At centres it already: a second translate(-50%,-50%) here put the
    // counter half its size up and left — "1 → 7" ran off the frame
    <At x={x} y={y} center={center} style={{ opacity: clamp(p * 2), transform: `scale(${lerp(0.7, 1, q)})` }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center",
                    padding: framed ? "24px 54px 30px" : 0, borderRadius: 36,
                    border: framed ? `4px solid ${th.dark ? "rgba(253,209,62,0.55)" : "rgba(21,25,54,0.25)"}` : "none",
                    background: framed ? (th.dark ? "rgba(9,16,37,0.85)" : "rgba(255,255,255,0.85)") : "transparent" }}>
        <div style={{ ...display(size), lineHeight: 1, color: accent ? th.accent : th.ink,
                      whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>{value}</div>
        {label && <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: Math.max(22, size * 0.09), letterSpacing: 4,
                               color: th.ink, marginTop: 8, textTransform: "uppercase", whiteSpace: "nowrap" }}>{label}</div>}
      </div>
    </At>
  );
}

// ------------------------------------------------------- bracket, callout

/** A bracket under (or over) part of a row, with a label: "SUMMARY SEAT". */
export function Bracket({ x, y, w, label, field, p = 1, below = true }: {
  x: number; y: number; w: number; label: string; field: FieldName; p?: number; below?: boolean;
}) {
  const th = theme(field);
  const q = ease.outCubic(clamp(p));
  const col = th.dark ? C.yellow : FIELDS_BLUE;
  return (
    <At x={x} y={y} style={{ opacity: q }}>
      <div style={{ width: w * q, height: 18, borderLeft: `5px solid ${col}`, borderRight: `5px solid ${col}`,
                    [below ? "borderBottom" : "borderTop"]: `5px solid ${col}`, boxSizing: "border-box" } as React.CSSProperties} />
      <div style={{ position: "absolute", left: 0, top: below ? 28 : -40, fontFamily: FONT.mono, fontWeight: 700, fontSize: 22,
                    letterSpacing: 3, color: col, whiteSpace: "nowrap" }}>{label}</div>
    </At>
  );
}

/** A speech-bubble callout with a small label and a pointer down to (px, py). */
export function Callout({ x, y, w, label, text, px, py, field, p = 1, tag, scale = 1 }: {
  x: number; y: number; w: number; label: string; text: string; px: number; py: number;
  field: FieldName; p?: number; tag?: { text: string; tone: "ok" | "bad" }; scale?: number;
}) {
  const q = ease.outBack(clamp(p), 1.3);
  // Midnight Lab: a glass bubble with a lit edge instead of the paper one
  const th = theme(field);
  const lab = field === "lab" || field === "lab_violet";
  // (solid, not see-through: the pointer line runs behind the bubble)
  const box = lab ? { background: field === "lab" ? "#1A2152" : "#221D57", border: "3px solid rgba(255,255,255,0.22)", color: th.surfaceInk, sub: th.surfaceDim }
                  : { background: C.surf, border: `4px solid ${C.ink}`, color: C.ink, sub: C.sub };
  return (
    <>
      <Overlay>
        <line x1={x + 60} y1={y + 120} x2={px} y2={py} stroke={th.dark ? C.white : C.ink} strokeWidth={4}
              opacity={clamp(p)} />
      </Overlay>
      <At x={x} y={y} style={{ opacity: clamp(p * 2), transform: `scale(${lerp(0.85, 1, q)})`, transformOrigin: "0 100%" }}>
        <div style={{ width: w, padding: "20px 30px", borderRadius: 24, background: box.background, border: box.border, color: box.color }}>
          <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 20 * scale, letterSpacing: 3, color: box.sub }}>{label}</div>
          <div style={{ fontWeight: 700, fontSize: 36 * scale, lineHeight: 1.25 }}>{text}</div>
        </div>
        {tag && <div style={{ position: "absolute", right: -24, bottom: -24, padding: "6px 18px", borderRadius: 12,
                              background: tag.tone === "ok" ? C.mint : C.coral, color: C.white, ...display(36), transform: "rotate(-6deg)" }}>{tag.text}</div>}
      </At>
    </>
  );
}

// -------------------------------------------------------------- recap grid

/** The walkthrough recap: the concept, "in N steps", a numbered 2-column grid
 * of chapter titles, and the example's final state underneath. */
export function RecapGrid({ concept, steps, final, field, t }: {
  concept: string; steps: string[]; final: RowItem[]; field: FieldName; t: number;
}) {
  const th = theme(field);
  const colW = 450;
  return (
    <>
      <At x={W / 2} y={560} center style={{ opacity: ease.outCubic(seg(t, 0, 0.4)) }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ ...display(132), lineHeight: 1, color: th.ink,
                        whiteSpace: "nowrap" }}>{concept}</div>
          <div style={{ fontWeight: 800, fontSize: 44, color: th.accent, marginTop: 16 }}>in {steps.length} steps</div>
        </div>
      </At>
      {steps.map((s, i) => {
        const p = ease.outCubic(seg(t, 0.4 + i * 0.12, 0.3));
        return (
          <At key={s} x={W / 2 - colW - 12 + (i % 2) * (colW + 24)} y={760 + Math.floor(i / 2) * 120}
              style={{ opacity: p, transform: `translateY(${(1 - p) * 24}px)` }}>
            <div style={{ width: colW, height: 96, borderRadius: 18, border: `3px solid ${th.dark ? "rgba(255,255,255,0.3)" : C.ink}`,
                          display: "flex", alignItems: "center", gap: 18, padding: "0 24px", boxSizing: "border-box",
                          background: th.dark ? th.surface : C.surf, color: th.surfaceInk }}>
              <span style={{ ...display(48), color: th.accent }}>{i + 1}</span>
              <span style={{ fontWeight: 700, fontSize: 32, whiteSpace: "nowrap", overflow: "hidden" }}>{s}</span>
            </div>
          </At>
        );
      })}
      <div style={{ opacity: ease.outCubic(seg(t, 0.5 + steps.length * 0.12, 0.4)) }}>
        <TokenRow items={final} x={W / 2} y={790 + Math.ceil(steps.length / 2) * 120} field={field} size={28} center />
      </div>
    </>
  );
}

// ---------------------------------------------------------- texture (hook)

/** Falling columns of digits behind the hook — decorative, low contrast,
 * hook only. Pure in t: each column's offset is t * its speed. */
export function TextureBackground({ t, field, seed = 7, opacity = 1 }: {
  t: number; field: FieldName; seed?: number; opacity?: number;
}) {
  const th = theme(field);
  const cols = 16;
  const rowH = 64;
  const nodes: ReactNode[] = [];
  for (let c = 0; c < cols; c++) {
    const speed = 60 + hash3(seed, c) * 110;
    const off = (t * speed + hash3(seed, c, 1) * H) % rowH;
    const first = Math.floor((t * speed + hash3(seed, c, 1) * H) / rowH);
    for (let r = -1; r < H / rowH + 1; r++) {
      const k = r - first;
      const d = Math.floor(hash3(seed, c, k) * 10);
      // brighter near the vertical centre, the way the reference glows
      const y = r * rowH + off;
      const centre = 1 - Math.min(1, Math.abs(y - H * 0.32) / (H * 0.38));
      const vis = hash3(seed + 1, c, k) > 0.35 ? 1 : 0;
      nodes.push(
        <text key={`${c}-${r}`} x={36 + c * 66} y={y} fontFamily={FONT.mono} fontSize={34} fontWeight={600}
              fill={th.dark ? C.white : C.ink} opacity={vis * (0.06 + 0.5 * centre * centre)}>{d}</text>,
      );
    }
  }
  return <svg width={W} height={H} style={{ position: "absolute", inset: 0, opacity }}>{nodes}</svg>;
}
