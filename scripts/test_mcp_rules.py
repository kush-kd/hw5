"""Check the MCP server enforces the shop rules, on a throwaway copy of the original DB.

Never touches data/campus_customs_new.db. Exercises every tool through a real
FastMCP client and asserts the money rules: human key required, payments only
after approval, no negative cash, vendor blocked while an invoice is open.

    python scripts/test_mcp_rules.py
"""

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp()) / "test.db"
shutil.copyfile(ROOT / "data" / "campus_customs.db", tmp)
os.environ["CAMPUS_CUSTOMS_DB"] = str(tmp)
os.environ["HUMAN_APPROVAL_KEY"] = "test-key"
sys.path.insert(0, str(ROOT / "mcp_server"))

from fastmcp import Client  # noqa: E402
from server import mcp  # noqa: E402

results = []


def check(label, cond, detail=""):
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -> {detail}" if not cond else ""))


async def main():
    async with Client(mcp) as c:
        call = lambda name, **kw: c.call_tool(name, kw, raise_on_error=False)
        tools = sorted(t.name for t in await c.list_tools())
        print("tools:", tools)

        t = (await call("list_open_tickets")).data
        check("3 open tickets", t["count"] == 3, t)
        g = (await call("get_ticket", ticket_id=101)).data
        check("ticket 101 links invoice 501 (3 days overdue)", g["linked_invoice"]["days_overdue"] == 3, g["linked_invoice"])

        m = (await call("check_margin", sku="CC-HOOD-NAVY", unit_price=46.4, qty=20)).data
        check("margin at $46.40 = 52.59%", m["gross_margin_pct"] == 52.59, m)
        d = (await call("request_discount_approval", ticket_id=103, sku="CC-HOOD-NAVY", qty=20, unit_price=20, agent="accounting", reason="t")).data
        check("discount below cost refused", d["ok"] is False, d)

        po = (await call("create_purchase_order", ticket_id=101, vendor_id=1, sku="CC-TEE-WHITE", size="S", qty=1, agent="accounting", reason="t")).data
        check("PO to blocked vendor refused before invoice payment requested", po["ok"] is False, po)

        inv = (await call("request_payment", ticket_id=101, kind="invoice", ref_id=501, agent="accounting", reason="t")).data
        check("invoice payment queued as pending (not paid)", inv["ok"] and inv["amount"] == 840 and inv["paid"] is False, inv)
        dup = (await call("request_payment", ticket_id=101, kind="invoice", ref_id=501, agent="accounting", reason="t")).data
        check("duplicate payment request refused", dup["ok"] is False, dup)

        po = (await call("create_purchase_order", ticket_id=101, vendor_id=1, sku="CC-TEE-WHITE", size="S", qty=1, agent="accounting", reason="t")).data
        check("PO allowed once invoice payment is pending; depends on it", po["ok"] and po["depends_on_approval"] == inv["approval_id"], po)

        rent = (await call("request_payment", ticket_id=102, kind="rent", ref_id=1, agent="accounting", reason="t")).data
        big = (await call("create_purchase_order", ticket_id=103, vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12, agent="accounting", reason="t")).data

        st = (await call("set_ticket_status", ticket_id=101, status="resolved", agent="inventory", reason="t")).data
        check("non-boss cannot change status", st["ok"] is False, st)
        st = (await call("set_ticket_status", ticket_id=101, status="resolved", agent="boss", reason="t")).data
        check("boss resolves ticket; pending approvals stay with the human", st["ok"] and st["pending_approvals"] == 2, st)

        bad = (await call("human_approve_and_pay", approval_id=inv["approval_id"], approved_by="x", approval_key="wrong")).data
        check("approval without the human key refused", bad["ok"] is False, bad)

        early = (await call("human_approve_and_pay", approval_id=po["approval_id"], approved_by="Kush", approval_key="test-key")).data
        check("PO cannot be paid before the vendor's invoice", early["ok"] is False and early.get("refused"), early)

        p1 = (await call("human_approve_and_pay", approval_id=inv["approval_id"], approved_by="Kush", approval_key="test-key")).data
        check("invoice paid: cash 3400 -> 2560", p1["ok"] and p1["new_balance"] == 2560, p1)
        p2 = (await call("human_approve_and_pay", approval_id=rent["approval_id"], approved_by="Kush", approval_key="test-key")).data
        check("rent paid: cash -> 160, next_due -> 2026-10-02", p2["ok"] and p2["new_balance"] == 160 and p2["new_next_due"] == "2026-10-02", p2)
        p3 = (await call("human_approve_and_pay", approval_id=po["approval_id"], approved_by="Kush", approval_key="test-key")).data
        check("tee PO paid: cash -> 152, ETA 2026-09-05", p3["ok"] and p3["new_balance"] == 152 and p3["eta"] == "2026-09-05", p3)
        p4 = (await call("human_approve_and_pay", approval_id=big["approval_id"], approved_by="Kush", approval_key="test-key")).data
        check("$264 hoodie PO refused: not enough cash (no negative balance)", p4["ok"] is False and p4.get("refused"), p4)

        cash = (await call("get_cash_position")).data
        check("balance 152, 3 payments recorded with approver", cash["balance"] == 152 and len(cash["payments_made"]) == 3
              and all(p["approved_by"] == "Kush" for p in cash["payments_made"]), cash)
        v = (await call("get_vendor_status", vendor_id=1)).data
        check("Bulldog Print Co unblocked after invoice paid", v["vendors"][0]["will_ship_now"] is True, v)
        dr = (await call("save_draft_message", ticket_id=101, recipient="Tauhid Zaman", subject="s", body="b", agent="customer_service")).data
        check("draft saved, never sent", dr["ok"] and dr["sent"] is False, dr)
        rj = (await call("human_reject_request", approval_id=big["approval_id"], rejected_by="Kush", reason="no cash", approval_key="test-key")).data
        check("human can reject; PO cancelled", rj["ok"], rj)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    shutil.rmtree(tmp.parent)
    sys.exit(0 if all(results) else 1)


asyncio.run(main())
