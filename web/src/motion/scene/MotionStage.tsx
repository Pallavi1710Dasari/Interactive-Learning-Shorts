// MotionStage — the full-reel player (RESTYLE_TO_MOTION_REELS.md, phase 3):
// one frame of a whole motion reel at time t, from its plan
// (output/<short_id>/plan.json). It lays the shots, the field transitions
// between them, the chrome, the captions and the language identity on ONE
// timeline.
//
// No drawn people (phase 3 badges). The reel's LANGUAGE is a badge in the
// top-right corner for the whole reel, a large mark on the hook, and the
// colour of the progress. In a two-speaker reel the captions are a CHAT:
// circular speaker badges (grey host on the left, the language speaker on
// the right) beside bubbles whose words light as they are spoken; the active
// speaker's badge glows and shows a waveform. The chat has its own region
// below the scene objects and never covers them.
//
// OPTIONAL CHARACTERS (plan.characters, off by default): one per speaker — the
// host and the language character in a two-speaker reel, the language
// character alone narrating a one-narrator reel — in their own region between
// the scene objects and the chat or captions (cast/ReelCharacters.tsx). In a
// two-speaker reel the chat then starts lower and is clipped to its region,
// so nothing covers anything; the plan says per shot whether they show.
//
// PURE IN t. Nothing here keeps time; MotionPlayer (or the capture renderer)
// hands in t.

import { Fit, Frame, Layer } from "../Stage";
import { KaraokeCaption, sentenceAt, type CaptionSentence } from "../KaraokeCaption";
import { CornerMark, ProgressSegments, SectionLabel, StepChip } from "../chrome";
import { FieldTransition, TRANSITION_DUR, type TransitionKind } from "../transitions";
import { CHAPTER_CARD } from "../objects/editorial";
import { FIELDS, SAFE } from "../tokens";
import { clamp, seg } from "../time";
import { BUBBLE, ChatRow, IdentitySting, LanguageBadge, SIDE_BUBBLE, SideBubble, SpeakerBadge, bubbleHeight, rowHeight,
         sideBubbleHeight, toneOn } from "../identity/Identity";
import { FULL_KINDS, SceneObject } from "./objects";
import { textToneOn } from "../identity/contrast";
import { ReelCharacters, STAGE, charactersOn } from "../cast/ReelCharacters";
import type { MotionPlan, PlanCaption, PlanShot } from "./types";
import library from "../library.json";
import { designOf, designVars } from "../designs";
import { LabBackground, LabCamera, ZOOM_DUR, ZoomThrough } from "../lab";

const FRAME = (library as {
  frame: { chat: { top: number; bottom: number }; badge: { x: number; y: number } }
}).frame;
const CHAT_RISE = 32;
const TRANSITIONS = new Set(["iris", "bar_wipe", "double_bar_wipe", "diagonal_stripes", "stack_rise"]);

/** The plan as its design draws it: each shot on the design's field. Cached
 * per plan object, so a frame does not rebuild it. */
const DESIGNED = new WeakMap<MotionPlan, MotionPlan>();
export function designed(plan: MotionPlan): MotionPlan {
  const d = designOf(plan.design);
  if (d.id === "classic") return plan;
  let out = DESIGNED.get(plan);
  if (!out) {
    out = { ...plan, shots: plan.shots.map((s) => ({ ...s, field: d.field(s.field) })) };
    DESIGNED.set(plan, out);
  }
  return out;
}

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

/** The chat at t: the captions that have started, newest last, carrying the
 * end of the previous shot's conversation so both speakers stay on screen. */
export function chatAt(plan: MotionPlan, index: number, t: number): PlanCaption[] {
  const out: PlanCaption[] = [];
  for (let k = Math.max(0, index - 1); k <= index; k++) {
    const shot = plan.shots[k];
    if (k < index && shot.objects.some((o) => FULL_KINDS.has(o.kind))) continue;
    for (const c of shot.captions) if (c.start - 0.25 <= t) out.push(c);
  }
  return out;
}

/** The chat: as many of the latest bubbles as fit the chat region, newest at
 * the bottom, older ones dimmer. Only the bubble being spoken has its badge
 * glowing; every other badge is still. */
function Chat({ plan, index, t }: { plan: MotionPlan; index: number; t: number }) {
  const shot = plan.shots[index];
  const rows = chatAt(plan, index, t);
  const cast = plan.characters?.length > 0;
  if (rev(plan) >= 2 && cast && charactersOn(plan, shot)) return <SideChat plan={plan} index={index} t={t} rows={rows} />;
  // the chat starts below the shot's lowest object: a stack taller than its
  // region (an entity wired to a panel) ran into the oldest bubble
  const objectsBottom = Math.max(0, ...shot.objects
    .filter((o) => o.box && o.box.h > 0 && !FULL_KINDS.has(o.kind)).map((o) => o.box!.y + o.box!.h));
  const top = Math.max(cast && charactersOn(plan, shot) ? STAGE.chat_top : FRAME.chat.top, objectsBottom + 40);
  // with characters the chat may reach CHAT_RISE lower, so the previous
  // speaker's bubble still fits above the newest one
  const bottom = FRAME.chat.bottom + (cast ? CHAT_RISE : 0);
  const room = bottom - top;
  const shown: { c: PlanCaption; h: number }[] = [];
  let used = 0;
  for (let i = rows.length - 1; i >= 0; i--) {
    // only the newest row's badge is large and ringed; older rows are their bubble
    const text = rows[i].words.map((w) => w.text).join(" ");
    const h = i === rows.length - 1 ? rowHeight(text) : bubbleHeight(text);
    if (used + h > room && shown.length) break;
    shown.unshift({ c: rows[i], h });
    used += h + BUBBLE.gap;
  }
  let y = bottom - (used - BUBBLE.gap) - (cast ? top : 0);
  const speaking = speakerAt(shot, t);
  const body = (
    <>
      {shown.map(({ c, h }, i) => {
        const member = plan.cast.find((m) => m.role === c.speaker) ?? plan.cast[0];
        const top = y;
        y += h + BUBBLE.gap;
        const latest = i === shown.length - 1;
        const active = latest && speaking === c.speaker && t <= c.end + 0.05;
        return <ChatRow key={`${c.start}`} member={member} field={shot.field} words={c.words} t={t} y={top}
                        active={active} fade={latest ? 1 : 0.5 + 0.3 * (i / Math.max(1, shown.length - 1))} />;
      })}
    </>
  );
  if (!cast) return body;
  return (
    // the clip reaches CHAT_RISE below the region: a row entering rises that far into place
    <div data-part="chat" style={{ position: "absolute", left: 0, top, width: 1080, height: room + CHAT_RISE, overflow: "hidden" }}>{body}</div>
  );
}

/** The plan's layout rules (MotionPlan.rev): absent = 1, the old look. */
export function rev(plan: MotionPlan): number {
  return plan.rev ?? 1;
}

/** Rev 2 chat beside the drawn characters: its own zone, a clear gap below
 * the characters (frame.chat.bubble.avatar_gap), down to the safe line. Each
 * bubble is pushed to its speaker's side; the newest at the bottom, and only
 * whole bubbles that fit. */
export function sideChatZone(): { top: number; bottom: number } {
  return { top: STAGE.bottom + SIDE_BUBBLE.avatar_gap, bottom: SIDE_BUBBLE.safe_bottom };
}

function SideChat({ plan, index, t, rows }: { plan: MotionPlan; index: number; t: number; rows: PlanCaption[] }) {
  const shot = plan.shots[index];
  const { top, bottom } = sideChatZone();
  const room = bottom - top;
  const shown: { c: PlanCaption; h: number }[] = [];
  let used = 0;
  for (let i = rows.length - 1; i >= 0; i--) {
    const h = sideBubbleHeight(rows[i].words.map((w) => w.text).join(" "));
    if (used + h > room && shown.length) break;
    shown.unshift({ c: rows[i], h });
    used += h + SIDE_BUBBLE.gap;
  }
  let y = room - (used - SIDE_BUBBLE.gap);
  return (
    <div data-part="chat" style={{ position: "absolute", left: 0, top, width: 1080, height: room, overflow: "hidden" }}>
      {shown.map(({ c, h }, i) => {
        const member = plan.cast.find((m) => m.role === c.speaker) ?? plan.cast[0];
        const at = y;
        y += h + SIDE_BUBBLE.gap;
        const latest = i === shown.length - 1;
        return <SideBubble key={`${c.start}`} member={member} field={shot.field} words={c.words} t={t} y={at}
                           fade={latest ? 1 : 0.6} />;
      })}
    </div>
  );
}

/** One shot's content (no transition): field, label, objects, chrome, chat. */
export function ShotContent({ plan, index, t }: { plan: MotionPlan; index: number; t: number }) {
  const shot = plan.shots[index];
  const field = shot.field;
  const full = shot.objects.some((o) => FULL_KINDS.has(o.kind));
  const walk = plan.template === "walkthrough";
  const chapters = Math.max(0, ...plan.shots.map((s) => s.chapter ?? 0));
  const cardShot = shot.objects.some((o) => o.kind === "chapter_card");
  const local = t - shot.start;
  const tone = plan.identity ? toneOn(plan.identity, field) : undefined;
  const design = designOf(plan.design);
  // data-part: what the overlap audit (shorts/motion_overlap) calls each drawn part
  const objects = shot.objects.map((o) => <div key={o.id} data-part={`obj:${o.id}:${o.kind}`}>
    <SceneObject obj={o} shot={shot} t={t} field={field} series={plan.series}
                 identity={plan.identity} themeLabel={plan.theme_label} tags={plan.tags} rev={rev(plan)} /></div>);
  return (
    <Layer style={{ background: design.background === "lab" ? undefined : FIELDS[field] }}>
      {design.background === "lab" && <LabBackground field={field} t={t} />}
      {shot.label && !full && <div data-part="label"><SectionLabel text={design.background === "lab" ? `// ${shot.label}` : shot.label} x={SAFE.side}
                                            y={shot.layout === "duo" || charactersOn(plan, shot) ? 186 : 226} field={field}
                                            p={seg(local, 0, 0.3)} accent={design.background === "lab"} /></div>}
      {design.camera ? <LabCamera local={local}>{objects}</LabCamera> : objects}
      {shot.layout === "duo" && !full && <Chat plan={plan} index={index} t={t} />}
      {!walk && !full && <ProgressSegments count={plan.shots.length} index={index} color={tone}
                                           progress={clamp(local / Math.max(0.1, shot.end - shot.start))} field={field} />}
      {walk && shot.chapter != null && !full && <div data-part="stepchip"><StepChip n={shot.chapter} of={chapters} field={field} color={tone} /></div>}
      {walk && cardShot && shot.chapter != null && (
        <StepChip n={shot.chapter} of={chapters} field={field} color={tone} p={seg(local, CHAPTER_CARD.exitAt, 0.2)}
                  hideNumber={local < CHAPTER_CARD.exitAt + CHAPTER_CARD.fly} />
      )}
      {!full && plan.series && <div data-part="corner"><CornerMark text={plan.series} field={field} /></div>}
    </Layer>
  );
}

/** On a full-frame shot of a two-speaker reel (title, code map, recap, end
 * card) there is no chat: a small badge and label name the speaker above the
 * normal caption. */
function SpeakerTag({ plan, shot, t }: { plan: MotionPlan; shot: PlanShot; t: number }) {
  const s = sentenceAt(sentences(shot), t);
  if (!s) return null;
  const cap = shot.captions.find((c) => c.start === s.start);
  if (!cap?.speaker) return null;
  const member = plan.cast.find((m) => m.role === cap.speaker);
  if (!member) return null;
  const active = t <= cap.end + 0.05;
  return (
    // under the caption, not above it: above, it sat on a full-frame card's last row
    <div style={{ position: "absolute", left: SAFE.side, top: SAFE.captionBottom + 22, display: "flex", alignItems: "center", gap: 16 }}>
      <SpeakerBadge member={member} field={shot.field} active={active} t={t} size={64} />
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 22, letterSpacing: 3,
                     color: textToneOn(member.identity, shot.field), textTransform: "uppercase" }}>{member.label}</span>
    </div>
  );
}

/** One frame of the reel at time t. */
export function MotionFrame({ plan: raw, t }: { plan: MotionPlan; t: number }) {
  const plan = designed(raw);
  const design = designOf(plan.design);
  const vars = designVars(design);
  if (plan.identity && plan.intro > 0 && t < plan.intro) {
    return <Frame field={design.field("navy")} style={vars}><IdentitySting spec={plan.identity} t={t} /></Frame>;
  }
  const i = shotIndexAt(plan, t);
  const shot = plan.shots[i];
  const prev = i > 0 ? plan.shots[i - 1] : null;
  const into = t - shot.start;
  const kind = TRANSITIONS.has(shot.transition) ? shot.transition as TransitionKind
    : shot.transition === "type_scatter" ? "iris" : null;
  const zoom = design.transition === "zoom_through";
  const transitioning = prev && kind && into < (zoom ? ZOOM_DUR : TRANSITION_DUR);
  const full = shot.objects.some((o) => FULL_KINDS.has(o.kind));
  const cardCaption = !shot.objects.some((o) => o.kind === "title_card" || o.kind === "end_card");
  const chat = shot.layout === "duo" && !full;
  return (
    <Frame field={shot.field} style={vars}>
      {transitioning && zoom ? (
        <ZoomThrough t={into} outgoing={<ShotContent plan={plan} index={i - 1} t={Math.min(t, prev!.end)} />}
                     incoming={<ShotContent plan={plan} index={i} t={t} />} />
      ) : transitioning ? (
        <FieldTransition kind={kind!} from={prev!.field} to={shot.field} t={into}
                         outgoing={<ShotContent plan={plan} index={i - 1} t={Math.min(t, prev!.end)} />}
                         incoming={<ShotContent plan={plan} index={i} t={t} />} />
      ) : (
        <ShotContent plan={plan} index={i} t={t} />
      )}
      {charactersOn(plan, shot) && (
        <ReelCharacters plan={plan} t={t} field={shot.field}
                        opacity={transitioning && !charactersOn(plan, prev!) ? clamp(into / (zoom ? ZOOM_DUR : TRANSITION_DUR)) : 1} />
      )}
      {!chat && cardCaption && <>
        <div data-part="speakertag"><SpeakerTag plan={plan} shot={shot} t={t} /></div>
        <div data-part="caption"><KaraokeCaption sentences={sentences(shot)} t={t} field={shot.field} /></div>
      </>}
      {plan.identity && <LanguageBadge spec={plan.identity} field={shot.field} right={1080 - FRAME.badge.x} top={FRAME.badge.y}
                                       p={clamp((t - plan.intro) / 0.3)} />}
    </Frame>
  );
}

/** The frame scaled to a screen width. */
export function MotionStage({ plan, t, width }: { plan: MotionPlan; t: number; width: number }) {
  return <Fit width={width}><MotionFrame plan={plan} t={t} /></Fit>;
}
