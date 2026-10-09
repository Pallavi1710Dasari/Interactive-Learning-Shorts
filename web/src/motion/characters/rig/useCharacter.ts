/* The runtime: a clock, a Timeline in a ref, and one setState per frame
 * with the pose. Nothing else is React state, so play() in the middle of a
 * frame never re-renders twice.
 *
 * Two clocks. `auto` runs on requestAnimationFrame from its own epoch, for
 * a slide. `manual` only moves on seek(t), for the recorder and the shoot
 * harness, which step time themselves so every frame is exact. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { ACTIONS, EXPRESSIONS } from '../actions'
import { talkAction } from '../actions/talk'
import { defaultPose, type Pose } from './channels'
import { clipDone, EXPRESSION_CROSSFADE, poseAt, type Timeline } from './compose'
import { delay, mirror, retime, scaleAction, type Action, type Key, type Tracks } from './track'
import type { IdleOptions } from './idle'
import type { LifeOptions } from './life'

export type { IdleOptions } from './idle'
export type { LifeOptions } from './life'

export type PlayOptions = {
  speed?: number
  amplitude?: number
  side?: 'L' | 'R'
  repeat?: number
  loop?: boolean
  /** 0..1, how much this play differs from the last: the same wave twice
      is a machine. Default 1 (about 6 percent in size and timing). */
  variation?: number
}

export type Controls = {
  pose: Pose
  time: number
  play: (gesture: string | Action, opts?: PlayOptions) => void
  stop: () => void
  setExpression: (name: string, intensity?: number) => void
  say: (text: string, opts?: { wpm?: number; emphasis?: boolean }) => void
  seek: (t: number) => void
  setClock: (mode: 'auto' | 'manual') => void
  setIdle: (opts: IdleOptions) => void
  setLife: (opts: LifeOptions | 0) => void
  current: { gesture?: string; expression: string; talking: boolean }
}

/* A seeded number in -1..1 for the n-th play, so a recording is still
   repeatable: the same script gives the same variations. */
function wobble(seed: number, n: number, salt: number): number {
  let h = (seed * 2246822519 + n * 3266489917 + salt * 668265263) | 0
  h = Math.imul(h ^ (h >>> 15), 2246822507)
  h = Math.imul(h ^ (h >>> 13), 3266489909)
  return (((h ^ (h >>> 16)) >>> 0) / 4294967296) * 2 - 1
}

declare global {
  interface Window {
    __actors?: Record<string, Controls>
  }
}

type Clock = 'auto' | 'manual'

/* n passes laid end to end; a plain loop would never stop. */
function repeatAction(action: Action, n: number): Action {
  const tracks: Tracks = {}
  for (const ch in action.tracks) {
    const keys = action.tracks[ch as keyof Tracks]!
    const out: Key[] = []
    for (let k = 0; k < n; k++) out.push(...delay(keys, k * action.duration))
    tracks[ch as keyof Tracks] = out
  }
  return { ...action, duration: action.duration * n, loop: false, tracks }
}

/* Actions are authored on the screen-left arm; side R is the mirror. The
   n-th play is a little bigger or smaller and a little quicker or slower
   than the last, so a repeated gesture reads as a person repeating it. */
function prepare(action: Action, o: PlayOptions, seed: number, n: number): Action {
  let a = action
  const vary = o.variation ?? 1
  const speed = (o.speed ?? 1) * (1 + 0.05 * vary * wobble(seed, n, 1))
  const amplitude = (o.amplitude ?? 1) * (1 + 0.06 * vary * wobble(seed, n, 2))
  if (speed !== 1) a = retime(a, 1 / speed)
  if (amplitude !== 1) a = scaleAction(a, amplitude, defaultPose())
  if (o.side === 'R') a = mirror(a)
  if (o.repeat && o.repeat > 1) a = repeatAction(a, Math.floor(o.repeat))
  if (o.loop !== undefined) a = { ...a, loop: o.loop }
  return a
}

export function useCharacter(opts: { id?: string; seed?: number; clock?: Clock; idle?: IdleOptions; life?: LifeOptions | 0 } = {}): Controls {
  const tl = useRef<Timeline>({ seed: opts.seed ?? 1, idle: opts.idle ?? {}, life: opts.life })
  const playsRef = useRef(0)
  const timeRef = useRef(0)
  const poseRef = useRef<Pose>(poseAt(tl.current, 0))
  const currentRef = useRef<Controls['current']>({ expression: 'neutral', talking: false })
  /* auto clock: performance.now() at which t was 0; moved by seek and by a hidden tab */
  const epochRef = useRef(0)
  const [mode, setMode] = useState<Clock>(opts.clock ?? 'auto')
  const modeRef = useRef(mode)
  modeRef.current = mode
  const [frame, setFrame] = useState({ pose: poseRef.current, time: 0 })

  /* every control reads refs, so one instance serves the whole life of the hook */
  const { api, render } = useMemo(() => {
    const now = () => timeRef.current

    /* Drop clips that can no longer contribute, and let `current` say so. */
    const tidy = (t: number) => {
      const T = tl.current
      if (T.prevGesture && clipDone(T.prevGesture, t)) delete T.prevGesture
      if (T.gesture && clipDone(T.gesture, t)) {
        delete T.gesture
        delete currentRef.current.gesture
      }
      if (T.prevExpression && T.expression && t >= T.expression.start + EXPRESSION_CROSSFADE) delete T.prevExpression
      if (T.talk) {
        if (t >= T.talk.start + T.talk.action.duration) currentRef.current.talking = false
        if (clipDone(T.talk, t)) delete T.talk
      }
    }

    const render = (t: number) => {
      timeRef.current = t
      tidy(t)
      poseRef.current = poseAt(tl.current, t)
      setFrame({ pose: poseRef.current, time: t })
    }

    /* the auto clock redraws on its next frame; a manual clock would show nothing until the next seek */
    const redraw = () => {
      if (modeRef.current === 'manual') render(now())
    }

    const play: Controls['play'] = (gesture, o = {}) => {
      const base = typeof gesture === 'string' ? ACTIONS[gesture] : gesture
      if (!base) {
        console.warn(`useCharacter: no gesture named "${String(gesture)}"`)
        return
      }
      const T = tl.current
      const t = now()
      /* the old gesture fades out while the new one fades in */
      if (T.gesture && !clipDone(T.gesture, t)) T.prevGesture = { ...T.gesture, stopAt: Math.min(T.gesture.stopAt ?? Infinity, t) }
      T.gesture = { action: prepare(base, o, T.seed, ++playsRef.current), start: t }
      currentRef.current.gesture = typeof gesture === 'string' ? gesture : gesture.name
      redraw()
    }

    const stop: Controls['stop'] = () => {
      const T = tl.current
      if (T.gesture && T.gesture.stopAt === undefined) T.gesture.stopAt = now()
      delete currentRef.current.gesture
      redraw()
    }

    const setExpression: Controls['setExpression'] = (name, intensity = 1) => {
      const base = EXPRESSIONS[name]
      if (!base) {
        console.warn(`useCharacter: no expression named "${name}"`)
        return
      }
      const T = tl.current
      T.prevExpression = T.expression
      T.expression = { action: intensity === 1 ? base : scaleAction(base, intensity, defaultPose()), start: now() }
      currentRef.current.expression = name
      redraw()
    }

    const say: Controls['say'] = (text, o) => {
      tl.current.talk = { action: talkAction(text, o), start: now() }
      currentRef.current.talking = true
      redraw()
    }

    const seek: Controls['seek'] = (t) => {
      epochRef.current = performance.now() - t * 1000
      render(t)
    }

    const setIdle: Controls['setIdle'] = (o) => {
      tl.current.idle = { ...tl.current.idle, ...o }
      redraw()
    }

    const setLife: Controls['setLife'] = (o) => {
      tl.current.life = o === 0 ? 0 : { ...(tl.current.life || {}), ...o }
      redraw()
    }

    const api = { play, stop, setExpression, say, seek, setClock: (m: Clock) => setMode(m), setIdle, setLife }
    return { api, render }
  }, [])

  useEffect(() => {
    if (mode !== 'auto') return
    let raf = 0
    epochRef.current = performance.now() - timeRef.current * 1000
    const tick = (nowMs: number) => {
      render((nowMs - epochRef.current) / 1000)
      raf = requestAnimationFrame(tick)
    }
    /* a hidden tab gets no frames; on return, continue from where we were
       rather than jumping past every gesture that was queued */
    const onVisibility = () => {
      if (document.hidden) cancelAnimationFrame(raf)
      else {
        epochRef.current = performance.now() - timeRef.current * 1000
        raf = requestAnimationFrame(tick)
      }
    }
    if (!document.hidden) raf = requestAnimationFrame(tick)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [mode, render])

  useEffect(() => {
    const id = opts.id
    if (!id) return
    const registry = (window.__actors ??= {})
    /* getters, so the harness reads the live pose right after a seek */
    registry[id] = {
      ...api,
      get pose() {
        return poseRef.current
      },
      get time() {
        return timeRef.current
      },
      get current() {
        return currentRef.current
      },
    }
    return () => {
      delete registry[id]
    }
  }, [opts.id, api])

  return { ...api, pose: frame.pose, time: frame.time, current: currentRef.current }
}
