"""FastAPI backend for the Campus Customs operations dashboard.

Start from the backend/ folder:
    uvicorn main:app --reload --port 8000

Every shop fact these routes return, and every change they make, goes through the MCP
server -- the same toolbox the agents use. Two MCP connections are opened:

- the **agent team's** connection (inside `Team`), whose server process is NOT given the
  human-approval key, so agents can never pay;
- the **desk** connection used by these routes, whose server process IS given the key,
  because the approve/reject routes are what a human clicks.

The approve route is the only code path that moves cash.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel, Field

import audit
from config import AUDIT_PATH, DB_PATH, MCP_SERVER_SCRIPT, PYTHON, ROOT
from team import Team

sys.path.insert(0, str(ROOT / "scripts"))
from reset_db import reset as reset_working_db  # noqa: E402

# The human-approval key lives only in this process and the desk MCP server it launches.
HUMAN_APPROVAL_KEY = os.environ.get("HUMAN_APPROVAL_KEY") or secrets.token_urlsafe(32)


def _desk_client() -> Client:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env.update({"CAMPUS_CUSTOMS_DB": str(DB_PATH), "HUMAN_APPROVAL_KEY": HUMAN_APPROVAL_KEY})
    return Client(StdioTransport(command=PYTHON, args=[str(MCP_SERVER_SCRIPT)], env=env, cwd=str(ROOT)))


class State:
    desk: Client
    team: Team
    runs: dict[str, dict[str, Any]] = {}
    active_run: str | None = None
    lock = asyncio.Lock()


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state.desk = _desk_client()
    state.team = Team()
    async with state.desk, state.team:
        yield


app = FastAPI(title="Campus Customs Ops API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # the React dashboard (Vite)
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp(tool: str, **args: Any) -> Any:
    """Call an MCP tool on the desk connection and return its data."""
    result = await state.desk.call_tool(tool, args, raise_on_error=False)
    if result.is_error:
        raise HTTPException(502, f"MCP tool {tool} failed: {result.content[0].text if result.content else ''}")
    return result.data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------------------ tickets


@app.get("/api/tickets")
async def list_tickets():
    """All tickets on the board with status, open/resolved, and attached work counts."""
    data = await mcp("list_tickets")
    running = {r["ticket_id"] for r in state.runs.values() if r["status"] == "running"}
    for t in data["tickets"]:
        t["state"] = "resolved" if t["is_resolved"] else "open"
        t["agents_running"] = t["id"] in running
    return data


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int):
    """One ticket with its notes, approvals, purchase orders, and drafts."""
    data = await mcp("get_ticket", ticket_id=ticket_id)
    if not data.get("found"):
        raise HTTPException(404, data.get("error"))
    return data


async def _run(run_id: str, ticket_id: int) -> None:
    run = state.runs[run_id]
    try:
        decision = await state.team.run_ticket(ticket_id, run_id=run_id)
        run.update(status="completed", decision=decision.model_dump() if decision else None)
    except Exception as exc:  # also written to the audit trail by Team.run_ticket
        run.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        run["finished_at"] = _now()
        state.active_run = None


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int):
    """Start the agent team on one ticket in the background. Poll /api/runs/{run_id} or /api/events."""
    ticket = await mcp("get_ticket", ticket_id=ticket_id)
    if not ticket.get("found"):
        raise HTTPException(404, ticket.get("error"))
    async with state.lock:
        # One run at a time: every run plans against the same cash, so runs must not overlap.
        if state.active_run:
            active = state.runs[state.active_run]
            raise HTTPException(409, f"Agents are already working on ticket {active['ticket_id']} (run {state.active_run}).")
        run_id = uuid.uuid4().hex[:12]
        state.runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "started_at": _now(),
                              "finished_at": None, "decision": None, "error": None}
        state.active_run = run_id
    asyncio.create_task(_run(run_id, ticket_id))
    return state.runs[run_id]


@app.get("/api/runs")
async def list_runs():
    """Agent runs started since the server came up, newest first."""
    return {"active_run": state.active_run, "runs": sorted(state.runs.values(), key=lambda r: r["started_at"], reverse=True)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    if run_id not in state.runs:
        raise HTTPException(404, f"No run {run_id} since the server started.")
    return state.runs[run_id]


# ------------------------------------------------------------------------------- events


def _summarize(seq: int, e: dict) -> dict:
    """Turn one audit-trail event into what the board shows: who, what they said, which tools."""
    d = e.get("data", {})
    said, tools, results, output = None, [], [], None
    kind = e["event"]
    if kind == "model_response":
        said = d.get("reasoning")
        tools = [{"tool": c["tool"], "args": c["args"]} for c in d.get("tool_calls", [])]
    elif kind == "model_request":
        for part in d.get("inputs", []):
            if part["kind"] == "tool_result":
                text = json.dumps(part["content"], default=str) if not isinstance(part["content"], str) else part["content"]
                results.append({"tool": part["tool"], "result": text[:400]})
    elif kind == "delegation":
        said = f"→ {d.get('to_agent')}: {d.get('task')}"
        tools = [{"tool": "delegate", "args": {"to_agent": d.get("to_agent")}}]
    elif kind == "delegation_refused":
        said = f"Delegation to {d.get('to_agent')} refused: {d.get('reason')}"
    elif kind == "final_output":
        out = d.get("output", {})
        said = out.get("decision") or out.get("summary")
        output = out
    elif kind == "agent_start":
        said = d.get("prompt")
    elif kind == "ticket_run_end":
        said = (d.get("decision") or {}).get("decision")
        output = d.get("decision")
    elif kind in ("ticket_run_error", "delegation_error", "budget_exceeded"):
        said = d.get("error") or d.get("reason") or "budget exceeded"
    elif kind.startswith("human_") or kind == "db_reset":
        said = d.get("summary")
    return {
        "seq": seq,
        "event_id": e["event_id"],
        "logged_at": e["logged_at"],
        "run_id": e["run_id"],
        "ticket_id": e["ticket_id"],
        "agent": e["agent"],
        "chain": e.get("chain", []),
        "depth": e.get("depth", 0),
        "step": e.get("step"),
        "event": kind,
        "said": said,
        "tools": tools,
        "tool_results": results,
        "model": d.get("model") if kind == "model_response" else None,
        "output": output,
    }


@app.get("/api/events")
async def events(
    after: int | None = Query(None, description="Return events with seq greater than this (for polling)."),
    limit: int = Query(100, ge=1, le=1000),
    ticket_id: int | None = None,
    run_id: str | None = None,
):
    """Recent agent events from output/audit_trail.json: who spoke, what they said, which tools they used."""
    try:
        raw = json.loads(AUDIT_PATH.read_text()) if AUDIT_PATH.exists() else []
    except json.JSONDecodeError:
        raw = []
    items = [(i, e) for i, e in enumerate(raw)
             if (ticket_id is None or e.get("ticket_id") == ticket_id) and (run_id is None or e.get("run_id") == run_id)]
    if after is not None:
        items = [(i, e) for i, e in items if i > after][:limit]
    else:
        items = items[-limit:]
    out = [_summarize(i, e) for i, e in items]
    return {"total": len(raw), "next_after": out[-1]["seq"] if out else after, "events": out}


# ----------------------------------------------------------------------------- approvals


async def _approval(approval_id: int) -> dict:
    rows = (await mcp("list_approvals", status=None))["approvals"]
    match = next((a for a in rows if a["id"] == approval_id), None)
    if match is None:
        raise HTTPException(404, f"No approval with id {approval_id}.")
    return match


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human clicking Approve.")


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


@app.get("/api/approvals")
async def list_approvals(status: str | None = "pending"):
    """The human-approval queue (status=pending|paid|approved|rejected; omit value for all)."""
    return await mcp("list_approvals", status=status or None)


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: ApproveBody):
    """A human approved: pay the invoice / rent / purchase order (or approve the discount).
    This is the only route that changes cash. The MCP pay tool refuses if cash would go negative."""
    req = await _approval(approval_id)
    result = await mcp("human_approve_and_pay", approval_id=approval_id, approved_by=body.approved_by,
                       approval_key=HUMAN_APPROVAL_KEY)
    audit.log("human_approval", run_id="dashboard", ticket_id=req["ticket_id"], agent=None, approval_id=approval_id,
              kind=req["kind"], amount=req["amount"],
              approved_by=body.approved_by, result=result,
              summary=f"{body.approved_by} approved #{approval_id}: " + ("ok" if result.get("ok") else result.get("error", "")))
    if not result.get("ok"):
        raise HTTPException(409, result.get("error"))
    return result


@app.post("/api/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: RejectBody):
    """A human rejected the request. No cash moves; a rejected purchase order is cancelled."""
    req = await _approval(approval_id)
    result = await mcp("human_reject_request", approval_id=approval_id, rejected_by=body.rejected_by,
                       reason=body.reason, approval_key=HUMAN_APPROVAL_KEY)
    audit.log("human_rejection", run_id="dashboard", ticket_id=req["ticket_id"], agent=None, approval_id=approval_id,
              kind=req["kind"], amount=req["amount"],
              rejected_by=body.rejected_by, result=result,
              summary=f"{body.rejected_by} rejected #{approval_id}: {body.reason}")
    if not result.get("ok"):
        raise HTTPException(409, result.get("error"))
    return result


# ---------------------------------------------------------------------------------- cash


@app.get("/api/cash")
async def cash():
    """Current checking balance from cash_accounts, plus what is pending human approval."""
    c = await mcp("get_cash_position", account="checking")
    return {
        "account": c["account"],
        "balance": c["balance"],
        "balance_as_of": c["balance_as_of"],
        "date_today": c["date_today"],
        "pending_total": c["pending_total"],
        "available_after_pending": c["available_after_pending"],
        "payments_made": c["payments_made"],
    }


# --------------------------------------------------------------------------------- reset


@app.post("/api/reset")
async def reset():
    """Restore data/campus_customs_new.db from the untouched original for a fresh run.
    Refused while agents are running. The audit trail is kept (append-only)."""
    async with state.lock:
        if state.active_run:
            raise HTTPException(409, "Agents are running; wait for the run to finish before resetting.")
        reset_working_db()
    audit.log("db_reset", run_id="dashboard", summary="Working database reset to the original values.")
    board = await mcp("list_tickets")
    c = await mcp("get_cash_position")
    return {"ok": True, "tickets": [(t["id"], t["status"]) for t in board["tickets"]], "balance": c["balance"]}


@app.get("/api/health")
async def health():
    return {"ok": True, "db": str(DB_PATH.relative_to(ROOT)), "active_run": state.active_run}
