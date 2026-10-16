// #videos — every long-form VIDEO (plan.format = "video"), newest first, as a
// grid of cards: a still of the video, its question, length and chapters.
// A card opens the video in its player (#motion-video/<short_id>). Reels are
// not here: they play in the vertical feed.
//
// A card's still is the video's own frame a few seconds in, drawn without
// the 3D presenter (one WebGL canvas per card would be far too heavy).

import { useEffect, useRef, useState } from "react";
import type { MotionSummary } from "../../MotionFeedItem";
import type { MotionPlan } from "../scene/types";
import { loadPlan } from "../scene/MotionPlayer";
import { VideoStage } from "./VideoFrame";

const fmt = (x: number) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;

/** The width an element is drawn at, kept up to date. */
function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function Card({ m }: { m: MotionSummary }) {
  const [plan, setPlan] = useState<MotionPlan | null>(null);
  const [box, width] = useWidth<HTMLDivElement>();
  useEffect(() => {
    loadPlan(`/api/motion/${encodeURIComponent(m.short_id)}/plan`)
      .then((p) => setPlan({ ...p, characters: [] })).catch(() => {});
  }, [m.short_id]);
  const chapters = plan ? plan.shots.filter((s) => s.objects.some((o) => o.kind === "chapter_card")).length : 0;
  // a still from the first shot after the hook's opening second
  const still = plan ? Math.min(plan.duration, (plan.shots[1]?.start ?? 2) - 0.6) : 0;
  return (
    <a className="vcard" href={`#motion-video/${m.short_id}`} data-video={m.short_id}
       onClick={(e) => { e.preventDefault(); location.hash = `#motion-video/${m.short_id}`; location.reload(); }}>
      <div className="vthumb" ref={box}>
        {plan && width > 0 ? <VideoStage plan={plan} t={still} width={width} /> : <div className="vthumb-empty" />}
        {m.duration != null && <span className="vlen">{fmt(m.duration)}</span>}
      </div>
      <div className="vtitle">{m.topic || m.short_id}</div>
      <div className="vmeta">
        {chapters > 0 && `${chapters} chapters · `}{m.stub ? "test (stub) video" : m.silent ? "no voice" : "voiced"}
        {m.cost ? ` · $${m.cost.toFixed(2)}` : ""}
      </div>
    </a>
  );
}

export function VideoLibrary() {
  const [videos, setVideos] = useState<MotionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/motion").then((r) => (r.ok ? r.json() : Promise.reject(new Error(`the server answered ${r.status}`))))
      .then((d) => setVideos(((d.reels ?? []) as MotionSummary[])
        .filter((m) => m.format === "video" && m.has_plan)
        .sort((a, b) => (b.created ?? 0) - (a.created ?? 0))))
      .catch((e) => setError((e as Error).message));
  }, []);
  return (
    <div className="shell vlibrary">
      <header className="topbar">
        <div className="brand"><span className="spark">▶</span> Learning Shorts</div>
        <span className="spacer" />
        <button className="ghost sm" onClick={() => { location.hash = ""; location.reload(); }}>Make a reel or video</button>
        <button className="ghost sm" onClick={() => { location.hash = "#reels"; location.reload(); }}>Reels</button>
      </header>
      <div className="panel wide">
        <h1>Videos</h1>
        <p className="lede">Long-form lessons, 16:9 — one topic in depth, chapter by chapter.</p>
        {error && <div className="error">{error}</div>}
        {videos && videos.length === 0 && (
          <div className="outcome">No videos yet. Upload your material and choose <b>Video</b> to make one.</div>
        )}
        {!videos && !error && <div className="hintline">Loading…</div>}
        <div className="vgrid">{videos?.map((m) => <Card key={m.short_id} m={m} />)}</div>
      </div>
    </div>
  );
}
