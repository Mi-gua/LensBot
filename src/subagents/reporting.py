from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.memory import run_memory_update
from agent.settings import AgentInput, AgentResult
from runtime.artifacts import refresh_run_manifest
from runtime.traces import trace_row as _trace_row
from subagents.types import LensDesignParams, public_params_dict


class ReportingNode:
    name = "Reporting"

    def run(self, ctx: Any, runtime: Any) -> None:
        if ctx.result is not None:
            return

        if ctx.failed or not ctx.design_result:
            result = AgentResult(
                ok=False,
                summary=ctx.failure_summary or "Lens design failed.",
                references=ctx.references,
                timeline=ctx.timeline,
                memory_snapshot=ctx.memory_snapshot,
            )
            ctx.result = _record_memory(runtime, ctx, ctx.request, result, ctx.params)
            trace = [
                _trace_row(
                    agent=self.name,
                    turn=0,
                    thought="Record a compact failed-run memory because no usable design was produced.",
                    action="record_memory",
                    action_input={"ok": False, "summary": result.summary},
                    observation=result.summary,
                    done=True,
                )
            ]
            ctx.agent_trace.extend(trace)
            runtime.record_agent_trace(ctx, trace)
            return

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
        refresh_run_manifest(ctx.design_result.get("result_dir"), metrics=ctx.metrics)

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
        _record_final_review_memory(ctx, runtime, result)
        runtime.emit_event(ctx, "workflow.done")
        ctx.result = _record_memory(runtime, ctx, ctx.request, result, ctx.params)

        trace = [
            _trace_row(
                agent=self.name,
                turn=0,
                thought="Archive metrics and report, then update reusable optical design memory.",
                action="archive_report_and_memory",
                action_input={"accepted": ctx.accepted, "issues": ctx.issues},
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
            accepted=ctx.accepted,
            issues=ctx.issues,
        )
        ctx.memory_snapshot["final_review_lessons"] = runtime.memory.load_markdown_lessons("final_review")

    run_memory_update(runtime, ctx, label="final review lessons", update=update)


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
        "params": public_params_dict(params or request.params),
    }
    final_lens = _safe_read_json(design_result.get("final_json"))
    starting_json = design_result.get("starting_json") or (
        Path(result_dir) / "engines" / "deeplens" / "attempts" / "attempt-001-curriculum" / "starting-point.json"
    )
    starting_lens = _safe_read_json(starting_json)
    lines = [
        "# LensBot Generation Report",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Result directory: `{result_dir}`",
        "",
        "## User Input",
        "",
        _fenced_json(request_payload),
        "",
        "## Agent Trace",
        "",
        _format_trace_summary(agent_trace),
        "",
        "## Optimization Result",
        "",
        f"- Summary: {summary}",
        f"- Starting point: `{starting_json}`",
        f"- Curriculum lens: `{design_result.get('curriculum_json')}`",
        f"- Final lens JSON: `{design_result.get('final_json')}`",
        f"- Final lens ZMX: `{design_result.get('final_zmx')}`",
        f"- Metrics file: `{str(Path(result_dir) / 'metrics.json')}`",
        "",
        "## Key Metrics",
        "",
        _fenced_json(_compact_metrics(metrics)),
        "",
        "## Starting Structure Summary",
        "",
        _fenced_json(_surface_summary(starting_lens)),
        "",
        "## Final Structure Summary",
        "",
        _fenced_json(_surface_summary(final_lens)),
        "",
        "## Effective Parameters",
        "",
        _fenced_json(public_params_dict(params)),
        "",
        "## Final Lens JSON",
        "",
        _fenced_json(final_lens),
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def _build_summary(metrics: dict[str, Any], accepted: bool, issues: list[str]) -> str:
    final_summary = _normalize_final_summary(metrics.get("final_summary"))
    if final_summary:
        return final_summary

    status = "优化已完成，最终结构与 Zemax 文件已生成。" if accepted else "优化已完成，但当前结果仍有需要复核的质量或目标漂移问题。"
    if accepted:
        return status + " 关键指标已归档，可进入完整结果页查看详细评估。"
    if issues:
        caveats = "；".join(str(issue).strip().rstrip(".。") for issue in issues[:2] if str(issue).strip())
        if caveats:
            return f"{status} 主要注意事项：{caveats}。"
    return status + " 详细指标已归档，建议结合结果页和 summary.md 继续判断是否需要重跑。"


def _normalize_final_summary(value: Any) -> str:
    return " ".join(str(value or "").split())


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
        return "No agent trace was recorded."
    if len(labels) == 1:
        return f"Completed {labels[0]}."
    if len(labels) == 2:
        return f"Completed {labels[0]}, then {labels[1]}."
    return f"Completed {labels[0]}, {labels[1]}, and later {labels[-1]}."


def _trace_action_label(action: str) -> str:
    labels = {
        "parse_requirements": "requirement parsing",
        "confirm_budget": "budget confirmation",
        "retrieve_seed_cases": "seed candidate retrieval",
        "confirm_seed": "seed confirmation",
        "read_seed_cases": "reference batch inspection",
        "deeplens_curriculum": "curriculum learning",
        "deeplens_finetune": "fine-tune export",
        "deeplens_analysis": "DeepLens analysis",
        "finish": "pi finish validation",
        "zemax_analysis": "Zemax validation",
        "record_finish_acceptance": "finish acceptance record",
        "record_memory": "memory recording",
        "archive_report_and_memory": "report archiving",
    }
    return labels.get(action, action.replace("_", " "))


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
        "zemax_status",
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


__all__ = ["ReportingNode"]
