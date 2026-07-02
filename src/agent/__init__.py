"""Agent runtime package.

Keep this module import-light.

Concrete tools import tool contracts from `agent.tools`; if this package eagerly
imports workflow/UI modules, it can easily create circular imports.
"""

from __future__ import annotations

from typing import Any


__all__ = [
    "build_agent_input",
    "LensResearchAgent",
    "LensWorkflow",
    "LensToolset",
    "ToolCall",
    "ToolContext",
    "ToolDefinition",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "ToolSchema",
]


def __getattr__(name: str) -> Any:
    if name == "build_agent_input":
        from subagents.types import build_agent_input

        return build_agent_input
    if name in {"LensResearchAgent", "LensWorkflow"}:
        from agent import workflow

        return getattr(workflow, name)
    if name in {
        "LensToolset",
        "ToolCall",
        "ToolContext",
        "ToolDefinition",
        "ToolError",
        "ToolRegistry",
        "ToolResult",
        "ToolSchema",
    }:
        from agent import tools

        return getattr(tools, name)
    raise AttributeError(name)
