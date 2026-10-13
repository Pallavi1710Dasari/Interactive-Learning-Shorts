// In-shot animations — REFERENCE_STYLE_ADDENDUM.md 4.6 C (13), plus count_up
// (the 14th) and the moves findings 8.2 adds: category highlight, zoom into
// a cell, and the scan line. Each is a time-driven component: `t` is seconds
// since the animation started, and nothing else moves it.
//
// They are generic. ScanWindow matches pieces of any word against any row;
// SlotScroll stops any table on any row; CountUp counts to any number.

import type { ReactNode } from "react";
import { At, Overlay } from "./Stage";
import { C, FONT, MONO_ADVANCE, W, display, theme, type FieldName } from "./tokens";
import { clamp, ease, hash3, lerp, pathD, pointAt, polylineLength, seg, type Pt } from "./time";
import {
  BigCounter, Chip, ChipTag, LookupGrid, LookupTable, SearchBar, Stamp, TokenRow,
  chipHeight, chipWidth, gridCellCenter, rowLayout, rowWidth, type ChipTone, type RowItem,
} from "./objects/editorial";

// ------------------------------------------------------------ 1 text_scramble

const SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

/** Random characters settle letter by letter into the real word
 * ("NUM9351" -> "NUMBERS"). Letter i settles at start + dur * (i+1)/n. */
export function TextScramble({ text, t, x, y, size, field, start = 0, dur = 0.8, seed = 11, center = false }: {
  text: string; t: number; x: number; y: number; size: number; field: FieldName;
  start?: number; dur?: number; seed?: number; center?: boolean;
}) {
  const th = theme(field);
  const tick = Math.floor(t * 15);
  const n = text.length;
  const allDone = t >= start + dur;
  return (
    <At x={x} y={y} center={center}>
      <div style={{ ...display(size), lineHeight: 1, whiteSpace: "pre",
                    color: allDone ? th.accent : th.dark ? "rgba(253,209,62,0.6)" : "rgba(40,62,230,0.6)" }}>
        {text.split("").map((ch, i) => {
          const settled = t >= start + (dur * (i + 1)) / n || ch === " ";
          const r = SCRAMBLE_CHARS[Math.floor(hash3(seed, i, tick) * SCRAMBLE_CHARS.length)];
          return <span key={i} style={{ color: settled ? th.accent : undefined }}>{settled ? ch : r}</span>;
        })}
      </div>
    </At>
  );
}

// ------------------------------------------------------------ 2 type_assemble

export const ASSEMBLE = { gap: 0.07, letter: 0.25, underline: 0.35 } as const;

/** Letters slide in one by one to build a word in display type, then an
 * underline draws in under it. */
export function TypeAssemble({ text, t, x, y, size, field, center = true }: {
  text: string; t: number; x: number; y: number; size: number; field: FieldName; center?: boolean;
}) {
  const th = theme(field);
  const n = text.length;
  const ul = ease.inOutCubic(seg(t, n * ASSEMBLE.gap + 0.1, ASSEMBLE.underline));
  return (
    <At x={x} y={y} center={center}>
      <div style={{ position: "relative", ...display(size), lineHeight: 1, whiteSpace: "pre",
 color: th.ink }}>
        {text.split("").map((ch, i) => {
          const p = ease.outBack(seg(t, i * ASSEMBLE.gap, ASSEMBLE.letter), 1.4);
          return (
            <span key={i} style={{ display: "inline-block", opacity: clamp(p * 1.5),
                                   transform: `translate(${(1 - p) * size * 0.3}px, ${(1 - p) * -size * 0.45}px) rotate(${(1 - p) * 14}deg)` }}>
              {ch}
            </span>
          );
        })}
        <div style={{ position: "absolute", left: 0, bottom: -size * 0.12, height: Math.max(6, size * 0.05),
                      width: `${ul * 100}%`, background: th.accent, borderRadius: 4 }} />
      </div>
    </At>
  );
}

// --------------------------------------------------------------- 3 arrow_draw

/** An arrow stroke draws from the start to the end of its path; the head
 * appears as the stroke arrives. */
export function ArrowDraw({ points, t, start = 0, dur = 0.45, color, width = 9, head = 28 }: {
  points: Pt[]; t: number; start?: number; dur?: number; color: string; width?: number; head?: number;
}) {
  const p = ease.inOutCubic(seg(t, start, dur));
  const L = polylineLength(points);
  const tip = pointAt(points, p);
  const prev = pointAt(points, Math.max(0, p - 0.02));
  const ang = Math.atan2(tip[1] - prev[1], tip[0] - prev[0]);
  const hp = clamp((p - 0.75) / 0.25);
  const a1: Pt = [tip[0] - head * Math.cos(ang - 0.5), tip[1] - head * Math.sin(ang - 0.5)];
  const a2: Pt = [tip[0] - head * Math.cos(ang + 0.5), tip[1] - head * Math.sin(ang + 0.5)];
  return (
    <Overlay>
      <path d={pathD(points)} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round"
            strokeDasharray={`${L} ${L}`} strokeDashoffset={L * (1 - p)} />
      {p > 0 && <path d={pathD([a1, tip, a2])} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round"
                      strokeLinejoin="round" opacity={hp} />}
    </Overlay>
  );
}

// -------------------------------------------------------- 4 typewriter_cursor

/** A blinking cursor types the text at `cps` characters a second; solid
 * while typing, blinking once 1 s after it stops. */
export function TypewriterCursor({ text, t, x, y, size, field, cps = 14, mono = true, color }: {
  text: string; t: number; x: number; y: number; size: number; field: FieldName; cps?: number; mono?: boolean; color?: string;
}) {
  const th = theme(field);
  const n = Math.max(0, Math.min(text.length, Math.floor(t * cps)));
  const typingEnd = text.length / cps;
  const on = t < typingEnd ? true : Math.floor((t - typingEnd) * 2) % 2 === 0;
  return (
    <At x={x} y={y}>
      <div style={{ fontFamily: mono ? FONT.mono : FONT.body, fontWeight: mono ? 600 : 800, fontSize: size, lineHeight: 1.2,
                    color: color ?? th.ink, whiteSpace: "pre", display: "flex", alignItems: "center" }}>
        {text.slice(0, n)}
        <span style={{ display: "inline-block", width: size * 0.08, height: size * 1.05, marginLeft: size * 0.06,
                       background: th.dark ? C.yellow : C.coral, opacity: on ? 1 : 0 }} />
      </div>
    </At>
  );
}

// ------------------------------------------------------------ 5 grid_cascade

export interface GridSpec {
  cells: string[]; cols: number; x: number; y: number; w: number; cellH?: number; gap?: number; readable?: number[];
}

/** Grid tiles flow in column by column with a slight zoom-out, so the grid
 * grows denser to show scale. */
export function GridCascade({ grid, t, field, colGap = 0.06, dur = 0.32, zoomFrom = 1.18, toneOf, dimRest = 0 }: {
  grid: GridSpec; t: number; field: FieldName; colGap?: number; dur?: number; zoomFrom?: number;
  toneOf?: (i: number) => ChipTone | null; dimRest?: number;
}) {
  const total = grid.cols * colGap + dur;
  const zoom = lerp(zoomFrom, 1, ease.outCubic(seg(t, 0, total + 0.3)));
  return (
    <LookupGrid {...grid} field={field} scale={zoom}
                state={{ reveal: (i) => seg(t, (i % grid.cols) * colGap + Math.floor(i / grid.cols) * 0.012, dur),
                         tone: toneOf, dimRest }} />
  );
}

// ------------------------------------------------------------- 6 scan_window

export interface ScanPiece { len: number; label: string; tone?: ChipTone; target?: Pt }

export const SCAN = { step: 0.22, flip: 0.2, connect: 0.35, drop: 0.35, hold: 0.25 } as const;

/** The schedule of a scan: for each piece, when its shrink starts, how many
 * shrink steps it takes, and when its flip, connector and drop happen. */
export function scanSchedule(word: string, pieces: ScanPiece[]) {
  const out: { start: number; steps: number; flipAt: number; connectAt: number; dropAt: number; end: number; from: number }[] = [];
  let at = 0, consumed = 0;
  for (const pc of pieces) {
    const steps = Math.max(0, word.length - consumed - pc.len);
    const flipAt = at + SCAN.hold + steps * SCAN.step;
    const connectAt = flipAt + SCAN.flip;
    const dropAt = connectAt + SCAN.connect;
    const end = dropAt + SCAN.drop;
    out.push({ start: at, steps, flipAt, connectAt, dropAt, end, from: consumed });
    at = end + 0.1;
    consumed += pc.len;
  }
  return out;
}

/** A selection box sits over the rest of a word with a NO tag and shrinks
 * from the right until it matches a piece; the tag flips to a mint YES, a
 * connector draws to the matching item, and the piece drops to the result
 * row. Then the next piece, from what is left. */
export function ScanWindow({ word, pieces, t, x, y, size, field, resultY }: {
  word: string; pieces: ScanPiece[]; t: number; x: number; y: number; size: number; field: FieldName; resultY: number;
}) {
  const th = theme(field);
  const cw = size * MONO_ADVANCE;
  const sched = scanSchedule(word, pieces);
  const k = sched.findIndex((s) => t < s.end + 0.1);
  const cur = k === -1 ? sched.length - 1 : k;
  const s = sched[cur];
  const pc = pieces[cur];
  const remaining = word.length - s.from;
  const stepsDone = Math.min(s.steps, Math.max(0, Math.floor((t - s.start - SCAN.hold) / SCAN.step) + 1));
  const boxLen = t < s.start + SCAN.hold ? remaining : remaining - stepsDone;
  const flip = seg(t, s.flipAt, SCAN.flip);
  const boxX = x + s.from * cw - 14;
  const boxW = boxLen * cw + 28;
  const consumed = (i: number) => sched.findIndex((q, j) => i >= q.from && i < q.from + pieces[j].len && t >= q.dropAt);
  const results: RowItem[] = [];
  const alphas: number[] = [];
  sched.forEach((q, j) => {
    const d = seg(t, q.dropAt, SCAN.drop);
    if (d > 0) { results.push({ text: pieces[j].label, tone: "plain" }); alphas.push(d); }
  });
  const box = (
    <div style={{ position: "absolute", left: boxX, top: y - 18, width: boxW, height: size * 1.25 + 36, borderRadius: 18,
                  border: `5px solid ${flip >= 0.5 ? C.mint : C.coral}`, boxSizing: "border-box",
                  background: flip >= 0.5 ? "rgba(23,178,123,0.10)" : "rgba(242,85,90,0.06)" }} />
  );
  const conn = pc.target && t >= s.connectAt
    ? <ConnectorCurve from={[boxX + 30, y - 18]} to={pc.target} p={seg(t, s.connectAt, SCAN.connect)} />
    : null;
  // Connectors of earlier pieces stay drawn.
  const prevConns = sched.slice(0, cur).map((q, j) => pieces[j].target
    ? <ConnectorCurve key={j} from={[x + q.from * cw + 16, y - 18]} to={pieces[j].target!} p={1} /> : null);
  return (
    <>
      {prevConns}
      {conn}
      {box}
      <At x={x} y={y}>
        <div style={{ fontFamily: FONT.mono, fontWeight: 600, fontSize: size, lineHeight: 1.25, whiteSpace: "pre", color: th.ink }}>
          {word.split("").map((ch, i) => <span key={i} style={{ opacity: consumed(i) >= 0 ? 0.3 : 1 }}>{ch}</span>)}
        </div>
      </At>
      <ChipTag kind="no" flip={flip} x={boxX + boxW - 10} y={y - 24} p={1} />
      <TokenRow items={results} x={x} y={resultY} field={field} alpha={alphas.map((a) => a)}
                xs={rowLayout(results.map((r) => r.text), x).map((px, i) => px + (1 - alphas[i]) * 0)} />
    </>
  );
}

function ConnectorCurve({ from, to, p }: { from: Pt; to: Pt; p: number }) {
  const mid: Pt = [from[0] - 30, (from[1] + to[1]) / 2];
  const pts: Pt[] = [];
  for (let i = 0; i <= 20; i++) {
    const u = i / 20;
    const a: Pt = [lerp(from[0], mid[0], u), lerp(from[1], mid[1], u)];
    const b: Pt = [lerp(mid[0], to[0], u), lerp(mid[1], to[1], u)];
    pts.push([lerp(a[0], b[0], u), lerp(a[1], b[1], u)]);
  }
  const L = polylineLength(pts);
  return (
    <Overlay>
      <path d={pathD(pts)} fill="none" stroke={C.mint} strokeWidth={6} strokeLinecap="round"
            strokeDasharray={`${L} ${L}`} strokeDashoffset={L * (1 - ease.inOutCubic(clamp(p)))} />
    </Overlay>
  );
}

// ------------------------------------------------------------- 7 slot_scroll

/** Table rows scroll like a slot machine and stop on the matching row,
 * which then highlights. */
export function SlotScroll({ header, rows, target, t, x, y, w, field, from, dur = 1.0 }: {
  header: [string, string]; rows: [string, string][]; target: number; t: number;
  x: number; y: number; w: number; field: FieldName; from?: number; dur?: number;
}) {
  const start = from ?? Math.max(0, target - 12);
  const offset = lerp(start, target, ease.outCubic(seg(t, 0, dur)));
  return <LookupTable header={header} rows={rows} offset={offset} x={x} y={y} w={w} field={field}
                      highlight={seg(t, dur * 0.85, 0.2)} />;
}

// ------------------------------------------------------------- 8 chip_insert

/** New chips slide into the ends (or anywhere) of a row and push the others
 * apart. `items` is the FINAL row; `inserts` lists which of its indexes are
 * new, in the order they arrive, `gap` seconds apart. */
export function ChipInsert({ items, inserts, t, x, y, field, center = true, gap = 0.9, dur = 0.42, size }: {
  items: RowItem[]; inserts: number[]; t: number; x: number; y: number; field: FieldName;
  center?: boolean; gap?: number; dur?: number; size?: number;
}) {
  const prog = items.map((_, i) => {
    const k = inserts.indexOf(i);
    return k === -1 ? 1 : ease.outCubic(seg(t, k * gap, dur));
  });
  const texts = items.map((i) => i.text);
  const widths = texts.map((tx) => chipWidth(tx, size));
  const g = 14;
  const total = widths.reduce((a, w, i) => a + (w + g) * prog[i], 0) - g;
  let cx = center ? x - total / 2 : x;
  const xs: number[] = [];
  const alpha: number[] = [];
  items.forEach((_, i) => {
    const k = inserts.indexOf(i);
    const p = prog[i];
    const dir = i === 0 ? -1 : 1;
    xs.push(cx + (k === -1 ? 0 : (1 - p) * dir * 120));
    alpha.push(k === -1 ? 1 : p);
    cx += (widths[i] + g) * p;
  });
  return (
    <>
      {items.map((it, i) => {
        const k = inserts.indexOf(i);
        const dy = k === -1 ? 0 : (1 - prog[i]) * (i === 0 ? 70 : -70);
        return (
          <At key={i} x={xs[i]} y={y + dy} style={{ opacity: alpha[i] }}>
            <Chip text={it.text} tone={it.tone} field={field} size={size} />
          </At>
        );
      })}
    </>
  );
}

// -------------------------------------------------------------- 9 ghost_word

/** A huge outlined word fades in behind the content and fades out as the
 * explanation starts. */
export function GhostWord({ text, t, x = W / 2, y, size = 360, field, fadeIn = 0.35, hold = 1.2, fadeOut = 0.4 }: {
  text: string; t: number; x?: number; y: number; size?: number; field: FieldName; fadeIn?: number; hold?: number; fadeOut?: number;
}) {
  const th = theme(field);
  const a = seg(t, 0, fadeIn) * (1 - seg(t, fadeIn + hold, fadeOut));
  return (
    <At x={x} y={y} center style={{ opacity: a * 0.9 }}>
      <div style={{ ...display(size), lineHeight: 1, color: "transparent", whiteSpace: "nowrap",
                    WebkitTextStroke: `4px ${th.dark ? "rgba(255,255,255,0.75)" : "rgba(21,25,54,0.55)"}`,
                    transform: `scale(${lerp(0.96, 1, ease.outCubic(seg(t, 0, fadeIn)))})` }}>
        {text}
      </div>
    </At>
  );
}

// ----------------------------------------------------------- 10 counter_morph

/** A big number appears, an arrow draws, and the new number pops in using
 * the accent colour ("2 -> 7"). */
export function CounterMorph({ from, to, fromLabel, toLabel, t, x = 70, y, size = 300, field }: {
  from: string; to: string; fromLabel?: string; toLabel?: string; t: number; x?: number; y: number; size?: number; field: FieldName;
}) {
  const th = theme(field);
  const fw = from.length * size * 0.5;
  const ax0 = x + fw + 40, ax1 = ax0 + size * 0.75;
  const ay = y + size * 0.55;
  return (
    <>
      <BigCounter value={from} label={fromLabel} x={x} y={y} size={size} field={field} accent={false}
                  p={seg(t, 0, 0.3)} center={false} />
      <ArrowDraw points={[[ax0, ay], [ax1, ay]]} t={t} start={0.35} dur={0.4} color={th.accent} width={10} head={34} />
      <BigCounter value={to} label={toLabel} x={ax1 + 40} y={y} size={size} field={field} accent p={seg(t, 0.8, 0.3)} center={false} />
    </>
  );
}

// ------------------------------------------------------------ 11 stagger_rows

/** Rows of a comparison appear one by one, about 120 ms apart. */
export function StaggerRows({ rows, t, x, y, rowH, gap = 0.12, dur = 0.3 }: {
  rows: ReactNode[]; t: number; x: number; y: number; rowH: number; gap?: number; dur?: number;
}) {
  return (
    <>
      {rows.map((r, i) => {
        const p = ease.outCubic(seg(t, i * gap, dur));
        return (
          <At key={i} x={x} y={y + i * rowH} style={{ opacity: p, transform: `translateX(${(1 - p) * -40}px)` }}>{r}</At>
        );
      })}
    </>
  );
}

// ------------------------------------------------------------------ 12 stamp

export const STAMP_DUR = 0.35;

/** A rotated verdict stamp slams in with a slight overshoot and a tiny
 * shake. At most one per reel. */
export function StampSlam({ text, t, x, y, rotate = -8 }: { text: string; t: number; x: number; y: number; rotate?: number }) {
  return <Stamp text={text} x={x} y={y} rotate={rotate} p={seg(t, 0, STAMP_DUR)} t={t} />;
}

// ------------------------------------------------------------ 13 search_type

export const SEARCH = { barIn: 0.2, cps: 12, settle: 0.25 } as const;

/** A search bar types a query while a scan line sweeps the grid, then the
 * matching cell lights up — or, with no match, the bar turns coral. */
export function SearchType({ grid, query, match, t, field, barY, dimRest = 0.5 }: {
  grid: GridSpec; query: string; match: number | null; t: number; field: FieldName; barY: number; dimRest?: number;
}) {
  const typeEnd = SEARCH.barIn + query.length / SEARCH.cps;
  const typed = seg(t, SEARCH.barIn, query.length / SEARCH.cps);
  const done = t >= typeEnd + SEARCH.settle;
  const rowsN = Math.ceil(grid.cells.length / grid.cols);
  const gh = rowsN * ((grid.cellH ?? 66) + (grid.gap ?? 12));
  const scanP = seg(t, SEARCH.barIn, typeEnd - SEARCH.barIn + SEARCH.settle);
  return (
    <>
      <LookupGrid {...grid} field={field}
                  state={{ tone: (i) => (done && match === i ? "ok" : null), dimRest: done ? dimRest : 0 }} />
      {scanP > 0 && scanP < 1 && <ScanLine x={grid.x} y={grid.y} w={grid.w} h={gh} p={scanP} field={field} />}
      <SearchBar query={query} typed={typed} x={grid.x + 40} y={barY} w={grid.w - 80} field={field}
                 p={seg(t, 0, SEARCH.barIn)} found={done ? match !== null : null} />
    </>
  );
}

/** A thin accent line sweeping down a region (findings 8.2). */
export function ScanLine({ x, y, w, h, p, field }: { x: number; y: number; w: number; h: number; p: number; field: FieldName }) {
  const th = theme(field);
  return (
    <div style={{ position: "absolute", left: x - 10, width: w + 20, top: y + h * clamp(p), height: 6, borderRadius: 3,
                  background: th.accent, boxShadow: `0 0 24px ${th.accent}` }} />
  );
}

// --------------------------------------------------------------- 14 count_up

export function formatNumber(n: number, grouping: "indian" | "intl" | "none"): string {
  const s = String(Math.round(n));
  if (grouping === "none" || s.length <= 3) return s;
  if (grouping === "intl") return s.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const last3 = s.slice(-3);
  const rest = s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${last3}`;
}

/** A framed counter rolls from 0 up to `to`, easing out, digits grouped as
 * the source writes them (findings 8.2). Its number must be one the source
 * states — check_motion_numbers_sourced applies to it like any spoken number. */
export function CountUp({ to, t, x = W / 2, y, size = 150, field, dur = 2.4, grouping = "indian", label }: {
  to: number; t: number; x?: number; y: number; size?: number; field: FieldName; dur?: number;
  grouping?: "indian" | "intl" | "none"; label?: string;
}) {
  const v = to * ease.outCubic(seg(t, 0.1, dur));
  return <BigCounter value={formatNumber(v, grouping)} label={seg(t, 0.1, dur) >= 1 ? label : undefined}
                     x={x} y={y} size={size} field={field} framed p={seg(t, 0, 0.25)} />;
}

// ------------------------------------------------------- category highlight

export interface Category { name: string; tone: ChipTone; cells: number[]; at: number }

/** Grid cells light up by group while small legend chips appear above the
 * grid ("WHOLE WORDS", "## PIECES"). Each group lights at its own time —
 * snap it to the spoken word that names it. */
export function CategoryHighlight({ grid, groups, t, field, legendY }: {
  grid: GridSpec; groups: Category[]; t: number; field: FieldName; legendY: number;
}) {
  const toneOf = (i: number) => {
    for (const g of groups) {
      const k = g.cells.indexOf(i);
      if (k !== -1 && t >= g.at + k * 0.04) return g.tone;
    }
    return null;
  };
  const anyOn = groups.some((g) => t >= g.at);
  const texts = groups.map((g) => g.name);
  const xs = rowLayout(texts, W / 2 - rowWidth(texts, 26) / 2, 26);
  return (
    <>
      <LookupGrid {...grid} field={field} state={{ tone: toneOf, dimRest: anyOn ? 0.45 : 0 }} />
      {groups.map((g, i) => {
        const p = ease.outBack(seg(t, g.at, 0.3), 1.6);
        return (
          <At key={g.name} x={xs[i]} y={legendY} style={{ opacity: clamp(p * 2), transform: `scale(${lerp(0.6, 1, clamp(p))})` }}>
            <Chip text={g.name} tone={g.tone} field={field} size={26} />
          </At>
        );
      })}
    </>
  );
}

// --------------------------------------------------------------- zoom cell

export const ZOOM = { dur: 0.6, scale: 2.4 } as const;

/** The camera pushes into one grid cell; it grows into a readable chip with
 * a state tag under it while the rest of the grid blurs and dims. */
export function ZoomCell({ grid, index, tag, tagTone = "ok", t, field }: {
  grid: GridSpec; index: number; tag: string; tagTone?: ChipTone; t: number; field: FieldName;
}) {
  const z = ease.inOutCubic(seg(t, 0, ZOOM.dur));
  const c = gridCellCenter(index, grid.cols, grid.x, grid.y, grid.w, grid.cellH, grid.gap);
  const text = grid.cells[index];
  const tagP = ease.outBack(seg(t, ZOOM.dur, 0.3), 1.6);
  return (
    <>
      <div style={{ position: "absolute", inset: 0, filter: `blur(${6 * z}px)`, opacity: 1 - 0.55 * z }}>
        <LookupGrid {...grid} field={field} scale={lerp(1, ZOOM.scale, z)} origin={c} />
      </div>
      <At x={c[0]} y={c[1] - 20} center style={{ transform: `translate(-50%,-50%) scale(${lerp(0.5, 1, z)})`, opacity: z }}>
        <Chip text={text} tone={tagTone} field={field} size={52} />
      </At>
      <At x={c[0]} y={c[1] + chipHeight(52) / 2 + 10} center style={{ opacity: clamp(tagP * 2),
                                                                     transform: `translate(-50%,0) scale(${lerp(0.6, 1, clamp(tagP))})` }}>
        <div style={{ padding: "8px 18px", borderRadius: 10, background: tagTone === "bad" ? C.coral : C.mint, color: C.white,
                      fontFamily: FONT.mono, fontWeight: 700, fontSize: 22, letterSpacing: 2, whiteSpace: "nowrap" }}>{tag}</div>
      </At>
    </>
  );
}
