// Motion-reel AVATARS (RESTYLE_TO_MOTION_REELS.md phase 3). One parametric,
// original character per course language plus the shared host, drawn from
// shorts/motion_avatars.yaml's `art` (body, head, hair, skin, accessories)
// and palette — flat shapes in the same style as the cards: no outlines
// thicker than the cards', no gradients, no stick figures, and nothing that
// copies a language's official logo or mascot.
//
// PURE IN t, like every motion component. Three states:
//   idle      breathing, a slow head bob, blinks at fixed times;
//   talking   the mouth opens and closes on a syllable rhythm, the head nods,
//             one hand gestures;
//   reacting  brows up, eyes wide, the head tilts, three accent ticks flash.
// `since` is seconds since the state began, so a reaction eases in.

import type { ReactNode } from "react";
import { C } from "../tokens";
import { clamp, ease, hash3 } from "../time";
import library from "../library.json";

export type AvatarState = "idle" | "talking" | "reacting";

export interface AvatarSpec {
  id: string; name: string; body: string; head: string; hair: string; skin: string;
  accessories: string[];
  palette: { primary: string; secondary: string; accent: string; ink: string };
}

const SKINS = (library as { avatar: { skins: Record<string, string> } }).avatar.skins;
export const AVATAR_BOX = (library as { avatar: { box: { w: number; h: number } } }).avatar.box;

/** Darken a #RRGGBB colour by `k` (0..1). */
function shade(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16);
  const f = (v: number) => Math.round(v * (1 - k)).toString(16).padStart(2, "0");
  return `#${f((n >> 16) & 255)}${f((n >> 8) & 255)}${f(n & 255)}`;
}

/** Relative luminance 0..1 of a #RRGGBB colour. */
function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
}

function seedOf(id: string): number {
  let h = 7;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 9973;
  return h;
}

/** How open the mouth is while talking: a syllable rhythm (~6 per second)
 * with a slower phrase envelope, both from a fixed hash — pure in t. */
export function mouthOpen(t: number, seed: number): number {
  const syl = Math.floor(t * 6.2);
  const within = t * 6.2 - syl;
  const peak = 0.35 + 0.65 * hash3(seed, syl);
  const shape = Math.sin(Math.PI * within);
  const phrase = 0.75 + 0.25 * Math.sin(t * 1.7 + seed);
  return clamp(peak * shape * phrase);
}

/** 0..1 eyelid closure: a quick blink every ~3.4 s at a per-character phase. */
function blink(t: number, seed: number): number {
  const period = 3.4 + (seed % 7) * 0.13;
  const p = ((t + seed * 0.37) % period) / period;
  const d = Math.abs(p - 0.5) * period;
  return d < 0.09 ? 1 - d / 0.09 : 0;
}

// --------------------------------------------------------------------- body

function Body({ kind, color, dark, outline }: { kind: string; color: string; dark: string; outline: string }) {
  const y0 = 262;
  return <g stroke={outline} strokeWidth={outline === "none" ? 0 : 6} strokeLinejoin="round">{bodyShape(kind, color, dark, y0)}</g>;
}

function bodyShape(kind: string, color: string, dark: string, y0: number) {
  switch (kind) {
    case "square": return <rect x={66} y={y0} width={228} height={200} rx={26} fill={color} />;
    case "tall": return <rect x={88} y={y0 - 14} width={184} height={214} rx={48} fill={color} />;
    case "pill": return <rect x={80} y={y0} width={200} height={240} rx={100} fill={color} />;
    case "arch": return <path d={`M70,${y0 + 220} L70,${y0 + 70} Q70,${y0} 180,${y0} Q290,${y0} 290,${y0 + 70} L290,${y0 + 220} Z`} fill={color} />;
    case "wide": return <rect x={44} y={y0 + 6} width={272} height={200} rx={42} fill={color} />;
    case "compact": return <rect x={96} y={y0 + 6} width={168} height={200} rx={34} fill={color} />;
    case "hex": return <polygon points={`110,${y0} 250,${y0} 300,${y0 + 50} 300,${y0 + 220} 60,${y0 + 220} 60,${y0 + 50}`} fill={color} />;
    case "stacked": return (
      <g>
        <rect x={56} y={y0 + 70} width={248} height={160} rx={30} fill={dark} />
        <rect x={84} y={y0} width={192} height={110} rx={32} fill={color} />
      </g>
    );
    case "broad": return <path d={`M40,${y0 + 220} L52,${y0 + 46} Q60,${y0} 112,${y0} L248,${y0} Q300,${y0} 308,${y0 + 46} L320,${y0 + 220} Z`} fill={color} />;
    default: return <rect x={68} y={y0} width={224} height={220} rx={72} fill={color} />;   // rounded
  }
}

// --------------------------------------------------------------------- head

function headGeom(kind: string) {
  if (kind === "oval") return { cx: 180, cy: 156, rx: 70, ry: 86, top: 70 };
  if (kind === "rounded_square") return { cx: 180, cy: 160, rx: 76, ry: 80, top: 80 };
  return { cx: 180, cy: 160, rx: 78, ry: 78, top: 82 };
}

function Head({ kind, skin }: { kind: string; skin: string }) {
  const g = headGeom(kind);
  if (kind === "rounded_square") return <rect x={g.cx - g.rx} y={g.cy - g.ry} width={g.rx * 2} height={g.ry * 2} rx={50} fill={skin} />;
  return <ellipse cx={g.cx} cy={g.cy} rx={g.rx} ry={g.ry} fill={skin} />;
}

/** Hair drawn BEHIND the head (long hair, tails) and OVER it (the cap of hair). */
function Hair({ kind, color, accent, primary, head, layer }: {
  kind: string; color: string; accent: string; primary: string; head: string; layer: "back" | "front";
}) {
  const g = headGeom(head);
  const top = g.cy - g.ry;
  const L = g.cx - g.rx, R = g.cx + g.rx;
  const cap = <path d={`M${L - 4},${g.cy - 6} Q${L - 4},${top - 18} ${g.cx},${top - 16} Q${R + 4},${top - 18} ${R + 4},${g.cy - 6} Q${g.cx + 30},${top + 22} ${g.cx},${top + 26} Q${g.cx - 40},${top + 26} ${L - 4},${g.cy - 6} Z`} fill={color} />;
  if (layer === "back") {
    if (kind === "long") return <path d={`M${L - 8},${g.cy - 20} L${L - 16},${g.cy + 130} L${L + 30},${g.cy + 130} L${L + 24},${g.cy + 30} Z M${R + 8},${g.cy - 20} L${R + 16},${g.cy + 130} L${R - 30},${g.cy + 130} L${R - 24},${g.cy + 30} Z`} fill={color} />;
    if (kind === "bob") return <rect x={L - 12} y={g.cy - 50} width={g.rx * 2 + 24} height={120} rx={46} fill={color} />;
    if (kind === "ponytail") return <ellipse cx={R + 16} cy={g.cy + 30} rx={26} ry={58} fill={color} />;
    if (kind === "ponytail_high") return <ellipse cx={R + 8} cy={top + 30} rx={24} ry={64} fill={color} transform={`rotate(24 ${R + 8} ${top + 30})`} />;
    if (kind === "curly") return (
      <g fill={color}>{[-1.0, -0.6, -0.2, 0.2, 0.6, 1.0].map((k, i) => (
        <circle key={i} cx={g.cx + k * (g.rx + 6)} cy={g.cy - g.ry * 0.55 - (1 - Math.abs(k)) * 26} r={30} />))}</g>
    );
    return null;
  }
  switch (kind) {
    case "buzz": return <path d={`M${L + 2},${g.cy - 14} Q${g.cx},${top - 10} ${R - 2},${g.cy - 14} Q${g.cx},${top + 10} ${L + 2},${g.cy - 14} Z`} fill={color} opacity={0.9} />;
    case "bun": return <g>{cap}<circle cx={g.cx} cy={top - 22} r={30} fill={color} /></g>;
    case "swept": return <g>{cap}<path d={`M${g.cx - 20},${top - 10} Q${R + 30},${top - 30} ${R + 6},${g.cy - 30} Q${g.cx + 10},${top + 6} ${g.cx - 20},${top - 10} Z`} fill={color} /></g>;
    case "side_part": return <g>{cap}<path d={`M${L - 4},${g.cy - 8} Q${L + 6},${top} ${g.cx - 22},${top - 12} L${g.cx - 18},${top + 20} Q${L + 20},${top + 30} ${L - 4},${g.cy - 8} Z`} fill={shade(color, 0.15)} /></g>;
    case "twists": return <g>{cap}{[-0.7, -0.35, 0, 0.35, 0.7].map((k, i) => (
      <rect key={i} x={g.cx + k * g.rx - 9} y={top - 34} width={18} height={40} rx={9} fill={color} />))}</g>;
    case "curly": return <g>{cap}{[-0.5, 0, 0.5].map((k, i) => <circle key={i} cx={g.cx + k * g.rx} cy={top - 4} r={24} fill={color} />)}</g>;
    case "beanie": return (
      <g>
        <path d={`M${L - 6},${g.cy - 20} Q${L - 6},${top - 34} ${g.cx},${top - 34} Q${R + 6},${top - 34} ${R + 6},${g.cy - 20} Z`} fill={accent} />
        <rect x={L - 10} y={g.cy - 36} width={g.rx * 2 + 20} height={26} rx={12} fill={shade(accent, 0.18)} />
        <circle cx={g.cx} cy={top - 38} r={14} fill={shade(accent, 0.18)} />
      </g>
    );
    case "cap": return (
      <g>
        <path d={`M${L - 4},${g.cy - 22} Q${L - 4},${top - 26} ${g.cx},${top - 26} Q${R + 4},${top - 26} ${R + 4},${g.cy - 22} Z`} fill={primary} />
        <rect x={L - 30} y={g.cy - 30} width={50} height={14} rx={7} fill={shade(primary, 0.25)} />
        <circle cx={g.cx} cy={top - 24} r={7} fill={shade(primary, 0.3)} />
      </g>
    );
    case "long": case "bob": case "ponytail": case "ponytail_high": case "short": default:
      return cap;
  }
}

// ----------------------------------------------------------------- the face

function Face({ head, ink, state, t, since, seed, skin }: {
  head: string; ink: string; state: AvatarState; t: number; since: number; seed: number; skin: string;
}) {
  const g = headGeom(head);
  const react = state === "reacting" ? ease.outBack(clamp(since / 0.25), 1.8) : 0;
  const lid = blink(t, seed);
  const eyeY = g.cy + 4;
  const eyeR = 9 + 3 * react;
  const brow = 18 + 9 * react;
  const mouthY = g.cy + 44;
  let mouth: ReactNode;
  if (state === "talking") {
    const o = mouthOpen(t, seed);
    mouth = <ellipse cx={g.cx} cy={mouthY} rx={14 + 4 * o} ry={3 + 13 * o} fill={shade(ink, 0)} />;
  } else if (state === "reacting") {
    mouth = <ellipse cx={g.cx} cy={mouthY + 2} rx={11} ry={4 + 10 * react} fill={ink} />;
  } else {
    mouth = <path d={`M${g.cx - 18},${mouthY - 2} Q${g.cx},${mouthY + 12} ${g.cx + 18},${mouthY - 2}`} fill="none" stroke={ink} strokeWidth={6} strokeLinecap="round" />;
  }
  return (
    <g>
      {[-1, 1].map((s) => (
        <g key={s}>
          <ellipse cx={g.cx + s * 30} cy={eyeY} rx={eyeR * 0.85} ry={Math.max(1.2, eyeR * (1 - 0.9 * lid))} fill={ink} />
          <path d={`M${g.cx + s * 30 - 14},${eyeY - brow} Q${g.cx + s * 30},${eyeY - brow - 6 - 4 * react} ${g.cx + s * 30 + 14},${eyeY - brow + (s * react * 2)}`}
                fill="none" stroke={ink} strokeWidth={5.5} strokeLinecap="round" />
        </g>
      ))}
      <ellipse cx={g.cx - 46} cy={g.cy + 30} rx={11} ry={6} fill={shade(skin, 0.12)} opacity={0.55} />
      <ellipse cx={g.cx + 46} cy={g.cy + 30} rx={11} ry={6} fill={shade(skin, 0.12)} opacity={0.55} />
      {mouth}
    </g>
  );
}

// -------------------------------------------------------------- accessories

function Accessory({ kind, p, head, skin }: {
  kind: string; p: AvatarSpec["palette"]; head: string; skin: string;
}) {
  const g = headGeom(head);
  const L = g.cx - g.rx, R = g.cx + g.rx;
  switch (kind) {
    case "glasses": return (
      <g fill="none" stroke={p.ink} strokeWidth={5}>
        <circle cx={g.cx - 30} cy={g.cy + 4} r={19} /><circle cx={g.cx + 30} cy={g.cy + 4} r={19} />
        <path d={`M${g.cx - 11},${g.cy + 2} L${g.cx + 11},${g.cy + 2}`} />
      </g>
    );
    case "headset": return (
      <g>
        <path d={`M${L - 6},${g.cy} Q${L - 6},${g.cy - g.ry - 26} ${g.cx},${g.cy - g.ry - 26} Q${R + 6},${g.cy - g.ry - 26} ${R + 6},${g.cy}`} fill="none" stroke={p.ink} strokeWidth={9} />
        <rect x={L - 18} y={g.cy - 18} width={22} height={40} rx={10} fill={p.accent} />
        <path d={`M${L - 8},${g.cy + 18} Q${L + 6},${g.cy + 52} ${g.cx - 26},${g.cy + 48}`} fill="none" stroke={p.ink} strokeWidth={5} />
        <circle cx={g.cx - 26} cy={g.cy + 48} r={7} fill={p.accent} />
      </g>
    );
    case "lanyard": return (
      <g>
        <path d="M146,262 L180,330 L214,262" fill="none" stroke={p.accent} strokeWidth={8} />
        <rect x={160} y={326} width={40} height={52} rx={8} fill={C.white} stroke={p.accent} strokeWidth={5} />
      </g>
    );
    case "scarf": return (
      <g fill={p.accent}>
        <rect x={120} y={248} width={120} height={34} rx={16} />
        <rect x={200} y={262} width={30} height={80} rx={12} />
      </g>
    );
    case "notebook": return <g><rect x={238} y={322} width={70} height={92} rx={8} fill={p.accent} /><rect x={238} y={322} width={12} height={92} fill={shade(p.accent, 0.25)} /></g>;
    case "clipboard": return <g><rect x={234} y={316} width={74} height={98} rx={8} fill={p.secondary} stroke={p.ink} strokeWidth={4} /><rect x={256} y={308} width={30} height={16} rx={5} fill={p.ink} /><path d="M248,348 L294,348 M248,368 L284,368 M248,388 L290,388" stroke={p.ink} strokeWidth={4} /></g>;
    case "pencil": return <g transform={`rotate(-30 ${R + 8} ${g.cy - 20})`}><rect x={R} y={g.cy - 40} width={12} height={58} rx={4} fill={p.accent} /><path d={`M${R},${g.cy + 18} L${R + 6},${g.cy + 30} L${R + 12},${g.cy + 18} Z`} fill={skin} /></g>;
    case "watch": return <g><rect x={58} y={392} width={34} height={22} rx={6} fill={p.ink} /><circle cx={75} cy={403} r={8} fill={p.accent} /></g>;
    case "toolbelt": return <g><rect x={80} y={404} width={200} height={20} fill={p.ink} /><rect x={104} y={398} width={40} height={30} rx={6} fill={p.accent} /><rect x={214} y={398} width={40} height={30} rx={6} fill={p.accent} /></g>;
    case "vest": return <g fill={p.secondary} opacity={0.95}><path d="M86,272 L150,272 L170,420 L86,420 Z" /><path d="M274,272 L210,272 L190,420 L274,420 Z" /></g>;
    case "blazer": return <g><path d="M150,262 L180,330 L150,420 L96,420 L104,276 Z" fill={shade(p.primary, 0.25)} /><path d="M210,262 L180,330 L210,420 L264,420 L256,276 Z" fill={shade(p.primary, 0.25)} /><rect x={226} y={300} width={22} height={10} rx={3} fill={p.accent} /></g>;
    case "bag": return <path d="M110,268 L262,410" stroke={p.accent} strokeWidth={14} strokeLinecap="round" />;
    case "beard": return <path d={`M${g.cx - 62},${g.cy + 16} Q${g.cx - 58},${g.cy + g.ry + 22} ${g.cx},${g.cy + g.ry + 26} Q${g.cx + 58},${g.cy + g.ry + 22} ${g.cx + 62},${g.cy + 16} Q${g.cx + 30},${g.cy + 66} ${g.cx},${g.cy + 64} Q${g.cx - 30},${g.cy + 66} ${g.cx - 62},${g.cy + 16} Z`} fill={p.secondary === "#FFF3D9" ? shade(skin, 0.45) : shade(skin, 0.5)} />;
    case "hivis": return <g><rect x={110} y={270} width={22} height={150} fill={p.accent} /><rect x={228} y={270} width={22} height={150} fill={p.accent} /><rect x={110} y={350} width={140} height={14} fill="#E2E4EF" /></g>;
    case "hoodie": return <g><path d="M118,262 Q180,236 242,262 L232,290 Q180,272 128,290 Z" fill={shade(p.primary, 0.18)} /><path d="M164,284 L160,330 M196,284 L200,330" stroke={p.accent} strokeWidth={5} strokeLinecap="round" /><rect x={110} y={360} width={140} height={10} fill={p.accent} /></g>;
    case "cardigan": return <g><path d="M180,276 L148,420 L100,420 L104,280 Z" fill={p.secondary} /><path d="M180,276 L212,420 L260,420 L256,280 Z" fill={p.secondary} />{[316, 350, 384].map((y) => <circle key={y} cx={166 + (y - 316) * 0.0} cy={y} r={5} fill={p.ink} />)}<ellipse cx={92} cy={380} rx={14} ry={22} fill={shade(p.secondary, 0.15)} /></g>;
    case "track_jacket": return <g><path d="M70,300 L110,272 M290,300 L250,272" stroke={p.accent} strokeWidth={10} strokeLinecap="round" /><path d="M180,272 L180,420" stroke={p.secondary} strokeWidth={6} /></g>;
    default: return null;
  }
}

// ---------------------------------------------------------------- the whole

/** One avatar, drawn in its AVATAR_BOX (360 x 420) and scaled to `size`
 * (height). `flip` mirrors it so two avatars face each other. */
export function Avatar({ spec, state, t, since = 99, size = 420, flip = false, outline = "none" }: {
  spec: AvatarSpec; state: AvatarState; t: number; since?: number; size?: number; flip?: boolean;
  /** A stroke round the body, so a character never melts into a field of its
   * own colour (the host is blue; so is the blue field). */
  outline?: string;
}) {
  const seed = seedOf(spec.id);
  const skin = SKINS[spec.skin] ?? SKINS.s3;
  const p = spec.palette;
  const breathe = Math.sin((t + seed * 0.1) * Math.PI * 2 / 3.2);
  const talking = state === "talking";
  const react = state === "reacting" ? ease.outCubic(clamp(since / 0.25)) : 0;
  const bob = talking ? Math.sin(t * 7.3 + seed) * 4 + Math.abs(Math.sin(t * 2.1)) * 3 : breathe * 2.5;
  const tilt = (talking ? Math.sin(t * 2.3 + seed) * 2.5 : 0) + react * 7;
  const gesture = talking ? Math.sin(t * 3.1 + seed) * 0.5 + 0.5 : 0;
  const hand = shade(skin, 0.05);
  const w = AVATAR_BOX.w, h = AVATAR_BOX.h;
  const scale = size / h;
  const body = p.primary;
  // Hair takes the secondary colour unless that is a light tint, then ink.
  const hair = luminance(p.secondary) > 0.62 ? p.ink : p.secondary;
  return (
    <svg width={w * scale} height={size} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", overflow: "hidden" }}
         aria-label={`${spec.name}, ${state}`}>
      <g transform={flip ? `translate(${w},0) scale(-1,1)` : undefined}>
        <ellipse cx={180} cy={416} rx={130} ry={10} fill="rgba(9,16,37,0.18)" />
        <g transform={`translate(0 ${420 + breathe * 1.2}) scale(1 ${1 + breathe * 0.006}) translate(0 -420)`}>
          <Body kind={spec.body} color={body} dark={shade(body, 0.22)} outline={outline} />
          {spec.accessories.filter((a) => ["vest", "blazer", "cardigan", "hivis", "track_jacket", "hoodie", "lanyard", "toolbelt", "bag", "notebook", "clipboard", "watch", "scarf"].includes(a))
            .map((a) => <Accessory key={a} kind={a} p={p} head={spec.head} skin={skin} />)}
          {/* hands: the near one gestures while talking */}
          <circle cx={84} cy={404 - gesture * 10} r={17} fill={hand} />
          <circle cx={276} cy={404 - gesture * 64} r={17} fill={hand}
                  transform={`rotate(${-gesture * 14} 276 ${404 - gesture * 64})`} />
          <rect x={160} y={226} width={40} height={42} rx={14} fill={shade(skin, 0.08)} />
        </g>
        <g transform={`translate(0 ${bob}) rotate(${tilt} 180 230)`}>
          <Hair kind={spec.hair} color={hair}
                accent={p.accent} primary={p.primary} head={spec.head} layer="back" />
          <Head kind={spec.head} skin={skin} />
          <Hair kind={spec.hair} color={hair}
                accent={p.accent} primary={p.primary} head={spec.head} layer="front" />
          <Face head={spec.head} ink={p.ink} state={state} t={t} since={since} seed={seed} skin={skin} />
          {spec.accessories.filter((a) => ["glasses", "headset", "pencil", "beard"].includes(a))
            .map((a) => <Accessory key={a} kind={a} p={p} head={spec.head} skin={skin} />)}
          {state === "reacting" && (
            <g stroke={p.accent} strokeWidth={7} strokeLinecap="round" opacity={clamp(1.6 - since)}>
              {[-38, 0, 38].map((a, i) => {
                const r0 = 104 + 10 * react, r1 = 128 + 16 * react;
                const rad = ((a - 90) * Math.PI) / 180;
                return <line key={i} x1={180 + Math.cos(rad) * r0} y1={160 + Math.sin(rad) * r0}
                             x2={180 + Math.cos(rad) * r1} y2={160 + Math.sin(rad) * r1} />;
              })}
            </g>
          )}
        </g>
      </g>
    </svg>
  );
}

/** The speaker's name tag under an avatar: role and name; the talking one
 * lights up in the field's accent. */
export function NameTag({ name, role, active, accent, dark }: {
  name: string; role: string; active: boolean; accent: string; dark: boolean;
}) {
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 12, padding: "10px 22px", borderRadius: 999,
                  background: active ? accent : dark ? "rgba(255,255,255,0.12)" : "rgba(21,25,54,0.08)",
                  color: active ? C.ink : dark ? C.white : C.ink, fontWeight: 800, fontSize: 28, whiteSpace: "nowrap" }}>
      {name}
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 18, letterSpacing: 2,
                     opacity: 0.75 }}>{role.replace("_", " ")}</span>
    </div>
  );
}
