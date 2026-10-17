// VideoFrame — one frame of a long-form VIDEO (plan.format = "video",
// shorts/motion_video.py) at time t: a 1920 x 1080 landscape frame, the way a
// YouTube lesson looks.
//
// Every shot's visual is the reel's own: its objects are laid out in the
// 1080 x 1920 design units every scene object draws in, and drawn here through
// the shot's VIEW — the region src of that layout scaled into dst on this
// frame. So every object, animation and highlight is the reel's, unchanged.
//
// Around it:
//   - the mentor, a 3D VRM avatar, beside the board on the shots that have
//     the presenter (shot.characters), sliding in and out (presenceAt); a
//     two-speaker video adds the asker on the left, the board between them;
//   - subtitles along the bottom, one spoken sentence at a time, the words
//     lighting as they are said — never under the mentor;
//   - the chapter top left ("CHAPTER 2 · How it grows"), the series top right;
//   - a progress bar at the very bottom with a tick at every chapter.
// Shots change with a short cross-fade (the reel's field transitions are
// drawn for a portrait frame).
//
// PURE IN t, like the reel's MotionFrame.

import type { CSSProperties, ReactNode } from "react";
import { FIELDS, FONT, theme, type FieldName } from "../tokens";
import { clamp, ease, seg } from "../time";
import { sentenceAt, plainWord, type CaptionSentence } from "../KaraokeCaption";
import { SceneObject, FULL_KINDS } from "../scene/objects";
import { VrmCast } from "../vrm/VrmCast";
import { presenceAt } from "../cast/ReelCharacters";
import { designOf, designVars, MIDNIGHT_STUDIO_VARS } from "../designs";
import { applyPalette } from "../tokens";
import { textToneOn } from "../identity/contrast";
import { designed, paletteOf, rev, shotIndexAt, studio } from "../scene/MotionStage";
import type { MotionPlan, PlanShot, PlanView } from "../scene/types";
import library from "../library.json";

import "../fonts.css";

export const VIDEO_W = 1920;
export const VIDEO_H = 1080;

interface VideoGeometry {
  board_on: number[]; board_off: number[];
  /** a two-speaker video, both presenters on: the board between them */
  board_duo: number[];
  chapter: { x: number; y: number; h: number };
  subtitle: { top: number; bottom: number; side: number; font: number; line_h: number; lines: number };
  progress: { y: number; h: number };
}
export const VIDEO = (library as unknown as { frame: { video: VideoGeometry } }).frame.video;

/** Seconds a shot change cross-fades over. */
export const VIDEO_FADE = 0.45;

/** A visual's soft board behind it: a quiet panel, lighter on dark fields. */
function BoardPanel({ rect, field, opacity }: { rect: number[]; field: FieldName; opacity: number }) {
  const dark = theme(field).dark;
  const [x, y, w, h] = rect;
  return <div data-part="board" style={{
    position: "absolute", left: x - 20, top: y - 20, width: w + 40, height: h + 40, borderRadius: 36, opacity,
    background: dark ? "rgba(255,255,255,0.04)" : "rgba(21,25,54,0.035)",
    boxShadow: dark ? "inset 0 0 0 2px rgba(255,255,255,0.07)" : "inset 0 0 0 2px rgba(21,25,54,0.06)",
  }} />;
}

/** The shot's objects, drawn from the reel layout's src region into dst. */
function ShotVisual({ plan, shot, t, view }: { plan: MotionPlan; shot: PlanShot; t: number; view: PlanView }) {
  const { src, dst, s } = view;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: 1080, height: 1920, transformOrigin: "0 0",
                  transform: `translate(${dst[0] - src[0] * s}px, ${dst[1] - src[1] * s}px) scale(${s})` }}>
      <div style={{ position: "absolute", left: src[0], top: src[1], width: src[2], height: src[3], overflow: "hidden",
                    borderRadius: 28 / s }}>
        <div style={{ position: "absolute", left: -src[0], top: -src[1], width: 1080, height: 1920 }}>
          {shot.objects.map((o) => (
            <div key={o.id} data-part={`obj:${o.id}:${o.kind}`}>
              <SceneObject obj={o} shot={shot} t={t} field={shot.field} series={plan.series}
                           identity={plan.identity} themeLabel={plan.theme_label} tags={plan.tags} rev={rev(plan)}
                           board={!!shot.characters} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The fallback view (a plan made before views): the reel's content region, fitted. */
function viewOf(shot: PlanShot): PlanView {
  if (shot.view) return shot.view;
  const src: [number, number, number, number] = [0, 150, 1080, 1150];
  const [dx, dy, dw, dh] = VIDEO.board_off;
  const s = Math.min(dw / src[2], dh / src[3]);
  return { src, dst: [dx + (dw - src[2] * s) / 2, dy, src[2] * s, src[3] * s], s };
}

/** Two presenters (a two-speaker theme): the asker left, the mentor right. */
const duo = (plan: MotionPlan) => (plan.characters?.length ?? 0) === 2;

/** The board a shot is drawn on: beside the presenter(s), or wide without. */
function boardOf(plan: MotionPlan, shot: PlanShot): number[] {
  if (!shot.characters) return VIDEO.board_off;
  return duo(plan) ? VIDEO.board_duo : VIDEO.board_on;
}

/** One shot's layer: its board panel and its visual. */
function ShotLayer({ plan, index, t, opacity = 1 }: { plan: MotionPlan; index: number; t: number; opacity?: number }) {
  const shot = plan.shots[index];
  const view = viewOf(shot);
  const full = shot.objects.some((o) => FULL_KINDS.has(o.kind));
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      {!full && <BoardPanel rect={boardOf(plan, shot)} field={shot.field} opacity={1} />}
      <ShotVisual plan={plan} shot={shot} t={t} view={view} />
    </div>
  );
}

/** The field across the whole frame, with a soft light from the top. */
function Background({ field }: { field: FieldName }) {
  const dark = theme(field).dark;
  return <div style={{ position: "absolute", inset: 0, background: FIELDS[field],
    backgroundImage: dark
      ? "radial-gradient(120% 90% at 30% 0%, rgba(255,255,255,0.07), transparent 60%)"
      : "radial-gradient(120% 90% at 30% 0%, rgba(255,255,255,0.55), transparent 60%)" }} />;
}

function sentences(shot: PlanShot): CaptionSentence[] {
  return shot.captions.map((c) => ({ start: c.start, end: c.end, words: c.words }));
}

/** The sentence being said, as a subtitle: spoken words full white, the rest
 * dimmed, a highlighted keyword in yellow — on a dark band, centred under
 * the board (presenter on) or across the frame (off). In a two-speaker
 * video it opens with the speaker's name, in their identity's colour. */
function Subtitle({ plan, shot, t, on }: { plan: MotionPlan; shot: PlanShot; t: number; on: boolean }) {
  const s = sentenceAt(sentences(shot), t);
  if (!s || t > s.end + 0.6) return null;
  const g = VIDEO.subtitle;
  const [bx, , bw] = on ? boardOf(plan, shot) : [g.side, 0, VIDEO_W - 2 * g.side];
  const appear = ease.outCubic(seg(t, s.start - 0.05, 0.18));
  const said = shot.captions.find((c) => c.start === s.start && c.end === s.end);
  const member = said?.speaker ? plan.cast.find((m) => m.role === said.speaker) : undefined;
  return (
    <div data-part="caption" style={{ position: "absolute", left: bx, width: bw, top: g.top, height: g.bottom - g.top,
                                      display: "flex", alignItems: "center", justifyContent: "center", opacity: appear }}>
      <div style={{ maxWidth: bw, padding: "10px 26px", borderRadius: 16, background: "rgba(8,10,28,0.74)",
                    fontFamily: FONT.body, fontWeight: 700, fontSize: g.font, lineHeight: `${g.line_h}px`,
                    textAlign: "center", color: "#FFFFFF" }}>
        {member && <span data-part="speaker" style={{ fontFamily: FONT.mono, fontSize: 24, letterSpacing: 3,
                                                      textTransform: "uppercase", marginRight: 16, verticalAlign: "middle",
                                                      color: member.identity ? textToneOn(member.identity, "navy") : "#9FB4FF" }}>
          {member.label}</span>}
        {s.words.map((w, i) => {
          const said = t >= w.start - 0.02;
          return <span key={i} style={{ color: w.hl ? "#FDD13E" : "#FFFFFF", opacity: said ? 1 : 0.42 }}>
            {plainWord(w.text)}{i < s.words.length - 1 ? " " : ""}</span>;
        })}
      </div>
    </div>
  );
}

/** Top left: the chapter this shot belongs to, or the concept. */
function ChapterTag({ plan, shot, t }: { plan: MotionPlan; shot: PlanShot; t: number }) {
  const th = theme(shot.field);
  const chapters = Math.max(0, ...plan.shots.map((s) => s.chapter ?? 0));
  const card = plan.shots.find((s) => s.chapter === shot.chapter && s.objects.some((o) => o.kind === "chapter_card"));
  const title = card?.objects.find((o) => o.kind === "chapter_card")?.props.title as string | undefined;
  const g = VIDEO.chapter;
  const p = ease.outCubic(seg(t - shot.start, 0, 0.35));
  const pill: CSSProperties = { fontFamily: FONT.mono, fontWeight: 700, fontSize: 22, letterSpacing: 3,
                                textTransform: "uppercase", padding: "8px 14px", borderRadius: 999 };
  return (
    <div data-part="chapter" style={{ position: "absolute", left: g.x, top: g.y, height: g.h, display: "flex",
                                      alignItems: "center", gap: 16, opacity: p }}>
      {shot.chapter != null ? <>
        <span style={{ ...pill, background: th.accent, color: th.dark ? "#151936" : "#FFFFFF" }}>
          Chapter {shot.chapter}{chapters ? ` / ${chapters}` : ""}</span>
        {title && <span style={{ fontFamily: FONT.body, fontWeight: 750, fontSize: 28, color: th.ink }}>{title}</span>}
      </> : plan.concept_name ? (
        <span style={{ ...pill, color: th.dim, padding: 0 }}>{plan.concept_name}</span>
      ) : null}
    </div>
  );
}

/** Top right: the series handle, small. */
function SeriesMark({ plan, field }: { plan: MotionPlan; field: FieldName }) {
  if (!plan.series) return null;
  return <div data-part="corner" style={{ position: "absolute", right: 64, top: VIDEO.chapter.y, height: VIDEO.chapter.h,
                                          display: "flex", alignItems: "center", fontFamily: FONT.mono, fontSize: 22,
                                          fontWeight: 700, color: theme(field).dim }}>{plan.series}</div>;
}

/** The bottom edge: how far into the video, with a tick at each chapter. */
function Progress({ plan, t, field }: { plan: MotionPlan; t: number; field: FieldName }) {
  const g = VIDEO.progress;
  const th = theme(field);
  const ticks = plan.shots.filter((s) => s.objects.some((o) => o.kind === "chapter_card"));
  return (
    <div data-part="progress" style={{ position: "absolute", left: 0, top: g.y, width: VIDEO_W, height: g.h,
                                       background: th.dark ? "rgba(255,255,255,0.12)" : "rgba(21,25,54,0.1)" }}>
      <div style={{ width: `${100 * clamp(t / Math.max(0.1, plan.duration))}%`, height: "100%", background: th.accent }} />
      {ticks.map((s) => <div key={s.id} style={{ position: "absolute", top: -4, left: `${100 * s.start / Math.max(0.1, plan.duration)}%`,
                                                 width: 4, height: g.h + 8, borderRadius: 2,
                                                 background: th.dark ? "rgba(255,255,255,0.55)" : "rgba(21,25,54,0.45)" }} />)}
    </div>
  );
}

/** One frame of the video at time t. */
export function VideoFrame({ plan: raw, t }: { plan: MotionPlan; t: number }) {
  const plan = designed(raw);
  const design = designOf(plan.design);
  applyPalette(paletteOf(plan), studio(plan));
  const vars = studio(plan) && design.id === "midnight_lab" ? MIDNIGHT_STUDIO_VARS as CSSProperties : designVars(design);
  const i = shotIndexAt(plan, t);
  const shot = plan.shots[i];
  const prev = i > 0 ? plan.shots[i - 1] : null;
  const into = t - shot.start;
  const fading = prev && into < VIDEO_FADE;
  const p = fading ? ease.inOutCubic(clamp(into / VIDEO_FADE)) : 1;
  let layers: ReactNode;
  if (fading) {
    layers = <>
      <Background field={prev!.field} />
      <div style={{ position: "absolute", inset: 0, opacity: p }}><Background field={shot.field} /></div>
      <ShotLayer plan={plan} index={i - 1} t={Math.min(t, prev!.end)} opacity={1 - p} />
      <ShotLayer plan={plan} index={i} t={t} opacity={p} />
    </>;
  } else {
    layers = <><Background field={shot.field} /><ShotLayer plan={plan} index={i} t={t} /></>;
  }
  return (
    <div data-frame="" data-format="video" style={{ position: "relative", width: VIDEO_W, height: VIDEO_H, overflow: "hidden",
                                                    background: FIELDS[shot.field], fontFamily: FONT.body, ...vars }}>
      {layers}
      {/* a chapter card names its own chapter */}
      {!shot.objects.some((o) => o.kind === "chapter_card") && <ChapterTag plan={plan} shot={shot} t={t} />}
      <SeriesMark plan={plan} field={shot.field} />
      {/* the 3D mentor stays mounted (its model loads once) and comes and goes with its shots */}
      {plan.avatars === "vrm" && plan.characters?.length > 0 && (
        <VrmCast plan={plan} t={t} presence={presenceAt(plan, i, t, fading ? VIDEO_FADE : 0)} slide />
      )}
      <Subtitle plan={plan} shot={shot} t={t} on={!!shot.characters} />
      <Progress plan={plan} t={t} field={shot.field} />
    </div>
  );
}

/** The video frame scaled to a screen width. */
export function VideoStage({ plan, t, width }: { plan: MotionPlan; t: number; width: number }) {
  const s = width / VIDEO_W;
  return (
    <div style={{ width, height: VIDEO_H * s, position: "relative", overflow: "hidden", flex: "none" }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: VIDEO_W, height: VIDEO_H,
                    transform: `scale(${s})`, transformOrigin: "0 0" }}>
        <VideoFrame plan={plan} t={t} />
      </div>
    </div>
  );
}
