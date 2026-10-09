// Lip-sync from our word timings (learning-shorts, not part of the
// characters lab). The lab's talkAction() times its mouth shapes for 150 wpm
// from the text alone; a reel already knows when every word was said
// (forced alignment on the Chatterbox audio, or the even split in stub mode),
// so here each word's visemes are laid inside THAT word's [start, end] and
// the lips close in the silences between words. Same shapes, same mouth
// channels and the same coarticulation rule as talk.ts; only the clock is
// ours. Pure: words in, one Action out.

import { CLOSED, MOUTH_CHANNEL, MOUTH_FIELDS, NOD, PARTED, SHAPES, STRESS_OPEN, visemesFor, type Mouth } from "../characters/actions/talk";
import type { Action, Ease, Tracks } from "../characters/rig/track";

export interface TimedWord { text: string; start: number; end: number; hl?: boolean }

const LEAD = 0.06;     // the lips part a moment before the first sound
const SETTLE = 0.22;   // and come back to rest after the last
const MIN = 0.05;      // the jaw never snaps: no two mouth keys closer than this
const EARLY = 0.3;     // a shape is reached this fraction of the previous one early
const PAUSE = 0.28;    // a silence this long closes the lips; a shorter one only parts them
const VOWELS = new Set(["A", "E", "I", "O", "U"]);

/** One caption's mouth, as an Action whose local time 0 is `t0` on the reel
 * clock (the clip starts at t0). Highlighted words get the stressed-syllable
 * head dip, the beat of emphasis. */
export function alignedTalk(words: TimedWord[], t0: number): Action {
  const tracks: Tracks = {};
  let lastKey = -Infinity;
  const key = (t: number, shape: Mouth, e: Ease = "inOut", force = false) => {
    if (!force && t - lastKey < MIN) return;
    const at = Math.max(t, lastKey + MIN);
    for (const f of MOUTH_FIELDS) (tracks[MOUTH_CHANNEL[f]] ??= []).push([at - t0, shape[f], e]);
    (tracks.headY ??= []).push([at - t0, shape.open * 2, e]);
    lastKey = at;
  };
  const nods: [number, number, Ease?][] = [];

  const first = words[0];
  if (!first) return { name: "talk", group: "talk", duration: 0.1, tracks };
  key(first.start - LEAD - MIN, CLOSED, "inOut", true);
  words.forEach((w, i) => {
    const letters = w.text.toLowerCase().replace(/[^a-z]/g, "");
    const vis = letters ? visemesFor(letters) : [];
    const span = Math.max(MIN, w.end - w.start);
    const total = vis.reduce((s, v) => s + v.dur, 0) || 1;
    let t = w.start;
    let prev = MIN;
    for (const v of vis) {
      const dur = (v.dur / total) * span;
      const shape = { ...SHAPES[v.shape] };
      if (v.stress) shape.open = Math.min(1, shape.open + STRESS_OPEN);
      key(t - EARLY * prev, shape, v.stress ? "out" : "inOut");
      if (v.stress && w.hl && VOWELS.has(v.shape)) {
        const n = t - t0;
        if (!nods.length || n - 0.3 > nods[nods.length - 1][0]) nods.push([n - 0.04, 0], [n + 0.08, NOD, "out"], [n + 0.26, 0, "inOut"]);
      }
      t += dur;
      prev = dur;
    }
    const next = words[i + 1];
    const gap = next ? next.start - w.end : Infinity;
    key(w.end - EARLY * prev, gap >= PAUSE ? CLOSED : PARTED);
  });
  const end = words[words.length - 1].end;
  key(end + SETTLE, CLOSED, "inOut", true);
  if (nods.length) tracks.headNod = nods;
  return { name: "talk", group: "talk", duration: end + SETTLE - t0, blendIn: 0.06, blendOut: SETTLE, tracks };
}
