// Language identities in the motion player (RESTYLE_TO_MOTION_REELS.md,
// phase 3 badges). Motion reels draw no people, like both reference reels:
// a reel's language is carried by an IDENTITY — a signature colour and an
// original geometric symbol (shorts/motion_identities.yaml) — and its two
// speakers, when it has two, are circular BADGES with chat bubbles.
//
// Every colour drawn on a field is the identity's tone FOR that field
// (on_dark on navy and blue, on_light on paper and yellow), which shorts/
// motion_identities.py guarantees reaches 3:1 there — for symbols, waveforms
// and large titles. SMALL TEXT reaches 4.5:1: role labels use the text tones
// (text_on_dark / text_on_light), and bubble words use contrast.ts's bubble
// colours, whose "dim" for upcoming and older words still reaches 4.5:1.
// Flat shapes, design tokens, Anton for display. PURE IN t: no CSS
// animation, no timers.

import type { CSSProperties, ReactNode } from "react";
import { At } from "../Stage";
import { C, FONT, theme, type FieldName } from "../tokens";
import { clamp, ease, hash3, seg } from "../time";
import { bubbleColours, textToneOn } from "./contrast";

export interface IdentityShape {
  rect?: number[]; circle?: number[]; path?: string; r?: number; stroke?: number; tone?: "main" | "soft";
}
export interface IdentitySpec {
  id: string; name: string; colour: string; on_dark: string; on_light: string; file: string;
  /** 4.5:1 tones for small text (absent in plans written before them) */
  text_on_dark?: string; text_on_light?: string;
  symbol: IdentityShape[];
}

/** The identity's colour as drawn on `field`: readable there (>= 3:1). */
export function toneOn(spec: IdentitySpec, field: FieldName): string {
  return theme(field).dark ? spec.on_dark : spec.on_light;
}

/** Ink or white, whichever reads on a fill of `fill`'s lightness: the tone
 * drawn on a dark field is light (ink on it), on a light field dark (white). */
function inkOn(field: FieldName): string {
  return theme(field).dark ? C.ink : C.white;
}

/** The symbol: its shapes on a 100 x 100 grid, scaled to `size`, in one
 * colour (soft shapes at 35 %). `draw` 0..1 grows it in, shape by shape. */
export function IdentitySymbol({ spec, size, colour, draw = 1, style }: {
  spec: IdentitySpec; size: number; colour: string; draw?: number; style?: CSSProperties;
}) {
  const n = spec.symbol.length;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ display: "block", overflow: "visible", ...style }}
         aria-label={`${spec.name} symbol`}>
      {spec.symbol.map((s, i) => {
        const p = ease.outBack(clamp(draw * (n + 1) - i), 1.6);
        if (p <= 0) return null;
        const op = (s.tone === "soft" ? 0.35 : 1) * clamp(p * 1.5);
        const filled = s.stroke == null && !s.path;
        const paint = filled ? { fill: colour } : { fill: "none", stroke: colour, strokeWidth: s.stroke,
                                                    strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
        let cx = 50, cy = 50;
        if (s.rect) { cx = s.rect[0] + s.rect[2] / 2; cy = s.rect[1] + s.rect[3] / 2; }
        if (s.circle) { cx = s.circle[0]; cy = s.circle[1]; }
        const tf = `translate(${cx} ${cy}) scale(${p}) translate(${-cx} ${-cy})`;
        if (s.rect) return <rect key={i} x={s.rect[0]} y={s.rect[1]} width={s.rect[2]} height={s.rect[3]} rx={s.r ?? 0}
                                 opacity={op} transform={tf} {...paint} />;
        if (s.circle) return <circle key={i} cx={s.circle[0]} cy={s.circle[1]} r={s.circle[2]} opacity={op} transform={tf} {...paint} />;
        return <path key={i} d={s.path} opacity={op} transform={tf} {...paint} />;
      })}
    </svg>
  );
}

/** The language badge that sits in the top-right corner for the whole reel:
 * the symbol in a small tile and the language's name. */
export function LanguageBadge({ spec, field, right, top, p = 1 }: {
  spec: IdentitySpec; field: FieldName; right: number; top: number; p?: number;
}) {
  const th = theme(field);
  const tone = toneOn(spec, field);
  return (
    <div style={{ position: "absolute", right, top, opacity: clamp(p), display: "flex", alignItems: "center",
                  gap: 12, padding: "8px 18px 8px 10px", borderRadius: 999, background: th.surface,
                  border: `3px solid ${th.dark ? "rgba(255,255,255,0.12)" : C.line}` }}>
      <IdentitySymbol spec={spec} size={34} colour={tone} />
      <span style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 22, letterSpacing: 2.4, color: th.surfaceInk,
                     textTransform: "uppercase" }}>{spec.name}</span>
    </div>
  );
}

/** The hook's language mark: the symbol large, then a chip such as
 * "REACT · INTERVIEW" above the hook line. Laid out in its box (Python's
 * layout_scene), entering over ~0.6 s. */
export function IdentityTitle({ spec, label, field, x, y, t }: {
  spec: IdentitySpec; label: string; field: FieldName; x: number; y: number; t: number;
}) {
  const tone = toneOn(spec, field);
  const draw = clamp(t / 0.5);
  const chip = ease.outCubic(seg(t, 0.35, 0.3));
  return (
    <At x={x} y={y}>
      <IdentitySymbol spec={spec} size={170} colour={tone} draw={draw} />
      <div style={{ marginTop: 26, display: "inline-flex", alignItems: "center", gap: 14, padding: "12px 24px",
                    borderRadius: 999, background: tone, color: inkOn(field), opacity: chip,
                    transform: `translateY(${(1 - chip) * 14}px)` }}>
        <span style={{ fontFamily: FONT.display, fontSize: 40, lineHeight: 1, letterSpacing: 1.5, textTransform: "uppercase" }}>
          {spec.name}{label ? ` · ${label}` : ""}
        </span>
      </div>
    </At>
  );
}

/** A 1-second intro sting: the symbol builds in its colour on navy, the name
 * rises under it, then everything settles. Optional (MOTION_INTRO_STING). */
export function IdentitySting({ spec, t }: { spec: IdentitySpec; t: number }) {
  const draw = clamp(t / 0.55);
  const name = ease.outCubic(seg(t, 0.45, 0.3));
  const out = 1 - seg(t, 0.85, 0.15);
  return (
    <div style={{ position: "absolute", inset: 0, background: "#091025", display: "grid", placeItems: "center", opacity: out }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 34 }}>
        <IdentitySymbol spec={spec} size={300} colour={spec.on_dark} draw={draw}
                        style={{ transform: `rotate(${(1 - ease.outCubic(draw)) * -12}deg)` }} />
        <div style={{ fontFamily: FONT.display, fontSize: 96, lineHeight: 1, color: C.white, textTransform: "uppercase",
                      opacity: name, transform: `translateY(${(1 - name) * 24}px)` }}>{spec.name}</div>
      </div>
    </div>
  );
}

/** A small waveform: 5 bars whose heights follow a fixed hash of t — the
 * active speaker's tell. `level` 0 holds it flat (the listener). */
export function Waveform({ t, colour, level = 1, height = 26 }: { t: number; colour: string; level?: number; height?: number }) {
  const bars = [0, 1, 2, 3, 4].map((i) => {
    const k = Math.floor(t * 9) + i * 17;
    const v = 0.25 + 0.75 * (0.5 * hash3(5, k) + 0.5 * hash3(9, k + 1) * Math.abs(Math.sin(t * 7 + i)));
    return 0.22 + (v - 0.22) * clamp(level);
  });
  return (
    <svg width={42} height={height} viewBox={`0 0 42 ${height}`} style={{ display: "block" }}>
      {bars.map((v, i) => <rect key={i} x={i * 9} y={(height - v * height) / 2} width={5} height={v * height} rx={2.5} fill={colour} />)}
    </svg>
  );
}

export interface CastMember { role: string; side: "left" | "right"; label: string; voice_slot: string; identity: IdentitySpec }

/** A speaker as a circular badge: the host shows its role's initial, the
 * language speaker its language's symbol. Active: a glowing ring and a
 * waveform; otherwise still. */
export function SpeakerBadge({ member, field, active, t, size = 112 }: {
  member: CastMember; field: FieldName; active: boolean; t: number; size?: number;
}) {
  const tone = toneOn(member.identity, field);
  const glow = active ? 0.55 + 0.45 * Math.sin(t * 5.2) : 0;
  const host = member.identity.id === "host";
  return (
    <div style={{ width: size, height: size, position: "relative", flex: "none" }}>
      {active && (
        <svg width={size + 48} height={size + 48} style={{ position: "absolute", left: -24, top: -24 }}>
          <circle cx={(size + 48) / 2} cy={(size + 48) / 2} r={size / 2 + 10 + 6 * glow} fill="none" stroke={tone}
                  strokeWidth={5} opacity={0.35 + 0.4 * glow} />
          <circle cx={(size + 48) / 2} cy={(size + 48) / 2} r={size / 2 + 4} fill={tone} opacity={0.18} />
        </svg>
      )}
      <div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: tone, display: "grid", placeItems: "center" }}>
        {host
          ? <span style={{ fontFamily: FONT.display, fontSize: size * 0.48, lineHeight: 1, color: inkOn(field) }}>{member.label.charAt(0)}</span>
          : <IdentitySymbol spec={member.identity} size={size * 0.56} colour={inkOn(field)} />}
      </div>
    </div>
  );
}

/** Approximate lines a bubble's text wraps to — computed from characters,
 * never measured from the page, so a frame depends only on t. */
export function bubbleLines(text: string, maxChars: number): number {
  let lines = 1, cur = 0;
  for (const w of text.split(/\s+/).filter(Boolean)) {
    if (cur && cur + 1 + w.length > maxChars) { lines += 1; cur = w.length; }
    else cur += (cur ? 1 : 0) + w.length;
  }
  return lines;
}

export const BUBBLE = { font: 42, lineH: 54, padX: 30, padY: 22, maxW: 720, chars: 31, gap: 26, labelH: 34 } as const;

export function bubbleHeight(text: string): number {
  return BUBBLE.labelH + BUBBLE.padY * 2 + bubbleLines(text, BUBBLE.chars) * BUBBLE.lineH;
}

/** One chat row: the speaker's badge on its side, its role label, and the
 * bubble with the caption's words lit as they are spoken (karaoke). */
export function ChatRow({ member, field, words, active, t, y, fade = 1 }: {
  member: CastMember; field: FieldName; active: boolean; t: number; y: number; fade?: number;
  words: { text: string; start: number; end: number; hl: boolean }[];
}) {
  const th = theme(field);
  const left = member.side === "left";
  const tone = toneOn(member.identity, field);
  const host = member.identity.id === "host";
  const colours = bubbleColours(host, field);
  const older = fade < 1;
  const border = host ? (th.dark ? "rgba(255,255,255,0.16)" : C.line) : tone;
  const text = words.map((w) => w.text).join(" ");
  const rise = 1 - ease.outCubic(clamp((t - (words[0]?.start ?? 0) + 0.25) / 0.3));
  /* Older bubbles recede by their badge and border, never by fading the text:
     every word stays at 4.5:1 against its bubble (contrast.ts). */
  return (
    <div style={{ position: "absolute", left: 54, right: 54, top: y, display: "flex", gap: 22,
                  flexDirection: left ? "row" : "row-reverse", alignItems: "flex-start",
                  transform: `translateY(${rise * 30}px)` }}>
      <div style={{ marginTop: BUBBLE.labelH - 4, opacity: fade }}>
        <SpeakerBadge member={member} field={field} active={active} t={t} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", alignItems: left ? "flex-start" : "flex-end", maxWidth: BUBBLE.maxW }}>
        <div style={{ height: BUBBLE.labelH, display: "flex", alignItems: "center", gap: 12, flexDirection: left ? "row" : "row-reverse" }}>
          <span style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 20, letterSpacing: 3, textTransform: "uppercase",
                         color: textToneOn(member.identity, field) }}>{member.label}</span>
          {active && <Waveform t={t} colour={tone} height={20} />}
        </div>
        <div style={{ background: colours.bg, border: `3px solid ${border}`, borderColor: older ? "transparent" : undefined, borderRadius: 30,
                      borderTopLeftRadius: left ? 8 : 30, borderTopRightRadius: left ? 30 : 8,
                      padding: `${BUBBLE.padY}px ${BUBBLE.padX}px`, maxWidth: BUBBLE.maxW, boxSizing: "border-box",
                      fontFamily: FONT.body, fontWeight: 750, fontSize: BUBBLE.font, lineHeight: `${BUBBLE.lineH}px`,
                      color: colours.ink, letterSpacing: -0.3 }}>
          {words.map((w, i) => {
            const lit = !older && t >= w.start + Math.min(0.08, (w.end - w.start) / 3);
            return <span key={i} style={{ color: !lit ? colours.dim : w.hl ? colours.accent : colours.ink }}>
              {w.text}{i < words.length - 1 ? " " : ""}</span>;
          })}
          {!text && <span>&nbsp;</span>}
        </div>
      </div>
    </div>
  );
}

/** A labelled colour swatch (the identity registry page). */
export function Swatch({ colour, label, children }: { colour: string; label: string; children?: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, fontFamily: FONT.mono }}>
      <span style={{ width: 22, height: 22, borderRadius: 6, background: colour, border: "1px solid rgba(255,255,255,0.2)" }} />
      <span>{label} {colour}</span>{children}
    </div>
  );
}
