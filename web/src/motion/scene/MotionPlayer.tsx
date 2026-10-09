// #motion-reel/<short_id> — play a motion reel in the browser (phase 3):
// the plan from /api/motion/<short_id>/plan and its narration from
// /api/motion/<short_id>/audio, or any plan URL with #motion-reel?src=<url>
// (the stub demo in web/public/motion-demo/ works with only Vite running).
//
// The audio element is the clock while playing; otherwise the scrubber is.
// The stage itself is a pure function of t (MotionStage), so a paused frame,
// a scrubbed frame and a captured frame at the same t are the same frame.
// window.__capture.seek(t) puts the page at t for the phase 4 renderer.

import { useEffect, useMemo, useRef, useState } from "react";
import { MotionStage, shotIndexAt } from "./MotionStage";
import type { MotionPlan } from "./types";

declare global {
  interface Window { __capture?: { seek: (t: number) => Promise<void>; duration: number } }
}

function parseRoute(): { id: string | null; src: string | null; t: number; bare: boolean } {
  const raw = location.hash.replace(/^#/, "");
  const [path, query = ""] = raw.split("?");
  const q = new URLSearchParams(query);
  const id = path.split("/")[1] || null;
  return { id: id ? decodeURIComponent(id) : null, src: q.get("src"), t: Number(q.get("t") ?? 0) || 0,
           bare: q.get("bare") === "1" };
}

export function MotionPlayer() {
  const route = useMemo(parseRoute, []);
  const [plan, setPlan] = useState<MotionPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = route.src ?? (route.id ? `/api/motion/${encodeURIComponent(route.id)}/plan` : null);
    if (!url) { setError("Open #motion-reel/<short_id>, or #motion-reel?src=<plan url>."); return; }
    loadPlan(url).then(setPlan).catch((e) => setError(`Could not load the plan from ${url}: ${e.message}`));
  }, [route]);

  if (error) return <div style={{ padding: 32, color: "#E9EBF7", background: "#0E1224", minHeight: "100vh" }}>{error}</div>;
  if (!plan) return <div style={{ padding: 32, color: "#E9EBF7", background: "#0E1224", minHeight: "100vh" }}>Loading…</div>;
  return (
    <div style={{ minHeight: "100vh", background: "#0E1224", color: "#E9EBF7", fontFamily: "'Manrope Variable', system-ui, sans-serif",
                  padding: route.bare ? 0 : 28, boxSizing: "border-box" }}>
      <PlanPlayer plan={plan} initialT={route.t} bare={route.bare} />
    </div>
  );
}

/** Fetch a plan; a relative audio path is resolved against the plan's URL. */
export async function loadPlan(url: string): Promise<MotionPlan> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  const p = (await r.json()) as MotionPlan;
  if (p.audio && !p.audio_url && !url.startsWith("/api/")) p.audio_url = new URL(p.audio, new URL(url, location.href)).toString();
  return p;
}

/** A plan on the stage with its controls: play / pause (the audio is the
 * clock while it plays), a scrubber, a button per shot, and the captions of
 * the shot on screen with their timing source. `bare` draws the frame alone
 * at full size (screenshots, capture). */
export function PlanPlayer({ plan, initialT = 0, bare = false, width = 420 }: {
  plan: MotionPlan; initialT?: number; bare?: boolean; width?: number;
}) {
  const [t, setT] = useState(initialT);
  const [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const raf = useRef<number | null>(null);
  const started = useRef<{ wall: number; t: number } | null>(null);

  useEffect(() => {
    window.__capture = {
      duration: plan.duration,
      seek: (to: number) => new Promise((done) => { setT(to); requestAnimationFrame(() => requestAnimationFrame(() => done())); }),
    };
  }, [plan]);

  useEffect(() => {
    if (!playing) return;
    const tick = () => {
      const a = audio.current;
      let now: number;
      if (a && plan.audio_url && !a.paused) now = a.currentTime;
      else {
        if (!started.current) started.current = { wall: performance.now(), t };
        now = started.current.t + (performance.now() - started.current.wall) / 1000;
      }
      if (now >= plan.duration) { setT(plan.duration); setPlaying(false); return; }
      setT(now);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); started.current = null; };
  }, [playing, plan]); // eslint-disable-line react-hooks/exhaustive-deps

  if (bare) return <MotionStage plan={plan} t={t} width={1080} />;

  const toggle = () => {
    const a = audio.current;
    if (playing) { a?.pause(); setPlaying(false); return; }
    const from = t >= plan.duration - 0.05 ? 0 : t;
    setT(from);
    if (a && plan.audio_url) { a.currentTime = from; a.play().catch(() => undefined); }
    setPlaying(true);
  };
  const seek = (to: number) => {
    setT(to);
    if (audio.current) audio.current.currentTime = to;
    started.current = null;
  };
  const i = shotIndexAt(plan, t);
  const shot = plan.shots[i];
  return (
    <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "flex-start" }}>
      <div style={{ borderRadius: 18, overflow: "hidden", boxShadow: "0 20px 60px rgba(0,0,0,0.45)" }}>
        <MotionStage plan={plan} t={t} width={Math.min(width, window.innerWidth - 56)} />
      </div>
      <div style={{ flex: "1 1 320px", maxWidth: 560 }}>
        <div style={{ color: "#9AA0C0", fontSize: 14, marginBottom: 14 }}>
          {plan.template}{plan.theme ? ` · ${plan.theme}` : ""} · {plan.duration.toFixed(1)}s ·
          caption timing: {plan.timing_source}{plan.audio_url ? "" : " · no audio"}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 10 }}>
          <button onClick={toggle} style={{ padding: "10px 22px", borderRadius: 999, border: 0, fontWeight: 800,
                                            background: "#FDD13E", color: "#151936", cursor: "pointer" }}>
            {playing ? "Pause" : "Play"}
          </button>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{t.toFixed(2)}s / {plan.duration.toFixed(2)}s</span>
        </div>
        <input type="range" min={0} max={plan.duration} step={1 / 30} value={t} aria-label="Scrub the reel"
               onChange={(e) => seek(Number(e.target.value))} style={{ width: "100%" }} />
        <div style={{ display: "flex", gap: 4, margin: "6px 0 18px" }}>
          {plan.shots.map((s, k) => (
            <button key={s.id} title={`${s.id} ${s.beat}`} onClick={() => seek(s.start)}
                    style={{ flex: s.end - s.start, height: 22, border: 0, borderRadius: 4, cursor: "pointer",
                             background: k === i ? "#FDD13E" : "#2A3052", color: k === i ? "#151936" : "#9AA0C0",
                             fontSize: 10, overflow: "hidden" }}>{s.beat}</button>
          ))}
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.6 }}>
          <div><b>{shot.id}</b> {shot.beat} · {shot.field} · in: {shot.transition}{shot.label ? ` · ${shot.label}` : ""}</div>
          {shot.captions.map((c, k) => (
            <div key={k} style={{ color: t >= c.start && t <= c.end ? "#FDD13E" : "#C9CCF0" }}>
              {c.speaker ? <b>{c.speaker}: </b> : null}{c.text.replace(/<\/?b>/g, "")}
              <span style={{ color: "#6A6F8E" }}> ({c.source})</span>
            </div>
          ))}
        </div>
        {plan.audio_url && <audio ref={audio} src={plan.audio_url} preload="auto" onEnded={() => setPlaying(false)} />}
      </div>
    </div>
  );
}
