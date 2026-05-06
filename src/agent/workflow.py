from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from agent.memory import AgentMemory
from agent.loop import ReactAgentLoop, ReactState, ReactTurn
from agent.prompts import workflow_agent_context, workflow_agent_prompt
from agent.tools import ToolContext, ToolRegistry
from agent.settings import AgentInput, AgentResult, LensDesignParams
from agent.tools import LensToolset


ProgressCallback = Callable[[str], None]
ArtifactCallback = Callable[[str], None]


@dataclass
class WorkflowContext:
    request: AgentInput
    memory_snapshot: dict[str, Any]
    params: LensDesignParams | None = None
    references: list[dict[str, Any]] = field(default_factory=list)
    design_result: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    timeline: list[str] = field(default_factory=list)
    agent_trace: list[dict[str, Any]] = field(default_factory=list)
    accepted: bool = False
    issues: list[str] = field(default_factory=list)
    result: AgentResult | None = None
    failed: bool = False
    failure_summary: str = ""

    def fail(self, summary: str) -> None:
        self.failed = True
        self.failure_summary = summary


class WorkflowNode(Protocol):
    name: str

    def run(self, ctx: WorkflowContext, runtime: "LensWorkflow") -> None:
        ...


class LensWorkflow:
    """Workflow backbone with node-level agent loops for optical design runs."""

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
        self.nodes: list[WorkflowNode] = [
            IntakeNode(),
            SeedDesignAgentNode(),
            OptimizationAgentNode(),
            AnalysisAgentNode(),
            ReportMemoryNode(),
        ]
        self.progress_cb: ProgressCallback | None = None
        self.artifact_cb: ArtifactCallback | None = None

    def run(
        self,
        request: AgentInput,
        *,
        progress_cb: ProgressCallback | None = None,
        artifact_cb: ArtifactCallback | None = None,
    ) -> AgentResult:
        self.progress_cb = progress_cb
        self.artifact_cb = artifact_cb
        ctx = WorkflowContext(request=request, memory_snapshot=self.memory.create_snapshot(request))

        for node in self.nodes:
            self.emit(ctx, f"{_node_label(node.name)}开始。")
            try:
                node.run(ctx, self)
            except Exception as exc:
                ctx.fail(f"{_node_label(node.name)}失败：{exc}")
            self.emit(ctx, f"{_node_label(node.name)}完成。")
            if ctx.failed:
                ReportMemoryNode().run(ctx, self)
                break

        if ctx.result is None:
            ctx.result = AgentResult(
                ok=False,
                summary=ctx.failure_summary or "Workflow did not produce a result.",
                references=ctx.references,
                timeline=ctx.timeline,
                memory_snapshot=ctx.memory_snapshot,
            )
        return ctx.result

    def emit(self, ctx: WorkflowContext, message: str) -> None:
        ctx.timeline.append(message)
        ctx.memory_snapshot.setdefault("timeline", []).append(message)
        if self.progress_cb:
            self.progress_cb(message)

    def publish_artifact(self, result_dir: str | None) -> None:
        if result_dir and self.artifact_cb:
            self.artifact_cb(result_dir)

    def tool_context(self, ctx: WorkflowContext, state: ReactState | None = None) -> ToolContext:
        return ToolContext(
            project_root=self.project_root,
            progress_cb=lambda message: self.emit(ctx, message),
            artifact_cb=self.artifact_cb,
            agent_name=str((state.context or {}).get("agent", "")) if state else "",
            system_prompt=state.system_prompt if state else "",
            agent_context=state.context if state else {},
        )

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
        progress_cb: Callable[[str], None] | None = None,
        artifact_cb: Callable[[str], None] | None = None,
    ) -> AgentResult:
        return self.workflow.run(
            request,
            progress_cb=progress_cb,
            artifact_cb=artifact_cb,
        )


class IntakeNode:
    name = "intake_agent"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        loop = ReactAgentLoop("IntakeAgent", max_turns=2)
        available_tools = runtime.tool_names("parse_requirements")

        def step(state: ReactState) -> ReactTurn:
            if ctx.params is None:
                result = runtime.registry.call(
                    "parse_requirements",
                    ctx=runtime.tool_context(ctx, state),
                    request=ctx.request,
                )
                if not result.ok:
                    ctx.fail(result.message)
                    return ReactTurn(
                        thought="先把用户需求转换成明确的光学目标",
                        action="parse_requirements",
                        action_input={"mode": ctx.request.mode, "prompt": ctx.request.prompt},
                        observation=result.message,
                        done=True,
                    )
                ctx.params = result.data
                runtime.memory.refresh_task_context(ctx.memory_snapshot, ctx.request, ctx.params)
                return ReactTurn(
                    thought="用户需求已整理为结构化镜头参数",
                    action="parse_requirements",
                    action_input={"mode": ctx.request.mode, "prompt": ctx.request.prompt},
                    observation=result.message,
                )

            message = "Budget: curriculum={curriculum}, fine_tune={fine_tune}".format(
                curriculum=ctx.params.curriculum.iterations,
                fine_tune=ctx.params.fine_tune.iterations,
            )
            return ReactTurn(
                thought="确认优化预算已明确，再继续后续流程",
                observation=message,
                done=True,
            )

        ctx.agent_trace.extend(
            loop.run(
                "将用户意图解析为光学设计上下文",
                step,
                lambda msg: runtime.emit(ctx, msg),
                memory=ctx.memory_snapshot,
                available_tools=available_tools,
                system_prompt=workflow_agent_prompt(self.name),
                context=workflow_agent_context(
                    agent_name=self.name,
                    objective="将用户意图解析为光学设计上下文",
                    memory=ctx.memory_snapshot,
                    params=ctx.params,
                ),
            )
        )


class SeedDesignAgentNode:
    name = "seed_design_agent"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for seeding.")
            return

        loop = ReactAgentLoop("SeedDesignAgent", max_turns=2)

        available_tools = runtime.tool_names("seed_from_cases", "read_file", "list_dir")

        def step(state: ReactState) -> ReactTurn:
            if not ctx.references:
                result = runtime.registry.call(
                    "seed_from_cases",
                    ctx=runtime.tool_context(ctx, state),
                    params=ctx.params,
                    prompt=ctx.request.prompt or "",
                )
                if not result.ok:
                    return ReactTurn(
                        thought="参考种子生成失败，停止当前节点",
                        action="seed_from_cases",
                        action_input={"prompt": ctx.request.prompt or "", "target": _target_payload(ctx.params)},
                        observation=result.message,
                        done=True,
                    )
                ctx.params = result.data["params"]
                ctx.references.extend(result.data["references"])
                return ReactTurn(
                    thought="根据记忆和目标检索本地光学参考作为初始结构",
                    action="seed_from_cases",
                    action_input={"prompt": ctx.request.prompt or "", "target": _target_payload(ctx.params)},
                    observation=result.message or "Reference seeding completed.",
                )

            selected = next((item for item in ctx.references if item.get("selected")), None)
            if selected and selected.get("applied"):
                message = (
                    f"Seed accepted from {selected.get('case_id')}: "
                    f"{len(ctx.params.surf_list)} surface groups."
                )
            elif selected:
                message = (
                    f"Reference {selected.get('case_id')} was inspected but not applied; "
                    f"using current {len(ctx.params.surf_list)} surface groups."
                )
            else:
                message = f"No reference seed applied; using current {len(ctx.params.surf_list)} surface groups."
            return ReactTurn(
                thought="检查选中的初始结构是否适合进入优化",
                observation=message,
                done=True,
            )

        ctx.agent_trace.extend(
            loop.run(
                "选择并验证初始光学结构",
                step,
                lambda msg: runtime.emit(ctx, msg),
                memory=ctx.memory_snapshot,
                available_tools=available_tools,
                system_prompt=workflow_agent_prompt(self.name),
                context=workflow_agent_context(
                    agent_name=self.name,
                    objective="选择并验证初始光学结构",
                    memory=ctx.memory_snapshot,
                    params=ctx.params,
                    references=ctx.references,
                ),
            )
        )


class OptimizationAgentNode:
    name = "optimization_agent"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for optimization.")
            return

        loop = ReactAgentLoop("OptimizationAgent", max_turns=3)
        available_tools = runtime.tool_names("optimize_lens", "evaluate_lens", "read_file")

        def step(state: ReactState) -> ReactTurn:
            if not ctx.design_result:
                result = runtime.registry.call(
                    "optimize_lens",
                    ctx=runtime.tool_context(ctx, state),
                    params=ctx.params,
                )
                if not result.ok:
                    ctx.fail(result.message)
                    return ReactTurn(
                        thought="优化器运行失败，流程无法继续",
                        action="optimize_lens",
                        action_input={"target": _target_payload(ctx.params)},
                        observation=result.message,
                        done=True,
                    )
                ctx.design_result = result.data
                runtime.publish_artifact(ctx.design_result.get("result_dir"))
                return ReactTurn(
                    thought="当前还没有优化结果，先运行配置好的算法引擎",
                    action="optimize_lens",
                    action_input={"target": _target_payload(ctx.params)},
                    observation=result.message,
                )

            if not ctx.metrics.get("has_final_json"):
                result = runtime.registry.call(
                    "evaluate_lens",
                    ctx=runtime.tool_context(ctx, state),
                    result_dir=ctx.design_result["result_dir"],
                )
                ctx.metrics.update(result.data)
                ctx.metrics.update(
                    {
                        "rfov": ctx.design_result.get("rfov"),
                        "fnum": ctx.design_result.get("fnum"),
                        "r_sensor": ctx.design_result.get("r_sensor"),
                        "case_references": ctx.references,
                    }
                )
                return ReactTurn(
                    thought="优化器已生成结果，先评估像质指标再判断可信度",
                    action="evaluate_lens",
                    action_input={"result_dir": ctx.design_result["result_dir"]},
                    observation=result.message,
                )

            return ReactTurn(
                thought="DeepLens 优化和基础指标评估已完成，交给性能分析智能体做独立验证",
                observation="Optimization artifacts and DeepLens metrics are ready for performance analysis.",
                done=True,
            )

        ctx.agent_trace.extend(
            loop.run(
                "运行 DeepLens 优化并完成基础指标评估",
                step,
                lambda msg: runtime.emit(ctx, msg),
                memory=ctx.memory_snapshot,
                available_tools=available_tools,
                system_prompt=workflow_agent_prompt(self.name),
                context=workflow_agent_context(
                    agent_name=self.name,
                    objective="运行 DeepLens 优化并完成基础指标评估",
                    memory=ctx.memory_snapshot,
                    params=ctx.params,
                    references=ctx.references,
                    metrics=ctx.metrics,
                    issues=ctx.issues,
                ),
            )
        )


class AnalysisAgentNode:
    name = "performance_analysis_agent"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for performance analysis.")
            return
        if not ctx.design_result:
            ctx.fail("No optimized design artifacts are available for performance analysis.")
            return

        loop = ReactAgentLoop("AnalysisAgent", max_turns=3)
        available_tools = runtime.tool_names("analyze_zemax", "read_file")

        def step(state: ReactState) -> ReactTurn:
            if "zemax" not in ctx.metrics:
                result = runtime.registry.call(
                    "analyze_zemax",
                    ctx=runtime.tool_context(ctx, state),
                    final_zmx=ctx.design_result.get("final_zmx"),
                    result_dir=ctx.design_result.get("result_dir"),
                )
                ctx.metrics["zemax"] = result.data
                _merge_zemax_metrics(ctx.metrics, result.data)
                runtime.publish_artifact(ctx.design_result.get("result_dir"))
                if not result.ok:
                    return ReactTurn(
                        thought="Zemax 暂不可用，保留 DeepLens 指标作为部分结果",
                        action="analyze_zemax",
                        action_input={"final_zmx": ctx.design_result.get("final_zmx")},
                        observation=f"Zemax analysis unavailable: {result.data.get('error')}",
                )
                return ReactTurn(
                    thought="用 Zemax 独立评估导出的 final.zmx",
                    action="analyze_zemax",
                    action_input={"final_zmx": ctx.design_result.get("final_zmx")},
                    observation=result.message,
                )

            ctx.accepted, ctx.issues = _evaluate_acceptance(ctx.params, ctx.metrics)
            ctx.metrics["acceptance"] = {"accepted": ctx.accepted, "issues": ctx.issues}
            message = "Design accepted by evaluator." if ctx.accepted else "Design completed with evaluator issues."
            if ctx.issues:
                message += " " + "; ".join(ctx.issues[:3])
            return ReactTurn(
                thought="将实测性能与用户目标逐项对比",
                action="evaluate_acceptance",
                action_input={"target": _target_payload(ctx.params), "metric_keys": sorted(ctx.metrics)},
                observation=message,
                done=True,
            )

        ctx.agent_trace.extend(
            loop.run(
                "执行商业级性能分析并判断光学验收结果",
                step,
                lambda msg: runtime.emit(ctx, msg),
                memory=ctx.memory_snapshot,
                available_tools=available_tools,
                system_prompt=workflow_agent_prompt(self.name),
                context=workflow_agent_context(
                    agent_name=self.name,
                    objective="执行商业级性能分析并判断光学验收结果",
                    memory=ctx.memory_snapshot,
                    params=ctx.params,
                    references=ctx.references,
                    metrics=ctx.metrics,
                    issues=ctx.issues,
                ),
            )
        )


class ReportMemoryNode:
    name = "report_memory_agent"

    def run(self, ctx: WorkflowContext, runtime: LensWorkflow) -> None:
        if ctx.result is not None:
            return

        loop = ReactAgentLoop("ReportMemoryAgent", max_turns=1)

        def step(state: ReactState) -> ReactTurn:
            if ctx.failed or not ctx.design_result:
                result = AgentResult(
                    ok=False,
                    summary=ctx.failure_summary or "Lens design failed.",
                    references=ctx.references,
                    timeline=ctx.timeline,
                    memory_snapshot=ctx.memory_snapshot,
                )
                ctx.result = _record_memory(
                    runtime.memory,
                    ctx.request,
                    result,
                    ctx.params,
                    system_prompt=state.system_prompt,
                )
                return ReactTurn(
                    thought="流程未产出可用设计，记录简洁的失败记忆",
                    action="record_memory",
                    action_input={"ok": False, "summary": result.summary},
                    observation=result.summary,
                    done=True,
                )

            metrics_file = _archive_metrics(ctx.design_result.get("result_dir"), ctx.metrics)
            summary = _build_summary(ctx.metrics, ctx.accepted, ctx.issues)
            summary_report_file = _archive_generation_report(
                request=ctx.request,
                result_dir=ctx.design_result.get("result_dir"),
                summary=summary,
                params=ctx.params,
                design_result=ctx.design_result,
                metrics=ctx.metrics,
                agent_trace=ctx.agent_trace,
            )

            result = AgentResult(
                ok=True,
                summary=summary,
                result_dir=ctx.design_result.get("result_dir"),
                curriculum_json=ctx.design_result.get("curriculum_json"),
                final_json=ctx.design_result.get("final_json"),
                final_zmx=ctx.design_result.get("final_zmx"),
                summary_report_file=summary_report_file,
                log_file=ctx.design_result.get("log_file"),
                metrics_file=metrics_file,
                metrics=ctx.metrics,
                references=ctx.references,
                timeline=ctx.timeline,
                memory_snapshot=ctx.memory_snapshot,
            )
            runtime.emit(ctx, "流程已完成。")
            ctx.result = _record_memory(
                runtime.memory,
                ctx.request,
                result,
                ctx.params,
                system_prompt=state.system_prompt,
            )
            return ReactTurn(
                thought="归档指标与报告，并更新可复用的光学设计记忆",
                action="archive_report_and_memory",
                action_input={"accepted": ctx.accepted, "issues": ctx.issues},
                observation=summary,
                done=True,
            )

        ctx.agent_trace.extend(
            loop.run(
                "归档运行结果并更新分层记忆",
                step,
                lambda msg: runtime.emit(ctx, msg),
                memory=ctx.memory_snapshot,
                available_tools=[],
                system_prompt=workflow_agent_prompt(self.name),
                context=workflow_agent_context(
                    agent_name=self.name,
                    objective="归档运行结果并更新分层记忆",
                    memory=ctx.memory_snapshot,
                    params=ctx.params,
                    references=ctx.references,
                    metrics=ctx.metrics,
                    issues=ctx.issues,
                ),
            )
        )


def _record_memory(
    memory: AgentMemory,
    request: AgentInput,
    result: AgentResult,
    params: LensDesignParams | None,
    *,
    system_prompt: str,
) -> AgentResult:
    try:
        memory.record_design_run(request, result, params=params)
        memory.record_engineering_lesson(request, result, params=params, system_prompt=system_prompt)
    except Exception as exc:
        result.timeline.append(f"Memory recording skipped: {exc}")
    return result


def _target_payload(params: LensDesignParams | None) -> dict[str, Any] | None:
    if params is None:
        return None
    return {
        "foclen": params.foclen,
        "fov": params.fov,
        "fnum": params.fnum,
        "bfl": params.bfl,
        "thickness": params.thickness,
        "surf_list": params.surf_list,
    }


def _node_label(name: str) -> str:
    labels = {
        "intake_agent": "需求解析",
        "seed_design_agent": "初始结构选择",
        "optimization_agent": "优化与基础评估",
        "performance_analysis_agent": "性能分析",
        "report_memory_agent": "报告归档",
    }
    return labels.get(name, name)


def _archive_metrics(result_dir: str | None, metrics: dict[str, Any]) -> str | None:
    if not result_dir:
        return None
    metrics_path = Path(result_dir) / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(metrics_path)


def _archive_generation_report(
    *,
    request: AgentInput,
    result_dir: str | None,
    summary: str,
    params: LensDesignParams | None,
    design_result: dict[str, Any],
    metrics: dict[str, Any],
    agent_trace: list[dict[str, Any]],
) -> str | None:
    if not result_dir:
        return None

    report_path = Path(result_dir) / "summary.md"
    request_payload = {
        "mode": request.mode,
        "prompt": request.prompt,
        "params": asdict(request.params) if request.params else None,
    }
    final_lens = _safe_read_json(design_result.get("final_json"))
    starting_lens = _safe_read_json(Path(result_dir) / "starting-point.json")
    lines = [
        "# LensBot 生成报告",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Result directory: `{result_dir}`",
        "",
        "## 用户输入",
        "",
        _fenced_json(request_payload),
        "",
        "## 思考轨迹",
        "",
        _format_trace_summary(agent_trace),
        "",
        "## 优化结果",
        "",
        f"- Summary: {summary}",
        f"- Starting point: `{design_result.get('starting_json') or str(Path(result_dir) / 'starting-point.json')}`",
        f"- Curriculum lens: `{design_result.get('curriculum_json')}`",
        f"- Final lens JSON: `{design_result.get('final_json')}`",
        f"- Final lens ZMX: `{design_result.get('final_zmx')}`",
        f"- Metrics file: `{str(Path(result_dir) / 'metrics.json')}`",
        "",
        "## 关键指标",
        "",
        _fenced_json(_compact_metrics(metrics)),
        "",
        "## 初始结构摘要",
        "",
        _fenced_json(_surface_summary(starting_lens)),
        "",
        "## 最终结构摘要",
        "",
        _fenced_json(_surface_summary(final_lens)),
        "",
        "## 生效参数",
        "",
        _fenced_json(asdict(params) if params else None),
        "",
        "## 优化后镜头 JSON",
        "",
        _fenced_json(final_lens),
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def _build_summary(metrics: dict[str, Any], accepted: bool, issues: list[str]) -> str:
    base = (
        "Lens design finished. "
        f"spot_rms_edge={metrics.get('spot_rms_um_edge')}um, "
        f"distortion_edge={metrics.get('distortion_pct_edge')}%, "
        f"MTF50_center_tan={metrics.get('mtf50_center_tan_cy_mm')} cy/mm."
    )
    if accepted:
        return base + " Evaluator accepted the result."
    if issues:
        return base + " Evaluator noted: " + "; ".join(issues[:3]) + "."
    return base


def _format_trace_summary(agent_trace: list[dict[str, Any]]) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for row in agent_trace:
        action = row.get("action")
        if not action:
            continue
        label = _trace_action_label(str(action))
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)

    if not labels:
        return "暂无思路概述。"

    if len(labels) == 1:
        return f"已完成{labels[0]}。"

    if len(labels) == 2:
        return f"已完成{labels[0]}，随后进入{labels[1]}。"

    return f"已完成{labels[0]}、{labels[1]}等步骤，最后进入{labels[-1]}。"


def _trace_action_label(action: str) -> str:
    labels = {
        "parse_requirements": "需求解析",
        "seed_from_cases": "初始结构选择",
        "optimize_lens": "镜头优化",
        "evaluate_lens": "结果评估",
        "analyze_zemax": "Zemax 校验",
        "evaluate_acceptance": "性能验收",
        "record_memory": "经验记忆记录",
        "archive_report_and_memory": "报告归档",
    }
    return labels.get(action, action.replace("_", ""))


def _evaluate_acceptance(params: LensDesignParams, metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []

    efl = _first_number(metrics, "zemax_efl_mm", "deeplens_efl_mm")
    if efl is not None and params.foclen > 0:
        drift = abs(efl - params.foclen) / params.foclen
        if drift > 0.25:
            issues.append(f"EFL drift is {drift:.0%}.")

    fnum = _first_number(metrics, "zemax_fnum", "deeplens_fnum", "fnum")
    if fnum is not None and params.fnum > 0:
        drift = abs(fnum - params.fnum) / params.fnum
        if drift > 0.30:
            issues.append(f"F-number drift is {drift:.0%}.")

    fov = _first_number(metrics, "zemax_fov_deg", "deeplens_fov_deg")
    if fov is not None and params.fov > 0:
        drift = abs(fov - params.fov) / params.fov
        if drift > 0.30:
            issues.append(f"FOV drift is {drift:.0%}.")

    spot_edge = _first_number(metrics, "zemax_spot_rms_edge_um", "spot_rms_um_edge")
    if spot_edge is not None and spot_edge > 500:
        issues.append(f"Edge RMS spot is high ({spot_edge:.3g}um).")

    if metrics.get("zemax_ok") is False:
        error = metrics.get("zemax_error") or "unknown error"
        issues.append(f"Zemax analysis unavailable: {error}.")

    return len(issues) == 0, issues


def _first_number(values: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = values.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


def _safe_read_json(path_value: str | Path | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _surface_summary(lens_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not lens_json:
        return None
    surfaces = lens_json.get("surfaces", [])
    return {
        "foclen": lens_json.get("foclen"),
        "fnum": lens_json.get("fnum"),
        "r_sensor": lens_json.get("r_sensor"),
        "surface_count": len(surfaces),
        "surface_types": [surface.get("type", "Unknown") for surface in surfaces],
        "materials": [
            surface.get("mat2")
            for surface in surfaces
            if isinstance(surface.get("mat2"), str) and surface.get("mat2")
        ],
    }


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "rfov",
        "fnum",
        "r_sensor",
        "spot_rms_um_center",
        "spot_rms_um_edge",
        "distortion_pct_edge",
        "mtf50_center_tan_cy_mm",
        "mtf50_edge_tan_cy_mm",
        "zemax_ok",
        "zemax_efl_mm",
        "zemax_fnum",
        "zemax_fov_deg",
        "zemax_distortion_pct_edge",
        "zemax_spot_rms_edge_um",
        "zemax_mtf50_center_tan_cy_mm",
        "zemax_mtf50_edge_tan_cy_mm",
        "acceptance",
    ]
    compact = {key: metrics.get(key) for key in keys if key in metrics}
    zemax = metrics.get("zemax")
    if isinstance(zemax, dict) and zemax.get("error"):
        compact["zemax_error"] = zemax.get("error")
    return compact


def _fenced_json(value: object) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def _merge_zemax_metrics(metrics: dict[str, Any], zemax_report: dict[str, Any]) -> None:
    metrics["zemax_ok"] = bool(zemax_report.get("ok"))
    if not zemax_report.get("ok"):
        metrics["zemax_error"] = zemax_report.get("error")
        return

    spot_summary = zemax_report.get("spot_summary") or {}
    system_metrics = zemax_report.get("system_metrics") or {}
    distortion_metrics = system_metrics.get("distortion") or {}
    mtf_summary = zemax_report.get("mtf_summary") or {}

    def spot_um(key: str) -> float | None:
        value = spot_summary.get(key)
        return None if value is None else float(value)

    def spot_mm(key: str) -> float | None:
        value_um = spot_um(key)
        return value_um / 1000.0 if value_um is not None else None

    metrics.update(
        {
            "zemax_field_count": zemax_report.get("field_count"),
            "zemax_wavelength_count": zemax_report.get("wavelength_count"),
            "zemax_efl_mm": system_metrics.get("efl_mm"),
            "zemax_fnum": system_metrics.get("fnum"),
            "zemax_fov_deg": system_metrics.get("fov_deg"),
            "zemax_distortion_pct_edge": distortion_metrics.get("edge_pct"),
            "zemax_distortion_pct_abs_max": distortion_metrics.get("abs_max_pct"),
            "zemax_mtf50_center_tan_cy_mm": mtf_summary.get("mtf50_center_tangential"),
            "zemax_mtf50_center_sag_cy_mm": mtf_summary.get("mtf50_center_sagittal"),
            "zemax_mtf50_edge_tan_cy_mm": mtf_summary.get("mtf50_edge_tangential"),
            "zemax_mtf50_edge_sag_cy_mm": mtf_summary.get("mtf50_edge_sagittal"),
            "zemax_spot_rms_min_um": spot_um("rms_spot_radius_min"),
            "zemax_spot_rms_edge_um": spot_um("rms_spot_radius_edge"),
            "zemax_spot_rms_max_um": spot_um("rms_spot_radius_max"),
            "zemax_spot_geo_min_um": spot_um("geo_spot_radius_min"),
            "zemax_spot_geo_edge_um": spot_um("geo_spot_radius_edge"),
            "zemax_spot_geo_max_um": spot_um("geo_spot_radius_max"),
            "zemax_spot_rms_min_mm": spot_mm("rms_spot_radius_min"),
            "zemax_spot_rms_edge_mm": spot_mm("rms_spot_radius_edge"),
            "zemax_spot_rms_max_mm": spot_mm("rms_spot_radius_max"),
            "zemax_spot_geo_min_mm": spot_mm("geo_spot_radius_min"),
            "zemax_spot_geo_edge_mm": spot_mm("geo_spot_radius_edge"),
            "zemax_spot_geo_max_mm": spot_mm("geo_spot_radius_max"),
            "zemax_report_file": zemax_report.get("report_file"),
            "zemax_figure_files": zemax_report.get("figure_files", []),
        }
    )
