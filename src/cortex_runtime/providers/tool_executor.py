"""Shared tool execution helper for providers.

Bridges PluginRegistry actions to OpenAI/Anthropic tool-calling formats,
enabling providers to execute plugin tools without a full MCP bridge.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cortex_runtime.plugins.models import ActionTier

if TYPE_CHECKING:
    from cortex_runtime.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_TURNS = 10
"""Maximum tool-calling loop iterations before forcing a text response."""

TOOL_NAME_SEP = "__"
"""Separator between plugin and action names in tool identifiers."""

# Tiers excluded from provider tool exposure — APPROVE needs a separate flow
_EXCLUDED_TIERS: frozenset[ActionTier] = frozenset({ActionTier.APPROVE})


@dataclass(frozen=True)
class ToolCall:
    """Normalized tool call from a model response."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """Result of executing a tool call."""

    tool_call_id: str
    content: str
    is_error: bool = False


def build_tool_schemas(registry: PluginRegistry) -> list[dict[str, Any]]:
    """Build OpenAI-compatible tool schemas from all loaded plugins.

    Args:
        registry: The plugin registry to query.

    Returns:
        List of tool schema dicts in OpenAI function-calling format.
    """
    schemas: list[dict[str, Any]] = []

    for info in registry.list_plugins():
        for action in info.actions:
            if action.tier in _EXCLUDED_TIERS:
                continue

            tool_name = f"{info.name}{TOOL_NAME_SEP}{action.name}"
            schema: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": action.description,
                    "parameters": action.parameters or {"type": "object", "properties": {}},
                },
            }
            schemas.append(schema)

    return schemas


async def execute_tool_calls(
    tool_calls: list[ToolCall],
    registry: PluginRegistry,
) -> list[ToolResult]:
    """Execute a list of tool calls via the plugin registry.

    Args:
        tool_calls: List of tool calls from the model response.
        registry: Plugin registry to route calls through.

    Returns:
        List of tool results (one per input call, in the same order).
    """
    results: list[ToolResult] = []

    for call in tool_calls:
        # Parse plugin and action from the tool name
        if TOOL_NAME_SEP not in call.name:
            results.append(
                ToolResult(
                    tool_call_id=call.id,
                    content=f"Invalid tool name format: {call.name!r}. "
                            f"Expected '<plugin>{TOOL_NAME_SEP}<action>'.",
                    is_error=True,
                )
            )
            continue

        plugin_name, action_name = call.name.split(TOOL_NAME_SEP, 1)

        try:
            result = await registry.execute(plugin_name, action_name, call.arguments)

            if result.success:
                content = json.dumps(result.data) if result.data is not None else "OK"
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=content,
                        is_error=False,
                    )
                )
            else:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        content=result.error or "Action failed without error message",
                        is_error=True,
                    )
                )

        except Exception as exc:
            logger.warning(
                "Tool call %s.%s failed: %s",
                plugin_name,
                action_name,
                exc,
            )
            results.append(
                ToolResult(
                    tool_call_id=call.id,
                    content=str(exc),
                    is_error=True,
                )
            )

    return results
