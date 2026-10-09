// The optional character layer of a motion reel (learning-shorts). As many
// characters as speakers: the host (left) and the language character (right)
// of a two-speaker reel, or the language character alone (centre) narrating
// a one-narrator reel. Upper body, in their own region of the 9:16 frame
// (library.json frame.characters) between the scene objects and the chat or
// captions, so they never cover either; the plan says per shot whether they
// show (MotionShotPlan.characters: never on a full-frame card).
//
// Who each one is comes from the plan (track.config, the preset as it was
// when the reel was made). Pure in t: every pose comes from performance.ts.

import { Character } from "../characters/rig/Character";
import { buildSkin, PRESETS, type CharacterConfig } from "../characters/skins/config";
import type { Skin } from "../characters/skins/types";
import { buildPerformance, poseOf, type CharacterTrack, type Performance } from "./performance";
import library from "../library.json";
import type { MotionPlan, PlanShot } from "../scene/types";
import { FULL_KINDS } from "../scene/objects";
import { theme, type FieldName } from "../tokens";

export const STAGE = (library as unknown as {
  frame: { characters: { top: number; bottom: number; chat_top: number; view: { top: number; bottom: number }; cx: number[]; center_x: number } }
}).frame.characters;

/** The rig's viewBox is 400 x 600; the reel shows the band view.top..view.bottom
 * of it (the hair to just below the hands at rest) scaled to the region. */
export const SCALE = (STAGE.bottom - STAGE.top) / (STAGE.view.bottom - STAGE.view.top);
export const CHAR_W = Math.round(400 * SCALE);

const SKINS = new Map<string, Skin>();
/** The skin a config builds, memoised by the config's JSON. */
export function skinFor(config: CharacterConfig): Skin {
  const key = JSON.stringify(config);
  let s = SKINS.get(key);
  if (!s) SKINS.set(key, (s = buildSkin(config)));
  return s;
}

/** A track's config (plans before presets named "arjun" / "riya" instead). */
function configOf(track: CharacterTrack): CharacterConfig {
  const legacy = (track as unknown as { character?: "arjun" | "riya" }).character;
  return track.config ?? PRESETS[legacy ?? "arjun"];
}

const CACHE = new WeakMap<MotionPlan, Map<string, Performance>>();
/** One performance per (plan, track), kept so the life layer can continue
 * from the last frame instead of starting over. */
export function performanceFor(plan: MotionPlan, track: CharacterTrack): Performance {
  let m = CACHE.get(plan);
  if (!m) CACHE.set(plan, (m = new Map()));
  const key = `${track.side}:${track.role ?? ""}`;
  let p = m.get(key);
  if (!p) {
    const lines = plan.shots.flatMap((s) => s.captions.map((c) => ({ speaker: c.speaker, words: c.words })));
    m.set(key, (p = buildPerformance(track, lines)));
  }
  return p;
}

/** Whether the layer shows on a shot. */
export function charactersOn(plan: MotionPlan, shot: PlanShot): boolean {
  if (!plan.characters?.length) return false;
  if (typeof shot.characters === "boolean") return shot.characters;
  return shot.layout === "duo" && !shot.objects.some((o) => FULL_KINDS.has(o.kind));   // older plans
}

function centreX(side: CharacterTrack["side"]): number {
  return side === "center" ? STAGE.center_x : STAGE.cx[side === "left" ? 0 : 1];
}

/** A soft round backdrop behind a character's upper body, so light clothes
 * (a white shirt on paper) and dark ones (navy trousers on navy) still read:
 * a navy tint on the light fields, a light one on the dark. Static. */
export function Backdrop({ field, cx, size }: { field: FieldName; cx: number; size: number }) {
  const tint = theme(field).dark ? "rgba(255,255,255,0.075)" : "rgba(21,25,54,0.085)";
  return (
    /* a "circle" gradient measures its stops to the box's corner (0.707 of
       the side), so the 71 % stop is the box's inscribed circle: a box as tall
       as the region (less a margin) fades out before either edge, never cut */
    <div data-part="backdrop" style={{ position: "absolute", left: cx - size / 2, top: (STAGE.bottom - STAGE.top - size) / 2,
                                       width: size, height: size, borderRadius: "50%",
                                       background: `radial-gradient(circle, ${tint} 0%, ${tint} 58%, rgba(0,0,0,0) 71%)` }} />
  );
}

/** The characters at t. Two speakers each turn a little toward the other, so
 * they read as talking to each other; a narrator faces the viewer. */
export function ReelCharacters({ plan, t, opacity = 1, field = "navy" }: { plan: MotionPlan; t: number; opacity?: number; field?: FieldName }) {
  if (!plan.characters?.length) return null;
  const h = STAGE.bottom - STAGE.top;
  return (
    <div data-part="characters" style={{ position: "absolute", left: 0, top: STAGE.top, width: 1080, height: h, overflow: "hidden", opacity }}>
      {/* a wide gesture (a shrug, a spread) reaches past the rig's 400-wide
          viewBox; let it, the region above still bounds the layer */}
      <style>{"[data-character] > svg { overflow: visible; }"}</style>
      {plan.characters.map((track) => <Backdrop key={`b${track.side}`} field={field} cx={centreX(track.side)} size={STAGE.bottom - STAGE.top - 8} />)}
      {plan.characters.map((track) => {
        const pose = { ...poseOf(performanceFor(plan, track), t) };
        const toward = track.side === "left" ? 1 : track.side === "right" ? -1 : 0;
        pose.headTurn += 0.14 * toward;
        pose.lookX += 0.35 * toward;
        return (
          <div key={`${track.side}:${track.role ?? ""}`} data-character={track.preset} data-side={track.side}
               style={{ position: "absolute", left: centreX(track.side) - CHAR_W / 2, top: -STAGE.view.top * SCALE, width: CHAR_W }}>
            <Character pose={pose} skin={skinFor(configOf(track))} width={CHAR_W} />
          </div>
        );
      })}
    </div>
  );
}
