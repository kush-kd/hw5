// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentKey = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'
export type TicketStatus = 'open' | 'in_progress' | 'waiting_on_approval' | 'blocked' | 'resolved'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: TicketStatus
  notes: string | null
  created_at: string
  pending_approvals: number
  purchase_orders: number
  drafts: number
  is_resolved: boolean
  state: 'open' | 'resolved'
  agents_running: boolean
}

export interface Note { id: number; ticket_id: number; agent: string; note: string; shop_date: string }
export interface Draft { id: number; ticket_id: number; recipient: string; subject: string; body: string; author: string; status: string; shop_date: string }
export interface PurchaseOrder { id: number; vendor_id: number; sku: string; size: string; qty: number; unit_cost: number; total: number; status: string; eta: string | null; approval_id: number | null }

export interface Approval {
  id: number
  ticket_id: number | null
  kind: 'invoice' | 'rent' | 'purchase_order' | 'discount'
  ref_id: number | null
  amount: number
  details: Record<string, unknown> | null
  requested_by: string
  reason: string
  status: 'pending' | 'paid' | 'approved' | 'rejected'
  depends_on: number | null
  shop_date: string
  decided_by: string | null
  decision_note: string | null
  payment_id: number | null
}

export interface TicketDetail {
  found: boolean
  date_today: string
  ticket: Ticket
  linked_lease: Record<string, unknown> | null
  linked_invoice: Record<string, unknown> | null
  notes: Note[]
  approvals: Approval[]
  purchase_orders: PurchaseOrder[]
  drafts: Draft[]
}

export interface Payment { id: number; kind: string; ref_id: number; amount: number; account: string; paid_at: string; approved_by: string }

export interface Cash {
  account: string
  balance: number
  balance_as_of: string
  date_today: string
  pending_total: number
  available_after_pending: number
  payments_made: Payment[]
}

export interface TicketDecision {
  ticket_id: number
  final_status: TicketStatus
  decision: string
  rationale: string
  agents_consulted: AgentKey[]
  approval_ids: number[]
  purchase_order_ids: number[]
  draft_ids: number[]
  human_actions_required: string[]
  next_steps: string[]
}

export interface AgentReport {
  agent: AgentKey
  ticket_id: number
  summary: string
  facts: { statement: string; source_tool: string }[]
  actions_taken: string[]
  approval_ids: number[]
  purchase_order_ids: number[]
  draft_ids: number[]
  blockers: string[]
  recommendations: string[]
  needs_human: boolean
}

export interface Run {
  run_id: string
  ticket_id: number
  status: 'running' | 'completed' | 'failed'
  started_at: string
  finished_at: string | null
  decision: TicketDecision | null
  error: string | null
}

export interface ToolCall { tool: string; args: Record<string, unknown> }

export interface AgentEvent {
  seq: number
  event_id: string
  logged_at: string
  run_id: string
  ticket_id: number | null
  agent: AgentKey | null
  chain: string[]
  depth: number
  step: number | null
  event: string
  said: string | null
  tools: ToolCall[]
  tool_results: { tool: string; result: string }[]
  model: string | null
  output: (AgentReport & TicketDecision) | null
}
