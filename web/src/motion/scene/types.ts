// The player's input — the TypeScript mirror of shorts/schema.py's MotionPlan
// (output/<short_id>/plan.json, written by the motion runner's timing stage).
// Python resolves every cue to seconds and lays every object out; the player
// only draws, so it is a pure function of (plan, t).

import type { CastMember, IdentitySpec } from "../identity/Identity";
import type { CharacterTrack } from "../cast/performance";
import type { FieldName } from "../tokens";

export interface PlanWord { text: string; start: number; end: number; hl: boolean }
export interface PlanCaption {
  text: string; speaker: string | null; start: number; end: number; words: PlanWord[];
  source: "forced_alignment" | "whisper" | "even";
}
export interface PlanAction { t: number; do: string; target: string; value?: string | null; tone?: string | null; cue: string }
export interface PlanBox { x: number; y: number; w: number; h: number }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Props = Record<string, any>;
export interface PlanObject { id: string; kind: string; props: Props; box: PlanBox | null }
export interface PlanShot {
  id: string; beat: string; chapter: number | null; start: number; end: number;
  field: FieldName; transition: string; label: string; layout: "solo" | "duo";
  /** the animated characters show on this shot (absent in older plans) */
  characters?: boolean;
  objects: PlanObject[]; actions: PlanAction[]; captions: PlanCaption[];
}
export type PlanCast = CastMember;
export interface MotionPlan {
  short_id: string; template: string; theme: string | null; series: string; concept_name: string;
  duration: number; audio: string | null; audio_url?: string; timing_source: string;
  identity: IdentitySpec | null; theme_label: string; tags: string[]; intro: number;
  cast: PlanCast[]; shots: PlanShot[];
  /** the optional animated characters (shorts/motion_characters.py); empty = off */
  characters: CharacterTrack[];
}
