import { useEffect, useMemo, useState } from "react";
import { useNarration } from "./useNarration";
import { Avatar } from "./Avatars";
import { ReelStage, beatFill, hueFor } from "./ReelStage";
import { CommentIcon, DownloadIcon, RedrawIcon, ReplayIcon,
         SpinnerIcon, VolumeIcon } from "./RailIcons";
import { revisual } from "./api";
import type { Feedback, Unit } from "./types";

/**
 * One short, playing.
 *
 * The PICTURE lives in <ReelStage>, which the MP4 renderer draws too — see that
 * file for why. What is left here is everything a video file cannot have: the
 * clock, the keyboard, and the controls down the right-hand side.
 */
export function Reel({
  unit, active, voiceOn, rate, onFeedback, onDownload, downloading, downloadPct,
  onRedrawn,
}: {
  unit: Unit;
  active: boolean;
  voiceOn: boolean;
  rate: number;
  onFeedback: (f: Feedback) => void;
  /** Save this short as an MP4. Lives in the rail, where a reel's actions live. */
  onDownload?: (unit: Unit) => void;
  downloading?: boolean;
  /** 0-100 while the MP4 renders, so the button can show real progress. */
  downloadPct?: number;
  /** The short, with its frames replaced, after a redraw. */
  onRedrawn?: (unit: Unit) => void;
}) {
  const n = useNarration(unit.beats, unit.seconds,
                         { enabled: voiceOn, rate, active, audioUrl: unit.audio_url });
  const beat = unit.beats[n.beat];
  // Asked, not inferred. The old test was `!playing && beat === last &&
  // progress > 0.5`, which called a short finished on the strength of a sampled
  // clock — see Narration.completed for why that read as an unfinished video.
  const finished = n.completed;
  const [flagged, setFlagged] = useState(false);
  // The redraw composer. Open state and text live here rather than in App because
  // the note is about THIS short and nothing above needs to know it was typed.
  const [redrawOpen, setRedrawOpen] = useState(false);
  const [note, setNote] = useState("");
  const [redrawing, setRedrawing] = useState(false);
  const [redrawErr, setRedrawErr] = useState<string | null>(null);

  const sendRedraw = async () => {
    if (!note.trim() || redrawing) return;
    setRedrawing(true);
    setRedrawErr(null);
    try {
      const r = await revisual(unit.short_id, note);
      if (r.short) onRedrawn?.(r.short);
      setNote("");
      setRedrawOpen(false);
    } catch (e) {
      setRedrawErr(e instanceof Error ? e.message : String(e));
    } finally {
      setRedrawing(false);
    }
  };

  const hue = useMemo(() => hueFor(unit.short_id), [unit.short_id]);

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
      else if (e.key === "d") onDownload?.(unit);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, n, unit, onDownload]);

  const isAsking = beat.speaker === "interviewer";

  return (
    <div className={`reel${active ? " live" : ""}`} style={{ ["--hue" as string]: hue }}>
      {/* ReelStage owns .stage; clicking the picture pauses, and pausing
          silences the voice. */}
      <ReelStage
        unit={unit}
        beatIndex={n.beat}
        time={n.time}
        speaking={n.speaking}
        hue={hue}
        progressPct={beatFill(n.progress, n.beat, unit.beats.length)}
        onStageClick={n.toggle}
      />

      {/* The action rail. Reads top to bottom the way a reel's does: whose turn it
          is, react to it, then keep it. The speaker avatar sits at the top because
          on a reel that slot is whose post it is, and here the "author" of the
          moment is whoever is talking. Like/share/save were dropped: they toggled
          local state and did nothing else (share only copied a link), and on a
          solo-study tool that social-engagement chrome read as a kids' app rather
          than exam prep. */}
      <div className="rail">
        <div className="whocell" title={isAsking ? "interviewer asking" : "student answering"}>
          <Avatar speaker={beat.speaker} speaking={n.speaking} size={34} />
        </div>

        {/* The honest label for "this confused me". It is the one feedback signal
            the reel can collect that the pipeline actually consumes — see
            README Part E — so it keeps a button rather than being dropped for a
            comment box the server has nowhere to put. */}
        <button className="railbtn"
                onClick={() => { onFeedback({ short_id: unit.short_id, event: "confusing",
                                              at: +n.time.toFixed(1) });
                                 setFlagged(true); setTimeout(() => setFlagged(false), 1600); }}
                title="mark this moment confusing (c)">
          <CommentIcon />
          <em>{flagged ? "noted" : "unclear"}</em>
        </button>

        <button className={`railbtn${downloading ? " busy" : ""}`} disabled={downloading}
                onClick={() => onDownload?.(unit)} title="download this reel (d)">
          {downloading ? <SpinnerIcon /> : <DownloadIcon />}
          <em>{downloading ? (downloadPct ? `${downloadPct}%` : "start\u2026") : "mp4"}</em>
        </button>

        <button className={`railbtn${redrawOpen ? " on" : ""}`}
                onClick={() => setRedrawOpen((v) => !v)}
                title="redraw these frames from a note">
          <RedrawIcon />
          <em>redraw</em>
        </button>

        <button className="railbtn" onClick={n.replay} title="replay (r)">
          <ReplayIcon />
          <em>replay</em>
        </button>

        <div className="railstate"
             title={n.recorded ? "recorded narration"
                   : n.voiceReady ? "browser voice" : "no voice available"}>
          <VolumeIcon level={!voiceOn ? "off" : !n.voiceReady ? "warn"
                             : n.speaking ? "on" : "idle"} />
          <em>{n.recorded ? "hd" : voiceOn ? "voice" : "muted"}</em>
        </div>
      </div>

      {/* The redraw composer. Anchored to the rail, over the reel, because the
          thing being described is on screen behind it. */}
      {redrawOpen && (
        <div className="redrawbox" onClick={(e) => e.stopPropagation()}>
          <b>What should the pictures show instead?</b>
          <textarea
            autoFocus value={note} rows={3}
            placeholder={'e.g. "frame 2 is unreadable \u2014 show the page table as a table, not icons"'}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void sendRedraw();
              if (e.key === "Escape") setRedrawOpen(false);
            }}
          />
          {redrawErr && <span className="error sm">{redrawErr}</span>}
          <div className="redrawfoot">
            <span className="hintline">{"\u2318"}/Ctrl + Enter</span>
            <span className="spacer" />
            <button className="ghost sm" onClick={() => setRedrawOpen(false)}>cancel</button>
            <button className="primary sm" disabled={!note.trim() || redrawing}
                    onClick={sendRedraw}>
              {redrawing ? "redrawing\u2026" : "Redraw"}
            </button>
          </div>
        </div>
      )}

      {/* Big centre affordance */}
      {!n.playing && active && (
        <button className="tap" onClick={finished ? n.replay : n.play}>
          <span>{finished ? "↻" : "▶"}</span>
        </button>
      )}
    </div>
  );
}
