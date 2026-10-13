// #motion-gallery/directions — three ORIGINAL NxtWave design directions for
// motion reels, side by side with today's look, on the same five sample shots
// and the same words. A proposal page only: nothing here is used by the reel
// renderer (MotionStage) until one direction is picked.
//
//   #motion-gallery/directions                    the comparison (play / scrub)
//   #motion-gallery/directions?t=2.6              paused at one moment
//   #motion-gallery/directions/frame?d=B&s=how&t=2   one frame alone, full size
//   #motion-gallery/directions/frame?d=B&s=tr&t=0.5  a direction's transition
//
// Every frame is a pure function of t, like every other motion component.

import { Fragment, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Fit, Icon } from "../Stage";
import { clamp, ease, lerp, seg } from "../time";
import { MotionFrame } from "../scene/MotionStage";
import type { MotionPlan } from "../scene/types";

export const SHOT_DUR = 4.5;
export const TR_DUR = 1.0;
export type DirId = "A" | "B" | "C";
export type ShotId = "hook" | "code" | "how" | "idea" | "takeaway";

/** The five sample shots: the same words as the layout audit (/motion-audit/solo.json). */
export const SHOTS: { id: ShotId; name: string; audit: string; caption: string }[] = [
  { id: "hook", name: "Hook", audit: "hook", caption: "Why does your counter stay stuck at zero?" },
  { id: "code", name: "Code", audit: "code_window", caption: "Here is the code a beginner writes first." },
  { id: "how", name: "How it works", audit: "entity_to_panel", caption: "React keeps the value in its own memory." },
  { id: "idea", name: "Key idea", audit: "kinetic_statement", caption: "React only redraws when state changes." },
  { id: "takeaway", name: "Takeaway", audit: "takeaway_list", caption: "Remember these three things." },
];

const MONO = "'JetBrains Mono', monospace";
const SANS = "'Manrope Variable', system-ui, sans-serif";
const BLOCK = "'Archivo Black', system-ui, sans-serif";
const TITLE = "Why does your counter stay stuck at zero?";
const IDEA = "React only redraws when state changes.";
const ROWS = [
  { icon: "refresh", line: "Renders reset", sub: "plain variables" },
  { icon: "memory", line: "State remembers", sub: "between renders" },
  { icon: "bolt", line: "Setters redraw", sub: "the screen" },
];

const P = (t: number, s: number, d: number, e: (p: number) => number = ease.outCubic) => e(seg(t, s, d));
const bare = (w: string) => w.replace(/[^\w]/g, "").toLowerCase();
const abs = (x: number, y: number, extra?: CSSProperties): CSSProperties => ({ position: "absolute", left: x, top: y, ...extra });

/** The word being spoken: captions run 0.3 s – 3.9 s, evenly. */
function spokenIndex(n: number, t: number) {
  return Math.floor((t - 0.3) / (3.6 / n));
}

export interface Direction {
  id: DirId; name: string; mood: string; swatches: string[];
  aspects: [string, string][];
}

export const DIRECTIONS: Direction[] = [
  {
    id: "A", name: "Notebook", mood: "A smart friend's notebook: warm paper, ink lines, a highlighter pen. Calm, human, easy to trust.",
    swatches: ["#F7F2E8", "#1D1B33", "#4B3FE0", "#FFD84D", "#18A874", "#E9534F"],
    aspects: [
      ["Layout", "Left-aligned like a page, wide margins, one idea per sheet; notes overlap the edge of what they explain."],
      ["Depth", "Flat paper cards with an ink outline and a hard offset shadow, like cut paper. No blur."],
      ["Type", "Manrope ExtraBold, sentence case, tight spacing; mono only inside code."],
      ["Colour", "Cream paper and ink; indigo for React and system things; highlighter yellow for the key word."],
      ["Transitions", "Page slide: the next sheet slides up over the last one, which sinks back."],
      ["Camera", "A slow push-in on the part being explained, never a jump."],
      ["Morphs", "The value itself travels along a drawn arc into React's memory."],
      ["Key words", "Words rise in; the key word gets a highlighter swipe or a hand-drawn circle."],
    ],
  },
  {
    id: "B", name: "Midnight Lab", mood: "Inside the machine: deep night blue, glass panels lit from within, things glowing as they work.",
    swatches: ["#070B1F", "#18215A", "#42E2FF", "#8C7BFF", "#FFB547", "#3BE6A0"],
    aspects: [
      ["Layout", "Centred on a 3D stage with a grid floor; the main object floats above it."],
      ["Depth", "Frosted-glass cards, soft glows, blurred light behind, layers that move at different speeds (parallax)."],
      ["Type", "Thin and heavy Manrope side by side; key words heavy and lit; mono labels like // THE CODE."],
      ["Colour", "Night blue base; cyan for what is happening now, violet for React, amber for a warning."],
      ["Transitions", "Zoom-through: the camera flies into the shot and comes out in the next one."],
      ["Camera", "The stage tilts in 3D and settles, then drifts slowly."],
      ["Morphs", "The component card reshapes into React's memory panel (size, corners and colour)."],
      ["Key words", "Words come into focus out of a blur; the key word glows and swells."],
    ],
  },
  {
    id: "C", name: "Colour Block", mood: "Bold and friendly: big rounded blocks of colour, chunky type, playful snaps. Built to stop the scroll.",
    swatches: ["#FFF8EE", "#17162B", "#4F46E5", "#38A3FF", "#FFC53D", "#FF5A5F"],
    aspects: [
      ["Layout", "A big colour block holds the words; objects sit across its bottom edge, half in, half out."],
      ["Depth", "Long soft shadows under white cards; stickers overlap edges."],
      ["Type", "Archivo Black, sentence case, big; key words sit in a pill."],
      ["Colour", "One strong block colour per shot (indigo, ink, sky, sun) on warm white."],
      ["Transitions", "Circle wipe that grows out of the object you were just looking at."],
      ["Camera", "A quick punch-in with a little bounce on the key moment."],
      ["Morphs", "The value tile grows out of the card into a big memory block."],
      ["Key words", "Words pop in one by one; a pill slides in under the key word."],
    ],
  },
];

// ============================================================= shared bits

function Caption({ text, t, x, y, w, style, spoken, todo, current }: {
  text: string; t: number; x: number; y: number; w: number; style: CSSProperties;
  spoken: string; todo: string; current?: (word: ReactNode) => ReactNode;
}) {
  const ws = text.split(" ");
  const k = spokenIndex(ws.length, t);
  return (
    <div style={abs(x, y, { width: w, display: "flex", flexWrap: "wrap", gap: "0 0.28em", ...style })}>
      {ws.map((wd, i) => {
        const el = <span key={i} style={{ color: i <= k ? spoken : todo }}>{wd}</span>;
        return i === k && current ? <span key={i}>{current(el)}</span> : el;
      })}
    </div>
  );
}

/** Code tokens coloured by a palette. */
function codeTokens(line: string, pal: { kw: string; num: string; ink: string; op: string }) {
  return line.split(/(\s+|[=;+])/).filter(Boolean).map((tok, i) => {
    const color = tok === "let" || tok === "const" ? pal.kw : /^\d+$/.test(tok) ? pal.num : /^[=;+]$/.test(tok) ? pal.op : pal.ink;
    return <span key={i} style={{ color }}>{tok}</span>;
  });
}

function TypedCode({ line, p, pal }: { line: string; p: number; pal: { kw: string; num: string; ink: string; op: string } }) {
  const n = Math.round(line.length * clamp(p));
  let used = 0;
  return <>{codeTokens(line, pal).map((el) => {
    const s = el.props.children as string;
    const take = clamp((n - used) / s.length) * s.length;
    used += s.length;
    return take > 0 ? <span key={el.key} style={el.props.style}>{s.slice(0, Math.round(take))}</span> : null;
  })}</>;
}

const LINES = ["let count = 0;", "count = count + 1;"];

// ============================================================ A — Notebook

const A = {
  paper: "#F7F2E8", ink: "#1D1B33", sub: "#6E6A80", indigo: "#4B3FE0", indigoSoft: "#ECE9FF",
  marker: "#FFD84D", mint: "#18A874", coral: "#E9534F", card: "#FFFEFB", todo: "#BDB5A4",
};
const aCard: CSSProperties = { background: A.card, border: `4px solid ${A.ink}`, borderRadius: 30, boxShadow: `12px 12px 0 ${A.ink}` };

function Marker({ p, color = A.marker, children }: { p: number; color?: string; children: ReactNode }) {
  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <span style={{ position: "absolute", left: "-0.06em", bottom: "0.04em", height: "0.44em",
                     width: `calc((100% + 0.12em) * ${clamp(p)})`, background: color, borderRadius: "0.08em",
                     transform: "skewX(-10deg)" }} />
      <span style={{ position: "relative" }}>{children}</span>
    </span>
  );
}

function Circled({ p, children }: { p: number; children: ReactNode }) {
  const len = 1000;
  return (
    <span style={{ position: "relative", display: "inline-block" }}>
      <svg viewBox="0 0 200 100" preserveAspectRatio="none" style={{ position: "absolute", left: "-14%", top: "-12%", width: "128%", height: "124%", overflow: "visible" }}>
        <path d="M 30 18 C 90 -4, 196 8, 194 50 C 192 92, 40 104, 10 70 C -10 44, 40 14, 110 10"
              pathLength={len} fill="none" stroke={A.indigo} strokeWidth={5} strokeLinecap="round"
              strokeDasharray={len} strokeDashoffset={len * (1 - clamp(p))} vectorEffect="non-scaling-stroke" />
      </svg>
      <span style={{ position: "relative", color: A.indigo }}>{children}</span>
    </span>
  );
}

function ARise({ text, t, start, keyFx }: { text: string; t: number; start: number; keyFx: (w: string, i: number) => ReactNode | null }) {
  return <>{text.split(" ").map((w, i) => {
    const p = P(t, start + i * 0.07, 0.5);
    const inner = keyFx(w, i) ?? w;
    return <span key={i} style={{ display: "inline-block", opacity: p, transform: `translateY(${(1 - p) * 60}px)`, marginRight: "0.24em" }}>{inner}</span>;
  })}</>;
}

function AChrome({ label, n }: { label: string; n: number }) {
  return (
    <>
      <div style={abs(80, 150, { display: "flex", alignItems: "center", gap: 18, fontFamily: SANS, fontWeight: 800, fontSize: 28, letterSpacing: 4, color: A.ink })}>
        <span style={{ fontFamily: MONO, color: A.indigo }}>{String(n).padStart(2, "0")}</span>
        <span style={{ width: 44, height: 4, background: A.ink, borderRadius: 2 }} />
        {label}
      </div>
      <div style={abs(840, 132, { padding: "10px 24px", border: `3px solid ${A.ink}`, borderRadius: 40, boxShadow: `5px 5px 0 ${A.ink}`,
                                   background: A.card, fontFamily: SANS, fontWeight: 800, fontSize: 28, color: A.indigo })}>React</div>
      <div style={abs(80, 1830, { fontFamily: SANS, fontWeight: 700, fontSize: 26, color: A.sub })}>@learnthesimpleway</div>
    </>
  );
}

function AShot({ shot, t }: { shot: ShotId; t: number }) {
  const focus: Record<ShotId, string> = { hook: "50% 55%", code: "50% 26%", how: "70% 45%", idea: "30% 30%", takeaway: "50% 40%" };
  const push = 1 + 0.04 * ease.inOutQuad(clamp(t / SHOT_DUR));
  const n = SHOTS.findIndex((s) => s.id === shot) + 1;
  const label = { hook: "THE QUESTION", code: "THE CODE", how: "HOW IT WORKS", idea: "THE IDEA", takeaway: "REMEMBER" }[shot];
  return (
    <div style={{ position: "absolute", inset: 0, background: A.paper,
                  backgroundImage: `radial-gradient(#DCD4C2 2px, transparent 2px)`, backgroundSize: "44px 44px" }}>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${push})`, transformOrigin: focus[shot] }}>
        <AChrome label={label} n={n} />
        {shot === "hook" && <AHook t={t} />}
        {shot === "code" && <ACode t={t} />}
        {shot === "how" && <AHow t={t} />}
        {shot === "idea" && <AIdea t={t} />}
        {shot === "takeaway" && <ATakeaway t={t} />}
      </div>
      <Caption text={SHOTS[n - 1].caption} t={t} x={80} y={1520} w={920} spoken={A.ink} todo={A.todo}
               style={{ fontFamily: SANS, fontWeight: 800, fontSize: 54, lineHeight: 1.3 }}
               current={(el) => <Marker p={1}>{el}</Marker>} />
    </div>
  );
}

function AHook({ t }: { t: number }) {
  const presses = [1.7, 2.2, 2.7];
  const press = Math.max(...presses.map((s) => Math.sin(Math.PI * seg(t, s, 0.2))));
  const shake = Math.max(...presses.map((s) => Math.sin(Math.PI * seg(t, s + 0.1, 0.3)))) * Math.sin(t * 60) * 10;
  const note = P(t, 3.0, 0.45, ease.outBack);
  const card = P(t, 1.0, 0.5);
  return (
    <>
      <div style={abs(80, 290, { width: 920, fontFamily: SANS, fontWeight: 800, fontSize: 120, lineHeight: 1.04, letterSpacing: -3, color: A.ink })}>
        <ARise text={TITLE} t={t} start={0.2} keyFx={(w) => bare(w) === "zero" ? <Marker p={P(t, 1.3, 0.45)}>{w}</Marker> : null} />
      </div>
      <div style={abs(80, 960, { ...aCard, width: 640, height: 300, opacity: card, transform: `translateY(${(1 - card) * 40}px)` })}>
        <div style={abs(40, 34, { fontFamily: MONO, fontSize: 32, color: A.sub })}>&lt;Counter /&gt;</div>
        <div style={abs(40, 84, { fontFamily: SANS, fontWeight: 800, fontSize: 170, lineHeight: 1, color: A.ink, transform: `translateX(${shake}px)` })}>0</div>
        <div style={abs(430, 80, { width: 160, height: 160, borderRadius: 80, background: A.indigo, border: `4px solid ${A.ink}`,
                                   boxShadow: `${8 - press * 8}px ${8 - press * 8}px 0 ${A.ink}`, transform: `translate(${press * 8}px, ${press * 8}px)`,
                                   display: "grid", placeItems: "center", fontFamily: SANS, fontWeight: 800, fontSize: 64, color: "#fff" })}>+1</div>
      </div>
      <div style={abs(620, 1200, { padding: "22px 34px", background: A.marker, border: `4px solid ${A.ink}`, boxShadow: `8px 8px 0 ${A.ink}`,
                                   fontFamily: SANS, fontWeight: 800, fontSize: 46, color: A.ink, borderRadius: 8,
                                   opacity: clamp(note * 2), transform: `rotate(${4 - note * 2}deg) scale(${0.6 + 0.4 * note})` })}>
        Still 0 <span style={{ color: A.coral }}>✕</span>
      </div>
    </>
  );
}

function ACode({ t }: { t: number }) {
  const pal = { kw: A.indigo, num: "#C26A00", ink: A.ink, op: A.sub };
  const card = P(t, 0.1, 0.45);
  const note = P(t, 3.0, 0.45, ease.outBack);
  const arrow = P(t, 3.2, 0.5);
  return (
    <>
      <div style={abs(80, 290, { ...aCard, width: 920, overflow: "hidden", opacity: card, transform: `translateY(${(1 - card) * 40}px)` })}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "22px 32px", borderBottom: `4px solid ${A.ink}`,
                      fontFamily: SANS, fontWeight: 800, fontSize: 30, color: A.ink }}>
          {[0, 1, 2].map((i) => <span key={i} style={{ width: 20, height: 20, borderRadius: 10, border: `3px solid ${A.ink}` }} />)}
          <span style={{ marginLeft: 12 }}>Counter.jsx</span>
        </div>
        <div style={{ padding: "34px 36px 40px", fontFamily: MONO, fontSize: 50, lineHeight: 1.9, background: "#FFFDF6" }}>
          {LINES.map((l, i) => (
            <div key={i} style={{ display: "flex", gap: 30 }}>
              <span style={{ color: A.todo, width: 30 }}>{i + 1}</span>
              {i === 1 ? <Marker p={P(t, 2.6, 0.5)}><TypedCode line={l} p={seg(t, 1.5, 0.9)} pal={pal} /></Marker>
                       : <span><TypedCode line={l} p={seg(t, 0.5, 0.8)} pal={pal} /></span>}
            </div>
          ))}
        </div>
      </div>
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <path d="M 560 860 C 540 760, 640 720, 760 690" pathLength={100} fill="none" stroke={A.ink} strokeWidth={5} strokeLinecap="round"
              strokeDasharray={100} strokeDashoffset={100 * (1 - arrow)} />
        <path d="M 735 668 L 765 690 L 738 716" fill="none" stroke={A.ink} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round"
              opacity={arrow > 0.95 ? 1 : 0} />
      </svg>
      <div style={abs(300, 880, { ...aCard, padding: "26px 34px", width: 560, opacity: clamp(note * 2), background: A.card,
                                   transform: `rotate(${-2 * note}deg) scale(${0.7 + 0.3 * note})`, transformOrigin: "30% 0" })}>
        <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 44, color: A.ink }}>A plain variable</div>
        <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 32, color: A.sub, marginTop: 6 }}>React never hears it change.</div>
      </div>
    </>
  );
}

function AHow({ t }: { t: number }) {
  const card = P(t, 0.1, 0.45);
  const panel = P(t, 0.6, 0.45);
  const arrow = P(t, 1.0, 0.6);
  const fly = P(t, 1.7, 0.9, ease.inOutCubic);
  const from = [128, 432], to = [826, 1012];
  const x = lerp(from[0], to[0], fly), y = lerp(from[1], to[1], fly) - Math.sin(Math.PI * fly) * 260;
  const landed = seg(t, 2.6, 0.3);
  return (
    <>
      <div style={abs(80, 290, { ...aCard, width: 600, height: 280, opacity: card, transform: `translateY(${(1 - card) * 40}px)` })}>
        <div style={abs(40, 34, { fontFamily: MONO, fontSize: 32, color: A.sub })}>&lt;Counter /&gt;</div>
        <div style={abs(40, 90, { fontFamily: SANS, fontWeight: 700, fontSize: 30, color: A.sub })}>On screen</div>
        <div style={abs(48, 142, { width: 100, height: 100, border: `4px dashed ${A.todo}`, borderRadius: 18, opacity: fly > 0 ? 1 : 0 })} />
      </div>
      <div style={abs(260, 860, { ...aCard, width: 740, height: 340, background: A.indigoSoft, opacity: panel, transform: `translateY(${(1 - panel) * 40}px)` })}>
        <div style={abs(40, 36, { display: "flex", alignItems: "center", gap: 18, fontFamily: SANS, fontWeight: 800, fontSize: 46, color: A.ink })}>
          <span style={{ width: 72, height: 72, borderRadius: 18, background: A.indigo, display: "grid", placeItems: "center" }}>
            <Icon name="memory" size={44} color="#fff" stroke={2.4} />
          </span>
          React's memory
        </div>
        <div style={abs(40, 160, { width: 660, height: 130, border: `4px solid ${A.ink}`, borderRadius: 22, background: A.card,
                                   display: "flex", alignItems: "center", padding: "0 36px", fontFamily: MONO, fontSize: 46, color: A.ink })}>
          count
          {landed > 0 && <span style={{ marginLeft: "auto", marginRight: 120, fontFamily: SANS, fontWeight: 800, fontSize: 40, color: A.mint, opacity: landed }}>✓ kept</span>}
        </div>
      </div>
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <path d="M 420 600 C 430 720, 520 760, 600 840" pathLength={100} fill="none" stroke={A.ink} strokeWidth={5} strokeLinecap="round"
              strokeDasharray={100} strokeDashoffset={100 * (1 - arrow)} />
        <path d="M 572 834 L 602 842 L 600 812" fill="none" stroke={A.ink} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" opacity={arrow > 0.95 ? 1 : 0} />
      </svg>
      <div style={abs(x, y, { width: 100, height: 100, borderRadius: 18, background: A.marker, border: `4px solid ${A.ink}`,
                              boxShadow: `${6 + 10 * Math.sin(Math.PI * fly)}px ${6 + 10 * Math.sin(Math.PI * fly)}px 0 ${A.ink}`,
                              transform: `scale(${1 + 0.25 * Math.sin(Math.PI * fly)}) rotate(${-8 * Math.sin(Math.PI * fly)}deg)`,
                              display: "grid", placeItems: "center", fontFamily: SANS, fontWeight: 800, fontSize: 64, color: A.ink,
                              opacity: card })}>1</div>
    </>
  );
}

function AIdea({ t }: { t: number }) {
  return (
    <>
      <div style={abs(80, 330, { width: 920, fontFamily: SANS, fontWeight: 800, fontSize: 138, lineHeight: 1.06, letterSpacing: -4, color: A.ink })}>
        <ARise text={IDEA} t={t} start={0.2} keyFx={(w) => bare(w) === "redraws" ? <Marker p={P(t, 1.4, 0.45)}>{w}</Marker>
                                                     : bare(w) === "state" ? <Circled p={P(t, 2.3, 0.7, ease.inOutCubic)}>{w}</Circled> : null} />
      </div>
      <div style={abs(80, 1130, { display: "flex", gap: 22, fontFamily: SANS, fontWeight: 800, fontSize: 38, color: A.ink })}>
        {[["memory", "State changes"], ["refresh", "React redraws"]].map(([ic, txt], i) => {
          const p = P(t, 2.9 + i * 0.25, 0.4, ease.outBack);
          return (
            <span key={i} style={{ ...aCard, boxShadow: `7px 7px 0 ${A.ink}`, padding: "18px 28px", display: "flex", alignItems: "center", gap: 14,
                                   opacity: clamp(p * 2), transform: `scale(${0.7 + 0.3 * p})` }}>
              <Icon name={ic} size={42} color={A.indigo} stroke={2.6} />{txt}{i === 0 && <span style={{ marginLeft: 8 }}>→</span>}
            </span>
          );
        })}
      </div>
    </>
  );
}

function ATakeaway({ t }: { t: number }) {
  return (
    <>
      <div style={abs(80, 290, { fontFamily: SANS, fontWeight: 800, fontSize: 80, letterSpacing: -2, color: A.ink, whiteSpace: "nowrap" })}>
        <ARise text="Remember these three" t={t} start={0.1} keyFx={(w) => w === "three" ? <Marker p={P(t, 0.9, 0.4)}>{w}</Marker> : null} />
      </div>
      {ROWS.map((r, i) => {
        const p = P(t, 0.9 + i * 0.35, 0.5, ease.outBack);
        const tick = P(t, 1.4 + i * 0.5, 0.4);
        return (
          <div key={i} style={abs(80, 470 + i * 240, { ...aCard, width: 920, height: 190, display: "flex", alignItems: "center", gap: 36, padding: "0 40px",
                                                       opacity: clamp(p * 2), transform: `translateX(${(1 - p) * -120}px) rotate(${(1 - p) * -3}deg)` })}>
            <svg width={86} height={86} viewBox="0 0 86 86" style={{ flex: "none" }}>
              <rect x={4} y={4} width={78} height={78} rx={16} fill={tick > 0 ? A.marker : A.card} stroke={A.ink} strokeWidth={5} />
              <path d="M 20 44 L 37 60 L 66 26" pathLength={100} fill="none" stroke={A.ink} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round"
                    strokeDasharray={100} strokeDashoffset={100 * (1 - tick)} />
            </svg>
            <div>
              <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 56, color: A.ink }}>{r.line}</div>
              <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 34, color: A.sub }}>{r.sub}</div>
            </div>
          </div>
        );
      })}
    </>
  );
}

function ATransition({ t, from, to }: { t: number; from: ShotId; to: ShotId }) {
  const p = P(t, 0, TR_DUR, ease.inOutCubic);
  return (
    <>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${1 - 0.06 * p})`, filter: `brightness(${1 - 0.25 * p})` }}>
        <AShot shot={from} t={SHOT_DUR} />
      </div>
      <div style={{ position: "absolute", inset: 0, transform: `translateY(${(1 - p) * 1920}px)`, borderRadius: `${48 * (1 - p)}px ${48 * (1 - p)}px 0 0`,
                    overflow: "hidden", boxShadow: "0 -30px 70px rgba(29,27,51,.35)" }}>
        <AShot shot={to} t={Math.max(0, t - 0.6)} />
      </div>
    </>
  );
}

// ======================================================== B — Midnight Lab

const B = {
  ink: "#F2F4FF", dim: "#8A92C4", todo: "#3E4680", cyan: "#42E2FF", violet: "#8C7BFF", amber: "#FFB547",
  mint: "#3BE6A0", coral: "#FF6B7A",
};
const glass: CSSProperties = {
  background: "linear-gradient(180deg, rgba(255,255,255,.11), rgba(255,255,255,.04))",
  border: "2px solid rgba(255,255,255,.16)", borderRadius: 40,
  boxShadow: "0 50px 110px rgba(0,0,0,.55), inset 0 2px 0 rgba(255,255,255,.18)",
  backdropFilter: "blur(24px)",
};
const glow = (c: string, r = 40) => `0 0 ${r}px ${c}`;

function BWords({ text, t, start, keys, size, weightKey = 800 }: { text: string; t: number; start: number; keys: Record<string, number>; size: number; weightKey?: number }) {
  return <>{text.split(" ").map((w, i) => {
    const p = P(t, start + i * 0.09, 0.6);
    const k = keys[bare(w)];
    const hit = k != null ? Math.sin(Math.PI * seg(t, k, 0.6)) : 0;
    const lit = k != null ? P(t, k, 0.3) : 0;
    return (
      <span key={i} style={{ display: "inline-block", marginRight: "0.24em", opacity: p, filter: `blur(${(1 - p) * 14}px)`,
                             transform: `translateY(${(1 - p) * 30}px) scale(${1 + hit * 0.12})`, fontSize: size,
                             fontWeight: k != null ? weightKey : 300, color: k != null && lit > 0 ? B.cyan : B.ink,
                             textShadow: k != null ? glow(`rgba(66,226,255,${0.7 * lit})`, 50) : "none" }}>{w}</span>
    );
  })}</>;
}

function BBackground({ t }: { t: number }) {
  const drift = (a: number) => Math.sin(t * 0.5 + a) * 60;
  const rows = Array.from({ length: 12 }, (_, i) => i);
  const flow = (t * 0.35) % 1;
  return (
    <>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(1300px 1000px at 50% 28%, #1B2566 0%, #0B1033 52%, #05081A 100%)" }} />
      <div style={abs(-120 + drift(0), 180, { width: 700, height: 700, borderRadius: 350, background: "rgba(66,226,255,.22)", filter: "blur(120px)" })} />
      <div style={abs(560 + drift(2), 900 + drift(1), { width: 640, height: 640, borderRadius: 320, background: "rgba(140,123,255,.26)", filter: "blur(130px)" })} />
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0, opacity: 0.22 }}>
        {Array.from({ length: 15 }, (_, i) => <line key={i} x1={540} y1={1180} x2={-1100 + i * 235} y2={1920} stroke={B.violet} strokeWidth={2} />)}
        {rows.map((i) => {
          const d = (i + flow) / rows.length;
          const y = 1180 + 740 * d * d;
          return <line key={`h${i}`} x1={0} x2={1080} y1={y} y2={y} stroke={B.violet} strokeWidth={2} opacity={d} />;
        })}
      </svg>
    </>
  );
}

function BChrome({ label, n }: { label: string; n: number }) {
  return (
    <>
      <div style={abs(80, 150, { fontFamily: MONO, fontSize: 28, letterSpacing: 3, color: B.cyan })}>
        <span style={{ color: B.dim }}>{String(n).padStart(2, "0")} </span>// {label}
      </div>
      <div style={abs(820, 132, { ...glass, borderRadius: 40, padding: "12px 26px", display: "flex", alignItems: "center", gap: 12,
                                   fontFamily: SANS, fontWeight: 700, fontSize: 28, color: B.ink })}>
        <span style={{ width: 14, height: 14, borderRadius: 7, background: B.cyan, boxShadow: glow(B.cyan, 14) }} />React
      </div>
      <div style={abs(80, 1830, { fontFamily: MONO, fontSize: 24, color: B.dim })}>@learnthesimpleway</div>
    </>
  );
}

function BShot({ shot, t }: { shot: ShotId; t: number }) {
  const s = P(t, 0, 1.3, ease.outCubic);
  const drift = Math.sin(t * 0.6) * 1.5;
  const n = SHOTS.findIndex((x) => x.id === shot) + 1;
  const label = { hook: "THE QUESTION", code: "THE CODE", how: "HOW IT WORKS", idea: "THE IDEA", takeaway: "REMEMBER" }[shot];
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: "#05081A" }}>
      <BBackground t={t} />
      <div style={{ position: "absolute", inset: 0, perspective: 2200, perspectiveOrigin: "50% 40%" }}>
        <div style={{ position: "absolute", inset: 0, transformStyle: "preserve-3d",
                      transform: `rotateX(${lerp(12, 2, s)}deg) rotateY(${lerp(-8, 0, s) + drift}deg) translateZ(${lerp(-160, 0, s)}px)` }}>
          {shot === "hook" && <BHook t={t} />}
          {shot === "code" && <BCode t={t} />}
          {shot === "how" && <BHow t={t} />}
          {shot === "idea" && <BIdea t={t} />}
          {shot === "takeaway" && <BTakeaway t={t} />}
        </div>
      </div>
      <BChrome label={label} n={n} />
      <Caption text={SHOTS[n - 1].caption} t={t} x={80} y={1520} w={920} spoken={B.ink} todo={B.todo}
               style={{ fontFamily: SANS, fontWeight: 600, fontSize: 52, lineHeight: 1.32 }}
               current={(el) => <span style={{ color: B.cyan, textShadow: glow("rgba(66,226,255,.8)", 24) }}>{el}</span>} />
    </div>
  );
}

function BHook({ t }: { t: number }) {
  const zero = P(t, 0, 2.2);
  const chip = P(t, 2.8, 0.5);
  const beat = 0.5 + 0.5 * Math.sin(t * 6);
  return (
    <>
      <div style={abs(540, 620, { transform: `translate(-50%, -50%) scale(${lerp(1.25, 1, zero)}) translateY(${-t * 10}px)`,
                                  fontFamily: SANS, fontWeight: 800, fontSize: 1150, lineHeight: 1, color: "transparent",
                                  WebkitTextStroke: `4px rgba(66,226,255,${0.28 * zero})` })}>0</div>
      <div style={abs(80, 320, { width: 920, fontFamily: SANS, lineHeight: 1.06, letterSpacing: -2, color: B.ink })}>
        <BWords text={TITLE} t={t} start={0.2} keys={{ stuck: 1.3, zero: 1.7 }} size={122} />
      </div>
      <div style={abs(80, 1150, { ...glass, padding: "26px 40px", display: "flex", alignItems: "center", gap: 22, opacity: chip,
                                   transform: `translateY(${(1 - chip) * 40}px)`, fontFamily: MONO, fontSize: 44, color: B.ink })}>
        <span style={{ width: 22, height: 22, borderRadius: 11, background: B.coral, boxShadow: glow(B.coral, 10 + 24 * beat) }} />
        count is still <span style={{ color: B.coral, fontWeight: 700 }}>0</span>
      </div>
    </>
  );
}

function BCode({ t }: { t: number }) {
  const pal = { kw: B.violet, num: B.amber, ink: B.ink, op: B.dim };
  const panel = P(t, 0, 0.6);
  const scan = seg(t, 2.5, 0.7);
  const flag = P(t, 3.0, 0.4);
  const caret = Math.floor(t * 2.5) % 2 === 0;
  return (
    <>
      <div style={abs(70, 300, { ...glass, width: 940, overflow: "hidden", opacity: panel, transform: `translateZ(${(1 - panel) * -300}px)` })}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "26px 36px", borderBottom: "2px solid rgba(255,255,255,.1)",
                      fontFamily: MONO, fontSize: 28, color: B.dim }}>
          {[B.coral, B.amber, B.mint].map((c, i) => <span key={i} style={{ width: 18, height: 18, borderRadius: 9, background: c, opacity: 0.8 }} />)}
          <span style={{ marginLeft: 14 }}>Counter.jsx</span>
        </div>
        <div style={{ position: "relative", padding: "36px 36px 44px", fontFamily: MONO, fontSize: 50, lineHeight: 1.9 }}>
          {scan > 0 && scan < 1 && <div style={abs(0, 36 + 95 + 6, { width: 940 * scan, height: 82, background: "linear-gradient(90deg, transparent, rgba(66,226,255,.35))" })} />}
          {LINES.map((l, i) => (
            <div key={i} style={{ position: "relative", display: "flex", gap: 30, borderLeft: `6px solid ${i === 1 && flag > 0 ? B.amber : "transparent"}`,
                                  marginLeft: -36, paddingLeft: 30, background: i === 1 ? `rgba(255,181,71,${0.12 * flag})` : "none" }}>
              <span style={{ color: B.todo, width: 30 }}>{i + 1}</span>
              <span><TypedCode line={l} p={i ? seg(t, 1.4, 0.9) : seg(t, 0.5, 0.8)} pal={pal} />
                {((i === 0 && t < 1.4) || (i === 1 && t >= 1.4)) && caret && <span style={{ display: "inline-block", width: 26, height: 54, background: B.cyan, verticalAlign: "middle", boxShadow: glow(B.cyan, 16) }} />}</span>
            </div>
          ))}
        </div>
      </div>
      <div style={abs(70, 760, { ...glass, borderRadius: 30, padding: "24px 34px", display: "flex", alignItems: "center", gap: 20, opacity: flag,
                                  transform: `translateY(${(1 - flag) * 30}px)`, fontFamily: SANS, fontWeight: 700, fontSize: 40, color: B.ink })}>
        <span style={{ width: 20, height: 20, borderRadius: 10, background: B.amber, boxShadow: glow(B.amber, 18) }} />
        A plain variable <span style={{ fontWeight: 300, color: B.dim }}>— React isn't watching</span>
      </div>
    </>
  );
}

function BHow({ t }: { t: number }) {
  const m = P(t, 1.1, 1.2, ease.inOutCubic);
  const rect = { x: lerp(140, 90, m), y: lerp(330, 600, m), w: lerp(800, 900, m), h: lerp(240, 420, m), r: lerp(40, 56, m) };
  const tint = `rgba(140,123,255,${0.28 * m})`;
  const cardOut = 1 - seg(t, 1.1, 0.45), panelIn = seg(t, 1.45, 0.45);
  const enter = P(t, 0, 0.6);
  const screen = P(t, 2.6, 0.5);
  const pulseP = (t - 2.9) % 1.1 / 1.1;
  return (
    <>
      <div style={abs(rect.x, rect.y, { ...glass, width: rect.w, height: rect.h, borderRadius: rect.r, opacity: enter,
                                        background: `linear-gradient(180deg, ${tint}, rgba(255,255,255,.04)), rgba(255,255,255,.06)`,
                                        boxShadow: `0 50px 110px rgba(0,0,0,.55), 0 0 ${80 * m}px rgba(140,123,255,${0.45 * m})` })}>
        <div style={{ opacity: cardOut, padding: "36px 44px" }}>
          <div style={{ fontFamily: MONO, fontSize: 32, color: B.cyan }}>&lt;Counter /&gt;</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 20, marginTop: 14 }}>
            <span style={{ fontFamily: SANS, fontWeight: 300, fontSize: 40, color: B.dim }}>count</span>
            <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: 110, color: B.ink }}>1</span>
          </div>
        </div>
        <div style={abs(0, 0, { opacity: panelIn, padding: "40px 48px", width: "100%", boxSizing: "border-box" })}>
          <div style={{ display: "flex", alignItems: "center", gap: 20, fontFamily: SANS, fontWeight: 800, fontSize: 50, color: B.ink }}>
            <span style={{ width: 84, height: 84, borderRadius: 24, background: `linear-gradient(135deg, ${B.cyan}, ${B.violet})`, display: "grid", placeItems: "center" }}>
              <Icon name="memory" size={50} color="#fff" stroke={2.2} />
            </span>
            React's memory
          </div>
          <div style={{ marginTop: 44, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "28px 36px",
                        borderRadius: 28, background: "rgba(5,8,26,.45)", border: "2px solid rgba(255,255,255,.1)" }}>
            <span style={{ fontFamily: MONO, fontSize: 46, color: B.dim }}>count</span>
            <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: 90, color: B.cyan, textShadow: glow("rgba(66,226,255,.8)", 40) }}>1</span>
          </div>
        </div>
      </div>
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0, overflow: "visible", opacity: screen }}>
        <line x1={540} y1={600} x2={540} y2={470} stroke={B.cyan} strokeWidth={4} strokeDasharray="6 12" />
        {t > 2.9 && <circle cx={540} cy={lerp(600, 470, pulseP)} r={12} fill={B.cyan} style={{ filter: `drop-shadow(0 0 12px ${B.cyan})` }} />}
      </svg>
      <div style={abs(340, 330, { ...glass, borderRadius: 30, width: 400, padding: "24px 30px", display: "flex", alignItems: "center", gap: 18,
                                   opacity: screen, transform: `translateY(${(1 - screen) * 30}px)`, fontFamily: SANS, fontWeight: 600, fontSize: 36, color: B.ink })}>
        <Icon name="eye" size={44} color={B.mint} stroke={2.4} /> On screen <b style={{ marginLeft: "auto", fontSize: 58, color: B.mint }}>1</b>
      </div>
    </>
  );
}

function BIdea({ t }: { t: number }) {
  const rings = [1.5, 2.4].flatMap((k) => [0, 0.3].map((d) => seg(t, k + d, 1.4)));
  return (
    <>
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0 }}>
        {rings.map((p, i) => p > 0 && p < 1 && <circle key={i} cx={540} cy={600} r={120 + 700 * ease.outCubic(p)} fill="none"
                                                        stroke={B.cyan} strokeWidth={3} opacity={0.45 * (1 - p)} />)}
      </svg>
      <div style={abs(80, 330, { width: 920, fontFamily: SANS, lineHeight: 1.08, letterSpacing: -2, color: B.ink, textAlign: "left" })}>
        <BWords text={IDEA} t={t} start={0.2} keys={{ redraws: 1.5, state: 2.4 }} size={138} />
      </div>
      <div style={abs(80, 1130, { display: "flex", alignItems: "center", gap: 26 })}>
        {[["memory", "state changes", B.violet], ["refresh", "screen redraws", B.mint]].map(([ic, txt, c], i) => {
          const p = P(t, 3.0 + i * 0.3, 0.5);
          return (
            <div key={i} style={{ ...glass, borderRadius: 28, padding: "20px 28px", display: "flex", alignItems: "center", gap: 14, opacity: p,
                                  filter: `blur(${(1 - p) * 10}px)`, fontFamily: MONO, fontSize: 34, color: B.ink }}>
              <Icon name={ic} size={40} color={c} stroke={2.4} />{txt}
            </div>
          );
        })}
      </div>
    </>
  );
}

function BTakeaway({ t }: { t: number }) {
  return (
    <>
      <div style={abs(80, 290, { fontFamily: SANS, color: B.ink, letterSpacing: -2 })}>
        <BWords text="Three things to keep" t={t} start={0.1} keys={{ three: 0.8 }} size={96} />
      </div>
      {ROWS.map((r, i) => {
        const p = P(t, 0.8 + i * 0.35, 0.7);
        const sweep = seg(t, 1.6 + i * 0.4, 0.7);
        return (
          <div key={i} style={abs(80, 480 + i * 250, { ...glass, width: 920, height: 200, overflow: "hidden", display: "flex", alignItems: "center", gap: 36,
                                                       padding: "0 40px", boxSizing: "border-box", opacity: p, filter: `blur(${(1 - p) * 12}px)`,
                                                       transform: `translateZ(${(1 - p) * -400}px)` })}>
            {sweep > 0 && sweep < 1 && <div style={abs(-300 + 1500 * sweep, 0, { width: 260, height: 200, transform: "skewX(-20deg)",
                                                                                  background: "linear-gradient(90deg, transparent, rgba(255,255,255,.14), transparent)" })} />}
            <span style={{ width: 110, height: 110, flex: "none", borderRadius: 30, background: `linear-gradient(135deg, ${B.cyan}, ${B.violet})`,
                           display: "grid", placeItems: "center", boxShadow: glow("rgba(66,226,255,.35)", 30) }}>
              <Icon name={r.icon} size={60} color="#fff" stroke={2.2} />
            </span>
            <div>
              <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 56, color: B.ink }}>{r.line}</div>
              <div style={{ fontFamily: SANS, fontWeight: 300, fontSize: 36, color: B.dim }}>{r.sub}</div>
            </div>
          </div>
        );
      })}
    </>
  );
}

function BTransition({ t, from, to }: { t: number; from: ShotId; to: ShotId }) {
  const out = P(t, 0, 0.6, ease.inCubic);
  const inn = P(t, 0.35, 0.65, ease.outCubic);
  return (
    <>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${1 + 1.4 * out})`, transformOrigin: "50% 40%", filter: `blur(${16 * out}px)`, opacity: 1 - out }}>
        <BShot shot={from} t={SHOT_DUR} />
      </div>
      {t > 0.35 && (
        <div style={{ position: "absolute", inset: 0, transform: `scale(${lerp(0.7, 1, inn)})`, filter: `blur(${16 * (1 - inn)}px)`, opacity: inn }}>
          <BShot shot={to} t={Math.max(0, t - 0.35)} />
        </div>
      )}
    </>
  );
}

// ======================================================== C — Colour Block

const Cc = {
  bg: "#FFF8EE", ink: "#17162B", sub: "#6F6A80", indigo: "#4F46E5", sky: "#38A3FF", sun: "#FFC53D", coral: "#FF5A5F",
  mint: "#12B886", todo: "#CFC6B6", white: "#FFFFFF",
};
const soft = "0 44px 80px -26px rgba(23,22,43,.45)";
const BLOCKS: Record<ShotId, { color: string; h: number; text: string }> = {
  hook: { color: Cc.indigo, h: 1010, text: Cc.white },
  code: { color: Cc.ink, h: 860, text: Cc.white },
  how: { color: Cc.sky, h: 760, text: Cc.white },
  idea: { color: Cc.sun, h: 1100, text: Cc.ink },
  takeaway: { color: Cc.indigo, h: 520, text: Cc.white },
};

function CPop({ text, t, start, keys, pill }: { text: string; t: number; start: number; keys: Record<string, number>; pill: string }) {
  return <>{text.split(" ").map((w, i) => {
    const p = P(t, start + i * 0.08, 0.4, ease.outBack);
    const k = keys[bare(w)];
    const g = k != null ? P(t, k, 0.35, ease.outBack) : 0;
    return (
      <span key={i} style={{ position: "relative", display: "inline-block", marginRight: "0.26em", opacity: clamp(p * 3),
                             transform: `translateY(${(1 - p) * 30}px) scale(${0.5 + 0.5 * p})` }}>
        {k != null && <span style={{ position: "absolute", left: "-0.16em", right: "-0.16em", top: "0.02em", bottom: "-0.04em", borderRadius: "0.3em",
                                     background: pill, transform: `scaleX(${g})`, transformOrigin: "0 50%" }} />}
        <span style={{ position: "relative", color: k != null && g > 0.5 ? Cc.ink : undefined }}>{w}</span>
      </span>
    );
  })}</>;
}

function CShot({ shot, t }: { shot: ShotId; t: number }) {
  const blk = BLOCKS[shot];
  const n = SHOTS.findIndex((x) => x.id === shot) + 1;
  const keyAt: Record<ShotId, [number, string]> = { hook: [2.9, "50% 62%"], code: [2.6, "50% 32%"], how: [2.4, "50% 62%"], idea: [2.3, "40% 30%"], takeaway: [2.2, "50% 55%"] };
  const [k, origin] = keyAt[shot];
  const punch = 1 + 0.07 * P(t, k, 0.45, ease.outBack);
  const spin = t * 12;
  const label = { hook: "The question", code: "The code", how: "How it works", idea: "The idea", takeaway: "Remember" }[shot];
  return (
    <div style={{ position: "absolute", inset: 0, background: Cc.bg, overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${punch})`, transformOrigin: origin }}>
        <div style={abs(40, 40, { width: 1000, height: blk.h, borderRadius: 64, background: blk.color, overflow: "hidden" })}>
          <div style={abs(720, blk.h - 230, { width: 420, height: 420, borderRadius: 210, background: shot === "idea" ? Cc.white : Cc.sun, opacity: shot === "idea" ? 0.35 : 0.9,
                                              transform: `rotate(${spin}deg)` })} />
          <div style={abs(770, -60, { width: 200, height: 200, borderRadius: 40, border: `16px solid ${shot === "idea" ? Cc.ink : "rgba(255,255,255,.18)"}`,
                                      opacity: shot === "idea" ? 0.12 : 1, transform: `rotate(${20 + spin}deg)` })} />
        </div>
        <div style={abs(100, 110, { padding: "10px 24px", borderRadius: 40, background: Cc.white, fontFamily: BLOCK, fontSize: 28, color: Cc.ink })}>
          {String(n).padStart(2, "0")} · {label}
        </div>
        <div style={abs(820, 110, { padding: "10px 24px", borderRadius: 40, background: shot === "idea" ? Cc.ink : Cc.sun, fontFamily: BLOCK, fontSize: 28,
                                    color: shot === "idea" ? Cc.sun : Cc.ink })}>React</div>
        {shot === "hook" && <CHook t={t} />}
        {shot === "code" && <CCode t={t} />}
        {shot === "how" && <CHow t={t} />}
        {shot === "idea" && <CIdea t={t} />}
        {shot === "takeaway" && <CTakeaway t={t} />}
      </div>
      <Caption text={SHOTS[n - 1].caption} t={t} x={80} y={1540} w={920} spoken={Cc.ink} todo={Cc.todo}
               style={{ fontFamily: BLOCK, fontSize: 56, lineHeight: 1.3 }}
               current={(el) => <span style={{ background: Cc.sun, borderRadius: 14, padding: "0 10px", margin: "0 -10px" }}>{el}</span>} />
      <div style={abs(80, 1830, { fontFamily: BLOCK, fontSize: 24, color: Cc.sub })}>@learnthesimpleway</div>
    </div>
  );
}

function CHook({ t }: { t: number }) {
  const presses = [1.6, 2.1, 2.6];
  const press = Math.max(...presses.map((s) => Math.sin(Math.PI * seg(t, s, 0.18))));
  const card = P(t, 0.9, 0.5, ease.outBack);
  const sticker = P(t, 2.9, 0.4, ease.outBack);
  return (
    <>
      <div style={abs(100, 250, { width: 880, fontFamily: BLOCK, fontSize: 112, lineHeight: 1.08, color: Cc.white })}>
        <CPop text={TITLE} t={t} start={0.2} keys={{ zero: 1.4 }} pill={Cc.sun} />
      </div>
      <div style={abs(160, 900, { width: 760, height: 330, borderRadius: 52, background: Cc.white, boxShadow: soft, opacity: clamp(card * 2),
                                   transform: `translateY(${(1 - card) * 120}px)` })}>
        <div style={abs(60, 40, { fontFamily: MONO, fontSize: 30, color: Cc.sub })}>&lt;Counter /&gt;</div>
        <div style={abs(60, 70, { fontFamily: BLOCK, fontSize: 210, lineHeight: 1.1, color: Cc.ink })}>0</div>
        {presses.map((s, i) => {
          const f = seg(t, s, 0.7);
          return f > 0 && f < 1 && <div key={i} style={abs(520, 40 - 120 * f, { fontFamily: BLOCK, fontSize: 48, color: Cc.indigo, opacity: 1 - f })}>+1?</div>;
        })}
        <div style={abs(500, 90, { width: 180, height: 180, borderRadius: 90, background: Cc.sun, display: "grid", placeItems: "center",
                                   boxShadow: `0 ${18 - 14 * press}px 0 #D99A00`, transform: `translateY(${14 * press}px)`,
                                   fontFamily: BLOCK, fontSize: 96, color: Cc.ink })}>+</div>
      </div>
      <div style={abs(300, 1180, { padding: "18px 34px", borderRadius: 24, background: Cc.coral, color: Cc.white, fontFamily: BLOCK, fontSize: 46,
                                    boxShadow: soft, opacity: clamp(sticker * 3), transform: `rotate(${-8 + 2 * sticker}deg) scale(${sticker})` })}>Still 0!</div>
    </>
  );
}

function CCode({ t }: { t: number }) {
  const pal = { kw: Cc.sun, num: Cc.sky, ink: Cc.white, op: "#8E8AA8" };
  const bar = P(t, 2.5, 0.4);
  const sticker = P(t, 2.9, 0.4, ease.outBack);
  return (
    <>
      <div style={abs(100, 250, { padding: "14px 28px", borderRadius: 20, background: "rgba(255,255,255,.1)", fontFamily: MONO, fontSize: 30, color: Cc.white })}>Counter.jsx</div>
      <div style={abs(100, 380, { fontFamily: MONO, fontSize: 58, lineHeight: 2.0 })}>
        {LINES.map((l, i) => (
          <div key={i} style={{ position: "relative" }}>
            {i === 1 && <div style={abs(-20, 98, { height: 12, width: 640 * bar, borderRadius: 6, background: Cc.sun })} />}
            <TypedCode line={l} p={i ? seg(t, 1.4, 0.9) : seg(t, 0.4, 0.8)} pal={pal} />
          </div>
        ))}
      </div>
      <div style={abs(460, 820, { padding: "28px 40px", borderRadius: 36, background: Cc.sun, boxShadow: soft, opacity: clamp(sticker * 3),
                                   transform: `rotate(${6 - 2 * sticker}deg) scale(${sticker})`, transformOrigin: "20% 50%" })}>
        <div style={{ fontFamily: BLOCK, fontSize: 52, color: Cc.ink }}>Plain variable</div>
        <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 32, color: Cc.ink, opacity: 0.75 }}>React never hears it change</div>
      </div>
    </>
  );
}

function CHow({ t }: { t: number }) {
  const card = P(t, 0.1, 0.5, ease.outBack);
  const g = P(t, 1.3, 1.0, ease.inOutCubic);
  const box = { x: lerp(560, 80, g), y: lerp(380, 920, g), w: lerp(150, 920, g), h: lerp(150, 380, g), r: lerp(32, 56, g) };
  const label = seg(t, 2.1, 0.35);
  const arrow = P(t, 2.3, 0.4);
  return (
    <>
      <div style={abs(100, 236, { fontFamily: BLOCK, fontSize: 64, lineHeight: 1.05, color: Cc.white, width: 900, whiteSpace: "nowrap" })}>
        <CPop text="Where does count live?" t={t} start={0.1} keys={{}} pill={Cc.sun} />
      </div>
      <div style={abs(100, 350, { width: 680, height: 220, borderRadius: 44, background: Cc.white, boxShadow: soft, opacity: clamp(card * 2),
                                   transform: `scale(${0.6 + 0.4 * card})`, transformOrigin: "0 50%" })}>
        <div style={abs(44, 44, { fontFamily: MONO, fontSize: 32, color: Cc.sub })}>&lt;Counter /&gt;</div>
        <div style={abs(44, 100, { fontFamily: BLOCK, fontSize: 52, color: Cc.ink })}>On screen</div>
      </div>
      <svg width={1080} height={1920} style={{ position: "absolute", inset: 0, overflow: "visible", opacity: arrow }}>
        <path d="M 300 600 L 300 860" stroke={Cc.ink} strokeWidth={18} strokeLinecap="round" pathLength={100} strokeDasharray={100} strokeDashoffset={100 * (1 - arrow)} />
        <path d="M 250 815 L 300 870 L 350 815" fill="none" stroke={Cc.ink} strokeWidth={18} strokeLinecap="round" strokeLinejoin="round" opacity={arrow > 0.9 ? 1 : 0} />
      </svg>
      <div style={abs(box.x, box.y, { width: box.w, height: box.h, borderRadius: box.r, background: Cc.sun, boxShadow: soft, opacity: clamp(card * 2),
                                      overflow: "hidden" })}>
        <div style={abs(0, 0, { width: 150, height: 150, display: "grid", placeItems: "center", fontFamily: BLOCK, fontSize: 90, color: Cc.ink, opacity: 1 - label })}>1</div>
        <div style={abs(56, 50, { opacity: label, width: 820 })}>
          <div style={{ display: "flex", alignItems: "center", gap: 18, fontFamily: BLOCK, fontSize: 52, color: Cc.ink }}>
            <Icon name="memory" size={60} color={Cc.ink} stroke={2.6} /> React's memory
          </div>
          <div style={{ marginTop: 34, display: "flex", alignItems: "center", gap: 30 }}>
            <span style={{ fontFamily: MONO, fontSize: 56, color: Cc.ink }}>count</span>
            <span style={{ width: 150, height: 150, borderRadius: 36, background: Cc.white, display: "grid", placeItems: "center",
                           fontFamily: BLOCK, fontSize: 96, color: Cc.ink }}>1</span>
          </div>
        </div>
      </div>
    </>
  );
}

function CIdea({ t }: { t: number }) {
  return (
    <div style={abs(100, 260, { width: 880, fontFamily: BLOCK, fontSize: 132, lineHeight: 1.08, color: Cc.ink })}>
      <CPop text={IDEA} t={t} start={0.2} keys={{ redraws: 1.5, state: 2.3 }} pill={Cc.white} />
      <div style={{ display: "flex", gap: 22, marginTop: 70 }}>
        {[["memory", "State changes", Cc.indigo], ["refresh", "Screen redraws", Cc.mint]].map(([ic, txt, c], i) => {
          const p = P(t, 3.0 + i * 0.25, 0.4, ease.outBack);
          return (
            <span key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "20px 30px", borderRadius: 30, background: Cc.white, boxShadow: soft,
                                   fontFamily: BLOCK, fontSize: 36, color: Cc.ink, opacity: clamp(p * 3), transform: `scale(${p})` }}>
              <Icon name={ic} size={42} color={c} stroke={2.8} />{txt}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function CTakeaway({ t }: { t: number }) {
  const colors = [Cc.sun, Cc.sky, Cc.white];
  const tilt = [-4, 3, -2];
  return (
    <>
      <div style={abs(100, 250, { width: 880, fontFamily: BLOCK, fontSize: 104, lineHeight: 1.05, color: Cc.white })}>
        <CPop text="Remember these three" t={t} start={0.1} keys={{ three: 0.9 }} pill={Cc.sun} />
      </div>
      {ROWS.map((r, i) => {
        const p = P(t, 1.0 + i * 0.3, 0.55, ease.outBack);
        return (
          <div key={i} style={abs(80, 480 + i * 270, { width: 920, height: 230, borderRadius: 48, background: colors[i], boxShadow: soft,
                                                       display: "flex", alignItems: "center", gap: 36, padding: "0 48px", boxSizing: "border-box",
                                                       opacity: clamp(p * 3), transform: `translateY(${(1 - p) * 500}px) rotate(${tilt[i] * (1 - p) + tilt[i] * 0.25}deg)` })}>
            <span style={{ width: 120, height: 120, flex: "none", borderRadius: 60, background: Cc.ink, color: colors[i] === Cc.white ? Cc.sun : colors[i],
                           display: "grid", placeItems: "center", fontFamily: BLOCK, fontSize: 64 }}>{i + 1}</span>
            <div>
              <div style={{ fontFamily: BLOCK, fontSize: 58, color: Cc.ink }}>{r.line}</div>
              <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 36, color: Cc.ink, opacity: 0.7 }}>{r.sub}</div>
            </div>
          </div>
        );
      })}
    </>
  );
}

function CTransition({ t, from, to }: { t: number; from: ShotId; to: ShotId }) {
  const p = P(t, 0, 0.85, ease.inOutCubic);
  const r = 2300 * p;
  return (
    <>
      <div style={{ position: "absolute", inset: 0 }}><CShot shot={from} t={SHOT_DUR} /></div>
      <div style={{ position: "absolute", inset: 0, clipPath: `circle(${r}px at 600px 1000px)`, transform: `scale(${lerp(1.08, 1, p)})` }}>
        <CShot shot={to} t={Math.max(0, t - 0.3)} />
      </div>
      {p > 0 && p < 1 && (
        <div style={abs(600 - r, 1000 - r, { width: 2 * r, height: 2 * r, borderRadius: "50%", border: `28px solid ${Cc.sun}`, boxSizing: "border-box" })} />
      )}
    </>
  );
}

// ============================================================== frames

const FRAMES: Record<DirId, { Shot: typeof AShot; Tr: typeof ATransition }> = {
  A: { Shot: AShot, Tr: ATransition },
  B: { Shot: BShot, Tr: BTransition },
  C: { Shot: CShot, Tr: CTransition },
};

/** One 1080 x 1920 frame of a direction: a shot at local time t, or ("tr")
 * its transition from the code shot into the how-it-works shot. */
export function DirectionFrame({ dir, shot, t }: { dir: DirId; shot: ShotId | "tr"; t: number }) {
  const { Shot, Tr } = FRAMES[dir];
  return (
    <div style={{ position: "relative", width: 1080, height: 1920, overflow: "hidden" }}>
      {shot === "tr" ? <Tr t={t} from="code" to="how" /> : <Shot shot={shot} t={t} />}
    </div>
  );
}

// ============================================================== page

function useAudit() {
  const [plan, setPlan] = useState<MotionPlan | null>(null);
  const [ids, setIds] = useState<Record<string, string>>({});
  useEffect(() => {
    fetch("/motion-audit/solo.json").then((r) => r.json()).then(setPlan).catch(() => {});
    fetch("/motion-audit/index.json").then((r) => r.json())
      .then((ix) => setIds(Object.fromEntries(ix.contexts.solo.map((r: { scene: string; id: string }) => [r.scene, r.id])))).catch(() => {});
  }, []);
  return { plan, ids };
}

/** Today's look: the same shot from the audit plan, through the real renderer. */
function Today({ plan, ids, shot, t, width }: { plan: MotionPlan | null; ids: Record<string, string>; shot: (typeof SHOTS)[number]; t: number; width: number }) {
  const s = plan?.shots.find((x) => x.id === ids[shot.audit]);
  if (!plan || !s) return <div style={{ width, height: width * 16 / 9, background: "#1A1F3D", borderRadius: 8 }} />;
  const at = Math.min(s.end - 0.05, s.start + t * ((s.end - s.start) / SHOT_DUR));
  return <Fit width={width}><MotionFrame plan={plan} t={at} /></Fit>;
}

function useClock(initial: number | null) {
  const [t, setT] = useState(initial ?? 0);
  const [playing, setPlaying] = useState(initial == null);
  const last = useRef<number | null>(null);
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = (now: number) => {
      if (last.current != null) setT((x) => (x + (now - last.current!) / 1000) % (SHOT_DUR + 0.8));
      last.current = now;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); last.current = null; };
  }, [playing]);
  return { t: Math.min(t, SHOT_DUR), raw: t, setT, playing, setPlaying };
}

const page: CSSProperties = { minHeight: "100vh", background: "#0E1224", color: "#E9EBF7", fontFamily: SANS, padding: "24px 28px 80px" };

export function DirectionsPage({ q }: { q: URLSearchParams }) {
  const start = q.get("t");
  const { t, raw, setT, playing, setPlaying } = useClock(start != null ? Number(start) : null);
  const { plan, ids } = useAudit();
  const width = Number(q.get("w") || 230);
  const trT = (raw % 1.6) / 1.6 * (TR_DUR + 0.3);
  const cols: { id: "today" | DirId; title: string }[] = [
    { id: "today", title: "Today (for comparison)" }, ...DIRECTIONS.map((d) => ({ id: d.id, title: `${d.id} · ${d.name}` })),
  ];
  return (
    <div style={page}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 18, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 28 }}>Design directions: pick one</h1>
        <span style={{ color: "#9AA0C0", fontSize: 14 }}>The same five shots and the same words in today's look and three original directions. Nothing here is applied to reels yet.</span>
        <a href="#motion-gallery" style={{ color: "#FDD13E", fontSize: 14, marginLeft: "auto" }}>← Motion gallery</a>
      </header>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, margin: "20px 0" }}>
        {DIRECTIONS.map((d) => (
          <div key={d.id} style={{ background: "#151A33", borderRadius: 14, padding: 16 }}>
            <div style={{ fontSize: 20, fontWeight: 800 }}>{d.id} · {d.name}</div>
            <p style={{ margin: "6px 0 10px", color: "#C9CDE6", fontSize: 14 }}>{d.mood}</p>
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              {d.swatches.map((c) => <span key={c} title={c} style={{ width: 30, height: 30, borderRadius: 8, background: c, border: "1px solid #ffffff22" }} />)}
            </div>
            <dl style={{ margin: 0, fontSize: 13, display: "grid", gridTemplateColumns: "92px 1fr", gap: "4px 10px" }}>
              {d.aspects.map(([k, v]) => <Fragment key={k}><dt style={{ color: "#FDD13E", fontWeight: 700 }}>{k}</dt><dd style={{ margin: 0, color: "#C9CDE6" }}>{v}</dd></Fragment>)}
            </dl>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14, position: "sticky", top: 0, background: "#0E1224", padding: "10px 0", zIndex: 2 }}>
        <button onClick={() => setPlaying(!playing)} style={{ padding: "8px 18px", borderRadius: 8, border: 0, background: "#FDD13E", fontWeight: 800 }}>
          {playing ? "Pause" : "Play"}
        </button>
        <input type="range" min={0} max={SHOT_DUR} step={1 / 30} value={t} style={{ width: 360 }}
               onChange={(e) => { setPlaying(false); setT(Number(e.target.value)); }} />
        <span style={{ fontFamily: MONO, fontSize: 13, color: "#9AA0C0" }}>{t.toFixed(2)} s of {SHOT_DUR} s per shot</span>
      </div>
      <table style={{ borderCollapse: "separate", borderSpacing: "14px 12px", marginLeft: -14 }}>
        <thead>
          <tr><th />{cols.map((c) => <th key={c.id} style={{ textAlign: "left", fontSize: 15 }}>{c.title}</th>)}</tr>
        </thead>
        <tbody>
          {SHOTS.map((s) => (
            <tr key={s.id}>
              <td style={{ verticalAlign: "top", fontSize: 14, color: "#9AA0C0", width: 90 }}>{s.name}</td>
              {cols.map((c) => (
                <td key={c.id} style={{ verticalAlign: "top" }}>
                  {c.id === "today" ? <Today plan={plan} ids={ids} shot={s} t={t} width={width} />
                    : <a href={`#motion-gallery/directions/frame?d=${c.id}&s=${s.id}&t=${t.toFixed(2)}`}>
                        <Fit width={width}><DirectionFrame dir={c.id} shot={s.id} t={t} /></Fit></a>}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <td style={{ verticalAlign: "top", fontSize: 14, color: "#9AA0C0" }}>Transition<br />code → how</td>
            <td style={{ verticalAlign: "top", fontSize: 13, color: "#9AA0C0", maxWidth: width }}>Today: a field-colour wipe (unchanged)</td>
            {DIRECTIONS.map((d) => (
              <td key={d.id}><Fit width={width}><DirectionFrame dir={d.id} shot="tr" t={start != null ? Number(q.get("tr") ?? 0.5) : trT} /></Fit></td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** One frame alone at full design size (for screenshots). */
export function DirectionSingle({ q }: { q: URLSearchParams }) {
  const d = (q.get("d") as DirId) || "A";
  const s = (q.get("s") as ShotId | "tr") || "hook";
  const t = Number(q.get("t") ?? 2);
  const width = Number(q.get("w") || 540);
  return <Fit width={width}><DirectionFrame dir={d} shot={s} t={t} /></Fit>;
}
