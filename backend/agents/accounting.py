"""Accounting: watches cash and invoices, checks margins, prepares payments and POs for human approval."""

from agents.base import AgentSpec
from models import AgentReport

SPEC = AgentSpec(
    name="accounting",
    title="Accounting",
    prompt_file="accounting.md",
    mcp_tools=(
        "get_ticket", "get_cash_position", "get_invoice", "get_vendor_status", "get_lease_due",
        "check_margin", "list_approvals", "request_payment", "create_purchase_order",
        "request_discount_approval", "add_ticket_note",
    ),
    output_type=AgentReport,
    request_limit=10,
    tool_calls_limit=20,
)
