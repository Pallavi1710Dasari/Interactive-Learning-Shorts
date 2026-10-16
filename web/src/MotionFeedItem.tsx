import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Avatar } from "./Avatars";
import { CommentIcon, DownloadIcon, RedrawIcon, ReplayIcon, SpinnerIcon, VolumeIcon } from "./RailIcons";
import { money, tokens as tokenText } from "./CostPill";
import { MotionStage, shotIndexAt, speakerAt } from "./motion/scene/MotionStage";
import type { MotionPlan } from "./motion/scene/types";
import type { Feedback } from "./types";

/** A motion reel's row in /api/motion (shorts/motion_bundle.summary). */
export interface MotionSummary {
  short_id: string; topic: string; stub: boolean; silent?: boolean; theme: string | null; template: string | null;
  duration: number | null; stage: string; has_plan: boolean; created?: number;
  /** "video": a long-form landscape video (listed on #videos, not in the feed) */
  format?: "reel" | "video";
  cost?: number; cost_estimated?: boolean; tokens?: number;
}

/**
 * A MOTION reel in the reels feed, drawn and played the way the explainer
 * reels are (Reel.tsx): the same 9:16 card, it plays by itself when it is
 * the reel on screen, a click pauses, the big round button resumes or
 * replays, and the same rail of actions sits down the right. The picture is
 * the motion player's frame (MotionStage), filling the card. A stub reel says
 * plainly, on the card, that it has no voice.
 */
export function MotionReel({ reel, active, near, voiceOn, rate, onFeedback, onDownload, downloading, downloadPct }: {
  reel: MotionSummary; active: boolean; near: boolean; voiceOn: boolean; rate: number;
  onFeedback: (f: Feedback) => void;
  /** Save this reel as an MP4 (the feed's own render-and-poll download). */
  onDownload?: () => void; downloading?: boolean; downloadPct?: number;
}) {
  const [plan, setPlan] = useState<MotionPlan | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [flagged, setFlagged] = useState(false);
  // redraw the visuals from a note (shorts/motion_redraw.py)
  const [redrawOpen, setRedrawOpen] = useState(false);
  const [note, setNote] = useState("");
  const [redraw, setRedraw] = useState<{ status: string; step?: string; error?: string | null; estimate: number; stub: boolean } | null>(null);
  useEffect(() => {
    if (!redrawOpen && redraw?.status !== "working") return;
    let stop = false;
    const poll = () => fetch(`/api/motion/${encodeURIComponent(reel.short_id)}/redraw`).then((r) => r.json()).then((d) => {
      if (stop) return;
      setRedraw(d);
      if (d.status === "working") setTimeout(poll, 1500);
      if (d.status === "done" && redraw?.status === "working") { setPlan(null); setRedrawOpen(false); setNote(""); }
    }).catch(() => {});
    poll();
    return () => { stop = true; };
  }, [redrawOpen, redraw?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const sendRedraw = () => {
    if (!note.trim()) return;
    fetch(`/api/motion/${encodeURIComponent(reel.short_id)}/redraw`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) })
      .then(async (r) => { const d = await r.json(); if (!r.ok) throw new Error(d.detail ?? r.status); setRedraw(d); })
      .catch((e) => setRedraw({ status: "error", error: String(e.message ?? e), estimate: 0, stub: false }));
  };
  const [width, setWidth] = useState(0);
  const frameBox = useRef<HTMLDivElement | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const clock = useRef<{ wall: number; t: number } | null>(null);

  useEffect(() => {
    if (!near || plan) return;
    fetch(`/api/motion/${encodeURIComponent(reel.short_id)}/plan`).then((r) => (r.ok ? r.json() : null))
      .then((p) => p && setPlan(p)).catch(() => {});
  }, [near, plan, reel.short_id]);

  // the frame fills its 9:16 box at whatever size the feed gives it
  useLayoutEffect(() => {
    const el = frameBox.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const recorded = plan?.voice === "recorded" && !!plan.audio_url;
  const finished = !!plan && t >= plan.duration - 0.05;

  const play = (from?: number) => {
    if (!plan) return;
    const start = from ?? (finished ? 0 : t);
    setT(start);
    clock.current = null;
    const a = audio.current;
    if (a && recorded) {
      a.currentTime = start;
      a.play().then(() => setBlocked(false)).catch(() => { setBlocked(true); setPlaying(false); });
    }
    setPlaying(true);
  };
  const pause = () => { audio.current?.pause(); setPlaying(false); };

  // plays by itself when it is the reel on screen, like the explainer reels
  useEffect(() => {
    if (active && plan) play(t >= plan.duration - 0.05 ? 0 : t);
    if (!active) {
      pause();
      if (plan && t > 0.5) onFeedback({ short_id: reel.short_id, event: "view",
                                        watched_pct: Math.round((100 * t) / plan.duration), dropped_at: +t.toFixed(1) });
    }
  }, [active, plan]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const a = audio.current;
    if (a) { a.muted = !voiceOn; a.playbackRate = rate; }
  }, [voiceOn, rate, plan]);

  useEffect(() => {
    if (!playing || !plan) return;
    let raf = 0;
    const tick = () => {
      const a = audio.current;
      let now: number;
      if (a && recorded && !a.paused) now = a.currentTime;
      else {
        if (!clock.current) clock.current = { wall: performance.now(), t };
        now = clock.current.t + ((performance.now() - clock.current.wall) / 1000) * rate;
      }
      if (now >= plan.duration) { setT(plan.duration); setPlaying(false); audio.current?.pause(); return; }
      setT(now);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); clock.current = null; };
  }, [playing, plan]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === " ") { e.preventDefault(); if (playing) pause(); else play(); }
      else if (e.key === "r") play(0);
      else if (e.key === "d") onDownload?.();
      else if (plan && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        e.preventDefault();
        const i = shotIndexAt(plan, t) + (e.key === "ArrowRight" ? 1 : -1);
        const shot = plan.shots[Math.max(0, Math.min(plan.shots.length - 1, i))];
        if (playing) play(shot.start); else setT(shot.start);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  const shot = plan ? plan.shots[shotIndexAt(plan, t)] : null;
  const speaker = shot ? speakerAt(shot, t) : null;
  const host = !!speaker && plan?.cast?.find((m) => m.role === speaker)?.identity?.id === "host";

  return (
    <div className={`reel mreel2${active ? " live" : ""}`} data-motion-reel={reel.short_id}>
      <div ref={frameBox} className="mframe" onClick={() => (playing ? pause() : play())}>
        {plan && width > 0 ? <MotionStage plan={plan} t={t} width={width} /> : <div className="mloading">{reel.topic}</div>}
      </div>
      {plan?.audio_url && <audio ref={audio} src={plan.audio_url} preload="auto" />}

      {reel.silent && <span className="stubtag" title="This test reel was made without recording a voice: it is silent on purpose, the sound is not broken">Test reel: no voice</span>}
      {blocked && <span className="stubtag warn">The browser blocked the sound. Tap ▶ to play with sound.</span>}

      <div className="rail">
        <div className="whocell" title={speaker ? `speaking: ${speaker.toLowerCase()}` : "narrating"}>
          <Avatar speaker={host ? "interviewer" : "narrator"} speaking={playing && !!speaker} size={34} />
        </div>
        <button className="railbtn"
                onClick={() => { onFeedback({ short_id: reel.short_id, event: "confusing", at: +t.toFixed(1) });
                                 setFlagged(true); setTimeout(() => setFlagged(false), 1600); }}
                title="mark this moment confusing (c)">
          <CommentIcon />
          <em>{flagged ? "noted" : "unclear"}</em>
        </button>
        <button className={`railbtn${downloading ? " busy" : ""}`} disabled={downloading || !onDownload}
                onClick={() => onDownload?.()} title="download this reel as an MP4 (d) — recorded on this computer, free">
          {downloading ? <SpinnerIcon /> : <DownloadIcon />}
          <em>{downloading ? (downloadPct ? `${downloadPct}%` : "start…") : "mp4"}</em>
        </button>
        <button className={`railbtn${redrawOpen ? " on" : ""}${redraw?.status === "working" ? " busy" : ""}`}
                onClick={() => setRedrawOpen((v) => !v)} title="redraw the visuals from a note (the words and the voice stay)">
          {redraw?.status === "working" ? <SpinnerIcon /> : <RedrawIcon />}
          <em>{redraw?.status === "working" ? "drawing…" : "redraw"}</em>
        </button>
        <button className="railbtn" onClick={() => play(0)} title="replay (r)">
          <ReplayIcon />
          <em>replay</em>
        </button>
        <div className="railstate" title={reel.silent ? "test reel: no voice" : recorded ? "recorded narration" : "no voice"}>
          <VolumeIcon level={!voiceOn ? "off" : reel.silent || !recorded ? "warn" : playing ? "on" : "idle"} />
          <em>{!voiceOn ? "muted" : reel.silent ? "silent" : recorded ? "hd" : "none"}</em>
        </div>
        <div className="railstate cost" title={reel.cost != null ? `what this reel cost to make${reel.cost_estimated ? " (estimated)" : ""}` : "not recorded"}>
          <b>{reel.cost != null ? money(reel.cost, reel.cost_estimated) : "—"}</b>
          <em>{reel.tokens ? tokenText(reel.tokens) : "tokens"}</em>
        </div>
      </div>

      {redrawOpen && (
        <div className="redrawbox" onClick={(e) => e.stopPropagation()}>
          <b>What should the visuals show instead?</b>
          <textarea autoFocus value={note} rows={3} disabled={redraw?.status === "working"}
                    placeholder={'e.g. "show the cart number going up when the button is tapped"'}
                    onChange={(e) => setNote(e.target.value)}
                    onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) sendRedraw(); if (e.key === "Escape") setRedrawOpen(false); }} />
          {redraw?.status === "working" && <span className="hintline">{redraw.step}… the words and the voice stay the same.</span>}
          {redraw?.status === "error" && <span className="error sm">{redraw.error}</span>}
          <div className="redrawfoot">
            <span className="hintline">{redraw ? (redraw.stub ? "free in test mode" : `costs up to $${redraw.estimate.toFixed(2)}`) : ""}</span>
            <span className="spacer" />
            <button className="ghost sm" onClick={() => setRedrawOpen(false)}>cancel</button>
            <button className="primary sm" disabled={!note.trim() || redraw?.status === "working"} onClick={sendRedraw}>
              {redraw?.status === "working" ? "redrawing…" : "Redraw"}
            </button>
          </div>
        </div>
      )}

      {!playing && active && plan && (
        <button className="tap" onClick={() => play()}>
          <span>{finished ? "↻" : "▶"}</span>
        </button>
      )}
    </div>
  );
}
