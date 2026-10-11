"""Data types shared by the agent team: agent outputs, run context, and audit events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from team import Team

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "blocked", "resolved"]


class Fact(BaseModel):
    """One shop fact an agent relied on, tied to the MCP tool that returned it."""

    statement: str = Field(description="The fact, with exact numbers/dates as the tool returned them.")
    source_tool: str = Field(description="MCP tool name the fact came from, e.g. check_stock.")


class AgentReport(BaseModel):
    """What a specialist (Inventory, Accounting, Facilities, Customer Service) hands back."""

    agent: AgentName
    ticket_id: int
    summary: str = Field(description="2-4 sentences: what you found and did.")
    facts: list[Fact] = Field(default_factory=list, description="Every number you relied on, with its source tool.")
    actions_taken: list[str] = Field(default_factory=list, description="Database changes you made via MCP tools.")
    approval_ids: list[int] = Field(default_factory=list, description="Approval requests you created (pending human).")
    purchase_order_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list, description="What stops the ticket from moving forward.")
    recommendations: list[str] = Field(default_factory=list, description="What you advise the Boss to do next.")
    needs_human: bool = Field(description="True if a human must approve or decide something.")


class TicketDecision(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    final_status: TicketStatus
    decision: str = Field(description="The final call in 1-3 sentences.")
    rationale: str = Field(description="Why, citing the facts the team found.")
    agents_consulted: list[AgentName] = Field(default_factory=list)
    approval_ids: list[int] = Field(default_factory=list, description="Approvals waiting on the human for this ticket.")
    purchase_order_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    human_actions_required: list[str] = Field(default_factory=list, description="Exactly what the human must approve/do.")
    next_steps: list[str] = Field(default_factory=list)


@dataclass
class Budget:
    """Per-ticket counters shared by every agent working on that ticket."""

    model_requests: int = 0
    delegations: int = 0


@dataclass
class TeamDeps:
    """PydanticAI deps for one agent run inside a ticket run."""

    team: "Team"
    run_id: str
    ticket_id: int
    agent: AgentName
    chain: tuple[AgentName, ...]  # who delegated to whom, root first; used to stop cycles
    depth: int
    budget: Budget = field(default_factory=Budget)


class AuditEvent(BaseModel):
    """One line of output/audit_trail.json."""

    event_id: str
    logged_at: str  # wall-clock UTC, when the event was written
    run_id: str
    ticket_id: int | None
    agent: AgentName | None
    chain: list[str] = Field(default_factory=list)
    depth: int = 0
    step: int | None = None
    event: str  # ticket_run_start | agent_start | model_request | model_response | delegation | ... | final_output | error
    data: dict[str, Any] = Field(default_factory=dict)
