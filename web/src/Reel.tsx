import { useEffect, useMemo, useState } from "react";
import { AnimatedSvg } from "./AnimatedSvg";
import { Avatar } from "./Avatars";
import { FlowingCaption } from "./FlowingCaption";
import { ThreeStage } from "./ThreeStage";
import type { Feedback, Unit } from "./types";
import { useNarration } from "./useNarration";

/**
 * One short, playing.
 *
 * ONE THING AT A TIME. THAT IS THE WHOLE LAYOUT RULE.
 * This frame used to carry, simultaneously: a diagram, a three-word headline chip
 * over the diagram, the spoken line as a caption, the short's question along the
 * bottom, and two illustrated characters at a desk. Five things competing inside a
 * phone-sized rectangle, and a first-time viewer read none of them — the eye had
 * nowhere to land, and the caption and the question said overlapping things in two
 * different places.
 *
 * So the frame is now two zones and nothing else:
 *   the diagram   — the thing to remember, given the whole upper frame
 *   the caption   — the sentence being spoken, flowing word by word
 *
 * The chip went because it repeated the diagram's own title. The question footer
 * went because the first beat IS the question, spoken and captioned. The characters
 * went because they carried no information and took a quarter of the height.
 *
 * No question/answer review panel here either by design — reviewing happens in
 * step 2. A learner watching a reel should see what a learner sees.
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

  // Every frame of this short, so AnimatedSvg can crop them all to one shared box
  // instead of letting each beat pick its own scale. See cropFor().
  const frames = useMemo(
    () => unit.beats.map((b) => b.svg ?? "").filter(Boolean),
    [unit.beats],
  );

  // A stable per-short hue so the feed does not look like one long identical page —
  // but confined to a narrow teal-to-green band.
  //
  // It used to hash across the whole 360-degree wheel, which gave some shorts a hot
  // magenta frame and others acid yellow. Against a light diagram card that reads as
  // garish rather than varied, and a saturated caption panel competes with the one
  // amber element in the drawing that is supposed to be the brightest thing on
  // screen. 55 degrees is enough for one short not to look like the last one.
  const hue = useMemo(() => {
    let h = 0;
    for (const c of unit.short_id) h = (h * 31 + c.charCodeAt(0)) % 360;
    return 152 + (h % 56);
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
      {/* WebGL depth behind everything. Mounted only while this reel is the one on
          screen — see ThreeStage for why that matters in a long feed. */}
      <ThreeStage hue={hue} active={active} speaking={n.speaking} beat={n.beat} />

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
        {/* The mode marker. It changes with the speaker, which the 🤔 in the action
            rail never did — that one is a feedback button, but sitting there
            unchanged through question AND answer it read as a broken indicator. So
            the indicator is here, next to the name it belongs to, and it moves. */}
        <div className="who">
          <span className="mode" aria-hidden="true">{isAsking ? "🤔" : "📖"}</span>
          {isAsking ? "Asking" : "Answering"}
        </div>
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

      {/* The narration itself, revealed word by word under the voice saying it.
          It used to show `on_screen` — three words, read instantly, then nothing
          to follow for the rest of the beat. The spoken line, flowing, is what
          lets a viewer watch with the sound off and still follow the answer. */}
      <div className={`bubble ${isAsking ? "left" : "right"}`}>
        <FlowingCaption line={beat.line} words={beat.words} time={n.time}
                        speaker={beat.speaker} />
      </div>

      {/* Instagram-style action rail */}
      <div className="rail">
        <button className={liked ? "on" : ""} onClick={() => setLiked((v) => !v)} title="like (l)">
          <span className="glyph">{liked ? "♥" : "♡"}</span>
        </button>
        {/* The character whose turn it is, small, and mouthing along while the
            voice runs — the .avatar.speaking keyframes are already in styles.css.
            This slot held three different glyphs before: 🤔 read as a speaker
            state that never changed, ⚑ read as a bare mark, ❓ read as a control.
            The honest answer was that a speaker indicator belongs here and the
            drawn characters already ARE that indicator, so they came back — as an
            icon rather than the full desk scene that used to eat a quarter of the
            frame.

            Note this replaces the "mark this moment confusing" button, so that
            feedback signal is no longer collectable from the reel. The `confusing`
            event and its handling are untouched, and README Part E still describes
            drop-off capture, so putting a control back is a one-line change. */}
        <div className="whocell" title={isAsking ? "interviewer asking" : "student answering"}>
          <Avatar speaker={beat.speaker} speaking={n.speaking} size={30} />
        </div>
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
