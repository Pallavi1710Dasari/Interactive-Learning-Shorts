import { useCallback, useEffect, useRef, useState } from "react";
import type { ReelBeat } from "./types";

/**
 * Speaks a short, one beat at a time, and reports which beat is on screen.
 *
 * Beat changes are driven by the *voice*, not a timer: an utterance ends, the
 * next beat starts. Word-count timing was always an estimate, and with real
 * speech the estimate and the audio drift apart within a couple of beats.
 *
 * If the browser has no speech (or no voices installed), it falls back to the
 * estimated beat durations so the reel still plays — silently.
 */

export type Narration = {
  beat: number;
  playing: boolean;
  speaking: boolean;
  progress: number;          // 0..1 across the whole short
  voiceReady: boolean;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  replay: () => void;
  goToBeat: (i: number) => void;
};

const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;

/** Voices load asynchronously in Chrome; this resolves once they exist. */
export function useVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    if (!synth) return;
    const read = () => setVoices(synth.getVoices());
    read();
    synth.addEventListener("voiceschanged", read);
    return () => synth.removeEventListener("voiceschanged", read);
  }, []);
  return voices;
}

/**
 * Two distinguishable English voices — interviewer and student.
 *
 * Quality varies enormously between the engines a Linux box exposes through
 * speech-dispatcher. mbrola voices are diphone-concatenative and sound markedly
 * less synthetic than raw espeak, so prefer them; then any non-espeak engine;
 * then whatever is left. The two picks must also differ from each other, or the
 * interview sounds like one person talking to themselves.
 */
const NICER = [/mbrola/i, /neural|natural|premium|enhanced/i, /google|microsoft/i];

export function pickVoices(voices: SpeechSynthesisVoice[]) {
  const en = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = [...(en.length ? en : voices)].sort((a, b) => rank(a) - rank(b));
  const first = pool[0] ?? null;
  return {
    interviewer: first,
    student: pool.find((v) => v !== first) ?? first,
    quality: first ? (NICER.some((re) => re.test(first.name)) ? "good" : "basic") : "none",
  };
}

function rank(v: SpeechSynthesisVoice): number {
  const i = NICER.findIndex((re) => re.test(v.name));
  return i === -1 ? NICER.length : i;
}

export function useNarration(
  beats: ReelBeat[],
  totalSeconds: number,
  opts: { enabled: boolean; rate: number; active: boolean },
): Narration {
  const { enabled, rate, active } = opts;
  const voices = useVoices();
  const [beat, setBeat] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const beatRef = useRef(0);
  const cancelled = useRef(false);
  beatRef.current = beat;

  const voiceReady = !!synth && voices.length > 0 && enabled;

  const stopVoice = useCallback(() => {
    cancelled.current = true;
    synth?.cancel();
    setSpeaking(false);
  }, []);

  // Queue every remaining beat in one go, and move the visuals on each utterance's
  // onstart.
  //
  // Speaking one beat, waiting for onend, setting state, and letting an effect
  // start the next utterance put a React render in the middle of the sentence —
  // audibly, a gap between every beat. speechSynthesis has its own queue, so
  // handing it all the utterances at once lets it run them back to back and the
  // explanation flows as one take.
  useEffect(() => {
    if (!playing || !voiceReady || !active) return;
    const from = beatRef.current;
    cancelled.current = false;
    const chosen = pickVoices(voices);

    beats.slice(from).forEach((b, offset) => {
      const index = from + offset;
      const utter = new SpeechSynthesisUtterance(b.line);
      utter.voice = b.speaker === "interviewer" ? chosen.interviewer : chosen.student;
      utter.rate = rate;
      // A little separation in pitch is what makes two espeak voices read as two
      // different people rather than one.
      utter.pitch = b.speaker === "interviewer" ? 1.12 : 0.92;

      utter.onstart = () => {
        if (cancelled.current) return;
        setSpeaking(true);
        setBeat(index);           // visuals follow the audio, never lead it
      };
      utter.onend = () => {
        if (cancelled.current) return;
        setSpeaking(false);
        if (index === beats.length - 1) setPlaying(false);
      };
      utter.onerror = () => {
        // cancel() surfaces as onerror in some browsers; only a genuine failure
        // should stop playback.
        setSpeaking(false);
        if (!cancelled.current) setPlaying(false);
      };
      synth!.speak(utter);
    });

    return () => {
      cancelled.current = true;
      synth!.cancel();
    };
    // Deliberately not keyed on `beat`: re-running per beat is what caused the
    // gaps. Seeking cancels and re-queues through goToBeat/replay instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, voiceReady, active, beats, voices, rate]);

  // Silent fallback: no speech available, so advance on the estimated durations.
  useEffect(() => {
    if (!playing || voiceReady || !active) return;
    const current = beats[beatRef.current];
    if (!current) return;
    const ms = Math.max(800, ((current.end - current.start) * 1000) / rate);
    const id = window.setTimeout(() => {
      const next = beatRef.current + 1;
      if (next < beats.length) setBeat(next);
      else setPlaying(false);
    }, ms);
    return () => window.clearTimeout(id);
  }, [playing, beat, voiceReady, active, beats, rate]);

  // A clock purely for the progress bar. Never drives beat changes.
  useEffect(() => {
    if (!playing) return;
    let prev = performance.now();
    let id = requestAnimationFrame(function tick(now) {
      setElapsed((e) => e + (now - prev) / 1000);
      prev = now;
      id = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(id);
  }, [playing]);

  // Scrolled away -> silence immediately. Nothing should narrate off screen.
  useEffect(() => {
    if (!active) {
      setPlaying(false);
      stopVoice();
      setBeat(0);
      setElapsed(0);
    }
  }, [active, stopVoice]);

  useEffect(() => () => stopVoice(), [stopVoice]);

  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => {
    setPlaying(false);
    stopVoice();            // pause must actually silence it, not keep talking
  }, [stopVoice]);
  const toggle = useCallback(() => (playing ? pause() : play()), [playing, pause, play]);

  const replay = useCallback(() => {
    synth?.cancel();
    beatRef.current = 0;
    setBeat(0);
    setElapsed(0);
    setPlaying(false);
    requestAnimationFrame(() => { cancelled.current = false; setPlaying(true); });
  }, []);

  const goToBeat = useCallback((i: number) => {
    if (i < 0 || i >= beats.length) return;
    // Cancel the queued utterances and let the speak effect re-queue from here.
    synth?.cancel();
    setSpeaking(false);
    beatRef.current = i;
    setBeat(i);
    setElapsed(beats[i].start);
    if (playing) {
      // Force the effect to re-run: it is keyed on `playing`, not on `beat`.
      setPlaying(false);
      requestAnimationFrame(() => { cancelled.current = false; setPlaying(true); });
    }
  }, [beats, playing]);

  // With voice on, real duration is unknown, so blend beat position with the
  // clock. Without voice the clock is the truth.
  const byBeat = beats.length ? (beat + 1) / beats.length : 0;
  const byClock = totalSeconds ? Math.min(1, elapsed / totalSeconds) : 0;
  const progress = voiceReady ? Math.max(byClock * 0.6, byBeat * 0.85) : byClock;

  return { beat, playing, speaking, progress: Math.min(1, progress),
           voiceReady, play, pause, toggle, replay, goToBeat };
}
