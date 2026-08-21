/**
 * Making browser speech sound less like a machine reading a paragraph.
 *
 * Two things make TTS read as robotic, and neither is the voice engine:
 *
 *   1. One utterance per beat. A 28-word block handed to the engine in one piece
 *      comes back at one pitch, one speed, with no phrasing — the engine has no
 *      reason to breathe where a person would. Splitting on clause boundaries and
 *      speaking the pieces back to back gives the phrasing back, because each
 *      piece gets its own sentence-final intonation.
 *   2. A constant pitch. The old code offset the two speakers by ±0.1 pitch and
 *      held each one flat for the whole short, which is exactly the giveaway —
 *      real speech drifts. Small per-phrase variation, derived from the text so it
 *      is stable across replays, reads as natural where a fixed value does not.
 *
 * Notation is also spoken here. "2^3" read literally is "two caret three", which
 * is not what the diagram says and not what a teacher would say out loud.
 */

/** Written notation -> what a person would say. Order matters; longest first. */
const SPOKEN: [RegExp, string][] = [
  [/(\d+)\s*\^\s*(\d+)/g, "$1 to the power of $2"],
  [/(\d+)\s*\*\s*(\d+)/g, "$1 times $2"],
  [/\s*->\s*/g, " leads to "],
  [/\s*=>\s*/g, " gives "],
  [/\s*!=\s*/g, " is not equal to "],
  [/\s*>=\s*/g, " is at least "],
  [/\s*<=\s*/g, " is at most "],
  [/\s*=\s*/g, " equals "],
  [/\be\.g\.\s*/gi, "for example, "],
  [/\bi\.e\.\s*/gi, "that is, "],
  [/\betc\.\s*/gi, "and so on. "],
  [/\bvs\.?\s/gi, "versus "],
  [/\s*&\s*/g, " and "],
  [/\s*\/\s*/g, " or "],
  [/\b2\s*\^\s*n\b/gi, "two to the power of n"],
];

export function forSpeech(text: string): string {
  let out = text;
  for (const [re, to] of SPOKEN) out = out.replace(re, to);
  // An em dash is a spoken pause. Left as a dash the engine runs straight
  // through it; as a comma it gets the breath the writer intended.
  out = out.replace(/\s*[—–]\s*/g, ", ");
  return out.replace(/\s+/g, " ").trim();
}

/**
 * Split a spoken line into phrases the engine can intone one at a time.
 *
 * Sentence ends first, then clause boundaries, and only long leftovers are broken
 * at a comma — splitting every comma chops the line into a staccato list, which
 * trades one unnatural reading for another.
 */
const MAX_PHRASE_WORDS = 12;
const MIN_PHRASE_WORDS = 4;

export function phrases(line: string): string[] {
  const spoken = forSpeech(line);
  const sentences = spoken.match(/[^.!?]+[.!?]*/g) ?? [spoken];

  const out: string[] = [];
  for (const sentence of sentences) {
    const s = sentence.trim();
    if (!s) continue;
    if (words(s) <= MAX_PHRASE_WORDS) {
      out.push(s);
      continue;
    }
    // Too long to say in one breath. Break at commas and conjunctions, then glue
    // any runt back onto its neighbour so nothing is spoken as a two-word stub.
    // Multi-word connectives first — the alternation is ordered, and a bare
    // "though" matches inside "even though", splitting the phrase mid-conjunction.
    // Kept in step with shorts/speech.py, which uses the same list.
    const parts = s
      .split(/,\s*|\s+(?=(?:even though|and then|but|so|because|which|instead|while|whereas)\b)/i)
      .map((p) => p.trim()).filter(Boolean);
    for (const part of parts) {
      const prev = out[out.length - 1];
      if (prev && words(part) < MIN_PHRASE_WORDS) out[out.length - 1] = `${prev}, ${part}`;
      else out.push(part);
    }
  }
  // Give every phrase sentence-final punctuation, or the engine runs the queue
  // together into one flat line and the phrasing work is wasted.
  return out.map((p) => (/[.!?,]$/.test(p) ? p : `${p},`));
}

const words = (s: string) => s.trim().split(/\s+/).length;

/**
 * A stable pseudo-random number in [0,1) from a string.
 *
 * Deliberately not Math.random(): the same phrase must be spoken the same way on
 * a replay, or re-watching a short sounds like a different take every time.
 */
export function jitter(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 1000;
}

export type VoiceProfile = { rate: number; pitch: number };

/**
 * Per-speaker delivery, plus per-phrase drift.
 *
 * The interviewer asks, so a touch quicker and brighter; the student explains, so
 * a touch slower. The drift is ±0.04 — enough that consecutive phrases are not
 * identical, small enough that it never sounds like a pitch effect.
 */
export function profile(
  speaker: "interviewer" | "student", phrase: string, rate: number,
): VoiceProfile {
  const drift = (jitter(phrase) - 0.5) * 0.08;
  const asking = speaker === "interviewer";
  return {
    rate: clamp(rate * (asking ? 1.04 : 0.98) + drift * 0.5, 0.5, 2),
    pitch: clamp((asking ? 1.04 : 0.96) + drift, 0.5, 1.6),
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Rank the installed voices, best first.
 *
 * What "best" means is engine quality, and the name is the only clue the Web
 * Speech API gives. Chrome's "Google …" voices are server-side neural and by far
 * the most human thing available without an API key; Microsoft's Natural voices
 * are next; mbrola is diphone-concatenative and merely tolerable; raw espeak is
 * the floor. localService=false is a useful tiebreak because it means the audio
 * came from a server rather than a formant synthesiser on the box.
 */
const TIERS: RegExp[] = [
  /neural|natural/i,
  /\bgoogle\b/i,
  /\bmicrosoft\b/i,
  /premium|enhanced|siri|samantha|daniel|karen|moira/i,
  /mbrola/i,
];

export function rank(v: SpeechSynthesisVoice): number {
  const tier = TIERS.findIndex((re) => re.test(v.name));
  const base = tier === -1 ? TIERS.length : tier;
  return base * 2 + (v.localService ? 1 : 0);
}

/**
 * Two English voices that sound like two different people.
 *
 * Preferring a different-gendered second pick matters more than its rank: two
 * high-quality voices of the same gender still read as one person talking to
 * themselves, which defeats the interview format.
 */
const FEMALE = /female|samantha|karen|moira|zira|susan|victoria|serena|\bf\d|women/i;
const MALE = /male|daniel|alex|fred|david|mark|thomas|\bm\d|\bman\b/i;

export function pickVoices(voices: SpeechSynthesisVoice[]) {
  const en = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = [...(en.length ? en : voices)].sort((a, b) => rank(a) - rank(b));
  const first = pool[0] ?? null;

  const contrasting = first
    ? pool.find((v) => v !== first && gender(v) !== gender(first) && gender(v) !== "?")
    : null;

  return {
    interviewer: first,
    student: contrasting ?? pool.find((v) => v !== first) ?? first,
    quality: first ? (rank(first) <= 3 ? "good" : "basic") : "none",
  };
}

function gender(v: SpeechSynthesisVoice): "f" | "m" | "?" {
  if (FEMALE.test(v.name)) return "f";
  if (MALE.test(v.name)) return "m";
  return "?";
}
