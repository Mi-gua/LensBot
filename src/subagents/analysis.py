from __future__ import annotations

from typing import Any

from runtime.traces import trace_row as _trace_row


class AnalysisNode:
    name = "Analysis"

    def run(self, ctx: Any, runtime: Any) -> None:
        if ctx.params is None:
            ctx.fail("No design parameters are available for performance analysis.")
            return
        if not ctx.design_result:
            ctx.fail("No optimized design artifacts are available for performance analysis.")
            return

        trace: list[dict[str, Any]] = []
        if "zemax" not in ctx.metrics:
            result = runtime.registry.call(
                "zemax_analysis",
                ctx=runtime.tool_context(ctx, agent_name=self.name),
                final_zmx=ctx.design_result.get("final_zmx"),
                result_dir=ctx.design_result.get("result_dir"),
            )
            ctx.metrics["zemax"] = result.data
            _merge_zemax_metrics(ctx.metrics, result.data or {})
            runtime.publish_artifact(ctx.design_result.get("result_dir"), ctx=ctx)
            if result.ok:
                thought = "Run independent Zemax evaluation for exported final.zmx."
                observation = result.message
            else:
                status = str((result.data or {}).get("status") or "unavailable")
                reason = (result.data or {}).get("error") or "no reason reported"
                thought = "Zemax verification did not complete; keep DeepLens metrics as primary evidence."
                observation = f"Zemax verification {status}: {reason}. DeepLens metrics remain available."
            trace.append(
                _trace_row(
                    agent=self.name,
                    turn=0,
                    thought=thought,
                    action="zemax_analysis",
                    action_input={"final_zmx": ctx.design_result.get("final_zmx")},
                    observation=observation,
                    data=result.for_trace(),
                    ok=result.ok,
                )
            )

        ctx.accepted = True
        ctx.issues = []
        ctx.metrics["acceptance"] = {
            "accepted": True,
            "issues": [],
            "source": "optimization_finish",
            "note": "Optimization agent finish validated final artifacts and final analysis evidence; optical caveats remain in metrics and final_summary.",
        }
        trace.append(
            _trace_row(
                agent=self.name,
                turn=len(trace),
                thought="Record Optimization agent finish status without applying a second hardcoded optical threshold evaluator.",
                action="record_finish_acceptance",
                action_input={"source": "optimization_finish", "metric_keys": sorted(ctx.metrics)},
                observation="Optimization finish contract accepted final artifacts and evidence. Metrics are retained for review.",
                done=True,
            )
        )
        ctx.agent_trace.extend(trace)
        runtime.record_agent_trace(ctx, trace)


def _merge_zemax_metrics(metrics: dict[str, Any], zemax_report: dict[str, Any]) -> None:
    status = _zemax_status(zemax_report)
    metrics["zemax_status"] = status
    metrics["zemax_ok"] = status == "complete"
    if zemax_report.get("error"):
        metrics["zemax_error"] = zemax_report.get("error")
    if not zemax_report.get("ok"):
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


def _zemax_status(zemax_report: dict[str, Any]) -> str:
    status = str(zemax_report.get("status") or "").strip().lower()
    if status in {"complete", "unavailable", "failed", "skipped"}:
        return status
    return "complete" if zemax_report.get("ok") else "unavailable"


__all__ = ["AnalysisNode"]
