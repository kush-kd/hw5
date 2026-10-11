"""What every agent on the team is made of: a prompt file, an MCP tool allowlist, an output type, and limits."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from config import PROMPTS_DIR
from models import AgentName


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    title: str
    prompt_file: str
    mcp_tools: tuple[str, ...]      # least privilege: the only MCP tools this agent can see
    output_type: type[BaseModel]
    request_limit: int              # max model turns in one run of this agent
    tool_calls_limit: int           # max tool calls in one run of this agent

    def instructions(self) -> str:
        return (PROMPTS_DIR / self.prompt_file).read_text()
