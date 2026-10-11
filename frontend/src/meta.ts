import {
  Building2, Calculator, Crown, House, Inbox, MessageCircleHeart, Package, Shirt, Tag,
  type LucideIcon,
} from 'lucide-react'
import type { AgentKey, TicketStatus } from './types'

export interface AgentMeta {
  key: AgentKey
  name: string
  role: string
  voice: string // how this agent "sounds" on the floor
  color: string
  soft: string
  Icon: LucideIcon
}

export const AGENTS: Record<AgentKey, AgentMeta> = {
  boss: {
    key: 'boss', name: 'Boss', role: 'Routes tickets, makes the call', voice: 'decides',
    color: '#0b3a6f', soft: '#e5edf7', Icon: Crown,
  },
  inventory: {
    key: 'inventory', name: 'Inventory', role: 'Stock, shortfalls, vendors', voice: 'counts',
    color: '#2f7a57', soft: '#e4f2ea', Icon: Package,
  },
  accounting: {
    key: 'accounting', name: 'Accounting', role: 'Cash, invoices, approvals', voice: 'tallies',
    color: '#a36f1c', soft: '#f7ecd9', Icon: Calculator,
  },
  facilities: {
    key: 'facilities', name: 'Facilities', role: 'Lease, rent, landlord', voice: 'checks',
    color: '#2a6d84', soft: '#e1eff4', Icon: Building2,
  },
  customer_service: {
    key: 'customer_service', name: 'Customer Service', role: 'Drafts replies, never sends', voice: 'writes',
    color: '#b04468', soft: '#f8e5ec', Icon: MessageCircleHeart,
  },
}

export const AGENT_ORDER: AgentKey[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export const TICKET_TYPES: Record<string, { label: string; Icon: LucideIcon; tint: string }> = {
  customer_order: { label: 'Customer order', Icon: Shirt, tint: '#2f7a57' },
  rent_notice: { label: 'Rent notice', Icon: House, tint: '#2a6d84' },
  price_override: { label: 'Discount request', Icon: Tag, tint: '#b04468' },
}
export const ticketType = (t: string) => TICKET_TYPES[t] ?? { label: t.replace(/_/g, ' '), Icon: Inbox, tint: '#5b6475' }

export const STATUS: Record<TicketStatus, { label: string; tone: 'idle' | 'live' | 'wait' | 'bad' | 'ok' }> = {
  open: { label: 'On the board', tone: 'idle' },
  in_progress: { label: 'Team at work', tone: 'live' },
  waiting_on_approval: { label: 'Waiting on you', tone: 'wait' },
  blocked: { label: 'Blocked', tone: 'bad' },
  resolved: { label: 'Resolved', tone: 'ok' },
}

export const APPROVAL_KINDS: Record<string, string> = {
  invoice: 'Vendor invoice',
  rent: 'Rent',
  purchase_order: 'Purchase order',
  discount: 'Price approval',
}
