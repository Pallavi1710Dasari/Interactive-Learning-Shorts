import { useEffect, useMemo, useRef } from "react";
import type { CaptionWord } from "./types";

/**
 * The narration, revealed word by word under the voice that is speaking it.
 *
 * WHY WORDS AND NOT A BLOCK OF TEXT
 * A caption that appears complete is read in one glance, which puts the viewer
 * ahead of the narrator and then bored for the rest of the beat. Revealing it in
 * step with the voice keeps reading and listening on the same word, and it is the
 * single cheapest thing that makes a short feel produced rather than assembled.
 *
 * Every word has three states and they are all visible at once:
 *   spoken    — said already: full weight, so the sentence so far can be re-read
 *   current   — being said now: the accent colour, lifted
 *   upcoming  — not yet said: dim but present, so the line does not reflow as it
 *               fills. Words appearing one at a time made the whole bubble jump
 *               on every word, which is far more distracting than a dim word.
 *
 * Timings come from the server (shorts/feed.py) so the same numbers drive this
 * whether the voice is a recorded track or the browser's synthesiser.
 */
export function FlowingCaption({ line, words, time, speaker }: {
  line: string;
  words: CaptionWord[] | undefined;
  /** Position of the narration, in seconds from the start of the short. */
  time: number;
  speaker: "interviewer" | "student";
}) {
  // No timings (an older unit, or a payload from before feed.py grew them) still
  // has to render: fall back to the plain sentence rather than an empty bubble.
  const items = useMemo<CaptionWord[]>(() => {
    if (words && words.length) return words;
    return line.split(/\s+/).filter(Boolean).map((w) => ({ w, s: -1, e: -1 }));
  }, [words, line]);

  const untimed = items.length > 0 && items[0].s < 0;
  const spokenTo = untimed
    ? items.length
    : items.findIndex((word) => time < word.e);
  // findIndex returns -1 once the whole line is behind us, which is "all spoken".
  const cursor = spokenTo === -1 ? items.length : spokenTo;

  // Keep the word being spoken in view when a long line wraps past the bubble.
  const box = useRef<HTMLParagraphElement | null>(null);
  const live = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    const el = live.current;
    const wrap = box.current;
    if (!el || !wrap) return;
    const top = el.offsetTop;
    if (top < wrap.scrollTop || top > wrap.scrollTop + wrap.clientHeight - el.offsetHeight)
      wrap.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
  }, [cursor]);

  return (
    <p className={`flow ${speaker}`} ref={box} aria-label={line}>
      {items.map((word, i) => {
        const state = untimed ? "said" : i < cursor ? "said" : i === cursor ? "now" : "next";
        return (
          <span
            key={i}
            ref={state === "now" ? live : undefined}
            className={`word ${state}`}
          >
            {word.w}{" "}
          </span>
        );
      })}
    </p>
  );
}
