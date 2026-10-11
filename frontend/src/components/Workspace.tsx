import { Armchair, FileText, History, Play, Radio, ScrollText, Timer } from 'lucide-react'
import { useMemo, useState } from 'react'
import { elapsed, money } from '../format'
import { useNow } from '../hooks'
import { STATUS, ticketType } from '../meta'
import { feed, seats as seatsOf, type RunView } from '../runs'
import type { Ticket, TicketDetail } from '../types'
import { Debrief, Drafts } from './Debrief'
import { LiveFloor } from './LiveFloor'
import { TeamStrip } from './TeamStrip'

type Tab = 'floor' | 'debrief' | 'drafts'

interface Props {
  ticket: Ticket | null
  detail: TicketDetail | null
  runs: RunView[]
  busyTicket: number | null
  starting: boolean
  onStart: (id: number) => void
  preferTab?: Tab | null
}

export function Workspace({ ticket, detail, runs, busyTicket, starting, onStart, preferTab = null }: Props) {
  const current = runs.filter((r) => !r.beforeLastReset)
  const latest = current.at(-1) ?? null
  const [pickedRun, setPickedRun] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('floor')

  const run = runs.find((r) => r.runId === pickedRun) ?? latest
  const running = run?.status === 'running'
  const now = useNow(running)
  const items = useMemo(() => feed(run), [run])
  const seats = useMemo(() => seatsOf(run), [run])

  // New ticket or a new run started: follow the newest run on the live floor.
  // When that run finishes, flip to the debrief so the summary is front and centre.
  // (React's "adjust state when a prop changes" pattern: compare with the last seen value during render.)
  const followKey = `${ticket?.id}:${latest?.runId ?? ''}`
  const [seen, setSeen] = useState({ key: followKey, status: latest?.status })
  if (seen.key !== followKey) {
    setSeen({ key: followKey, status: latest?.status })
    setPickedRun(null)
    setTab(preferTab ?? (latest?.status === 'completed' ? 'debrief' : 'floor'))
  } else if (seen.status !== latest?.status) {
    setSeen({ key: followKey, status: latest?.status })
    if (latest?.status === 'completed' && !pickedRun && !preferTab) setTab('debrief')
  }

  if (!ticket) return <section className="workspace empty-state"><Armchair size={28} /> Opening the back office…</section>

  const type = ticketType(ticket.type)
  const st = STATUS[ticket.status] ?? STATUS.open
  const someoneBusy = busyTicket !== null
  const busyHere = busyTicket === ticket.id
  const linked = detail?.linked_invoice ?? detail?.linked_lease

  return (
    <section className="workspace" aria-label={`Ticket ${ticket.id}`}>
      <div className="ws-head">
        <div className="ws-title">
          <span className="type-chip" style={{ ['--tint' as string]: type.tint }}><type.Icon size={13} /> {type.label}</span>
          <h1>
            <span className="ticket-no big">#{ticket.id}</span> {ticket.subject}
          </h1>
          <div className="ws-meta">
            <span>from <b>{ticket.requester}</b></span>
            {ticket.sku && <span>{ticket.qty} × {ticket.sku} · size {ticket.size}</span>}
            {detail?.linked_invoice && <span>invoice #{String(detail.linked_invoice.id)} · {money(detail.linked_invoice.amount as number)}</span>}
            {detail?.linked_lease && <span>lease #{String(detail.linked_lease.id)} · {money(detail.linked_lease.monthly_rent as number)}/mo</span>}
            {!linked && !ticket.sku && <span>no linked records</span>}
          </div>
        </div>

        <div className="ws-actions">
          <span className={`status-pill ${st.tone} lg`}>{busyHere && <span className="live-dot" />}{busyHere ? 'Team at work' : st.label}</span>
          <button
            className="primary-btn"
            onClick={() => onStart(ticket.id)}
            disabled={someoneBusy || starting}
            title={someoneBusy && !busyHere ? `The team is busy on ticket #${busyTicket}` : undefined}
          >
            {busyHere || starting ? <Radio size={16} className="pulse" /> : <Play size={16} />}
            {busyHere ? 'Team is on it' : starting ? 'Calling the team…' : current.length ? 'Run the team again' : 'Start the team'}
          </button>
          {run && (
            <span className="run-timer">
              <Timer size={13} /> {running ? elapsed(run.startedAt, now) : run.endedAt ? elapsed(run.startedAt, new Date(run.endedAt).getTime()) : '—'}
            </span>
          )}
        </div>
      </div>

      <TeamStrip seats={seats} />

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'floor'} className={tab === 'floor' ? 'on' : ''} onClick={() => setTab('floor')}>
          <Radio size={14} /> Live floor {running && <span className="live-dot" />}
        </button>
        <button role="tab" aria-selected={tab === 'debrief'} className={tab === 'debrief' ? 'on' : ''} onClick={() => setTab('debrief')}>
          <ScrollText size={14} /> Debrief
        </button>
        <button role="tab" aria-selected={tab === 'drafts'} className={tab === 'drafts' ? 'on' : ''} onClick={() => setTab('drafts')}>
          <FileText size={14} /> Drafts & notes {detail?.drafts.length ? <span className="count">{detail.drafts.length}</span> : null}
        </button>
        {runs.length > 0 && (
          <label className="run-pick">
            <History size={13} />
            <select value={run?.runId ?? ''} onChange={(e) => setPickedRun(e.target.value || null)} aria-label="Choose a run">
              {!latest && <option value="">No run since the last reset</option>}
              {[...runs].reverse().map((r, i) => (
                <option key={r.runId} value={r.runId}>
                  {i === 0 && !r.beforeLastReset ? 'Latest run' : `Run ${runs.length - i}`} · {new Date(r.startedAt).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                  {r.beforeLastReset ? ' · before reset' : ''} · {r.status}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="tab-body">
        {!run && tab !== 'drafts' ? (
          <div className="empty-state inner">
            <Armchair size={26} />
            <p><b>The team hasn’t looked at this one yet.</b></p>
            <p className="muted">Press <b>Start the team</b>. The Boss reads the ticket and pulls in only the specialists it needs. You’ll watch every step here.</p>
          </div>
        ) : tab === 'floor' ? (
          <LiveFloor items={items} running={running} />
        ) : tab === 'debrief' ? (
          <Debrief run={run} seats={seats} />
        ) : (
          <Drafts drafts={detail?.drafts ?? []} notes={detail?.notes ?? []} />
        )}
      </div>
    </section>
  )
}
