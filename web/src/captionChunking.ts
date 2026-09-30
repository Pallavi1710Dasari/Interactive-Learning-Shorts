// RESTYLE_TO_STORY_REELS.md Step 8 Part 3 — pure caption-chunking logic,
// kept in its own non-JSX module so it can be run and tested directly with
// plain `node` (Node 24's native TypeScript stripping does not handle JSX,
// so a .tsx file can't be executed this way — see captionChunking.test.ts).
//
// ChunkCaption.tsx imports this; nothing in this file touches React.

import type { CaptionWord } from "./types";

/**
 * Split `words` into balanced runs of 3-5 words each — RESTYLE_TO_STORY_
 * REELS.md's own caption rule. Balanced, not "take 5 until none are left":
 * a naive greedy split leaves a straggler final chunk (e.g. 5,5,5,1), which
 * both looks wrong on screen and violates the 3-5 rule on its own last
 * chunk. This instead picks the number of chunks first (ceil(n / maxSize))
 * and spreads `words` as evenly as possible across them, so every chunk
 * from a line long enough to need more than one lands inside [minSize,
 * maxSize] — the only exception is a line with FEWER than minSize words
 * total, which is left as its own single (necessarily short) chunk since
 * there is nothing to balance it against.
 */
export function chunkWords(words: CaptionWord[], minSize = 3, maxSize = 5): CaptionWord[][] {
  if (!words.length) return [];
  const n = words.length;
  if (n <= maxSize) return [words];

  const numChunks = Math.ceil(n / maxSize);
  const base = Math.floor(n / numChunks);
  const remainder = n % numChunks;
  const chunks: CaptionWord[][] = [];
  let i = 0;
  for (let c = 0; c < numChunks; c++) {
    const size = base + (c < remainder ? 1 : 0);
    chunks.push(words.slice(i, i + size));
    i += size;
  }
  return chunks;
}

export type CaptionChunk = { text: string; start: number; end: number };

/** `chunkWords`'s groups, turned into displayable {text, start, end} runs —
 *  start/end taken from the group's own first/last word timings (real
 *  measured timings, not re-derived), so a chunk's own on-screen window is
 *  exactly the union of its words' spoken spans. */
export function buildCaptionChunks(words: CaptionWord[]): CaptionChunk[] {
  return chunkWords(words).map((group) => ({
    text: group.map((w) => w.w).join(" "),
    start: group[0].s,
    end: group[group.length - 1].e,
  }));
}

/** The chunk that should be on screen at `time` (absolute seconds from the
 *  reel's start) — clamped to the first chunk before its own start and the
 *  last chunk after its own end, so there is never a blank gap mid-shot
 *  (a capture running exactly AT a boundary must still show something). */
export function chunkAt(chunks: CaptionChunk[], time: number): CaptionChunk | null {
  if (!chunks.length) return null;
  if (time < chunks[0].start) return chunks[0];
  const found = chunks.findIndex((c) => time < c.end);
  return found === -1 ? chunks[chunks.length - 1] : chunks[found];
}
