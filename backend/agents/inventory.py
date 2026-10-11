"""Inventory: checks stock by SKU and size, spots shortfalls, and finds the vendor who can restock."""

from agents.base import AgentSpec
from models import AgentReport

SPEC = AgentSpec(
    name="inventory",
    title="Inventory",
    prompt_file="inventory.md",
    mcp_tools=("get_ticket", "check_stock", "list_inventory", "get_vendor_status", "add_ticket_note"),
    output_type=AgentReport,
    request_limit=8,
    tool_calls_limit=16,
)
