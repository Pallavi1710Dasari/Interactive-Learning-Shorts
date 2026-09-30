// RESTYLE_TO_STORY_REELS.md Step 8 Part 3 VERIFY: caption chunking must
// produce 3-5 word chunks (max 2 lines is a CSS/layout concern, verified by
// eye in the actual capture, not here). Plain `node`, no test framework —
// this project has none for the web/ side (see web/package.json); Node 24's
// native TypeScript stripping runs this file directly:
//
//     node web/src/captionChunking.test.ts
//
// This file itself is NOT part of the Vite build (see vite.config.ts's own
// include, or the absence of any reference to it) — a *.test.ts is not
// imported by anything the app ships.
// .ts extensions here ON PURPOSE, unlike every other import in this
// project: plain `node` (unlike Vite's bundler resolution) requires an
// explicit extension for a relative ESM import, and this file is only ever
// run directly with `node`, never bundled (see the module docstring above).
import { buildCaptionChunks, chunkAt, chunkWords } from "./captionChunking.ts";
import type { CaptionWord } from "./types.ts";

let failures = 0;

function assert(cond: boolean, msg: string): void {
  if (!cond) {
    failures++;
    console.error(`  FAIL: ${msg}`);
  } else {
    console.log(`  ok: ${msg}`);
  }
}

function words(...texts: string[]): CaptionWord[] {
  // 0.4s per word, back to back — real timings are never exactly this even
  // in practice (see story_audio.py's own whisper-based real timing), but
  // the chunking logic only cares about word COUNT and ORDER, not spacing.
  return texts.map((w, i) => ({ w, s: i * 0.4, e: (i + 1) * 0.4 }));
}

// ------------------------------------------------------------ chunkWords

{
  const w = words("a", "b", "c");
  assert(chunkWords(w).length === 1, "3 words -> 1 chunk");
  assert(chunkWords(w)[0].length === 3, "that chunk has all 3 words");
}

{
  const w = words("a", "b", "c", "d", "e");
  const chunks = chunkWords(w);
  assert(chunks.length === 1 && chunks[0].length === 5, "5 words -> 1 chunk of 5 (the max)");
}

{
  const w = words("a", "b", "c", "d", "e", "f");
  const chunks = chunkWords(w);
  assert(chunks.length === 2, "6 words -> 2 chunks, not a 5+1 straggler");
  assert(chunks.every((c) => c.length >= 3 && c.length <= 5),
        `every chunk is within [3,5]: ${chunks.map((c) => c.length)}`);
  assert(chunks.reduce((n, c) => n + c.length, 0) === 6, "no word lost or duplicated");
}

{
  // A long narration line — this project's SHOT_MAX_LINE_WORDS caps a
  // spoken line around 18-20 words; 17 is a realistic worst case.
  const w = words(..."the quick brown fox jumps over the lazy dog again and again until it finally".split(" "));
  const chunks = chunkWords(w);
  assert(chunks.every((c) => c.length >= 3 && c.length <= 5),
        `a realistic long line's chunks are all within [3,5]: ${chunks.map((c) => c.length)}`);
  assert(chunks.reduce((n, c) => n + c.length, 0) === w.length,
        "every word from a long line appears in exactly one chunk");
}

{
  const w = words("hi");
  const chunks = chunkWords(w);
  assert(chunks.length === 1 && chunks[0].length === 1,
        "a line shorter than the minimum (1 word) is its own chunk, not padded or dropped");
}

{
  assert(chunkWords([]).length === 0, "no words -> no chunks");
}

// ------------------------------------------------------------- buildCaptionChunks

{
  const w = words("five", "clicks", "still", "zero");
  const chunks = buildCaptionChunks(w);
  assert(chunks.length === 1, "4 words stay one chunk");
  assert(chunks[0].text === "five clicks still zero",
        `chunk text is the joined words: ${JSON.stringify(chunks[0].text)}`);
  assert(chunks[0].start === 0 && chunks[0].end === 1.6,
        `chunk start/end come from its first/last word's REAL timing: ${chunks[0].start}-${chunks[0].end}`);
}

// ------------------------------------------------------------------- chunkAt

{
  const w = words(..."one two three four five six seven eight nine".split(" "));
  const chunks = buildCaptionChunks(w);   // 9 words -> 2 chunks of 4,5 (or similar split)
  assert(chunkAt(chunks, -1) === chunks[0], "before the first chunk's start -> the first chunk (never blank)");
  assert(chunkAt(chunks, 999) === chunks[chunks.length - 1],
        "after every chunk has ended -> the last chunk (never blank)");
  const mid = (chunks[0].start + chunks[0].end) / 2;
  assert(chunkAt(chunks, mid) === chunks[0], "a time inside the first chunk's span -> that chunk");
  assert(chunkAt([], 0) === null, "no chunks at all -> null, never throws");
}

if (failures > 0) {
  console.error(`\n${failures} FAILURE(S)`);
  process.exit(1);
}
console.log("\nALL CAPTION CHUNKING TESTS PASSED.");
