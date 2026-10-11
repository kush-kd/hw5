"""PydanticAI model that runs every agent turn on Opus 5.5 through the Claude Code subscription.

PydanticAI owns the agent loop: it decides when to call the model, executes the tool
calls the model asks for (MCP tools and delegation), feeds results back, and validates
the final output. This module is only the "model" in that loop. Each turn it:

1. renders the agent's instructions + the tools it may use into a system prompt,
2. renders the conversation so far (task, earlier tool calls, tool results) as text,
3. calls `claude -p --model claude-opus-5-5` with all of Claude Code's own tools disabled
   and a JSON schema that forces the reply to be {reasoning, tool_calls[]},
4. turns that reply into PydanticAI ToolCallParts.

Auth is the Claude Code subscription: ANTHROPIC_API_KEY and friends are removed from the
child environment so the call can never fall back to metered API billing.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from config import (
    MAX_REASONING_WORDS,
    MAX_TOOL_CALLS_PER_TURN,
    MAX_TOOL_RESULT_CHARS,
    MODEL,
    MODEL_CALL_ATTEMPTS,
    MODEL_CALL_TIMEOUT_S,
    ROOT,
)


class ClaudeCallError(RuntimeError):
    pass


PROTOCOL = """\
# How you act in this system

You are one turn inside an agent loop. Each turn you reply ONLY with JSON:
  {{"reasoning": "...", "tool_calls": [{{"name": "...", "args": {{...}}}}, ...]}}

- `reasoning`: at most {words} words on why you are making these calls. It is saved to the audit trail.
- `tool_calls`: 1 to {max_calls} calls. Calls in the same turn run in parallel, so only batch
  calls that do not depend on each other's results. The results come back to you next turn.
- `args` must match the tool's parameter JSON Schema exactly.
- To finish, call `{final}` with your complete answer as its args. It must be the ONLY call
  in that turn. Finish as soon as you have what you need.
- Never invent a tool result, number, date, or id. If you have not seen it in a tool result,
  you do not know it.
"""


def _tool_catalogue(info: AgentInfo) -> str:
    lines = ["# Tools you can call"]
    for tool in [*info.function_tools, *info.output_tools]:
        lines.append(f"\n## {tool.name}\n{(tool.description or '').strip()}")
        lines.append("Parameters (JSON Schema): " + json.dumps(tool.parameters_json_schema, separators=(",", ":")))
    return "\n".join(lines)


def _truncate(text: str) -> str:
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + f"... [truncated {len(text) - MAX_TOOL_RESULT_CHARS} chars]"


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, default=str, separators=(",", ":"))
    except TypeError:
        return str(content)


def render_transcript(messages: list[ModelMessage]) -> str:
    """The conversation so far as plain text, oldest first."""
    out: list[str] = ["# Conversation so far"]
    turn = 0
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    out.append(f"\n[TASK]\n{_content_text(part.content)}")
                elif isinstance(part, ToolReturnPart):
                    out.append(f"\n[TOOL RESULT {part.tool_name} id={part.tool_call_id}]\n{_truncate(_content_text(part.content))}")
                elif isinstance(part, RetryPromptPart):
                    where = f" for {part.tool_name} id={part.tool_call_id}" if part.tool_name else ""
                    out.append(f"\n[ERROR{where} - fix it and try again]\n{_truncate(_content_text(part.content))}")
        elif isinstance(msg, ModelResponse):
            turn += 1
            reasoning = (msg.provider_details or {}).get("reasoning", "")
            calls = [
                f"  - {p.tool_name}({_content_text(p.args)}) id={p.tool_call_id}"
                for p in msg.parts
                if isinstance(p, ToolCallPart)
            ]
            out.append(f"\n[YOUR TURN {turn}] reasoning: {reasoning}\n" + "\n".join(calls))
    out.append("\nTake your next turn now.")
    return "\n".join(out)


def _response_schema(info: AgentInfo) -> dict:
    names = [t.name for t in [*info.function_tools, *info.output_tools]]
    return {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_TOOL_CALLS_PER_TURN,
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "enum": names}, "args": {"type": "object"}},
                    "required": ["name", "args"],
                },
            },
        },
        "required": ["reasoning", "tool_calls"],
    }


# Only these variables reach the `claude` child process. Inheriting the launcher's whole
# environment (IDE/desktop/session variables, API keys, proxies) made some calls pull in a second
# background model; a minimal environment keeps every call on MODEL and on the subscription.
_ENV_ALLOWLIST = ("HOME", "PATH", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG", "LC_ALL")


def _child_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}


async def _claude(system: str, prompt: str, schema: dict) -> dict:
    cli = shutil.which("claude")
    if not cli:
        raise ClaudeCallError("The `claude` CLI is not on PATH; install Claude Code and log in with your subscription.")
    cmd = [
        cli, "-p",
        "--model", MODEL,
        "--system-prompt", system,
        "--tools", "",                 # no Claude Code built-in tools: the model can only answer
        "--strict-mcp-config",         # and no MCP servers of its own; tools run in PydanticAI
        "--disable-slash-commands",
        "--no-session-persistence",
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
    ]
    last: Exception | None = None
    for attempt in range(1, MODEL_CALL_ATTEMPTS + 1):
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=ROOT, env=_child_env(),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(prompt.encode()), MODEL_CALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            last = ClaudeCallError(f"claude -p timed out after {MODEL_CALL_TIMEOUT_S}s")
            continue
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            last = ClaudeCallError(f"claude -p exit {proc.returncode}: {(stdout + stderr).decode()[:600]}")
            continue
        if envelope.get("is_error") or not envelope.get("structured_output"):
            last = ClaudeCallError(f"claude -p error: {str(envelope.get('result'))[:600]}")
            continue
        return envelope
    raise last or ClaudeCallError("claude -p failed")


async def _turn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    final_name = info.output_tools[0].name if info.output_tools else "final_result"
    system = "\n\n".join(
        [
            (info.instructions or "").strip(),
            PROTOCOL.format(words=MAX_REASONING_WORDS, max_calls=MAX_TOOL_CALLS_PER_TURN, final=final_name),
            _tool_catalogue(info),
        ]
    )
    started = time.monotonic()
    envelope = await _claude(system, render_transcript(messages), _response_schema(info))
    out = envelope["structured_output"]

    parts: list = [
        ToolCallPart(tool_name=c["name"], args=c.get("args") or {}, tool_call_id=f"call_{uuid.uuid4().hex[:12]}")
        for c in out.get("tool_calls", [])[:MAX_TOOL_CALLS_PER_TURN]
    ]
    if not parts:
        parts = [TextPart(content=out.get("reasoning", ""))]

    u = envelope.get("usage") or {}
    usage = RequestUsage(
        input_tokens=int(u.get("input_tokens", 0)) + int(u.get("cache_creation_input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)),
        cache_write_tokens=int(u.get("cache_creation_input_tokens", 0)),
        cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
    )
    return ModelResponse(
        parts=parts,
        usage=usage,
        model_name=MODEL,
        provider_name="claude-code-subscription",
        provider_details={
            "reasoning": out.get("reasoning", ""),
            "latency_s": round(time.monotonic() - started, 2),
            "notional_cost_usd": envelope.get("total_cost_usd"),
            "models_used": list((envelope.get("modelUsage") or {}).keys()),
        },
    )


def subscription_model() -> FunctionModel:
    """The one model every agent on the team uses."""
    return FunctionModel(_turn, model_name=MODEL)
