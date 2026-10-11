import type { AgentEvent, Approval, Cash, Run, Ticket, TicketDetail } from './types'

// The FastAPI backend. Override with VITE_API_BASE in frontend/.env if it runs elsewhere.
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, { headers: { 'content-type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(`Can't reach the backend at ${API_BASE}. Is uvicorn running?`, 0)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (body as { detail?: unknown }).detail
    throw new ApiError(typeof detail === 'string' ? detail : res.statusText, res.status)
  }
  return body as T
}

const post = <T>(path: string, body?: unknown) =>
  req<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  tickets: () => req<{ date_today: string; tickets: Ticket[] }>('/api/tickets'),
  ticket: (id: number) => req<TicketDetail>(`/api/tickets/${id}`),
  runTicket: (id: number) => post<Run>(`/api/tickets/${id}/run`),
  runs: () => req<{ active_run: string | null; runs: Run[] }>('/api/runs'),
  events: (after?: number) =>
    req<{ total: number; next_after: number | null; events: AgentEvent[] }>(
      after === undefined ? '/api/events?limit=1000' : `/api/events?after=${after}&limit=1000`,
    ),
  approvals: (status: 'pending' | 'all') =>
    req<{ count: number; approvals: Approval[] }>(`/api/approvals?status=${status === 'all' ? '' : status}`),
  approve: (id: number, approvedBy: string) =>
    post<Record<string, unknown>>(`/api/approvals/${id}/approve`, { approved_by: approvedBy }),
  reject: (id: number, rejectedBy: string, reason: string) =>
    post<Record<string, unknown>>(`/api/approvals/${id}/reject`, { rejected_by: rejectedBy, reason }),
  cash: () => req<Cash>('/api/cash'),
  reset: () => post<{ ok: boolean; balance: number }>('/api/reset'),
}
