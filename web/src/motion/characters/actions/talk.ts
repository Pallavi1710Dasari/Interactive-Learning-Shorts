/* Text becomes mouth. A line is split into words, each word into visemes
 * (the dozen mouth shapes speech is made of), and the visemes become keys
 * on the mouth channels. Around the mouth the head does what a speaking
 * head does: it dips on a stressed syllable, lifts with the brows on a
 * question, flashes the brows on an exclamation, and blinks where a breath
 * goes. The mapping is from English spelling, not sound. That is crude
 * phonetically, but at slide size the rhythm is what reads, and the rhythm
 * comes from the timing, not from which letter made which shape. */
import type { Channel } from '../rig/channels'
import { delay } from '../rig/track'
import type { Action, Ease, Key, Tracks } from '../rig/track'

export type VisemeShape = 'rest' | 'A' | 'E' | 'I' | 'O' | 'U' | 'M' | 'F' | 'L' | 'W' | 'TH' | 'S'
export type Viseme = { shape: VisemeShape; dur: number; stress: boolean }

/* A rest inside a word is a consonant the lips hardly move for (d, t, n, k,
   g, r, h). A rest with a gap is silence, and the mouth closes for it. */
type Gap = 'word' | 'comma' | 'stop'
type Segment = Viseme & { gap?: Gap }
type Mark = '' | ',' | '.' | '?' | '!'
type Phrase = { segs: Segment[]; mark: Mark }

/* Seconds at 150 wpm. Vowels run longer than consonants and a stressed
   vowel longer still; that unevenness is most of what makes it look like
   speech rather than a metronome. */
const T = {
  consonant: 0.06,
  vowel: 0.08,
  stressed: 0.11,
  glide: 0.065, // each half of a diphthong (ou, ow)
  wordGap: 0.12,
  comma: 0.2,
  stop: 0.35,
  lead: 0.08, // the lips part before the first sound
  settle: 0.25, // the return to rest after the last
  min: 0.05, // the jaw never snaps: no shape arrives sooner than this after the last
  early: 0.3, // coarticulation: a shape is reached this fraction of the previous one before its boundary
}

/* ---------- text to visemes ---------- */

/* Pairs that make one sound. Checked before single letters, so 'oo' is a
   U and never two O's. A doubled consonant is merged by the single-letter
   path. */
const DIGRAPHS: Record<string, VisemeShape[]> = {
  oo: ['U'],
  ou: ['O', 'U'],
  ow: ['O', 'U'],
  ee: ['E'],
  ea: ['E'],
  ai: ['E'],
  ay: ['E'],
  th: ['TH'],
  sh: ['S'],
  ch: ['S'],
  ph: ['F'],
  qu: ['W'],
  ck: ['rest'],
}

/* Every letter not listed is a consonant the lips barely shape (d, t, n,
   k, g, h, r, j, c): a brief, slightly open rest. */
const LETTERS: Partial<Record<string, VisemeShape>> = {
  a: 'A', e: 'E', i: 'I', o: 'O', u: 'U', y: 'I',
  s: 'S', z: 'S', x: 'S',
  f: 'F', v: 'F',
  m: 'M', b: 'M', p: 'M',
  l: 'L',
  w: 'W',
}

const VOWELS = new Set<VisemeShape>(['A', 'E', 'I', 'O', 'U'])

/* Words that carry no stress in a sentence. Everything else is a content
   word and its first vowel gets the beat. */
const FUNCTION_WORDS = new Set([
  'a', 'an', 'the', 'of', 'to', 'in', 'on', 'at', 'for', 'and', 'or', 'but', 'as', 'so', 'if', 'by', 'from', 'with',
  'is', 'are', 'am', 'was', 'were', 'be', 'do', 'does', 'did', 'has', 'have', 'had', 'will', 'can', 'not', 'no',
  'it', 'its', 'i', 'you', 'we', 'he', 'she', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'our', 'this', 'that',
])

/* 'make' ends in a silent e; 'the' and 'see' do not. The e is silent when a
   consonant sits before it and the word already has a vowel earlier. */
function dropSilentE(w: string): string {
  const silent = w.length >= 3 && w.endsWith('e') && !/[aeiou]/.test(w[w.length - 2]) && /[aeiouy]/.test(w.slice(0, -2))
  return silent ? w.slice(0, -1) : w
}

function durOf(shape: VisemeShape, stress: boolean, glide: boolean): number {
  if (glide) return stress ? T.glide + 0.03 : T.glide
  if (stress) return T.stressed
  return VOWELS.has(shape) ? T.vowel : T.consonant
}

function wordVisemes(letters: string, content: boolean): Segment[] {
  const w = dropSilentE(letters)
  const out: Segment[] = []
  let stressed = !content
  for (let i = 0; i < w.length; ) {
    const pair = DIGRAPHS[w.slice(i, i + 2)]
    let shapes: VisemeShape[]
    if (pair) {
      shapes = pair
      i += 2
    } else {
      shapes = [LETTERS[w[i]] ?? 'rest']
      i += 1
      while (w[i] === w[i - 1]) i += 1 // 'll', 'ss', 'tt': one shape, not two
    }
    const glide = shapes.length > 1
    for (const shape of shapes) {
      const stress = VOWELS.has(shape) && !stressed
      if (stress) stressed = true
      out.push({ shape, dur: durOf(shape, stress, glide), stress })
    }
  }
  return out
}

/* The strongest punctuation at the end of a token decides what kind of
   pause follows it; '!' beats '?' beats '.' beats the rest. */
function markOf(token: string): Mark {
  const tail = token.replace(/["')\]]+$/, '').match(/[.,;:!?]+$/)?.[0] ?? ''
  if (tail.includes('!')) return '!'
  if (tail.includes('?')) return '?'
  if (tail.includes('.')) return '.'
  return tail ? ',' : ''
}

function parse(text: string): Phrase[] {
  const phrases: Phrase[] = []
  let segs: Segment[] = []
  for (const token of text.split(/\s+/)) {
    const letters = token.toLowerCase().replace(/[^a-z]/g, '')
    if (letters) {
      if (segs.length) segs.push({ shape: 'rest', dur: T.wordGap, stress: false, gap: 'word' })
      segs.push(...wordVisemes(letters, !FUNCTION_WORDS.has(letters)))
    }
    const mark = markOf(token)
    if (mark && segs.length) {
      const gap: Gap = mark === ',' ? 'comma' : 'stop'
      segs.push({ shape: 'rest', dur: gap === 'comma' ? T.comma : T.stop, stress: false, gap })
      phrases.push({ segs, mark })
      segs = []
    }
  }
  if (segs.length) phrases.push({ segs, mark: '' })
  return phrases
}

/** The mouth shapes of a line in order, with word gaps and pauses as rests,
    timed for 150 wpm. */
export function visemesFor(text: string): Viseme[] {
  return parse(text).flatMap((p) => p.segs.map(({ shape, dur, stress }) => ({ shape, dur, stress })))
}

/* ---------- visemes to a timeline ---------- */

type Timed = { seg: Segment; at: number; dur: number; key: number }
type TimedPhrase = { items: Timed[]; mark: Mark; lastWordAt: number; stopAt: number; end: number }

/* Lays the visemes end to end from T.lead, scaled for the speaking rate but
   never under T.min, and gives each one its key time: a little before its
   boundary, by a fraction of the viseme before it, so one shape is still
   finishing as the next begins. Measuring the lead on the previous viseme
   is what keeps a long pause from arriving before the short consonant
   ahead of it. */
function schedule(text: string, wpm: number): { phrases: TimedPhrase[]; end: number } {
  const parsed = parse(text)
  if (!parsed.length) return { phrases: [], end: 0 }
  const rate = 150 / wpm
  let t = T.lead
  let prevDur = T.lead
  const phrases = parsed.map((ph) => {
    const items: Timed[] = []
    let lastWordAt = t
    for (const seg of ph.segs) {
      const dur = Math.max(T.min, seg.dur * rate)
      if (seg.gap === 'word') lastWordAt = t + dur
      items.push({ seg, at: t, dur, key: t - T.early * prevDur })
      t += dur
      prevDur = dur
    }
    const last = items[items.length - 1]
    return { items, mark: ph.mark, lastWordAt, stopAt: last.seg.gap ? last.at : t, end: t }
  })
  return { phrases, end: t }
}

/** How long a line takes to say, so a caller can schedule the next one.
    The Action runs T.settle longer than this while the mouth returns to rest. */
export function sayDuration(text: string, wpm = 150): number {
  return schedule(text, wpm).end
}

/* ---------- timeline to tracks ---------- */

export type Mouth = { open: number; wide: number; pucker: number; teeth: number; tongue: number }
const m = (open: number, wide: number, pucker: number, teeth: number, tongue: number): Mouth => ({ open, wide, pucker, teeth, tongue })

/* The contract's shapes. Teeth show where the real sound shows them: an
   'ee' bares them, an 'f' sets them on the lip, an 's' hisses through them;
   rounded and closed shapes hide them. */
export const SHAPES: Record<VisemeShape, Mouth> = {
  rest: m(0.2, 0.5, 0, 0.3, 0),
  A: m(0.75, 0.55, 0, 0.25, 0),
  E: m(0.45, 0.9, 0, 0.6, 0),
  I: m(0.3, 1, 0, 0.7, 0),
  O: m(0.7, 0.15, 0.6, 0, 0),
  U: m(0.35, 0.1, 0.9, 0, 0),
  M: m(0, 0.3, 0.2, 0, 0),
  F: m(0.15, 0.7, 0, 0.8, 0),
  L: m(0.5, 0.5, 0, 0.3, 0.6),
  W: m(0.25, 0, 0.8, 0, 0),
  TH: m(0.3, 0.6, 0, 0.4, 0.4),
  S: m(0.15, 0.8, 0, 1, 0),
}
export const PARTED = m(0.08, 0.4, 0, 0, 0) // between words the lips stay a touch apart
export const CLOSED = m(0, 0.35, 0, 0, 0) // the channel defaults: the mouth closes for a pause

export const MOUTH_CHANNEL: Record<keyof Mouth, Channel> = { open: 'mouthOpen', wide: 'mouthWide', pucker: 'pucker', teeth: 'teeth', tongue: 'tongue' }
export const MOUTH_FIELDS = Object.keys(MOUTH_CHANNEL) as (keyof Mouth)[]

export const NOD = 0.12 // headNod is a blend; this much reads as about 1.5 degrees of pitch
export const STRESS_OPEN = 0.15
const BANG_OPEN = 0.2

/* Adds a multi-channel event, or drops it whole when any of its channels is
   still busy with the one before: a nod that lands on a nod is a wobble,
   not two nods. */
function event(tracks: Tracks, parts: Tracks): void {
  for (const ch in parts) {
    const lane = tracks[ch as Channel]
    if (lane?.length && lane[lane.length - 1][0] + T.min > parts[ch as Channel]![0][0]) return
  }
  for (const ch in parts) (tracks[ch as Channel] ??= []).push(...parts[ch as Channel]!)
}

/* Rise then settle, with one side a shade higher than the other because a
   symmetric face reads as a mask. */
const browPair = (a: number, peak: number, b: number, c: number, level: number): Tracks => ({
  browL: [[a, 0], [peak, level - 0.05, 'out'], [b, level - 0.05], [c, 0, 'inOut']],
  browR: [[a, 0], [peak, level + 0.05, 'out'], [b, level + 0.05], [c, 0, 'inOut']],
})

/** A line of speech as an Action: mouth channels replace, head and brows
    add on top of whatever expression and gesture are running. */
export function talkAction(text: string, opts: { wpm?: number; emphasis?: boolean } = {}): Action {
  const { wpm = 150, emphasis = true } = opts
  const { phrases, end } = schedule(text, wpm)
  const tracks: Tracks = {}

  /* The jaw pulls the whole head down a touch as it opens: 1 px per 0.5 open. */
  const mouthKey = (t: number, shape: Mouth, e: Ease = 'inOut') => {
    for (const f of MOUTH_FIELDS) (tracks[MOUTH_CHANNEL[f]] ??= []).push([t, shape[f], e])
    ;(tracks.headY ??= []).push([t, shape.open * 2, e])
  }

  /* A beat of the head on a stressed syllable: a quick dip, a slower lift. */
  const nod = (t: number) => event(tracks, { headNod: [[t - 0.04, 0], [t + 0.08, NOD, 'out'], [t + 0.26, 0, 'inOut']] })

  /* Brows and chin come up over the last word of a question, hold through
     the pause, and let go after it. */
  const lift = (ph: TimedPhrase) => {
    const b = ph.stopAt
    const a = Math.max(0, Math.min(Math.max(ph.lastWordAt - 0.05, b - 0.45), b - 0.15))
    const c = ph.end
    event(tracks, {
      ...browPair(a, b, c, c + 0.3, 0.4),
      headNod: [[a, 0], [b, -0.14, 'out'], [c, -0.14], [c + 0.3, 0, 'inOut']],
      headTilt: [[a, 0], [b, 2, 'out'], [c, 2], [c + 0.35, 0, 'inOut']],
    })
  }

  /* The greeting flash, on the last word of an exclamation. */
  const flash = (ph: TimedPhrase) => {
    const t = ph.lastWordAt
    event(tracks, browPair(t - 0.03, t + 0.08, t + 0.16, t + 0.34, 0.55))
  }

  /* 90 ms down, 180 ms up, the right eye 15 ms behind. */
  const blink = (t: number) => {
    const keys: Key[] = [[t, 0], [t + 0.09, 1, 'out'], [t + 0.27, 0, 'inOut']]
    event(tracks, { blinkL: keys, blinkR: delay(keys, 0.015) })
  }

  mouthKey(0, CLOSED)
  let lastBlink = -0.6 // the first blink waits long enough not to double an idle blink at the start
  for (const ph of phrases) {
    const question = emphasis && ph.mark === '?'
    const bang = emphasis && ph.mark === '!'
    /* No stress nods just before a question lift: the lift is the bigger
       move and the head needs to be still to make it. */
    const nodUntil = question ? ph.lastWordAt - 0.35 : Infinity

    for (const { seg, at, key } of ph.items) {
      if (seg.gap) {
        mouthKey(key, seg.gap === 'word' ? PARTED : CLOSED)
        const due = seg.gap === 'word' ? at - lastBlink > 4 : at - lastBlink > 1.2
        if (due) {
          blink(at - 0.05)
          lastBlink = at
        }
        continue
      }
      const shape = { ...SHAPES[seg.shape] }
      const extra = (seg.stress ? STRESS_OPEN : 0) + (bang && VOWELS.has(seg.shape) ? BANG_OPEN : 0)
      shape.open = Math.min(1, shape.open + extra)
      mouthKey(key, shape, seg.stress ? 'out' : 'inOut')
      if (seg.stress && emphasis && at < nodUntil) nod(key)
    }

    if (question) lift(ph)
    if (bang) flash(ph)
  }
  mouthKey(end + T.settle, CLOSED)

  return { name: 'talk', group: 'talk', duration: end + T.settle, blendIn: 0.08, blendOut: T.settle, tracks }
}
