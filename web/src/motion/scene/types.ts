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
  /** the virtual camera's framings (shorts/motion_camera.py); absent = none */
  camera?: CameraCue[];
  /** the virtual cursor's moves (shorts/motion_camera.py); absent = none */
  cursor?: CursorCue[];
  /** a VIDEO's shot (shorts/motion_video.py): the reel-layout region src it
   *  is drawn from, into dst on the 1920x1080 frame, at scale s */
  view?: PlanView | null;
}
export interface PlanView { src: Rect; dst: Rect; s: number }
export type Rect = [number, number, number, number];
export interface CameraCue { t0: number; t1: number; target: string; part: number | null; rect: Rect; zoom: number; viewport: Rect; why?: string }
export interface CursorCue { t: number; do: "click" | "type"; target: string; part: number | null; rect: Rect; text?: string; t_end?: number }
export type PlanCast = CastMember;
export interface MotionPlan {
  /** "video": a long-form landscape video (1920x1080, web/src/motion/video);
   *  absent or "reel": a vertical reel (1080x1920) */
  format?: "reel" | "video";
  width?: number;
  height?: number;
  /** The look it is drawn in (designs.ts); absent = "classic". */
  design?: string;
  /** The layout rules it is drawn by (shorts/schema.py MotionPlan.rev); absent = 1. */
  rev?: number;
  /** "board": the visual as a board, the explaining character large beside it (cast/teach.ts) */
  stage?: string | null;
  /** the studio palette it is drawn in (library.json studio.palettes); rev 3 */
  palette?: string | null;
  /** "vrm": the characters as 3D VRM avatars (vrm/VrmCast.tsx); absent = the 2D rig */
  avatars?: string | null;
  short_id: string; template: string; theme: string | null; series: string; concept_name: string;
  duration: number; audio: string | null; audio_url?: string; timing_source: string;
  /** "stub": the narration is stub silence (SHORTS_STUB=1); "recorded": a real
   *  voice; "none": no audio. Set by GET /api/motion/<id>/plan. */
  voice?: "stub" | "recorded" | "none";
  identity: IdentitySpec | null; theme_label: string; tags: string[]; intro: number;
  cast: PlanCast[]; shots: PlanShot[];
  /** the optional animated characters (shorts/motion_characters.py); empty = off */
  characters: CharacterTrack[];
}
