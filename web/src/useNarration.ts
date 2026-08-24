import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReelBeat } from "./types";
import { phrases, pickVoices, profile } from "./speech";

/**
 * Speaks a short, one beat at a time, and reports which beat is on screen.
 *
 * THE NARRATOR IS THE RECORDED ELEVENLABS TRACK (`audioUrl`). It is synthesised
 * server-side at build time — see shorts/tts.py — and cached, so playback is
 * instant and a re-watch costs nothing. Beats are cut to the synthesiser's own
 * per-beat spans, so picture and audio cannot drift.
 *
 * window.speechSynthesis is now only a FALLBACK, for a unit that has no recorded
 * track yet: the units built before the switch, or a build where the provider was
 * unreachable. It is audibly a synthesiser however well it is phrased, which is why
 * it is no longer the default. Back it up with `python -m shorts.voice --all` and
 * this path stops being used at all.
 *
 * Beat changes are driven by the *voice* in both modes, never by a timer: word-count
 * timing was always an estimate, and with real speech the estimate and the audio
 * drift apart within a couple of beats.
 *
 * If neither narrator is available the reel still plays, silently, on the estimated
 * beat durations.
 */

export type Narration = {
  beat: number;
  playing: boolean;
  speaking: boolean;
  progress: number;          // 0..1 across the whole short
  /**
   * Where the narration is, in seconds from the start of the short. This is what
   * the flowing caption highlights against, so it has to be a real position and
   * not a beat index: the recorded track reports its own currentTime, and the
   * other two modes interpolate inside the current beat's span.
   */
  time: number;
  voiceReady: boolean;
  /** True when a recorded neural track is what you are hearing. */
  recorded: boolean;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  replay: () => void;
  goToBeat: (i: number) => void;
};

const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;

/**
 * THE NARRATION FLOOR — at most one reel may make sound, app-wide.
 *
 * Every reel used to police itself: stop when you scroll off screen. That is not
 * enough, for two reasons that combine into audibly overlapping voices.
 *
 * First, window.speechSynthesis is a single global queue, not a per-component
 * one, and Chrome's cancel() does not reliably stop the utterance already in
 * flight — a reel that has been scrolled past can keep talking for a second or
 * two after it was told to stop.
 *
 * Second, the two narrators know nothing about each other. Half the deck has a
 * recorded track and half falls back to browser speech, so scrolling from a
 * spoken reel to a recorded one starts an <audio> element while the synthesiser
 * is still finishing its sentence. Two different voices, two different scripts,
 * at the same time.
 *
 * So claiming the floor is what starts playback, and claiming it stops whoever
 * held it first. One holder, therefore one voice — whichever narrator it uses.
 */
let floorHolder: (() => void) | null = null;

function claimFloor(release: () => void): void {
  if (floorHolder && floorHolder !== release) floorHolder();
  floorHolder = release;
}

function releaseFloor(release: () => void): void {
  if (floorHolder === release) floorHolder = null;
}

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

export { pickVoices };

export function useNarration(
  beats: ReelBeat[],
  totalSeconds: number,
  opts: { enabled: boolean; rate: number; active: boolean; audioUrl?: string | null },
): Narration {
  const { enabled, rate, active, audioUrl } = opts;
  const voices = useVoices();
  const [beat, setBeat] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [time, setTime] = useState(0);

  const beatRef = useRef(0);
  /** performance.now() at the moment the current beat became current. */
  const beatEnteredAt = useRef(0);
  const cancelled = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  beatRef.current = beat;

  const recorded = !!audioUrl && enabled;
  const canSpeak = !!synth && voices.length > 0 && enabled;
  const voiceReady = recorded || canSpeak;

  // Stable identity: it doubles as this reel's key on the narration floor, so it
  // must not be rebuilt between renders or the floor would lose track of who
  // holds it.
  const stopVoice = useCallback(() => {
    cancelled.current = true;
    synth?.cancel();
    const a = audioRef.current;
    if (a) { a.pause(); a.currentTime = 0; }
    setSpeaking(false);
    setPlaying(false);
  }, []);

  // ------------------------------------------------------ 1. recorded neural track
  //
  // One <audio> element for the whole short. Beats are driven off timeupdate against
  // the beat spans the server derived from the provider's word timings, so the
  // picture changes on the word rather than on an estimate.
  useEffect(() => {
    if (!recorded || !active) return;
    const a = new Audio(audioUrl!);
    a.preload = "auto";
    audioRef.current = a;

    const onTime = () => {
      setElapsed(a.currentTime);
      setTime(a.currentTime);
      const at = beats.findIndex((b) => a.currentTime >= b.start && a.currentTime < b.end);
      if (at !== -1 && at !== beatRef.current) setBeat(at);
    };
    const onEnd = () => { setPlaying(false); setSpeaking(false); };
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("ended", onEnd);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("ended", onEnd);
      a.pause();
      audioRef.current = null;
    };
  }, [recorded, audioUrl, active, beats]);

  useEffect(() => {
    const a = audioRef.current;
    if (!recorded || !a) return;
    a.playbackRate = rate;
    if (playing && active && floorHolder === stopVoice) {
      setSpeaking(true);
      // A rejected play() is the browser's autoplay policy, not a bug. The reel
      // shows its tap-to-play affordance whenever playing is false.
      a.play().catch(() => { setPlaying(false); setSpeaking(false); });
    } else {
      a.pause();
      setSpeaking(false);
    }
  }, [recorded, playing, active, rate, stopVoice]);

  // -------------------------------------------------- 2. browser speech, phrased
  //
  // Every remaining phrase is queued in one go, and the visuals move on each
  // utterance's onstart.
  //
  // Speaking one piece, waiting for onend, setting state, and letting an effect
  // start the next put a React render in the middle of the sentence — audibly, a
  // gap. speechSynthesis has its own queue, so handing it everything at once lets
  // it run the phrases back to back and the explanation flows as one take.
  const queue = useMemo(
    () => beats.flatMap((b, index) =>
      phrases(b.line).map((text, part) => ({ text, index, part, speaker: b.speaker }))),
    [beats],
  );

  useEffect(() => {
    if (!playing || recorded || !canSpeak || !active) return;
    if (floorHolder !== stopVoice) return;   // someone else is narrating
    const from = beatRef.current;
    cancelled.current = false;
    const chosen = pickVoices(voices);

    for (const item of queue.filter((q) => q.index >= from)) {
      const utter = new SpeechSynthesisUtterance(item.text);
      utter.voice = item.speaker === "interviewer" ? chosen.interviewer : chosen.student;
      const p = profile(item.speaker, item.text, rate);
      utter.rate = p.rate;
      utter.pitch = p.pitch;

      utter.onstart = () => {
        if (cancelled.current) return;
        setSpeaking(true);
        setBeat(item.index);      // visuals follow the audio, never lead it
      };
      utter.onend = () => {
        if (cancelled.current) return;
        const last = queue[queue.length - 1];
        if (item.index === last.index && item.part === last.part) {
          setSpeaking(false);
          setPlaying(false);
        }
      };
      utter.onerror = () => {
        // cancel() surfaces as onerror in some browsers; only a genuine failure
        // should stop playback.
        setSpeaking(false);
        if (!cancelled.current) setPlaying(false);
      };
      synth!.speak(utter);
    }

    return () => {
      cancelled.current = true;
      synth!.cancel();
    };
    // Deliberately not keyed on `beat`: re-running per beat is what caused the
    // gaps. Seeking cancels and re-queues through goToBeat/replay instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, recorded, canSpeak, active, queue, voices, rate, stopVoice]);

  // ------------------------------------- 3. silent fallback: no narrator at all
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

  // When did this beat start? Browser speech tells us a beat began (onstart) but
  // never where it is inside it, so the caption's position is measured from here.
  useEffect(() => {
    beatEnteredAt.current = performance.now();
    if (beats[beat]) setTime(beats[beat].start);
  }, [beat, beats]);

  // A clock purely for the progress bar, plus the interpolated caption position.
  // Never drives beat changes. The recorded track reports its own currentTime, so
  // it does not need this.
  //
  // The caption clock is clamped to the current beat's own span rather than left
  // to run free: an utterance that takes longer than the estimate would otherwise
  // walk the highlight into the next beat's words, and a caption highlighting a
  // word the voice is not saying is worse than one that simply waits at the end
  // of the line.
  useEffect(() => {
    if (!playing || recorded) return;
    let prev = performance.now();
    let id = requestAnimationFrame(function tick(now) {
      setElapsed((e) => e + (now - prev) / 1000);
      prev = now;
      const current = beats[beatRef.current];
      if (current) {
        const into = ((now - beatEnteredAt.current) / 1000) * rate;
        setTime(Math.min(current.start + into, current.end));
      }
      id = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(id);
  }, [playing, recorded, beats, rate]);

  // Scrolled away -> silence immediately. Nothing should narrate off screen.
  useEffect(() => {
    if (!active) {
      stopVoice();
      releaseFloor(stopVoice);
      setBeat(0);
      setElapsed(0);
      setTime(0);
    }
  }, [active, stopVoice]);

  useEffect(() => () => { stopVoice(); releaseFloor(stopVoice); }, [stopVoice]);

  const play = useCallback(() => {
    claimFloor(stopVoice);    // silences whatever else was narrating
    setPlaying(true);
  }, [stopVoice]);

  const pause = useCallback(() => {
    setPlaying(false);
    synth?.cancel();          // pause must actually silence it, not keep talking
    audioRef.current?.pause();
    setSpeaking(false);
    releaseFloor(stopVoice);
  }, [stopVoice]);
  const toggle = useCallback(() => (playing ? pause() : play()), [playing, pause, play]);

  const replay = useCallback(() => {
    claimFloor(stopVoice);
    synth?.cancel();
    if (audioRef.current) audioRef.current.currentTime = 0;
    beatRef.current = 0;
    setBeat(0);
    setElapsed(0);
    setTime(0);
    beatEnteredAt.current = performance.now();
    setPlaying(false);
    requestAnimationFrame(() => { cancelled.current = false; setPlaying(true); });
  }, [stopVoice]);

  const goToBeat = useCallback((i: number) => {
    if (i < 0 || i >= beats.length) return;
    setSpeaking(false);
    beatRef.current = i;
    setBeat(i);
    setElapsed(beats[i].start);
    setTime(beats[i].start);
    beatEnteredAt.current = performance.now();

    if (audioRef.current) {
      audioRef.current.currentTime = beats[i].start;   // a seek, not a re-queue
      return;
    }
    // Cancel the queued utterances and let the speak effect re-queue from here.
    synth?.cancel();
    if (playing) {
      // Force the effect to re-run: it is keyed on `playing`, not on `beat`.
      setPlaying(false);
      requestAnimationFrame(() => { cancelled.current = false; setPlaying(true); });
    }
  }, [beats, playing]);

  // A recorded track knows exactly where it is. Browser speech does not report a
  // position, so blend beat index with the clock. Silent mode: the clock is truth.
  const byBeat = beats.length ? (beat + 1) / beats.length : 0;
  const byClock = totalSeconds ? Math.min(1, elapsed / totalSeconds) : 0;
  const progress = recorded ? byClock
                 : canSpeak ? Math.max(byClock * 0.6, byBeat * 0.85)
                 : byClock;

  return { beat, playing, speaking, progress: Math.min(1, progress), time,
           voiceReady, recorded, play, pause, toggle, replay, goToBeat };
}
