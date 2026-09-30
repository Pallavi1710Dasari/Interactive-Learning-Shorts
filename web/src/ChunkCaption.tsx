import { useMemo } from "react";
import { buildCaptionChunks, chunkAt } from "./captionChunking";
import type { CaptionWord } from "./types";

/**
 * Story mode's caption — RESTYLE_TO_STORY_REELS.md Step 8 Part 3.
 *
 * Deliberately NOT FlowingCaption (explainer mode's own word-by-word
 * highlighted caption, web/src/FlowingCaption.tsx): the spec here is a
 * plain subtitle box that SWAPS between 3-5-word chunks on real timing,
 * with no per-word highlight state — a simpler, different visual language
 * for a different mode, not a shared component with a flag.
 *
 * `time` is the SAME absolute-seconds-from-reel-start clock every other
 * story-mode prop already uses (see StoryStage) — this component does not
 * re-derive or offset it.
 *
 * Renders nothing (null) for a shot with no line at all (text_card/recap/
 * cta) — the caller (StoryStage) already only mounts this for `kind ===
 * "scene"` shots, but this is a second, cheap guarantee against an empty
 * caption box ever flashing on screen.
 */
export function ChunkCaption({ line, words, time }: {
  line: string;
  words: CaptionWord[] | undefined;
  time: number;
}) {
  const chunks = useMemo(() => {
    const items = words && words.length ? words
      : (line || "").split(/\s+/).filter(Boolean).map((w) => ({ w, s: -1, e: -1 }));
    return buildCaptionChunks(items);
  }, [words, line]);

  if (!chunks.length) return null;
  const current = chunks[0].start < 0 ? chunks[chunks.length - 1] : chunkAt(chunks, time);
  if (!current) return null;

  return (
    <div className="chunk-caption">
      <p>{current.text}</p>
    </div>
  );
}
