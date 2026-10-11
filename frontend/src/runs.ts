// Turns the raw audit-trail events into runs, agent states, and a readable feed.

import { AGENT_ORDER } from './meta'
import type { AgentEvent, AgentKey, AgentReport, TicketDecision, ToolCall } from './types'

export type RunStatus = 'running' | 'completed' | 'failed' | 'interrupted'

export interface RunView {
  runId: string
  ticketId: number
  startedAt: string
  endedAt: string | null
  status: RunStatus
  events: AgentEvent[]
  decision: TicketDecision | null
  error: string | null
  beforeLastReset: boolean
}

export function lastResetSeq(events: AgentEvent[]) {
  let seq = -1
  for (const e of events) if (e.event === 'db_reset') seq = e.seq
  return seq
}

export function runsForTicket(events: AgentEvent[], ticketId: number, activeRunId: string | null): RunView[] {
  const resetSeq = lastResetSeq(events)
  const byRun = new Map<string, AgentEvent[]>()
  for (const e of events) {
    if (e.run_id === 'dashboard') continue
    const list = byRun.get(e.run_id) ?? []
    list.push(e)
    byRun.set(e.run_id, list)
  }
  const runs: RunView[] = []
  for (const [runId, evs] of byRun) {
    const start = evs.find((e) => e.event === 'ticket_run_start')
    if (!start || start.ticket_id !== ticketId) continue
    const end = evs.find((e) => e.event === 'ticket_run_end')
    const err = evs.find((e) => e.event === 'ticket_run_error')
    runs.push({
      runId,
      ticketId,
      startedAt: start.logged_at,
      endedAt: (end ?? err)?.logged_at ?? null,
      status: end ? 'completed' : err ? 'failed' : runId === activeRunId ? 'running' : 'interrupted',
      events: evs,
      decision: (end?.output as TicketDecision | null) ?? null,
      error: err?.said ?? null,
      beforeLastReset: start.seq < resetSeq,
    })
  }
  return runs.sort((a, b) => a.startedAt.localeCompare(b.startedAt))
}

export type SeatState = 'idle' | 'working' | 'done' | 'skipped'

export interface Seat {
  agent: AgentKey
  state: SeatState
  toolCalls: number
  delegationsIn: number
  lastSaid: string | null
}

export function seats(run: RunView | null): Seat[] {
  return AGENT_ORDER.map((agent) => {
    if (!run) return { agent, state: 'idle' as SeatState, toolCalls: 0, delegationsIn: 0, lastSaid: null }
    const mine = run.events.filter((e) => e.agent === agent)
    const starts = mine.filter((e) => e.event === 'agent_start').length
    const ends = mine.filter((e) => e.event === 'agent_end').length
    const responses = mine.filter((e) => e.event === 'model_response')
    const toolCalls = responses.reduce((n, e) => n + e.tools.filter((t) => t.tool !== 'final_result').length, 0)
    const delegationsIn = run.events.filter((e) => e.event === 'delegation' && e.tools[0]?.args?.to_agent === agent).length
    let state: SeatState = 'idle'
    if (starts > ends && run.status === 'running') state = 'working'
    else if (starts > 0) state = 'done'
    else if (run.status !== 'running') state = 'skipped'
    return { agent, state, toolCalls, delegationsIn, lastSaid: responses.at(-1)?.said ?? null }
  })
}

export type FeedItem =
  | { kind: 'start'; e: AgentEvent }
  | { kind: 'pickup'; e: AgentEvent }
  | { kind: 'think'; e: AgentEvent; calls: ToolCall[]; results: { tool: string; result: string }[] }
  | { kind: 'handoff'; e: AgentEvent; to: AgentKey; task: string }
  | { kind: 'refused'; e: AgentEvent }
  | { kind: 'report'; e: AgentEvent; report: AgentReport }
  | { kind: 'decision'; e: AgentEvent; decision: TicketDecision }
  | { kind: 'error'; e: AgentEvent }

export function feed(run: RunView | null): FeedItem[] {
  if (!run) return []
  const items: FeedItem[] = []
  const lastThink = new Map<string, Extract<FeedItem, { kind: 'think' }>>()
  for (const e of run.events) {
    const key = e.chain.join('>')
    switch (e.event) {
      case 'ticket_run_start':
        items.push({ kind: 'start', e })
        break
      case 'agent_start':
        if (e.depth > 0) items.push({ kind: 'pickup', e })
        break
      case 'model_response': {
        const item = { kind: 'think' as const, e, calls: e.tools, results: [] as { tool: string; result: string }[] }
        items.push(item)
        lastThink.set(key, item)
        break
      }
      case 'model_request': {
        const prev = lastThink.get(key)
        if (prev && e.tool_results.length) prev.results.push(...e.tool_results.filter((r) => r.tool !== 'delegate'))
        break
      }
      case 'delegation':
        items.push({ kind: 'handoff', e, to: e.tools[0]?.args?.to_agent as AgentKey, task: (e.said ?? '').replace(/^→ \w+: /, '') })
        break
      case 'delegation_refused':
        items.push({ kind: 'refused', e })
        break
      case 'final_output':
        if (e.agent !== 'boss' && e.output) items.push({ kind: 'report', e, report: e.output })
        break
      case 'ticket_run_end':
        if (e.output) items.push({ kind: 'decision', e, decision: e.output })
        break
      case 'ticket_run_error':
      case 'delegation_error':
      case 'budget_exceeded':
        items.push({ kind: 'error', e })
        break
    }
  }
  return items
}

/** Every report each agent filed in this run (an agent can be asked more than once). */
export function reports(run: RunView | null): Partial<Record<AgentKey, AgentReport[]>> {
  const out: Partial<Record<AgentKey, AgentReport[]>> = {}
  for (const e of run?.events ?? []) {
    if (e.event === 'final_output' && e.agent && e.agent !== 'boss' && e.output) (out[e.agent] ??= []).push(e.output)
  }
  return out
}
