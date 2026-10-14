// Scene objects (RESTYLE_TO_MOTION_REELS.md phase 3): one renderer per kind
// in web/src/motion/library.json, each drawn with the phase 2 components.
// Every renderer gets the object (its props and the box Python laid it out
// in), the shot's actions, and t — and derives everything it shows from
// those: when it entered, its current tone and value, what is highlighted,
// how far a pulse has travelled. Pure in t.

import type { ReactNode } from "react";
import { At, Overlay } from "../Stage";
import { C, LOOK, W, theme, type FieldName } from "../tokens";
import { clamp, ease, hash3, pulse as pulseOf, seg } from "../time";
import {
  CodeMapCard, CodeWindow, Connector, EndCard, EntityCard, IconTile, StatusPill, SystemPanel,
  TakeawayList, TitleCard, TriggerChip, type CodeLine, type Tone,
} from "../objects/reference";
import {
  BigCounter, Callout, ChapterCard, KineticTitle, LookupTable, RecapGrid, Stamp, TokenRow,
  rowWidth, type ChipTone,
} from "../objects/editorial";
import type { PlanAction, PlanObject, PlanShot } from "./types";
import { AppScreen, Compare, Cycle, Flow, MemoryBox } from "../objects/action";
import { IdentityTitle, type IdentitySpec } from "../identity/Identity";
import { CodeAnnotated, EndCardCued, LanguageChip, PointerBox, PointerSlot, locatePart } from "../objects/annotated";
import { typedChars } from "../camera";
import { BOARD } from "../cast/teach";
import library from "../library.json";

const KINETIC = (library as { kinetic: { size: number; line_height: number } }).kinetic;
export const ENTER_DUR = 0.45;
/** How large the small objects draw in a 1080x1920 frame. Their heights in
 * library.json reserve the room, so the Python layout keeps them apart. */
export const SIZES = { pill: 44, chip: 42, token: 46, counter: 280, callout: 1.25 } as const;

/** What an object's actions have done to it by time t. */
export interface ObjState {
  enterT: number;          // when it appeared (shot start if it never "enter"s)
  p: number;               // entrance progress 0..1 (times exit fade)
  local: number;           // seconds since it appeared
  tone?: string;
  value?: string;
  highlight: number;       // 1-based index of the latest highlight, 0 for none
  highlightAge: number;    // seconds since that highlight
  pulseAge: number;        // seconds since the latest pulse (99 = none)
  typeT: number | null;    // when "type" started
  countT: number | null;   // when "count" started
  scrambleAge: number;     // seconds since the latest scramble (99 = none)
  stampT: number | null;
  // action objects (objects/action.tsx)
  prevValue?: string;      // the value before the latest "state"
  valueT: number;          // when the latest "state" happened (-99 = never)
  tapT: number;            // the next or latest "tap" (a finger arrives 0.6 s before it)
  travelT: number;         // when "travel" started (99 = never)
  resetT: number;          // when the latest "reset" happened (99 = never)
  revealT: number;         // when "reveal" happened (99 = never)
  hasReveal: boolean;
}

export function objectState(obj: PlanObject, shot: PlanShot, t: number): ObjState {
  const mine = shot.actions.filter((a) => a.target === obj.id);
  const enter = mine.find((a) => a.do === "enter" || a.do === "stamp");
  const enterT = enter ? enter.t : shot.start;
  const exit = mine.find((a) => a.do === "exit" && a.t <= t);
  const fade = exit ? 1 - seg(t, exit.t, 0.35) : 1;
  const s: ObjState = {
    enterT, p: ease.outCubic(seg(t, enterT, ENTER_DUR)) * fade, local: t - enterT,
    tone: obj.props.tone, value: obj.props.value, highlight: 0, highlightAge: 99, pulseAge: 99,
    typeT: null, countT: null, scrambleAge: 99, stampT: null,
    valueT: -99, tapT: 99, travelT: 99, resetT: 99, revealT: 99, hasReveal: mine.some((a) => a.do === "reveal"),
  };
  // a tap is drawn from 0.6 s before it (the finger coming in): the next
  // tap within that window counts as the current one
  const taps = mine.filter((a) => a.do === "tap").map((a) => a.t);
  const upcoming = taps.find((x) => x >= t && x - t <= 0.6);
  const past = taps.filter((x) => x <= t);
  s.tapT = upcoming ?? (past.length ? past[past.length - 1] : 99);
  for (const a of mine) {
    if (a.t > t) continue;
    if (a.do === "state") {
      if (a.tone) s.tone = a.tone;
      if (a.value != null) { s.prevValue = s.value; s.value = a.value; }
      s.valueT = a.t;
    } else if (a.do === "highlight") {
      s.highlight = Number(a.value) || 1;
      s.highlightAge = t - a.t;
    } else if (a.do === "pulse") s.pulseAge = t - a.t;
    else if (a.do === "type") s.typeT = a.t;
    else if (a.do === "count") s.countT = a.t;
    else if (a.do === "scramble") s.scrambleAge = t - a.t;
    else if (a.do === "stamp") s.stampT = a.t;
    else if (a.do === "travel") s.travelT = a.t;
    else if (a.do === "reset") s.resetT = a.t;
    else if (a.do === "reveal") s.revealT = a.t;
  }
  if (!enter && mine.length === 0) s.p = ease.outCubic(seg(t, shot.start, ENTER_DUR));
  return s;
}

function chipTone(tone?: string): ChipTone {
  if (tone === "ok" || tone === "bad" || tone === "special") return tone;
  if (tone === "warn" || tone === "info") return "key";
  return "plain";
}

const KEYWORDS = /^(const|let|var|function|return|def|class|import|from|if|else|for|while|new|await|async|public|private|static|void|int)$/;

/** A line of code coloured the way the phase 2 code window expects. */
export function codeLine(line: string): CodeLine {
  const out: CodeLine = [];
  for (const m of line.matchAll(/(\s+|[A-Za-z_$][\w$]*|\d+|[^\sA-Za-z_$\d]+)/g)) {
    const tok = m[0];
    const after = line.slice((m.index ?? 0) + tok.length);
    if (KEYWORDS.test(tok)) out.push({ text: tok, color: C.codeKeyword });
    else if (/^[A-Za-z_$]/.test(tok) && after.startsWith("(")) out.push({ text: tok, color: C.codeFn });
    else if (/^\d+$/.test(tok)) out.push({ text: tok, color: C.amber });
    else out.push({ text: tok });
  }
  return out;
}

/** Characters settling left to right into `text` (text_scramble), pure in age. */
function scrambled(text: string, age: number, seed: number): string {
  if (age >= 0.6) return text;
  const settled = Math.floor((age / 0.6) * text.length);
  return text.split("").map((ch, i) => (i < settled || ch === " " ? ch
    : "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"[Math.floor(hash3(seed, i, Math.floor(age * 30)) * 33)])).join("");
}

const highlightOn = (s: ObjState) => s.highlight > 0 && s.highlightAge < 0.9;

/** One scene object at time t. */
export function SceneObject({ obj, shot, t, field, series, identity, themeLabel = "", tags = [], rev = 1, board = false }: {
  obj: PlanObject; shot: PlanShot; t: number; field: FieldName; series: string;
  identity?: IdentitySpec | null; themeLabel?: string; tags?: string[];
  /** the plan's layout rules (MotionPlan.rev): 2 draws the annotated.tsx objects */
  rev?: number;
  /** drawn on the board stage, beside a presenter (cast/teach.ts) */
  board?: boolean;
}): ReactNode {
  const s = objectState(obj, shot, t);
  const p = obj.props;
  const b = obj.box ?? { x: 60, y: 0, w: 960, h: 0 };
  const cx = W / 2;
  const th = theme(field);
  switch (obj.kind) {
    case "identity_title":
      return identity ? (
        <div style={{ transform: `scale(${1 + 0.05 * pulseOf(s.pulseAge, 0, 0.5)})`, transformOrigin: `${b.x + 85}px ${b.y + 85}px` }}>
          <IdentityTitle spec={identity} label={themeLabel} field={field} x={b.x} y={b.y} t={s.local} />
        </div>) : null;
    case "kinetic_title": {
      const accent = new Set((p.accent ?? []).map((a: string) => a.toUpperCase().replace(/[^\w]/g, "")));
      let n = 0;
      const lit = highlightOn(s) ? s.highlight : 0;
      const lines = (p.lines ?? [p.text]).map((line: string, li: number) => line.split(" ").map((w: string, wi: number) => {
        n += 1;
        return {
          text: scrambled(w, s.scrambleAge, 17 + li * 7 + wi),
          // a highlighted word takes the accent while the narration says it
          accent: accent.has(w.toUpperCase().replace(/[^\w]/g, "")) || n === lit,
        };
      }));
      return <div style={{ opacity: s.p > 0 ? 1 : 0 }}>
        <KineticTitle lines={lines} x={b.x} y={b.y} size={KINETIC.size} t={s.local} field={field}
                      lineHeight={KINETIC.line_height} />
      </div>;
    }
    case "code_window": {
      // typed by the virtual cursor (camera.tsx): character by character behind a caret
      const typing = shot.cursor?.find((c) => c.do === "type" && c.target === obj.id);
      if (typing && t >= typing.t - 0.6) {
        const n = t < typing.t ? 0 : typedChars(typing, t);
        const text = (typing.text ?? "").slice(0, n);
        const blink = t > (typing.t_end ?? typing.t) + 0.2 && Math.floor(t * 2.2) % 2 === 1;
        const rows = text.split("\n").map(codeLine);
        if (!blink) rows[rows.length - 1] = [...rows[rows.length - 1], { text: "\u258F", color: C.amber }];
        return <CodeWindow x={b.x} y={b.y} w={b.w} file={p.file ?? ""} lines={rows}
                           highlight={s.highlight ? s.highlight - 1 : -1} p={s.p} field={field} />;
      }
      const lines = (p.lines as string[]).map(codeLine);
      const shown = s.typeT === null ? Infinity : Math.max(0, (t - s.typeT) / 0.45);
      return <CodeWindow x={b.x} y={b.y} w={b.w} file={p.file ?? ""} lines={lines} shown={shown}
                         highlight={s.highlight ? s.highlight - 1 : -1} p={s.p} field={field} />;
    }
    case "entity_card":
      return <EntityCard x={b.x} y={b.y} w={b.w} h={b.h} label={p.label} value={s.value ?? p.value}
                         valueTone={(s.tone as Tone) ?? "plain"} unit={p.unit ?? ""} p={s.p} field={field}
                         sweep={s.pulseAge < 0.9 ? s.pulseAge / 0.9 : -1} />;
    case "system_panel":
      return <SystemPanel x={b.x} y={b.y} w={b.w} h={b.h} title={p.title} status={s.value ?? p.status}
                          statusTone={(s.tone as Tone) ?? "plain"} p={s.p} field={field}
                          slot={p.slot_name ? { name: p.slot_name, value: p.slot_value ?? "", pulse: pulseOf(s.pulseAge, 0, 0.45) } : null}
                          glow={s.pulseAge < 0.8 ? 1 - s.pulseAge / 0.8 : 0}
                          pointer={rev >= 2 && p.slot_name && p.slot_value
                            ? <PointerSlot name={p.slot_name} value={String(p.slot_value)} pulse={pulseOf(s.pulseAge, 0, 0.45)} field={field} />
                            : undefined} />;
    case "status_pill":
      return <StatusPill x={b.w ? b.x + b.w / 2 : cx} y={b.y + b.h / 2} text={s.value ?? p.text} tone={(s.tone as Tone) ?? "plain"}
                         icon={p.icon} field={field} p={s.p} size={SIZES.pill} />;
    case "trigger_chip":
      return <TriggerChip x={b.w ? b.x + b.w / 2 : cx} y={b.y + b.h / 2} label={p.label} field={field} p={s.p}
                          firing={pulseOf(s.pulseAge, 0, 0.5)} size={SIZES.chip} />;
    case "token_row": {
      const tones = s.value && /^[a-z,]+$/.test(s.value) ? s.value.split(",") : (p.tones ?? []);
      const items = (p.items as string[]).map((text, i) => ({
        text, tone: highlightOn(s) && s.highlight === i + 1 ? "key" as ChipTone : chipTone(tones[i]),
      }));
      // as large as fits the content width: a short row reads from across the room
      const texts = items.map((it) => it.text);
      let size: number = SIZES.token;
      while (size > 26 && rowWidth(texts, size) > b.w) size -= 2;
      return <div style={{ opacity: s.p, transform: `translateY(${(1 - s.p) * 24}px)` }}>
        <TokenRow items={items} x={b.w ? b.x + b.w / 2 : cx} y={b.y + 4} field={field} center size={size} />
      </div>;
    }
    case "big_counter": {
      let value = String(s.value ?? p.value);
      if (s.countT !== null && /^\d+$/.test(value)) {
        value = String(Math.round(Number(value) * ease.outCubic(seg(t, s.countT, 1.2))));
      }
      // a long value ("1 → 7") is set smaller so it stays inside the frame
      const fit = Math.min(SIZES.counter, Math.floor(880 / Math.max(1, String(p.value).length * 0.62)));
      return <BigCounter value={value} label={p.label} x={b.w ? b.x + b.w / 2 : cx} y={b.y + b.h / 2} size={fit} field={field} p={s.p} />;
    }
    case "callout":
      return <Callout x={b.x + 60} y={b.y} w={b.w - 120} label={p.label} text={p.text}
                      px={b.x + 90} py={b.y + b.h} field={field} p={s.p} scale={SIZES.callout} />;
    case "icon_row": {
      const icons = p.icons as { name: string; label?: string; tone?: string }[];
      const gap = Math.min(300, b.w / icons.length);
      return <>{icons.map((ic, i) => {
        const x = cx + (i - (icons.length - 1) / 2) * gap;
        const lit = highlightOn(s) && s.highlight === i + 1;
        const q = clamp(s.p * 1.4 - i * 0.2);
        return (
          <div key={i}>
            <IconTile x={x} y={b.y + 80} size={lit ? 168 : 150} icon={ic.name} tone={lit ? "warn" : ((ic.tone as Tone) ?? "info")}
                      field={field} p={q} />
            {ic.label && <At x={x} y={b.y + 190} center style={{ opacity: q }}>
              <div style={{ fontWeight: 800, fontSize: 32, color: th.ink, whiteSpace: "nowrap" }}>{ic.label}</div>
            </At>}
          </div>
        );
      })}</>;
    }
    case "lookup_table": {
      const rows = p.rows as [string, string][];
      const hi = s.highlight ? s.highlight - 1 : Math.floor(rows.length / 2);
      return <div style={{ opacity: s.p }}>
        <LookupTable header={p.header} rows={rows} offset={hi} x={b.x} y={b.y} w={b.w} field={field}
                     visible={Math.min(5, rows.length)} highlight={s.highlight ? 1 : 0} />
      </div>;
    }
    case "stamp": {
      if (s.stampT === null) return null;
      // a long verdict ("THROWN AWAY") is set smaller and kept inside the
      // card's right side, so it never covers the card's value and unit
      const len = String(p.text ?? "").length;
      const size = Math.min(84, 360 / Math.max(1, len * 0.5));
      const half = (len * size * 0.5 + 86) / 2;
      return <Stamp text={p.text} x={Math.min(b.x, W - 80 - half)} y={b.y} p={seg(t, s.stampT, 0.35)} t={t} size={size} />;
    }
    case "connector": {
      const pts = p.points as [number, number][] | undefined;
      if (!pts) return null;
      return <Connector points={pts} tone={(s.tone as Tone) ?? (p.tone as Tone) ?? "info"} broken={!!p.broken && s.tone !== "ok"}
                        pulse={s.pulseAge < 0.8 ? s.pulseAge / 0.8 : -1} draw={seg(t, s.enterT, 0.4)} field={field} />;
    }
    // ------------------------------------------------------- action objects
    case "app_screen":
      return <AppScreen x={b.x} y={b.y} w={b.w} h={b.h} title={p.title} button={p.button} label={p.label}
                        value={s.value ?? p.value} prev={s.prevValue} tone={s.tone} valueAge={t - s.valueT}
                        tapAge={t - s.tapT} p={s.p} field={field} />;
    case "memory_box":
      if (p.points_to) {
        // the name pointing at its value (motion_tidy._resolve): the arrow draws
        // on the state that resolves it (tone ok), else the first state change
        const states = shot.actions.filter((a) => a.target === obj.id && a.do === "state");
        const first = states.find((a) => a.tone === "ok") ?? states[0];
        return <PointerBox x={b.x} y={b.y} w={b.w} h={b.h} name={p.name} value={String(p.points_to)} p={s.p}
                           arrowAge={first ? t - first.t : -1} tone={s.tone} toneAge={t - s.valueT}
                           pulse={pulseOf(s.pulseAge, 0, 0.45)} field={field} />;
      }
      return <MemoryBox x={b.x} y={b.y} w={b.w} h={b.h} name={p.name} value={s.value ?? p.value} prev={s.prevValue}
                        tone={s.tone} valueAge={t - s.valueT} resetAge={t - s.resetT} start={p.value} p={s.p} field={field} />;
    case "flow":
      return <Flow x={b.x} y={b.y} w={b.w} h={b.h} steps={p.steps} packet={p.packet} travelAge={t - s.travelT}
                   highlight={highlightOn(s) ? s.highlight : 0} p={s.p} field={field} />;
    case "compare":
      return <Compare x={b.x} y={b.y} w={b.w} h={b.h} left={p.left} right={p.right} leftIcon={p.left_icon ?? "x"}
                      rightIcon={p.right_icon ?? "check"} leftNote={p.left_note} rightNote={p.right_note}
                      revealAge={t - s.revealT} hasReveal={s.hasReveal} glow={pulseOf(s.pulseAge, 0, 0.6)} p={s.p} field={field}
                      slideIn={rev >= 2} />;
    case "cycle":
      return <Cycle x={b.x} y={b.y} w={b.w} h={b.h} steps={p.steps} travelAge={t - s.travelT}
                    highlight={highlightOn(s) ? s.highlight : 0} p={s.p} field={field} />;
    // ------------------------------------------------------- full frame
    case "title_card": {
      const icons = (p.icons ?? []) as { name: string; label: string }[];
      return <>
        <TitleCard series={series} title={p.title} promise={p.promise} icons={icons} t={s.local}
                   chip={rev >= 2 ? (identity ? <LanguageChip spec={identity} /> : null) : undefined} />
        {highlightOn(s) && s.highlight <= icons.length && !LOOK.studio && (
          <Overlay><circle cx={270 + (s.highlight - 1) * 270} cy={1230} r={110 + 30 * clamp(s.highlightAge / 0.5)}
                           fill="none" stroke={C.amber} strokeWidth={8} opacity={1 - clamp(s.highlightAge / 0.9)} /></Overlay>
        )}
      </>;
    }
    case "end_card":
      if (rev >= 2) {
        const mine = shot.actions.filter((a) => a.target === obj.id);
        const age = (pred: (a: PlanAction) => boolean) => { const a = mine.find(pred); return a ? t - a.t : -1; };
        const settle = mine.filter((a) => a.do === "pulse").pop();
        const cued = tags.map((_, i) => age((a) => a.do === "highlight" && Number(a.value) === i + 1));
        // a tag no word was left for pops in with the final settle
        const tagAges = cued.map((v, i) => (v >= 0 || !settle ? v : t - settle.t - i * 0.08));
        return <EndCardCued series={series} upNext={p.up_next || "More soon"} tags={tags} local={s.local}
                            tapAge={age((a) => a.do === "tap")} revealAge={age((a) => a.do === "reveal")}
                            tagAges={tagAges} settleAge={settle ? t - settle.t : -1} identity={identity} />;
      }
      return <>
        <EndCard upNext={p.up_next || "Follow for more"} chips={tags.map((label) => ({ label, done: false }))} t={s.local} />
        {s.pulseAge < 0.9 && <Overlay><rect x={cx - 230 - 30 * s.pulseAge} y={1050 - 20 * s.pulseAge} width={460 + 60 * s.pulseAge}
                                             height={96 + 40 * s.pulseAge} rx={60} fill="none" stroke={C.white} strokeWidth={6}
                                             opacity={1 - s.pulseAge / 0.9} /></Overlay>}
      </>;
    case "takeaway_list": {
      const rows = (p.rows as { icon: string; line: string; sub?: string; tone?: string }[]).map((r) => ({
        icon: r.icon, line: r.line, sub: r.sub ?? "", tone: ((r.tone as Tone) ?? "info"),
      }));
      return <>
        <TakeawayList heading={p.heading ?? "Key takeaways"} rows={rows} t={s.local} field={field} lit={s.highlight} />
        {highlightOn(s) && s.highlight <= rows.length && !LOOK.studio && (
          <Overlay><rect x={54} y={648 + (s.highlight - 1) * 252} width={972} height={216} rx={58} fill="none"
                         stroke={th.dark ? C.yellow : C.indigo} strokeWidth={7} opacity={1 - clamp(s.highlightAge / 0.9)} /></Overlay>
        )}
      </>;
    }
    case "recap_grid":
      return <RecapGrid concept={p.concept} steps={p.steps} final={(p.final ?? []).map((text: string) => ({ text, tone: "ok" as ChipTone }))}
                        field={field} t={s.local} />;
    case "chapter_card":
      return <ChapterCard n={p.n} of={p.of} title={p.title} field={field} t={s.local} />;
    case "code_map": {
      const lines = p.lines as string[];
      if (rev >= 2) {
        const parts = (p.parts as { code: string; icon: string; label: string }[]).map((part) => ({
          ...part, at: locatePart(lines, part.code) }));
        // the part being talked about stays lit until the next one; every part
        // reached so far keeps its callout (the narration may go back to one)
        const hits = shot.actions.filter((a) => a.target === obj.id && a.do === "highlight" && a.t <= t);
        const reached = Math.max(0, ...hits.map((a) => Number(a.value) || 0));
        // a callout animates in the first time its part is reached, never again
        const firstAges = parts.map((_, i) => { const a = hits.find((h) => Number(h.value) === i + 1); return a ? t - a.t : -1; });
        return <CodeAnnotated lines={lines.map(codeLine)} parts={parts} active={s.highlight ? s.highlight - 1 : -1}
                              reached={reached - 1} firstAges={firstAges} activeAge={s.highlightAge} t={s.local} field={field}
                              rightEdge={board ? BOARD.callout_right : undefined} />;
      }
      const parts = (p.parts as { code: string; icon: string; label: string }[]).map((part) => {
        // the token's real place (a part the code does not contain gets no highlight)
        const at = locatePart(lines.slice(0, 2), part.code);
        return { at: at ? [at.col, at.len] as [number, number] : null, icon: part.icon, tone: "info" as Tone,
                 name: part.code, desc: part.label, row: at?.row ?? 0 };
      });
      return <CodeMapCard line1={codeLine(lines[0])} line2={codeLine(lines[1] ?? "")} parts={parts}
                          active={s.highlight ? s.highlight - 1 : -1} t={s.local} field={field} />;
    }
    default:
      return null;
  }
}

export const FULL_KINDS = new Set(["title_card", "end_card", "takeaway_list", "recap_grid", "chapter_card", "code_map"]);

/** The most recent action at or before t (for the two-speaker reactions). */
export function lastAction(shot: PlanShot, t: number, pred: (a: PlanAction) => boolean): PlanAction | null {
  let out: PlanAction | null = null;
  for (const a of shot.actions) if (a.t <= t && pred(a)) out = a;
  return out;
}
