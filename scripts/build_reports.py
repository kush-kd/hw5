"""Build the Problem 9 reports from the real full run.

Reads the append-only audit trail (output/audit_trail.json) and the shop state through the
running backend (http://localhost:8000, which reads through MCP), then:

  * fills the Actual section of each ticket tab and the Cash tab in output/desk_tickets.html
  * writes output/resolved_tickets.json

The run used for each ticket is the latest completed run after the most recent DB reset.
Cash math is checked: start - sum(payments) must equal cash_accounts in the working DB.

    python scripts/build_reports.py
"""

from __future__ import annotations

import html
import json
import sqlite3
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "http://localhost:8000/api"
AUDIT = ROOT / "output" / "audit_trail.json"
DESK = ROOT / "output" / "desk_tickets.html"
RESOLVED_JSON = ROOT / "output" / "resolved_tickets.json"
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"

NAMES = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting", "facilities": "Facilities", "customer_service": "Customer Service"}
SPECIALISTS = ["inventory", "accounting", "facilities", "customer_service"]

# The plan written in Problem 6 (Expected sections), used for an objective plan-vs-actual check.
PLAN = {
    101: {"first": "inventory", "delegations": ["inventory", "accounting", "customer_service"], "not_called": ["facilities"],
          "tools": {"get_ticket", "set_ticket_status", "get_cash_position", "check_stock", "get_vendor_status", "list_inventory",
                    "add_ticket_note", "get_invoice", "request_payment", "create_purchase_order", "save_draft_message"},
          "not_expected": {"get_lease_due", "check_margin", "request_discount_approval"}},
    102: {"first": "facilities", "delegations": ["facilities", "accounting"], "not_called": ["inventory", "customer_service"],
          "tools": {"get_ticket", "set_ticket_status", "get_cash_position", "get_lease_due", "add_ticket_note", "request_payment"},
          "not_expected": {"check_stock", "get_vendor_status", "create_purchase_order", "save_draft_message"}},
    103: {"first": "inventory", "delegations": ["inventory", "accounting", "accounting", "customer_service"], "not_called": ["facilities"],
          "tools": {"get_ticket", "set_ticket_status", "get_cash_position", "check_stock", "get_vendor_status", "list_inventory",
                    "add_ticket_note", "check_margin", "request_discount_approval", "save_draft_message"},
          "not_expected": {"create_purchase_order", "request_payment", "get_lease_due"}},
}


def get(path: str):
    with urllib.request.urlopen(API + path) as r:
        return json.load(r)


def money(x: float) -> str:
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


def esc(x) -> str:
    return html.escape(str(x))


def latest_runs(events: list[dict]) -> dict[int, list[dict]]:
    reset_idx = max((i for i, e in enumerate(events) if e["event"] == "db_reset"), default=-1)
    runs: dict[str, list[dict]] = {}
    for e in events[reset_idx + 1:]:
        runs.setdefault(e["run_id"], []).append(e)
    out: dict[int, list[dict]] = {}
    for run in runs.values():
        start = next((e for e in run if e["event"] == "ticket_run_start"), None)
        if start and any(e["event"] == "ticket_run_end" for e in run):
            out[start["ticket_id"]] = run  # later runs overwrite earlier ones
    return out


def analyse(run: list[dict]) -> dict:
    delegations = [e for e in run if e["event"] == "delegation"]
    results = {e["data"]["to_agent"]: [] for e in run if e["event"] == "delegation_result"}
    for e in run:
        if e["event"] == "delegation_result":
            results[e["data"]["to_agent"]].append(e["data"]["report"])
    calls = []
    for e in run:
        if e["event"] == "model_response":
            for c in e["data"]["tool_calls"]:
                if c["tool"] not in ("final_result", "delegate"):
                    calls.append({"agent": e["agent"], "tool": c["tool"], "args": {k: v for k, v in c["args"].items() if k not in ("agent", "reason", "body")}})
    start = next(e for e in run if e["event"] == "ticket_run_start")
    end = next(e for e in run if e["event"] == "ticket_run_end")
    responses = [e for e in run if e["event"] == "model_response"]
    models = sorted({m for e in responses for m in (e["data"].get("models_used") or [])})
    called = [a for a in SPECIALISTS if any(e["agent"] == a and e["event"] == "agent_start" for e in run)]
    violations = sum(1 for e in run if e["event"] == "model_violation")
    return {
        "run_id": start["run_id"],
        "started": start["logged_at"],
        "finished": end["logged_at"],
        "seconds": round((datetime.fromisoformat(end["logged_at"]) - datetime.fromisoformat(start["logged_at"])).total_seconds()),
        "decision": end["data"]["decision"],
        "budget": end["data"]["budget"],
        "delegations": [{"from": e["agent"], "to": e["data"]["to_agent"], "task": e["data"]["task"], "depth": e["depth"]} for e in delegations],
        "reports": results,
        "calls": calls,
        "model_requests": len(responses),
        "models": models,
        "called": called,
        "model_violations": violations,
    }


def compare(tid: int, a: dict) -> tuple[list[str], list[str]]:
    plan = PLAN[tid]
    match, diff = [], []
    first = a["delegations"][0]["to"] if a["delegations"] else None
    (match if first == plan["first"] else diff).append(
        f"First call: planned {NAMES[plan['first']]}, actual {NAMES.get(first, 'none')}.")
    boss_d = [d["to"] for d in a["delegations"] if d["from"] == "boss"]
    if boss_d == plan["delegations"]:
        match.append("Boss delegations in exactly the planned order: " + " → ".join(NAMES[x] for x in boss_d) + ".")
    else:
        diff.append("Boss delegations: planned " + " → ".join(NAMES[x] for x in plan["delegations"]) +
                    "; actual " + (" → ".join(NAMES[x] for x in boss_d) or "none") + ".")
    side = [d for d in a["delegations"] if d["from"] != "boss"]
    (diff if side else match).append(
        "Specialist-to-specialist delegations: " + (", ".join(f"{NAMES[d['from']]} → {NAMES[d['to']]}" for d in side) if side else "none, as planned") + ".")
    skipped_ok = [x for x in plan["not_called"] if x not in a["called"]]
    if len(skipped_ok) == len(plan["not_called"]):
        match.append("Not called, as planned: " + ", ".join(NAMES[x] for x in plan["not_called"]) + ".")
    else:
        diff.append("Planned to skip " + ", ".join(NAMES[x] for x in plan["not_called"]) + " but called: " +
                    ", ".join(NAMES[x] for x in plan["not_called"] if x in a["called"]) + ".")
    used = {c["tool"] for c in a["calls"]}
    missing = sorted(plan["tools"] - used)
    extra = sorted(used - plan["tools"])
    bad = sorted(used & plan["not_expected"])
    match.append(f"{len(plan['tools'] & used)} of {len(plan['tools'])} planned MCP tools were used.")
    if missing:
        diff.append("Planned but not used: " + ", ".join(f"<code>{t}</code>" for t in missing) + ".")
    if extra:
        diff.append("Used but not in the plan: " + ", ".join(f"<code>{t}</code>" for t in extra) + ".")
    if bad:
        diff.append("Used a tool the plan said should NOT be used: " + ", ".join(f"<code>{t}</code>" for t in bad) + ".")
    else:
        match.append("None of the tools the plan ruled out were used (" + ", ".join(f"<code>{t}</code>" for t in sorted(plan["not_expected"])) + ").")
    status = a["decision"]["final_status"]
    diff.append(f"Final status: the plan expected <code>waiting_on_approval</code>; actual <code>{status}</code>. "
                "Problem 8 changed \"resolved\" to mean the agents finished, with approvals left in the human inbox.")
    return match, diff


def args_text(args: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in args.items())


def actual_html(tid: int, a: dict, detail: dict, approvals: list[dict], extra_note: str = "") -> str:
    d = a["decision"]
    first = a["delegations"][0] if a["delegations"] else None
    match, diff = compare(tid, a)
    rows = []
    for i, dl in enumerate(a["delegations"], 1):
        reps = a["reports"].get(dl["to"], [])
        idx = sum(1 for x in a["delegations"][:i] if x["to"] == dl["to"]) - 1
        rep = reps[idx] if idx < len(reps) else None
        rows.append(
            f'<li><span class="arrow">{NAMES[dl["from"]]} → {NAMES[dl["to"]]}</span>'
            + (f' <span class="tag">depth {dl["depth"] + 1}</span>' if dl["depth"] else "")
            + f': “{esc(dl["task"][:420])}{"…" if len(dl["task"]) > 420 else ""}”'
            + (f'<div class="meta"><b>Reported back:</b> {esc(rep["summary"])}</div>' if rep else "")
            + "</li>")
    counts = Counter((c["agent"], c["tool"]) for c in a["calls"])
    seen, tool_rows = set(), []
    for c in a["calls"]:
        key = (c["agent"], c["tool"], json.dumps(c["args"], sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        tool_rows.append(f'<tr><td>{NAMES[c["agent"]]}</td><td><code>{esc(c["tool"])}({esc(args_text(c["args"]))})</code></td></tr>')
    not_called = [NAMES[x] for x in SPECIALISTS if x not in a["called"]]
    appr = "".join(
        f'<li>#{x["id"]} {esc(x["kind"])} {money(x["amount"]) if x["amount"] else "(no cash)"}: <b>{esc(x["status"])}</b>'
        + (f' by {esc(x["decided_by"])}' if x.get("decided_by") else "")
        + (f' (payment #{x["payment_id"]})' if x.get("payment_id") else "")
        + (f' · “{esc(x["decision_note"])}”' if x.get("decision_note") else "") + "</li>"
        for x in approvals)
    drafts = "".join(f'<li>Draft #{x["id"]} to {esc(x["recipient"])}: “{esc(x["subject"])}” (not sent)</li>' for x in detail["drafts"])
    pos = "".join(f'<li>PO #{x["id"]}: {x["qty"]} × {esc(x["sku"])} {esc(x["size"])}, {money(x["total"])}, {esc(x["status"])}'
                  + (f', ETA {esc(x["eta"])}' if x.get("eta") else "") + "</li>" for x in detail["purchase_orders"])
    return f'''  <!--ACTUAL-{tid}-START-->
  <div class="card first actual-card">
    <h3>Who the Boss actually called first</h3>
    <div class="who">{NAMES[first["to"]] if first else "Nobody"}</div>
    <p class="note">Run <code>{a["run_id"]}</code> · {a["seconds"]}s · {a["model_requests"]} model turns · {a["budget"]["delegations"]} delegations · {len(a["calls"])} MCP tool calls · model(s) used on every turn: {", ".join(f"<code>{m}</code>" for m in a["models"])} · model violations: {a["model_violations"]}</p>
  </div>
  <div class="card actual-card">
    <h3>Delegations that actually happened (in order)</h3>
    <ol class="flow">{"".join(rows) or "<li>None</li>"}</ol>
    <p class="note"><b>Agents that worked:</b> Boss, {", ".join(NAMES[x] for x in a["called"]) or "no specialists"}. <b>Not called:</b> {", ".join(not_called) or "none"}.</p>
  </div>
  <div class="card actual-card">
    <h3>MCP tools actually used ({len(a["calls"])} calls)</h3>
    <table><tr><th>Agent</th><th>Tool call (as logged in the audit trail)</th></tr>{"".join(tool_rows)}</table>
    <p class="note">Calls per agent: {", ".join(f"{NAMES[ag]} {n}" for ag, n in Counter(c["agent"] for c in a["calls"]).items())}.</p>
  </div>
  <div class="card outcome actual-card">
    <h3>Actual end state</h3>
    <p><b>The Boss’s call:</b> {esc(d["decision"])}</p>
    <ul class="tight">
      <li>Ticket {tid} is <span class="tag r">{esc(detail["ticket"]["status"])}</span>.</li>
      {f"<li><b>Human approvals:</b><ul class='tight'>{appr}</ul></li>" if appr else "<li>No approvals were requested.</li>"}
      {f"<li><b>Purchase orders:</b><ul class='tight'>{pos}</ul></li>" if pos else ""}
      {f"<li><b>Drafts:</b><ul class='tight'>{drafts}</ul></li>" if drafts else "<li>No drafts.</li>"}
    </ul>
  </div>
  <div class="card compare actual-card">
    <h3>Plan vs. actual</h3>
    <div class="cmp"><div><h4>✓ Matched the plan</h4><ul class="tight">{"".join(f"<li>{m}</li>" for m in match)}</ul></div>
    <div><h4>≠ Differed from the plan</h4><ul class="tight">{"".join(f"<li>{x}</li>" for x in diff)}</ul></div></div>
    {f'<p class="note">{extra_note}</p>' if extra_note else ""}
  </div>
  <!--ACTUAL-{tid}-END-->
'''


def cash_html(start: float, per_ticket: list[dict], payments: list[dict], ending_api: float, ending_db: float, unpaid: list[dict]) -> str:
    running = start
    rows = []
    for t in per_ticket:
        lines = []
        for p in t["payments"]:
            running -= p["amount"]
            lines.append(f'<tr><td>#{t["id"]}</td><td>{esc(p["what"])}</td><td>payment #{p["payment_id"]} · approval #{p["approval_id"]} · signed by {esc(p["approved_by"])}</td>'
                         f'<td class="num neg">−{money(p["amount"])}</td><td class="num">{money(running)}</td></tr>')
        if not lines:
            lines.append(f'<tr><td>#{t["id"]}</td><td colspan="2">{esc(t["no_cash_reason"])}</td><td class="num">$0.00</td><td class="num">{money(running)}</td></tr>')
        rows.extend(lines)
        rows.append(f'<tr class="subtotal"><td></td><td colspan="2">Ticket {t["id"]} total</td><td class="num {"neg" if t["total"] else ""}">{"−" + money(t["total"]) if t["total"] else "$0.00"}</td><td></td></tr>')
    computed = round(start - sum(p["amount"] for p in payments), 2)
    ok = computed == round(ending_db, 2) == round(ending_api, 2)
    unpaid_rows = "".join(f'<li>#{u["id"]} ({esc(u["kind"])}, ticket {u["ticket_id"]}): {money(u["amount"]) if u["amount"] else "no cash"}, <b>{esc(u["status"])}</b>'
                          + (f' by {esc(u["decided_by"])}' if u.get("decided_by") else "") + (f': “{esc(u["decision_note"])}”' if u.get("decision_note") else "") + "</li>" for u in unpaid)
    return f'''  <!--CASH-START-->
  <div class="card">
    <h2>Cash</h2>
    <p class="note">Every figure below comes from the <code>payments</code> and <code>cash_accounts</code> tables after the full run. Cash only goes out; no revenue is modelled.</p>
    <div class="cash-kpis">
      <div><b>Starting checking (after reset)</b><span>{money(start)}</span></div>
      <div><b>Paid out (human-approved)</b><span class="neg">−{money(sum(p["amount"] for p in payments))}</span></div>
      <div><b>Ending checking</b><span>{money(ending_db)}</span></div>
    </div>
  </div>
  <div class="card">
    <h3>How cash changed, ticket by ticket</h3>
    <table class="ledger-table"><tr><th>Ticket</th><th>What was paid</th><th>Record</th><th class="num">Amount</th><th class="num">Balance</th></tr>
      <tr><td></td><td colspan="2"><b>Starting balance</b> (checking, right after the reset)</td><td></td><td class="num"><b>{money(start)}</b></td></tr>
      {"".join(rows)}
      <tr class="total"><td></td><td colspan="2"><b>Ending balance</b></td><td class="num neg">−{money(sum(p["amount"] for p in payments))}</td><td class="num"><b>{money(running)}</b></td></tr>
    </table>
  </div>
  <div class="card {"outcome" if ok else ""}">
    <h3>Check against the database</h3>
    <ul class="tight">
      <li>{money(start)} − {" − ".join(money(p["amount"]) for p in payments) or "$0.00"} = <b>{money(computed)}</b></li>
      <li><code>cash_accounts</code> (checking) in <code>data/campus_customs_new.db</code>: <b>{money(ending_db)}</b> (read directly from the file)</li>
      <li><code>GET /api/cash</code>: <b>{money(ending_api)}</b></li>
      <li>{"✓ All three agree." if ok else "✗ MISMATCH: investigate before submitting."}</li>
    </ul>
  </div>
  {f'<div class="card skip"><h3>Requests that moved no cash</h3><ul class="tight">{unpaid_rows}</ul></div>' if unpaid_rows else ""}
  <!--CASH-END-->'''


EXTRA_CSS = """
  .badge.actual.done { background: #e7f6ee; color: var(--ok); }
  .actual-card { border-left: 4px solid var(--ok); }
  .compare .cmp { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  .compare h4 { margin: 0 0 6px; font-size: 13px; }
  .cash-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 12px; }
  .cash-kpis div { background: #f7faff; border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
  .cash-kpis b { display: block; font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .4px; }
  .cash-kpis span { font-size: 24px; font-weight: 700; color: var(--yale); }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .neg { color: var(--bad) !important; }
  .ledger-table tr.subtotal td { color: var(--muted); font-size: 12.5px; background: #fafbfd; }
  .ledger-table tr.total td { border-top: 2px solid var(--yale); }
"""


def main() -> None:
    events = json.loads(AUDIT.read_text())
    runs = latest_runs(events)
    missing = [t for t in (101, 102, 103) if t not in runs]
    if missing:
        raise SystemExit(f"No completed run after the last reset for tickets {missing}.")

    with sqlite3.connect(f"file:{ORIGINAL_DB}?mode=ro", uri=True) as c:
        start = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    with sqlite3.connect(f"file:{WORKING_DB}?mode=ro", uri=True) as c:
        ending_db = c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    cash = get("/cash")
    all_appr = get("/approvals?status=")["approvals"]
    payments = cash["payments_made"]
    pay_by_id = {p["id"]: p for p in payments}

    page = DESK.read_text()
    resolved, per_ticket = [], []
    for tid in (101, 102, 103):
        a = analyse(runs[tid])
        detail = get(f"/tickets/{tid}")
        approvals = [x for x in all_appr if x["ticket_id"] == tid]
        block_start, block_end = f"  <!--ACTUAL-{tid}-START-->", f"  <!--ACTUAL-{tid}-END-->\n"
        i, j = page.index(block_start), page.index(block_end) + len(block_end)
        page = page[:i] + actual_html(tid, a, detail, approvals) + page[j:]

        paid = []
        for x in approvals:
            if x["status"] == "paid" and x["payment_id"] in pay_by_id:
                det = x["details"] or {}
                what = {"invoice": f"Invoice #{det.get('invoice_id')} to {det.get('payee')}",
                        "rent": f"Rent, lease {det.get('lease_id')} ({det.get('space_name')}) to {det.get('payee')}",
                        "purchase_order": f"PO #{det.get('purchase_order_id')}: {det.get('qty')} × {det.get('sku')} {det.get('size')} from {det.get('payee')}"}.get(x["kind"], x["kind"])
                p = pay_by_id[x["payment_id"]]
                paid.append({"approval_id": x["id"], "payment_id": p["id"], "kind": x["kind"], "what": what, "amount": p["amount"], "approved_by": p["approved_by"]})
        reasons = [f"#{x['id']} {x['kind']} {x['status']}" for x in approvals if x["status"] != "paid"]
        per_ticket.append({"id": tid, "payments": paid, "total": round(sum(p["amount"] for p in paid), 2),
                           "no_cash_reason": "No payment. " + ("; ".join(reasons) if reasons else "No cash request was made.")})

        agents = {"boss": {"role": "Routed the ticket and made the final call", "decision": a["decision"]["decision"],
                           "rationale": a["decision"]["rationale"], "delegated_to": [NAMES[d["to"]] for d in a["delegations"] if d["from"] == "boss"],
                           "tools": sorted({c["tool"] for c in a["calls"] if c["agent"] == "boss"})}}
        for sp in SPECIALISTS:
            reps = a["reports"].get(sp, [])
            agents[sp] = {"called": sp in a["called"],
                          "contribution": [r["summary"] for r in reps],
                          "actions": [x for r in reps for x in r["actions_taken"]],
                          "blockers": [x for r in reps for x in r["blockers"]],
                          "tools": sorted({c["tool"] for c in a["calls"] if c["agent"] == sp})}
        resolved.append({
            "id": tid,
            "type": detail["ticket"]["type"],
            "requester": detail["ticket"]["requester"],
            "subject": detail["ticket"]["subject"],
            "final_status": detail["ticket"]["status"],
            "short_outcome": a["decision"]["decision"],
            "run": {"run_id": a["run_id"], "started": a["started"], "finished": a["finished"], "seconds": a["seconds"],
                    "model_turns": a["model_requests"], "delegations": a["budget"]["delegations"], "mcp_tool_calls": len(a["calls"]), "models": a["models"], "model_violations": a["model_violations"]},
            "agents": agents,
            "human_approvals": [{"approval_id": x["id"], "kind": x["kind"], "amount": x["amount"], "payee": (x["details"] or {}).get("payee"),
                                 "status": x["status"], "decided_by": x["decided_by"], "decision_note": x["decision_note"], "payment_id": x["payment_id"],
                                 "requested_by": x["requested_by"], "reason": x["reason"]} for x in approvals],
            "cash_change": -round(sum(p["amount"] for p in paid), 2),
            "purchase_orders": detail["purchase_orders"],
            "drafts": [{"id": x["id"], "recipient": x["recipient"], "subject": x["subject"], "sent": False} for x in detail["drafts"]],
        })

    unpaid = [x for x in all_appr if x["status"] != "paid"]
    i, j = page.index("  <!--CASH-START-->"), page.index("<!--CASH-END-->") + len("<!--CASH-END-->")
    page = page[:i] + cash_html(start, per_ticket, payments, cash["balance"], ending_db, unpaid) + page[j:]
    page = page.replace('<span class="badge actual">to fill after the run</span>', '<span class="badge actual done">from the full run</span>')
    if ".badge.actual.done" not in page:
        page = page.replace("</style>", EXTRA_CSS + "</style>", 1)
    DESK.write_text(page)

    computed = round(start - sum(p["amount"] for p in payments), 2)
    RESOLVED_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shop_date": cash["date_today"],
        "database": "data/campus_customs_new.db",
        "cash": {"starting_balance": start, "total_paid_out": round(sum(p["amount"] for p in payments), 2),
                 "ending_balance_computed": computed, "ending_balance_cash_accounts": ending_db,
                 "matches": computed == round(ending_db, 2)},
        "tickets": resolved,
    }, indent=2) + "\n")
    print(f"start {money(start)} -> end {money(ending_db)} (computed {money(computed)}); "
          f"statuses {[r['final_status'] for r in resolved]}; payments {len(payments)}")


if __name__ == "__main__":
    main()
