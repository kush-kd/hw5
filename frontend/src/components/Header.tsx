import { RotateCcw, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { money, shopDate } from '../format'
import { useTween } from '../hooks'
import type { Cash } from '../types'

export function Header({ cash, busy, onReset }: { cash: Cash | null; busy: boolean; onReset: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false)
  const [resetting, setResetting] = useState(false)
  const d = shopDate(cash?.date_today)

  return (
    <header className="topbar">
      <div className="brand">
        <div className="monogram" aria-hidden>CC</div>
        <div>
          <div className="brand-name">Campus Customs</div>
          <div className="brand-sub">Back Office · Chapel Street, New Haven</div>
        </div>
      </div>

      <div className="calendar" title="The shop's date (desk.date_today). All due dates and ETAs are measured from this day.">
        <div className="cal-month">{d.month}</div>
        <div className="cal-day">{d.day}</div>
        <div className="cal-week">{d.weekday}</div>
      </div>
      <div className="calendar-caption">
        <span className="eyebrow">Shop date</span>
        <span>{d.long || 'Loading…'}</span>
      </div>

      <CashDrawer cash={cash} />

      <div className="topbar-actions">
        <span className="guard" title="Agents can only request payments. Cash moves only when you sign.">
          <ShieldCheck size={15} /> Human-signed payments only
        </span>
        <button className="ghost-btn" onClick={() => setConfirming(true)} disabled={busy} title={busy ? 'Wait for the agents to finish' : 'Reset the shop'}>
          <RotateCcw size={15} /> Reset shop
        </button>
      </div>

      {confirming && (
        <div className="modal-scrim" role="dialog" aria-modal="true" aria-labelledby="reset-title">
          <div className="modal">
            <h2 id="reset-title">Reset to opening morning?</h2>
            <p>
              This restores the original shop database. All three tickets go back on the board, approvals, purchase orders and drafts are
              cleared, and checking returns to <b>$3,400.00</b>.
            </p>
            <p className="muted">The audit trail is kept. It is append-only, so earlier runs stay on record.</p>
            <div className="modal-actions">
              <button className="ghost-btn" onClick={() => setConfirming(false)} disabled={resetting}>Keep working</button>
              <button
                className="primary-btn"
                disabled={resetting}
                onClick={async () => {
                  setResetting(true)
                  try {
                    await onReset()
                  } finally {
                    setResetting(false)
                    setConfirming(false)
                  }
                }}
              >
                <RotateCcw size={15} /> {resetting ? 'Resetting…' : 'Reset the shop'}
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}

function CashDrawer({ cash }: { cash: Cash | null }) {
  const balance = cash?.balance ?? 0
  const shown = useTween(cash ? balance : null)
  const prev = useRef<number | null>(null)
  const [flash, setFlash] = useState<'down' | 'up' | null>(null)

  useEffect(() => {
    if (prev.current !== null && prev.current !== balance) {
      setFlash(balance < prev.current ? 'down' : 'up')
      const t = setTimeout(() => setFlash(null), 1600)
      prev.current = balance
      return () => clearTimeout(t)
    }
    prev.current = balance
  }, [balance])

  const pending = cash?.pending_total ?? 0
  const pct = balance > 0 ? Math.min(100, (pending / balance) * 100) : 0
  const over = (cash?.available_after_pending ?? 0) < 0

  return (
    <div className={`drawer ${flash ? `flash-${flash}` : ''}`} aria-live="polite">
      <div className="drawer-top">
        <span className="eyebrow">Checking</span>
        <span className="drawer-note">no revenue modelled · cash only goes out</span>
      </div>
      <div className="drawer-balance">{cash ? money(shown) : '—'}</div>
      <div className="drawer-bar" aria-hidden>
        <div className="drawer-bar-pending" style={{ width: `${pct}%` }} />
      </div>
      <div className="drawer-legend">
        <button className="drawer-link" onClick={() => document.getElementById('approvals')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
          <i className="dot pending" /> {money(pending)} awaiting your signature
        </button>
        <span className={over ? 'bad' : ''}><i className="dot free" /> {money(cash?.available_after_pending)} free after</span>
      </div>
    </div>
  )
}
