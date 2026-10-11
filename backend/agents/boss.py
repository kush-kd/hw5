"""Boss: reads each ticket, decides who works on it, and makes the final call."""

from agents.base import AgentSpec
from models import TicketDecision

SPEC = AgentSpec(
    name="boss",
    title="Boss",
    prompt_file="boss.md",
    mcp_tools=("list_open_tickets", "get_ticket", "get_cash_position", "list_approvals", "add_ticket_note", "set_ticket_status"),
    output_type=TicketDecision,
    request_limit=14,
    tool_calls_limit=24,
)
