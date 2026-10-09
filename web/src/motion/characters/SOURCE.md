# Source of the animated characters

Arjun and Riya, with their rig and action library, are copied from another project. To update them, copy the same folders again from a newer commit, then reapply the local changes listed below.

| | |
|---|---|
| Repository | `Web-Slides` (local clone: `/home/nxtwave/Desktop/projects/Web-Slides`) |
| Branch | `lab/characters` |
| Folder | `slide-kit/characters-lab` |
| Commit | `d7d512d5569fabe8d2795de576566ad5c1cf8728` (2026-10-07 12:25 +0530) |
| Author | jeevansravanth |
| Copied | 2026-10-09, into `web/src/motion/characters/` of learning-shorts |

## What was copied

- `src/skins/` → `skins/`: `config.ts` (CharacterConfig, PRESETS for arjun and riya, buildSkin), `hair.tsx`, `outfits.tsx`, `types.ts`, `index.ts`.
- `src/rig/` → `rig/`: the channels, keyframe tracks, composer, idle and life layers, the SVG renderer (`Character.tsx`, `Body.tsx`, `Face.tsx`, `Arm.tsx`, `Hand.tsx`, `lighting.tsx`), and `useCharacter.ts` plus `Actor.tsx`. The Actor component is kept as it was for slide use; the reel player does not use it.
- `src/actions/` → `actions/`: every gesture, expression and hand pose, plus `talk.ts`.

## Left out

The playground (`src/playground/`, `src/App.tsx`, `src/main.tsx`, `src/index.css`), `shoot.mjs`, `record.mjs`, `match.mjs`, the lab's tests, the review material and reference images, and its package and config files. Nothing in the source repository was changed.

## Local changes to the copied files

1. **Imports.** Every `@/…` alias import is rewritten as a relative path, because our Vite config and test bundler have no `@` alias. The import targets are the same.
2. **`rig/Character.tsx`.** Two unused lines (`earScale`, `earX`) are removed, because our `tsc` (`noUnusedLocals`) rejects them. They were never drawn, so the output is the same. A comment marks the spot.
3. **`actions/talk.ts`.** `Mouth`, `SHAPES`, `PARTED`, `CLOSED`, `MOUTH_CHANNEL`, `MOUTH_FIELDS`, `NOD` and `STRESS_OPEN` are now exported, so `lipsync.ts` can reuse the lab's mouth shapes. Only the `export` keywords differ from the source.

## Our files, not from the lab

This folder holds only the copied `skins/`, `rig/` and `actions/`, plus this file. Our own code and data live elsewhere, so recopying the three folders can never overwrite them:

- `web/src/motion/cast/`: our code.
  - `performance.ts`: a character's whole reel performance as a pure function of time. It uses the lab's `composeAt` and `applyLife`. The lab's `<Actor time={t}>` is not pure: it starts a gesture or a line whenever its React effect runs.
  - `lipsync.ts`: mouth shapes timed from our caption word timings.
  - `ReelCharacters.tsx`: the optional layer in the 9:16 player.
  - `CharacterSheet.tsx` (`#motion/characters`) and `CharacterDesigner.tsx` (`#motion/characters/designer`).
  - `presets.ts` and `presets.generated.json`.
- `shorts/motion_character_presets.yaml`: the default presets (the host and one character per language), in the rig's CharacterConfig shape.
- `shorts/motion_character_presets.saved.yaml`: what the designer saved over the defaults.

## Updating

Recopy the three folders, then:

1. Rerun the import rewrite.
2. Reapply changes 2 and 3 above.
3. Run `npx tsc --noEmit`, `npm run test:motion` and `SHORTS_STUB=1 python -m shorts.motion_characters_test`. The TS test checks that every gesture and expression the reel director uses still exists in the rig.
4. Update the commit hash and date here.
