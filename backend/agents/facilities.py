"""Facilities: handles the shop space -- leases, rent notices, and the landlord."""

from agents.base import AgentSpec
from models import AgentReport

SPEC = AgentSpec(
    name="facilities",
    title="Facilities",
    prompt_file="facilities.md",
    mcp_tools=("get_ticket", "get_lease_due", "get_cash_position", "add_ticket_note"),
    output_type=AgentReport,
    request_limit=6,
    tool_calls_limit=12,
)
