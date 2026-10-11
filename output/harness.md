# Harness

This is the complete harness for **Campus Customs Multi-Agent Operations**. The sections below were written one problem at a time; this overview ties them together.

## At a glance (final)

| Piece | Where | Summary | Details |
|---|---|---|---|
| **Tables** | `data/campus_customs.db` (original, never written), `data/campus_customs_new.db` (working copy) | 9 shop tables: `desk`, `tickets`, `inventory`, `pricing`, `vendors`, `invoices`, `leases`, `cash_accounts`, `payments`. The MCP server adds 4 work tables to the working copy only: `ticket_notes`, `approvals`, `purchase_orders`, `drafts`. | Problems 2 and 5 |
| **MCP tools** | `mcp_server/server.py` (FastMCP) | 19 tools. **Read (11):** `list_tickets`, `list_open_tickets`, `get_ticket`, `check_stock`, `list_inventory`, `get_vendor_status`, `get_lease_due`, `get_cash_position`, `get_invoice`, `check_margin`, `list_approvals`. **Agent writes, no cash (6):** `add_ticket_note`, `set_ticket_status`, `save_draft_message`, `request_payment`, `create_purchase_order`, `request_discount_approval`. **Human only (2):** `human_approve_and_pay` (the pay tool), `human_reject_request`. | Problems 3, 5 and 7; `mcp_server/README.md` |
| **Five agents** | `backend/agents/*.py`, `backend/prompts/*.md`, `backend/team.py` | PydanticAI agents: Boss, Inventory, Accounting, Facilities and Customer Service. They're fully connected through `delegate`, and each sees only its own allowlist of MCP tools. Every turn runs on **Opus 5.5 (`claude-opus-5-5`) through the Claude subscription** (`backend/llm/claude_subscription.py`). | Problem 5 |
| **API routes** | `backend/main.py` (FastAPI, `uvicorn main:app --reload --port 8000`) | Tickets, run a ticket, runs, events, approvals (approve and reject), cash, reset, health. Approving is the only path that moves cash. | Problem 7 |
| **Dashboard** | `frontend/` (React + Vite + TS, `npm run dev`, port 5173) | A back-office desk: index-card ticket board, team table and live floor, debrief, drafts, signed cheques, and the cash drawer. | Problem 8; `output/design.md` |
| **Safety** | MCP tools, prompts, backend | Human-signed payments only, no negative cash, amounts read from the database, the vendor-invoice rule enforced in code, nothing ever sent, least privilege, one shop clock, an append-only audit trail, and token limits. | Problem 5 *Safety*, plus the Problem 9 additions |
| **Audit trail** | `output/audit_trail.json` | Append-only. Records every agent-loop step, delegation, human approval and reset. | Problems 5 and 9 |

## Problem 2: Database — `data/campus_customs.db`

- **Original:** `data/campus_customs.db`. Never written to; it's the reset point.
- **Working copy:** `data/campus_customs_new.db`, a byte-identical copy (checked with `cmp`). The MCP server and backend read and write only this file. To reset, copy the original over it again.

The database has 9 tables. None of them has an `orders`, `customers` or `purchase_orders` table. Cash only goes out; no table records revenue.

### `desk` (1 row): the shop's clock

| Field | Type | Why it matters |
|---|---|---|
| `date_today` | TEXT | "Today" for the shop (**2026-08-31**). Every agent uses this, not the real clock, to decide what is due or overdue and to work out arrival dates. |
| `notes` | TEXT | Free-text desk notes (currently empty). |

**Why it matters:** this table is the shared clock. Boss and Accounting need it to rank urgency, and Inventory needs it for restock ETAs.

### `tickets` (3 rows): the work board

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER, PK | Ticket number shown on the dashboard. |
| `type` | TEXT | `customer_order` / `rent_notice` / `price_override`. Boss uses it as the first hint for which agent to route the ticket to. |
| `requester` | TEXT | Who asked (customer, landlord, student org). Customer Service addresses its draft to them. |
| `subject` | TEXT | Short title for the board. |
| `sku` / `size` / `qty` | TEXT / TEXT / INTEGER | What the ticket wants. Inventory looks these up in `inventory`. |
| `lease_id` | INTEGER, FK → `leases.id` | Links rent tickets to a lease, for Facilities. |
| `invoice_id` | INTEGER, FK → `invoices.id` | Links a ticket to a vendor bill, for Accounting. |
| `status` | TEXT | All three are `open`. Agents move tickets toward resolved or waiting for approval. |
| `notes` | TEXT | The request in plain words. |
| `created_at` | TEXT (ISO, -04:00) | When the ticket landed. Used for ordering on the board. |

**Why it matters:** this is the queue Boss reads. Each ticket's foreign keys show which agents and tables it touches.

### `inventory` (10 rows): stock by SKU and size

| Field | Type | Why it matters |
|---|---|---|
| `sku` | TEXT, PK part | Product key. It shares values with `pricing.sku`, but no foreign key is declared. |
| `name` | TEXT | Display name for drafts and the dashboard. |
| `size` | TEXT, PK part | Stock is tracked per size (S/M/L/XL, or `OS` for one size). |
| `qty` | INTEGER | Units on hand. This is the number Inventory checks for shortfalls. |
| `location` | TEXT | Aisle in the shop. |

**Why it matters:** this is Inventory's main table. `(sku, size)` is the primary key, so each SKU and size has exactly one row.

### `pricing` (4 rows): cost and list price per SKU

| Field | Type | Why it matters |
|---|---|---|
| `sku` | TEXT, PK | Joins to `inventory.sku`. |
| `unit_cost` | REAL | What a restock costs per unit. Used to size purchase orders. |
| `list_price` | REAL | Normal selling price. Accounting uses it to work out margin before approving any discount. |

**Why it matters:** this table supports Accounting's margin checks for discount requests and the cost of restock purchase orders.

### `vendors` (3 rows): who can restock

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER, PK | Referenced by `invoices.vendor_id`. |
| `name` | TEXT | Vendor name used in purchase-order drafts. |
| `specialty` | TEXT | `apparel reprint` / `mugs and small goods` / `local courier`. **No table links a SKU to a vendor**, so Inventory has to match the product type to this field. |
| `lead_days` | INTEGER | Days from order to arrival. Per the shop rules, ETA = `date_today` + `lead_days`. |

**Why it matters:** Inventory uses it to pick a vendor and give an ETA. Accounting checks whether that vendor is blocked by an unpaid invoice.

### `invoices` (1 row): money owed to vendors

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER, PK | Referenced by `tickets.invoice_id`. |
| `vendor_id` | INTEGER, FK → `vendors.id` | Which vendor is owed. |
| `amount` | REAL | Amount due. |
| `due_date` | TEXT | Compared with `desk.date_today` to decide whether the invoice is overdue. |
| `status` | TEXT | `open` means unpaid. **A vendor with an open invoice won't ship.** A payment should flip this to paid. |
| `description` | TEXT | What the bill was for. |

**Why it matters:** Accounting's payables list. It is also the gate that decides whether a vendor will ship.

### `leases` (1 row): the shop space

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER, PK | Referenced by `tickets.lease_id`. |
| `space_name` | TEXT | Chapel Street shop. |
| `landlord` | TEXT | Elm City Properties, which is also the requester on ticket 102. |
| `monthly_rent` | REAL | $2,400. |
| `next_due` | TEXT | 2026-09-02. A rent payment should move this forward one month. |
| `notes` | TEXT | Free text. |

**Why it matters:** Facilities' table, which shows what rent is owed and when.

### `cash_accounts` (1 row): money available

| Field | Type | Why it matters |
|---|---|---|
| `name` | TEXT, PK | `checking`. |
| `balance` | REAL | **$3,400**. The pay tool must refuse any payment larger than this, so the balance never goes negative. |
| `date` | TEXT | Date the balance was last updated. |

**Why it matters:** Accounting's hard limit. With no revenue coming in, this is all the money the team can spend.

### `payments` (0 rows): record of approved payments

| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER, PK | Payment number. |
| `kind` | TEXT | What was paid, e.g. `invoice`, `rent`, or a purchase order. |
| `ref_id` | INTEGER | ID of the thing paid (`invoices.id`, `leases.id`, …). It points to a different table depending on `kind`, so no foreign key is declared. |
| `amount` | REAL | Cash out. |
| `account` | TEXT | Which `cash_accounts.name` was charged. |
| `paid_at` | TEXT | Payment date. |
| `approved_by` | TEXT | **The human approver.** A payment row should never exist without one, which is the human-approval rule. |

**Why it matters:** this is the audit trail. Each payment writes one row here, lowers `cash_accounts.balance`, and updates the invoice or lease it paid.

### How the three open tickets link to the other tables

**Ticket 101: customer order** (Tauhid Zaman, 1× `CC-TEE-WHITE` size S)
- `inventory`: CC-TEE-WHITE size S has **qty 0**, so there's a shortfall of 1.
- Vendor: a tee is apparel, so **Bulldog Print Co** (id 1, `lead_days` 5).
- `tickets.invoice_id = 501` → `invoices` 501: Bulldog Print Co is owed **$840**, due 2026-08-28. It's **open and 3 days overdue**, and was for "Rush reprint CC-TEE-WHITE S."
- So Bulldog Print Co won't ship until #501 is paid. After that, a 1-unit restock costs 1 × $8 = $8, and the earliest arrival is 2026-08-31 + 5 days = **2026-09-05**.
- Agents involved: Boss → Inventory (shortfall, vendor) → Accounting (pay #501, purchase order) → Customer Service (draft to Tauhid with the ETA).

**Ticket 102: rent notice** (Elm City Properties)
- `tickets.lease_id = 1` → `leases` 1: Chapel Street shop, **$2,400** due **2026-09-02**. That's 2 days from now, so not yet overdue.
- Agents involved: Boss → Facilities (confirm lease, amount, due date) → Accounting (prepare the rent payment for approval).

**Ticket 103: price override** (Yale AI Club, 20× `CC-HOOD-NAVY` size M, bulk discount)
- `inventory`: CC-HOOD-NAVY size M has **qty 8**, so there's a shortfall of **12**.
- `pricing`: cost $22, list $58. At list price, 20 hoodies come to $1,160 with a margin of about 62%. Any discount has to keep the price above the $22 cost.
- Vendor: also **Bulldog Print Co**, so it's **blocked by invoice #501** too. Restocking 12 costs 12 × $22 = **$264**.
- Agents involved: Boss → Inventory (shortfall) → Accounting (margin check, purchase order) → Boss (final call on the discount) → Customer Service (draft to the club).

**Cash constraint across all three tickets** (balance $3,400):

| Step | Cash out | Balance after |
|---|---|---|
| Pay invoice #501 (unblocks Bulldog Print Co) | $840 | $2,560 |
| Pay rent (lease 1) | $2,400 | **$160** |
| Purchase order: 1 tee size S | $8 | $152 |
| Purchase order: 12 hoodies size M | $264 | ✗ refused, not enough cash |

Not everything fits. Paying the invoice and the rent leaves $160, which doesn't cover restocking 12 hoodies. Boss has to rank the tickets, and the pay tool has to refuse anything that would make the balance negative.

### Open questions for later problems (answered later)
- **Where purchase orders and drafts live:** in new work tables in the working copy (`purchase_orders`, `drafts`, plus `approvals` and `ticket_notes`), created by the MCP server. See Problem 5.
- **Whether a purchase order costs cash right away:** it's queued for human approval, and approving it *is* the payment (cash out, then the PO is `ordered` with ETA = shop date + lead days). It can't be paid while the vendor still has an open invoice. See Problem 5.

## Problem 3: MCP server — `mcp_server/server.py`

The server is built with FastMCP. It opens `data/campus_customs_new.db` read-only and takes "today" from `desk.date_today` (2026-08-31). Every value a tool returns is a database field or simple arithmetic on database fields. A missing row returns `found: false` instead of a guess. All three tools were tested through an in-memory FastMCP client, and the database file's checksum was the same before and after.

### Tool 1: `check_stock(sku, size, qty_needed=1)`
- **Reads:** `inventory` (qty, location, name) joined to `pricing` (unit_cost, list_price).
- **Unlocks:** **101** and **103**.
- **Why it's the right tool:** it compares a ticket's `sku`/`size`/`qty` against `inventory` and costs the gap from `pricing`, which proves ticket 101's CC-TEE-WHITE size S is at 0 (short 1, $8 to restock) and ticket 103's CC-HOOD-NAVY size M has 8 of 20 (short 12, $264 to restock, $22 cost vs. $58 list as the discount floor).

### Tool 2: `get_vendor_status(vendor_id=None)`
- **Reads:** `vendors` (specialty, lead_days), `invoices` (open rows per vendor), `desk` (date_today).
- **Unlocks:** **101** and **103**.
- **Why it's the right tool:** both shortfalls need the apparel vendor Bulldog Print Co (5-day lead time), and the tool shows its open invoice #501 ($840, due 2026-08-28, 3 days overdue) sets `will_ship_now` to false, so neither ticket's restock can ship until #501 is paid, with the earliest arrival on 2026-09-05.

### Tool 3: `get_lease_due(lease_id, account="checking")`
- **Reads:** `leases` (monthly_rent, next_due, landlord), `desk` (date_today), `cash_accounts` (balance).
- **Unlocks:** **102**.
- **Why it's the right tool:** ticket 102 links to `lease_id` 1, and the tool confirms the $2,400 Chapel Street rent owed to Elm City Properties is due 2026-09-02 (2 days away, not yet overdue) and that the $3,400 checking balance covers it with $1,000 left, which is what Facilities and Accounting need to prepare a rent payment for human approval without paying anything.

## Problem 4: Connect the MCP server to the vibe coder

**Connection:** `.mcp.json` at the project root registers the server for Claude Code:

```json
{ "mcpServers": { "campus-customs": { "type": "stdio", "command": ".venv/bin/python",
  "args": ["mcp_server/server.py"], "env": { "CAMPUS_CUSTOMS_DB": "data/campus_customs_new.db" } } } }
```

Claude Code starts the server over stdio from the project root. Its tools show up as `mcp__campus-customs__check_stock`, `mcp__campus-customs__get_vendor_status`, and `mcp__campus-customs__get_lease_due`.

**Smoke test:** `scripts/mcp_smoke_test.py` writes the evidence to `output/mcp_smoke.json`. It sends each test prompt to Claude Code (`claude -p`, Opus 5.5 on the subscription) with `.mcp.json` loaded and only the tool under test allowed. Each run also gets one line of shop context (`shop_context` in the JSON): "today" is `desk.date_today`, not the computer's clock, as the shop rules say. From the stream it records the tool name, the tool input, the raw tool output, and Claude Code's reply. It then re-reads the same fields directly from `data/campus_customs_new.db` (read-only) and checks each one.

| Test | Tool | Key output | Matches DB |
|---|---|---|---|
| Ticket 101 | `check_stock` | CC-TEE-WHITE size S: 0 on hand, short 1, $8 cost / $28 list | ✓ |
| Ticket 103 | `check_stock` | CC-HOOD-NAVY size M: 8 on hand of 20, short 12, $264 to restock | ✓ |
| Tickets 101, 103 | `get_vendor_status` | Bulldog Print Co blocked by open invoice #501 ($840, 3 days overdue); ETA 2026-09-05 once paid | ✓ |
| Ticket 102 | `get_lease_due` | Lease 1: $2,400 due 2026-09-02 (2 days away); checking $3,400 covers it | ✓ |

`all_tools_match_db: true`. The database checksum was the same before and after the run.

## Problem 5: The agent team and the grown MCP server

### Architecture

```
run_team.py ─► Team (backend/team.py)
                 ├─ 5 PydanticAI agents (backend/agents/*.py, prompts in backend/prompts/*.md)
                 │     model: Opus 5.5 (claude-opus-5-5) via Claude subscription (backend/llm/claude_subscription.py)
                 │     toolsets: [MCP server filtered to that agent's allowlist, delegate]
                 └─ one MCP stdio connection ─► mcp_server/server.py ─► data/campus_customs_new.db
```

- **Agent loop:** each agent is a PydanticAI `Agent` run with `agent.iter()`. PydanticAI owns the loop: model turn → tool calls (MCP or `delegate`) → tool results → next model turn, until the agent calls its output tool and returns a validated `AgentReport` or `TicketDecision` (`backend/models.py`).
- **Model:** `backend/llm/claude_subscription.py` is a PydanticAI `FunctionModel`. Each turn it sends the agent's prompt, its tool schemas and the conversation so far to `claude -p --model claude-opus-5-5`, with Claude Code's own tools and MCP turned off. A JSON schema forces the reply to `{reasoning, tool_calls[]}`, and the reply becomes PydanticAI tool calls. API-key variables are removed from the child process, so it always runs on the subscription. The audit trail's `models_used` field confirms every call ran on `claude-opus-5-5`.
- **No bypass:** agents have no database access of their own. Every shop fact and every change goes through an MCP tool. Even the orchestrator's "which tickets are open?" is the MCP call `list_open_tickets`.
- **Full connectivity:** every agent has `delegate(to_agent, task)` and can call any of the other four. The callee runs its own loop and returns its report as the tool result. Three limits keep this from looping forever:
  - no delegating to yourself
  - no delegating to an agent already up the chain (no A → B → A)
  - a maximum depth of 2

### The five agents

| Agent | File / prompt | MCP tools it can see | Output | Limits (turns / tool calls) |
|---|---|---|---|---|
| **Boss**: reads each ticket, routes work, makes the final call, sets status | `agents/boss.py`, `prompts/boss.md` | `list_open_tickets`, `get_ticket`, `get_cash_position`, `list_approvals`, `add_ticket_note`, `set_ticket_status` | `TicketDecision` | 14 / 24 |
| **Inventory**: stock by SKU and size, shortfalls, alternatives, which vendor can restock, ETA | `agents/inventory.py`, `prompts/inventory.md` | `get_ticket`, `check_stock`, `list_inventory`, `get_vendor_status`, `add_ticket_note` | `AgentReport` | 8 / 16 |
| **Accounting**: cash, invoices, margins, and payment, PO and discount approval requests | `agents/accounting.py`, `prompts/accounting.md` | `get_ticket`, `get_cash_position`, `get_invoice`, `get_vendor_status`, `get_lease_due`, `check_margin`, `list_approvals`, `request_payment`, `create_purchase_order`, `request_discount_approval`, `add_ticket_note` | `AgentReport` | 10 / 20 |
| **Facilities**: leases, rent notices (checked against the lease), the landlord | `agents/facilities.py`, `prompts/facilities.md` | `get_ticket`, `get_lease_due`, `get_cash_position`, `add_ticket_note` | `AgentReport` | 6 / 12 |
| **Customer Service**: drafts messages to requesters; never sends | `agents/customer_service.py`, `prompts/customer_service.md` | `get_ticket`, `check_stock`, `list_inventory`, `save_draft_message`, `add_ticket_note` | `AgentReport` | 6 / 12 |

Every agent also has `delegate`. Each prompt covers:
- the agent's role and scope (what it owns, and what it hands off and to whom)
- the shop rules that apply to it
- when to use each tool
- a step-by-step procedure
- its policies, such as cash priority, the discount guideline, vendor matching and the fraud check
- guardrails
- budget discipline
- the exact output contract

### Every MCP tool and the tables it uses

| Tool | Type | Tables read (R) / written (W) | Used by |
|---|---|---|---|
| `list_tickets` | read | tickets, approvals, purchase_orders, drafts, desk (R) | backend `/api/tickets` (dashboard board), added in Problem 7 |
| `list_open_tickets` | read | tickets (R), desk (R) | Boss, orchestrator |
| `get_ticket` | read | tickets, leases, invoices, vendors, desk, ticket_notes, approvals, purchase_orders, drafts (R) | all agents |
| `check_stock` | read | inventory, pricing (R) | Inventory, Customer Service |
| `list_inventory` | read | inventory (R) | Inventory, Customer Service |
| `get_vendor_status` | read | vendors, invoices, desk (R) | Inventory, Accounting |
| `get_lease_due` | read | leases, desk, cash_accounts (R) | Facilities, Accounting |
| `get_cash_position` | read | cash_accounts, approvals, payments, desk (R) | Boss, Accounting, Facilities |
| `get_invoice` | read | invoices, vendors, approvals, desk (R) | Accounting |
| `check_margin` | read | pricing (R) | Accounting |
| `list_approvals` | read | approvals (R) | Boss, Accounting |
| `add_ticket_note` | write | ticket_notes (W) | all agents |
| `set_ticket_status` | write | tickets (W), approvals (R), ticket_notes (W) | Boss only (the tool also checks `agent == "boss"`); `resolved` notes any approvals still waiting on the human |
| `save_draft_message` | write | drafts (W), ticket_notes (W) | Customer Service |
| `request_payment` | write | invoices or leases, cash_accounts, approvals (R), approvals (W), ticket_notes (W) | Accounting |
| `create_purchase_order` | write | vendors, invoices, inventory, pricing (R), purchase_orders, approvals, ticket_notes (W) | Accounting |
| `request_discount_approval` | write | pricing (R), approvals, ticket_notes (W) | Accounting |
| `human_approve_and_pay` | **human only** | approvals, cash_accounts, invoices, leases, purchase_orders, payments, ticket_notes (W) | dashboard (later problem); no agent |
| `human_reject_request` | **human only** | approvals, purchase_orders, ticket_notes (W) | dashboard (later problem); no agent |

**New tables in the working copy:** the MCP server adds four tables at startup with `CREATE TABLE IF NOT EXISTS`:
- `ticket_notes`: the team's shared memory per ticket.
- `approvals`: the human-approval queue.
- `purchase_orders`
- `drafts`: never sent.

They exist only in `campus_customs_new.db`; `scripts/reset_db.py` restores the original and drops them.

**How approval and payment work:**
1. An agent requests something. That creates an `approvals` row with status `pending`, and no money moves.
2. The human approves it with `human_approve_and_pay`, which is the pay tool. In one transaction it:
   - checks the cash covers the amount, and refuses otherwise
   - for a purchase order, checks the vendor has no open invoices
   - inserts a `payments` row with `approved_by`
   - lowers `cash_accounts.balance`
   - updates the item that was paid: invoice → `paid`, the lease's `next_due` moves forward one month, or the PO → `ordered` with its ETA
   - marks the approval `paid`

### Audit trail: `output/audit_trail.json`

- **Format:** a JSON array. `backend/audit.py` appends one event at a time with an atomic write, and **never wipes earlier runs**.
- **Fields on every event:** `event_id`, `logged_at` (UTC), `run_id`, `ticket_id`, `agent`, `chain` (who delegated to whom), `depth`, `step`, `event`, `data`.
- **Events per agent-loop step:**
  - `agent_start`: the prompt, the agent's MCP allowlist and its limits.
  - `model_request`: the inputs to the turn, meaning the task and the **tool results** from the previous turn.
  - `model_response`: the model's `reasoning`, the **tool calls with their arguments**, token usage, latency, and `models_used`.
  - `delegation`, `delegation_result`, `delegation_refused`, `delegation_error`.
  - `final_output`: the validated report or decision.
  - `agent_end`.
- **Events per ticket:** `ticket_run_start`, `ticket_run_end` (the decision and the per-ticket budget used), and `ticket_run_error`.
- **Database side:** every change is also recorded in `ticket_notes`.

### Safety

**Guardrails for real customers and real money:**
1. **Humans approve all money.** Agents can only *request*. The pay tool is human-only in three ways:
   - it isn't in any agent's toolset
   - it needs `HUMAN_APPROVAL_KEY`, which the agents' MCP server process isn't given
   - it records who approved
2. **No negative cash.** The pay tool refuses anything over the balance. `request_payment` refuses amounts above the balance, and Accounting won't queue requests that exceed `available_after_pending`, which counts approvals already queued on other tickets.
3. **Amounts come from the database, not the model.** Invoice and rent amounts, and PO unit costs, are read by the tools, so an agent can't mistype or inflate a payment.
4. **Vendor rule enforced in code.** POs to a vendor with an open invoice are refused unless that invoice's payment is queued, and they can't be paid before it.
5. **Prices are protected.** Discounts below unit cost or above list price are refused; every discount needs human approval; and the Boss's policy caps bulk discounts at 15% off list with gross margin at or above 45%.
6. **Nothing is sent.** Customer Service only saves drafts (`sent: false`). There's no email or vendor-contact tool anywhere.
7. **No internal data in customer messages.** Cash, costs, margins and vendor problems are banned from drafts by the Customer Service prompt.
8. **Fraud check.** Facilities checks every rent notice against `leases` (landlord, amount, due date). A mismatch blocks payment.
9. **Least privilege and no bypass.** Each agent sees only its allowlisted MCP tools. Only the Boss can change ticket status. "Resolved" means the agents have finished; it never pays anything, and pending approvals stay in the human's queue. The database is reached only through MCP.
10. **One clock.** The shop date is `desk.date_today` everywhere.
11. **Duplicate protection.** The tools refuse a second pending request for the same invoice or lease.
12. **Full audit.** Every step and every database change is logged and attributable to an agent, and every payment to a named human.

**Limits that keep token use in check:**
- One model for everything: Opus 5.5 through the subscription. Claude Code's default system prompt, built-in tools and MCP are disabled on each call, so the only prompt is the agent's own. That prompt is identical on every turn, so it gets cached.
- Per-agent caps on model turns and tool calls (see the agent table). PydanticAI `UsageLimits` enforces them.
- Per ticket: at most 10 delegations and 45 model requests across the specialists. Delegation depth is capped at 2, and cycles are refused.
- At most 4 tool calls per turn, batched in parallel. Reasoning is at most 60 words per turn. Each tool result is truncated at 6,000 characters before it goes back to the model.
- Prompts tell each agent its usual number of turns, not to repeat calls, and to finish as soon as it has what it needs.
- Each model call times out after 240 seconds, with at most 2 attempts.

## Problem 7: Backend routes (`backend/main.py`, FastAPI)

**Start:** from `backend/`, with the venv active (`source ../.venv/bin/activate`), run `uvicorn main:app --reload --port 8000`. The API is at `http://localhost:8000`, and CORS is open to the Vite dashboard on `localhost:5173`.

**MCP connections:** every route that touches shop data goes through MCP, using two connections:
- The **desk** connection serves these routes. Its server process holds the human-approval key, which is generated per backend start or taken from `HUMAN_APPROVAL_KEY`.
- The **agent team's** connection is separate, and its server process has no key.

**Routes:**
- `GET /api/tickets`: all three tickets with their status, `state` (open or resolved), pending approvals, POs, drafts, and whether agents are running on each one.
- `GET /api/tickets/{ticket_id}`: one ticket with its linked lease or invoice, and the notes, approvals, purchase orders and drafts on it.
- `POST /api/tickets/{ticket_id}/run`: starts the agent team on that ticket in the background and returns a `run_id` (HTTP 202). Returns 409 if a run is already going, since runs share one cash pool and must not overlap.
- `GET /api/runs` / `GET /api/runs/{run_id}`: the status of agent runs (running, completed or failed), with the Boss's final decision.
- `GET /api/events?after=&limit=&ticket_id=&run_id=`: recent agent events from `output/audit_trail.json`. Each one shows who acted, what they said (reasoning, delegation task or final summary), the tools they called and their results, so the board can poll with `after=next_after`.
- `GET /api/approvals?status=pending`: the human-approval queue: invoice, rent, purchase-order and discount requests.
- `POST /api/approvals/{approval_id}/approve` (body `{"approved_by": "name"}`): the human approves. For cash requests this calls the MCP pay tool, which is **the only route that changes cash**. It writes a payments row with the approver, lowers the balance, and updates the invoice, lease or PO. If cash would go negative, or the vendor still has an open invoice, it refuses with 409 and nothing moves.
- `POST /api/approvals/{approval_id}/reject` (body `{"rejected_by", "reason"}`): the human rejects. No cash moves, and a rejected PO is cancelled.
- `GET /api/cash`: the current checking balance from `cash_accounts`, plus the total pending approval and what's available after pending.
- `POST /api/reset`: restores `data/campus_customs_new.db` from the untouched original for a fresh run. Refused (409) while agents are running. The audit trail is kept.
- `GET /api/health`: liveness check, the database in use, and the active run.

**Logged by the backend:** approvals, rejections and resets are written to the audit trail as `human_approval`, `human_rejection` and `db_reset`.

**Tested through HTTP:**
- reset → tickets (all open) → cash $3,400
- run ticket 102: the Boss sent work to Facilities and then Accounting, and rent approval #1 ended up pending
- a second run while busy → 409; a reset while busy → 409
- approving with an empty name → 422
- approving #1 → paid: cash $3,400 → $1,000, payment row approved by "Kush Dhall", lease next due → 2026-10-02
- approving the same request again → 409
- a reset at the end restored $3,400 with nothing pending and no payments

## Problem 8: The React dashboard (`frontend/`)

**Start:** run `npm install` once, then `npm run dev` in `frontend/`. It opens `http://localhost:5173`. The board calls the FastAPI backend at `http://localhost:8000` (`VITE_API_BASE`), and the backend's CORS allows `http://localhost:5173`. The design rationale is in `output/design.md`.

**What the board calls:**
- `GET /api/tickets`, `/api/cash`, `/api/approvals` (pending and all) and `/api/runs`: every 1.5s while agents are working, 4s when idle.
- `GET /api/events?after=…`: every 1s while working. The Live floor and the Debrief are rebuilt from these audit-trail events.
- `GET /api/tickets/{id}`: drafts and notes for the selected ticket.
- `POST /api/tickets/{id}/run`: "Start the team".
- `POST /api/approvals/{id}/approve` / `reject`: "Sign & pay" and "Reject".
- `POST /api/reset`: "Reset shop".

**Change made for this problem: "resolved" now means the agents have finished.** The dashboard has to mark a ticket resolved when the run finishes. So `set_ticket_status` now accepts `resolved` even while approvals are pending, and records how many are still waiting. The Boss prompt makes `resolved` the normal end of a run (`blocked` if the team can't finish). Resolving a ticket never moves money: pending approvals stay in the human's inbox, and the pay tool still needs a human signature. This differs from the end state written in `output/desk_tickets.html` (Problem 6), which expected `waiting_on_approval`. The plan was written before this requirement.

**Tested in the browser:**
- From a fresh reset, "Start the team" on #101:
  - seats lit up live (Facilities stayed "Not needed")
  - the feed showed reasoning, MCP tool receipts and handoffs
  - cheques for invoice 501 ($840) and PO 1 ($8, locked behind "Sign #1 first") appeared during the run
  - when it finished, the card was stamped RESOLVED and the view flipped to the Debrief
- Signing #1 as "Kush Dhall": the drawer counted from $3,400.00 to $2,560.00, the ledger recorded the payment, and the PO cheque unlocked.
- "Reset shop" restored $3,400.00 and all three tickets to open.
- `tsc`, `oxlint` and `vite build` are clean, and the browser console has no errors.

## Problem 9: Full run over the three tickets

**Procedure:**
1. `POST /api/reset` restored `data/campus_customs_new.db` from the original. Starting checking was **$3,400.00**.
2. The agent team ran on 101 → 102 → 103, one at a time, through `POST /api/tickets/{id}/run` (the same route as the dashboard's Start button). Each ticket ended `resolved`.
3. The human (Kush) signed every request in the React dashboard: #1 invoice 501 $840 → #2 PO 1 $8 → #3 rent $2,400 → #4 price approval for 8 hoodies at $49.30 (no cash).
4. `scripts/build_reports.py` built the reports from the audit trail and the shop data. It fills the Actual and Cash tabs in `output/desk_tickets.html` and writes `output/resolved_tickets.json`.
5. `scripts/build_resolved_board.py` built `output/resolved_board.html`, with 2× screenshots of the React board per ticket (Debrief and Live floor). They were captured with headless Chrome from `http://localhost:5173/#ticket=<id>&tab=<tab>`.

**Results (from the audit trail):**

| Ticket | Boss called first | Delegations | MCP tool calls | Model turns | Cash change | Human approvals |
|---|---|---|---|---|---|---|
| 101 | Inventory | Inventory → Accounting → Customer Service | 19 | 16 | $-848.00 | #1 paid, #2 paid |
| 102 | Facilities | Facilities → Accounting | 13 | 12 | $-2,400.00 | #3 paid |
| 103 | Inventory | Inventory → Accounting → Accounting → Customer Service | 25 | 19 | $0.00 | #4 approved (no cash) |

**Cash:** $3,400.00 − $840.00 − $8.00 − $2,400.00 = **$152.00**. That equals `cash_accounts` in the working database (**$152.00**) and `GET /api/cash`. The 12-hoodie restock ($264) was correctly **not** requested: only $152 was free after the approvals queued for 101 and 102.

**Plan vs. actual (Problem 6):**
- **Matched for every ticket:** the first agent called, the Boss's delegations in order, no specialist-to-specialist delegations, the specialists that weren't needed (Facilities on 101 and 103; Inventory and Customer Service on 102), every planned MCP tool, and none of the tools the plan ruled out.
- **The one difference:** the final status is `resolved` rather than `waiting_on_approval`, because of the Problem 8 change to what "resolved" means.

**Models:** every one of the 47 agent turns in this run used only `claude-opus-5-5`, with **0 model violations**.

**Issue found and fixed during Problem 9:**
- **What happened:** the first full run went through the backend, which had been launched with the desktop app's environment. In that setup the Claude CLI added a background `claude-haiku-4-5` call to most agent turns. The main answers were still Opus.
- **How it was caught:** while building the resolved board, which lists the models used per run.
- **The fix, in two parts:**
  1. `backend/llm/claude_subscription.py` now gives the `claude` child process only an allowlist of variables (HOME, PATH, USER, LOGNAME, SHELL, TMPDIR, LANG, LC_ALL).
  2. `backend/team.py` checks `models_used` on every turn and logs a `model_violation` event if anything other than `claude-opus-5-5` appears.
- **Then:** the database was reset and all three tickets were re-run and re-signed.
- **The earlier runs stay in the audit trail**, which is append-only by design. The reports use only the latest run after the last reset.

**Safety additions from this problem (on top of the Problem 5 list):**
- The model is pinned in code and checked at runtime (`model_violation`). The model subprocess gets a minimal environment, so no API keys, proxies or app variables leak into it.
- Approvals in the dashboard need a typed signature name, and that name is what's recorded in `payments.approved_by`. A purchase order can't be signed before the invoice it depends on.
- Reports are generated from recorded data (the audit trail plus the database) and cross-check the cash three ways (computed, `cash_accounts`, API) before anything is published.
