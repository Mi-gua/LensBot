from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from agent.memory import AgentMemory, run_memory_update
from agent.prompts import workflow_agent_prompt
from subagents import AnalysisNode, OptimizationRunner, ReportingNode, SeedingNode
from agent.tools import ToolContext, ToolRegistry
from agent.settings import AgentInput, AgentResult
from agent.tools import LensToolset
from runtime.artifacts import refresh_run_manifest
from runtime.result import ResultWorkspace, safe_run_id
from runtime.timeline import TimelineCatalog, TimelineEvent
from runtime.traces import append_agent_event, append_timeline_event, trace_row as _trace_row
from subagents.types import LensDesignParams, SeedCandidate, public_params_dict


ProgressCallback = Callable[[dict[str, Any]], None]
ArtifactCallback = Callable[[str], None]
ReferenceCallback = Callable[[list[dict[str, Any]]], None]

@dataclass
class WorkflowContext:
    request: AgentInput
    memory_snapshot: dict[str, Any]
    params: LensDesignParams | None = None
    references: list[dict[str, Any]] = field(default_factory=list)
    seed_candidates: list[SeedCandidate] = field(default_factory=list)
    design_result: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    accepted: bool = False
    issues: list[str] = field(default_factory=list)
    result: AgentResult | None = None
    failed: bool = False
    failure_summary: str = ""
    runtime_result_dir: str | None = None
    global_trace_written_count: int = 0
    run_id: str = ""

    def fail(self, summary: str) -> None:
        self.failed = True
        self.failure_summary = summary


class WorkflowNode(Protocol):
    name: str

    def run(self, ctx: WorkflowContext, runtime: "LensWorkflow") -> None:
        ...


class LensWorkflow:
    """Workflow backbone for optical design runs."""

    def __init__(
        self,
        *,
        default_params: LensDesignParams,
        project_root: Path,
        memory: AgentMemory,
        tools: LensToolset,
    ) -> None:
        self.default_params = default_params
        self.project_root = project_root
        self.memory = memory
        self.tools = tools
        self.registry = ToolRegistry()
        self.tools.register_all(self.registry)
        self.timeline = TimelineCatalog()
        self.nodes: list[WorkflowNode] = [
            IntakeNode(),
            SeedingNode(),
            OptimizationNode(),
            AnalysisNode(),
            ReportingNode(),
        ]
        self.progress_cb: ProgressCallback | None = None
        self.artifact_cb: ArtifactCallback | None = None
        self.reference_cb: ReferenceCallback | None = None

    def run(
        self,
        request: AgentInput,
        *,
        progress_cb: ProgressCallback | None = None,
        artifact_cb: ArtifactCallback | None = None,
        reference_cb: ReferenceCallback | None = None,
    ) -> AgentResult:
        self.progress_cb = progress_cb
        self.artifact_cb = artifact_cb
        self.reference_cb = reference_cb
        ctx = WorkflowContext(
            request=request,
            memory_snapshot=self.memory.create_snapshot(request),
            run_id=_run_id_for_request(request),
        )
        workspace = ResultWorkspace.start(self.project_root, ctx.run_id)
        ctx.runtime_result_dir = str(workspace.root)
        self.record_workflow_artifact(ctx, "Intake", "request", _request_payload(request))

        for node in self.nodes:
            self.emit_event(ctx, "workflow.node.start", node=node.name, node_label=_node_label(node.name))
            try:
                node.run(ctx, self)
            except Exception as exc:
                failure = self.timeline.event("workflow.node.failed", node=node.name, node_label=_node_label(node.name), error=exc)
                ctx.fail(failure.message)
                self._publish_timeline_event(ctx, failure)
            self.emit_event(ctx, "workflow.node.done", node=node.name, node_label=_node_label(node.name))
            self._archive_workflow_state(ctx, node.name)
            if ctx.failed:
                ReportingNode().run(ctx, self)
                self._archive_workflow_state(ctx, "Reporting")
                break

        if ctx.result is None:
            ctx.result = AgentResult(
                ok=False,
                summary=ctx.failure_summary or "Workflow did not produce a result.",
                references=ctx.references,
                timeline=ctx.timeline,
                memory_snapshot=ctx.memory_snapshot,
            )
        self._archive_workflow_state(ctx, "Result")
        return ctx.result

    def emit_event(self, ctx: WorkflowContext, key: str, **fields: Any) -> None:
        self._publish_timeline_event(ctx, self.timeline.event(key, **fields))

    def _publish_timeline_event(self, ctx: WorkflowContext, event: TimelineEvent) -> None:
        if not event.visible or not event.message:
            return
        payload = event.for_trace()
        ctx.timeline.append(payload)
        ctx.memory_snapshot.setdefault("timeline", []).append(payload)
        self._flush_global_trace(ctx)
        if self.progress_cb:
            self.progress_cb(payload)

    def publish_artifact(self, result_dir: str | None, ctx: WorkflowContext | None = None) -> None:
        normalized_dir = self._normalize_result_dir(result_dir)
        if ctx is not None and normalized_dir:
            self.bind_result_dir(ctx, normalized_dir)
        if normalized_dir:
            refresh_run_manifest(normalized_dir)
        if normalized_dir and self.artifact_cb:
            self.artifact_cb(normalized_dir)

    def bind_result_dir(self, ctx: WorkflowContext, result_dir: str | None) -> None:
        normalized_dir = self._normalize_result_dir(result_dir)
        if not normalized_dir:
            return
        ctx.runtime_result_dir = normalized_dir
        ResultWorkspace.from_result_dir(normalized_dir)
        refresh_run_manifest(normalized_dir)
        self._flush_global_trace(ctx)

    def record_agent_turn(self, ctx: WorkflowContext, row: Any, result_dir: str | None = None) -> None:
        normalized_dir = self._normalize_result_dir(result_dir) or ctx.runtime_result_dir
        if not normalized_dir:
            return
        ctx.runtime_result_dir = normalized_dir
        append_agent_event(normalized_dir, row)
        if isinstance(row, dict) and row.get("agent") == "Optimization":
            ResultWorkspace.from_result_dir(normalized_dir).record_optimization_agent_turn(row)
        refresh_run_manifest(normalized_dir)

    def record_agent_trace(self, ctx: WorkflowContext, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.record_agent_turn(ctx, row)

    def record_workflow_artifact(self, ctx: WorkflowContext, node: str, name: str, payload: Any) -> None:
        result_dir = ctx.runtime_result_dir or self._normalize_result_dir(ctx.design_result.get("result_dir"))
        if not result_dir:
            return
        ResultWorkspace.from_result_dir(result_dir).write_workflow_artifact(node, name, payload)
        refresh_run_manifest(result_dir)

    def publish_references(self, references: list[dict[str, Any]]) -> None:
        if self.reference_cb:
            self.reference_cb(references)

    def tool_context(
        self,
        ctx: WorkflowContext,
        *,
        agent_name: str = "",
        system_prompt: str = "",
        agent_context: dict[str, Any] | None = None,
    ) -> ToolContext:
        return ToolContext(
            project_root=self.project_root,
            progress_cb=None,
            artifact_cb=self.artifact_cb,
            agent_name=agent_name,
            system_prompt=system_prompt,
            agent_context=agent_context or {},
        )

    def _flush_global_trace(self, ctx: WorkflowContext) -> None:
        result_dir = ctx.runtime_result_dir or self._normalize_result_dir(ctx.design_result.get("result_dir"))
        if not result_dir:
            return
        ctx.runtime_result_dir = result_dir
        for index, event in enumerate(ctx.timeline[ctx.global_trace_written_count:], start=ctx.global_trace_written_count):
            append_timeline_event(result_dir, event, index=index)
        ctx.global_trace_written_count = len(ctx.timeline)
        ResultWorkspace.from_result_dir(result_dir).write_timeline(ctx.timeline)

    def _archive_workflow_state(self, ctx: WorkflowContext, node: str) -> None:
        self.record_workflow_artifact(ctx, node, "state", _workflow_state_payload(ctx, node))
        self._archive_named_workflow_artifacts(ctx, node)

    def _archive_named_workflow_artifacts(self, ctx: WorkflowContext, node: str) -> None:
        if node == "Intake":
            self.record_workflow_artifact(ctx, node, "params", public_params_dict(ctx.params))
        if node == "Seeding":
            candidates = _seed_candidates_payload(ctx)
            self.record_workflow_artifact(ctx, node, "seed_candidates", candidates)
            self.record_workflow_artifact(ctx, node, "selected_seed", _selected_seed_payload(ctx))
        if node == "Optimization" and ctx.design_result:
            self.record_workflow_artifact(
                ctx,
                node,
                "optimization_result",
                {"design_result": ctx.design_result, "metrics": ctx.metrics},
            )
        if node == "Analysis":
            self.record_workflow_artifact(
                ctx,
                node,
                "acceptance",
                {"accepted": ctx.accepted, "issues": ctx.issues, "metrics": ctx.metrics.get("acceptance")},
            )
        if node in {"Reporting", "Result"} and ctx.result is not None:
            self.record_workflow_artifact(ctx, "Reporting", "agent_result", ctx.result)

    def _normalize_result_dir(self, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(str(value))
        if not path.is_absolute():
            path = self.project_root / path
        try:
            path = path.resolve()
        except OSError:
            return None

        results_root = (self.project_root / "results").resolve()
        try:
            relative = path.relative_to(results_root)
        except ValueError:
            return str(path) if path.is_dir() else None

        first_part = relative.parts[0] if relative.parts else ""
        if not first_part:
            return str(path)
        return str((results_root / first_part).resolve())

    def tool_names(self, *names: str) -> list[str]:
        known = set(self.registry.names())
        return [name for name in names if name in known]


class LensResearchAgent:
    """Compatibility facade around the LensBot workflow runtime."""

    def __init__(self, default_params: LensDesignParams, project_root: Path):
        self.default_params = default_params
        self.project_root = project_root
        self.memory = AgentMemory(project_root / "src" / "memory")
        self.tools = LensToolset(default_params, project_root=project_root)
        self.workflow = LensWorkflow(
            default_params=default_params,
            project_root=project_root,
            memory=self.memory,
            tools=self.tools,
        )

    def run(
        self,
        request: AgentInput,
        progress_cb: ProgressCallback | None = None,
        artifact_cb: Callable[[str], None] | None = None,
        reference_cb: ReferenceCallback | None = None,
    ) -> AgentResult:
        return self.workflow.run(
            request,
            progress_cb=progress_cb,
            artifact_cb=artifact_cb,
            reference_cb=reference_cb,
        )


class IntakeNode:
    name = "Intake"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        available_tools = runtime.tool_names("parse_requirements")
        objective = "将用户意图解析为光学设计上下文"
        system_prompt = workflow_agent_prompt(
            self.name,
            objective=objective,
            available_tools=available_tools,
            context={
                "agent": self.name,
                "objective": objective,
                "current_task": ctx.memory_snapshot.get("current_task"),
            },
        )

        trace: list[dict[str, Any]] = []
        if ctx.params is None:
            result = runtime.registry.call(
                "parse_requirements",
                ctx=runtime.tool_context(ctx, agent_name=self.name, system_prompt=system_prompt),
                request=ctx.request,
            )
            if not result.ok:
                ctx.fail(result.message)
                trace.append(
                    _trace_row(
                        agent=self.name,
                        turn=0,
                        thought="Parse user requirements into explicit optical targets.",
                        action="parse_requirements",
                        action_input={"mode": ctx.request.mode, "prompt": ctx.request.prompt},
                        observation=result.message,
                        data=result.for_trace(),
                        done=True,
                    )
                )
            else:
                ctx.params = result.data
                runtime.memory.refresh_task_context(ctx.memory_snapshot, ctx.request, ctx.params)
                trace.append(
                    _trace_row(
                        agent=self.name,
                        turn=0,
                        thought="User requirements were converted into structured lens parameters.",
                        action="parse_requirements",
                        action_input={"mode": ctx.request.mode, "prompt": ctx.request.prompt},
                        observation=result.message,
                        data=result.for_trace(),
                    )
                )

        if ctx.params is not None:
            message = "Budget: curriculum={curriculum}, fine_tune={fine_tune}".format(
                curriculum=ctx.params.curriculum.iterations,
                fine_tune=ctx.params.fine_tune.iterations,
            )
            trace.append(
                _trace_row(
                    agent=self.name,
                    turn=len(trace),
                    thought="Confirm the optimization budget before moving downstream.",
                    action="confirm_budget",
                    action_input={},
                    observation=message,
                    done=True,
                )
            )
        ctx.agent_trace.extend(trace)
        runtime.record_agent_trace(ctx, trace)


class OptimizationNode:
    name = "Optimization"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        OptimizationRunner().run(ctx, runtime)
        _record_optimization_memory(ctx, runtime)


def _record_optimization_memory(ctx: WorkflowContext, runtime: LensWorkflow) -> None:
    def update() -> None:
        runtime.memory.record_optimization_lessons(
            request=ctx.request,
            params=ctx.params,
            seed_candidates=ctx.seed_candidates,
            design_result=ctx.design_result,
            metrics=ctx.metrics,
            agent_trace=ctx.agent_trace,
        )
        ctx.memory_snapshot["optimization_lessons"] = runtime.memory.load_markdown_lessons("optimization")

    _run_memory_update(runtime, ctx, label="optimization lessons", update=update)


def _run_memory_update(
    runtime: Any,
    ctx: Any,
    *,
    label: str,
    update: Callable[[], None],
) -> bool:
    return run_memory_update(
        runtime,
        ctx,
        label=label,
        update=update,
    )


def _node_label(name: str) -> str:
    labels = {
        "Intake": "需求解析",
        "Seeding": "初始结构选择",
        "Optimization": "优化与基础评估",
        "Analysis": "性能分析",
        "Reporting": "报告归档",
    }
    return labels.get(name, name)


def _run_id_for_request(request: AgentInput) -> str:
    params = request.params
    name = getattr(params, "exp_name", None) or "lensbot-run"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return safe_run_id(f"{name}-{stamp}")


def _request_payload(request: AgentInput) -> dict[str, Any]:
    return {
        "mode": request.mode,
        "prompt": request.prompt,
        "params": public_params_dict(request.params),
    }


def _workflow_state_payload(ctx: WorkflowContext, node: str) -> dict[str, Any]:
    return _jsonable(
        {
            "run_id": ctx.run_id,
            "node": node,
            "params": public_params_dict(ctx.params),
            "references": ctx.references,
            "seed_candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "case_id": item.case_id,
                    "title": item.title,
                    "category": item.category,
                    "path": item.path,
                    "applied": item.applied,
                    "inspected": item.inspected,
                    "params": public_params_dict(item.params),
                }
                for item in ctx.seed_candidates
            ],
            "design_result": ctx.design_result,
            "metrics": ctx.metrics,
            "accepted": ctx.accepted,
            "issues": ctx.issues,
            "failed": ctx.failed,
            "failure_summary": ctx.failure_summary,
            "result": ctx.result,
            "timeline": ctx.timeline,
        }
    )


def _seed_candidates_payload(ctx: WorkflowContext) -> list[dict[str, Any]]:
    return [_seed_candidate_artifact(item) for item in ctx.seed_candidates]


def _selected_seed_payload(ctx: WorkflowContext) -> dict[str, Any] | None:
    for item in ctx.seed_candidates:
        if item.applied or item.inspected:
            return _seed_candidate_artifact(item)
    return None


def _seed_candidate_artifact(item: SeedCandidate) -> dict[str, Any]:
    return {
        "candidate_id": item.candidate_id,
        "case_id": item.case_id,
        "title": item.title,
        "category": item.category,
        "path": item.path,
        "reasons": item.reasons,
        "risks": item.risks,
        "applied": item.applied,
        "inspected": item.inspected,
        "params": public_params_dict(item.params),
    }


def _jsonable(value: Any) -> Any:
    import json

    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
