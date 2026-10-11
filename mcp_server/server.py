"""Campus Customs MCP server.

The single shared toolbox every agent (Boss, Inventory, Accounting, Facilities,
Customer Service) uses to read and update the shop database. Agents never touch
SQLite directly -- every shop fact and every state change goes through a tool here.

Every number a tool returns comes straight from `data/campus_customs_new.db` or is
simple arithmetic on those numbers -- nothing is guessed. If a row is missing, the
tool says so instead of inventing one. Money amounts for payments are always read
from the database, never taken from the caller.

Two tools are for the human approver only (`human_approve_and_pay`,
`human_reject_request`). They require HUMAN_APPROVAL_KEY, which only the backend's
human-facing endpoint holds; agent toolsets never include them.

Run (stdio transport):
    .venv/bin/python mcp_server/server.py
"""

from __future__ import annotations

import calendar
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Iterator, Literal

from fastmcp import FastMCP

# Working copy only -- data/campus_customs.db is the untouched original we reset from.
DB_PATH = Path(
    os.environ.get(
        "CAMPUS_CUSTOMS_DB",
        Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db",
    )
)

mcp = FastMCP("campus-customs")

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "blocked", "resolved"]

# Tables the original database does not have but the agents need. Created in the
# working copy only, so resetting from the original wipes them cleanly.
_OPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_notes (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    agent TEXT NOT NULL,
    note TEXT NOT NULL,
    shop_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id),
    kind TEXT NOT NULL,              -- invoice | rent | purchase_order | discount
    ref_id INTEGER,                  -- invoices.id | leases.id | purchase_orders.id | NULL
    amount REAL NOT NULL,            -- cash that leaves the shop if approved (0 for discount)
    details TEXT,                    -- JSON with the facts the human needs
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,            -- pending | paid | approved | rejected
    depends_on INTEGER REFERENCES approvals(id),
    shop_date TEXT NOT NULL,
    decided_by TEXT,
    decision_note TEXT,
    payment_id INTEGER REFERENCES payments(id)
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id),
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL,            -- pending_approval | ordered | rejected
    eta TEXT,                        -- set when the order is actually placed (paid)
    approval_id INTEGER REFERENCES approvals(id),
    created_by TEXT NOT NULL,
    shop_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id),
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',   -- always 'draft': nothing is ever sent
    shop_date TEXT NOT NULL
);
"""


# --------------------------------------------------------------------------- helpers


@contextmanager
def _db(write: bool = False) -> Iterator[sqlite3.Connection]:
    """Open the working DB. Read-only unless write=True; commits on success, rolls back on error.

    mode=ro / mode=rw both refuse to create an empty database if the path is wrong.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. "
            "Run `python scripts/reset_db.py` to copy the original first."
        )
    _ensure_ops_tables()
    conn = sqlite3.connect(f"file:{DB_PATH}?mode={'rw' if write else 'ro'}", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        if write:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_ops_tables() -> None:
    """Create the work tables if missing. Runs before every connection, so a DB reset
    (which restores the original file without them) never breaks a running server."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='drafts'").fetchone() is None:
            conn.executescript(_OPS_SCHEMA)
            conn.commit()
    finally:
        conn.close()


def _today(conn: sqlite3.Connection) -> date:
    """The shop's 'today' is desk.date_today, never the real clock."""
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"])


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def _rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def _approval_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["details"] = json.loads(d["details"]) if d.get("details") else None
    return d


def _ticket_exists(conn: sqlite3.Connection, ticket_id: int) -> bool:
    return conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


def _note(conn: sqlite3.Connection, ticket_id: int, agent: str, note: str) -> int:
    cur = conn.execute(
        "INSERT INTO ticket_notes (ticket_id, agent, note, shop_date) VALUES (?, ?, ?, ?)",
        (ticket_id, agent, note, _today(conn).isoformat()),
    )
    return cur.lastrowid


def _open_invoices(conn: sqlite3.Connection, vendor_id: int, today: date) -> list[dict]:
    rows = conn.execute(
        "SELECT id, amount, due_date, description FROM invoices "
        "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
        (vendor_id,),
    ).fetchall()
    return [
        {
            "invoice_id": r["id"],
            "amount": r["amount"],
            "due_date": r["due_date"],
            "days_overdue": max(0, (today - date.fromisoformat(r["due_date"])).days),
            "description": r["description"],
        }
        for r in rows
    ]


def _pending_cash_out(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn.execute(
            "SELECT id, ticket_id, kind, ref_id, amount, requested_by FROM approvals "
            "WHERE status = 'pending' AND amount > 0 ORDER BY id"
        )
    )


def _check_human_key(approval_key: str) -> str | None:
    """Return an error string unless the caller holds the backend's human-approval key."""
    expected = os.environ.get("HUMAN_APPROVAL_KEY", "")
    if not expected:
        return "Human approval is not configured on this server (HUMAN_APPROVAL_KEY unset); nothing was paid."
    if not hmac.compare_digest(approval_key or "", expected):
        return "Invalid approval key: only the human approver can approve or reject requests."
    return None


# ------------------------------------------------------------------ read tools: tickets


@mcp.tool
def list_tickets() -> dict:
    """List every ticket on the board (open or resolved) with its status and how much work is
    attached: pending approvals, purchase orders, and drafts."""
    with _db() as conn:
        rows = _rows(
            conn.execute(
                """
                SELECT t.id, t.type, t.requester, t.subject, t.sku, t.size, t.qty, t.lease_id, t.invoice_id,
                       t.status, t.notes, t.created_at,
                       (SELECT COUNT(*) FROM approvals a WHERE a.ticket_id = t.id AND a.status = 'pending') AS pending_approvals,
                       (SELECT COUNT(*) FROM purchase_orders p WHERE p.ticket_id = t.id) AS purchase_orders,
                       (SELECT COUNT(*) FROM drafts d WHERE d.ticket_id = t.id) AS drafts
                FROM tickets t ORDER BY t.created_at
                """
            )
        )
        today = _today(conn)
    for r in rows:
        r["is_resolved"] = r["status"] == "resolved"
    return {"date_today": today.isoformat(), "count": len(rows), "tickets": rows}


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not yet resolved, oldest first, with its type, requester, and status."""
    with _db() as conn:
        rows = _rows(
            conn.execute(
                "SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id, status, created_at "
                "FROM tickets WHERE status != 'resolved' ORDER BY created_at"
            )
        )
        return {"date_today": _today(conn).isoformat(), "count": len(rows), "tickets": rows}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket in full: its fields, the lease or invoice it links to, and all work recorded
    on it so far (agent notes, approval requests, purchase orders, and customer drafts)."""
    with _db() as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return {"found": False, "error": f"No ticket with id {ticket_id}."}
        today = _today(conn)
        lease = invoice = None
        if ticket["lease_id"] is not None:
            row = conn.execute("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)).fetchone()
            lease = dict(row) if row else {"error": f"Linked lease {ticket['lease_id']} not found."}
        if ticket["invoice_id"] is not None:
            row = conn.execute(
                "SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                "WHERE i.id = ?",
                (ticket["invoice_id"],),
            ).fetchone()
            if row:
                invoice = dict(row)
                invoice["days_overdue"] = max(0, (today - date.fromisoformat(row["due_date"])).days)
            else:
                invoice = {"error": f"Linked invoice {ticket['invoice_id']} not found."}
        return {
            "found": True,
            "date_today": today.isoformat(),
            "ticket": dict(ticket),
            "linked_lease": lease,
            "linked_invoice": invoice,
            "notes": _rows(conn.execute("SELECT * FROM ticket_notes WHERE ticket_id = ? ORDER BY id", (ticket_id,))),
            "approvals": [
                _approval_dict(r)
                for r in conn.execute("SELECT * FROM approvals WHERE ticket_id = ? ORDER BY id", (ticket_id,))
            ],
            "purchase_orders": _rows(
                conn.execute("SELECT * FROM purchase_orders WHERE ticket_id = ? ORDER BY id", (ticket_id,))
            ),
            "drafts": _rows(conn.execute("SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,))),
        }


# ---------------------------------------------------------------- read tools: inventory


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int = 1) -> dict:
    """Check on-hand stock for one SKU + size against how many a ticket needs.

    Returns quantity on hand, the shortfall (if any), the shelf location, and the
    SKU's unit cost and list price so the shortfall can be costed for a restock
    or a discount can be margin-checked. Use for customer orders and bulk requests.
    """
    with _db() as conn:
        row = conn.execute(
            """
            SELECT i.sku, i.name, i.size, i.qty, i.location, p.unit_cost, p.list_price
            FROM inventory i LEFT JOIN pricing p ON p.sku = i.sku
            WHERE i.sku = ? AND i.size = ?
            """,
            (sku, size),
        ).fetchone()
        if row is None:
            sizes = [r["size"] for r in conn.execute("SELECT size FROM inventory WHERE sku = ?", (sku,))]
            return {
                "found": False,
                "sku": sku,
                "size": size,
                "error": (
                    f"No inventory row for {sku} size {size}. Sizes on file for this SKU: {sizes}"
                    if sizes
                    else f"SKU {sku} is not in inventory."
                ),
            }

    shortfall = max(0, qty_needed - row["qty"])
    unit_cost = row["unit_cost"]
    return {
        "found": True,
        "sku": row["sku"],
        "name": row["name"],
        "size": row["size"],
        "location": row["location"],
        "qty_on_hand": row["qty"],
        "qty_needed": qty_needed,
        "shortfall": shortfall,
        "can_fill_from_stock": shortfall == 0,
        "unit_cost": unit_cost,
        "list_price": row["list_price"],
        "restock_cost_for_shortfall": round(shortfall * unit_cost, 2) if unit_cost is not None else None,
    }


@mcp.tool
def list_inventory(sku: str | None = None) -> dict:
    """List stock rows (every size with qty and location), for one SKU or the whole shop.

    Use it to find alternative sizes for a customer or to see the full stock picture
    for a SKU before recommending a restock quantity.
    """
    with _db() as conn:
        if sku is None:
            rows = _rows(conn.execute("SELECT * FROM inventory ORDER BY sku, size"))
        else:
            rows = _rows(conn.execute("SELECT * FROM inventory WHERE sku = ? ORDER BY size", (sku,)))
            if not rows:
                return {"found": False, "error": f"SKU {sku} is not in inventory."}
    return {"found": True, "rows": rows}


@mcp.tool
def get_vendor_status(vendor_id: int | None = None) -> dict:
    """List vendors with their specialty, lead time, open invoices, and whether they will ship.

    A vendor will NOT ship new product while it has any open (unpaid) invoice, so
    `will_ship_now` is False whenever `open_invoices` is non-empty. Days overdue and
    the ETA are measured from desk.date_today. Pass vendor_id for one vendor, or
    omit it to compare all vendors when choosing who can restock.
    """
    with _db() as conn:
        today = _today(conn)
        if vendor_id is None:
            vendors = conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()
        else:
            vendors = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchall()
            if not vendors:
                return {"found": False, "error": f"No vendor with id {vendor_id}."}

        results = []
        for v in vendors:
            open_invoices = _open_invoices(conn, v["id"], today)
            results.append(
                {
                    "vendor_id": v["id"],
                    "name": v["name"],
                    "specialty": v["specialty"],
                    "lead_days": v["lead_days"],
                    # Only meaningful once the vendor is unblocked and the order is placed today.
                    "eta_if_ordered_today": (today + timedelta(days=v["lead_days"])).isoformat(),
                    "open_invoices": open_invoices,
                    "open_invoice_total": round(sum(i["amount"] for i in open_invoices), 2),
                    "will_ship_now": not open_invoices,
                }
            )

    return {"found": True, "date_today": today.isoformat(), "vendors": results}


# ------------------------------------------------------------- read tools: money & space


@mcp.tool
def get_lease_due(lease_id: int, account: str = "checking") -> dict:
    """Look up a lease's rent amount and due date, and whether cash covers it.

    Days until due are measured from desk.date_today (negative means overdue).
    Also reports the named cash account's balance and what it would be after
    paying one month's rent -- this tool does NOT pay anything.
    """
    with _db() as conn:
        today = _today(conn)
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if lease is None:
            return {"found": False, "error": f"No lease with id {lease_id}."}
        cash = conn.execute("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)).fetchone()

    days_until_due = (date.fromisoformat(lease["next_due"]) - today).days
    result = {
        "found": True,
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": lease["monthly_rent"],
        "next_due": lease["next_due"],
        "date_today": today.isoformat(),
        "days_until_due": days_until_due,
        "is_overdue": days_until_due < 0,
        "notes": lease["notes"],
    }
    if cash is None:
        result["cash_error"] = f"No cash account named {account!r}."
    else:
        result.update(
            {
                "cash_account": cash["name"],
                "cash_balance": cash["balance"],
                "cash_balance_as_of": cash["date"],
                "balance_after_rent": round(cash["balance"] - lease["monthly_rent"], 2),
                "cash_covers_rent": cash["balance"] >= lease["monthly_rent"],
            }
        )
    return result


@mcp.tool
def get_cash_position(account: str = "checking") -> dict:
    """Show the cash balance, every pending cash-out approval already requested, and what would be
    left if all of them were approved. Check this before requesting any new payment or purchase order."""
    with _db() as conn:
        cash = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if cash is None:
            names = [r["name"] for r in conn.execute("SELECT name FROM cash_accounts")]
            return {"found": False, "error": f"No cash account named {account!r}. Accounts: {names}"}
        pending = _pending_cash_out(conn)
        paid = _rows(conn.execute("SELECT * FROM payments ORDER BY id"))
        today = _today(conn)
    pending_total = round(sum(p["amount"] for p in pending), 2)
    return {
        "found": True,
        "date_today": today.isoformat(),
        "account": cash["name"],
        "balance": cash["balance"],
        "balance_as_of": cash["date"],
        "pending_cash_out": pending,
        "pending_total": pending_total,
        "available_after_pending": round(cash["balance"] - pending_total, 2),
        "payments_made": paid,
        "note": "No revenue is modelled: cash only goes out.",
    }


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """Look up one vendor invoice: amount, due date, days overdue (from desk.date_today), status,
    the vendor it belongs to, and whether a payment approval has already been requested for it."""
    with _db() as conn:
        row = conn.execute(
            "SELECT i.*, v.name AS vendor_name, v.specialty AS vendor_specialty FROM invoices i "
            "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
            (invoice_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "error": f"No invoice with id {invoice_id}."}
        today = _today(conn)
        approvals = [
            _approval_dict(r)
            for r in conn.execute("SELECT * FROM approvals WHERE kind = 'invoice' AND ref_id = ?", (invoice_id,))
        ]
    inv = dict(row)
    inv["days_overdue"] = max(0, (today - date.fromisoformat(row["due_date"])).days)
    inv["is_overdue"] = row["status"] == "open" and inv["days_overdue"] > 0
    return {"found": True, "date_today": today.isoformat(), "invoice": inv, "payment_approvals": approvals}


@mcp.tool
def check_margin(sku: str, unit_price: float, qty: int = 1) -> dict:
    """Margin check for selling `qty` of a SKU at a proposed `unit_price` (e.g. a discount request).

    Uses pricing.unit_cost and pricing.list_price. Reports revenue, cost, gross margin
    in dollars and percent, the discount versus list price, and whether the price is
    below cost (never allowed).
    """
    with _db() as conn:
        p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if p is None:
        return {"found": False, "error": f"No pricing row for SKU {sku}."}
    if unit_price <= 0 or qty <= 0:
        return {"found": True, "error": "unit_price and qty must both be positive."}
    revenue = round(unit_price * qty, 2)
    cost = round(p["unit_cost"] * qty, 2)
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": p["unit_cost"],
        "list_price": p["list_price"],
        "proposed_unit_price": unit_price,
        "discount_pct_vs_list": round((1 - unit_price / p["list_price"]) * 100, 2),
        "revenue": revenue,
        "cost": cost,
        "gross_margin": round(revenue - cost, 2),
        "gross_margin_pct": round((revenue - cost) / revenue * 100, 2),
        "list_price_margin_pct": round((p["list_price"] - p["unit_cost"]) / p["list_price"] * 100, 2),
        "below_cost": unit_price < p["unit_cost"],
    }


@mcp.tool
def list_approvals(status: str | None = "pending") -> dict:
    """List approval requests waiting for (or already decided by) the human, newest last.
    Pass status='pending' (default), 'paid', 'approved', 'rejected', or None for all."""
    with _db() as conn:
        if status is None:
            rows = conn.execute("SELECT * FROM approvals ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM approvals WHERE status = ? ORDER BY id", (status,)).fetchall()
    return {"count": len(rows), "approvals": [_approval_dict(r) for r in rows]}


# ------------------------------------------------------------------ agent write tools


@mcp.tool
def add_ticket_note(ticket_id: int, agent: AgentName, note: str) -> dict:
    """Record a finding, recommendation, or hand-off on a ticket so every agent and the human
    can see it. Notes are the shared memory of the team; they never change money or stock."""
    note = note.strip()
    if not note:
        return {"ok": False, "error": "Note is empty."}
    with _db(write=True) as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id {ticket_id}."}
        note_id = _note(conn, ticket_id, agent, note[:2000])
    return {"ok": True, "note_id": note_id}


@mcp.tool
def set_ticket_status(ticket_id: int, status: TicketStatus, agent: AgentName, reason: str) -> dict:
    """Move a ticket to open / in_progress / waiting_on_approval / blocked / resolved and record why.
    Only the Boss makes this call. `resolved` means the agent team has finished its work on the
    ticket; any approvals still pending stay in the human's queue and are noted on the ticket."""
    if agent != "boss":
        return {"ok": False, "error": "Only the boss agent may change a ticket's status."}
    with _db(write=True) as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id {ticket_id}."}
        pending = conn.execute(
            "SELECT COUNT(*) FROM approvals WHERE ticket_id = ? AND status = 'pending'", (ticket_id,)
        ).fetchone()[0]
        old = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()["status"]
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        waiting = f" ({pending} approval(s) waiting on the human)" if status == "resolved" and pending else ""
        _note(conn, ticket_id, agent, f"Status {old} -> {status}{waiting}: {reason.strip()}")
    return {"ok": True, "ticket_id": ticket_id, "old_status": old, "new_status": status, "pending_approvals": pending}


@mcp.tool
def save_draft_message(ticket_id: int, recipient: str, subject: str, body: str, agent: AgentName) -> dict:
    """Save a message to a customer (or other requester) as a DRAFT on the board.
    Nothing is ever emailed or sent -- a human reviews drafts on the dashboard."""
    if not body.strip() or not recipient.strip():
        return {"ok": False, "error": "Recipient and body are required."}
    with _db(write=True) as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id {ticket_id}."}
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, recipient, subject, body, author, status, shop_date) "
            "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
            (ticket_id, recipient.strip(), subject.strip(), body.strip(), agent, _today(conn).isoformat()),
        )
        _note(conn, ticket_id, agent, f"Saved draft #{cur.lastrowid} to {recipient.strip()} (not sent).")
    return {"ok": True, "draft_id": cur.lastrowid, "status": "draft", "sent": False}


@mcp.tool
def request_payment(ticket_id: int, kind: Literal["invoice", "rent"], ref_id: int, agent: AgentName, reason: str) -> dict:
    """Prepare a payment for HUMAN approval. Nothing is paid here.

    kind='invoice' -> ref_id is invoices.id (amount = the invoice amount; invoice must be open).
    kind='rent'    -> ref_id is leases.id (amount = one month's rent).
    The amount always comes from the database. Refuses duplicates of a request that is
    already pending, and refuses if the amount exceeds the current cash balance.
    """
    with _db(write=True) as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id {ticket_id}."}
        today = _today(conn)
        if kind == "invoice":
            inv = conn.execute(
                "SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ref_id,),
            ).fetchone()
            if inv is None:
                return {"ok": False, "error": f"No invoice with id {ref_id}."}
            if inv["status"] != "open":
                return {"ok": False, "error": f"Invoice {ref_id} is '{inv['status']}', not open; nothing to pay."}
            amount = inv["amount"]
            details = {
                "payee": inv["vendor_name"],
                "vendor_id": inv["vendor_id"],
                "invoice_id": inv["id"],
                "due_date": inv["due_date"],
                "days_overdue": max(0, (today - date.fromisoformat(inv["due_date"])).days),
                "description": inv["description"],
            }
        else:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                return {"ok": False, "error": f"No lease with id {ref_id}."}
            amount = lease["monthly_rent"]
            details = {
                "payee": lease["landlord"],
                "lease_id": lease["id"],
                "space_name": lease["space_name"],
                "due_date": lease["next_due"],
                "days_until_due": (date.fromisoformat(lease["next_due"]) - today).days,
            }

        dup = conn.execute(
            "SELECT id FROM approvals WHERE kind = ? AND ref_id = ? AND status = 'pending'", (kind, ref_id)
        ).fetchone()
        if dup:
            return {"ok": False, "error": f"Approval #{dup['id']} for this {kind} is already pending.", "approval_id": dup["id"]}

        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
        pending_total = sum(p["amount"] for p in _pending_cash_out(conn))
        if amount > balance:
            return {"ok": False, "error": f"${amount:,.2f} exceeds the ${balance:,.2f} cash balance; cannot be paid."}

        cur = conn.execute(
            "INSERT INTO approvals (ticket_id, kind, ref_id, amount, details, requested_by, reason, status, shop_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (ticket_id, kind, ref_id, amount, json.dumps(details), agent, reason.strip(), today.isoformat()),
        )
        _note(conn, ticket_id, agent, f"Requested human approval #{cur.lastrowid}: pay {kind} {ref_id} ${amount:,.2f}.")
    return {
        "ok": True,
        "approval_id": cur.lastrowid,
        "status": "pending",
        "amount": amount,
        "details": details,
        "cash_balance": balance,
        "other_pending_total": round(pending_total, 2),
        "fits_after_other_pending": balance - pending_total >= amount,
        "paid": False,
    }


@mcp.tool
def create_purchase_order(ticket_id: int, vendor_id: int, sku: str, size: str, qty: int, agent: AgentName, reason: str) -> dict:
    """Draft a restock purchase order and queue it for HUMAN approval (approval = payment + order placed).

    Cost = qty x pricing.unit_cost. Because a vendor will not ship while it has an open
    unpaid invoice, the PO is refused for a blocked vendor UNLESS a payment approval for
    that invoice is already pending -- the PO then depends on it and cannot be paid first.
    """
    if qty <= 0:
        return {"ok": False, "error": "qty must be positive."}
    with _db(write=True) as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id {ticket_id}."}
        today = _today(conn)
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"ok": False, "error": f"No vendor with id {vendor_id}."}
        item = conn.execute(
            "SELECT i.name, p.unit_cost FROM inventory i JOIN pricing p ON p.sku = i.sku WHERE i.sku = ? AND i.size = ?",
            (sku, size),
        ).fetchone()
        if item is None:
            return {"ok": False, "error": f"No priced inventory row for {sku} size {size}."}

        depends_on = None
        for inv in _open_invoices(conn, vendor_id, today):
            pay = conn.execute(
                "SELECT id FROM approvals WHERE kind = 'invoice' AND ref_id = ? AND status = 'pending'", (inv["invoice_id"],)
            ).fetchone()
            if pay is None:
                return {
                    "ok": False,
                    "error": (
                        f"{vendor['name']} will not ship: invoice {inv['invoice_id']} (${inv['amount']:,.2f}) is open. "
                        "Request payment of that invoice first, then create the PO."
                    ),
                }
            depends_on = pay["id"]

        total = round(qty * item["unit_cost"], 2)
        cur = conn.execute(
            "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, total, status, created_by, shop_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?)",
            (ticket_id, vendor_id, sku, size, qty, item["unit_cost"], total, agent, today.isoformat()),
        )
        po_id = cur.lastrowid
        details = {
            "payee": vendor["name"],
            "vendor_id": vendor_id,
            "purchase_order_id": po_id,
            "sku": sku,
            "name": item["name"],
            "size": size,
            "qty": qty,
            "unit_cost": item["unit_cost"],
            "lead_days": vendor["lead_days"],
            "eta_if_paid_today": (today + timedelta(days=vendor["lead_days"])).isoformat(),
        }
        cur = conn.execute(
            "INSERT INTO approvals (ticket_id, kind, ref_id, amount, details, requested_by, reason, status, depends_on, shop_date) "
            "VALUES (?, 'purchase_order', ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (ticket_id, po_id, total, json.dumps(details), agent, reason.strip(), depends_on, today.isoformat()),
        )
        approval_id = cur.lastrowid
        conn.execute("UPDATE purchase_orders SET approval_id = ? WHERE id = ?", (approval_id, po_id))
        balance = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()["balance"]
        pending_total = sum(p["amount"] for p in _pending_cash_out(conn))
        _note(conn, ticket_id, agent, f"Drafted PO #{po_id}: {qty} x {sku} {size} from {vendor['name']} ${total:,.2f}; approval #{approval_id}.")
    return {
        "ok": True,
        "purchase_order_id": po_id,
        "approval_id": approval_id,
        "total": total,
        "depends_on_approval": depends_on,
        "details": details,
        "cash_balance": balance,
        "pending_total_including_this": round(pending_total, 2),
        "all_pending_fit_in_cash": balance >= pending_total,
        "ordered": False,
    }


@mcp.tool
def request_discount_approval(ticket_id: int, sku: str, qty: int, unit_price: float, agent: AgentName, reason: str) -> dict:
    """Queue a proposed discounted unit price for HUMAN approval (no cash moves).
    Refused if the price is below pricing.unit_cost or above list price."""
    with _db(write=True) as conn:
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket with id {ticket_id}."}
        p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if p is None:
            return {"ok": False, "error": f"No pricing row for SKU {sku}."}
        if qty <= 0 or unit_price <= 0:
            return {"ok": False, "error": "qty and unit_price must be positive."}
        if unit_price < p["unit_cost"]:
            return {"ok": False, "error": f"${unit_price:.2f} is below unit cost ${p['unit_cost']:.2f}; never sell below cost."}
        if unit_price > p["list_price"]:
            return {"ok": False, "error": f"${unit_price:.2f} is above list price ${p['list_price']:.2f}; that is not a discount."}
        revenue = unit_price * qty
        details = {
            "sku": sku,
            "qty": qty,
            "list_price": p["list_price"],
            "unit_cost": p["unit_cost"],
            "proposed_unit_price": unit_price,
            "discount_pct_vs_list": round((1 - unit_price / p["list_price"]) * 100, 2),
            "revenue": round(revenue, 2),
            "revenue_at_list": round(p["list_price"] * qty, 2),
            "gross_margin": round(revenue - p["unit_cost"] * qty, 2),
            "gross_margin_pct": round((unit_price - p["unit_cost"]) / unit_price * 100, 2),
        }
        cur = conn.execute(
            "INSERT INTO approvals (ticket_id, kind, ref_id, amount, details, requested_by, reason, status, shop_date) "
            "VALUES (?, 'discount', NULL, 0, ?, ?, ?, 'pending', ?)",
            (ticket_id, json.dumps(details), agent, reason.strip(), _today(conn).isoformat()),
        )
        _note(conn, ticket_id, agent, f"Requested human approval #{cur.lastrowid}: {qty} x {sku} at ${unit_price:.2f}.")
    return {"ok": True, "approval_id": cur.lastrowid, "status": "pending", "details": details}


# ------------------------------------------------------------- human-only approval tools


@mcp.tool
def human_approve_and_pay(approval_id: int, approved_by: str, approval_key: str) -> dict:
    """HUMAN ONLY. Approve a pending request; for cash requests this is the pay tool.

    Refuses (and leaves the request pending) if cash would go negative, or if a purchase
    order's vendor still has an open invoice. On success it writes a payments row, lowers
    cash_accounts.balance, and updates the paid item (invoice -> paid, lease next_due +1 month,
    purchase order -> ordered with ETA). Discount approvals move no cash.
    """
    if err := _check_human_key(approval_key):
        return {"ok": False, "error": err}
    if not approved_by.strip():
        return {"ok": False, "error": "approved_by (the human's name) is required."}
    with _db(write=True) as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return {"ok": False, "error": f"No approval with id {approval_id}."}
        if a["status"] != "pending":
            return {"ok": False, "error": f"Approval {approval_id} is already '{a['status']}'."}
        today = _today(conn)

        if a["kind"] == "discount":
            conn.execute(
                "UPDATE approvals SET status = 'approved', decided_by = ? WHERE id = ?", (approved_by.strip(), approval_id)
            )
            if a["ticket_id"]:
                _note(conn, a["ticket_id"], "boss", f"Human {approved_by.strip()} approved discount #{approval_id}.")
            return {"ok": True, "approval_id": approval_id, "status": "approved", "cash_moved": 0}

        account = "checking"
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        amount = a["amount"]
        if amount > cash["balance"]:
            return {
                "ok": False,
                "refused": True,
                "error": f"Insufficient cash: ${amount:,.2f} needed, ${cash['balance']:,.2f} available. Nothing was paid.",
            }

        if a["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (a["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return {"ok": False, "error": f"Invoice {a['ref_id']} is not open; nothing was paid."}
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (a["ref_id"],))
            effect = {"invoice_id": a["ref_id"], "invoice_status": "paid"}
        elif a["kind"] == "rent":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
            new_due = _add_month(date.fromisoformat(lease["next_due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, a["ref_id"]))
            effect = {"lease_id": a["ref_id"], "old_next_due": lease["next_due"], "new_next_due": new_due}
        elif a["kind"] == "purchase_order":
            po = conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (a["ref_id"],)).fetchone()
            blocking = _open_invoices(conn, po["vendor_id"], today)
            if blocking:
                ids = [b["invoice_id"] for b in blocking]
                return {
                    "ok": False,
                    "refused": True,
                    "error": f"Vendor still has open invoice(s) {ids} and will not ship. Pay those first; nothing was paid.",
                }
            lead = conn.execute("SELECT lead_days FROM vendors WHERE id = ?", (po["vendor_id"],)).fetchone()["lead_days"]
            eta = (today + timedelta(days=lead)).isoformat()
            conn.execute("UPDATE purchase_orders SET status = 'ordered', eta = ? WHERE id = ?", (eta, po["id"]))
            effect = {"purchase_order_id": po["id"], "po_status": "ordered", "eta": eta}
        else:
            return {"ok": False, "error": f"Unknown approval kind {a['kind']!r}."}

        new_balance = round(cash["balance"] - amount, 2)
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today.isoformat(), account)
        )
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (a["kind"], a["ref_id"], amount, account, today.isoformat(), approved_by.strip()),
        )
        conn.execute(
            "UPDATE approvals SET status = 'paid', decided_by = ?, payment_id = ? WHERE id = ?",
            (approved_by.strip(), cur.lastrowid, approval_id),
        )
        if a["ticket_id"]:
            _note(conn, a["ticket_id"], "accounting", f"Human {approved_by.strip()} approved #{approval_id}; paid ${amount:,.2f} (payment #{cur.lastrowid}).")
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": "paid",
        "payment_id": cur.lastrowid,
        "amount": amount,
        "new_balance": new_balance,
        **effect,
    }


@mcp.tool
def human_reject_request(approval_id: int, rejected_by: str, reason: str, approval_key: str) -> dict:
    """HUMAN ONLY. Reject a pending request. No cash moves; a rejected PO is cancelled."""
    if err := _check_human_key(approval_key):
        return {"ok": False, "error": err}
    with _db(write=True) as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return {"ok": False, "error": f"No approval with id {approval_id}."}
        if a["status"] != "pending":
            return {"ok": False, "error": f"Approval {approval_id} is already '{a['status']}'."}
        conn.execute(
            "UPDATE approvals SET status = 'rejected', decided_by = ?, decision_note = ? WHERE id = ?",
            (rejected_by.strip(), reason.strip(), approval_id),
        )
        if a["kind"] == "purchase_order":
            conn.execute("UPDATE purchase_orders SET status = 'rejected' WHERE id = ?", (a["ref_id"],))
        if a["ticket_id"]:
            _note(conn, a["ticket_id"], "boss", f"Human {rejected_by.strip()} rejected #{approval_id}: {reason.strip()}")
    return {"ok": True, "approval_id": approval_id, "status": "rejected"}


if __name__ == "__main__":
    mcp.run(show_banner=False)
