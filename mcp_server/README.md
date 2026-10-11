# Campus Customs MCP server

## What it's for

This server, built with **FastMCP**, is the single toolbox the Campus Customs agent team uses: Boss, Inventory, Accounting, Facilities and Customer Service. Agents never open SQLite themselves. Every shop fact they read and every change they make goes through a tool here, so every agent sees the same numbers, and those numbers always come from the database. If a row doesn't exist, a tool returns `found: false` or `ok: false` with an error message instead of making up an answer. Payment amounts are always read from the database, never taken from the caller.

## Database file

- **Uses:** `data/campus_customs_new.db`, the working copy. Set `CAMPUS_CUSTOMS_DB` to point it somewhere else.
- **Never touched:** `data/campus_customs.db`, the original. To reset, run `python scripts/reset_db.py`.
- **Today:** taken from `desk.date_today` (2026-08-31), never from the computer's clock.
- **Extra tables:** on startup the server adds `ticket_notes`, `approvals`, `purchase_orders` and `drafts` to the working copy, if they're missing. The original database never has them.

## Tools

### Read

| Tool | Tables | Returns |
|---|---|---|
| `list_tickets()` | tickets, approvals, purchase_orders, drafts, desk | Every ticket (open or resolved) with its status and counts of pending approvals, POs and drafts |
| `list_open_tickets()` | tickets, desk | Every ticket that isn't resolved, oldest first |
| `get_ticket(ticket_id)` | tickets, leases, invoices, vendors, desk, ticket_notes, approvals, purchase_orders, drafts | The ticket, its linked lease or invoice, and all work recorded on it |
| `check_stock(sku, size, qty_needed=1)` | inventory, pricing | Quantity on hand, shortfall, location, unit cost, list price, and the cost to restock the shortfall |
| `list_inventory(sku=None)` | inventory | Every size of a SKU (or the whole shop), for alternatives |
| `get_vendor_status(vendor_id=None)` | vendors, invoices, desk | Specialty, lead time, ETA if ordered today, open invoices with days overdue, and `will_ship_now` |
| `get_lease_due(lease_id, account="checking")` | leases, desk, cash_accounts | Rent amount, due date, days until due, and whether cash covers it |
| `get_cash_position(account="checking")` | cash_accounts, approvals, payments, desk | Balance, pending cash-out approvals, available after pending, and payments made |
| `get_invoice(invoice_id)` | invoices, vendors, approvals, desk | Amount, due date, days overdue, status, and existing payment requests |
| `check_margin(sku, unit_price, qty=1)` | pricing | Revenue, cost, gross margin ($ and %), discount versus list, and `below_cost` |
| `list_approvals(status="pending")` | approvals | The human-approval queue |

### Agent writes (nothing here moves cash)

| Tool | Tables | Does |
|---|---|---|
| `add_ticket_note(ticket_id, agent, note)` | ticket_notes | Records a finding on the ticket |
| `set_ticket_status(ticket_id, status, agent, reason)` | tickets, approvals, ticket_notes | Boss only. `resolved` = the agents are done; any pending approvals stay in the human queue and are noted. |
| `save_draft_message(ticket_id, recipient, subject, body, agent)` | drafts, ticket_notes | Saves a **draft**. Nothing is ever sent. |
| `request_payment(ticket_id, kind, ref_id, agent, reason)` | invoices / leases, cash_accounts, approvals, ticket_notes | Queues an invoice or rent payment for human approval, with the amount taken from the database. Refuses duplicates and amounts over the balance. |
| `create_purchase_order(ticket_id, vendor_id, sku, size, qty, agent, reason)` | vendors, invoices, inventory, pricing, purchase_orders, approvals, ticket_notes | Drafts a restock PO and queues it for approval. Refused for a vendor with an open invoice unless that invoice's payment is already queued. |
| `request_discount_approval(ticket_id, sku, qty, unit_price, agent, reason)` | pricing, approvals, ticket_notes | Queues a discounted price for approval. Refused below cost or above list price. |

### Human only (never given to agents; requires `HUMAN_APPROVAL_KEY`)

| Tool | Tables | Does |
|---|---|---|
| `human_approve_and_pay(approval_id, approved_by, approval_key)` | approvals, cash_accounts, payments, invoices, leases, purchase_orders, ticket_notes | **The pay tool.** Refuses if cash would go negative, or if a PO's vendor still has an open invoice. Otherwise it writes a `payments` row, lowers the balance, and marks the invoice paid, moves the lease's due date forward a month, or marks the PO ordered with its ETA. |
| `human_reject_request(approval_id, rejected_by, reason, approval_key)` | approvals, purchase_orders, ticket_notes | Rejects a request. No cash moves. |

## Run

```bash
pip install -r requirements.txt
python mcp_server/server.py          # stdio transport
python scripts/test_mcp_rules.py     # rule checks on a throwaway copy of the DB
```

## Connecting to the vibe coder

`.mcp.json` at the project root registers this server as `campus-customs` for Claude Code. `python scripts/mcp_smoke_test.py` calls each tool through Claude Code and writes the evidence to `output/mcp_smoke.json`.
