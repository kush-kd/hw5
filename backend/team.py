"""The Campus Customs agent team: five PydanticAI agents, fully connected, sharing one MCP server.

- Every shop fact and every database change goes through the MCP server (mcp_server/server.py).
  Each agent sees only its allowlisted MCP tools (agents/*.py), and none of them can see the
  human-only approval tools. The agents' MCP server process isn't even given the approval key.
- Full connectivity: every agent has a `delegate` tool that can hand a task to any other agent.
  Delegation is limited by depth, a per-ticket budget, and a no-cycles rule.
- Every agent-loop step (model request, model response with tool calls, tool results,
  delegation, final output, errors) is appended to output/audit_trail.json.
"""

from __future__ import annotations

import os
import uuid
from contextlib import AsyncExitStack
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

import audit
from agents import SPECS
from agents.base import AgentSpec
from config import (
    DB_PATH,
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_MODEL_REQUESTS_PER_TICKET,
    MCP_SERVER_SCRIPT,
    MODEL,
    PYTHON,
    ROOT,
)
from llm.claude_subscription import subscription_model
from models import AgentName, Budget, TeamDeps, TicketDecision


class BudgetExceeded(RuntimeError):
    pass


def _mcp_client() -> Client:
    """Stdio client for the shop's MCP server, pointed at the working DB.

    HUMAN_APPROVAL_KEY is deliberately stripped: this server process serves the agents,
    so its human-only tools refuse even if something tried to call them.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("HUMAN_APPROVAL_KEY", "ANTHROPIC_API_KEY")}
    env["CAMPUS_CUSTOMS_DB"] = str(DB_PATH)
    return Client(StdioTransport(command=PYTHON, args=[str(MCP_SERVER_SCRIPT)], env=env, cwd=str(ROOT)))


async def delegate(ctx: RunContext[TeamDeps], to_agent: AgentName, task: str) -> dict[str, Any]:
    """Hand a specific sub-task on the current ticket to another agent and wait for its report.

    Team: boss (routes tickets, final calls), inventory (stock by SKU/size, shortfalls, which
    vendor can restock), accounting (cash, invoices, margins, payment / purchase-order /
    discount approval requests), facilities (leases, rent notices), customer_service (drafts
    messages to customers and requesters; never sends). Write `task` so it stands alone:
    include the ticket's SKU, size, qty, ids and any facts the other agent needs. You cannot
    delegate to yourself or to an agent already above you in the delegation chain.
    """
    return await ctx.deps.team.delegate(ctx.deps, to_agent, task)


class Team:
    def __init__(self) -> None:
        self.client = _mcp_client()
        self.mcp = MCPToolset(self.client)
        self.model = subscription_model()
        delegation = FunctionToolset([delegate])
        self.agents: dict[str, Agent] = {name: self._build(spec, delegation) for name, spec in SPECS.items()}
        self._stack: AsyncExitStack | None = None

    def _build(self, spec: AgentSpec, delegation: FunctionToolset) -> Agent:
        allowed = frozenset(spec.mcp_tools)
        return Agent(
            self.model,
            name=spec.name,
            deps_type=TeamDeps,
            output_type=spec.output_type,
            instructions=spec.instructions(),
            toolsets=[self.mcp.filtered(lambda ctx, tool_def, allowed=allowed: tool_def.name in allowed), delegation],
            retries=2,
        )

    async def __aenter__(self) -> "Team":
        self._stack = AsyncExitStack()
        await self._stack.enter_async_context(self.client)
        await self._stack.enter_async_context(self.mcp)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack:
            await self._stack.aclose()

    async def call_tool(self, name: str, **args: Any) -> Any:
        """Orchestrator-level MCP call (e.g. listing open tickets). Still goes through MCP."""
        return (await self.client.call_tool(name, args)).data

    # ---------------------------------------------------------------- ticket runs

    async def run_ticket(self, ticket_id: int, run_id: str | None = None) -> TicketDecision | None:
        deps = TeamDeps(team=self, run_id=run_id or uuid.uuid4().hex[:12], ticket_id=ticket_id, agent="boss", chain=("boss",), depth=0, budget=Budget())
        ticket = await self.call_tool("get_ticket", ticket_id=ticket_id)
        audit.log("ticket_run_start", run_id=deps.run_id, ticket_id=ticket_id, agent="boss", chain=deps.chain,
                  model=MODEL, shop_date=ticket.get("date_today"), ticket=ticket.get("ticket"))
        prompt = (
            f"Ticket #{ticket_id} is on the board. Handle it end to end: read it, route the work to the "
            "right agents, make the final call, and leave the ticket in the correct status."
        )
        try:
            decision = await self.run_agent("boss", prompt, deps)
        except Exception as exc:  # recorded, never swallowed silently
            audit.log("ticket_run_error", run_id=deps.run_id, ticket_id=ticket_id, agent="boss", chain=deps.chain,
                      error=f"{type(exc).__name__}: {exc}", budget=vars(deps.budget))
            raise
        audit.log("ticket_run_end", run_id=deps.run_id, ticket_id=ticket_id, agent="boss", chain=deps.chain,
                  decision=decision.model_dump(), budget=vars(deps.budget))
        return decision

    async def run_open_tickets(self) -> list[TicketDecision | None]:
        board = await self.call_tool("list_open_tickets")
        return [await self.run_ticket(t["id"]) for t in board["tickets"]]

    # ------------------------------------------------------------ one agent's loop

    async def run_agent(self, name: str, prompt: str, deps: TeamDeps):
        spec = SPECS[name]
        agent = self.agents[name]
        where = dict(run_id=deps.run_id, ticket_id=deps.ticket_id, agent=name, chain=deps.chain, depth=deps.depth)
        audit.log("agent_start", **where, prompt=prompt, mcp_tools=list(spec.mcp_tools),
                  limits={"request_limit": spec.request_limit, "tool_calls_limit": spec.tool_calls_limit})
        limits = UsageLimits(request_limit=spec.request_limit, tool_calls_limit=spec.tool_calls_limit)
        step = 0
        async with agent.iter(prompt, deps=deps, usage_limits=limits) as run:
            async for node in run:
                step += 1
                if Agent.is_model_request_node(node):
                    if name != "boss" and deps.budget.model_requests >= MAX_MODEL_REQUESTS_PER_TICKET:
                        audit.log("budget_exceeded", **where, step=step, budget=vars(deps.budget))
                        raise BudgetExceeded(f"Ticket model-request budget ({MAX_MODEL_REQUESTS_PER_TICKET}) used up.")
                    deps.budget.model_requests += 1
                    audit.log("model_request", **where, step=step, inputs=_request_parts(node.request.parts))
                elif Agent.is_call_tools_node(node):
                    r = node.model_response
                    audit.log(
                        "model_response", **where, step=step,
                        model=r.model_name,
                        reasoning=(r.provider_details or {}).get("reasoning"),
                        tool_calls=[{"tool": p.tool_name, "args": p.args, "id": p.tool_call_id} for p in r.parts if isinstance(p, ToolCallPart)],
                        text=[p.content for p in r.parts if isinstance(p, TextPart)],
                        usage={"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens,
                               "cache_read_tokens": r.usage.cache_read_tokens, "cache_write_tokens": r.usage.cache_write_tokens},
                        latency_s=(r.provider_details or {}).get("latency_s"),
                        models_used=(r.provider_details or {}).get("models_used"),
                    )
                    used = (r.provider_details or {}).get("models_used") or []
                    if any(m != MODEL for m in used):  # every call must run on MODEL only
                        audit.log("model_violation", **where, step=step, expected=MODEL, models_used=used)
                elif Agent.is_end_node(node):
                    audit.log("final_output", **where, step=step, output=node.data.output.model_dump())
            usage = run.usage
        audit.log("agent_end", **where, steps=step, usage={"requests": usage.requests, "tool_calls": usage.tool_calls,
                  "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens})
        return run.result.output

    # --------------------------------------------------------------- delegation

    async def delegate(self, parent: TeamDeps, to_agent: str, task: str) -> dict[str, Any]:
        where = dict(run_id=parent.run_id, ticket_id=parent.ticket_id, agent=parent.agent, chain=parent.chain, depth=parent.depth)
        refusal = None
        if to_agent not in SPECS:
            refusal = f"Unknown agent {to_agent!r}."
        elif to_agent == parent.agent:
            refusal = "You cannot delegate to yourself; do the work with your own tools."
        elif to_agent in parent.chain:
            refusal = (f"{to_agent} is already above you in this delegation chain ({' -> '.join(parent.chain)}). "
                       "Put what you need from them in your final report instead.")
        elif parent.depth + 1 > MAX_DELEGATION_DEPTH:
            refusal = f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached; finish with what you have and report blockers."
        elif parent.budget.delegations >= MAX_DELEGATIONS_PER_TICKET:
            refusal = f"Per-ticket delegation budget ({MAX_DELEGATIONS_PER_TICKET}) used up; finish with what you have."
        elif parent.budget.model_requests >= MAX_MODEL_REQUESTS_PER_TICKET:
            refusal = "Per-ticket model-request budget used up; finish with what you have."
        if refusal:
            audit.log("delegation_refused", **where, to_agent=to_agent, task=task, reason=refusal)
            return {"ok": False, "error": refusal}

        parent.budget.delegations += 1
        child = TeamDeps(team=self, run_id=parent.run_id, ticket_id=parent.ticket_id, agent=to_agent,  # type: ignore[arg-type]
                         chain=(*parent.chain, to_agent), depth=parent.depth + 1, budget=parent.budget)
        audit.log("delegation", **where, to_agent=to_agent, task=task, delegation_number=parent.budget.delegations)
        prompt = f"Ticket #{parent.ticket_id}. Task from {parent.agent}:\n{task}"
        try:
            report = await self.run_agent(to_agent, prompt, child)
        except Exception as exc:
            audit.log("delegation_error", **where, to_agent=to_agent, error=f"{type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"{to_agent} could not finish: {type(exc).__name__}: {exc}"}
        audit.log("delegation_result", **where, to_agent=to_agent, report=report.model_dump())
        return {"ok": True, "report": report.model_dump()}


def _request_parts(parts) -> list[dict[str, Any]]:
    out = []
    for p in parts:
        if isinstance(p, UserPromptPart):
            out.append({"kind": "task", "content": p.content})
        elif isinstance(p, ToolReturnPart):
            out.append({"kind": "tool_result", "tool": p.tool_name, "id": p.tool_call_id, "content": p.content})
        elif isinstance(p, RetryPromptPart):
            out.append({"kind": "retry", "tool": p.tool_name, "id": p.tool_call_id, "content": p.content})
    return out
