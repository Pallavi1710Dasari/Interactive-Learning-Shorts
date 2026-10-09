/* The declarative face of the rig, for decks:
 *   <Actor character="riya" expression="happy" gesture="wave" say="Hi there" />
 * Props are the whole interface. A changed `gesture` plays it, a changed
 * `say` speaks it, and `time` switches to the manual clock so a deck that
 * drives its own timeline gets the exact pose for that instant. */
import { useEffect, useMemo, type JSX } from 'react'
import { buildSkin, PRESETS, type CharacterConfig } from '../skins/config'
import { Character } from './Character'
import { useCharacter, type IdleOptions, type PlayOptions } from './useCharacter'

export type ActorProps = {
  character: 'arjun' | 'riya' | CharacterConfig
  expression?: string
  intensity?: number
  gesture?: string
  gestureOptions?: PlayOptions
  say?: string
  idle?: IdleOptions
  width?: number
  seed?: number
  className?: string
  /** manual clock: the pose at this time, for decks that drive their own timeline */
  time?: number
}

export function Actor(props: ActorProps): JSX.Element {
  const { character, expression, intensity, gesture, gestureOptions, say, idle, width, seed, className, time } = props

  /* A config written inline is a new object every render; its JSON is not,
     so the skin (hair paths, gradients) is rebuilt only when it really changes. */
  const skinKey = typeof character === 'string' ? character : JSON.stringify(character)
  const skin = useMemo(() => buildSkin(typeof character === 'string' ? PRESETS[character] : character), [skinKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const manual = time !== undefined
  const c = useCharacter({ seed, clock: manual ? 'manual' : 'auto', idle })
  const { setClock, seek, setIdle, setExpression, play, stop, say: speak } = c

  useEffect(() => setClock(manual ? 'manual' : 'auto'), [manual, setClock])
  useEffect(() => {
    if (time !== undefined) seek(time)
  }, [time, seek])

  const idleKey = JSON.stringify(idle ?? {})
  useEffect(() => {
    if (idle) setIdle(idle)
  }, [idleKey, setIdle]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (expression) setExpression(expression, intensity)
  }, [expression, intensity, setExpression])

  const optionsKey = JSON.stringify(gestureOptions ?? {})
  useEffect(() => {
    if (gesture) play(gesture, gestureOptions)
    else stop()
  }, [gesture, optionsKey, play, stop]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (say) speak(say)
  }, [say, speak])

  return <Character pose={c.pose} skin={skin} width={width} className={className} />
}
