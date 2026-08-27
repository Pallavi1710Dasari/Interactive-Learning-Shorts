import { useMemo } from "react";
import { AnimatedSvg } from "./AnimatedSvg";
import { FlowingCaption } from "./FlowingCaption";
import { ThreeStage } from "./ThreeStage";
import type { Unit } from "./types";

/**
 * Everything a viewer WATCHES, with none of what they click.
 *
 * WHY THIS WAS EXTRACTED. There are two things that draw a short: the player, which
 * gets its beat and its clock from <audio> via useNarration, and the MP4 renderer,
 * which gets them from a frame counter. Before this, only the player existed, and
 * shorts/video.py drew its OWN approximation of it — a hand-written HTML page whose
 * comment admitted it "deliberately mirrors web/src/styles.css rather than importing
 * it". The two drifted exactly as far as you would expect: the download had no
 * background, no depth layer, no progress segments, no per-word caption reveal and
 * no build animation. It was a slideshow of stills, and the complaint was the
 * obvious one — "it is looking like video not the reel".
 *
 * So the pixels now have ONE definition. This component is the picture; the two
 * callers only disagree about where `beatIndex` and `time` come from. A change to
 * the look lands in the download automatically, because there is no second copy of
 * the look to forget to update.
 *
 * WHAT IS DELIBERATELY NOT HERE: the action rail, the tap-to-play affordance, and
 * the judge's scores. The first two are controls, which a video file cannot honour
 * and should not show; the third is internal QA (faithfulness/clarity/pace) that
 * has no business in a file that gets posted. `chrome={false}` is what the renderer
 * passes, and it is why the export is postable as-is.
 */
export function ReelStage({
  unit, beatIndex, time, speaking, hue, chrome = true, progressPct, onStageClick,
}: {
  unit: Unit;
  /** Which beat is on screen. */
  beatIndex: number;
  /** Seconds into the whole short — drives the caption reveal. */
  time: number;
  /** Whether the voice is mid-sentence; the depth layer reacts to it. */
  speaking: boolean;
  /** The short's own hue, so the depth layer matches the background. */
  hue: number;
  /** false in the MP4 renderer: hide the header's QA scores. */
  chrome?: boolean;
  /** 0..100 fill for the current segment. */
  progressPct: number;
  /** Tap-to-pause in the player; absent in the renderer, which cannot be tapped. */
  onStageClick?: () => void;
}) {
  const beat = unit.beats[beatIndex];

  // Every frame of this short, so AnimatedSvg can crop them all to one shared box
  // instead of letting each beat pick its own scale. See cropFor().
  const frames = useMemo(
    () => unit.beats.map((b) => b.svg ?? "").filter(Boolean),
    [unit.beats],
  );

  const isAsking = beat.speaker === "interviewer";

  return (
    <>
      <div className="reelbg" />
      {/* WebGL depth behind everything. Mounted only while this reel is the one on
          screen — see ThreeStage for why that matters in a long feed. */}
      <ThreeStage hue={hue} active speaking={speaking} beat={beatIndex} />

      {/* Story-style segments: one per beat, the current one filling. */}
      <div className="segments">
        {unit.beats.map((_, i) => (
          <span key={i} className="seg">
            <span
              className="segfill"
              style={{
                width: i < beatIndex ? "100%"
                     : i === beatIndex ? `${progressPct}%` : "0%",
              }}
            />
          </span>
        ))}
      </div>

      <header className="reelhead">
        <div className="who">
          <span className="mode" aria-hidden="true">{isAsking ? "🤔" : "📖"}</span>
          {isAsking ? "Asking" : "Answering"}
        </div>
        <div className="tagline">
          §{unit.section}
          {/* QA scores are for the reviewer, not for a file that gets posted. */}
          {chrome && unit.judge && <> · <span title="faithfulness / clarity / pace">
            {unit.judge.faithfulness}·{unit.judge.clarity}·{unit.judge.pace}
          </span></>}
        </div>
      </header>

      {/* .stage WRAPS ONLY THE CARD, and the layers above and below it are its
          SIBLINGS. Getting this wrong is what broke the layout once already: the
          first cut of this component returned the whole stack for the caller to
          drop inside its own <div className="stage">, which nested .segments,
          .reelhead and .bubble inside the diagram's own box. They are positioned
          against .reel — top:0 for the segments, bottom for the caption — so
          against .stage instead they landed ON the drawing. The caption sat over
          the bottom third of every diagram and the "Asking" chip over its title. */}
      <div className="stage" onClick={onStageClick}>
        <div className="stageinner" key={beat.visual_ref}>
          {beat.svg ? (
            // Keyed on the visual_ref so a beat that REUSES the previous frame's
            // visual does not replay its build. That is the point of the "one
            // composition" design: the picture holds, and only the narration moves.
            <AnimatedSvg svg={beat.svg} beatKey={beat.visual_ref}
                         composition={frames}
                         beatMs={(beat.end - beat.start) * 1000} />
          ) : (
            <div className="bigtext">{beat.on_screen}</div>
          )}
        </div>
      </div>

      <div className={`bubble ${isAsking ? "left" : "right"}`}>
        <FlowingCaption line={beat.line} words={beat.words} time={time}
                        speaker={beat.speaker} />
      </div>
    </>
  );
}

/** A stable per-short hue so the feed does not look like one long identical page. */
export function hueFor(shortId: string): number {
  let h = 0;
  for (const c of shortId) h = (h * 31 + c.charCodeAt(0)) % 360;
  return 152 + (h % 56);
}

/** How full the current segment should be, so it animates rather than jumping. */
export function beatFill(progress: number, i: number, beats: number): number {
  if (!beats) return 0;
  const per = 1 / beats;
  const within = (progress - i * per) / per;
  return Math.max(0, Math.min(100, within * 100));
}
