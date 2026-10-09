// #motion/characters/designer (learning-shorts): design a language's
// character. Pick a preset (the host, a language, or an extra), change skin,
// hair, face, clothes, colours and accessories, watch it live in a few
// gestures and in the reel's character band, then save it as that preset
// (PUT /api/motion-characters/presets/<id> → shorts/motion_character_presets
// .saved.yaml) or reset it to its default. Reels made after a save use it;
// reels already made keep the character they were made with.

import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import type { CharacterConfig } from "../characters/skins/config";
import { buildPerformance, type CharacterCue, type Performance } from "./performance";
import { Backdrop, CHAR_W, SCALE, STAGE } from "./ReelCharacters";
import { Figure, evenWords } from "./CharacterSheet";
import { OPTIONS, PRESET_IDS, defaultPreset, identityOf, labelOf, resetPreset, savePreset, usePresets } from "./presets";
import { LanguageBadge } from "../identity/Identity";
import { FIELDS, FIELD_NAMES, type FieldName } from "../tokens";

const muted = "#9AA0C0";
const card: CSSProperties = { background: "#151A33", borderRadius: 14, padding: "14px 16px", marginBottom: 14 };
const input: CSSProperties = { background: "#232A4D", color: "#E9EBF7", border: 0, borderRadius: 8, padding: "5px 8px", fontSize: 13 };
const btn = (bg: string, fg = "#0E1224"): CSSProperties => ({ background: bg, color: fg, border: 0, borderRadius: 999, padding: "8px 18px",
                                                               fontWeight: 800, cursor: "pointer", fontSize: 13 });

/* The live loop: a wave, a line of speech with a spread of the hands, a point
   up and a thumbs up — the gestures a reel uses most. */
const LOOP = 9.8;
const CUES: CharacterCue[] = [
  { t: 0, kind: "expression", name: "happy", cue: "" },
  { t: 0.3, kind: "gesture", name: "wave", cue: "" },
  { t: 2.7, kind: "gesture", name: "handsSpread", cue: "" },
  { t: 5.3, kind: "gesture", name: "pointUp", cue: "" },
  { t: 7.6, kind: "gesture", name: "thumbsUp", cue: "" },
  { t: 7.6, kind: "expression", name: "grin", cue: "" },
];
const LINE = [{ speaker: "me", words: evenWords("Let me show you how this *really* works.", 2.5) }];
let LIVE: Performance | null = null;
const live = () => (LIVE ??= buildPerformance({ role: "me", seed: 23, cues: CUES }, LINE));

const THUMBS: [string, number][] = [["wave", 1.2], ["handsSpread", 3.5], ["pointUp", 6.1], ["thumbsUp", 8.4]];

function useLoop(len: number): number {
  const [t, setT] = useState(0);
  const t0 = useRef<number | null>(null);
  useEffect(() => {
    let raf = 0;
    const tick = (now: number) => {
      if (t0.current == null) t0.current = now;
      setT(((now - t0.current) / 1000) % len);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [len]);
  return t;
}

function route(): string {
  const q = new URLSearchParams(typeof location === "undefined" ? "" : location.hash.split("?")[1] ?? "");
  const id = q.get("preset") ?? "react";
  return PRESET_IDS.includes(id) ? id : "react";
}

/* ------------------------------------------------------------ controls */

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 34 }}>
      <div style={{ width: 120, color: muted, fontSize: 13, flex: "none" }}>{label}</div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>{children}</div>
    </div>
  );
}

function Choice({ value, options, onChange, name }: { value: string | undefined; options: string[]; onChange: (v: string) => void; name: string }) {
  return (
    <select aria-label={name} data-control={name} value={value ?? ""} onChange={(e) => onChange(e.target.value)} style={input}>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

/** A colour: a picker, a hex field, and quick swatches (named ones first). */
function Colour({ value, onChange, swatches, named = [], name }: {
  value: string | undefined; onChange: (v: string) => void; swatches: [string, string][]; named?: string[]; name: string;
}) {
  const hex = value && value.startsWith("#") ? value : "#000000";
  return (
    <>
      {named.map((n) => (
        <button key={n} onClick={() => onChange(n)} style={{ ...input, outline: value === n ? "2px solid #FDD13E" : "none", cursor: "pointer" }}>{n}</button>
      ))}
      <input aria-label={name} data-control={name} type="color" value={hex} onChange={(e) => onChange(e.target.value.toUpperCase())}
             style={{ width: 34, height: 28, border: 0, background: "none", padding: 0, cursor: "pointer" }} />
      <input key={value} defaultValue={value && value.startsWith("#") ? value : ""} placeholder="#RRGGBB"
             onChange={(e) => /^#[0-9A-Fa-f]{6}$/.test(e.target.value) && onChange(e.target.value.toUpperCase())}
             style={{ ...input, width: 76, fontFamily: "'JetBrains Mono', monospace" }} />
      {swatches.map(([label, c]) => (
        <button key={label + c} title={`${label} ${c}`} onClick={() => onChange(c)}
                style={{ width: 22, height: 22, borderRadius: 6, background: c, border: value === c ? "2px solid #FDD13E" : "1px solid rgba(255,255,255,.3)", cursor: "pointer" }} />
      ))}
    </>
  );
}

function Check({ label, value, onChange }: { label: string; value: boolean | undefined; onChange: (v: boolean) => void }) {
  return (
    <label style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 13, cursor: "pointer" }}>
      <input type="checkbox" data-control={label} checked={!!value} onChange={(e) => onChange(e.target.checked)} />{label}
    </label>
  );
}

function Slider({ value, onChange, name }: { value: number; onChange: (v: number) => void; name: string }) {
  return (
    <>
      <input aria-label={name} type="range" min={0.9} max={1.1} step={0.01} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{value.toFixed(2)}</span>
    </>
  );
}

/* ------------------------------------------------------------ previews */

/** The character where a reel puts it: the band between the objects and the
 * captions, with the language badge in its corner — a slice of the frame. */
function ReelBand({ config, field, t, id }: { config: CharacterConfig; field: FieldName; t: number; id: string }) {
  const ident = identityOf(id);
  const k = 0.42;
  const top = 60, h = STAGE.bottom - STAGE.top;
  return (
    <div style={{ width: 1080 * k, height: (h + top + 40) * k, overflow: "hidden", borderRadius: 10, position: "relative", flex: "none" }}>
      <div style={{ position: "absolute", width: 1080, height: h + top + 40, background: FIELDS[field], transform: `scale(${k})`, transformOrigin: "0 0" }}>
        {ident && <LanguageBadge spec={ident} field={field} right={54} top={8} />}
        <div style={{ position: "absolute", top, left: 0, width: 1080, height: h, overflow: "hidden" }}>
          <Backdrop field={field} cx={STAGE.center_x} size={h - 8} />
          <div style={{ position: "absolute", left: STAGE.center_x - CHAR_W / 2, top: -STAGE.view.top * SCALE }}>
            <Figure config={config} perf={live()} t={t} width={CHAR_W} />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ page */

export function CharacterDesigner() {
  const { effective, saved, api, loading, reload } = usePresets();
  const [id, setId] = useState(route);
  const [draft, setDraft] = useState<CharacterConfig>(() => effective[id]);
  const [field, setField] = useState<FieldName>("navy");
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const t = useLoop(LOOP);
  const base = effective[id];
  // pick up the API's saved version once it loads, and a new preset when chosen
  useEffect(() => { setDraft(effective[id]); setMsg(null); }, [id, loading]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const on = () => setId(route());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const dirty = JSON.stringify(draft) !== JSON.stringify(base);
  const isDefault = JSON.stringify(base) === JSON.stringify(defaultPreset(id));
  const ident = identityOf(id);
  const sw: [string, string][] = [
    ...(ident ? [["signature", ident.colour], ["on dark", ident.on_dark], ["on light", ident.on_light]] as [string, string][] : []),
    ["white", "#FFFFFF"], ["paper", "#F4F7FA"], ["navy", "#1B2238"], ["ink", "#171A3B"], ["slate", "#2A2F45"], ["grey", "#6C6F7A"],
  ];
  const set = (fn: (c: CharacterConfig) => CharacterConfig) => { setDraft((c) => fn(structuredClone(c))); setMsg(null); };
  const o = OPTIONS;

  const save = async () => {
    try { await savePreset(id, draft); setMsg({ text: `Saved as the ${labelOf(id)} preset. Reels made from now on use it.`, ok: true }); reload(); }
    catch (e) { setMsg({ text: `Not saved: ${(e as Error).message}`, ok: false }); }
  };
  const reset = async () => {
    if (!confirm(`Reset ${labelOf(id)} to its default? The saved version is removed.`)) return;
    try { const d = await resetPreset(id); setDraft(d); setMsg({ text: `${labelOf(id)} is back to its default.`, ok: true }); reload(); }
    catch (e) { setMsg({ text: `Not reset: ${(e as Error).message}`, ok: false }); }
  };

  return (
    <div>
      <style>{"[data-character] > svg { overflow: visible; }"}</style>
      <p style={{ color: muted, fontSize: 13, margin: "0 0 12px", maxWidth: 1040 }}>
        Design the character that plays a language (or the shared host). Changes preview live; <b>Save</b> stores them as that
        preset in <code>shorts/motion_character_presets.saved.yaml</code>, used by every reel made afterwards (reels already
        made keep their character). <b>Reset to default</b> brings back <code>motion_character_presets.yaml</code>'s version.
        One reel can use another preset with <code>motion_reel --character &lt;preset&gt;</code>.{" "}
        <a href="#motion/characters" style={{ color: "#FDD13E", fontWeight: 700 }}>All characters</a>
      </p>
      {!api && !loading && (
        <div style={{ ...card, background: "#3A2A16", color: "#FDD13E", fontSize: 13 }}>
          The API server is not reachable, so this page shows the defaults and cannot save. Start the API server and reload.
        </div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {PRESET_IDS.map((p) => (
          <a key={p} href={`#motion/characters/designer?preset=${p}`} data-preset={p}
             style={{ ...input, textDecoration: "none", fontWeight: 700, outline: p === id ? "2px solid #FDD13E" : "none",
                      color: p === id ? "#FDD13E" : "#E9EBF7" }}>
            {labelOf(p)}{saved.has(p) ? " •" : ""}</a>
        ))}
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ ...card, flex: "0 0 auto" }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
            {FIELD_NAMES.map((f) => (
              <button key={f} onClick={() => setField(f)} title={f}
                      style={{ width: 26, height: 26, borderRadius: 6, background: FIELDS[f], border: field === f ? "2px solid #FDD13E" : "1px solid rgba(255,255,255,.3)", cursor: "pointer" }} />
            ))}
            <span style={{ color: muted, fontSize: 12, alignSelf: "center" }}>background</span>
          </div>
          <div style={{ background: FIELDS[field], borderRadius: 12, padding: "6px 30px", display: "flex", justifyContent: "center" }}>
            <Figure id={id} config={draft} perf={live()} t={t} width={260} />
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            {THUMBS.map(([g, at]) => (
              <div key={g} style={{ background: FIELDS[field], borderRadius: 8, padding: 4, textAlign: "center" }}>
                <Figure config={draft} perf={live()} t={at} width={68} />
                <div style={{ fontSize: 10, color: field === "navy" || field === "blue" ? "#E9EBF7" : "#0E1224" }}>{g}</div>
              </div>
            ))}
          </div>
          <div style={{ color: muted, fontSize: 12, margin: "10px 0 4px" }}>In a reel (the character band, with the badge):</div>
          <ReelBand config={draft} field={field} t={t} id={id} />
        </div>

        <div style={{ ...card, flex: "1 1 520px", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
            <div style={{ fontSize: 20, fontWeight: 800 }}>{labelOf(id)}</div>
            <span style={{ fontSize: 12, color: muted }}>{dirty ? "unsaved changes" : saved.has(id) && !isDefault ? "saved (differs from default)" : "default"}</span>
          </div>
          <Row label="Name"><input value={draft.name} onChange={(e) => set((c) => ({ ...c, name: e.target.value }))} style={input} data-control="name" /></Row>
          <Row label="Body"><Choice name="gender" value={draft.gender} options={o.gender} onChange={(v) => set((c) => ({ ...c, gender: v as CharacterConfig["gender"] }))} />
            <Choice name="art" value={draft.art} options={o.art} onChange={(v) => set((c) => ({ ...c, art: v as CharacterConfig["art"] }))} />
            <span style={{ color: muted, fontSize: 12 }}>height</span><Slider name="height" value={draft.build.height} onChange={(v) => set((c) => ({ ...c, build: { ...c.build, height: v } }))} />
            <span style={{ color: muted, fontSize: 12 }}>shoulders</span><Slider name="shoulders" value={draft.build.shoulders} onChange={(v) => set((c) => ({ ...c, build: { ...c.build, shoulders: v } }))} /></Row>
          <Row label="Skin tone"><Colour name="skinTone" value={draft.skinTone} named={o.skinTone} swatches={[]} onChange={(v) => set((c) => ({ ...c, skinTone: v as CharacterConfig["skinTone"] }))} /></Row>
          <Row label="Hair"><Choice name="hairStyle" value={draft.hair.style} options={o.hairStyle} onChange={(v) => set((c) => ({ ...c, hair: { ...c.hair, style: v as CharacterConfig["hair"]["style"] } }))} />
            <Colour name="hairColor" value={draft.hair.color} named={o.hairColor} swatches={[]} onChange={(v) => set((c) => ({ ...c, hair: { ...c.hair, color: v as CharacterConfig["hair"]["color"] } }))} /></Row>
          <Row label="Face">
            {(["jaw", "brows", "eyes", "mouth"] as const).map((k) => (
              <Choice key={k} name={k} value={draft.face[k]} options={o[k]} onChange={(v) => set((c) => ({ ...c, face: { ...c.face, [k]: v } as CharacterConfig["face"] }))} />
            ))}</Row>
          <Row label="Top"><Choice name="top" value={draft.outfit.top} options={o.top} onChange={(v) => set((c) => ({ ...c, outfit: { ...c.outfit, top: v as CharacterConfig["outfit"]["top"] } }))} />
            <Colour name="topColor" value={draft.outfit.topColor} swatches={sw} onChange={(v) => set((c) => ({ ...c, outfit: { ...c.outfit, topColor: v as `#${string}` } }))} /></Row>
          <Row label="Bottom"><Choice name="bottom" value={draft.outfit.bottom} options={o.bottom} onChange={(v) => set((c) => ({ ...c, outfit: { ...c.outfit, bottom: v as CharacterConfig["outfit"]["bottom"] } }))} />
            <Colour name="bottomColor" value={draft.outfit.bottomColor} swatches={sw} onChange={(v) => set((c) => ({ ...c, outfit: { ...c.outfit, bottomColor: v as `#${string}` } }))} /></Row>
          <Row label="Shoes"><Colour name="shoeColor" value={draft.outfit.shoeColor} swatches={sw} onChange={(v) => set((c) => ({ ...c, outfit: { ...c.outfit, shoeColor: v as `#${string}` } }))} /></Row>
          <Row label="Tie / hair band"><Colour name="accentColor" value={draft.outfit.accentColor} swatches={sw} onChange={(v) => set((c) => ({ ...c, outfit: { ...c.outfit, accentColor: v as `#${string}` } }))} />
            {draft.outfit.accentColor && <button style={{ ...input, cursor: "pointer" }} onClick={() => set((c) => { delete c.outfit.accentColor; return c; })}>auto</button>}</Row>
          <Row label="Glasses / beard">
            <Choice name="glasses" value={draft.accessories.glasses ?? "none"} options={o.glasses} onChange={(v) => set((c) => ({ ...c, accessories: { ...c.accessories, glasses: v as "none" } }))} />
            <Choice name="beard" value={draft.accessories.beard ?? "none"} options={o.beard} onChange={(v) => set((c) => ({ ...c, accessories: { ...c.accessories, beard: v as "none" } }))} /></Row>
          <Row label="Accessories">
            {o.flags.map((k) => (
              <Check key={k} label={k} value={(draft.accessories as Record<string, boolean | undefined>)[k]}
                     onChange={(v) => set((c) => ({ ...c, accessories: { ...c.accessories, [k]: v } }))} />
            ))}</Row>

          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap", alignItems: "center" }}>
            <button onClick={save} disabled={!api || !dirty} data-action="save"
                    style={{ ...btn("#FDD13E"), opacity: api && dirty ? 1 : 0.4, cursor: api && dirty ? "pointer" : "default" }}>
              Save as {labelOf(id)} preset</button>
            <button onClick={() => { setDraft(base); setMsg(null); }} disabled={!dirty} style={{ ...btn("#232A4D", "#E9EBF7"), opacity: dirty ? 1 : 0.4 }}>Discard changes</button>
            <button onClick={reset} disabled={!api || isDefault} data-action="reset"
                    style={{ ...btn("#232A4D", "#E9EBF7"), opacity: api && !isDefault ? 1 : 0.4 }}>Reset to default</button>
            <button onClick={() => navigator.clipboard?.writeText(JSON.stringify(draft, null, 2))} style={{ ...btn("transparent", muted) }}>Copy JSON</button>
          </div>
          {msg && <div style={{ marginTop: 10, fontSize: 13, color: msg.ok ? "#17B27B" : "#F2555A" }}>{msg.text}</div>}
          <Diff a={defaultPreset(id)} b={draft} />
        </div>
      </div>
    </div>
  );
}

/** What differs from the default, so a reviewer sees the change at a glance. */
function Diff({ a, b }: { a: CharacterConfig; b: CharacterConfig }) {
  const rows = useMemo(() => {
    const out: string[] = [];
    const walk = (x: unknown, y: unknown, path: string) => {
      if (x && y && typeof x === "object" && typeof y === "object") {
        for (const k of new Set([...Object.keys(x as object), ...Object.keys(y as object)]))
          walk((x as Record<string, unknown>)[k], (y as Record<string, unknown>)[k], path ? `${path}.${k}` : k);
      } else if (JSON.stringify(x) !== JSON.stringify(y)) out.push(`${path}: ${JSON.stringify(x) ?? "—"} → ${JSON.stringify(y) ?? "—"}`);
    };
    walk(a, b, "");
    return out;
  }, [a, b]);
  if (!rows.length) return <div style={{ marginTop: 10, color: muted, fontSize: 12 }}>Same as the default.</div>;
  return (
    <div style={{ marginTop: 10, fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: muted }}>
      <div style={{ fontFamily: "inherit", marginBottom: 2 }}>Differs from the default:</div>
      {rows.map((r) => <div key={r}>{r}</div>)}
    </div>
  );
}
