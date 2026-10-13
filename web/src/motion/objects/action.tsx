// OBJECT SET 3 — ACTION OBJECTS (2026-10-13). The user's rule: "a student with
// zero knowledge should understand what is happening from the visuals alone,
// with the sound off — shown by the right action, not by text". So these
// objects ACT the idea out instead of writing it:
//
//   app_screen   a tiny app: a finger taps its button and the number on
//                screen changes (or stubbornly doesn't) — what the user sees
//   memory_box   a labelled box holding a value: a new value drops in, or the
//                box is wiped back to its start — what the computer remembers
//   flow         steps in a row, something travels from one to the next and
//                each step lights as it arrives — a process, a request
//   compare      the wrong way beside the right way, ✗ and ✓ — a fix
//   cycle        steps on a loop, a dot goes round and round — anything
//                that repeats (re-renders, an event loop, a lifecycle)
//
// Every one is a pure function of t (ages since its actions), drawn from the
// shot's theme so it works on every field and in every design. Text on them
// is only short labels.

import { At, Icon } from "../Stage";
import { C, FONT, theme, type FieldName, type Theme } from "../tokens";
import { clamp, ease, lerp, seg } from "../time";
import { popStyle, toneColors, type Tone } from "./reference";

const lab = (th: Theme) => th.field === "lab" || th.field === "lab_violet";
const card = (th: Theme) => ({
  background: th.surface,
  boxShadow: lab(th)
    ? "0 40px 90px rgba(0,0,0,0.5), inset 0 0 0 2px rgba(255,255,255,0.14), inset 0 2px 0 rgba(255,255,255,0.2)"
    : th.dark ? "0 30px 60px rgba(0,0,0,0.35)" : "0 30px 60px rgba(21,25,54,0.13)",
});
const toneInk = (tone: string | undefined, th: Theme) =>
  tone === "bad" ? C.coral : tone === "ok" ? C.mint : tone === "warn" ? (th.dark ? C.amber : C.amberInk) : th.surfaceInk;
const shake = (age: number) => (age >= 0 && age < 0.5 ? Math.sin(age * 60) * 14 * (1 - age / 0.5) : 0);

/** A value that changes: the old one lifts away, the new one rises in. */
function Rolling({ value, prev, age, size, color }: { value: string; prev?: string; age: number; size: number; color: string }) {
  const q = ease.outCubic(seg(age, 0, 0.4));
  const changing = prev !== undefined && prev !== value && age >= 0 && q < 1;
  return (
    <div style={{ position: "relative", height: size * 1.1, display: "grid", placeItems: "center", overflow: "hidden" }}>
      {changing && <div style={{ position: "absolute", fontSize: size, fontWeight: 800, color, opacity: 1 - q,
                                 transform: `translateY(${-q * size * 0.9}px)` }}>{prev}</div>}
      <div style={{ fontSize: size, fontWeight: 800, color, lineHeight: 1,
                    opacity: changing ? q : 1, transform: changing ? `translateY(${(1 - q) * size * 0.9}px)` : undefined }}>{value}</div>
    </div>
  );
}

// ------------------------------------------------------------- app_screen

export function AppScreen({ x, y, w, h, title, button, label, value, prev, tone, valueAge, tapAge, p, field }: {
  x: number; y: number; w: number; h: number; title: string; button: string; label: string; value: string;
  prev?: string; tone?: string; valueAge: number; tapAge: number; p: number; field: FieldName;
}) {
  const th = theme(field);
  const cw = Math.min(w, 720), ch = h - 20;
  const cx = x + w / 2;
  const left = cx - cw / 2;
  // the finger: comes in 0.6 s before the tap, presses, then leaves
  const comes = ease.inOutCubic(seg(tapAge, -0.6, 0.6));
  const leaves = ease.inOutCubic(seg(tapAge, 0.55, 0.45));
  const press = tapAge >= 0 && tapAge < 0.25 ? Math.sin((tapAge / 0.25) * Math.PI) : 0;
  const ripple = seg(tapAge, 0, 0.6);
  const btnY = ch - 150;
  const fingerOn = tapAge > -0.6 && tapAge < 1.0;
  const fx = lerp(cw - 40, cw / 2 + 40, comes) + leaves * 140;
  const fy = lerp(ch + 40, btnY + 70, comes) + leaves * 120 + press * 10;
  const stuck = tone === "bad" && valueAge >= 0 && valueAge < 0.6;
  const { bg: btnBg, fg: btnFg } = toneColors("info", th);
  return (
    <At x={left} y={y + 10} style={popStyle(p)}>
      <div style={{ position: "relative", width: cw, height: ch, borderRadius: 56, ...card(th), overflow: "hidden" }}>
        <div style={{ height: 86, display: "flex", alignItems: "center", gap: 14, padding: "0 36px",
                      borderBottom: `2px solid ${th.surfaceLine}`, color: th.surfaceDim, fontWeight: 800, fontSize: 30 }}>
          {[C.coral, C.amber, C.mint].map((c) => <span key={c} style={{ width: 18, height: 18, borderRadius: 9, background: c, opacity: 0.85 }} />)}
          <span style={{ marginLeft: 10 }}>{title}</span>
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 104, textAlign: "center", color: th.surfaceDim, fontWeight: 700, fontSize: 34 }}>{label}</div>
        <div style={{ position: "absolute", left: 0, right: 0, top: 150, transform: `translateX(${stuck ? shake(valueAge) : 0}px)` }}>
          <Rolling value={value} prev={prev} age={valueAge} size={150} color={toneInk(tone, th)} />
        </div>
        <div style={{ position: "absolute", left: cw / 2 - 210, top: btnY, width: 420, height: 104, borderRadius: 52,
                      background: btnBg, color: btnFg, display: "grid", placeItems: "center", fontWeight: 800, fontSize: 40,
                      transform: `scale(${1 - 0.07 * press})`, whiteSpace: "nowrap", overflow: "hidden" }}>
          {ripple > 0 && ripple < 1 && <span style={{ position: "absolute", width: 420 * ripple * 1.4, height: 420 * ripple * 1.4,
                                                      borderRadius: "50%", background: btnFg, opacity: 0.25 * (1 - ripple) }} />}
          <span style={{ position: "relative" }}>{button}</span>
        </div>
        {fingerOn && (
          <div style={{ position: "absolute", left: fx, top: fy, transform: `scale(${1 - 0.12 * press})` }}>
            <Icon name="tap" size={96} color={th.dark ? C.white : C.ink} stroke={2.2} />
          </div>
        )}
      </div>
    </At>
  );
}

// ------------------------------------------------------------- memory_box

export function MemoryBox({ x, y, w, h, name, value, prev, tone, valueAge, resetAge, start, p, field }: {
  x: number; y: number; w: number; h: number; name: string; value: string; prev?: string; tone?: string;
  valueAge: number; resetAge: number; start: string; p: number; field: FieldName;
}) {
  const th = theme(field);
  const bw = Math.min(w, 560), bh = h - 70;
  const cx = x + w / 2;
  // a reset wipes the box (a band sweeps down) and leaves the starting value
  const wipe = seg(resetAge, 0, 0.5);
  const resetting = resetAge >= 0 && wipe < 1;
  const shown = resetAge >= 0.25 ? start : value;
  const spin = resetAge >= 0 && resetAge < 0.9 ? resetAge * 400 : 0;
  const { fg: nameFg, bg: nameBg } = toneColors("special", th);
  return (
    <At x={cx - bw / 2} y={y + 10} style={popStyle(p)}>
      <div style={{ display: "inline-block", padding: "8px 24px", borderRadius: "18px 18px 0 0", background: nameBg, color: nameFg,
                    fontFamily: FONT.mono, fontWeight: 700, fontSize: 32, whiteSpace: "nowrap" }}>{name}</div>
      <div style={{ position: "relative", width: bw, height: bh, borderRadius: "0 32px 32px 32px", ...card(th),
                    border: `4px solid ${nameFg}`, display: "grid", placeItems: "center", overflow: "hidden" }}>
        <Rolling value={shown} prev={resetAge >= 0.25 ? undefined : prev} age={valueAge} size={104} color={toneInk(tone, th)} />
        {resetting && <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: `${wipe * 100}%`,
                                    background: lab(th) ? "rgba(140,123,255,0.25)" : "rgba(91,75,245,0.15)" }} />}
        {spin > 0 && <div style={{ position: "absolute", right: 18, top: 14, transform: `rotate(${spin}deg)` }}>
          <Icon name="refresh" size={52} color={nameFg} stroke={2.6} /></div>}
      </div>
    </At>
  );
}

// ------------------------------------------------------------- flow

export interface Step { name: string; label?: string }

/** Where the travelling thing is: step index (fractional) at `age`. */
const STEP_DUR = 0.7;
function travelAt(age: number, n: number): number {
  if (age < 0) return -1;
  return Math.min(n - 1, age / STEP_DUR);
}

export function Flow({ x, y, w, h, steps, packet, travelAge, highlight, p, field }: {
  x: number; y: number; w: number; h: number; steps: Step[]; packet?: string; travelAge: number; highlight: number;
  p: number; field: FieldName;
}) {
  const th = theme(field);
  const n = Math.max(1, steps.length);
  const gap = w / n;
  const tile = Math.min(150, gap - 40);
  const cy = y + 20 + tile / 2;
  const at = travelAt(travelAge, n);
  const xs = steps.map((_, i) => x + gap * (i + 0.5));
  const px = at < 0 ? xs[0] : lerp(xs[Math.floor(at)], xs[Math.min(n - 1, Math.floor(at) + 1)], at - Math.floor(at));
  const lit = (i: number) => (at >= i - 0.02) || highlight === i + 1;
  const arrive = (i: number) => (at >= 0 ? Math.max(0, 1 - Math.abs(at - i) * 3) : 0);
  return (
    <>
      {steps.slice(0, -1).map((_, i) => {
        const a = xs[i] + tile / 2 + 10, b = xs[i + 1] - tile / 2 - 10;
        const fill = clamp(at - i);
        return (
          <At key={`a${i}`} x={a} y={cy - 4} style={{ opacity: clamp(p * 1.5 - i * 0.2) }}>
            <div style={{ position: "relative", width: b - a, height: 8, borderRadius: 4, background: th.surfaceLine }}>
              <div style={{ width: `${fill * 100}%`, height: "100%", borderRadius: 4, background: th.accent }} />
              <div style={{ position: "absolute", right: -6, top: -11, width: 0, height: 0, borderTop: "15px solid transparent",
                            borderBottom: "15px solid transparent", borderLeft: `20px solid ${fill >= 1 ? th.accent : th.surfaceLine}` }} />
            </div>
          </At>
        );
      })}
      {steps.map((s, i) => {
        const q = clamp(p * 1.6 - i * 0.25);
        const on = lit(i);
        const pop = arrive(i);
        const { bg, fg } = toneColors(on ? "ok" : "info", th);
        return (
          <div key={i}>
            <At x={xs[i]} y={cy} center style={{ ...popStyle(q), transform: `${popStyle(q).transform} scale(${1 + 0.12 * pop})` }}>
              <div style={{ width: tile, height: tile, borderRadius: tile * 0.3, background: bg, display: "grid", placeItems: "center",
                            boxShadow: on ? `0 0 ${30 + 30 * pop}px ${C.mint}55` : undefined }}>
                <Icon name={s.name} size={tile * 0.5} color={fg} stroke={2.2} />
              </div>
            </At>
            {s.label && <At x={xs[i]} y={cy + tile / 2 + 36} center style={{ opacity: q }}>
              <div style={{ fontWeight: 800, fontSize: 30, color: on ? th.ink : th.dim, whiteSpace: "nowrap" }}>{s.label}</div>
            </At>}
          </div>
        );
      })}
      {at >= 0 && at < n - 1 + 0.6 && (
        <At x={px} y={cy - tile / 2 - 44} center>
          <div style={{ padding: packet ? "8px 20px" : 0, width: packet ? undefined : 34, height: packet ? undefined : 34,
                        borderRadius: 999, background: th.accent, color: th.dark ? C.ink : C.white,
                        fontFamily: FONT.mono, fontWeight: 700, fontSize: 30, whiteSpace: "nowrap",
                        boxShadow: `0 0 26px ${th.accent}` }}>{packet ?? ""}</div>
        </At>
      )}
    </>
  );
}

// ------------------------------------------------------------- compare

export function Compare({ x, y, w, h, left, right, leftIcon, rightIcon, leftNote, rightNote, revealAge, hasReveal, glow = 0, p, field }: {
  x: number; y: number; w: number; h: number; left: string; right: string; leftIcon: string; rightIcon: string;
  leftNote?: string; rightNote?: string; revealAge: number; hasReveal: boolean; glow?: number; p: number; field: FieldName;
}) {
  const th = theme(field);
  const cw = (w - 40) / 2, ch = h - 20;
  const rightP = hasReveal ? ease.outBack(clamp(seg(revealAge, 0, 0.5)), 1.4) : clamp(p * 1.5 - 0.35);
  const side = (title: string, icon: string, note: string | undefined, good: boolean, q: number, dx: number) => {
    const { bg, fg } = toneColors(good ? "ok" : "bad", th);
    return (
      <At x={x + dx} y={y + 10} style={popStyle(q)}>
        <div style={{ position: "relative", width: cw, height: ch, borderRadius: 40, ...card(th), border: `4px solid ${fg}`,
                      ...(good && glow > 0 ? { boxShadow: `0 0 ${60 * glow}px ${C.mint}88` } : {}),
                      display: "flex", flexDirection: "column", alignItems: "center", padding: "36px 24px 24px", boxSizing: "border-box", gap: 18 }}>
          <div style={{ width: 130, height: 130, borderRadius: 38, background: bg, display: "grid", placeItems: "center" }}>
            <Icon name={icon} size={70} color={fg} stroke={2.2} />
          </div>
          <div style={{ fontWeight: 800, fontSize: 40, color: th.surfaceInk, textAlign: "center", lineHeight: 1.15 }}>{title}</div>
          {note && <div style={{ fontWeight: 600, fontSize: 28, color: th.surfaceDim, textAlign: "center", lineHeight: 1.25 }}>{note}</div>}
          <div style={{ position: "absolute", top: -26, right: -18, width: 64, height: 64, borderRadius: 32, background: fg,
                        display: "grid", placeItems: "center", transform: `scale(${q})` }}>
            <Icon name={good ? "check" : "x"} size={38} color={C.white} stroke={3.2} />
          </div>
        </div>
      </At>
    );
  };
  return <>
    {side(left, leftIcon, leftNote, false, p, 0)}
    {side(right, rightIcon, rightNote, true, rightP, cw + 40)}
  </>;
}

// ------------------------------------------------------------- cycle

export function Cycle({ x, y, w, h, steps, travelAge, highlight, p, field }: {
  x: number; y: number; w: number; h: number; steps: Step[]; travelAge: number; highlight: number; p: number; field: FieldName;
}) {
  const th = theme(field);
  const n = Math.max(2, steps.length);
  const cx = x + w / 2, cy = y + h / 2;
  const r = Math.min(w, h) / 2 - 100;
  const angle = (i: number) => -Math.PI / 2 + (i / n) * Math.PI * 2;
  // the dot goes round and round once it starts, one step every 0.8 s
  const going = travelAge >= 0;
  const pos = going ? (travelAge / 0.8) % n : -1;
  const da = going ? -Math.PI / 2 + (pos / n) * Math.PI * 2 : 0;
  const near = (i: number) => (going ? Math.max(0, 1 - Math.min(Math.abs(pos - i), n - Math.abs(pos - i)) * 2.5) : 0);
  return (
    <>
      <At x={cx - r} y={cy - r} style={{ opacity: clamp(p * 1.4) }}>
        <svg width={r * 2} height={r * 2} style={{ overflow: "visible" }}>
          <circle cx={r} cy={r} r={r} fill="none" stroke={th.surfaceLine} strokeWidth={8} strokeDasharray="4 18" strokeLinecap="round" />
          {going && <circle cx={r + r * Math.cos(da)} cy={r + r * Math.sin(da)} r={20} fill={th.accent}
                            style={{ filter: `drop-shadow(0 0 14px ${th.accent})` }} />}
        </svg>
      </At>
      {steps.map((s, i) => {
        const q = clamp(p * 1.6 - i * 0.2);
        const glow = Math.max(near(i), highlight === i + 1 ? 1 : 0);
        const { bg, fg } = toneColors(glow > 0.3 ? "ok" : "info", th);
        const sx = cx + r * Math.cos(angle(i)), sy = cy + r * Math.sin(angle(i));
        return (
          <At key={i} x={sx} y={sy} center style={{ ...popStyle(q), transform: `${popStyle(q).transform} scale(${1 + 0.15 * glow})` }}>
            <div style={{ display: "grid", justifyItems: "center", gap: 8 }}>
              <div style={{ width: 128, height: 128, borderRadius: 40, background: bg, display: "grid", placeItems: "center",
                            boxShadow: glow > 0.3 ? `0 0 40px ${C.mint}66` : undefined }}>
                <Icon name={s.name} size={64} color={fg} stroke={2.2} />
              </div>
              {s.label && <div style={{ fontWeight: 800, fontSize: 30, color: th.ink, whiteSpace: "nowrap",
                                        background: th.dark ? "rgba(0,0,0,0.25)" : "rgba(255,255,255,0.7)", padding: "2px 12px", borderRadius: 12 }}>{s.label}</div>}
            </div>
          </At>
        );
      })}
    </>
  );
}

export type { Tone };
