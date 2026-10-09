// MotionStage — the full-reel player (RESTYLE_TO_MOTION_REELS.md phase 3,
// moved here from phase 2): one frame of a whole motion reel at time t, from
// its plan (output/<short_id>/plan.json). It lays the shots, the field
// transitions between them, the chrome, the karaoke captions and — in a
// two-speaker reel — the two avatars on ONE timeline.
//
// PURE IN t. Nothing here keeps time; MotionPlayer (or the capture renderer)
// hands in t. Every object's state comes from the plan's actions, every
// caption word's lighting from its real word times, every avatar's state
// from who is speaking at t.

import { Fit, Frame, Layer } from "../Stage";
import { KaraokeCaption, sentenceAt, type CaptionSentence } from "../KaraokeCaption";
import { CornerMark, ProgressSegments, SectionLabel, StepChip } from "../chrome";
import { FieldTransition, TRANSITION_DUR, type TransitionKind } from "../transitions";
import { CHAPTER_CARD } from "../objects/editorial";
import { FIELDS, SAFE, theme } from "../tokens";
import { clamp, seg } from "../time";
import { Avatar, NameTag, AVATAR_BOX, type AvatarState } from "../avatars/Avatar";
import { FULL_KINDS, SceneObject } from "./objects";
import type { MotionPlan, PlanCast, PlanShot } from "./types";
import library from "../library.json";

const FRAME = (library as { frame: { avatars: { top: number; bottom: number; left_x: number; right_x: number } } }).frame;
const TRANSITIONS = new Set(["iris", "bar_wipe", "double_bar_wipe", "diagonal_stripes", "stack_rise"]);

/** The index of the shot playing at t (the last one that has started). */
export function shotIndexAt(plan: MotionPlan, t: number): number {
  let i = 0;
  for (let k = 0; k < plan.shots.length; k++) if (t >= plan.shots[k].start) i = k;
  return i;
}

function sentences(shot: PlanShot): CaptionSentence[] {
  return shot.captions.map((c) => ({ start: c.start, end: c.end, words: c.words }));
}

/** Who is speaking at t: the speaker of the caption being spoken. */
export function speakerAt(shot: PlanShot, t: number): string | null {
  for (const c of shot.captions) if (t >= c.start - 0.02 && t <= c.end + 0.05) return c.speaker;
  return null;
}

/** An avatar's state at t, and since when: talking while its caption plays;
 * reacting for a moment after the OTHER speaker asks a question, or when a
 * result lands on screen (a state/stamp action with a tone); idle otherwise. */
export function avatarState(shot: PlanShot, role: string, t: number): { state: AvatarState; since: number } {
  const talking = shot.captions.find((c) => c.speaker === role && t >= c.start - 0.02 && t <= c.end + 0.05);
  if (talking) return { state: "talking", since: t - talking.start };
  let react = -1;
  for (const c of shot.captions) {
    if (c.speaker && c.speaker !== role && /\?\s*$/.test(c.text.replace(/<\/?b>/g, "")) && t >= c.end && t < c.end + 0.9) react = c.end;
  }
  for (const a of shot.actions) {
    if ((a.do === "state" || a.do === "stamp") && (a.tone === "ok" || a.tone === "bad") && t >= a.t && t < a.t + 0.9) react = Math.max(react, a.t);
  }
  if (react >= 0) return { state: "reacting", since: t - react };
  return { state: "idle", since: 99 };
}

function Duo({ plan, shot, t }: { plan: MotionPlan; shot: PlanShot; t: number }) {
  const th = theme(shot.field);
  const h = FRAME.avatars.bottom - FRAME.avatars.top;
  const w = AVATAR_BOX.w * (h / AVATAR_BOX.h);
  const speaking = speakerAt(shot, t);
  return (
    <>
      {plan.cast.map((m: PlanCast) => {
        const { state, since } = avatarState(shot, m.role, t);
        const x = m.side === "left" ? FRAME.avatars.left_x : FRAME.avatars.right_x;
        const active = speaking === m.role;
        return (
          <div key={m.role} style={{ position: "absolute", left: x - w / 2, top: FRAME.avatars.top, width: w,
                                     transform: `scale(${active || !speaking ? 1 : 0.93})`, transformOrigin: "50% 100%" }}>
            <Avatar spec={m.avatar} state={state} t={t} since={since} size={h} flip={m.side === "right"}
                    outline={th.dark ? "rgba(255,255,255,0.85)" : "#151936"} />
            <div style={{ position: "absolute", left: -60, right: -60, top: h + 14, display: "flex", justifyContent: "center" }}>
              <NameTag name={m.avatar.name} role={m.role} active={active} accent={th.accent} dark={th.dark} />
            </div>
          </div>
        );
      })}
    </>
  );
}

/** One shot's content (no transition): field, label, objects, chrome. */
export function ShotContent({ plan, index, t }: { plan: MotionPlan; index: number; t: number }) {
  const shot = plan.shots[index];
  const field = shot.field;
  const full = shot.objects.some((o) => FULL_KINDS.has(o.kind));
  const walk = plan.template === "walkthrough";
  const chapters = Math.max(0, ...plan.shots.map((s) => s.chapter ?? 0));
  const cardShot = shot.objects.some((o) => o.kind === "chapter_card");
  const local = t - shot.start;
  return (
    <Layer style={{ background: FIELDS[field] }}>
      {shot.label && !full && <SectionLabel text={shot.label} x={SAFE.side} y={shot.layout === "duo" ? 196 : 226} field={field}
                                            p={seg(local, 0, 0.3)} />}
      {shot.objects.map((o) => <SceneObject key={o.id} obj={o} shot={shot} t={t} field={field} series={plan.series} />)}
      {shot.layout === "duo" && !full && <Duo plan={plan} shot={shot} t={t} />}
      {!walk && !full && <ProgressSegments count={plan.shots.length} index={index}
                                           progress={clamp(local / Math.max(0.1, shot.end - shot.start))} field={field} />}
      {walk && shot.chapter != null && !full && <StepChip n={shot.chapter} of={chapters} field={field} />}
      {walk && cardShot && shot.chapter != null && (
        <StepChip n={shot.chapter} of={chapters} field={field} p={seg(local, CHAPTER_CARD.exitAt, 0.2)}
                  hideNumber={local < CHAPTER_CARD.exitAt + CHAPTER_CARD.fly} />
      )}
      {!full && plan.series && <CornerMark text={plan.series} field={field} />}
    </Layer>
  );
}

/** The speaker of the caption on screen, as a small tag above it. */
function SpeakerTag({ plan, shot, t }: { plan: MotionPlan; shot: PlanShot; t: number }) {
  const s = sentenceAt(sentences(shot), t);
  if (!s) return null;
  const cap = shot.captions.find((c) => c.start === s.start);
  // In a two-speaker reel the lit name tag under the avatar already says who
  // is talking; the tag here is for a shot that shows no avatars.
  if (!cap?.speaker || (plan.cast.length && !shot.objects.some((o) => FULL_KINDS.has(o.kind)))) return null;
  const member = plan.cast.find((m) => m.role === cap.speaker);
  const th = theme(shot.field);
  return (
    <div style={{ position: "absolute", left: SAFE.side, top: SAFE.captionTop - 58, fontFamily: "'JetBrains Mono', monospace",
                  fontWeight: 700, fontSize: 26, letterSpacing: 4, color: th.accent }}>
      {(member?.avatar.name ?? cap.speaker).toUpperCase()}
    </div>
  );
}

/** One frame of the reel at time t. */
export function MotionFrame({ plan, t }: { plan: MotionPlan; t: number }) {
  const i = shotIndexAt(plan, t);
  const shot = plan.shots[i];
  const prev = i > 0 ? plan.shots[i - 1] : null;
  const into = t - shot.start;
  const kind = TRANSITIONS.has(shot.transition) ? shot.transition as TransitionKind
    : shot.transition === "type_scatter" ? "iris" : null;
  const transitioning = prev && kind && into < TRANSITION_DUR;
  const showCaption = !shot.objects.some((o) => o.kind === "title_card" || o.kind === "end_card");
  return (
    <Frame field={shot.field}>
      {transitioning ? (
        <FieldTransition kind={kind!} from={prev!.field} to={shot.field} t={into}
                         outgoing={<ShotContent plan={plan} index={i - 1} t={Math.min(t, prev!.end)} />}
                         incoming={<ShotContent plan={plan} index={i} t={t} />} />
      ) : (
        <ShotContent plan={plan} index={i} t={t} />
      )}
      {showCaption && <>
        <SpeakerTag plan={plan} shot={shot} t={t} />
        <KaraokeCaption sentences={sentences(shot)} t={t} field={shot.field} />
      </>}
    </Frame>
  );
}

/** The frame scaled to a screen width. */
export function MotionStage({ plan, t, width }: { plan: MotionPlan; t: number; width: number }) {
  return <Fit width={width}><MotionFrame plan={plan} t={t} /></Fit>;
}
