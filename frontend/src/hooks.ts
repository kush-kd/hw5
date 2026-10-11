import { useEffect, useRef, useState } from 'react'

/** Run `fn` now and every `ms` milliseconds (the latest `fn` is always used). */
export function useInterval(fn: () => void, ms: number) {
  const saved = useRef(fn)
  useEffect(() => {
    saved.current = fn
  }, [fn])
  useEffect(() => {
    saved.current()
    const id = setInterval(() => saved.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

/** A ticking clock, only while `active`. */
export function useNow(active: boolean, ms = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(id)
  }, [active, ms])
  return now
}

/** Smoothly animates a number toward `target` (used by the cash drawer).
 *  The first real value (when `target` stops being null) appears instantly. */
export function useTween(target: number | null, duration = 1100) {
  const [value, setValue] = useState(target ?? 0)
  const from = useRef<number | null>(target)
  useEffect(() => {
    if (target === null) return
    const begin = from.current
    if (begin === null) {
      from.current = target
      setValue(target)
      return
    }
    if (begin === target) return
    const start = performance.now()
    let raf = 0
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      const v = begin + (target - begin) * eased
      setValue(v)
      from.current = v
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration])
  return value
}

/** A value persisted in localStorage (the approver's name). */
export function useStored(key: string, initial: string) {
  const [v, setV] = useState(() => localStorage.getItem(key) ?? initial)
  useEffect(() => {
    localStorage.setItem(key, v)
  }, [key, v])
  return [v, setV] as const
}
