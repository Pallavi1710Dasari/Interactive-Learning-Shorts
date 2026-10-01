// OBJECT SET 1 — the objects of the first reference reel,
// docs/reference/reference_reel.html (RESTYLE_TO_MOTION_REELS.md section 3),
// redrawn in design units (the reference is 360 wide; here 1080, so x3) and
// made time-driven: every animation the reference ran with CSS keyframes and
// setTimeout is a function of a `t` or a progress prop here.
//
// Each object takes a Theme so it works on paper AND on a dark field (cards
// invert on dark: dark surface, light text, same accents — addendum 4.1).

import type { ReactNode } from "react";
import { At, Icon, Overlay } from "../Stage";
import { C, FONT, H, W, theme, type FieldName, type Theme } from "../tokens";
import { clamp, ease, lerp, pathD, pointAt, pulse, seg, type Pt } from "../time";

export type Tone = "bad" | "ok" | "info" | "warn" | "special" | "plain";

/** Fixed colour meanings (spec section 3): coral = failure, mint = success,
 * indigo = the system/info, amber = a change being made, lavender = system-added. */
export function toneColors(tone: Tone, th: Theme): { bg: string; fg: string } {
  switch (tone) {
    case "bad": return { bg: th.dark ? "rgba(242,85,90,0.18)" : C.coralSoft, fg: C.coral };
    case "ok": return { bg: th.dark ? "rgba(23,178,123,0.2)" : C.mintSoft, fg: C.mint };
    case "info": return { bg: th.dark ? "rgba(255,255,255,0.12)" : C.indigoSoft, fg: th.dark ? C.white : C.indigo };
    case "warn": return { bg: th.dark ? "rgba(255,181,36,0.18)" : C.amberSoft, fg: th.dark ? C.amber : C.amberInk };
    case "special": return { bg: th.dark ? "rgba(185,168,255,0.22)" : C.specialSoft, fg: th.dark ? C.special : "#5B45D6" };
    default: return { bg: th.surface, fg: th.surfaceInk };
  }
}

/** The pop-in every object uses: rise 30 units and scale .94 -> 1 (the
 * reference's `pop` keyframes), as a function of progress p. */
export function popStyle(p: number) {
  const q = ease.outBack(clamp(p), 1.2);
  return { opacity: clamp(p * 1.6), transform: `translateY(${(1 - q) * 30}px) scale(${lerp(0.94, 1, q)})` };
}

const shadow = (th: Theme) => (th.dark ? "0 30px 60px rgba(0,0,0,0.35)" : "0 30px 60px rgba(21,25,54,0.13)");

/** The dotted canvas behind reference-style shots. */
export function DotGrid({ field }: { field: FieldName }) {
  const th = theme(field);
  const dots: ReactNode[] = [];
  for (let x = 72; x < W; x += 72) for (let y = 504; y < 1680; y += 72)
    dots.push(<circle key={`${x}-${y}`} cx={x} cy={y} r={2.7} fill={th.dark ? "#FFFFFF" : C.grey} opacity={th.dark ? 0.12 : 0.45} />);
  return <Overlay>{dots}</Overlay>;
}

export function StatusPill({ x, y, text, tone, icon, field, p = 1, size = 33 }: {
  x: number; y: number; text: string; tone: Tone; icon?: string; field: FieldName; p?: number; size?: number;
}) {
  const th = theme(field);
  const { bg, fg } = toneColors(tone, th);
  return (
    <At x={x} y={y} center style={popStyle(p)}>
      <div style={{ display: "flex", alignItems: "center", gap: size * 0.4, background: bg, color: fg,
                    padding: `${size * 0.42}px ${size * 0.85}px`, borderRadius: 999, whiteSpace: "nowrap",
                    fontWeight: 800, fontSize: size }}>
        {icon && <Icon name={icon} size={size * 1.15} color={fg} stroke={2.4} />}
        {text}
      </div>
    </At>
  );
}

export function TriggerChip({ x, y, label, field, p = 1, firing = 0 }: {
  x: number; y: number; label: string; field: FieldName; p?: number; firing?: number;
}) {
  const th = theme(field);
  const { bg, fg } = toneColors("warn", th);
  return (
    <At x={x} y={y} center style={popStyle(p)}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, background: bg, color: fg,
                    padding: "16px 28px", borderRadius: 999, fontFamily: FONT.mono, fontWeight: 700,
                    fontSize: 33, transform: `scale(${1 + 0.12 * firing})`,
                    boxShadow: firing ? `0 0 0 ${10 * firing}px rgba(255,181,36,${0.25 * firing})` : "none" }}>
        <Icon name="bolt" size={38} color={fg} stroke={2.4} />{label}
      </div>
    </At>
  );
}

export function IconTile({ x, y, size, icon, tone, field, p = 1 }: {
  x: number; y: number; size: number; icon: string; tone: Tone; field: FieldName; p?: number;
}) {
  const { bg, fg } = toneColors(tone, theme(field));
  return (
    <At x={x} y={y} center style={popStyle(p)}>
      <div style={{ width: size, height: size, borderRadius: size * 0.28, background: bg,
                    display: "grid", placeItems: "center" }}>
        <Icon name={icon} size={size * 0.5} color={fg} />
      </div>
    </At>
  );
}

/** A phone with a social post — the reference's hook and payoff device.
 * `tapAge`: seconds since the last tap (ripple + pulse), `failAge`: seconds
 * since a failed tap (coral shake), `liked`: the heart's success state. */
export function DeviceMock({ x, y, likes, liked = false, tapAge = 99, failAge = 99, p = 1, field }: {
  x: number; y: number; likes: number; liked?: boolean; tapAge?: number; failAge?: number;
  p?: number; field: FieldName;
}) {
  const w = 528, h = 1008;
  const ripple = seg(tapAge, 0, 0.65);
  const heartPulse = pulse(tapAge, 0, 0.45);
  const shake = failAge < 0.45 ? Math.sin(failAge * 40) * 15 * (1 - failAge / 0.45) : 0;
  const countColor = failAge < 0.65 ? C.coral : C.ink;
  // The liked heart is a success, so mint — never coral (decision 2026-09-30).
  const heart = liked ? C.mint : C.ink;
  return (
    <At x={x - w / 2} y={y} style={popStyle(p)}>
      <div style={{ width: w, height: h, borderRadius: 96, background: C.ink, padding: 21,
                    boxShadow: shadow(theme(field)), position: "relative" }}>
        <div style={{ position: "absolute", left: w / 2 - 78, top: 42, width: 156, height: 42, borderRadius: 21, background: C.ink, zIndex: 2 }} />
        <div style={{ width: "100%", height: "100%", borderRadius: 75, background: C.surf, position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", left: 45, top: 120, fontSize: 45, fontWeight: 800, color: C.ink }}>Feed</div>
          <div style={{ position: "absolute", left: 45, top: 210, width: 66, height: 66, borderRadius: 33,
                        background: `linear-gradient(135deg, ${C.indigo}, ${C.amber})` }} />
          <div style={{ position: "absolute", left: 130, top: 212, fontSize: 31, fontWeight: 700, color: C.ink }}>rahul.codes</div>
          <div style={{ position: "absolute", left: 130, top: 250, fontSize: 27, fontWeight: 600, color: C.sub }}>2 min ago</div>
          <div style={{ position: "absolute", left: 30, top: 300, right: 30, height: 396, borderRadius: 42,
                        background: "linear-gradient(135deg, #DCD7FF, #FFE7B8)" }} />
          <div style={{ position: "absolute", left: 50, top: 732, width: 72, height: 72 }}>
            <div style={{ position: "absolute", inset: -24, borderRadius: "50%", background: C.indigo,
                          opacity: ripple > 0 && ripple < 1 ? 0.8 * (1 - ripple) : 0,
                          transform: `scale(${0.4 + 1.4 * ripple})` }} />
            <div style={{ transform: `scale(${1 + 0.14 * heartPulse})` }}>
              <Icon name="heart" size={72} color={heart} fill={liked ? C.mint : "none"} />
            </div>
          </div>
          <div style={{ position: "absolute", left: 140, top: 740, fontSize: 39, fontWeight: 800, color: countColor,
                        transform: `translateX(${shake}px)` }}>
            {likes} {likes === 1 ? "like" : "likes"}
          </div>
          <div style={{ position: "absolute", left: 40, top: 840, width: 336, height: 21, borderRadius: 11, background: C.line }} />
          <div style={{ position: "absolute", left: 40, top: 882, width: 234, height: 21, borderRadius: 11, background: C.line }} />
        </div>
      </div>
    </At>
  );
}

/** The component card — "what React renders". `sweep`: 0..1 progress of a
 * render pass (the indigo sweep and the body dimming mid-pass). */
export function EntityCard({ x, y, w = 900, h = 528, label, value, valueTone = "plain", unit = "likes",
                             code, codeTone = "plain", note = "", renderCount = 1, sweep = -1, p = 1, field }: {
  x: number; y: number; w?: number; h?: number; label: string; value: string | number;
  valueTone?: Tone; unit?: string; code?: string; codeTone?: Tone; note?: string;
  renderCount?: number; sweep?: number; p?: number; field: FieldName;
}) {
  const th = theme(field);
  const sweeping = sweep >= 0 && sweep < 1;
  const bodyOpacity = sweeping ? (sweep > 0.2 && sweep < 0.56 ? 0.15 : 1) : 1;
  const valColor = valueTone === "bad" ? C.coral : valueTone === "info" ? C.indigo : th.surfaceInk;
  const row = toneColors(codeTone, th);
  return (
    <At x={x} y={y} style={popStyle(p)}>
      <div style={{ width: w, height: h, borderRadius: 54, background: th.surface, boxShadow: shadow(th),
                    position: "relative", overflow: "hidden", color: th.surfaceInk }}>
        <div style={{ position: "absolute", left: 36, top: 36, padding: "10px 24px", borderRadius: 999,
                      background: toneColors("info", th).bg, color: toneColors("info", th).fg,
                      fontFamily: FONT.mono, fontWeight: 700, fontSize: 33 }}>{label}</div>
        <div style={{ position: "absolute", right: 40, top: 48, display: "flex", alignItems: "center", gap: 12,
                      fontSize: 33, fontWeight: 700, color: th.surfaceDim }}>
          <span style={{ width: 21, height: 21, borderRadius: 11, background: sweeping ? C.indigo : C.mint }} />
          Render {renderCount}
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 138, height: 4, background: th.surfaceLine }} />
        <div style={{ opacity: bodyOpacity }}>
          <div style={{ position: "absolute", left: 60, top: 174, fontSize: 31, fontWeight: 700, color: th.surfaceDim }}>On screen</div>
          <div style={{ position: "absolute", left: 60, top: 230, display: "flex", alignItems: "baseline", gap: 18 }}>
            <span style={{ fontSize: 90, fontWeight: 800, color: valColor, lineHeight: 1 }}>{value}</span>
            <span style={{ fontSize: 36, fontWeight: 700, color: th.surfaceDim }}>{unit}</span>
          </div>
          {code !== undefined && (
            <div style={{ position: "absolute", left: 42, right: 42, bottom: 36, height: 96, borderRadius: 27,
                          background: codeTone === "plain" ? (th.dark ? "rgba(255,255,255,0.06)" : "#F3F4F9") : row.bg,
                          display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 36px" }}>
              <span style={{ fontFamily: FONT.mono, fontWeight: 600, fontSize: 37, color: codeTone === "plain" ? th.surfaceInk : row.fg }}>{code}</span>
              <span style={{ fontSize: 31, fontWeight: 700, color: th.surfaceDim }}>{note}</span>
            </div>
          )}
        </div>
        {sweeping && (
          <div style={{ position: "absolute", left: 0, right: 0, height: 210, top: -210 + (h + 210) * ease.inOutCubic(sweep),
                        background: "linear-gradient(to bottom, rgba(91,75,245,0), rgba(91,75,245,0.22) 75%, rgba(91,75,245,0.7))" }} />
        )}
      </div>
    </At>
  );
}

/** The system panel — the thing that remembers or decides ("React"). */
export function SystemPanel({ x, y, w = 840, h = 318, title, status, statusTone = "plain", slot, glow = 0, p = 1, field }: {
  x: number; y: number; w?: number; h?: number; title: string; status: string; statusTone?: Tone;
  slot?: { name: string; value: string | number; pulse?: number } | null; glow?: number; p?: number; field: FieldName;
}) {
  const th = theme(field);
  const st = toneColors(statusTone, th);
  return (
    <At x={x} y={y} style={popStyle(p)}>
      <div style={{ width: w, height: h, borderRadius: 54, background: th.surface, boxShadow: shadow(th),
                    position: "relative", color: th.surfaceInk }}>
        <div style={{ position: "absolute", left: 42, top: 36, width: 84, height: 84, borderRadius: 24, background: C.indigo,
                      display: "grid", placeItems: "center" }}>
          <Icon name="memory" size={48} color={C.white} />
        </div>
        <div style={{ position: "absolute", left: 156, top: 52, fontSize: 42, fontWeight: 800 }}>{title}</div>
        <div style={{ position: "absolute", right: 42, top: 45, display: "flex", alignItems: "center", gap: 12,
                      background: statusTone === "plain" ? (th.dark ? "rgba(255,255,255,0.08)" : "#F3F4F9") : st.bg,
                      padding: "12px 26px", borderRadius: 999, fontSize: 31, fontWeight: 700,
                      color: statusTone === "plain" ? th.surfaceDim : st.fg }}>
          <span style={{ width: 21, height: 21, borderRadius: 11, background: statusTone === "plain" ? C.grey : st.fg }} />
          {status}
        </div>
        {slot ? (
          <div style={{ position: "absolute", left: 42, right: 42, top: 156, bottom: 42, borderRadius: 36,
                        background: th.dark ? "rgba(255,255,255,0.06)" : "#F3F4F9", display: "flex",
                        alignItems: "center", justifyContent: "space-between", padding: "0 30px 0 42px" }}>
            <span style={{ fontFamily: FONT.mono, fontSize: 42, fontWeight: 600 }}>{slot.name}</span>
            <span style={{ minWidth: 180, height: 84, borderRadius: 27, background: C.amberSoft, border: `6px solid ${C.amber}`,
                           display: "grid", placeItems: "center", fontSize: 60, fontWeight: 800, color: C.ink,
                           transform: `scale(${1 + 0.14 * (slot.pulse ?? 0)})`,
                           boxShadow: glow ? `0 0 ${80 * glow}px rgba(255,181,36,${0.6 * glow})` : "none" }}>
              {slot.value}
            </span>
          </div>
        ) : (
          <div style={{ position: "absolute", left: 0, right: 0, bottom: 72, textAlign: "center", fontSize: 36,
                        fontWeight: 600, color: C.grey }}>No state stored</div>
        )}
      </div>
    </At>
  );
}

/** A connector between objects, with an optional travelling pulse (`pulse`
 * 0..1 along the line), an optional break (an x where it fails), and an
 * optional draw-on (`draw` 0..1). */
export function Connector({ points, tone = "info", dashed = false, broken = false, pulse: pp = -1, draw = 1, field }: {
  points: Pt[]; tone?: Tone; dashed?: boolean; broken?: boolean; pulse?: number; draw?: number; field: FieldName;
}) {
  const th = theme(field);
  const color = broken ? C.grey : tone === "warn" ? C.amber : tone === "ok" ? C.mint : (th.dark ? C.white : C.indigo);
  let L = 0;
  for (let i = 1; i < points.length; i++) L += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  const mid = pointAt(points, 0.5);
  const dot = pp >= 0 && pp <= 1 ? pointAt(points, ease.inOutQuad(pp)) : null;
  return (
    <Overlay>
      <path d={pathD(points)} fill="none" stroke={color} strokeWidth={7.5} strokeLinecap="round"
            opacity={broken ? 1 : 0.45}
            strokeDasharray={dashed || broken ? "15 18" : `${L} ${L}`}
            strokeDashoffset={dashed || broken ? 0 : L * (1 - clamp(draw))} />
      {broken && (
        <g transform={`translate(${mid[0]},${mid[1]})`}>
          <circle r={36} fill={C.coralSoft} stroke={C.coral} strokeWidth={6} />
          <path d="M-14,-14 L14,14 M14,-14 L-14,14" stroke={C.coral} strokeWidth={7} strokeLinecap="round" />
        </g>
      )}
      {dot && (
        <g transform={`translate(${dot[0]},${dot[1]})`}>
          <circle r={36} fill={color} opacity={0.22} />
          <circle r={16.5} fill={color} />
        </g>
      )}
    </Overlay>
  );
}

export interface CodeToken { text: string; color?: string }
export type CodeLine = CodeToken[];

/** A code editor window. `shown`: how many lines are visible (fractional
 * values pop the next one in); `highlight`: the line under the amber bar. */
export function CodeWindow({ x, y, w = 948, file, lines, shown = Infinity, highlight = -1, p = 1, field }: {
  x: number; y: number; w?: number; file: string; lines: CodeLine[]; shown?: number; highlight?: number;
  p?: number; field: FieldName;
}) {
  const lh = 120;
  const h = 114 + 60 + lines.length * lh;
  return (
    <At x={x} y={y} style={popStyle(p)}>
      <div style={{ width: w, height: h, borderRadius: 48, background: C.code, boxShadow: shadow(theme(field)),
                    position: "relative", overflow: "hidden" }}>
        <div style={{ height: 114, background: C.codeBar, display: "flex", alignItems: "center", gap: 18, padding: "0 42px" }}>
          {[C.coral, C.amber, C.mint].map((c) => <span key={c} style={{ width: 27, height: 27, borderRadius: 14, background: c }} />)}
          <span style={{ marginLeft: 36, fontFamily: FONT.mono, fontSize: 33, fontWeight: 600, color: "#C9CCF0" }}>{file}</span>
        </div>
        {lines.map((line, i) => {
          const q = clamp(shown - i);
          return (
            <div key={i} style={{ position: "absolute", left: 0, right: 0, top: 144 + i * lh, height: lh - 18,
                                  display: "flex", alignItems: "center", ...popStyle(q) }}>
              {highlight === i && <div style={{ position: "absolute", inset: 0, background: "rgba(255,181,36,0.1)", borderLeft: `9px solid ${C.amber}` }} />}
              <span style={{ width: 120, textAlign: "center", fontFamily: FONT.mono, fontSize: 39, color: C.codeDim, position: "relative" }}>{i + 1}</span>
              <span style={{ fontFamily: FONT.mono, fontSize: 43, fontWeight: 500, color: C.codeText, whiteSpace: "pre", position: "relative" }}>
                {line.map((tk, j) => <span key={j} style={{ color: tk.color ?? C.codeText }}>{tk.text}</span>)}
              </span>
            </div>
          );
        })}
      </div>
    </At>
  );
}

/** The title card: series pill, the concept in display weight, the promise,
 * and the icon vocabulary popping in one by one. */
export function TitleCard({ series, title, promise, icons, t }: {
  series: string; title: string; promise: string; icons: { name: string; label: string }[]; t: number;
}) {
  return (
    <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to bottom, #5B4BF5, #4234D6)", color: C.white }}>
      <div style={{ position: "absolute", left: 900, top: 570, width: 720, height: 720, borderRadius: "50%", background: "rgba(255,255,255,0.05)", transform: "translate(-50%,-50%)" }} />
      <At x={W / 2} y={708} center style={popStyle(seg(t, 0, 0.5))}>
        <div style={{ padding: "16px 36px", borderRadius: 999, background: "rgba(255,255,255,0.14)", fontWeight: 700, fontSize: 33, whiteSpace: "nowrap" }}>{series}</div>
      </At>
      <At x={W / 2} y={880} center style={popStyle(seg(t, 0.12, 0.5))}>
        <div style={{ fontSize: 162, fontWeight: 800, letterSpacing: -4.5, whiteSpace: "nowrap" }}>{title}</div>
      </At>
      <At x={W / 2} y={1002} center style={popStyle(seg(t, 0.26, 0.5))}>
        <div style={{ fontSize: 48, fontWeight: 700, color: C.amber, whiteSpace: "nowrap" }}>{promise}</div>
      </At>
      {icons.map((ic, i) => (
        <At key={ic.name} x={270 + i * 270} y={1230} center style={popStyle(seg(t, 0.7 + i * 0.35, 0.5))}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
            <div style={{ width: 180, height: 180, borderRadius: 51, background: C.white, display: "grid", placeItems: "center" }}>
              <Icon name={ic.name} size={84} color={C.indigo} />
            </div>
            <div style={{ fontSize: 36, fontWeight: 700 }}>{ic.label}</div>
          </div>
        </At>
      ))}
    </div>
  );
}

/** The code map card: the real syntax, with each named part tied to what it
 * controls. `active` moves the amber highlight from part to part. */
export function CodeMapCard({ line1, line2, parts, active, t, field }: {
  line1: CodeLine; line2: CodeLine;
  parts: { at: [number, number]; icon: string; tone: Tone; name: string; desc: string }[];
  active: number; t: number; field: FieldName;
}) {
  const th = theme(field);
  const cw = 32.4;
  return (
    <>
      <At x={60} y={528} style={popStyle(seg(t, 0, 0.5))}>
        <div style={{ width: 960, height: 348, borderRadius: 54, background: C.code, boxShadow: shadow(th), position: "relative" }}>
          {active >= 0 && parts[active] && (
            <div style={{ position: "absolute", top: 66, height: 90, borderRadius: 21, background: C.amber,
                          left: 60 + parts[active].at[0] * cw - 12, width: parts[active].at[1] * cw + 24 }} />
          )}
          {[line1, line2].map((line, i) => (
            <div key={i} style={{ position: "absolute", left: 60, top: 78 + i * 114, fontFamily: FONT.mono, fontSize: 54, whiteSpace: "pre" }}>
              {line.map((tk, j) => <span key={j} style={{ color: tk.color ?? C.codeText }}>{tk.text}</span>)}
            </div>
          ))}
        </div>
      </At>
      {parts.map((pt, i) => {
        const { bg, fg } = toneColors(pt.tone, th);
        return (
          <At key={pt.name} x={60} y={954 + i * 240} style={popStyle(i <= active ? 1 : 0)}>
            <div style={{ width: 960, height: 192, borderRadius: 48, background: th.surface, boxShadow: shadow(th),
                          display: "flex", alignItems: "center", gap: 42, padding: "0 48px", color: th.surfaceInk }}>
              <div style={{ width: 120, height: 120, borderRadius: 34, background: bg, display: "grid", placeItems: "center" }}>
                <Icon name={pt.icon} size={60} color={fg} />
              </div>
              <div>
                <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 45 }}>{pt.name}</div>
                <div style={{ fontWeight: 600, fontSize: 37, color: th.surfaceDim }}>{pt.desc}</div>
              </div>
            </div>
          </At>
        );
      })}
    </>
  );
}

/** The fix_story recap: a heading and three icon rows, each popping in. */
export function TakeawayList({ heading, rows, t, field }: {
  heading: string; rows: { icon: string; tone: Tone; line: string; sub: string }[]; t: number; field: FieldName;
}) {
  const th = theme(field);
  return (
    <>
      <At x={84} y={540} style={popStyle(seg(t, 0, 0.5))}>
        <div style={{ fontSize: 66, fontWeight: 800, color: th.ink }}>{heading}</div>
      </At>
      {rows.map((r, i) => {
        const { bg, fg } = toneColors(r.tone, th);
        return (
          <At key={r.line} x={60} y={654 + i * 252} style={popStyle(seg(t, 0.5 + i * 0.9, 0.5))}>
            <div style={{ width: 960, height: 204, borderRadius: 54, background: th.surface, boxShadow: shadow(th),
                          display: "flex", alignItems: "center", gap: 48, padding: "0 54px", color: th.surfaceInk }}>
              <div style={{ width: 126, height: 126, borderRadius: 36, background: bg, display: "grid", placeItems: "center" }}>
                <Icon name={r.icon} size={63} color={fg} />
              </div>
              <div>
                <div style={{ fontWeight: 800, fontSize: 47 }}>{r.line}</div>
                <div style={{ fontWeight: 600, fontSize: 37, color: th.surfaceDim }}>{r.sub}</div>
              </div>
            </div>
          </At>
        );
      })}
    </>
  );
}

/** The end card: "Up next", the next topic, a Follow button, series chips. */
export function EndCard({ upNext, chips, t }: { upNext: string; chips: { label: string; done: boolean }[]; t: number }) {
  return (
    <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to bottom, #5B4BF5, #4234D6)", color: C.white }}>
      <At x={W / 2} y={770} center style={popStyle(seg(t, 0, 0.5))}>
        <div style={{ fontSize: 42, fontWeight: 700, color: C.amber }}>Up next</div>
      </At>
      <At x={W / 2} y={890} center style={popStyle(seg(t, 0.12, 0.5))}>
        <div style={{ fontSize: 120, fontWeight: 800, letterSpacing: -3, whiteSpace: "nowrap" }}>{upNext}</div>
      </At>
      <At x={W / 2} y={1098} center style={popStyle(seg(t, 0.26, 0.5))}>
        <div style={{ padding: "30px 108px", borderRadius: 999, background: C.white, color: C.indigo, fontWeight: 800, fontSize: 48 }}>Follow</div>
      </At>
      {chips.map((c, i) => (
        <At key={c.label} x={216 + i * 324} y={1320} center style={popStyle(seg(t, 1 + i * 0.12, 0.5))}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 30px", borderRadius: 999,
                        background: c.done ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.14)",
                        color: c.done ? C.indigo : C.white, fontFamily: FONT.mono, fontWeight: 700, fontSize: 33, whiteSpace: "nowrap" }}>
            {c.done && <Icon name="check" size={36} color={C.indigo} stroke={2.6} />}{c.label}
          </div>
        </At>
      ))}
    </div>
  );
}

/** Used by the gallery to keep a fixed field when an object has none. */
export const DEFAULT_H = H;
