from __future__ import annotations

"""Agent-owned tool subsystem.

This file is the *single* entrypoint for tool contracts, registry, and toolset
composition.

Design constraints:
- Concrete tool implementations live under `tools/`.
- Tools may import contracts from this module.
- To avoid circular imports, this module must not import concrete tools at the
  top level.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from agent.settings import LensDesignParams


ToolHandler = Callable[..., "ToolResult"]
ProgressCallback = Callable[[str], None]
ArtifactCallback = Callable[[str], None]


@dataclass
class ToolResult:
    ok: bool
    message: str = ""
    data: Any = None


@dataclass
class ToolContext:
    project_root: Path
    progress_cb: ProgressCallback | None = None
    artifact_cb: ArtifactCallback | None = None
    agent_name: str = ""
    system_prompt: str = ""
    agent_context: dict[str, Any] = field(default_factory=dict)

    def emit(self, message: str) -> None:
        if self.progress_cb:
            self.progress_cb(message)

    def publish_artifact(self, path: str | Path | None) -> None:
        if path and self.artifact_cb:
            self.artifact_cb(str(path))


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(Protocol):
    name: str
    description: str
    category: str
    metadata: dict[str, Any]

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        ...


class ToolRegistry:
    """Registry for algorithm and general tools used by workflow nodes."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: ToolHandler,
        *,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not name:
            raise ValueError("Tool name cannot be empty.")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            handler=handler,
            category=category,
            metadata=metadata or {},
        )

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        return self.get(name).handler(**kwargs)

    def register_tool(self, tool: Tool) -> None:
        self.register(
            tool.name,
            tool.description,
            tool.run,
            category=tool.category,
            metadata=tool.metadata,
        )

    def names(self) -> list[str]:
        return sorted(self._tools)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "metadata": tool.metadata,
            }
            for tool in sorted(self._tools.values(), key=lambda item: item.name)
        ]


class LensToolset:
    """Concrete tool instances used by the workflow registry."""

    def __init__(self, default_params: LensDesignParams, project_root: Path | None = None):
        root = project_root or Path.cwd()

        # Local imports to avoid import cycles:
        # tools.* -> agent.tools (contracts) and agent.tools -> tools.* (toolset assembly)
        from tools.analysis import RequirementTool
        from tools.cases import CaseTool
        from tools.deeplens.design import DeepLensDesignTool
        from tools.deeplens.evaluation import DeepLensEvaluationTool
        from tools.system import ListDirTool, ReadFileTool, ShellCommandTool
        from tools.zemax import ZemaxAnalysisTool

        self.requirements = RequirementTool(default_params)
        self.cases = CaseTool(root)
        self.deeplens_design = DeepLensDesignTool()
        self.deeplens_evaluation = DeepLensEvaluationTool()
        self.zemax-analysis = ZemaxAnalysisTool()
        self.system = [ReadFileTool(), ListDirTool(), ShellCommandTool()]

    def register_all(self, registry: ToolRegistry) -> None:
        for tool in (
            *self.system,
            self.requirements,
            self.cases,
            self.deeplens_design,
            self.deeplens_evaluation,
            self.zemax-analysis,
        ):
            registry.register_tool(tool)


__all__ = [
    "ArtifactCallback",
    "LensToolset",
    "ProgressCallback",
    "Tool",
    "ToolContext",
    "ToolHandler",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
]
