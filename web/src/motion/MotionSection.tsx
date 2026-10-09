// #motion — the Motion section of the web UI (RESTYLE_TO_MOTION_REELS.md,
// phase 3 review). Separate from the explainer workspace, which it does not
// touch:
//
//   #motion                 every motion reel: the ones in output/ (stub and
//                           real, from /api/motion — needs the API server) and
//                           the stub demos in web/public/motion-demo/ (Vite only)
//   #motion/reel/<id>       one reel from output/
//   #motion/demo/<name>     one stub demo
//
// A reel page shows its player, theme (and why), teaching approach, tags, the
// script with speaker labels, the fact sources and the cost of every LLM call.
// The phase 2 gallery and the language identities (#motion/identities) are
// one click away. Read-only: nothing
// here runs or changes a reel.

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { PlanPlayer, loadPlan } from "./scene/MotionPlayer";
import { IdentitySheet } from "./identity/IdentitySheet";
import { CharacterSheet } from "./cast/CharacterSheet";
import { CharacterDesigner } from "./cast/CharacterDesigner";
import type { MotionPlan } from "./scene/types";

interface Summary {
  short_id: string; topic: string; stub: boolean; theme: string | null; template: string | null;
  teaching_approach: string | null; tags: string[]; language: string | null; duration: number | null;
  cost: number; cost_estimated?: boolean; stage: string; has_plan: boolean; demo?: string; bundle_url?: string;
}
interface CostCall { label: string; model: string; input_tokens: number; output_tokens: number; cost: number; estimated: boolean }
interface Bundle extends Summary {
  approach: { primary: string; combined_with?: string[]; alternatives?: string[]; rationale?: string } | null;
  theme_choice: {
    theme: string; reason: string; source: string; template: string; language: string; tags: string[]; eligible: string[];
    fit_check: { passed: boolean; attempts: number; fallback: boolean; fallback_reason: string; overrides: string[];
                 rejected: { theme: string; attempt: number; problems: string[] }[] };
  } | null;
  script: {
    concept_name: string; promise: string; hook_question: string; speakers: { role: string; label: string; identity: string; voice_slot: string }[];
    shots: { id: string; beat: string; chapter: number | null; speech: string; visual: string; code: string[];
             captions: { text: string; speaker: string | null }[]; scene: { field: string; transition: string } | null }[];
  } | null;
  facts: { kind: string; value: string; section: string; role: string; shots: string[] }[];
  cost_log: { runs: { started: string; ended: string; stub: boolean; calls: CostCall[]; cost: number }[];
              total: { calls: number; cost: number; estimated: boolean; by_label: Record<string, { calls: number; cost: number; model: string }> } } | null;
  plan_url: string | null; audio_url: string | null;
}

const page: CSSProperties = {
  minHeight: "100vh", background: "#0E1224", color: "#E9EBF7", fontFamily: "'Manrope Variable', system-ui, sans-serif",
  padding: "24px 28px 80px", boxSizing: "border-box",
};
const card: CSSProperties = { background: "#151A33", borderRadius: 14, padding: "14px 18px", marginBottom: 18 };
const muted = "#9AA0C0";
const link: CSSProperties = { color: "#FDD13E", textDecoration: "none", fontWeight: 700 };

function route(): { view: "list" | "reel" | "demo" | "identities" | "characters" | "designer"; id?: string } {
  const parts = location.hash.replace(/^#/, "").split("?")[0].split("/");
  if (parts[1] === "identities") return { view: "identities" };
  if (parts[1] === "characters" && parts[2] === "designer") return { view: "designer" };
  if (parts[1] === "characters") return { view: "characters" };
  if (parts[1] === "reel" && parts[2]) return { view: "reel", id: decodeURIComponent(parts[2]) };
  if (parts[1] === "demo" && parts[2]) return { view: "demo", id: decodeURIComponent(parts[2]) };
  return { view: "list" };
}

/** A link to another top-level screen of the app. App picks its screen once
 * per page load (the explainer workspace is unchanged by the Motion section),
 * so crossing screens reloads the page at the new hash. */
export function ScreenLink({ to, children, style }: { to: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <a href={to} style={{ ...link, ...style }}
       onClick={(e) => { e.preventDefault(); location.hash = to; location.reload(); }}>{children}</a>
  );
}

function Nav() {
  return (
    <nav style={{ display: "flex", gap: 22, alignItems: "baseline", flexWrap: "wrap", marginBottom: 22 }}>
      <a href="#motion" style={{ ...link, fontSize: 24, color: "#E9EBF7" }}>Motion</a>
      <a href="#motion" style={link}>All motion reels</a>
      <ScreenLink to="#motion-gallery">Scene library (gallery)</ScreenLink>
      <a href="#motion/identities" style={link}>Language identities</a>
      <a href="#motion/characters" style={link}>Characters</a>
      <a href="#motion/characters/designer" style={link}>Character designer</a>
      <ScreenLink to="#" style={{ color: muted, marginLeft: "auto" }}>Explainer workspace</ScreenLink>
    </nav>
  );
}

function Badge({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "stub" | "real" }) {
  const bg = tone === "stub" ? "#2A3052" : tone === "real" ? "#17B27B" : "#232A4D";
  return <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 999, background: bg, fontSize: 12,
                        fontWeight: 800, color: tone === "real" ? "#0E1224" : "#E9EBF7", whiteSpace: "nowrap" }}>{children}</span>;
}

const money = (n: number | null | undefined) => `$${(n ?? 0).toFixed(4)}`;

function ReelTable({ rows, hrefOf }: { rows: Summary[]; hrefOf: (r: Summary) => string }) {
  if (!rows.length) return <div style={{ color: muted }}>None.</div>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
      <thead><tr style={{ color: muted, textAlign: "left" }}>
        {["Reel", "", "Theme", "Teaching approach", "Tags", "Length", "Reached", "Cost"].map((h) => <th key={h} style={{ padding: "6px 8px" }}>{h}</th>)}
      </tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.short_id + (r.demo ?? "")} style={{ borderTop: "1px solid #2A3052" }}>
            <td style={{ padding: "8px" }}>
              <a href={hrefOf(r)} style={link}>{r.topic || r.short_id}</a>
              <div style={{ color: muted, fontSize: 12 }}>{r.short_id}</div>
            </td>
            <td><Badge tone={r.stub ? "stub" : "real"}>{r.stub ? "stub" : "real"}</Badge></td>
            <td>{r.theme ?? "—"}<div style={{ color: muted, fontSize: 12 }}>{r.template ?? ""}</div></td>
            <td>{r.teaching_approach ?? "—"}</td>
            <td style={{ fontSize: 12, color: "#C9CCF0" }}>{r.tags.join(" ")}</td>
            <td>{r.duration ? `${r.duration.toFixed(1)}s` : "—"}</td>
            <td>{r.stage}</td>
            <td>{money(r.cost)}{r.cost_estimated ? "*" : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ListView() {
  const [real, setReal] = useState<Summary[] | null>(null);
  const [realError, setRealError] = useState<string | null>(null);
  const [demos, setDemos] = useState<Summary[]>([]);
  useEffect(() => {
    fetch("/api/motion").then(async (r) => {
      if (r.ok) { setReal((await r.json()).reels); return; }
      // Tell "no server" apart from "a server running older code": a server
      // started before the Motion endpoints existed answers /api/health but
      // 404s /api/motion (Python does not pick up new code until restarted).
      const health = await fetch("/api/health").then((h) => h.ok).catch(() => false);
      setRealError(health
        ? `The API server is running but has no /api/motion (HTTP ${r.status}) — it was started before the Motion section existed. Restart it: stop it, then run \`python -m shorts.server\` again.`
        : "The API server is not reachable, so reels in output/ can't be listed. Start it with `python -m shorts.server` (it must be on 127.0.0.1:8000, where the dev server proxies /api).");
    }).catch(() => setRealError("The API server is not reachable, so reels in output/ can't be listed. Start it with `python -m shorts.server` (it must be on 127.0.0.1:8000, where the dev server proxies /api)."));
    fetch("/motion-demo/index.json").then((r) => r.json()).then((d) => setDemos(d.reels)).catch(() => setDemos([]));
  }, []);
  return (
    <>
      <div style={card}>
        <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Reels in output/</h2>
        <p style={{ margin: "0 0 12px", color: muted, fontSize: 13 }}>
          Every motion reel a run has written — real ones (from <code>python -m shorts.motion_reel</code>) and any stub
          runs. * = a cost estimated from the price table (OpenRouter sent no billed cost).
        </p>
        {realError ? <div style={{ color: "#FFB524" }}>{realError}</div>
          : real === null ? <div style={{ color: muted }}>Loading…</div>
          : <ReelTable rows={real} hrefOf={(r) => `#motion/reel/${encodeURIComponent(r.short_id)}`} />}
      </div>
      <div style={card}>
        <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>Stub demos</h2>
        <p style={{ margin: "0 0 12px", color: muted, fontSize: 13 }}>
          Three stub reels made at $0 by <code>SHORTS_STUB=1 python -m shorts.motion_demo</code> (golden scripts, default
          scenes, silent audio, even timing) and kept in web/public/motion-demo/.
        </p>
        <ReelTable rows={demos} hrefOf={(r) => `#motion/demo/${encodeURIComponent(r.demo ?? "")}`} />
      </div>
    </>
  );
}

function Section({ title, children, note }: { title: string; children: ReactNode; note?: string }) {
  return (
    <div style={card}>
      <h2 style={{ margin: "0 0 2px", fontSize: 17 }}>{title}</h2>
      {note && <p style={{ margin: "0 0 10px", color: muted, fontSize: 13 }}>{note}</p>}
      {children}
    </div>
  );
}

const plain = (s: string) => s.replace(/<\/?b>/g, "");
function Highlighted({ text }: { text: string }) {
  return <>{text.split(/(<b>.*?<\/b>)/).map((p, i) => p.startsWith("<b>")
    ? <b key={i} style={{ color: "#FDD13E" }}>{plain(p)}</b> : <span key={i}>{p}</span>)}</>;
}

function DetailView({ source, id }: { source: "reel" | "demo"; id: string }) {
  const [b, setB] = useState<Bundle | null>(null);
  const [plan, setPlan] = useState<MotionPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const url = source === "reel" ? `/api/motion/${encodeURIComponent(id)}/bundle` : `/motion-demo/${encodeURIComponent(id)}.bundle.json`;
    fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${r.statusText}`))))
      .then(async (bundle: Bundle) => {
        setB(bundle);
        if (bundle.plan_url) {
          const p = await loadPlan(bundle.plan_url);
          if (bundle.audio_url) p.audio_url = bundle.audio_url;
          setPlan(p);
        }
      }).catch((e) => setError(`Could not load ${url}: ${e.message}`));
  }, [source, id]);
  if (error) return <div style={{ color: "#FFB524" }}>{error}</div>;
  if (!b) return <div style={{ color: muted }}>Loading…</div>;
  const tc = b.theme_choice;
  const cost = b.cost_log;
  return (
    <>
      <div style={{ marginBottom: 18 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 22 }}>{b.topic || b.short_id}</h1>
          <Badge tone={b.stub ? "stub" : "real"}>{b.stub ? "stub" : "real"}</Badge>
          <Badge>reached: {b.stage}</Badge>
        </div>
        <div style={{ color: muted, fontSize: 13, marginTop: 4 }}>{b.short_id} · {b.template} · {b.language ?? ""}</div>
      </div>

      <Section title="Player" note={plan ? "Play, scrub, or jump to a shot. Captions light word by word from the timing; the source is shown per caption." : undefined}>
        {plan ? <PlanPlayer plan={plan} initialT={Math.min(2, plan.duration)} /> : <div style={{ color: muted }}>No playable plan yet — this reel stopped at "{b.stage}". The plan is written by the timing stage.</div>}
      </Section>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 18 }}>
        <Section title="Theme">
          {tc ? <>
            <div><b>{tc.theme}</b> <span style={{ color: muted }}>({tc.source}, template {tc.template})</span></div>
            <p style={{ margin: "6px 0" }}>{tc.reason}</p>
            <div style={{ fontSize: 13, color: muted }}>Fit check: {tc.fit_check.passed ? "passed" : "FAILED"}
              {tc.fit_check.attempts ? ` after ${tc.fit_check.attempts} pick(s)` : ""}
              {tc.fit_check.fallback ? ` — fallback: ${tc.fit_check.fallback_reason}` : ""}</div>
            {tc.fit_check.rejected.map((r, i) => <div key={i} style={{ fontSize: 13, color: "#FFB524" }}>rejected {r.theme}: {r.problems.join("; ")}</div>)}
            {tc.fit_check.overrides.map((o, i) => <div key={i} style={{ fontSize: 13, color: "#FFB524" }}>override: {o}</div>)}
            <div style={{ fontSize: 13, color: muted, marginTop: 6 }}>Eligible: {tc.eligible.join(", ")}</div>
          </> : <div style={{ color: muted }}>No theme chosen yet.</div>}
        </Section>
        <Section title="Teaching approach">
          {b.approach ? <>
            <div><b>{b.approach.primary}</b>{b.approach.combined_with?.length ? <span style={{ color: muted }}> with {b.approach.combined_with.join(", ")}</span> : null}</div>
            {b.approach.rationale && <p style={{ margin: "6px 0" }}>{b.approach.rationale}</p>}
            {b.approach.alternatives?.length ? <div style={{ fontSize: 13, color: muted }}>Considered: {b.approach.alternatives.join(", ")}</div> : null}
          </> : <div style={{ color: muted }}>None recorded.</div>}
        </Section>
        <Section title="Tags">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{b.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div>
        </Section>
      </div>

      <Section title="Script" note={b.script?.speakers?.length
        ? `Two speakers: ${b.script.speakers.map((s) => `${s.label} (${s.identity} badge, voice ${s.voice_slot})`).join(" · ")}`
        : "One narrator."}>
        {b.script ? <>
          <div style={{ marginBottom: 10, fontSize: 14 }}>
            <b>{b.script.concept_name}</b> — {b.script.promise} <span style={{ color: muted }}>· hook question: {b.script.hook_question}</span>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <tbody>
              {b.script.shots.map((s) => (
                <tr key={s.id} style={{ borderTop: "1px solid #2A3052", verticalAlign: "top" }}>
                  <td style={{ padding: "8px 8px 8px 0", whiteSpace: "nowrap", color: muted }}>
                    {s.id} <b style={{ color: "#E9EBF7" }}>{s.beat}</b>{s.chapter ? ` ch${s.chapter}` : ""}
                    {s.scene && <div style={{ fontSize: 12 }}>{s.scene.field} · {s.scene.transition}</div>}
                  </td>
                  <td style={{ padding: 8 }}>
                    {s.captions.map((c, i) => (
                      <div key={i}>{c.speaker ? <b style={{ color: "#B9A8FF" }}>{c.speaker}: </b> : null}<Highlighted text={c.text} /></div>
                    ))}
                    {s.code.length > 0 && <pre style={{ margin: "6px 0 0", background: "#0B0F22", padding: "6px 10px", borderRadius: 8, fontSize: 13 }}>{s.code.join("\n")}</pre>}
                    <div style={{ color: muted, fontSize: 12, marginTop: 4 }}>visual: {s.visual}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </> : <div style={{ color: muted }}>No script yet.</div>}
      </Section>

      <Section title="Fact sources" note="Every number and long term the narration says, with the section it came from.">
        {b.facts.length ? (
          <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
            <thead><tr style={{ color: muted, textAlign: "left" }}>{["kind", "value", "section", "role", "shots"].map((h) => <th key={h} style={{ padding: "4px 12px 4px 0" }}>{h}</th>)}</tr></thead>
            <tbody>{b.facts.map((f, i) => (
              <tr key={i}><td style={{ paddingRight: 12 }}>{f.kind}</td><td style={{ paddingRight: 12 }}><b>{f.value}</b></td>
                <td style={{ paddingRight: 12, color: f.section === "NOT IN SOURCE" ? "#F2555A" : undefined }}>{f.section}</td>
                <td style={{ paddingRight: 12 }}>{f.role}</td><td>{f.shots.join(", ")}</td></tr>))}</tbody>
          </table>
        ) : <div style={{ color: muted }}>None (or not written yet).</div>}
      </Section>

      <Section title="Cost" note="Every LLM call this reel made, across every run (output/<id>/cost.json). Voice and timing are local and free.">
        {cost ? <>
          <div style={{ fontSize: 15, marginBottom: 8 }}>Total: <b>{money(cost.total.cost)}</b> over {cost.total.calls} call(s)
            {cost.total.estimated ? <span style={{ color: muted }}> — includes estimated prices</span> : null}</div>
          <table style={{ borderCollapse: "collapse", fontSize: 14, marginBottom: 10 }}>
            <thead><tr style={{ color: muted, textAlign: "left" }}>{["step", "model", "calls", "cost"].map((h) => <th key={h} style={{ padding: "4px 14px 4px 0" }}>{h}</th>)}</tr></thead>
            <tbody>{Object.entries(cost.total.by_label).map(([label, r]) => (
              <tr key={label}><td style={{ paddingRight: 14 }}>{label}</td><td style={{ paddingRight: 14 }}>{r.model}</td>
                <td style={{ paddingRight: 14 }}>{r.calls}</td><td>{money(r.cost)}</td></tr>))}</tbody>
          </table>
          {cost.runs.map((run, i) => (
            <details key={i} style={{ fontSize: 13, color: "#C9CCF0" }}>
              <summary>Run {i + 1}: {run.started}{run.stub ? " (stub)" : ""} — {run.calls.length} call(s), {money(run.cost)}</summary>
              {run.calls.map((c, k) => <div key={k}>{c.label} · {c.model} · {c.input_tokens} in / {c.output_tokens} out · {money(c.cost)}{c.estimated ? " (estimated)" : ""}</div>)}
            </details>
          ))}
        </> : <div style={{ color: muted }}>No cost log (made before cost logging existed).</div>}
      </Section>
    </>
  );
}

export function MotionSection() {
  const [r, setR] = useState(route);
  useEffect(() => {
    const on = () => setR(route());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return (
    <div style={page}>
      <Nav />
      {r.view === "list" ? <ListView />
        : r.view === "identities" ? <IdentitySheet />
        : r.view === "characters" ? <CharacterSheet />
        : r.view === "designer" ? <CharacterDesigner />
        : <DetailView key={r.view + r.id} source={r.view} id={r.id!} />}
    </div>
  );
}
