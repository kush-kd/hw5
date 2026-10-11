import { useCallback, useMemo, useRef, useState } from 'react'
import { api, ApiError, API_BASE } from './api'
import { ApprovalsDesk } from './components/ApprovalsDesk'
import { Header } from './components/Header'
import { TicketBoard } from './components/TicketBoard'
import { Toasts, type Toast } from './components/Toasts'
import { Workspace } from './components/Workspace'
import { money } from './format'
import { useInterval, useStored } from './hooks'
import { APPROVAL_KINDS } from './meta'
import { runsForTicket } from './runs'
import type { AgentEvent, Approval, Cash, Run, Ticket, TicketDetail } from './types'

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [pending, setPending] = useState<Approval[]>([])
  const [history, setHistory] = useState<Approval[]>([])
  const [runs, setRuns] = useState<{ active_run: string | null; runs: Run[] }>({ active_run: null, runs: [] })
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  // Deep links: #ticket=102&tab=debrief opens that ticket on that tab.
  const [link] = useState(() => new URLSearchParams(location.hash.slice(1)))
  const [selected, setSelectedRaw] = useState<number | null>(() => Number(link.get('ticket')) || null)
  const setSelected = (id: number) => {
    setSelectedRaw(id)
    window.history.replaceState(null, '', `#ticket=${id}`)
  }
  const [starting, setStarting] = useState(false)
  const [offline, setOffline] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [signer, setSigner] = useStored('cc-signer', '')
  const cursor = useRef<number | null>(null)
  const lastActive = useRef<string | null>(null)

  const toast = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setToasts((ts) => [...ts, { ...t, id }])
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 6500)
  }, [])

  const activeRun = runs.active_run ? runs.runs.find((r) => r.run_id === runs.active_run) ?? null : null
  const busyTicket = activeRun?.ticket_id ?? null
  const fast = busyTicket !== null

  // ---- polling ---------------------------------------------------------------------------
  const refreshDesk = useCallback(async () => {
    try {
      const [t, c, p, all, r] = await Promise.all([api.tickets(), api.cash(), api.approvals('pending'), api.approvals('all'), api.runs()])
      setTickets(t.tickets)
      setCash(c)
      setPending(p.approvals)
      setHistory(all.approvals.filter((a) => a.status !== 'pending'))
      // Announce a run that just finished (kept outside the state updater, which StrictMode may call twice).
      const was = lastActive.current
      if (was && r.active_run !== was) {
        const done = r.runs.find((x) => x.run_id === was)
        if (done?.status === 'completed') toast({ tone: 'ok', title: `Ticket #${done.ticket_id} resolved`, body: done.decision?.decision })
        if (done?.status === 'failed') toast({ tone: 'bad', title: `Run on #${done.ticket_id} failed`, body: done.error ?? undefined })
      }
      lastActive.current = r.active_run
      setRuns(r)
      setSelectedRaw((s) => s ?? t.tickets[0]?.id ?? null)
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [toast])

  const refreshEvents = useCallback(async () => {
    try {
      const res = await api.events(cursor.current ?? undefined)
      if (res.events.length) {
        // Merge by seq so overlapping polls (e.g. StrictMode's double mount) never duplicate events.
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.seq))
          return [...prev, ...res.events.filter((e) => !seen.has(e.seq))]
        })
        cursor.current = Math.max(cursor.current ?? -1, res.next_after ?? -1)
      } else if (cursor.current === null) {
        cursor.current = -1
      }
    } catch {
      /* the desk poll reports offline */
    }
  }, [])

  const refreshDetail = useCallback(async () => {
    if (selected === null) return
    try {
      setDetail(await api.ticket(selected))
    } catch {
      /* ignore */
    }
  }, [selected])

  useInterval(refreshDesk, fast ? 1500 : 4000)
  useInterval(refreshEvents, fast ? 1000 : 4000)
  useInterval(refreshDetail, fast ? 2500 : 5000)

  // ---- actions ---------------------------------------------------------------------------
  const start = async (id: number) => {
    setStarting(true)
    try {
      const run = await api.runTicket(id)
      lastActive.current = run.run_id
      setRuns((r) => ({ active_run: run.run_id, runs: [run, ...r.runs] }))
      toast({ tone: 'info', title: `The team is on ticket #${id}`, body: 'Watch the live floor. The Boss decides who to call.' })
      await Promise.all([refreshEvents(), refreshDesk()])
    } catch (e) {
      toast({ tone: 'bad', title: 'Could not start the team', body: (e as Error).message })
    } finally {
      setStarting(false)
    }
  }

  const approve = async (a: Approval) => {
    try {
      const res = await api.approve(a.id, signer.trim())
      if (a.kind === 'discount') toast({ tone: 'ok', title: `Price approved (#${a.id})`, body: 'No cash moved.' })
      else toast({ tone: 'ok', title: `Paid ${money(a.amount)} · ${APPROVAL_KINDS[a.kind]}`, body: `Checking is now ${money(res.new_balance as number)}. Signed by ${signer.trim()}.` })
    } catch (e) {
      const refused = e instanceof ApiError && e.status === 409
      toast({ tone: 'bad', title: refused ? 'The pay tool refused' : 'Approval failed', body: (e as Error).message })
    }
    await Promise.all([refreshDesk(), refreshDetail(), refreshEvents()])
  }

  const reject = async (a: Approval, reason: string) => {
    try {
      await api.reject(a.id, signer.trim(), reason)
      toast({ tone: 'info', title: `Rejected #${a.id}`, body: 'No cash moved.' })
    } catch (e) {
      toast({ tone: 'bad', title: 'Reject failed', body: (e as Error).message })
    }
    await Promise.all([refreshDesk(), refreshDetail(), refreshEvents()])
  }

  const reset = async () => {
    try {
      const r = await api.reset()
      toast({ tone: 'ok', title: 'Shop reset to opening morning', body: `All tickets are back on the board. Checking is ${money(r.balance)}.` })
    } catch (e) {
      toast({ tone: 'bad', title: 'Reset refused', body: (e as Error).message })
    }
    await Promise.all([refreshDesk(), refreshDetail(), refreshEvents()])
  }

  // ---- derived ---------------------------------------------------------------------------
  const ticket = tickets.find((t) => t.id === selected) ?? null
  const ticketRuns = useMemo(
    () => (selected === null ? [] : runsForTicket(events, selected, runs.active_run)),
    [events, selected, runs.active_run],
  )

  return (
    <div className="app">
      <Header cash={cash} busy={fast} onReset={reset} />
      {offline && (
        <div className="offline">
          Can’t reach the backend at <code>{API_BASE}</code>. Start it from <code>backend/</code> with <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}
      <main className="desk">
        <TicketBoard tickets={tickets} selected={selected} onSelect={setSelected} loading={cash === null && !offline} />
        <Workspace
          ticket={ticket}
          detail={detail?.ticket.id === selected ? detail : null}
          runs={ticketRuns}
          busyTicket={busyTicket}
          starting={starting}
          onStart={start}
          preferTab={(['floor', 'debrief', 'drafts'] as const).find((t) => t === link.get('tab')) ?? null}
        />
        <ApprovalsDesk
          pending={pending}
          history={history}
          cash={cash}
          selectedTicket={selected}
          signer={signer}
          setSigner={setSigner}
          onApprove={approve}
          onReject={reject}
        />
      </main>
      {pending.length > 0 && (
        <button className="sign-fab" onClick={() => document.getElementById('approvals')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
          ✍ {pending.length} waiting for your signature
        </button>
      )}
      <Toasts toasts={toasts} dismiss={(id) => setToasts((ts) => ts.filter((t) => t.id !== id))} />
    </div>
  )
}
