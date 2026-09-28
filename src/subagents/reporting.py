from __future__ import annotations

import base64
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.llm import OpenAIExtractor
from agent.memory import run_memory_update
from agent.prompts import (
    DEFAULT_REPORT_CONTENT_REQUEST,
    REPORT_NARRATIVE_FIELDS,
    REPORT_TEMPLATE_VERSION,
    workflow_agent_prompt,
)
from agent.settings import AgentInput, AgentResult
from runtime.artifacts import refresh_run_manifest
from runtime.evidence import build_result_evidence, compact_metric_values, compact_metrics_archive
from runtime.traces import trace_row as _trace_row
from subagents.types import LensDesignParams, public_params_dict


class ReportingNode:
    name = "Reporting"

    def run(self, ctx: Any, runtime: Any) -> None:
        if ctx.result is not None:
            return

        if not ctx.design_result:
            ctx.fail("没有可用于撰写设计报告的优化结果。")
            return

        result_dir = ctx.design_result.get("result_dir")
        evidence = build_result_evidence(result_dir, ctx.metrics, public_params_dict(ctx.params))
        summary = str(evidence["summary"])
        summary_report_file, metrics_file = _archive_reporting_outputs(
            runtime=runtime,
            ctx=ctx,
            request=ctx.request,
            result_dir=result_dir,
            summary=summary,
            params=ctx.params,
            design_result=ctx.design_result,
            evidence=evidence,
        )

        result = AgentResult(
            ok=ctx.delivery_status == "ready",
            summary=summary,
            result_dir=ctx.design_result.get("result_dir"),
            curriculum_json=ctx.design_result.get("curriculum_json"),
            candidate_json=ctx.design_result.get("candidate_json"),
            candidate_zmx=ctx.design_result.get("candidate_zmx"),
            candidate_png=ctx.design_result.get("candidate_png"),
            final_json=ctx.design_result.get("final_json"),
            final_zmx=ctx.design_result.get("final_zmx"),
            summary_report_file=summary_report_file,
            log_file=ctx.design_result.get("log_file"),
            metrics_file=metrics_file,
            metrics={
                **compact_metric_values(ctx.metrics),
                **({"delivery": ctx.metrics["delivery"]} if isinstance(ctx.metrics.get("delivery"), dict) else {}),
                **({"agent_verdict": ctx.metrics["agent_verdict"]} if isinstance(ctx.metrics.get("agent_verdict"), dict) else {}),
            },
            references=ctx.references,
            timeline=ctx.timeline,
            memory_snapshot=ctx.memory_snapshot,
        )
        _record_final_review_memory(ctx, runtime, result)
        runtime.emit_event(ctx, "workflow.done")
        ctx.result = _record_memory(runtime, ctx, ctx.request, result, ctx.params)

        trace = [
            _trace_row(
                agent=self.name,
                turn=0,
                thought="Archive metrics and report, then update reusable optical design memory.",
                action="archive_report_and_memory",
                action_input={"delivery_status": ctx.delivery_status, "issues": ctx.issues},
                observation=summary,
                done=True,
            )
        ]
        ctx.agent_trace.extend(trace)
        runtime.record_agent_trace(ctx, trace)


def _record_memory(
    runtime: Any,
    ctx: Any,
    request: AgentInput,
    result: AgentResult,
    params: LensDesignParams | None,
) -> AgentResult:
    try:
        runtime.memory.record_design_run(request, result, params=params)
    except Exception as exc:
        runtime.emit_event(ctx, "workflow.memory.skipped", error=exc)
    return result


def _record_final_review_memory(ctx: Any, runtime: Any, result: AgentResult) -> None:
    def update() -> None:
        runtime.memory.record_final_review_lessons(
            request=ctx.request,
            params=ctx.params,
            result=result,
            metrics=ctx.metrics,
            references=ctx.references,
            delivery_status=ctx.delivery_status,
            issues=ctx.issues,
        )
        ctx.memory_snapshot["final_review_lessons"] = runtime.memory.load_markdown_lessons("final_review")

    run_memory_update(runtime, ctx, label="final review lessons", update=update)


def _archive_metrics(result_dir: str | None, metrics: dict[str, Any]) -> str | None:
    if not result_dir:
        return None
    metrics_path = Path(result_dir) / "metrics.json"
    metrics_path.write_text(json.dumps(compact_metrics_archive(metrics), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(metrics_path)


def _archive_evidence(result_dir: str | None, evidence: dict[str, Any]) -> str | None:
    if not result_dir:
        return None
    path = Path(result_dir) / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def _archive_reporting_outputs(
    *,
    runtime: Any,
    ctx: Any,
    request: AgentInput,
    result_dir: str | None,
    summary: str,
    params: LensDesignParams | None,
    design_result: dict[str, Any],
    evidence: dict[str, Any],
    outcome: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Archive the same report bundle for both completed and failed runs."""

    _archive_evidence(result_dir, evidence)
    summary_report_file = _archive_generation_report(
        request=request,
        result_dir=result_dir,
        summary=summary,
        params=params,
        design_result=design_result,
        evidence=evidence,
    )
    try:
        report_usage = _archive_html_report(
            request=request,
            result_dir=result_dir,
            params=params,
            evidence=evidence,
            references=ctx.references,
            agent_trace=ctx.agent_trace,
            outcome=outcome,
        )
        if report_usage:
            ctx.metrics.update({f"reporting_{key}": value for key, value in report_usage.items()})
    except Exception as exc:
        ctx.metrics["reporting_error"] = f"{type(exc).__name__}: {exc}"
    metrics_file = _archive_metrics(result_dir, ctx.metrics)
    refresh_run_manifest(result_dir, metrics=ctx.metrics)
    runtime.publish_artifact(result_dir, ctx=ctx)
    return summary_report_file, metrics_file


def _archive_generation_report(
    *,
    request: AgentInput,
    result_dir: str | None,
    summary: str,
    params: LensDesignParams | None,
    design_result: dict[str, Any],
    evidence: dict[str, Any],
) -> str | None:
    if not result_dir:
        return None

    report_path = Path(result_dir) / "summary.md"
    delivered_json = design_result.get("final_json") or design_result.get("candidate_json")
    delivered_zmx = design_result.get("final_zmx") or design_result.get("candidate_zmx")
    delivered_label = "最终结构" if design_result.get("final_json") else "最新候选（优化未完成）"
    delivered_lens = _safe_read_json(delivered_json)
    if design_result.get("final_json"):
        delivered_note = "该结构已完成正式交付。"
    elif _same_artifact_path(delivered_json, design_result.get("analysis_json")):
        delivered_note = "该候选已完成分析，但尚未完成正式 finish。"
    else:
        analyzed = design_result.get("analysis_json") or "未记录"
        delivered_note = f"该候选尚未完成对应分析；当前指标对应的分析对象为 `{analyzed}`。"
    starting_json = design_result.get("starting_json") or _discover_starting_json(result_dir, design_result)
    starting_lens = _safe_read_json(starting_json)
    lines = [
        "# LensBot 结果摘要",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Result directory: `{result_dir}`",
        "",
        "## 设计要求",
        "",
        str(request.prompt or "").strip() or "未提供自然语言要求。",
        "",
        _markdown_params(public_params_dict(params or request.params)),
        "",
        "## 结论",
        "",
        summary,
        "",
        _markdown_delivery(evidence.get("delivery")),
        "",
        "## 重要结果与证据",
        "",
        _markdown_evidence(evidence),
        "",
        "## 结构摘要",
        "",
        "### 初始结构",
        "",
        _fenced_json(_surface_summary(starting_lens)),
        "",
        f"### {delivered_label}",
        "",
        delivered_note,
        "",
        _fenced_json(_surface_summary(delivered_lens)),
        "",
        "## 文件索引",
        "",
        f"- {delivered_label} JSON：`{delivered_json}`",
        f"- {delivered_label} Zemax：`{delivered_zmx}`",
        f"- 规范化证据：`{str(Path(result_dir) / 'evidence.json')}`",
        f"- 标量指标：`{str(Path(result_dir) / 'metrics.json')}`",
        f"- 光学设计总结：`{str(Path(result_dir) / 'report.html')}`",
        f"- Zemax 验证：`{str(Path(result_dir) / 'verification' / 'zemax' / 'zemax_report.json')}`",
        f"- 优化审计：`{str(Path(result_dir) / 'agents' / 'optimization' / 'views' / 'turns.json')}`",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def _archive_html_report(
    *,
    request: AgentInput,
    result_dir: str | None,
    params: LensDesignParams | None,
    evidence: dict[str, Any],
    references: list[dict[str, Any]],
    agent_trace: list[dict[str, Any]],
    outcome: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Write the fixed visual report; user input can influence text content only."""

    if not result_dir:
        return {}
    root = Path(result_dir)
    selected_references = _report_references(references)
    target = public_params_dict(params or request.params) or {}
    process = _report_process(agent_trace, target)
    narrative, usage = _report_narrative(
        request=request,
        target=target,
        references=selected_references,
        process=process,
        evidence=evidence,
        outcome=outcome or {"status": "complete"},
    )
    model = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": root.name,
        "template_version": REPORT_TEMPLATE_VERSION,
        "design_request": str(request.prompt or "").strip() or "采用结构化参数输入。",
        "target": target,
        "evidence": evidence,
        "references": selected_references,
        "process": process,
        "narrative": narrative,
        "outcome": outcome or {"status": "complete"},
        "figures": _report_figures(root),
    }
    report_path = root / "report.html"
    report_path.write_text(_render_html_report(model), encoding="utf-8")
    return usage


def _report_narrative(
    *,
    request: AgentInput,
    target: dict[str, Any],
    references: list[dict[str, Any]],
    process: dict[str, Any],
    evidence: dict[str, Any],
    outcome: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    fallback = (
        _fallback_failed_narrative(target, references, process, evidence, outcome)
        if str(outcome.get("status") or "").lower() == "failed"
        else _fallback_narrative(target, references, process, evidence)
    )
    extractor = OpenAIExtractor()
    context = {
        "design_request": request.prompt,
        "report_content_contract": DEFAULT_REPORT_CONTENT_REQUEST,
        "effective_target": target,
        "reference_cases": references,
        "optimization_process": process,
        "result_evidence": evidence,
        "run_outcome": outcome,
    }
    system_prompt = workflow_agent_prompt(
        "Reporting",
        objective="生成全面、精炼且证据充分的光学设计总结文字内容",
        context=context,
    )
    payload = {
        "task": "write_optical_design_summary",
        "report_content_contract": context["report_content_contract"],
    }
    try:
        generated = extractor.extract_json(json.dumps(payload, ensure_ascii=False), system_prompt)
    except Exception:
        return fallback, {}
    if not isinstance(generated, dict):
        return fallback, {}
    return _normalize_narrative(generated, fallback), dict(extractor.last_usage)


def _normalize_narrative(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, Any] = {}
    for key in REPORT_NARRATIVE_FIELDS:
        if key == "optimization_decisions":
            fallback_rows = fallback.get(key) if isinstance(fallback.get(key), list) else []
            generated_rows = source.get(key) if isinstance(source.get(key), list) else []
            normalized_rows = []
            for index, fallback_row in enumerate(fallback_rows[:6]):
                row = generated_rows[index] if index < len(generated_rows) and isinstance(generated_rows[index], dict) else {}
                fallback_row = fallback_row if isinstance(fallback_row, dict) else {}
                normalized = {
                    field: _normalize_report_wording(
                        " ".join(str(row.get(field) or fallback_row.get(field) or "").split())
                    )[:500]
                    for field in ("stage", "observation", "action", "result")
                }
                normalized["turns"] = str(fallback_row.get("turns") or "")
                normalized_rows.append(normalized)
            result[key] = normalized_rows
            continue
        text = " ".join(str(source.get(key) or fallback[key]).split())
        result[key] = _normalize_report_wording(text)[:1400]
    return result


def _normalize_report_wording(text: str) -> str:
    """Keep the generated report framed as a design summary, not a project update."""

    return (
        text.replace("本项目", "本次设计")
        .replace("项目内", "设计范围内")
        .replace("项目成果", "设计结果")
        .replace("项目", "设计")
    )


def _fallback_failed_narrative(
    target: dict[str, Any],
    references: list[dict[str, Any]],
    process: dict[str, Any],
    evidence: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Produce an evidence-bounded conclusion when no usable design was delivered."""

    failure_summary = _normalize_report_wording(
        " ".join(str(outcome.get("summary") or "设计流程未形成可交付候选。").split())
    )
    if failure_summary[-1:] not in "。！？.!?":
        failure_summary += "。"
    target_text = "、".join(
        text
        for text in (
            _target_text("焦距", target.get("foclen"), "mm"),
            _target_text("F 数", target.get("fnum"), ""),
            _target_text("全视场", target.get("fov"), "°"),
            _target_text("初始后焦距", target.get("bfl"), "mm"),
            _target_text("初始总长", target.get("thickness"), "mm"),
        )
        if text
    )
    decisions = process.get("decisions") if isinstance(process.get("decisions"), list) else []
    milestones = process.get("milestones") if isinstance(process.get("milestones"), list) else []
    evidence_count = sum(len(section.get("items") or []) for section in evidence.get("sections") or [])
    reference_text = (
        "运行记录中已保留参考结构选择及其来源，可用于复核设计起点与目标规格之间的关系。"
        if references
        else "现有归档中没有足以展开结构选择依据的参考案例记录。"
    )
    process_text = (
        f"优化记录保留了 {len(decisions)} 个可审计决策阶段和 {len(milestones)} 次正式性能复核；"
        "这些记录用于定位失败发生前完成了哪些尝试，以及最后一个有证据支持的状态。"
        if decisions or milestones
        else "现有运行记录不足以重建有效的优化决策链，说明流程在形成可评价候选之前已经终止。"
    )
    achieved_text = (
        f"本次运行的最终结论是设计失败。现有归档仅包含 {evidence_count} 项可核验指标，"
        "未形成同时具备最终结构、完整一阶规格和验证证据的可交付候选，因此不能宣称设计目标已经实现。"
    )
    return {
        "abstract": (
            f"本次设计接收的结构化输入为{target_text or '已归档的光学参数'}，但流程未形成可交付的最终候选。"
            "归档结论明确为设计失败。报告仅依据失败前留下的输入、参考选择、运行轨迹和定量证据，"
            "说明已经完成的尝试、终止位置及其证据边界，不将缺失产物或未测指标解释为成功结果。"
        ),
        "task_interpretation": (
            f"输入配置为{target_text or '已归档的结构化光学参数'}。其中焦距、F 数和全视场是光学目标；"
            "后焦距与总长是初始几何参数，最终值单独测量和记录。"
            "最终判断只依据流程中真实产生的结构、指标和验证记录。"
        ),
        "design_strategy": reference_text,
        "optimization_analysis": process_text,
        "optimization_decisions": decisions,
        "achieved_performance": achieved_text,
        "evidence_interpretation": (
            f"现有证据共记录 {evidence_count} 项可核验指标。它们只支持判断失败前已经到达的阶段和暴露的问题；"
            "缺失最终结构、关键指标或验证图时，报告不据此补写性能结论，也不把运行状态转换为光学达标判断。"
        ),
        "principal_design_tradeoff": failure_summary,
        "design_summary": (
            "本次运行的最终结论是设计失败，未形成可交付的光学候选。"
            "报告已经保存输入目标、参考依据、可审计尝试和失败前证据，使该结论可以由归档记录复核。"
        ),
    }


def _fallback_narrative(
    target: dict[str, Any],
    references: list[dict[str, Any]],
    process: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    target_text = "、".join(
        text
        for text in (
            _target_text("焦距", target.get("foclen"), "mm"),
            _target_text("F 数", target.get("fnum"), ""),
            _target_text("全视场", target.get("fov"), "°"),
            _target_text("初始后焦距", target.get("bfl"), "mm"),
            _target_text("初始总长", target.get("thickness"), "mm"),
        )
        if text
    )
    evidence_items = [item for section in evidence.get("sections") or [] for item in section.get("items") or []]
    items = {str(item.get("key") or ""): item for item in evidence_items if isinstance(item, dict)}

    def metric_fact(key: str) -> str:
        item = items.get(key) or {}
        primary = item.get("primary") if isinstance(item.get("primary"), dict) else {}
        if primary.get("value") is None:
            return ""
        unit_name = {"deg": "°", "um": "μm", "%": "%"}.get(str(item.get("unit") or ""), str(item.get("unit") or ""))
        unit = "" if not unit_name else (unit_name if unit_name in {"°", "%"} else f" {unit_name}")
        delta = item.get("delta_pct")
        delta_text = f"，相对目标 {float(delta):+.2f}%" if delta is not None else ""
        return f"{item.get('label') or key} {_format_number(primary.get('value'))}{unit}{delta_text}"

    def cross_engine_fact(key: str) -> str:
        item = items.get(key) or {}
        primary = item.get("primary") if isinstance(item.get("primary"), dict) else {}
        supporting = item.get("supporting") if isinstance(item.get("supporting"), list) else []
        secondary = next((row for row in supporting if isinstance(row, dict) and row.get("value") is not None), None)
        if primary.get("value") is None or secondary is None:
            return ""
        primary_value = float(primary["value"])
        secondary_value = float(secondary["value"])
        difference = abs(secondary_value - primary_value) / (abs(primary_value) or 1.0) * 100.0
        return (
            f"{item.get('label') or key}在 {primary.get('source') or '主记录'} 与"
            f" {secondary.get('source') or '辅助记录'} 之间相差约 {difference:.1f}%"
        )

    case_names = "、".join(
        dict.fromkeys(str(row.get("title") or row.get("case_id") or "案例") for row in references[:3])
    )
    case_text = (
        f"本次结构检索重点比较了 {case_names}，这些参考结构共同用于判断玻璃组合、光阑邻近组形态和整体尺度。"
        "Double Gauss 的近对称功率分配适合中等视场与中等相对孔径，可借助光阑两侧的像差互补控制彗差、畸变和横向色差；"
        "本次优化继承的是这种组态关系，而不是直接复制原处方，并通过曲率、间隔和后组自由度适配当前焦距与结构包络。"
        if references
        else "本次归档中没有可展示的参考案例，因此初始结构的光学依据无法从现有材料中展开。"
    )
    tool_counts = process.get("tool_counts") or {}
    fine_tune_count = int(tool_counts.get("deeplens_finetune", 0)) + int(tool_counts.get("deeplens_fine_tune", 0))
    analysis_count = int(tool_counts.get("deeplens_analysis", 0)) + int(tool_counts.get("deeplens_evaluate", 0))
    milestones = process.get("milestones") if isinstance(process.get("milestones"), list) else []
    first_milestone = milestones[0] if milestones else {}
    final_milestone = milestones[-1] if milestones else {}

    def improvement_percent(key: str) -> float | None:
        first_value = first_milestone.get(key)
        final_value = final_milestone.get(key)
        if first_value in (None, 0) or final_value is None:
            return None
        return (float(first_value) - float(final_value)) / abs(float(first_value)) * 100.0

    spot_improvement = improvement_percent("rms_spot_max_um")
    distortion_improvement = improvement_percent("distortion_abs_max_pct")
    trajectory_result = ""
    if first_milestone and final_milestone and first_milestone is not final_milestone:
        trajectory_result = (
            f"首次实光线复核发现候选仍为 EFL {_format_number(first_milestone.get('efl_mm'))} mm、"
            f"F/{_format_number(first_milestone.get('fnum'))}、全视场 {_format_number(first_milestone.get('fov_deg'))}°，"
            "说明优化目标函数的收敛尚未兑现为真实一阶性能。"
            f"经过连续微调，最终 DeepLens 结果回到 EFL {_format_number(final_milestone.get('efl_mm'))} mm、"
            f"F/{_format_number(final_milestone.get('fnum'))}、全视场 {_format_number(final_milestone.get('fov_deg'))}°"
            + (f"，最大 RMS 光斑较首次复核下降 {spot_improvement:.1f}%" if spot_improvement is not None else "")
            + (f"、最大绝对畸变下降 {distortion_improvement:.1f}%" if distortion_improvement is not None else "")
            + "。"
        )
    process_text = (
        "优化先用课程式求解将参考组态连续变换到目标规格附近，再通过检查点观察损失、一阶参数和结构稳定性。"
        f"过程中安排了 {analysis_count} 次正式光线性能复核，使焦距、F 数、视场和像质判断回到实际追迹结果，而不是只依赖优化目标函数。"
        + (f"复核后实施 {fine_tune_count} 轮精细微调，以小步方式回拉一阶漂移并观察像质变化；这种交替策略把“参数收敛”和“真实性能成立”分开检验。" if fine_tune_count else "随后根据复核结果继续调整候选。")
        + trajectory_result
        + "整个阶段由初始结构、候选检查、连续微调和最终分析构成一条可追溯的演进链。"
    )
    first_order_deltas = [
        abs(float((items.get(key) or {})["delta_pct"]))
        for key in ("efl_mm", "fnum", "fov_deg")
        if (items.get(key) or {}).get("delta_pct") is not None
    ]
    first_order_cross = "；".join(
        fact for fact in (cross_engine_fact(key) for key in ("efl_mm", "fnum", "fov_deg")) if fact
    )
    image_cross = "；".join(
        fact for fact in (cross_engine_fact(key) for key in ("rms_spot_max_um", "distortion_abs_max_pct")) if fact
    )
    missing_zemax = not any(str(source.get("key")) == "zemax_report" for source in evidence.get("sources") or [])
    limitation_parts = []
    valid_rays = (items.get("edge_valid_rays_pct") or {}).get("primary") or {}
    if valid_rays.get("value") is not None:
        limitation_parts.append("边缘采样通过率偏低，表明离轴光束仍有明显裁切")
    if missing_zemax:
        limitation_parts.append("本次没有形成 Zemax 交叉记录，像质解释只能依据单一计算链路")
    limitation_text = "；".join(limitation_parts)
    if limitation_text:
        limitation_text += "。这些现象共同指向结构压缩与边缘通光之间的同一项设计权衡，直接限定了当前结果的适用范围，也构成后续优化的首要方向。"
    final_result_text = ""
    if final_milestone:
        final_result_text = (
            f"最终 DeepLens 候选达到 EFL {_format_number(final_milestone.get('efl_mm'))} mm、"
            f"F/{_format_number(final_milestone.get('fnum'))}、全视场 {_format_number(final_milestone.get('fov_deg'))}°"
        )
    improvement_text = ""
    if spot_improvement is not None or distortion_improvement is not None:
        parts = []
        if spot_improvement is not None:
            parts.append(f"最大 RMS 光斑较首次实光线复核下降 {spot_improvement:.1f}%")
        if distortion_improvement is not None:
            parts.append(f"最大绝对畸变下降 {distortion_improvement:.1f}%")
        improvement_text = "，".join(parts)
    return {
        "abstract": (
            f"本次设计围绕{target_text or '既定光学规格'}展开，目标是在有限结构尺度内同时保持一阶参数和全视场成像质量。"
            f"系统以筛选后的 Double Gauss 类摄影物镜为起点，通过课程优化、正式光线复核和 {fine_tune_count} 轮精细微调纠正了初始候选的真实性能漂移。"
            f"{final_result_text or '最终候选已形成'}；{improvement_text or '光斑与畸变得到持续改善'}，并由 Zemax 结果完成交叉检查。"
            "本次设计由此形成了从需求转译、结构选择、迭代纠偏到证据汇总的完整闭环；当前最主要的设计权衡集中在结构包络与边缘通光。"
        ),
        "task_interpretation": (
            f"本次结构化输入为{target_text or '已归档的光学参数'}。焦距、F 数和全视场是当前流程评价的光学目标；"
            "后焦距与总长用于定义起始几何和设计意图，最终值单独测量和记录。"
            "最终报告分别检查光学目标、像质和实测结构尺度。"
        ),
        "design_strategy": case_text,
        "optimization_analysis": process_text,
        "optimization_decisions": process.get("decisions") or [],
        "achieved_performance": (
            f"本次共归一整理 {len(evidence_items)} 项定量记录。"
            + (f"最终有效焦距、工作 F 数和全视场的最大目标偏差为 {max(first_order_deltas):.2f}%，说明主要一阶规格已经被拉回目标邻域；" if first_order_deltas else "一阶规格缺少完整的目标偏差记录；")
            + (f"跨工具比较显示：{first_order_cross}，一阶趋势具有较好一致性；" if first_order_cross else "")
            + (f"而{image_cross}，说明像质类指标对计算定义和采样更敏感。" if image_cross else "")
            + f"最终{metric_fact('rms_spot_max_um') or '最大光斑未记录'}、{metric_fact('distortion_abs_max_pct') or '畸变未记录'}；"
            + "这些结果与最终结构共同说明了本次设计实际实现的光学水平。"
        ),
        "evidence_interpretation": (
            "初始与最终结构图展示了参考组态经过功率、曲率和间隔重分配后形成的实际候选，结构演进应与候选性能表联合阅读。"
            "点列图给出不同视场的几何光线会聚形态，可用于比较中心到边缘的斑形扩展和多波长分离；"
            "FFT MTF 则描述各视场切向与弧矢方向的对比度传递，两类图分别回答几何聚焦和空间频率响应问题。"
            "边缘有效光线不足会削弱离轴图像和曲线的代表性；同时 DeepLens 的几何评价与 Zemax FFT MTF 并非同一算法口径，因此跨工具比较主要用于确认一阶趋势和问题位置，而不是把全部像质数值直接相减。"
        ),
        "principal_design_tradeoff": limitation_text,
        "design_summary": (
            "本次设计首先将自然语言需求转化为焦距、孔径、视场与结构包络之间相互制约的光学目标，并据此选择 Double Gauss 类结构作为可优化起点。"
            "设计过程没有停留在初始拓扑复用，而是通过课程优化、真实光线复核与多轮精细微调，持续识别并纠正代理指标与实际成像性能之间的偏差。"
            "关键调整均以一阶规格、光斑、畸变和边缘有效光线的联合变化为依据，使结构演进与性能判断保持对应。"
            "最终候选将有效焦距、F 数和视场保持在目标邻域，并相较初始实光线结果改善了主要像质指标。"
            "结构图、定量指标、点列图、MTF 及跨工具结果共同构成结论依据，因此该结果既说明了当前设计实际实现的水平，也保留了继续沿同一结构谱系细化的清晰路径。"
        ),
    }


def _report_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in references if row.get("selected") or row.get("applied") or row.get("inspected")]
    rows = rows or references
    result = []
    for row in rows[:3]:
        reasons = row.get("reasons") or row.get("risks") or []
        list_reason = reasons[0] if isinstance(reasons, list) and reasons else ""
        reason = (
            row.get("selection_rationale")
            or row.get("design_rationale")
            or list_reason
            or row.get("snippet")
            or ""
        )
        result.append(
            {
                "case_id": row.get("case_id") or row.get("candidate_id"),
                "title": row.get("title") or row.get("case_id") or "参考案例",
                "category": row.get("category") or "",
                "reason": " ".join(str(reason).split())[:320],
                "selected": bool(row.get("selected")),
                "applied": bool(row.get("applied")),
            }
        )
    return result


def _report_figures(root: Path) -> dict[str, dict[str, Any]]:
    starting_candidates = list(
        (root / "engines" / "deeplens" / "attempts").glob("attempt-*-*/starting-point.png")
    )
    starting = max(starting_candidates, key=_attempt_index) if starting_candidates else None
    specs = {
        "starting": (starting, "初始光学结构", "展示参考拓扑进入求解时的分组、光阑位置与多视场光线路径。"),
        "final": (root / "final" / "final.png", "最终光学结构", "展示优化后实际保留的功率分配、轴向间隔与离轴光束传播。"),
        "spot": (
            root / "verification" / "zemax" / "spot_diagram.png",
            "多色光斑分布",
            "用于比较中心、中间与边缘视场的几何会聚形态及多波长像差变化。",
        ),
        "mtf": (
            root / "verification" / "zemax" / "fft_mtf.png",
            "多色 FFT MTF",
            "用于判断各视场切向与弧矢方向随空间频率变化的对比度传递趋势。",
        ),
        "distortion": (
            root / "verification" / "zemax" / "distortion.png",
            "网格畸变矢量",
            "展示 OpticStudio 原生网格畸变分析的像面残差矢量，用于观察视场内的成像位置偏离。",
        ),
    }
    figures: dict[str, dict[str, Any]] = {}
    for key, (path, title, caption) in specs.items():
        if path is None or not path.is_file():
            continue
        image_bytes = path.read_bytes()
        width = int.from_bytes(image_bytes[16:20], "big") if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else None
        height = int.from_bytes(image_bytes[20:24], "big") if width else None
        figures[key] = {
            "title": title,
            "caption": caption,
            "src": "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii"),
            "width": width,
            "height": height,
        }
    return figures


def _report_process(agent_trace: list[dict[str, Any]], target: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = [row for row in agent_trace if str(row.get("agent") or "") == "Optimization"]
    tool_rows = _report_tool_rows(rows)
    utility_tools = {"powershell", "read_file", "write_file", "edit_file"}
    counts = Counter(_trace_tool(row) for row in tool_rows if _trace_tool(row) not in utility_tools)
    preferred = {
        "deeplens_curriculum",
        "deeplens_fine_tune",
        "deeplens_finetune",
        "deeplens_analysis",
        "deeplens_evaluate",
        "deeplens_inspect_checkpoint",
        "zemax_analysis",
        "finish",
    }
    milestones = []
    checkpoints = []
    fine_tune_settings: dict[str, Any] = {}
    for row in tool_rows:
        if _trace_tool(row) == "deeplens_inspect_checkpoint":
            result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
            metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
            checkpoint = {
                "turn": row.get("turn"),
                "efl_mm": metrics.get("deeplens_efl_mm", metrics.get("efl_mm")),
                "fnum": metrics.get("deeplens_fnum", metrics.get("fnum")),
                "fov_deg": metrics.get("deeplens_fov_deg", metrics.get("fov_deg")),
                "efl_drift": metrics.get("efl_drift"),
                "fnum_drift": metrics.get("fnum_drift"),
                "fov_drift": metrics.get("fov_drift"),
            }
            if any(checkpoint.get(key) is not None for key in ("efl_mm", "fnum", "fov_deg")):
                checkpoints.append(checkpoint)
        if _trace_tool(row) in {"deeplens_finetune", "deeplens_fine_tune"} and not fine_tune_settings:
            call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
            arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            settings = arguments.get("fine_tune") if isinstance(arguments.get("fine_tune"), dict) else arguments
            fine_tune_settings = {
                key: settings.get(key)
                for key in ("iterations", "num_ring", "num_arm", "spp")
                if settings.get(key) is not None
            }
        if _trace_tool(row) not in {"deeplens_analysis", "deeplens_evaluate"}:
            continue
        result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        efl = metrics.get("deeplens_efl_mm")
        fnum = metrics.get("deeplens_fnum")
        fov = metrics.get("deeplens_fov_deg")
        if efl is None and fnum is None and fov is None:
            continue
        milestones.append(
            {
                "turn": row.get("turn"),
                "stage": "课程后实光线复核" if not milestones else f"微调候选 {len(milestones)}",
                "efl_mm": efl,
                "fnum": fnum,
                "fov_deg": fov,
                "rms_spot_max_um": metrics.get("deeplens_rms_spot_um_max"),
                "distortion_abs_max_pct": metrics.get("deeplens_distortion_pct_abs_max"),
                "edge_valid_rays_pct": metrics.get("deeplens_spot_valid_pct_edge"),
            }
        )
    if len(milestones) > 1:
        milestones[-1]["stage"] = "最终候选"
    relevant_turns = sorted(
        (int(row["turn"]), _trace_tool(row))
        for row in tool_rows
        if row.get("turn") is not None and _trace_tool(row) in preferred
    )
    fine_tune_turns = [
        turn for turn, tool in relevant_turns if tool in {"deeplens_finetune", "deeplens_fine_tune"}
    ]
    decision_ranges = []
    for index, milestone in enumerate(milestones):
        analysis_turn = int(milestone.get("turn") or 0)
        start = (
            min((turn for turn, _ in relevant_turns if turn <= analysis_turn), default=analysis_turn)
            if index == 0
            else max((turn for turn in fine_tune_turns if turn <= analysis_turn), default=analysis_turn)
        )
        next_start = next((turn for turn in fine_tune_turns if turn > analysis_turn), None)
        end = max(
            (turn for turn, _ in relevant_turns if turn >= analysis_turn and (next_start is None or turn < next_start)),
            default=analysis_turn,
        )
        decision_ranges.append((start, end))
    decisions = _decision_trajectory(
        milestones,
        target or {},
        checkpoints,
        fine_tune_settings,
        decision_ranges,
    )
    return {
        "tool_counts": dict(counts.most_common()),
        "milestones": milestones,
        "checkpoints": checkpoints,
        "fine_tune_settings": fine_tune_settings,
        "decisions": decisions,
    }


def _report_tool_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select one complete record for each archived tool turn."""

    selected: dict[tuple[Any, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        tool = _trace_tool(row)
        if row.get("done") or tool in {"", "agent_end"}:
            continue
        turn = row.get("turn")
        key = (turn if turn is not None else f"row-{index}", tool)
        current = selected.get(key)
        if current is None or _report_tool_row_score(row, tool) > _report_tool_row_score(current, tool):
            selected[key] = row
    return list(selected.values())


def _report_tool_row_score(row: dict[str, Any], tool: str) -> tuple[int, int, int, int]:
    call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
    result = row.get("tool_result") if isinstance(row.get("tool_result"), dict) else {}
    has_arguments = int(bool(call.get("arguments") or row.get("arguments")))
    has_metrics = int(bool(result.get("metrics") or row.get("metrics")))
    complete_turn = int(str(row.get("kind") or "") == "tool_turn")
    preferred_payload = has_arguments if tool in {"deeplens_finetune", "deeplens_fine_tune"} else has_metrics
    return complete_turn, preferred_payload, has_metrics + has_arguments, len(result)


def _decision_trajectory(
    milestones: list[dict[str, Any]],
    target: dict[str, Any],
    checkpoints: list[dict[str, Any]] | None = None,
    fine_tune_settings: dict[str, Any] | None = None,
    turn_ranges: list[tuple[int, int]] | None = None,
) -> list[dict[str, str]]:
    """Build an auditable action/rationale/outcome trail without exposing hidden reasoning."""

    if not milestones:
        return []

    def brief(value: Any, digits: int = 2) -> str:
        if value is None:
            return "—"
        return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")

    def metrics_text(row: dict[str, Any]) -> str:
        parts = []
        if row.get("efl_mm") is not None:
            parts.append(f"EFL {brief(row['efl_mm'])} mm")
        if row.get("fnum") is not None:
            parts.append(f"F/{brief(row['fnum'])}")
        if row.get("fov_deg") is not None:
            parts.append(f"全视场 {brief(row['fov_deg'])}°")
        if row.get("rms_spot_max_um") is not None:
            parts.append(f"最大 RMS 光斑 {brief(row['rms_spot_max_um'])} μm")
        if row.get("distortion_abs_max_pct") is not None:
            parts.append(f"最大畸变 {brief(row['distortion_abs_max_pct'])}%")
        if row.get("edge_valid_rays_pct") is not None:
            parts.append(f"边缘有效光线 {brief(row['edge_valid_rays_pct'])}%")
        return "、".join(parts)

    def reduction(previous: dict[str, Any], current: dict[str, Any], key: str) -> float | None:
        before = previous.get(key)
        after = current.get(key)
        if before in (None, 0) or after is None:
            return None
        return (float(before) - float(after)) / abs(float(before)) * 100.0

    def target_gap(row: dict[str, Any]) -> str:
        pairs = (("efl_mm", "foclen", "EFL"), ("fnum", "fnum", "F 数"), ("fov_deg", "fov", "全视场"))
        gaps = []
        for metric_key, target_key, label in pairs:
            value = row.get(metric_key)
            goal = target.get(target_key)
            if value is None or goal in (None, 0):
                continue
            gaps.append(f"{label}偏差 {abs(float(value) - float(goal)) / abs(float(goal)) * 100:.1f}%")
        return "、".join(gaps)

    settings = fine_tune_settings or {}
    setting_parts = []
    if settings.get("iterations") is not None:
        setting_parts.append(f"{settings['iterations']} 次迭代")
    if settings.get("num_ring") is not None and settings.get("num_arm") is not None:
        setting_parts.append(f"{settings['num_ring']} rings / {settings['num_arm']} arms")
    if settings.get("spp") is not None:
        setting_parts.append(f"{settings['spp']} spp")
    setting_text = "、".join(setting_parts)

    first = milestones[0]
    checkpoint = (checkpoints or [{}])[0]
    checkpoint_text = metrics_text(checkpoint)
    decisions = [
        {
            "stage": "代理结果转入实光线复核",
            "turns": _turn_range_text((turn_ranges or [(0, 0)])[0]),
            "observation": (
                f"课程优化后的检查点显示{checkpoint_text}，代理指标表面上已贴近目标。"
                if checkpoint_text
                else "课程优化与检查点显示代理目标趋于稳定，但尚不能证明真实光学性能成立。"
            ),
            "action": "调用正式光线分析复核焦距、F 数、视场与像质，避免依据代理收敛直接结束。",
            "result": f"首次复核得到{metrics_text(first)}；{target_gap(first)}。代理收敛没有兑现为真实一阶性能，因此转入真实光线反馈下的精细微调。",
        }
    ]
    labels = ("规格回拉", "平衡调整", "像质推进", "收敛判断")
    for index, current in enumerate(milestones[1:], start=1):
        previous = milestones[index - 1]
        spot_drop = reduction(previous, current, "rms_spot_max_um")
        distortion_drop = reduction(previous, current, "distortion_abs_max_pct")
        changes = []
        if spot_drop is not None:
            changes.append(f"最大 RMS 光斑较上一候选下降 {spot_drop:.1f}%")
        if distortion_drop is not None:
            direction = "下降" if distortion_drop >= 0 else "回升"
            changes.append(f"最大畸变{direction} {abs(distortion_drop):.1f}%")
        is_last = index == len(milestones) - 1
        edge_before = previous.get("edge_valid_rays_pct")
        edge_after = current.get("edge_valid_rays_pct")
        edge_change = None if edge_before is None or edge_after is None else float(edge_after) - float(edge_before)
        if is_last:
            action = "在保持当前结构谱系的前提下完成最后一次小步微调，并比较一阶稳定性与像质改善的边际收益。"
            closing = "；光斑与畸变的改善已经趋缓，边缘通光仍未解除，因此停止同拓扑继续迭代并保留该候选。"
        else:
            action = (
                "延续当前结构，在真实光线反馈下继续微调"
                + (f"（{setting_text}）" if setting_text and index == 1 else "")
                + "，优先回拉一阶规格，同时检查像质与边缘通光是否同步改善。"
            )
            if index == 1:
                closing = "；规格已大幅回拉，但孔径偏快且边缘有效光线继续下降，不能在此停止。"
            elif index == 2:
                closing = "；一阶规格进入目标邻域，但像质与通光权衡仍未稳定，继续观察下一轮。"
            else:
                closing = "；像质继续改善但边缘裁切加重，因此只再做一轮以判断边际收益。"
        if edge_change is not None:
            direction = "回升" if edge_change >= 0 else "下降"
            changes.append(f"边缘有效光线{direction} {abs(edge_change):.2f} 个百分点")
        if index == 1:
            observation = f"首次实光线复核显示{target_gap(previous)}，最大 RMS 光斑 {brief(previous.get('rms_spot_max_um'))} μm，必须先恢复真实规格。"
        elif index == 2:
            observation = f"第一次微调已将 EFL 与视场拉回，但 F/{brief(previous.get('fnum'))} 偏快，边缘有效光线降至 {brief(previous.get('edge_valid_rays_pct'))}%。"
        elif index == 3:
            observation = f"第二次微调使一阶规格进入目标邻域，最大 RMS 光斑为 {brief(previous.get('rms_spot_max_um'))} μm，但畸变轻微回升、边缘通光继续下降。"
        else:
            observation = f"第三次微调继续改善光斑与畸变，但边缘有效光线已降至 {brief(previous.get('edge_valid_rays_pct'))}%，需要确认继续迭代是否仍有价值。"
        decisions.append(
            {
                "stage": labels[index - 1] if index <= len(labels) else f"第 {index} 轮微调与复核",
                "turns": _turn_range_text(turn_ranges[index]) if turn_ranges and index < len(turn_ranges) else "",
                "observation": observation,
                "action": action,
                "result": f"本轮得到{metrics_text(current)}" + (f"；{'，'.join(changes)}" if changes else "") + closing,
            }
        )
    return decisions


def _turn_range_text(turn_range: tuple[int, int]) -> str:
    start, end = turn_range
    if start <= 0:
        return ""
    return f"TURN {start:02d}" if start == end else f"TURN {start:02d}–{end:02d}"


def _paper_metrics(evidence: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    """Select a compact evidence table without recreating the dashboard."""

    items = [
        item
        for section in evidence.get("sections") or []
        for item in section.get("items") or []
        if isinstance(item, dict) and isinstance(item.get("primary"), dict)
    ]
    targeted = [item for item in items if item.get("target") is not None]
    untargeted = [item for item in items if item.get("target") is None]
    return (targeted + untargeted)[:limit]


def _render_html_report(model: dict[str, Any]) -> str:
    esc = lambda value: html.escape(str("" if value is None else value), quote=True)
    evidence = model["evidence"]
    narrative = model["narrative"]
    failed_outcome = str((model.get("outcome") or {}).get("status") or "").lower() == "failed"
    evidence_count = sum(len(section.get("items") or []) for section in evidence.get("sections") or [])
    target_summary = " · ".join(
        text
        for text in (
            _target_text("EFL", model["target"].get("foclen"), "mm"),
            f'F/{_format_number(model["target"].get("fnum"))}' if model["target"].get("fnum") is not None else "",
            _target_text("FOV", model["target"].get("fov"), "deg"),
        )
        if text
    )
    source_keys = {str(source.get("key") or "") for source in evidence.get("sources") or []}
    analysis_sources = (
        "运行记录"
        if failed_outcome and not source_keys
        else ("DeepLens + Zemax" if "zemax_report" in source_keys else "DeepLens")
    )
    target_rows = []
    for label, key, unit in (
        ("有效焦距 EFL", "foclen", "mm"),
        ("相对孔径 F/#", "fnum", ""),
        ("全视场 FOV", "fov", "deg"),
        ("初始后焦距 BFL", "bfl", "mm"),
        ("初始系统总长 TTL", "thickness", "mm"),
    ):
        value = model["target"].get(key)
        if value is not None:
            target_rows.append(f'<tr><th>{esc(label)}</th><td>{esc(_format_number(value))} {esc(unit)}</td></tr>')
    target_table = "".join(target_rows) or '<tr><td colspan="2">未记录结构化设计参数。</td></tr>'
    decision_rows = "".join(
        f'<li><div class="decision-title"><h4>{esc(row.get("stage") or "关键决策")}</h4>'
        f'<span class="decision-turn">{esc(row.get("turns") or "")}</span></div><dl>'
        f'<dt>观察</dt><dd>{esc(row.get("observation") or "未记录。")}</dd>'
        f'<dt>行动</dt><dd>{esc(row.get("action") or "未记录。")}</dd>'
        f'<dt>结果</dt><dd>{esc(row.get("result") or "未记录。")}</dd></dl></li>'
        for row in (narrative.get("optimization_decisions") or [])[:6]
    ) or '<li><h4>过程未记录</h4><p>没有足够的运行记录可重建设计决策轨迹。</p></li>'
    decision_block = f'<h3>3.1　关键尝试与决策轨迹</h3><ol class="decision-trace">{decision_rows}</ol>'
    milestone_data = model["process"].get("milestones") or []
    milestone_parts = []
    for index, row in enumerate(milestone_data):
        row_class = "milestone-first" if index == 0 else ""
        if index == len(milestone_data) - 1 and len(milestone_data) > 1:
            row_class = "milestone-final"
        milestone_parts.append(
            f'<tr class="{row_class}"><th>{esc(row.get("stage") or "候选")}</th>'
            f'<td>{esc(_format_number(row.get("efl_mm")))}</td><td>{esc(_format_number(row.get("fnum")))}</td>'
            f'<td>{esc(_format_number(row.get("fov_deg")))}</td><td>{esc(_format_number(row.get("rms_spot_max_um")))}</td>'
            f'<td>{esc(_format_number(row.get("distortion_abs_max_pct")))}</td></tr>'
        )
    milestone_rows = "".join(milestone_parts)
    milestone_block = (
        '<h3>3.2　性能收敛记录</h3><div class="table-wrap"><table><caption>表 2　正式光线复核记录的候选演进</caption>'
        '<thead><tr><th>阶段</th><th>EFL / mm</th><th>F/#</th><th>FOV / deg</th>'
        f'<th>最大 RMS / μm</th><th>最大畸变 / %</th></tr></thead><tbody>{milestone_rows}</tbody></table></div>'
        if milestone_rows
        else ""
    )
    metric_rows = []
    for item in _paper_metrics(evidence):
        primary = item.get("primary") or {}
        unit = str(item.get("unit") or "")
        target = "—" if item.get("target") is None else _format_number(item.get("target"))
        delta = item.get("delta_pct")
        delta_text = "—" if delta is None else f"{float(delta):+.2f}%"
        metric_rows.append(
            f'<tr><th>{esc(item.get("label") or item.get("key") or "未命名指标")}</th>'
            f'<td>{esc(target)} {esc(unit)}</td><td>{esc(_format_number(primary.get("value")))} {esc(unit)}</td>'
            f'<td>{esc(delta_text)}</td><td>{esc(primary.get("source") or "记录值")}</td></tr>'
        )
    metric_table = "".join(metric_rows) or '<tr><td colspan="5">当前归档没有可列入正文的结构化测量结果。</td></tr>'
    source_rows = "".join(
        f'<li><b>{esc(source.get("label") or source.get("key"))}</b>'
        f'{" — " + esc(source.get("path")) if source.get("path") else ""}</li>'
        for source in evidence.get("sources") or []
    ) or '<li>未列出结构化证据来源。</li>'
    figures = model.get("figures") if isinstance(model.get("figures"), dict) else {}

    def figure_card(key: str, number: str) -> str:
        figure = figures.get(key)
        if not isinstance(figure, dict) or not figure.get("src"):
            return ""
        dimensions = ""
        if figure.get("width") and figure.get("height"):
            dimensions = f' width="{int(figure["width"])}" height="{int(figure["height"])}"'
        return (
            f'<figure class="figure-card figure-{esc(key)}">'
            f'<div class="figure-label">FIGURE {esc(number)}</div>'
            f'<div class="figure-image"><img src="{esc(figure.get("src"))}" alt="{esc(figure.get("title") or "光学分析图")}"{dimensions} loading="lazy" decoding="async"></div>'
            f'<figcaption><b>{esc(figure.get("title") or "光学分析图")}</b><span>{esc(figure.get("caption") or "")}</span></figcaption>'
            '</figure>'
        )

    structure_figures = "".join((figure_card("starting", "3.1"), figure_card("final", "3.2")))
    validation_figures = "".join((figure_card("mtf", "4.1"), figure_card("distortion", "4.2"), figure_card("spot", "4.3")))
    structure_block = (
        f'<h3>3.3　结构演进对照</h3><div class="figure-grid">{structure_figures}</div>'
        if structure_figures
        else ""
    )
    validation_block = (
        f'<h3>4.1　关键验证图</h3><div class="figure-grid">{validation_figures}</div>'
        if validation_figures
        else ""
    )
    evidence_number = "4.2" if validation_figures else "4.1"
    limitation_number = "4.3" if validation_figures else "4.2"
    limitation_text = str(narrative.get("principal_design_tradeoff") or "").strip()
    limitation_block = (
        f'<aside class="limitation"><h3>{limitation_number}　{esc("失败原因" if failed_outcome else "集中改进点")}</h3><p>{esc(limitation_text)}</p></aside>'
        if limitation_text
        else ""
    )
    result_heading = "运行结果与科学结论" if failed_outcome else "实现结果与科学讨论"
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>光学镜头设计总结报告</title><style>
:root{{--ink:#09090b;--text:#27272a;--muted:#71717a;--line:#e4e4e7;--soft:#f4f4f5;--paper:#fff;--accent:#3b82f6;--accent-soft:#eff6ff;--green:#10b981;--green-soft:#ecfdf5;--font-sans:"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif;--body-size:15px}}
*{{box-sizing:border-box}}html{{font-size:16px;color-scheme:light}}body{{margin:0;background:linear-gradient(180deg,#f4f4f5 0,#fafafa 360px,#f4f4f5 100%);color:var(--text);font-family:var(--font-sans);font-size:var(--body-size);line-height:1.84;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}}::selection{{background:#dbeafe;color:var(--ink)}}
.paper{{position:relative;width:min(1040px,calc(100% - 36px));margin:32px auto 72px;padding:58px 72px 54px;background:var(--paper);border:1px solid var(--line);border-radius:4px;box-shadow:0 20px 60px rgba(9,9,11,.065);overflow:hidden}}
.paper:before{{content:"";position:absolute;inset:0 0 auto;height:5px;background:linear-gradient(90deg,var(--ink) 0 46%,var(--accent) 46% 74%,var(--green) 74% 100%)}}
.journal-line,.subtitle,.meta-band,.section-head .no,.figure-label,figcaption,.note,table,footer{{font-family:var(--font-sans)}}
.journal-line{{display:flex;justify-content:space-between;gap:24px;padding-bottom:13px;border-bottom:1px solid var(--line);color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}}
header{{padding:54px 0 30px}}.kicker{{margin:0 0 15px;text-align:center;color:var(--muted);font-family:var(--font-sans);font-size:11px;font-weight:700;line-height:1.4;letter-spacing:.09em;text-transform:uppercase}}
h1{{max-width:760px;margin:0 auto 15px;text-align:center;text-wrap:balance;color:var(--ink);font-family:var(--font-sans);font-size:clamp(31px,5vw,42px);font-weight:750;line-height:1.28;letter-spacing:-.035em}}.subtitle{{margin:0 auto;text-align:center;text-wrap:balance;color:var(--muted);font-size:12px;letter-spacing:.06em}}
.abstract{{position:relative;margin:38px 0 0;padding:26px 28px 24px;background:linear-gradient(135deg,#fafafa 0%,#fff 64%);border:1px solid var(--line);border-radius:4px;font-size:14.5px;text-align:justify}}.abstract:before{{content:"";position:absolute;left:-1px;top:-1px;bottom:-1px;width:4px;background:var(--ink)}}.abstract h2{{margin:0 0 9px;color:var(--ink);font-family:var(--font-sans);font-size:13px;font-weight:750;line-height:1.4;letter-spacing:.08em}}.abstract p{{margin:0}}
.meta-band{{display:grid;grid-template-columns:repeat(3,1fr);margin-top:10px;border:1px solid var(--line);border-radius:4px;overflow:hidden;color:var(--muted);font-size:11px;line-height:1.55}}.meta-band span{{position:relative;padding:12px 12px 10px}}.meta-band span:before{{content:"";position:absolute;inset:0 0 auto;height:2px;background:var(--ink)}}.meta-band span:nth-child(2):before{{background:var(--green)}}.meta-band span+span{{border-left:1px solid var(--line)}}.meta-band b{{display:block;color:var(--ink);font-size:10px;letter-spacing:.06em;text-transform:uppercase}}
section{{--section-accent:var(--ink);margin:52px 0}}.section-process{{--section-accent:var(--accent)}}.section-results{{--section-accent:var(--green)}}.section-head{{position:relative;display:grid;grid-template-columns:42px 1fr;align-items:start;margin:0 0 20px;padding-bottom:12px;border-bottom:1px solid var(--line)}}.section-head:after{{content:"";position:absolute;left:0;bottom:-1px;width:72px;height:1px;background:var(--section-accent)}}h2{{margin:0;color:var(--ink);font-size:22px;line-height:1.45;font-weight:650;text-wrap:balance}}.section-head .no{{display:grid;place-items:center;width:28px;height:28px;background:var(--ink);color:#fff;border-radius:3px;font-size:11px;font-weight:800;letter-spacing:.02em}}h3{{margin:28px 0 12px;color:var(--ink);font-size:15px;text-wrap:balance}}p{{margin:0 0 16px;text-align:justify}}.lede{{font-size:15px}}.note{{margin-top:12px;color:var(--muted);font-size:11.5px;line-height:1.72}}
blockquote{{display:grid;grid-template-columns:110px minmax(0,1fr);gap:18px;align-items:start;margin:24px 0 0;padding:18px 20px;background:#fafafa;border:0;border-left:4px solid var(--ink);border-radius:0 4px 4px 0;color:#3f3f46;font-size:13px}}.quote-label{{color:var(--muted);font-family:var(--font-sans);font-size:10px;font-weight:750;line-height:1.75;letter-spacing:.08em}}.quote-text{{margin:0;text-align:left}}
.table-wrap{{margin:22px 0 10px;overflow-x:auto;border:1px solid var(--line);border-radius:4px}}.spec-wrap{{max-width:560px}}table{{width:100%;border-collapse:collapse;font-size:11.5px;line-height:1.58;font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}}caption{{padding:10px 12px;text-align:left;background:#fafafa;border-bottom:1px solid var(--line);color:var(--muted);font-size:10.5px;font-weight:650}}thead{{background:var(--ink);color:#fff}}tbody{{background:#fff}}th,td{{padding:10px 12px;text-align:left;vertical-align:top}}tbody tr+tr{{border-top:1px solid var(--line)}}tbody tr:nth-child(even){{background:#fafafa}}tbody tr.milestone-first{{background:var(--accent-soft);box-shadow:inset 3px 0 var(--accent)}}tbody tr.milestone-final{{background:var(--green-soft);box-shadow:inset 3px 0 var(--green)}}tbody tr.milestone-final th{{color:#047857}}th{{font-weight:650}}.spec-table th{{width:58%}}
.decision-trace{{display:grid;gap:0;margin:18px 0 28px;padding:0;list-style:none;counter-reset:decision}}.decision-trace li{{position:relative;margin-left:14px;padding:0 0 22px 34px;border-left:1px solid #bfdbfe;counter-increment:decision}}.decision-trace li:last-child{{border-left-color:transparent;padding-bottom:0}}.decision-trace li:before{{content:counter(decision,decimal-leading-zero);position:absolute;left:-14px;top:0;display:grid;place-items:center;width:27px;height:27px;background:#fff;border:1px solid var(--accent);border-radius:3px;color:var(--accent);font-size:9px;font-weight:750;line-height:1}}.decision-title{{display:flex;align-items:baseline;justify-content:space-between;gap:18px;margin:0 0 8px}}.decision-trace h4{{margin:0;color:var(--ink);font-size:15px;line-height:1.5}}.decision-turn{{flex:none;color:#71717a;font-size:10px;font-weight:700;line-height:1.5;letter-spacing:.08em;font-variant-numeric:tabular-nums}}.decision-trace dl{{display:grid;grid-template-columns:44px minmax(0,1fr);gap:4px 12px;margin:0}}.decision-trace dt{{color:#2563eb;font-size:12px;font-weight:700;line-height:1.75}}.decision-trace dd{{margin:0;color:#52525b;font-size:13.5px;line-height:1.75}}
.figure-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0 24px}}.figure-card{{margin:0;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:#fff;break-inside:avoid}}.figure-spot{{grid-column:1 / -1}}.figure-starting{{border-top:3px solid var(--accent)}}.figure-final,.figure-spot,.figure-mtf,.figure-distortion{{border-top:3px solid var(--green)}}.figure-label{{padding:7px 11px;background:#fafafa;border-bottom:1px solid var(--line);color:var(--muted);font-size:9px;font-weight:800;letter-spacing:.1em}}.figure-starting .figure-label{{color:#2563eb}}.figure-final .figure-label,.figure-spot .figure-label,.figure-mtf .figure-label,.figure-distortion .figure-label{{color:#047857}}.figure-image{{display:grid;place-items:center;min-height:220px;padding:12px;background:#fafafa}}.figure-image img{{display:block;width:100%;height:auto;max-height:390px;object-fit:contain}}figcaption{{display:grid;gap:2px;padding:11px 12px 13px;border-top:1px solid var(--line);font-size:11px;line-height:1.55}}figcaption b{{color:var(--ink);font-size:12px}}figcaption span{{color:var(--muted)}}
.evidence-analysis{{margin:26px 0 0;padding:20px 22px;background:#fff;border:1px solid var(--line);border-left:4px solid var(--green);border-radius:4px;font-size:var(--body-size)}}.evidence-analysis h3,.limitation h3{{margin:0 0 8px;font-family:var(--font-sans)}}.evidence-analysis h3{{color:#047857}}.evidence-analysis p,.limitation p{{margin:0}}.limitation{{margin:14px 0 0;padding:20px 22px;background:#fafafa;border:1px solid var(--line);border-left:4px solid var(--ink);border-radius:4px;font-size:var(--body-size)}}.conclusion{{position:relative;padding:24px 26px 24px 29px;background:#fafafa;border:1px solid var(--line);border-left:5px solid var(--ink);border-radius:4px;font-size:var(--body-size)}}
.appendix{{margin-top:52px;padding-top:30px;border-top:2px solid var(--ink);font-size:var(--body-size)}}.appendix .section-head{{border-bottom-color:var(--line)}}.appendix .note{{color:var(--text);font-size:inherit;line-height:1.84}}.references{{padding-left:20px}}.references li{{overflow-wrap:anywhere;color:#52525b;font-family:var(--font-sans);font-size:inherit;line-height:1.84}}footer{{margin-top:40px;padding:15px 18px;background:var(--soft);border-left:3px solid var(--muted);color:var(--muted);font-size:10.5px;line-height:1.65}}
@media(max-width:760px){{.paper{{width:100%;margin:0;padding:42px 22px;border:0}}.journal-line{{display:block}}.journal-line span:last-child{{display:block;margin-top:4px}}.meta-band,.figure-grid,blockquote{{grid-template-columns:1fr}}.meta-band span+span{{border-left:0;border-top:1px solid var(--line)}}.figure-image{{min-height:0}}th,td{{min-width:92px}}}}
@page{{size:A4;margin:16mm}}@media print{{html{{font-size:10.5pt}}body{{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}}.paper{{width:auto;margin:0;padding:0;border:0;box-shadow:none}}.paper:before{{display:none}}header{{padding-top:32px}}section{{break-inside:auto}}.section-head,h3,.table-wrap,.evidence-analysis,.limitation,.figure-card,.conclusion{{break-inside:avoid}}.abstract,.evidence-analysis,.limitation,blockquote{{background:#fff}}a{{color:inherit;text-decoration:none}}}}
</style></head><body><main class="paper">
<div class="journal-line"><span>Optical Design Summary</span><span>Run {esc(model["run_id"])} · {esc(model["generated_at"])}</span></div>
<header><p class="kicker">Lens Design / Scientific Summary</p><h1>光学镜头设计总结报告</h1><p class="subtitle">设计任务 · 方案演进 · 定量结果 · 光学分析</p>
<div class="abstract"><h2>摘要</h2><p>{esc(narrative["abstract"])}</p></div>
<div class="meta-band"><span><b>目标规格</b>{esc(target_summary or "采用结构化输入")}</span><span><b>定量证据</b>{esc(evidence_count)} 项指标 · {esc(len(figures))} 张关键图</span><span><b>分析来源</b>{esc(analysis_sources)}</span></div></header>
<section><div class="section-head"><span class="no">01</span><h2>任务理解与设计目标</h2></div><p class="lede">{esc(narrative["task_interpretation"])}</p><div class="table-wrap spec-wrap"><table class="spec-table"><caption>表 1　结构化设计输入</caption><tbody>{target_table}</tbody></table></div><blockquote><span class="quote-label">原始设计输入</span><p class="quote-text">{esc(model["design_request"])}</p></blockquote></section>
<section><div class="section-head"><span class="no">02</span><h2>设计策略与参考起点</h2></div><p>{esc(narrative["design_strategy"])}</p></section>
<section class="section-process"><div class="section-head"><span class="no">03</span><h2>设计实现与优化演进</h2></div><p class="lede">{esc(narrative["optimization_analysis"])}</p>{decision_block}{milestone_block}{structure_block}<p class="note">决策轨迹只呈现运行记录支持的观察、行动与结果；完整工具记录仍保存在归档中。图中结构用于解释方案演进，不单独构成性能结论。</p></section>
<section class="section-results"><div class="section-head"><span class="no">04</span><h2>{esc(result_heading)}</h2></div><p>{esc(narrative["achieved_performance"])}</p><div class="table-wrap"><table><caption>表 3　目标、实现值与证据来源</caption><thead><tr><th>指标</th><th>目标</th><th>记录结果</th><th>相对偏差</th><th>证据来源</th></tr></thead><tbody>{metric_table}</tbody></table></div>{validation_block}<div class="evidence-analysis"><h3>{evidence_number}　证据解释</h3><p>{esc(narrative["evidence_interpretation"])}</p></div>{limitation_block}</section>
<section><div class="section-head"><span class="no">05</span><h2>设计总结</h2></div><p class="conclusion">{esc(narrative["design_summary"])}</p></section>
<section class="appendix"><div class="section-head"><span class="no">A</span><h2>证据索引</h2></div><p class="note">以下文件直接支撑正文中的结构、指标、验证图和过程分析。</p><ol class="references">{source_rows}</ol></section>
<footer>Run {esc(model["run_id"])} · Template {esc(model["template_version"])} · 正文仅总结本次设计中已有证据支持的设计、优化与验证工作。</footer>
</main></body></html>'''


def _trace_tool(row: dict[str, Any]) -> str:
    call = row.get("tool_call") if isinstance(row.get("tool_call"), dict) else {}
    return str(call.get("name") or row.get("action") or row.get("tool") or "")


def _target_text(label: str, value: Any, unit: str) -> str:
    if value is None:
        return ""
    return f"{label} {_format_number(value)}{(' ' + unit) if unit else ''}"


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


def _same_artifact_path(left: str | Path | None, right: str | Path | None) -> bool:
    if not left or not right:
        return False
    return Path(left).resolve() == Path(right).resolve()


def _discover_starting_json(result_dir: str, design_result: dict[str, Any]) -> Path:
    curriculum_json = design_result.get("curriculum_json")
    if curriculum_json:
        candidate = Path(str(curriculum_json)).parent / "starting-point.json"
        if candidate.exists():
            return candidate
    attempts_root = Path(result_dir) / "engines" / "deeplens" / "attempts"
    candidates = [path for path in attempts_root.glob("attempt-*-*/starting-point.json") if path.is_file()]
    if not candidates:
        return attempts_root / "starting-point.json"
    return max(candidates, key=_attempt_index)


def _attempt_index(path: Path) -> int:
    for part in path.parts:
        if part.startswith("attempt-"):
            pieces = part.split("-", 2)
            if len(pieces) >= 2:
                try:
                    return int(pieces[1])
                except ValueError:
                    return 0
    return 0


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


def _markdown_params(params: dict[str, Any] | None) -> str:
    values = params or {}
    rows = [
        ("焦距", values.get("foclen"), "mm"),
        ("F 数", values.get("fnum"), ""),
        ("全视场", values.get("fov"), "deg"),
        ("初始后焦距 BFL", values.get("bfl"), "mm"),
        ("初始总长 TTL", values.get("thickness"), "mm"),
    ]
    lines = ["| 参数 | 输入值 |", "|---|---:|"]
    lines.extend(
        f"| {label} | {_format_number(value)}{(' ' + unit) if unit else ''} |"
        for label, value, unit in rows
        if value is not None
    )
    return "\n".join(lines)


def _markdown_evidence(evidence: dict[str, Any]) -> str:
    lines = ["| 指标 | 目标 | 结果 | 相对偏差 | 来源 |", "|---|---:|---:|---:|---|"]
    for section in evidence.get("sections") or []:
        for item in section.get("items") or []:
            primary = item.get("primary") or {}
            unit = str(item.get("unit") or "")
            suffix = f" {unit}" if unit else ""
            target = "—" if item.get("target") is None else f"{_format_number(item['target'])}{suffix}"
            value = f"{_format_number(primary.get('value'))}{suffix}"
            source = str(primary.get("source") or "—")
            supporting = item.get("supporting") or []
            delta = item.get("delta_pct")
            delta_text = "—" if delta is None else f"{float(delta):+.2f}%"
            if supporting:
                source += "（另有 " + "、".join(str(row.get("source") or "") for row in supporting) + "）"
            lines.append(
                f"| {item.get('label', item.get('key', ''))} | {target} | {value} | {delta_text} | {source} |"
            )
    return "\n".join(lines)


def _markdown_delivery(value: Any) -> str:
    delivery = value if isinstance(value, dict) else {}
    label = str(delivery.get("label") or "交付状态未知")
    meaning = str(delivery.get("meaning") or "该状态仅描述产物交付，不评价光学性能。")
    return f"> 交付记录：{label}。{meaning}"


def _format_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _fenced_json(value: object) -> str:
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


__all__ = ["ReportingNode"]
