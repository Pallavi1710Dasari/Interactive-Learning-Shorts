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
import { BOARD, bulbAt, placement, spotOf, teach } from "./teach";

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

/** The board staging (plan.stage = "board", cast/teach.ts): the explaining
 * character large beside the board, the asking one smaller below it, both
 * cut softly at the waist, teaching through the aim / gaze / jaw overlays,
 * a lightbulb on an "aha". No backdrop halo. */
export function BoardCharacters({ plan, t, opacity = 1 }: { plan: MotionPlan; t: number; opacity?: number }) {
  if (!plan.characters?.length) return null;
  const n = plan.characters.length;
  const spots = plan.characters.map((tr) => placement(spotOf(tr, n)));
  const heads = spots.map((p) => [p.left + 200 * p.scale, p.top + 120 * p.scale] as [number, number]);
  return (
    <div data-part="characters" style={{ position: "absolute", inset: 0, opacity, pointerEvents: "none" }}>
      <style>{"[data-character] > svg { overflow: visible; }"}</style>
      {plan.characters.map((track, i) => {
        const place = spots[i];
        const skin = skinFor(configOf(track));
        const base = { ...poseOf(performanceFor(plan, track), t) };
        const { pose, aha } = teach(base, track, place, skin, t, n > 1 ? heads[1 - i] : null);
        const visible = (BOARD.view_bottom - 6) * place.scale;
        const bulb = bulbAt(aha);
        return (
          <div key={`${track.side}:${track.role ?? ""}`}>
            <div data-character={track.preset} data-side={track.side}
                 style={{ position: "absolute", left: place.left, top: place.top + 6 * place.scale, width: place.w, height: visible,
                          overflow: "hidden",
                          WebkitMaskImage: "linear-gradient(to bottom, #000 82%, transparent 100%)",
                          maskImage: "linear-gradient(to bottom, #000 82%, transparent 100%)" }}>
              <div style={{ position: "absolute", left: 0, top: -6 * place.scale, width: place.w }}>
                <Character pose={pose} skin={skin} width={place.w} />
              </div>
            </div>
            {bulb.opacity > 0 && (
              <svg data-part="aha" width={120} height={150} viewBox="0 0 60 75"
                   style={{ position: "absolute", left: heads[i][0] - 60 + 70 * place.scale * (track.side === "left" ? 1 : -1),
                            top: place.top - 30 * place.scale - 40, opacity: bulb.opacity,
                            transform: `scale(${bulb.scale})`, transformOrigin: "50% 100%", overflow: "visible" }}>
                {[0, 1, 2, 3, 4].map((k) => {
                  const a = (-150 + k * 30) * Math.PI / 180;
                  return <line key={k} x1={30 + Math.cos(a) * 24} y1={26 + Math.sin(a) * 24} x2={30 + Math.cos(a) * (31 + 3 * bulb.glow)}
                               y2={26 + Math.sin(a) * (31 + 3 * bulb.glow)} stroke="#FFD43B" strokeWidth={3.5} strokeLinecap="round" />;
                })}
                <circle cx={30} cy={26} r={17} fill="#FFE066" stroke="#F2B705" strokeWidth={2.5} />
                <path d="M24 42 h12 v6 h-12 z M25 50 h10" stroke="#5B6178" strokeWidth={3} fill="#9AA0B8" strokeLinecap="round" />
                <path d="M26 28 q4 -7 8 0" stroke="#F2B705" strokeWidth={2} fill="none" />
              </svg>
            )}
          </div>
        );
      })}
    </div>
  );
}
