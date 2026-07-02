from __future__ import annotations

"""Standard tool substrate for agentic workflows.

This module is intentionally domain-light. A tool is a small, registered
capability with a stable schema, a trace-friendly result, and no hidden control
flow. Agent runtimes should be able to print a `ToolCall` and a `ToolResult`
directly into their traces.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Protocol


JsonObject = dict[str, Any]
ToolHandler = Callable[..., "ToolResult"]
ProgressCallback = Callable[[str], None]
ArtifactCallback = Callable[[str], None]


class ToolScope(StrEnum):
    INTAKE = "intake"
    SEED_DESIGN = "seed_design"
    OPTIMIZATION = "optimization"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    DEBUG = "debug"
    WORKFLOW = "workflow"


class ToolCategory(StrEnum):
    CONTROL = "control"
    GENERAL = "general"
    ALGORITHM = "algorithm"
    FILESYSTEM = "filesystem"
    PROCESS = "process"
    MEMORY = "memory"


@dataclass(frozen=True)
class ToolSchema:
    input: JsonObject = field(default_factory=lambda: {"type": "object", "properties": {}})
    output: JsonObject = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    category: str = ToolCategory.GENERAL
    scope: str = ToolScope.WORKFLOW
    schema: ToolSchema = field(default_factory=ToolSchema)
    metadata: JsonObject = field(default_factory=dict)

    def for_prompt(self) -> JsonObject:
        return {
            "name": self.name,
            "description": self.description,
            "category": str(self.category),
            "scope": str(self.scope),
            "input_schema": self.schema.input,
            "output_schema": self.schema.output,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: JsonObject = field(default_factory=dict)
    call_id: str | None = None

    def for_trace(self) -> JsonObject:
        payload = {"name": self.name, "arguments": self.arguments}
        if self.call_id:
            payload["call_id"] = self.call_id
        return payload


@dataclass(frozen=True)
class ToolArtifact:
    path: str
    kind: str = "file"
    label: str = ""
    source: str = ""
    role: str = ""
    stage: str = ""
    preview: bool = True
    order: int = 100
    metadata: JsonObject = field(default_factory=dict)

    def for_trace(self) -> JsonObject:
        return {
            "path": self.path,
            "kind": self.kind,
            "label": self.label,
            "source": self.source,
            "role": self.role,
            "stage": self.stage,
            "preview": self.preview,
            "order": self.order,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str
    recoverable: bool = True
    details: JsonObject = field(default_factory=dict)

    def for_trace(self) -> JsonObject:
        return {
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "details": self.details,
        }


@dataclass
class ToolResult:
    """Trace-ready result produced by every tool."""

    ok: bool
    observation: str
    data: Any = None
    state_patch: JsonObject = field(default_factory=dict)
    metrics: JsonObject = field(default_factory=dict)
    artifacts: list[ToolArtifact] = field(default_factory=list)
    error: ToolError | None = None
    metadata: JsonObject = field(default_factory=dict)

    @property
    def message(self) -> str:
        return self.observation

    @message.setter
    def message(self, value: str) -> None:
        self.observation = value

    @classmethod
    def success(
        cls,
        observation: str,
        data: Any = None,
        *,
        state_patch: JsonObject | None = None,
        metrics: JsonObject | None = None,
        artifacts: Iterable[str | Path | ToolArtifact] = (),
        metadata: JsonObject | None = None,
    ) -> "ToolResult":
        return cls(
            ok=True,
            observation=observation,
            data=data,
            state_patch=state_patch or {},
            metrics=metrics or {},
            artifacts=_normalize_artifacts(artifacts),
            metadata=metadata or {},
        )

    @classmethod
    def failure(
        cls,
        observation: str,
        *,
        code: str = "tool_error",
        data: Any = None,
        state_patch: JsonObject | None = None,
        metrics: JsonObject | None = None,
        error: ToolError | JsonObject | None = None,
        artifacts: Iterable[str | Path | ToolArtifact] = (),
        metadata: JsonObject | None = None,
        recoverable: bool = True,
    ) -> "ToolResult":
        return cls(
            ok=False,
            observation=observation,
            data=data,
            state_patch=state_patch or {},
            metrics=metrics or {},
            artifacts=_normalize_artifacts(artifacts),
            error=_normalize_error(error, fallback_code=code, fallback_message=observation, recoverable=recoverable),
            metadata=metadata or {},
        )

    def for_trace(self) -> JsonObject:
        payload = {
            "ok": self.ok,
            "observation": self.observation,
            "data": {} if self.data is None else self.data,
            "state_patch": self.state_patch,
            "metrics": self.metrics,
            "artifacts": [artifact.for_trace() for artifact in self.artifacts],
            "error": self.error.for_trace() if self.error else None,
            "metadata": self.metadata,
        }
        return payload

    def to_trace(self) -> JsonObject:
        return self.for_trace()


@dataclass
class ToolContext:
    project_root: Path
    progress_cb: ProgressCallback | None = None
    artifact_cb: ArtifactCallback | None = None
    agent_name: str = ""
    system_prompt: str = ""
    agent_context: JsonObject = field(default_factory=dict)

    def emit(self, message: str) -> None:
        if self.progress_cb:
            self.progress_cb(message)

    def publish_artifact(self, artifact: str | Path | ToolArtifact | None) -> None:
        if artifact is None or self.artifact_cb is None:
            return
        if isinstance(artifact, ToolArtifact):
            self.artifact_cb(artifact.path)
        else:
            self.artifact_cb(str(artifact))


class Tool(Protocol):
    name: str
    description: str
    category: str
    scope: str
    input_schema: JsonObject
    output_schema: JsonObject
    metadata: JsonObject

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        ...


@dataclass(frozen=True)
class ToolSpec:
    """Registered tool plus executable handler."""

    definition: ToolDefinition
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.definition.name

    def for_prompt(self) -> JsonObject:
        return self.definition.for_prompt()


class ToolRegistry:
    """Single registry for tool definitions and dispatch."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        handler: ToolHandler,
        *,
        category: str = ToolCategory.GENERAL,
        scope: str = ToolScope.WORKFLOW,
        input_schema: JsonObject | None = None,
        output_schema: JsonObject | None = None,
        metadata: JsonObject | None = None,
        replace: bool = False,
    ) -> ToolDefinition:
        if not name:
            raise ValueError("Tool name cannot be empty.")
        if name in self._tools and not replace:
            raise ValueError(f"Tool already registered: {name}")
        definition = ToolDefinition(
            name=name,
            description=description,
            category=category,
            scope=scope,
            schema=ToolSchema(input=input_schema or {}, output=output_schema or {}),
            metadata=metadata or {},
        )
        self._tools[name] = ToolSpec(definition=definition, handler=handler)
        return definition

    def register_tool(self, tool: Tool, *, replace: bool = False) -> ToolDefinition:
        return self.register(
            name=tool.name,
            description=tool.description,
            handler=tool.run,
            category=getattr(tool, "category", ToolCategory.GENERAL),
            scope=getattr(tool, "scope", ToolScope.WORKFLOW),
            input_schema=getattr(tool, "input_schema", {}),
            output_schema=getattr(tool, "output_schema", {}),
            metadata=getattr(tool, "metadata", {}),
            replace=replace,
        )

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def names(self, *, scope: str | None = None, category: str | None = None) -> list[str]:
        return [tool.name for tool in self.find(scope=scope, category=category)]

    def find(self, *, scope: str | None = None, category: str | None = None) -> list[ToolSpec]:
        tools = list(self._tools.values())
        if scope is not None:
            tools = [tool for tool in tools if str(tool.definition.scope) == str(scope)]
        if category is not None:
            tools = [tool for tool in tools if str(tool.definition.category) == str(category)]
        return sorted(tools, key=lambda tool: tool.name)

    def describe(self, names: Iterable[str] | None = None) -> list[JsonObject]:
        allowed = set(names) if names is not None else None
        return [
            spec.for_prompt()
            for spec in self.find()
            if allowed is None or spec.name in allowed
        ]

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        spec = self.get(name)
        started = perf_counter()
        try:
            result = spec.handler(**kwargs)
        except Exception as exc:
            result = ToolResult.failure(
                f"{name} raised {type(exc).__name__}: {exc}",
                code="tool_exception",
                error=ToolError(
                    code="tool_exception",
                    message=str(exc),
                    details={"tool": name, "exception_type": type(exc).__name__},
                ),
            )
        result = self._coerce_result(spec, result)
        result.metadata.setdefault("tool", name)
        result.metadata.setdefault("scope", str(spec.definition.scope))
        result.metadata.setdefault("category", str(spec.definition.category))
        result.metadata.setdefault("elapsed_ms", round((perf_counter() - started) * 1000.0, 3))
        return result

    @staticmethod
    def _coerce_result(spec: ToolSpec, result: Any) -> ToolResult:
        if isinstance(result, ToolResult):
            return result
        return ToolResult.success(f"{spec.name} completed.", result)


class LensToolset:
    """Project-local tool composition.

    This stays at the edge of the substrate. Concrete tools can be replaced or
    removed without changing the registry or agent runtime contracts.
    """

    def __init__(self, default_params: Any, project_root: Path | None = None):
        root = project_root or Path.cwd()

        from tools.bash import PowerShellTool
        from tools.seed_case import ReadSeedCasesTool, RetrieveSeedCasesTool
        from tools.deeplens import DEEPLENS_TOOLS
        from tools.edit_file import EditFileTool
        from tools.read_file import ReadFileTool
        from tools.intake import RequirementTool
        from tools.write_file import WriteFileTool
        from tools.analysis import ZemaxAnalysisTool

        self.requirements = RequirementTool(default_params)
        self.seed_case_retrieval = RetrieveSeedCasesTool(root)
        self.seed_case_batch_reader = ReadSeedCasesTool(root)
        self.deeplens = DEEPLENS_TOOLS
        self.zemax_analysis = ZemaxAnalysisTool()
        self.basic = [ReadFileTool(), WriteFileTool(), EditFileTool(), PowerShellTool()]

    def all_tools(self) -> list[Tool]:
        return [
            *self.basic,
            self.requirements,
            self.seed_case_retrieval,
            self.seed_case_batch_reader,
            *self.deeplens,
            self.zemax_analysis,
        ]

    def register_all(self, registry: ToolRegistry) -> None:
        for tool in self.all_tools():
            registry.register_tool(tool)


def _normalize_artifacts(items: Iterable[str | Path | ToolArtifact]) -> list[ToolArtifact]:
    artifacts: list[ToolArtifact] = []
    for item in items:
        if isinstance(item, ToolArtifact):
            artifacts.append(item)
        else:
            artifacts.append(ToolArtifact(path=str(item)))
    return artifacts


def _normalize_error(
    error: ToolError | JsonObject | None,
    *,
    fallback_code: str,
    fallback_message: str,
    recoverable: bool,
) -> ToolError:
    if isinstance(error, ToolError):
        return error
    if isinstance(error, dict):
        return ToolError(
            code=str(error.get("code") or fallback_code),
            message=str(error.get("message") or fallback_message),
            recoverable=bool(error.get("recoverable", recoverable)),
            details={key: value for key, value in error.items() if key not in {"code", "message", "recoverable"}},
        )
    return ToolError(code=fallback_code, message=fallback_message, recoverable=recoverable)


__all__ = [
    "ArtifactCallback",
    "JsonObject",
    "LensToolset",
    "ProgressCallback",
    "Tool",
    "ToolArtifact",
    "ToolCall",
    "ToolCategory",
    "ToolContext",
    "ToolDefinition",
    "ToolError",
    "ToolHandler",
    "ToolRegistry",
    "ToolResult",
    "ToolSchema",
    "ToolScope",
    "ToolSpec",
]
