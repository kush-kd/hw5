import { FileText, Hourglass, Inbox, PackageOpen } from 'lucide-react'
import { STATUS, ticketType } from '../meta'
import type { Ticket } from '../types'

export function TicketBoard({ tickets, selected, onSelect, loading }: { tickets: Ticket[]; selected: number | null; onSelect: (id: number) => void; loading: boolean }) {
  const resolved = tickets.filter((t) => t.status === 'resolved').length
  return (
    <aside className="board" aria-label="Ticket board">
      <div className="col-head">
        <div>
          <span className="eyebrow">The board</span>
          <h2>Open tickets</h2>
        </div>
        <div className="tally" title="Resolved tickets">
          <b>{resolved}</b>/{tickets.length} resolved
        </div>
      </div>

      <div className="cards">
        {loading && [0, 1, 2].map((i) => <div key={i} className="index-card skeleton" aria-hidden />)}
        {!loading && tickets.length === 0 && <div className="empty-mini"><Inbox size={18} /> Nothing on the board.</div>}
        {tickets.map((t, i) => {
          const type = ticketType(t.type)
          const st = STATUS[t.status] ?? STATUS.open
          return (
            <button
              key={t.id}
              className={`index-card ${selected === t.id ? 'selected' : ''} tone-${st.tone}`}
              style={{ ['--tint' as string]: type.tint, ['--tilt' as string]: `${[-0.6, 0.5, -0.3][i % 3]}deg` }}
              onClick={() => onSelect(t.id)}
              aria-pressed={selected === t.id}
            >
              <span className="pin" aria-hidden />
              <div className="card-top">
                <span className="type-chip"><type.Icon size={13} /> {type.label}</span>
                <span className="ticket-no">#{t.id}</span>
              </div>
              <div className="card-subject">{t.subject}</div>
              <div className="card-requester">from {t.requester}</div>
              {t.sku && (
                <div className="card-ask">
                  <PackageOpen size={13} /> {t.qty} × {t.sku} · {t.size}
                </div>
              )}
              {t.notes && <div className="card-note">“{t.notes}”</div>}
              <div className="card-foot">
                <span className={`status-pill ${st.tone}`}>
                  {t.agents_running && <span className="live-dot" />}
                  {t.agents_running ? 'Team at work' : st.label}
                </span>
                <span className="card-counts">
                  {t.pending_approvals > 0 && (
                    <span title="Approvals waiting on you"><Hourglass size={12} /> {t.pending_approvals}</span>
                  )}
                  {t.drafts > 0 && (
                    <span title="Drafts (not sent)"><FileText size={12} /> {t.drafts}</span>
                  )}
                </span>
              </div>
              {t.status === 'resolved' && <span className="stamp" aria-label="Resolved">Resolved</span>}
            </button>
          )
        })}
      </div>

      <p className="board-foot">
        Tickets are worked one at a time. Every run plans against the same cash drawer.
      </p>
    </aside>
  )
}
