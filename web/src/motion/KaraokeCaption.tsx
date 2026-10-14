// Karaoke captions — REFERENCE_STYLE_ADDENDUM.md section 4.4. One spoken
// sentence at a time, bottom-left in the 70-80 % band, no background pill.
// Words already spoken are full ink, words still to come are dimmed to 35 %,
// and 1-2 <b> keywords per sentence take the field's accent colour.
//
// Word timings come from faster-whisper in phase 3. Until then evenWords()
// spreads a sentence's words over its span, the same approximation
// story_audio._even_words falls back to.

import { FONT, SAFE, W, theme, type FieldName, LOOK, C } from "./tokens";
import { clamp } from "./time";

export interface CaptionWord { text: string; start: number; end: number; hl: boolean }
export interface CaptionSentence { words: CaptionWord[]; start: number; end: number }

/** Split "<b>Tokenization</b> matters." into words, keeping which are highlighted. */
export function parseCaption(text: string): { text: string; hl: boolean }[] {
  const out: { text: string; hl: boolean }[] = [];
  let hl = false;
  let lastChar = " ";   // the last character of real text seen, tags skipped
  for (const part of text.split(/(<\/?b>)/)) {
    if (part === "<b>") { hl = true; continue; }
    if (part === "</b>") { hl = false; continue; }
    if (!part) continue;
    part.split(/\s+/).forEach((w, i) => {
      if (!w) return;
      // Text touching the previous word across a tag ("vocabulary</b>.")
      // belongs to that word, so it renders "vocabulary." not "vocabulary ."
      if (i === 0 && out.length && !/\s/.test(lastChar) && !/^\s/.test(part)) out[out.length - 1].text += w;
      else out.push({ text: w, hl });
    });
    lastChar = part[part.length - 1];
  }
  return out;
}

/** A sentence's words spread evenly over [start, end]. */
export function evenWords(text: string, start: number, end: number): CaptionSentence {
  const parsed = parseCaption(text);
  const step = (end - start) / Math.max(1, parsed.length);
  return {
    start, end,
    words: parsed.map((w, i) => ({ ...w, start: start + i * step, end: start + (i + 1) * step })),
  };
}

/** A word as it is shown: markdown code ticks dropped ("`count`" -> "count"). */
export function plainWord(text: string): string {
  return text.replace(/`/g, "");
}

/** The sentence on screen at t: the last one that has started. */
export function sentenceAt(sentences: CaptionSentence[], t: number): CaptionSentence | null {
  let cur: CaptionSentence | null = null;
  for (const s of sentences) if (t >= s.start - 0.05) cur = s;
  return cur;
}

export function KaraokeCaption({ sentences, t, field, size = 56 }: {
  sentences: CaptionSentence[]; t: number; field: FieldName; size?: number;
}) {
  const th = theme(field);
  const s = sentenceAt(sentences, t);
  if (!s) return null;
  return (
    <div style={{ position: "absolute", left: SAFE.side, width: W - SAFE.side * 2, top: SAFE.captionTop,
                  height: SAFE.captionBottom - SAFE.captionTop, display: "flex", alignItems: "flex-end" }}>
      <div style={{ fontFamily: FONT.body, fontWeight: 800, fontSize: size, lineHeight: 1.22, letterSpacing: -0.3,
                    maxWidth: "100%" }}>
        {s.words.map((w, i) => {
          // A word lights the moment it starts and fully by a third of its span.
          const lit = clamp((t - w.start) / Math.max(0.05, (w.end - w.start) / 3));
          const color = w.hl ? th.accent : th.ink;
          // the studio marks a key word with a highlighter stroke that sweeps under it as it is said
          const marker = LOOK.studio && w.hl
            ? { color: th.ink, backgroundImage: `linear-gradient(transparent 52%, ${C.yellow}${th.dark ? "66" : "99"} 52%, ${C.yellow}${th.dark ? "66" : "99"} 92%, transparent 92%)`,
                backgroundSize: `${lit * 100}% 100%`, backgroundRepeat: "no-repeat" }
            : {};
          return (
            <span key={i} style={{ color, opacity: 0.35 + 0.65 * lit, textShadow: w.hl && !LOOK.studio ? "var(--motion-glow, none)" : undefined, ...marker }}>
              {plainWord(w.text)}{i < s.words.length - 1 ? " " : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
}
