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
    "ReactAgentLoop",
    "ReactState",
    "ReactTurn",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
]


def __getattr__(name: str) -> Any:
    if name == "build_agent_input":
        from agent.settings import build_agent_input

        return build_agent_input
    if name in {"ReactAgentLoop", "ReactState", "ReactTurn"}:
        from agent import loop

        return getattr(loop, name)
    if name in {"LensResearchAgent", "LensWorkflow"}:
        from agent import workflow

        return getattr(workflow, name)
    if name in {"LensToolset", "ToolContext", "ToolRegistry", "ToolResult"}:
        from agent import tools

        return getattr(tools, name)
    raise AttributeError(name)
