// A character's whole performance in a reel, as a pure function of time
// (learning-shorts, not part of the characters lab).
//
// The lab's <Actor time={t}> is not pure: it starts a gesture or a line of
// speech at whatever moment its React effect runs, inside a stateful
// useCharacter() clock. A reel needs the same frame for the same t however
// the player got there (play, scrub, capture), so here every clip is laid on
// the reel's clock up front, from the plan:
//
//   gestures and expressions — the director's cues (plan.characters), each
//                              starting on its spoken word;
//   talk                      — one aligned clip per caption this role speaks
//                              (lipsync.ts, from the word timings).
//
// At any instant the lab's own composer (composeAt) gets the clips active
// at that instant, and the lab's life layer (applyLife: springs, lag,
// drift, hair and cloth) runs on top. Both are pure in (key, t), so the pose
// at t is fixed.

import { ACTIONS, EXPRESSIONS } from "../characters/actions";
import { composeAt, type Clip, type Timeline } from "../characters/rig/compose";
import { applyLife } from "../characters/rig/life";
import { mirror } from "../characters/rig/track";
import type { Pose } from "../characters/rig/channels";
import { alignedTalk, type TimedWord } from "./lipsync";
import type { CharacterConfig } from "../characters/skins/config";

export interface CharacterCue {
  t: number; kind: "gesture" | "expression" | "aim" | "gaze" | "aha" | "count"; name: string; side?: "L" | "R" | null; cue: string;
  /** aim / gaze (cast/teach.ts): when it lets go, what it looks or points at */
  until?: number | null; rect?: number[] | null; target?: string | null; full?: boolean | string;
}
/** One character in a plan (schema.MotionCharacterTrack): its preset id and
 * the rig CharacterConfig it was built with, where it stands, and its cues.
 * role is null for a one-narrator reel's narrator. */
export interface CharacterTrack {
  role: string | null; preset: string; config: CharacterConfig; side: "left" | "right" | "center";
  seed: number; cues: CharacterCue[];
}
export interface SpokenLine { speaker: string | null; words: TimedWord[] }

/** Everything one character does, on the reel clock. The object itself is
 * the life layer's cache key, so keep one per (plan, role). */
export interface Performance { seed: number; gestures: Clip[]; expressions: Clip[]; talks: Clip[] }

const LEAD = 0.11;

export function buildPerformance(track: Pick<CharacterTrack, "seed" | "cues" | "role">, lines: SpokenLine[]): Performance {
  const gestures: Clip[] = [];
  const expressions: Clip[] = [];
  for (const c of [...track.cues].sort((a, b) => a.t - b.t)) {
    if (c.kind === "gesture") {
      const base = ACTIONS[c.name];
      if (base) gestures.push({ action: c.side === "R" ? mirror(base) : base, start: c.t });
    } else {
      const base = EXPRESSIONS[c.name];
      if (base) expressions.push({ action: base, start: c.t });
    }
  }
  const talks: Clip[] = lines
    .filter((l) => (l.speaker ?? null) === (track.role ?? null) && l.words.length)
    .map((l) => {
      const t0 = l.words[0].start - LEAD;
      return { action: alignedTalk(l.words, t0), start: t0 };
    })
    .sort((a, b) => a.start - b.start);
  return { seed: track.seed, gestures, expressions, talks };
}

/** The index of the last clip started by t, or -1. */
function lastStarted(clips: Clip[], t: number): number {
  let lo = 0, hi = clips.length - 1, out = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (clips[mid].start <= t) { out = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return out;
}

/** The lab's Timeline at one instant: the current and previous gesture (the
 * previous one blending out as the new one starts), the current and previous
 * expression (cross-faded), and the line being spoken. */
export function timelineAt(p: Performance, t: number): Timeline {
  const tl: Timeline = { seed: p.seed, idle: {}, life: 0 };
  const g = lastStarted(p.gestures, t);
  if (g >= 0) {
    tl.gesture = p.gestures[g];
    if (g > 0) tl.prevGesture = { ...p.gestures[g - 1], stopAt: Math.min(p.gestures[g - 1].stopAt ?? Infinity, p.gestures[g].start) };
  }
  const e = lastStarted(p.expressions, t);
  if (e >= 0) {
    tl.expression = p.expressions[e];
    if (e > 0) tl.prevExpression = p.expressions[e - 1];
  }
  const k = lastStarted(p.talks, t);
  if (k >= 0) tl.talk = p.talks[k];
  return tl;
}

/** The pose at t: pure, the same t gives the same pose. */
export function poseOf(p: Performance, t: number): Pose {
  return applyLife(p, Math.max(0, t), (tt) => composeAt(timelineAt(p, tt), tt), {});
}
