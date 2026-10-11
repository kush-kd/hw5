import { BookOpen, Check, ChevronDown, Lock, PenLine, Stamp, X } from 'lucide-react'
import { useState } from 'react'
import { money } from '../format'
import { APPROVAL_KINDS, AGENTS } from '../meta'
import type { Approval, Cash } from '../types'

interface Props {
  pending: Approval[]
  history: Approval[]
  cash: Cash | null
  selectedTicket: number | null
  signer: string
  setSigner: (s: string) => void
  onApprove: (a: Approval) => Promise<void>
  onReject: (a: Approval, reason: string) => Promise<void>
}

export function ApprovalsDesk({ pending, history, cash, selectedTicket, signer, setSigner, onApprove, onReject }: Props) {
  const ordered = [...pending].sort((a, b) => Number(b.ticket_id === selectedTicket) - Number(a.ticket_id === selectedTicket) || a.id - b.id)
  const cashOut = pending.filter((a) => a.amount > 0).reduce((n, a) => n + a.amount, 0)
  return (
    <aside className="inbox" id="approvals" aria-label="Approvals">
      <div className="col-head">
        <div>
          <span className="eyebrow">Your signature</span>
          <h2>Approvals</h2>
        </div>
        <div className="tally">{pending.length} waiting · {money(cashOut)}</div>
      </div>

      <label className="signer">
        <PenLine size={14} />
        <span>Signing as</span>
        <input value={signer} onChange={(e) => setSigner(e.target.value)} placeholder="your name" aria-label="Your name" />
      </label>

      <div className="checks">
        {pending.length === 0 && (
          <div className="empty-mini inbox-empty">
            <Stamp size={18} />
            <div>
              <b>Nothing to sign.</b>
              <span>When an agent prepares a payment, purchase order, or price change, it lands here. Nothing moves until you sign.</span>
            </div>
          </div>
        )}
        {ordered.map((a) => (
          <Cheque
            key={a.id}
            a={a}
            cash={cash}
            pending={pending}
            highlight={a.ticket_id === selectedTicket}
            signer={signer}
            setSigner={setSigner}
            onApprove={onApprove}
            onReject={onReject}
          />
        ))}
      </div>

      <Ledger history={history} cash={cash} />
    </aside>
  )
}

function Cheque({
  a, cash, pending, highlight, signer, setSigner, onApprove, onReject,
}: { a: Approval; cash: Cash | null; pending: Approval[]; highlight: boolean; signer: string; setSigner: Props['setSigner']; onApprove: Props['onApprove']; onReject: Props['onReject'] }) {
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const d = (a.details ?? {}) as Record<string, string | number>
  const isDiscount = a.kind === 'discount'
  const balance = cash?.balance ?? 0
  const after = balance - a.amount
  const blocker = a.depends_on ? pending.find((p) => p.id === a.depends_on) : undefined
  const short = !isDiscount && a.amount > balance
  const lockReason = blocker
    ? `Sign #${blocker.id} first. The vendor won't ship until that invoice is paid.`
    : short
      ? `Not enough cash: ${money(a.amount)} needed, ${money(balance)} in checking. The pay tool would refuse.`
      : !signer.trim()
        ? 'Type your name on the signature line to sign.'
        : null
  const by = AGENTS[a.requested_by as keyof typeof AGENTS]

  return (
    <article className={`cheque ${isDiscount ? 'price' : ''} ${highlight ? 'hl' : ''}`}>
      <div className="cheque-top">
        <span className="cheque-kind">{APPROVAL_KINDS[a.kind] ?? a.kind}</span>
        <span className="cheque-no">No. {String(a.id).padStart(4, '0')} · ticket #{a.ticket_id}</span>
      </div>

      {isDiscount ? (
        <div className="price-line">
          <div className="price-big">{money(Number(d.proposed_unit_price))}<small>/unit</small></div>
          <div className="price-meta">
            {d.qty} × {String(d.sku)} · {d.discount_pct_vs_list}% off {money(Number(d.list_price))}
            <br />margin {d.gross_margin_pct}% · no cash moves
          </div>
        </div>
      ) : (
        <>
          <div className="payee">
            <span>Pay to the order of</span>
            <b>{String(d.payee ?? '—')}</b>
          </div>
          <div className="amount-row">
            <div className="amount-box">{money(a.amount)}</div>
            <div className="after">
              checking after signing
              <b className={after < 0 ? 'bad' : ''}>{money(after)}</b>
            </div>
          </div>
          <div className="cheque-detail">
            {a.kind === 'invoice' && <>Invoice #{d.invoice_id} · due {d.due_date}{Number(d.days_overdue) > 0 && <em> · {d.days_overdue} days overdue</em>}</>}
            {a.kind === 'rent' && <>{String(d.space_name)} · due {d.due_date} ({d.days_until_due} days)</>}
            {a.kind === 'purchase_order' && <>PO #{d.purchase_order_id} · {d.qty} × {String(d.sku)} {String(d.size)} @ {money(Number(d.unit_cost))} · ETA {String(d.eta_if_paid_today)} if paid today</>}
          </div>
        </>
      )}

      <div className="memo"><span>Memo</span> {a.reason}</div>
      <div className="requested">prepared by <b style={{ color: by?.color }}>{by?.name ?? a.requested_by}</b> · shop date {a.shop_date}</div>

      {lockReason && (
        <div className="lock"><Lock size={12} /> {lockReason}</div>
      )}

      {rejecting ? (
        <div className="reject-form">
          <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why not? (recorded on the ticket)" />
          <button className="ghost-btn sm" onClick={() => setRejecting(false)}>Cancel</button>
          <button
            className="danger-btn sm"
            disabled={!reason.trim() || !signer.trim() || busy}
            onClick={async () => {
              setBusy(true)
              try { await onReject(a, reason.trim()) } finally { setBusy(false); setRejecting(false) }
            }}
          >
            <X size={13} /> Reject
          </button>
        </div>
      ) : (
        <div className="sign-row">
          <label className="sig-line">
            <span className="sr-only">Your signature (your name)</span>
            <input className="sig-input" value={signer} onChange={(e) => setSigner(e.target.value)} placeholder="sign here: type your name" />
          </label>
          <button className="ghost-btn sm" onClick={() => setRejecting(true)} disabled={busy}>Reject</button>
          <button
            className="sign-btn"
            disabled={!!lockReason || busy}
            onClick={async () => {
              setBusy(true)
              try { await onApprove(a) } finally { setBusy(false) }
            }}
          >
            <Check size={14} /> {busy ? 'Signing…' : isDiscount ? 'Approve price' : 'Sign & pay'}
          </button>
        </div>
      )}
    </article>
  )
}

function Ledger({ history, cash }: { history: Approval[]; cash: Cash | null }) {
  const [open, setOpen] = useState(true)
  const payments = cash?.payments_made ?? []
  if (history.length === 0 && payments.length === 0) return null
  return (
    <section className="ledger">
      <button className="ledger-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <BookOpen size={14} /> Ledger <span className="muted">· {payments.length} payment{payments.length === 1 ? '' : 's'}</span>
        <ChevronDown size={14} className={open ? 'rot' : ''} />
      </button>
      {open && (
        <ol>
          {[...history].reverse().map((h) => (
            <li key={h.id} className={`ledger-row ${h.status}`}>
              <span className="l-kind">{APPROVAL_KINDS[h.kind]}</span>
              <span className="l-who">#{h.id} · {String(h.details?.payee ?? h.details?.sku ?? '')}</span>
              <span className="l-amt">{h.kind === 'discount' ? '—' : `−${money(h.amount)}`}</span>
              <span className="l-status">{h.status}{h.decided_by ? ` · ${h.decided_by}` : ''}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
