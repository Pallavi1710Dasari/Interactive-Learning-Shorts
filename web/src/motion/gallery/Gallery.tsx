// #motion-gallery — every motion object, transition and animation, checked
// frame by frame (REFERENCE_STYLE_ADDENDUM.md 4.6 E):
//
//   #motion-gallery                 overview: objects on paper AND dark, every
//                                   transition/animation with a scrubber and
//                                   the matching reference frames
//   #motion-gallery/fonts           Anton vs Archivo Black, side by side
//   #motion-gallery/strip/<id>      n evenly spaced frames of one entry above
//                                   the reference frames (for screenshots)
//   #motion-gallery/frame/<id>?t=   one frame alone, full size
//
// Query: t=<seconds>, field=<navy|blue|paper|yellow>, font=<anton|archivo>, n=<frames>.
//
// The gallery is the only place a clock runs (requestAnimationFrame while
// playing); every component it shows is still a pure function of t.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Fit, Frame } from "../Stage";
import { DISPLAY_FONTS, FPS, W, type DisplayFont, type FieldName } from "../tokens";
import { ENTRIES, GROUPS, SETTLED, type Entry } from "./catalog";
import { ChapterCard, KineticTitle, BigCounter } from "../objects/editorial";

interface Route { view: "overview" | "fonts" | "strip" | "frame"; id?: string; q: URLSearchParams }

function parseRoute(): Route {
  const raw = location.hash.replace(/^#/, "");
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").slice(1);
  const q = new URLSearchParams(query);
  if (parts[0] === "fonts") return { view: "fonts", q };
  if ((parts[0] === "strip" || parts[0] === "frame") && parts[1]) return { view: parts[0], id: parts[1], q };
  return { view: "overview", q };
}

const page: React.CSSProperties = {
  minHeight: "100vh", background: "#0E1224", color: "#E9EBF7", fontFamily: "'Manrope Variable', system-ui, sans-serif",
  padding: "24px 28px 80px",
};

export function MotionGallery() {
  const [route, setRoute] = useState(parseRoute);
  useEffect(() => {
    const on = () => setRoute(parseRoute());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const [font, setFont] = useState<DisplayFont>((route.q.get("font") as DisplayFont) || "anton");
  const vars = { ["--motion-display" as string]: DISPLAY_FONTS[font] } as React.CSSProperties;

  if (route.view === "frame" && route.id) return <div style={vars}><SingleFrame route={route} /></div>;
  if (route.view === "strip" && route.id) return <div style={{ ...page, ...vars }}><Strip route={route} /></div>;
  if (route.view === "fonts") return <div style={page}><Fonts /></div>;

  return (
    <div style={{ ...page, ...vars }}>
      <header style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", marginBottom: 8 }}>
        <h1 style={{ margin: 0, fontSize: 26 }}>Motion gallery</h1>
        <span style={{ color: "#9AA0C0", fontSize: 14 }}>{ENTRIES.length} entries · every frame a pure function of t</span>
        <label style={{ marginLeft: "auto", fontSize: 14 }}>
          Display font{" "}
          <select value={font} onChange={(e) => setFont(e.target.value as DisplayFont)}>
            <option value="anton">Anton</option>
            <option value="archivo">Archivo Black</option>
          </select>
        </label>
        <a href="#motion-gallery/fonts" style={{ color: "#B9A8FF", fontSize: 14 }}>Compare fonts</a>
      </header>
      <nav style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 14, marginBottom: 24 }}>
        {GROUPS.map((g) => <a key={g} href={`#motion-gallery`} onClick={(e) => { e.preventDefault(); document.getElementById(g)?.scrollIntoView(); }}
                              style={{ color: "#FDD13E" }}>{g}</a>)}
      </nav>
      {GROUPS.map((g) => (
        <section key={g} id={g} style={{ marginBottom: 40 }}>
          <h2 style={{ fontSize: 20, borderBottom: "1px solid #2A3052", paddingBottom: 6 }}>{g}</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 22 }}>
            {ENTRIES.filter((e) => e.group === g).map((e) =>
              e.both ? <ObjectCard key={e.id} entry={e} /> : <Player key={e.id} entry={e} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

function Card({ entry, children }: { entry: Entry; children: ReactNode }) {
  return (
    <div style={{ background: "#151A33", borderRadius: 14, padding: 14, maxWidth: 760 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
        <b style={{ fontSize: 16 }}>{entry.title}</b>
        <a href={`#motion-gallery/strip/${entry.id}`} style={{ color: "#9AA0C0", fontSize: 12 }}>filmstrip</a>
      </div>
      <p style={{ margin: "4px 0 10px", fontSize: 13, color: "#9AA0C0", maxWidth: 680 }}>{entry.note}</p>
      {children}
    </div>
  );
}

/** An object on paper and on a dark field, with its own little scrubber. */
function ObjectCard({ entry }: { entry: Entry }) {
  const [t, setT] = useState(entry.dur);
  const dark: FieldName = entry.field === "paper" || entry.field === "yellow" ? "navy" : entry.field;
  const light: FieldName = entry.field === "paper" || entry.field === "yellow" ? entry.field : "paper";
  return (
    <Card entry={entry}>
      <div style={{ display: "flex", gap: 10 }}>
        <Fit width={200}>{entry.render(t, light)}</Fit>
        <Fit width={200}>{entry.render(t, dark)}</Fit>
      </div>
      <Scrubber t={t} setT={setT} dur={entry.dur} />
    </Card>
  );
}

function useRefFrames(id?: string) {
  const [frames, setFrames] = useState<{ count: number; times: number[] } | null>(null);
  useEffect(() => {
    if (!id) return;
    let alive = true;
    fetch(`/reference/${id}/frames.json`).then((r) => (r.ok ? r.json() : null)).then((j) => alive && setFrames(j)).catch(() => {});
    return () => { alive = false; };
  }, [id]);
  return frames;
}
const refSrc = (id: string, i: number) => `/reference/${id}/${String(i).padStart(3, "0")}.jpg`;

/** A transition or animation: the component, a scrubber, and the reference
 * frame at the same point of the move beside it. */
function Player({ entry }: { entry: Entry }) {
  // Opens mid-move, so the overview shows each one doing something.
  const [t, setT] = useState(Math.round(entry.dur * 0.55 * FPS) / FPS);
  const frames = useRefFrames(entry.ref);
  const p = entry.dur > 0 ? Math.min(1, t / entry.dur) : 0;
  const ri = frames ? Math.round(p * (frames.count - 1)) : 0;
  return (
    <Card entry={entry}>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <Fit width={260}>{entry.render(t, entry.field)}</Fit>
        {frames && entry.ref && (
          <div>
            <img src={refSrc(entry.ref, ri)} width={260} height={462} style={{ display: "block", borderRadius: 4 }} alt="reference frame" />
            <div style={{ fontSize: 11, color: "#9AA0C0", marginTop: 4 }}>reference {frames.times[ri]?.toFixed(2)} s</div>
          </div>
        )}
      </div>
      {frames && entry.ref && (
        <div style={{ display: "flex", gap: 2, marginTop: 8, overflowX: "auto", maxWidth: 540 }}>
          {Array.from({ length: frames.count }, (_, i) => (
            <img key={i} src={refSrc(entry.ref!, i)} width={36} height={64} alt=""
                 style={{ outline: i === ri ? "2px solid #FDD13E" : "none", opacity: i === ri ? 1 : 0.6, cursor: "pointer" }}
                 onClick={() => setT((i / Math.max(1, frames.count - 1)) * entry.dur)} />
          ))}
        </div>
      )}
      <Scrubber t={t} setT={setT} dur={entry.dur} />
    </Card>
  );
}

function Scrubber({ t, setT, dur }: { t: number; setT: (t: number) => void; dur: number }) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const tRef = useRef(t);
  tRef.current = t;
  useEffect(() => {
    if (!playing) return;
    let raf = 0, last = performance.now();
    const step = (now: number) => {
      const next = tRef.current + ((now - last) / 1000) * speed;
      last = now;
      setT(next > dur ? 0 : next);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, dur, setT]);
  const frame = 1 / FPS;
  const btn: React.CSSProperties = { background: "#2A3052", color: "#E9EBF7", border: 0, borderRadius: 6, padding: "4px 10px", cursor: "pointer" };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 13 }}>
      <button style={btn} onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button>
      <button style={btn} onClick={() => setT(Math.max(0, t - frame))} aria-label="previous frame">−1f</button>
      <button style={btn} onClick={() => setT(Math.min(dur, t + frame))} aria-label="next frame">+1f</button>
      <input type="range" min={0} max={dur} step={frame} value={t} onChange={(e) => setT(Number(e.target.value))} style={{ width: 220 }} />
      <span style={{ fontVariantNumeric: "tabular-nums", width: 110 }}>{t.toFixed(3)} s · f{Math.round(t * FPS)}</span>
      <button style={btn} onClick={() => setSpeed(speed === 1 ? 0.25 : 1)}>{speed}×</button>
    </div>
  );
}

function entryFor(route: Route): Entry | undefined {
  return ENTRIES.find((e) => e.id === route.id);
}

function SingleFrame({ route }: { route: Route }) {
  const e = entryFor(route);
  if (!e) return <p>no entry {route.id}</p>;
  const t = Number(route.q.get("t") ?? (e.both ? SETTLED : 0));
  const field = (route.q.get("field") as FieldName) || e.field;
  const width = Number(route.q.get("w") ?? Math.min(window.innerWidth, (window.innerHeight * 9) / 16));
  return <Fit width={width}>{e.render(Math.min(t, e.dur || t), field)}</Fit>;
}

/** n evenly spaced frames of one entry, the reference frames under them. */
function Strip({ route }: { route: Route }) {
  const e = entryFor(route);
  const frames = useRefFrames(e?.ref);
  if (!e) return <p>no entry {route.id}</p>;
  const n = Number(route.q.get("n") ?? 8);
  const ts = Array.from({ length: n }, (_, i) => (e.dur * i) / (n - 1));
  const fields: FieldName[] = e.both ? [e.field === "paper" || e.field === "yellow" ? e.field : "paper", e.field === "paper" || e.field === "yellow" ? "navy" : e.field] : [e.field];
  const w = 150;
  return (
    <div>
      <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>{e.title}</h2>
      <p style={{ margin: "0 0 12px", color: "#9AA0C0", fontSize: 13 }}>{e.note}</p>
      {fields.map((f) => (
        <Row key={f} label={`ours · ${f}`}>
          {ts.map((t) => <div key={t}><Fit width={w}>{e.render(t, f)}</Fit><Cap>{t.toFixed(2)} s</Cap></div>)}
        </Row>
      ))}
      {frames && e.ref && (
        <Row label="reference">
          {ts.map((_, i) => {
            const k = Math.round((i / (n - 1)) * (frames.count - 1));
            return <div key={i}><img src={refSrc(e.ref!, k)} width={w} height={(w * 16) / 9} style={{ display: "block" }} alt="" />
              <Cap>{frames.times[k]?.toFixed(2)} s</Cap></div>;
          })}
        </Row>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, color: "#FDD13E", marginBottom: 4 }}>{label}</div>
      <div style={{ display: "flex", gap: 6 }}>{children}</div>
    </div>
  );
}
const Cap = ({ children }: { children: ReactNode }) =>
  <div style={{ fontSize: 11, color: "#9AA0C0", textAlign: "center", marginTop: 2 }}>{children}</div>;

/** Anton vs Archivo Black on the three places display type is used: the
 * hook, a chapter number, and a takeaway. */
function Fonts() {
  const samples = (font: DisplayFont) => {
    const vars = { ["--motion-display" as string]: DISPLAY_FONTS[font] } as React.CSSProperties;
    return (
      <div style={vars}>
        <h2 style={{ fontSize: 20, margin: "0 0 8px" }}>{font === "anton" ? "Anton" : "Archivo Black"}</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <Fit width={230}><Frame field="navy"><KineticTitle field="navy" t={9} x={54} y={520} size={font === "anton" ? 190 : 150}
            lines={[[{ text: "How" }, { text: "does" }], [{ text: "AI", accent: true }, { text: "read" }], [{ text: "your" }, { text: "text?" }]]} /></Frame></Fit>
          <Fit width={230}><Frame field="paper"><ChapterCard n={2} of={4} title="Check the word shelf" field="paper" t={1.8} exitAt={99} /></Frame></Fit>
          <Fit width={230}><Frame field="blue"><KineticTitle field="blue" t={9} x={54} y={560} size={font === "anton" ? 140 : 108}
            lines={[[{ text: "Count" }, { text: "tokens" }], [{ text: "with" }, { text: "your" }], [{ text: "model's" }, { text: "own" }], [{ text: "tokenizer.", accent: true }]]} />
            <BigCounter value="1,20,000" x={W / 2} y={1500} size={150} field="blue" framed /></Frame></Fit>
        </div>
      </div>
    );
  };
  return (
    <div>
      <h1 style={{ fontSize: 24, marginTop: 0 }}>Display font: Anton vs Archivo Black</h1>
      <p style={{ color: "#9AA0C0", fontSize: 14, maxWidth: 900 }}>
        Same frames, only the display face changes. Both are OFL and bundled locally. Body is Manrope, mono is JetBrains Mono in both.
      </p>
      <div style={{ display: "flex", gap: 40, flexWrap: "wrap" }}>{samples("anton")}{samples("archivo")}</div>
    </div>
  );
}

