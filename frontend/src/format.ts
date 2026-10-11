const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
export const money = (n: number | null | undefined) => (n == null ? '—' : usd.format(n))

export function shopDate(iso: string | undefined) {
  if (!iso) return { weekday: '', month: '', day: '', long: '' }
  const d = new Date(iso + 'T12:00:00')
  return {
    weekday: d.toLocaleDateString('en-US', { weekday: 'short' }),
    month: d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase(),
    day: String(d.getDate()),
    long: d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }),
  }
}

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit' })

export function elapsed(fromIso: string, toMs: number) {
  const s = Math.max(0, Math.round((toMs - new Date(fromIso).getTime()) / 1000))
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

/** Compact, readable tool arguments: check_stock(CC-TEE-WHITE · S · 1) */
export function argsLine(args: Record<string, unknown>): string {
  const skip = new Set(['agent', 'reason', 'body'])
  return Object.entries(args)
    .filter(([k]) => !skip.has(k))
    .map(([, v]) => {
      const s = typeof v === 'string' ? v : JSON.stringify(v)
      return s.length > 42 ? s.slice(0, 40) + '…' : s
    })
    .join(' · ')
}

export const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
