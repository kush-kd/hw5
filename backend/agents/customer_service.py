"""Customer Service: drafts messages for customers (and other requesters). Drafts are never sent."""

from agents.base import AgentSpec
from models import AgentReport

SPEC = AgentSpec(
    name="customer_service",
    title="Customer Service",
    prompt_file="customer_service.md",
    mcp_tools=("get_ticket", "check_stock", "list_inventory", "save_draft_message", "add_ticket_note"),
    output_type=AgentReport,
    request_limit=6,
    tool_calls_limit=12,
)
