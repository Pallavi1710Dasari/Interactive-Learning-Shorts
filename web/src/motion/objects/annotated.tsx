// Rev 2 objects (plan.rev >= 2, shorts/schema.py MotionPlan.rev): the
// first-real-reel fixes of 2026-10-13. Older plans keep the reference
// renderers in reference.tsx.
//
//   CodeAnnotated   the code map as real code with CALLOUTS: each named part
//                   gets a label under the code with a leader line up to its
//                   token, instead of comment lines used as labels and a
//                   separate list of rows
//   EndCardCued     the CTA, every step on a spoken word: Follow pressed on
//                   "follow", the Up next card slides in on "next", the
//                   hashtags pop one per word, a final settle
//   PointerSlot     a memory slot as name -> value: the name tag on the left,
//                   an arrow, the value's box on the right (a list as cells)
//   PointerBox      a memory box resolved the same way, full width: the name
//                   tag, an arrow that draws on its cue, the value's box
//
// locatePart finds a part's token in the code (all revs): the highlight is
// drawn from the token's real column, and a part the code does not contain
// gets no highlight at all instead of one at column 0.

import { At, Icon, Overlay } from "../Stage";
import { C, FONT, W, theme, type FieldName, R } from "../tokens";
import { clamp, ease, seg } from "../time";
import { popStyle, type CodeLine } from "./reference";
import type { IdentitySpec } from "../identity/Identity";
import { IdentitySymbol, toneOn } from "../identity/Identity";

const COMMENT = /^\s*(#|\/\/|--|\/\*)/;
const PAIRS: Record<string, string> = { "[": "]", "(": ")", "{": "}", "<": ">" };

/** Where `code` sits in `lines`: its row, column and length, or null when the
 * code does not contain it. Real code lines are searched before comments; a
 * name matches as a whole word; "[ ]" / "( )" match the bracket pair. */
export function locatePart(lines: string[], code: string): { row: number; col: number; len: number } | null {
  const order = lines.map((_, i) => i).sort((a, b) => Number(COMMENT.test(lines[a])) - Number(COMMENT.test(lines[b])));
  const word = /^[A-Za-z_$][\w$]*$/.test(code);
  for (const row of order) {
    const line = lines[row];
    if (word) {
      const m = new RegExp(`(^|[^\\w$])${code.replace(/\$/g, "\\$")}(?![\\w$])`).exec(line);
      if (m) return { row, col: m.index + m[1].length, len: code.length };
    } else {
      const col = line.indexOf(code);
      if (col >= 0 && code.trim()) return { row, col, len: code.length };
    }
  }
  const open = code.trim()[0];
  if (open && PAIRS[open] && code.trim().endsWith(PAIRS[open])) {
    for (const row of order) {
      const line = lines[row];
      const a = line.indexOf(open);
      if (a < 0) continue;
      let depth = 0;
      for (let i = a; i < line.length; i++) {
        if (line[i] === open) depth += 1;
        else if (line[i] === PAIRS[open] && --depth === 0) return { row, col: a, len: i - a + 1 };
      }
    }
  }
  return null;
}

/** JetBrains Mono's advance is 0.6 em: a column is 0.6 x the font size. */
const CODE_FONT = 54;
const CW = CODE_FONT * 0.6;

export interface AnnotatedPart { code: string; icon: string; label: string; at: { row: number; col: number; len: number } | null }

/** The code map, rev 2. `active` is the part being talked about (-1 none):
 * its token is lit and its callout is bright; every part before it keeps its
 * callout. */
export function CodeAnnotated({ lines, parts, active, reached = active, firstAges, activeAge, t, field, rightEdge = W - 60 }: {
  lines: CodeLine[]; parts: AnnotatedPart[]; active: number; activeAge: number; t: number; field: FieldName;
  /** the furthest part reached so far: its callout and every one before it show */
  reached?: number;
  /** seconds since each part was first reached (-1 not yet): its callout's entrance */
  firstAges?: number[];
  /** callouts end left of this (on the board: clear of the presenter beside it) */
  rightEdge?: number;
}) {
  const th = theme(field);
  const x0 = 60, y0 = 400, padX = 60, rowH = 114;
  const cardH = 72 + lines.length * rowH;
  const cardBottom = y0 + cardH;
  const tokenX = (a: { col: number; len: number }) => x0 + padX + (a.col + a.len / 2) * CW;
  // the rightmost token gets the shallowest callout, so no leader crosses a label
  const placed = parts.map((p, i) => ({ p, i })).filter(({ p }) => p.at)
    .sort((a, b) => tokenX(b.p.at!) - tokenX(a.p.at!));
  const depth = new Map(placed.map(({ i }, d) => [i, d]));
  const hot = active >= 0 ? parts[active] : undefined;
  return (
    <>
      <At x={x0} y={y0} style={popStyle(seg(t, 0, 0.5))}>
        <div style={{ width: 960, height: cardH, borderRadius: R(40), background: C.code, position: "relative",
                      boxShadow: th.dark ? "0 30px 70px rgba(0,0,0,0.45)" : "0 30px 60px rgba(21,25,54,0.18)" }}>
          {hot?.at && (
            <div style={{ position: "absolute", top: 36 + hot.at.row * rowH + 6, height: 90, borderRadius: R(18), background: C.amber,
                          left: padX + hot.at.col * CW - 10, width: hot.at.len * CW + 20,
                          transform: `scale(${1 + 0.08 * (1 - ease.outCubic(clamp(activeAge / 0.3)))})` }} />
          )}
          {lines.map((line, i) => {
            let col = 0;
            return (
              <div key={i} style={{ position: "absolute", left: padX, top: 48 + i * rowH, fontFamily: FONT.mono,
                                    fontSize: CODE_FONT, lineHeight: "66px", whiteSpace: "pre" }}>
                {line.map((tk, j) => {
                  const at = col;
                  col += tk.text.length;
                  const lit = hot?.at && hot.at.row === i && at < hot.at.col + hot.at.len && at + tk.text.length > hot.at.col;
                  return <span key={j} style={{ color: lit ? C.ink : tk.color ?? C.codeText }}>{tk.text}</span>;
                })}
              </div>
            );
          })}
        </div>
      </At>
      {parts.map((p, i) => {
        if (!p.at || i > Math.max(active, reached) || (active < 0 && reached < 0)) return null;
        const d = depth.get(i) ?? 0;
        const tx = tokenX(p.at);
        const pillW = 56 + 26 + p.label.length * 23 + 64;
        const left = Math.max(x0, Math.min(tx - 44, rightEdge - pillW));
        const top = cardBottom + 80 + d * 150;
        const age = firstAges ? firstAges[i] : i === active ? activeAge : 99;
        const q = age >= 0 ? ease.outCubic(clamp(age / 0.35)) : 1;
        const live = i === active;
        const lineTop = y0 + 36 + p.at.row * rowH + 96;
        return (
          <div key={i} data-part={`callout:${i}`}>
            <Overlay>
              <line x1={tx} y1={lineTop} x2={tx} y2={lineTop + (top - lineTop) * q} stroke={live ? C.amber : th.dark ? "rgba(255,255,255,0.45)" : C.grey}
                    strokeWidth={5} strokeLinecap="round" />
              <circle cx={tx} cy={lineTop} r={9} fill={live ? C.amber : th.dark ? "rgba(255,255,255,0.6)" : C.grey} opacity={q} />
            </Overlay>
            <At x={left} y={top} style={{ opacity: clamp(q * 3), transform: `translateY(${(1 - q) * 18}px)` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 26, padding: "18px 32px", borderRadius: R(999), whiteSpace: "nowrap",
                            background: live ? C.amber : th.surface, color: live ? C.ink : th.surfaceInk,
                            boxShadow: th.dark ? "0 16px 40px rgba(0,0,0,0.35)" : "0 16px 40px rgba(21,25,54,0.12)" }}>
                <Icon name={p.icon} size={56} color={live ? C.ink : th.dark ? C.white : C.indigo} stroke={2.4} />
                <span style={{ fontWeight: 800, fontSize: 40 }}>{p.label}</span>
              </div>
            </At>
          </div>
        );
      })}
    </>
  );
}

/** The CTA end card, rev 2. Ages are seconds since each step (negative or
 * 99 = not yet). `tagsShown`: how many hashtags have popped. */
export function EndCardCued({ series, upNext, tags, local, tapAge, revealAge, tagAges, settleAge, identity }: {
  series: string; upNext: string; tags: string[]; local: number; tapAge: number; revealAge: number;
  tagAges: number[]; settleAge: number; identity?: IdentitySpec | null;
}) {
  const press = tapAge >= 0 && tapAge < 0.35 ? Math.sin((tapAge / 0.35) * Math.PI) : 0;
  const followed = tapAge >= 0.15;
  const slide = revealAge >= 0 ? ease.outCubic(clamp(revealAge / 0.55)) : 0;
  const settle = settleAge >= 0 && settleAge < 0.6 ? Math.sin((settleAge / 0.6) * Math.PI) * 0.025 : 0;
  const ring = identity ? toneOn(identity, "navy") : C.yellow;
  return (
    <div style={{ position: "absolute", inset: 0, background: "var(--motion-card-bg, linear-gradient(to bottom, #5B4BF5, #4234D6))",
                  color: C.white, transform: `scale(${1 + settle})` }}>
      <At x={W / 2} y={560} center style={popStyle(seg(local, 0, 0.5))}>
        <div style={{ fontSize: 58, fontWeight: 800, letterSpacing: -1, whiteSpace: "nowrap" }}>{series}</div>
      </At>
      <At x={W / 2} y={700} center style={popStyle(seg(local, 0.12, 0.5))}>
        <div style={{ position: "relative" }}>
          {tapAge >= 0 && tapAge < 0.7 && (
            <div style={{ position: "absolute", left: "50%", top: "50%", width: 420, height: 130, borderRadius: R(999),
                          border: `6px solid ${ring}`, opacity: 1 - tapAge / 0.7,
                          transform: `translate(-50%,-50%) scale(${1 + tapAge * 0.6})` }} />
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "30px 92px", borderRadius: R(999),
                        background: followed ? "rgba(255,255,255,0.16)" : C.white, color: followed ? C.white : C.indigo,
                        border: `4px solid ${followed ? "rgba(255,255,255,0.5)" : C.white}`,
                        fontWeight: 800, fontSize: 50, transform: `scale(${1 - 0.08 * press})`, whiteSpace: "nowrap" }}>
            {followed && <Icon name="check" size={46} color={C.white} stroke={3} />}
            {followed ? "Following" : "Follow"}
          </div>
        </div>
      </At>
      {revealAge >= 0 && (
        <div style={{ position: "absolute", left: 90, top: 880, width: 900, opacity: clamp(revealAge / 0.08),
                      transform: `translateX(${(1 - slide) * 700}px)` }}>
          <div style={{ borderRadius: R(36), padding: "36px 44px", background: "rgba(255,255,255,0.1)",
                        border: "3px solid rgba(255,255,255,0.28)" }}>
            <div style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 28, letterSpacing: 4, color: C.amber }}>UP NEXT</div>
            <div style={{ marginTop: 14, fontWeight: 800, lineHeight: 1.12,
                          fontSize: Math.min(64, Math.floor(1700 / Math.max(1, upNext.length * 0.55))) }}>{upNext}</div>
          </div>
        </div>
      )}
      <div style={{ position: "absolute", left: 60, right: 60, top: 1210, display: "flex", flexWrap: "wrap",
                    justifyContent: "center", gap: 18 }}>
        {tags.map((label, i) => {
          const age = tagAges[i] ?? -1;
          if (age < 0) return null;
          return (
            <div key={label} style={{ padding: "14px 28px", borderRadius: R(999), background: "rgba(255,255,255,0.14)",
                                      fontFamily: FONT.mono, fontWeight: 700, fontSize: 32, whiteSpace: "nowrap",
                                      ...popStyle(clamp(age / 0.4)) }}>{label}</div>
          );
        })}
      </div>
    </div>
  );
}

/** A memory slot as name -> value: the name tag points at the value's box.
 * A list literal ('["milk", "bread"]') is drawn as a box of cells. */
export function PointerSlot({ name, value, pulse = 0, field }: { name: string; value: string; pulse?: number; field: FieldName }) {
  const th = theme(field);
  const list = /^\s*\[(.*)\]\s*$/.exec(value);
  const items = list ? list[1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, "")).filter(Boolean) : null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, height: "100%" }}>
      <div style={{ position: "relative", padding: "14px 30px 14px 46px", borderRadius: "14px 30px 30px 14px", background: C.special,
                    color: C.ink, fontFamily: FONT.mono, fontWeight: 700, fontSize: 40, whiteSpace: "nowrap" }}>
        <span style={{ position: "absolute", left: 16, top: "50%", width: 14, height: 14, marginTop: -7, borderRadius: R(7),
                       background: th.dark ? "#0B1030" : C.white }} />
        {name}
      </div>
      <svg width={110} height={40} viewBox="0 0 110 40" style={{ flex: "none" }}>
        <path d="M6 20 H92" stroke={th.dark ? C.white : C.ink} strokeWidth={6} strokeLinecap="round" />
        <path d="M78 6 L98 20 L78 34" fill="none" stroke={th.dark ? C.white : C.ink} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: 12, borderRadius: R(22), background: C.amberSoft,
                    border: `5px solid ${C.amber}`, transform: `scale(${1 + 0.1 * pulse})` }}>
        {items ? items.map((it, i) => (
          <div key={i} style={{ padding: "10px 20px", borderRadius: R(12), background: C.white, color: C.ink,
                                fontWeight: 800, fontSize: 36, whiteSpace: "nowrap" }}>{it}</div>
        )) : <div style={{ padding: "6px 18px", color: C.ink, fontWeight: 800, fontSize: 44, whiteSpace: "nowrap" }}>{value}</div>}
      </div>
    </div>
  );
}

/** The title card's language chip, rev 2: the language is named here once
 * instead of in a corner badge on every shot. */
export function LanguageChip({ spec }: { spec: IdentitySpec }) {
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 14, padding: "12px 30px 12px 16px", borderRadius: R(999),
                  background: "rgba(255,255,255,0.14)", whiteSpace: "nowrap" }}>
      <IdentitySymbol spec={spec} size={44} colour={spec.on_dark} />
      <span style={{ fontFamily: FONT.mono, fontWeight: 700, fontSize: 32, letterSpacing: 3, textTransform: "uppercase" }}>{spec.name}</span>
    </div>
  );
}

function listItems(value: string): string[] | null {
  const list = /^\s*\[(.*)\]\s*$/.exec(value);
  return list ? list[1].split(",").map((x) => x.trim().replace(/^["']|["']$/g, "")).filter(Boolean) : null;
}

/** A memory box shown as its name POINTING at its value: the tag on the
 * left, the value's box on the right, and between them an arrow that draws
 * on its cue (`arrowAge` >= 0). A tone of "ok" turns the box mint with a ✓. */
export function PointerBox({ x, y, w, h, name, value, p, arrowAge, tone, toneAge, pulse = 0, field }: {
  x: number; y: number; w: number; h: number; name: string; value: string; p: number; arrowAge: number;
  tone?: string; toneAge: number; pulse?: number; field: FieldName;
}) {
  const th = theme(field);
  const items = listItems(value);
  const ok = tone === "ok";
  const okQ = ok ? ease.outBack(clamp(toneAge / 0.4), 1.6) : 0;
  const draw = arrowAge >= 0 ? ease.inOutCubic(clamp(arrowAge / 0.5)) : 0;
  const border = ok ? C.mint : C.amber;
  const cy = y + h / 2;
  const tagW = 60 + name.length * 30;
  const ax0 = x + 20 + tagW + 16, ax1 = x + 20 + tagW + 150;
  return (
    <div style={{ opacity: clamp(p * 1.6), transform: `translateY(${(1 - ease.outCubic(clamp(p))) * 24}px)` }}>
      <At x={x + 20} y={cy - 48}>
        <div style={{ position: "relative", height: 96, padding: "0 34px 0 52px", borderRadius: "16px 40px 40px 16px", background: C.special,
                      color: C.ink, fontFamily: FONT.mono, fontWeight: 700, fontSize: 50, display: "flex", alignItems: "center",
                      whiteSpace: "nowrap" }}>
          <span style={{ position: "absolute", left: 18, top: 39, width: 18, height: 18, borderRadius: R(9), background: th.dark ? "#0B1030" : C.white }} />
          {name}
        </div>
      </At>
      <Overlay>
        <path d={`M${ax0} ${cy} H${ax0 + (ax1 - ax0 - 6) * draw}`} stroke={th.dark ? C.white : C.ink} strokeWidth={8} strokeLinecap="round" />
        {draw > 0.85 && <path d={`M${ax1 - 26} ${cy - 20} L${ax1} ${cy} L${ax1 - 26} ${cy + 20}`} fill="none"
                              stroke={th.dark ? C.white : C.ink} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round" />}
      </Overlay>
      <At x={ax1 + 18} y={cy - 70}>
        <div style={{ position: "relative", height: 140, display: "flex", alignItems: "center", gap: 14, padding: "0 20px", borderRadius: R(30),
                      background: ok ? C.mintSoft : C.amberSoft, border: `6px solid ${border}`, transform: `scale(${1 + 0.08 * pulse})`,
                      maxWidth: x + w - ax1 - 30, boxSizing: "border-box" }}>
          {(items ?? [value]).map((it, i) => (
            <div key={i} style={{ padding: "16px 24px", borderRadius: R(16), background: C.white, color: C.ink, fontWeight: 800,
                                  fontSize: 46, whiteSpace: "nowrap" }}>{it}</div>
          ))}
          {ok && (
            <div style={{ position: "absolute", top: -30, right: -26, width: 64, height: 64, borderRadius: R(32), background: C.mint,
                          display: "grid", placeItems: "center", transform: `scale(${okQ})` }}>
              <Icon name="check" size={38} color={C.white} stroke={3.2} />
            </div>
          )}
        </div>
      </At>
    </div>
  );
}
