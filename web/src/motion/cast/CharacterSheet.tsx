// #motion/characters (learning-shorts): the reel characters.
//
//  1. Every language's character as it is now (its default, or what the
//     designer saved over it) with the shared host, each linking to the
//     designer (#motion/characters/designer).
//  2. A stage that plays the selected expression, gesture or a lip-synced
//     exchange on the host and a chosen language character, with
//     play/pause and a scrubber.
//  3. Grids of every expression and gesture, held at their peak.
//
// The rig is the characters lab's (characters/SOURCE.md); the people are our
// presets (shorts/motion_character_presets.yaml). Every frame is drawn from
// performance.ts, the same pure path the reel player uses.

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ACTION_GROUPS, ACTIONS, EXPRESSIONS } from "../characters/actions";
import { Character } from "../characters/rig/Character";
import type { CharacterConfig } from "../characters/skins/config";
import { buildPerformance, poseOf, type CharacterCue, type Performance, type SpokenLine } from "./performance";
import { skinFor } from "./ReelCharacters";
import { EXTRAS, LANGUAGES, identityOf, labelOf, usePresets } from "./presets";
import { IdentitySymbol, toneOn } from "../identity/Identity";
import library from "../library.json";
import { FIELDS } from "../tokens";

const VOCAB = (library as unknown as { characters: Record<string, unknown> & { expressions: Record<string, string> } }).characters;
type Who = "host" | "lang";
type Item = { kind: "expression" | "gesture" | "talk"; name: string };

const muted = "#9AA0C0";
const card: CSSProperties = { background: "#151A33", borderRadius: 14, padding: "14px 16px", marginBottom: 14 };
const START = 0.25; // a gesture starts here, after a moment of rest
const SEEDS: Record<Who, number> = { host: 11, lang: 23 };

/* An even-timed exchange, the way stub mode times words: the host asks, the
   language character answers. */
export function evenWords(text: string, start: number, wps = 2.6) {
  return text.split(" ").map((w, i) => ({ text: w, start: start + i / wps, end: start + (i + 0.85) / wps, hl: /\*/.test(w) }))
    .map((w) => ({ ...w, text: w.text.replace(/\*/g, "") }));
}
const TALK: SpokenLine[] = [
  { speaker: "host", words: evenWords("Why does this counter stay *stuck* at zero?", 0.3) },
  { speaker: "lang", words: evenWords("Because a plain variable *resets* on every render.", 3.6) },
];

function itemLength(it: Item): number {
  if (it.kind === "talk") return 7.6;
  if (it.kind === "expression") return 3;
  const a = ACTIONS[it.name];
  return START + (a?.loop ? a.duration * 2 : a?.duration ?? 1) + 0.9;
}

const CACHE = new Map<string, Performance>();
function performanceOf(who: Who, it: Item): Performance {
  const key = `${who}:${it.kind}:${it.name}`;
  let p = CACHE.get(key);
  if (!p) {
    const cues: CharacterCue[] = it.kind === "gesture" ? [{ t: START, kind: "gesture", name: it.name, cue: "" }]
      : it.kind === "expression" ? [{ t: 0.1, kind: "expression", name: it.name, cue: "" }]
      : [{ t: 0, kind: "expression", name: "happy", cue: "" }];
    p = buildPerformance({ role: who, seed: SEEDS[who], cues }, it.kind === "talk" ? TALK : []);
    CACHE.set(key, p);
  }
  return p;
}

/** The moment a tile shows: an expression settled, a gesture at its hold. */
function peak(it: Item): number {
  if (it.kind === "expression") return 1.4;
  const a = ACTIONS[it.name];
  return START + (a ? a.duration * 0.45 : 0.5);
}

/* A head-and-shoulders crop of the 400 x 600 rig, so a face reads at tile size. */
const FACE = { x: 110, y: 22, w: 180, h: 210 };

/** One character, whole or cropped to the face. */
export function Figure({ config, perf, t, width, face, id }: { config: CharacterConfig; perf: Performance; t: number; width: number; face?: boolean; id?: string }) {
  const pic = <Character pose={poseOf(perf, t)} skin={skinFor(config)} width={width} />;
  if (!face) return <div data-character={id}>{pic}</div>;
  const k = width / 400;
  return (
    <div data-character={id} style={{ width: FACE.w * k, height: FACE.h * k, overflow: "hidden", position: "relative" }}>
      <div style={{ position: "absolute", left: -FACE.x * k, top: -FACE.y * k }}>{pic}</div>
    </div>
  );
}

function Pair({ it, t, width, face, host, lang }: { it: Item; t: number; width: number; face?: boolean; host: CharacterConfig; lang: CharacterConfig }) {
  return (
    <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
      <Figure config={host} perf={performanceOf("host", it)} t={t} width={width} face={face} />
      <Figure config={lang} perf={performanceOf("lang", it)} t={t} width={width} face={face} />
    </div>
  );
}

const IDLE: Item = { kind: "expression", name: "happy" };

/** Every language's character with the host: the default, or the designer's save. */
function Roster({ effective, saved, api }: { effective: Record<string, CharacterConfig>; saved: Set<string>; api: boolean }) {
  const ids = ["host", ...LANGUAGES, ...EXTRAS];
  return (
    <div style={card}>
      <div style={{ fontWeight: 800 }}>Characters by language <span style={{ color: muted, fontWeight: 600, fontSize: 13 }}>({ids.length})</span></div>
      <div style={{ color: muted, fontSize: 12, margin: "2px 0 10px" }}>
        One per course language, wearing its signature colour, plus the shared host (the asking speaker of every two-speaker reel)
        and two extras for <code>motion_reel --character</code>. Each shows its default
        (<code>shorts/motion_character_presets.yaml</code>) or, marked SAVED, what the designer saved over it.
        {!api && " (API server not reachable: showing defaults only.)"} Click one to open it in the designer.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
        {ids.map((id) => {
          const ident = identityOf(id);
          return (
            <a key={id} href={`#motion/characters/designer?preset=${id}`} data-preset={id}
               style={{ background: FIELDS.navy, borderRadius: 10, padding: "8px 6px 6px", color: "#E9EBF7", textDecoration: "none",
                        position: "relative", display: "block" }}>
              <div style={{ height: 28, display: "flex", justifyContent: "flex-end" }}>
                {ident && (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 10px 3px 6px", borderRadius: 999,
                                 background: "#1A2142", border: "2px solid rgba(255,255,255,0.12)", fontFamily: "'JetBrains Mono', monospace",
                                 fontWeight: 700, fontSize: 11, letterSpacing: 1.4, textTransform: "uppercase" }}>
                    <IdentitySymbol spec={ident} size={16} colour={toneOn(ident, "navy")} />{ident.name}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", justifyContent: "center" }}>
                <Figure id={id} config={effective[id]} perf={performanceOf("lang", IDLE)} t={1.4} width={112} />
              </div>
              <div style={{ fontSize: 13, fontWeight: 800, marginTop: 2 }}>{labelOf(id)}
                {saved.has(id) && <span style={{ color: "#FDD13E", marginLeft: 6, fontSize: 10, letterSpacing: 1 }}>SAVED</span>}
              </div>
              <div style={{ fontSize: 11, color: muted }}>{effective[id].name} · {effective[id].outfit.top} {effective[id].outfit.topColor}</div>
            </a>
          );
        })}
      </div>
    </div>
  );
}

function Stage({ it, host, lang, langLabel }: { it: Item; host: CharacterConfig; lang: CharacterConfig; langLabel: string }) {
  const len = itemLength(it);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const from = useRef<{ wall: number; t: number } | null>(null);
  useEffect(() => { setT(0); from.current = null; }, [it.kind, it.name]);
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = (now: number) => {
      if (!from.current) from.current = { wall: now, t };
      setT((from.current.t + (now - from.current.wall) / 1000) % len);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); from.current = null; };
  }, [playing, len, it.kind, it.name]); // eslint-disable-line react-hooks/exhaustive-deps
  const speaking = it.kind === "talk" ? TALK.find((l) => l.words.length && t >= l.words[0].start - 0.1 && t <= l.words[l.words.length - 1].end + 0.2) : undefined;
  return (
    <div style={{ ...card, display: "flex", gap: 22, alignItems: "center", flexWrap: "wrap" }}>
      <div style={{ background: FIELDS.navy, borderRadius: 12, padding: "8px 18px" }}>
        <Pair it={it} t={t} width={240} host={host} lang={lang} />
      </div>
      <div style={{ minWidth: 300, flex: 1 }}>
        <div style={{ fontSize: 22, fontWeight: 800 }}>{it.kind === "talk" ? "Lip-sync" : it.name}
          <span style={{ color: muted, fontSize: 14, fontWeight: 600 }}> · {it.kind} · host and {langLabel}</span></div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", margin: "12px 0" }}>
          <button onClick={() => setPlaying((p) => !p)}
                  style={{ background: "#FDD13E", color: "#0E1224", border: 0, borderRadius: 999, padding: "8px 20px", fontWeight: 800, cursor: "pointer" }}>
            {playing ? "Pause" : "Play"}</button>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}>{t.toFixed(2)}s / {len.toFixed(2)}s</span>
        </div>
        <input type="range" min={0} max={len} step={0.01} value={t} style={{ width: "100%" }}
               onChange={(e) => { setPlaying(false); setT(Number(e.target.value)); }} />
        {it.kind === "talk" && (
          <div style={{ marginTop: 10, fontSize: 15, lineHeight: 1.6 }}>
            {TALK.map((l) => (
              <div key={l.speaker} style={{ opacity: speaking === l ? 1 : 0.5 }}>
                <b>{l.speaker === "host" ? "Host" : langLabel}:</b>{" "}
                {l.words.map((w, i) => <span key={i} style={{ color: t >= w.start ? "#FDD13E" : undefined }}>{w.text} </span>)}
              </div>
            ))}
            <div style={{ color: muted, fontSize: 12 }}>Mouth shapes are laid inside each word's start and end (even timing
              here; forced alignment in a real reel). Highlighted words add a small head dip.</div>
          </div>
        )}
        <div style={{ color: muted, fontSize: 12, marginTop: 8 }}>Click any tile below to play it here. Pure in t: scrub and the
          frame is the same at the same time.</div>
      </div>
    </div>
  );
}

function Grid({ title, items, note, onPick, selected, used, host, lang }: {
  title: string; items: Item[]; note?: string; onPick: (it: Item) => void; selected: Item; used: Set<string>;
  host: CharacterConfig; lang: CharacterConfig;
}) {
  return (
    <div style={card}>
      <div style={{ fontWeight: 800, marginBottom: 2 }}>{title} <span style={{ color: muted, fontWeight: 600, fontSize: 13 }}>({items.length})</span></div>
      {note && <div style={{ color: muted, fontSize: 12, marginBottom: 8 }}>{note}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(176px, 1fr))", gap: 8 }}>
        {items.map((it) => {
          const on = selected.kind === it.kind && selected.name === it.name;
          return (
            <button key={it.name} onClick={() => onPick(it)} data-item={`${it.kind}:${it.name}`}
                    style={{ background: FIELDS.navy, border: on ? "2px solid #FDD13E" : "2px solid transparent", borderRadius: 10,
                             padding: "6px 4px 4px", cursor: "pointer", color: "#E9EBF7" }}>
              <Pair it={it} t={peak(it)} width={it.kind === "expression" ? 190 : 82} face={it.kind === "expression"} host={host} lang={lang} />
              <div style={{ fontSize: 12, fontWeight: 700, marginTop: 2 }}>{it.name}
                {used.has(it.name) && <span style={{ color: "#FDD13E", marginLeft: 6, fontSize: 10, letterSpacing: 1 }}>REEL</span>}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function CharacterSheet() {
  const { effective, saved, api } = usePresets();
  const [sel, setSel] = useState<Item>({ kind: "talk", name: "talk" });
  const [langId, setLangId] = useState("react");
  const used = useMemo(() => new Set(JSON.stringify([VOCAB.gestures, VOCAB.present, VOCAB.narrator_explain, Object.values(VOCAB.expressions)])
    .match(/[A-Za-z]+/g) ?? []), []);
  const pick = (it: Item) => { setSel(it); document.getElementById("stage")?.scrollIntoView({ behavior: "smooth" }); };
  const host = effective.host;
  const lang = effective[langId];
  const groups: [string, string][] = [["hands", "Hands and arms"], ["head", "Head"], ["body", "Body"], ["face", "Face one-shots"]];
  return (
    <div>
      <style>{"[data-character] > svg { overflow: visible; }"}</style>
      <p style={{ color: muted, fontSize: 13, margin: "0 0 14px", maxWidth: 1040 }}>
        The animated characters of motion reels: an optional layer, off by default (<code>MOTION_CHARACTERS=1</code> or
        <code> motion_reel --characters</code>). One character per speaker: in a two-speaker reel (interview, rapid-fire interview, peer
        discussion, mentor &amp; student) the host asks (left) and the language's character answers (right); in a one-narrator
        reel the language's character narrates alone. Gestures are cued on spoken words; mouths follow the caption word timings. The rig is the
        characters lab's (web/src/motion/characters/SOURCE.md).{" "}
        <a href="#motion/characters/designer" style={{ color: "#FDD13E", fontWeight: 700 }}>Open the designer</a>.
      </p>
      <Roster effective={effective} saved={saved} api={api} />
      <div id="stage" style={{ display: "flex", gap: 10, alignItems: "center", margin: "0 0 8px", flexWrap: "wrap" }}>
        <span style={{ fontWeight: 800 }}>Stage:</span>
        <span style={{ color: muted, fontSize: 13 }}>the host and</span>
        <select value={langId} onChange={(e) => setLangId(e.target.value)}
                style={{ background: "#232A4D", color: "#E9EBF7", border: 0, borderRadius: 8, padding: "5px 8px" }}>
          {[...LANGUAGES, ...EXTRAS].map((id) => <option key={id} value={id}>{labelOf(id)}</option>)}
        </select>
        <button onClick={() => pick({ kind: "talk", name: "talk" })}
                style={{ background: "none", border: 0, color: "#FDD13E", fontWeight: 700, cursor: "pointer" }}>Play the lip-sync sample</button>
      </div>
      <Stage it={sel} host={host} lang={lang} langLabel={labelOf(langId)} />
      <Grid title="Expressions" items={Object.keys(EXPRESSIONS).map((name) => ({ kind: "expression", name }))} used={used}
            host={host} lang={lang}
            note="Head and shoulders, 1.4 s after the expression starts (it cross-fades in over 0.35 s); the idle layer keeps breathing and blinking. Tiles marked REEL are the ones the reel director uses."
            onPick={pick} selected={sel} />
      {groups.map(([g, title]) => (
        <Grid key={g} title={`Gestures: ${title}`} selected={sel} onPick={pick} used={used} host={host} lang={lang}
              note={g === "hands" ? "Each shown at about the middle of the gesture." : undefined}
              items={(ACTION_GROUPS as Record<string, string[]>)[g].map((name) => ({ kind: "gesture", name }))} />
      ))}
    </div>
  );
}
