// Scene objects (RESTYLE_TO_MOTION_REELS.md phase 3): one renderer per kind
// in web/src/motion/library.json, each drawn with the phase 2 components.
// Every renderer gets the object (its props and the box Python laid it out
// in), the shot's actions, and t — and derives everything it shows from
// those: when it entered, its current tone and value, what is highlighted,
// how far a pulse has travelled. Pure in t.

import type { ReactNode } from "react";
import { At, Overlay } from "../Stage";
import { C, W, theme, type FieldName } from "../tokens";
import { clamp, ease, hash3, pulse as pulseOf, seg } from "../time";
import {
  CodeMapCard, CodeWindow, Connector, EndCard, EntityCard, IconTile, StatusPill, SystemPanel,
  TakeawayList, TitleCard, TriggerChip, type CodeLine, type Tone,
} from "../objects/reference";
import {
  BigCounter, Callout, ChapterCard, KineticTitle, LookupTable, RecapGrid, Stamp, TokenRow,
  type ChipTone,
} from "../objects/editorial";
import type { PlanAction, PlanObject, PlanShot } from "./types";
import library from "../library.json";

const KINETIC = (library as { kinetic: { size: number; line_height: number } }).kinetic;
export const ENTER_DUR = 0.45;

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
  };
  for (const a of mine) {
    if (a.t > t) continue;
    if (a.do === "state") {
      if (a.tone) s.tone = a.tone;
      if (a.value != null) s.value = a.value;
    } else if (a.do === "highlight") {
      s.highlight = Number(a.value) || 1;
      s.highlightAge = t - a.t;
    } else if (a.do === "pulse") s.pulseAge = t - a.t;
    else if (a.do === "type") s.typeT = a.t;
    else if (a.do === "count") s.countT = a.t;
    else if (a.do === "scramble") s.scrambleAge = t - a.t;
    else if (a.do === "stamp") s.stampT = a.t;
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
export function SceneObject({ obj, shot, t, field, series }: {
  obj: PlanObject; shot: PlanShot; t: number; field: FieldName; series: string;
}): ReactNode {
  const s = objectState(obj, shot, t);
  const p = obj.props;
  const b = obj.box ?? { x: 60, y: 0, w: 960, h: 0 };
  const cx = W / 2;
  const th = theme(field);
  switch (obj.kind) {
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
                          glow={s.pulseAge < 0.8 ? 1 - s.pulseAge / 0.8 : 0} />;
    case "status_pill":
      return <StatusPill x={cx} y={b.y + b.h / 2} text={s.value ?? p.text} tone={(s.tone as Tone) ?? "plain"}
                         icon={p.icon} field={field} p={s.p} />;
    case "trigger_chip":
      return <TriggerChip x={cx} y={b.y + b.h / 2} label={p.label} field={field} p={s.p}
                          firing={pulseOf(s.pulseAge, 0, 0.5)} />;
    case "token_row": {
      const tones = s.value && /^[a-z,]+$/.test(s.value) ? s.value.split(",") : (p.tones ?? []);
      const items = (p.items as string[]).map((text, i) => ({
        text, tone: highlightOn(s) && s.highlight === i + 1 ? "key" as ChipTone : chipTone(tones[i]),
      }));
      return <div style={{ opacity: s.p, transform: `translateY(${(1 - s.p) * 24}px)` }}>
        <TokenRow items={items} x={cx} y={b.y + 4} field={field} center />
      </div>;
    }
    case "big_counter": {
      let value = String(s.value ?? p.value);
      if (s.countT !== null && /^\d+$/.test(value)) {
        value = String(Math.round(Number(value) * ease.outCubic(seg(t, s.countT, 1.2))));
      }
      return <BigCounter value={value} label={p.label} x={cx} y={b.y + b.h / 2} size={220} field={field} p={s.p} />;
    }
    case "callout":
      return <Callout x={b.x + 60} y={b.y} w={b.w - 120} label={p.label} text={p.text}
                      px={b.x + 90} py={b.y + b.h} field={field} p={s.p} />;
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
    case "stamp":
      return s.stampT === null ? null : <Stamp text={p.text} x={b.x} y={b.y} p={seg(t, s.stampT, 0.35)} t={t} />;
    case "connector": {
      const pts = p.points as [number, number][] | undefined;
      if (!pts) return null;
      return <Connector points={pts} tone={(s.tone as Tone) ?? (p.tone as Tone) ?? "info"} broken={!!p.broken && s.tone !== "ok"}
                        pulse={s.pulseAge < 0.8 ? s.pulseAge / 0.8 : -1} draw={seg(t, s.enterT, 0.4)} field={field} />;
    }
    // ------------------------------------------------------- full frame
    case "title_card": {
      const icons = (p.icons ?? []) as { name: string; label: string }[];
      return <>
        <TitleCard series={series} title={p.title} promise={p.promise} icons={icons} t={s.local} />
        {highlightOn(s) && s.highlight <= icons.length && (
          <Overlay><circle cx={270 + (s.highlight - 1) * 270} cy={1230} r={110 + 30 * clamp(s.highlightAge / 0.5)}
                           fill="none" stroke={C.amber} strokeWidth={8} opacity={1 - clamp(s.highlightAge / 0.9)} /></Overlay>
        )}
      </>;
    }
    case "end_card":
      return <>
        <EndCard upNext={p.up_next || "Follow for more"} chips={[]} t={s.local} />
        {s.pulseAge < 0.9 && <Overlay><rect x={cx - 230 - 30 * s.pulseAge} y={1050 - 20 * s.pulseAge} width={460 + 60 * s.pulseAge}
                                             height={96 + 40 * s.pulseAge} rx={60} fill="none" stroke={C.white} strokeWidth={6}
                                             opacity={1 - s.pulseAge / 0.9} /></Overlay>}
      </>;
    case "takeaway_list": {
      const rows = (p.rows as { icon: string; line: string; sub?: string; tone?: string }[]).map((r) => ({
        icon: r.icon, line: r.line, sub: r.sub ?? "", tone: ((r.tone as Tone) ?? "info"),
      }));
      return <>
        <TakeawayList heading={p.heading ?? "Key takeaways"} rows={rows} t={s.local} field={field} />
        {highlightOn(s) && s.highlight <= rows.length && (
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
      const parts = (p.parts as { code: string; icon: string; label: string }[]).map((part) => {
        const row = lines[0].includes(part.code) || !(lines[1] ?? "").includes(part.code) ? 0 : 1;
        const col = Math.max(0, (lines[row] ?? "").indexOf(part.code));
        return { at: [col, part.code.length] as [number, number], icon: part.icon, tone: "info" as Tone,
                 name: part.code, desc: part.label, row };
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
