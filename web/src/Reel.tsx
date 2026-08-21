import { useEffect, useMemo, useState } from "react";
import { InterviewScene } from "./InterviewScene";
import type { Feedback, Unit } from "./types";
import { useNarration } from "./useNarration";

/**
 * One short, playing, with voice and characters.
 *
 * No question/answer text panel here by design — reviewing happens in step 2. A
 * learner watching a reel should see what a learner sees.
 */
export function Reel({
  unit, active, voiceOn, rate, onFeedback,
}: {
  unit: Unit;
  active: boolean;
  voiceOn: boolean;
  rate: number;
  onFeedback: (f: Feedback) => void;
}) {
  const n = useNarration(unit.beats, unit.seconds,
                         { enabled: voiceOn, rate, active, audioUrl: unit.audio_url });
  const beat = unit.beats[n.beat];
  const finished = !n.playing && n.beat === unit.beats.length - 1 && n.progress > 0.5;
  const [liked, setLiked] = useState(false);
  const [flagged, setFlagged] = useState<number | null>(null);

  // A stable per-short hue so the feed does not look like one long identical page.
  const hue = useMemo(() => {
    let h = 0;
    for (const c of unit.short_id) h = (h * 31 + c.charCodeAt(0)) % 360;
    return h;
  }, [unit.short_id]);

  useEffect(() => {
    if (active || n.progress <= 0.05) return;
    onFeedback({
      short_id: unit.short_id, event: "view",
      watched_pct: Math.round(n.progress * 100),
      dropped_at: +(n.progress * unit.seconds).toFixed(1),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === " ") { e.preventDefault(); n.toggle(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); n.goToBeat(n.beat + 1); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); n.goToBeat(n.beat - 1); }
      else if (e.key === "r") n.replay();
      else if (e.key === "l") setLiked((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, n]);

  const isAsking = beat.speaker === "interviewer";

  return (
    <div className={`reel${active ? " live" : ""}`} style={{ ["--hue" as string]: hue }}>
      <div className="reelbg" />

      {/* Story-style segments: one per beat, the current one filling. */}
      <div className="segments">
        {unit.beats.map((_, i) => (
          <span key={i} className="seg">
            <span
              className="segfill"
              style={{
                width: i < n.beat ? "100%" : i === n.beat ? `${beatFill(n, i, unit)}%` : "0%",
              }}
            />
          </span>
        ))}
      </div>

      <header className="reelhead">
        <div className="who">{isAsking ? "Interviewer" : "Student"}</div>
        <div className="tagline">
          §{unit.section}
          {unit.judge && <> · <span title="faithfulness / clarity / pace">
            {unit.judge.faithfulness}·{unit.judge.clarity}·{unit.judge.pace}
          </span></>}
        </div>
      </header>

      {/* The visual. Click anywhere to pause — and pausing silences the voice. */}
      <div className="stage" onClick={n.toggle}>
        <div className="stageinner" key={beat.visual_ref}>
          {beat.svg ? (
            // Sanitised server-side in shorts/feed.py._clean_svg.
            <div className="svgwrap" dangerouslySetInnerHTML={{ __html: beat.svg }} />
          ) : (
            <div className="bigtext">{beat.on_screen}</div>
          )}
        </div>
      </div>

      {/* Caption bubble, pointed at whoever is talking. */}
      <div className={`bubble ${isAsking ? "left" : "right"}`} key={`b${n.beat}`}>
        <p>{beat.on_screen}</p>
      </div>

      {/* The interview itself, seated across a desk along the bottom. */}
      <div className="scenewrap">
        <InterviewScene speaker={beat.speaker} speaking={n.speaking} />
      </div>

      <footer className="reelfoot">
        <span className="qtext">{unit.question}</span>
      </footer>

      {/* Instagram-style action rail */}
      <div className="rail">
        <button className={liked ? "on" : ""} onClick={() => setLiked((v) => !v)} title="like (l)">
          <span className="glyph">{liked ? "♥" : "♡"}</span>
        </button>
        <button
          className={flagged !== null ? "on" : ""}
          title="mark this moment confusing"
          onClick={() => {
            const at = +(n.progress * unit.seconds).toFixed(1);
            setFlagged(at);
            onFeedback({ short_id: unit.short_id, event: "confusing", at });
          }}
        >
          <span className="glyph">🤔</span>
          {flagged !== null && <em>{flagged}s</em>}
        </button>
        <button onClick={n.replay} title="replay (r)"><span className="glyph">↻</span></button>
        <div className="railstate"
             title={n.recorded ? "recorded narration"
                   : n.voiceReady ? "browser voice" : "no voice available"}>
          {voiceOn ? (n.voiceReady ? (n.speaking ? "🔊" : "🔈") : "⚠") : "🔇"}
          {n.recorded && <em>hd</em>}
        </div>
      </div>

      {/* Big centre affordance */}
      {!n.playing && active && (
        <button className="tap" onClick={finished ? n.replay : n.play}>
          <span>{finished ? "↻" : "▶"}</span>
        </button>
      )}
    </div>
  );
}

/** How full the current segment should be, so it animates rather than jumping. */
function beatFill(n: { progress: number }, i: number, unit: Unit): number {
  const beats = unit.beats.length;
  if (!beats) return 0;
  const per = 1 / beats;
  const within = (n.progress - i * per) / per;
  return Math.max(0, Math.min(100, within * 100));
}
