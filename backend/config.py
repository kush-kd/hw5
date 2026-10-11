"""One place for paths, the model, and the limits that keep the agent team cheap and safe."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PROMPTS_DIR = BACKEND / "prompts"
DB_PATH = ROOT / "data" / "campus_customs_new.db"  # working copy; the original is never written
AUDIT_PATH = ROOT / "output" / "audit_trail.json"
MCP_SERVER_SCRIPT = ROOT / "mcp_server" / "server.py"
PYTHON = sys.executable

# Every agent runs on Opus 5.5 through the Claude Code subscription (`claude -p`), no API key.
MODEL = "claude-opus-5-5"

# ---- token / cost limits -------------------------------------------------------------
MAX_TOOL_CALLS_PER_TURN = 4          # parallel calls the model may batch in one turn
MAX_TOOL_RESULT_CHARS = 6_000        # each tool result is truncated before it goes back to the model
MAX_REASONING_WORDS = 60             # per-turn rationale the model writes (kept for the audit trail)
MODEL_CALL_TIMEOUT_S = 240
MODEL_CALL_ATTEMPTS = 2

MAX_DELEGATION_DEPTH = 2             # boss -> specialist -> specialist, no deeper
MAX_DELEGATIONS_PER_TICKET = 10      # across the whole team, per ticket run
MAX_MODEL_REQUESTS_PER_TICKET = 45   # across every non-boss agent, per ticket run
