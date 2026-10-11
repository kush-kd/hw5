"""Smoke-test the campus-customs MCP tools through the vibe coder (Claude Code).

For each test, runs `claude -p` in this project with `.mcp.json` loaded, captures the
MCP tool call and its raw output from the stream, then re-reads the same values
straight from data/campus_customs_new.db (read-only) and records whether they match.
Writes everything to output/mcp_smoke.json.

Runs on the Claude Code subscription (ANTHROPIC_API_KEY is removed from the child env).

    python scripts/mcp_smoke_test.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "campus_customs_new.db"
OUT_PATH = ROOT / "output" / "mcp_smoke.json"
MODEL = "claude-opus-5-5"
SERVER = "campus-customs"
# Shop rule from the assignment: desk.date_today is "today" for the shop.
SHOP_CONTEXT = (
    "You are working on the Campus Customs class project. The shop's 'today' is "
    "desk.date_today in the database, as the MCP tools report it. Use only that date; "
    "do not compare it with the computer's clock."
)

TESTS = [
    {
        "ticket": 101,
        "tool": "check_stock",
        "prompt": "Using the campus-customs MCP server, check the stock for CC-TEE-WHITE "
        "in size S for ticket 101, which needs 1 unit.",
    },
    {
        "ticket": 103,
        "tool": "check_stock",
        "prompt": "Using the campus-customs MCP server, check the stock for CC-HOOD-NAVY "
        "in size M for ticket 103. The Yale AI Club wants 20 of them.",
    },
    {
        "ticket": "101, 103",
        "tool": "get_vendor_status",
        "prompt": "Using the campus-customs MCP server, get the status of all vendors. "
        "Which vendor can restock the apparel for tickets 101 and 103, and will they ship right now?",
    },
    {
        "ticket": 102,
        "tool": "get_lease_due",
        "prompt": "Using the campus-customs MCP server, look up lease 1 for ticket 102. "
        "When is the rent due, and does the checking account cover it?",
    },
]


def run_vibe_coder(prompt: str, tool: str) -> dict:
    """Run Claude Code headless with only this MCP tool allowed; return the call, raw output, and reply."""
    full_tool = f"mcp__{SERVER}__{tool}"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(
        [
            "claude", "-p", prompt,
            "--mcp-config", str(ROOT / ".mcp.json"), "--strict-mcp-config",
            "--allowedTools", full_tool,
            "--model", MODEL,
            "--append-system-prompt", SHOP_CONTEXT,
            "--output-format", "stream-json", "--verbose",
        ],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    call, output, reply, server_status = None, None, None, None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            server_status = {s["name"]: s["status"] for s in event.get("mcp_servers", [])}.get(SERVER)
        elif event.get("type") in ("assistant", "user"):
            content = event["message"].get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use" and block.get("name") == full_tool:
                    call = block
                elif block.get("type") == "tool_result" and call and block.get("tool_use_id") == call["id"]:
                    raw = block["content"]
                    if isinstance(raw, list):
                        raw = "".join(c.get("text", "") for c in raw)
                    output = json.loads(raw)
        elif event.get("type") == "result":
            reply = event.get("result")
    if call is None or output is None:
        raise RuntimeError(f"{tool}: no MCP tool call captured.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return {
        "mcp_server_status": server_status,
        "tool_name": full_tool,
        "tool_input": call["input"],
        "tool_output": output,
        "vibe_coder_reply": reply,
    }


def db_checks(tool: str, out: dict) -> list[dict]:
    """Re-read the same facts directly from the working DB and compare them field by field."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    checks = []

    def check(field, tool_value, db_value, source):
        checks.append({"field": field, "tool_value": tool_value, "db_value": db_value,
                       "db_source": source, "match": tool_value == db_value})

    today = conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]
    if tool == "check_stock":
        inv = conn.execute("SELECT * FROM inventory WHERE sku=? AND size=?", (out["sku"], out["size"])).fetchone()
        price = conn.execute("SELECT * FROM pricing WHERE sku=?", (out["sku"],)).fetchone()
        src = f"inventory WHERE sku='{out['sku']}' AND size='{out['size']}'"
        check("name", out["name"], inv["name"], src)
        check("location", out["location"], inv["location"], src)
        check("qty_on_hand", out["qty_on_hand"], inv["qty"], src)
        check("unit_cost", out["unit_cost"], price["unit_cost"], f"pricing WHERE sku='{out['sku']}'")
        check("list_price", out["list_price"], price["list_price"], f"pricing WHERE sku='{out['sku']}'")
    elif tool == "get_vendor_status":
        check("date_today", out["date_today"], today, "desk")
        for v in out["vendors"]:
            row = conn.execute("SELECT * FROM vendors WHERE id=?", (v["vendor_id"],)).fetchone()
            src = f"vendors WHERE id={v['vendor_id']}"
            check(f"vendor {v['vendor_id']} name", v["name"], row["name"], src)
            check(f"vendor {v['vendor_id']} specialty", v["specialty"], row["specialty"], src)
            check(f"vendor {v['vendor_id']} lead_days", v["lead_days"], row["lead_days"], src)
            invs = conn.execute(
                "SELECT id, amount, due_date FROM invoices WHERE vendor_id=? AND status='open' ORDER BY due_date",
                (v["vendor_id"],),
            ).fetchall()
            check(
                f"vendor {v['vendor_id']} open invoices (id, amount, due_date)",
                [[i["invoice_id"], i["amount"], i["due_date"]] for i in v["open_invoices"]],
                [[i["id"], i["amount"], i["due_date"]] for i in invs],
                f"invoices WHERE vendor_id={v['vendor_id']} AND status='open'",
            )
    elif tool == "get_lease_due":
        lease = conn.execute("SELECT * FROM leases WHERE id=?", (out["lease_id"],)).fetchone()
        cash = conn.execute("SELECT * FROM cash_accounts WHERE name=?", (out["cash_account"],)).fetchone()
        src = f"leases WHERE id={out['lease_id']}"
        check("date_today", out["date_today"], today, "desk")
        check("space_name", out["space_name"], lease["space_name"], src)
        check("landlord", out["landlord"], lease["landlord"], src)
        check("monthly_rent", out["monthly_rent"], lease["monthly_rent"], src)
        check("next_due", out["next_due"], lease["next_due"], src)
        check("cash_balance", out["cash_balance"], cash["balance"], f"cash_accounts WHERE name='{out['cash_account']}'")
    conn.close()
    return checks


def main() -> None:
    results = []
    for test in TESTS:
        print(f"Running {test['tool']} (ticket {test['ticket']}) ...")
        run = run_vibe_coder(test["prompt"], test["tool"])
        checks = db_checks(test["tool"], run["tool_output"])
        results.append({
            "ticket": test["ticket"],
            "prompt": test["prompt"],
            **run,
            "db_check": {"all_match": all(c["match"] for c in checks), "fields": checks},
        })

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "vibe_coder": "Claude Code (claude -p, Claude subscription)",
        "model": MODEL,
        "mcp_config": ".mcp.json",
        "mcp_server": SERVER,
        "shop_context": SHOP_CONTEXT,
        "database": "data/campus_customs_new.db",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "all_tools_match_db": all(r["db_check"]["all_match"] for r in results),
        "tests": results,
    }, indent=2) + "\n")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
