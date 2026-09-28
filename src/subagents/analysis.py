from __future__ import annotations

import math
from typing import Any

from runtime.evidence import build_delivery_record
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

        delivery = build_delivery_record(
            ctx.design_result.get("final_json") or "",
            ctx.design_result.get("final_zmx") or "",
            source="optimization_finish",
        )
        missing = delivery["missing_artifacts"]
        ctx.delivery_status = delivery["status"]
        ctx.issues = [f"Missing required artifact: {name}" for name in missing]
        ctx.metrics["delivery"] = delivery
        trace.append(
            _trace_row(
                agent=self.name,
                turn=len(trace),
                thought="Record one delivery status for required artifacts without inferring optical quality.",
                action="record_delivery_status",
                action_input={"source": "optimization_finish", "metric_keys": sorted(ctx.metrics)},
                observation=(
                    "Required artifacts are ready; optical measurements remain factual evidence."
                    if not missing
                    else "Delivery is incomplete: " + ", ".join(missing)
                ),
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

    spot_summary = zemax_report["spot_summary"]
    system_metrics = zemax_report["system_metrics"]
    distortion_metrics = system_metrics["distortion"]
    mtf_summary = zemax_report["mtf_summary"]
    geometric_mtf_summary = zemax_report["geometric_mtf_summary"]
    spot_unit = str(zemax_report["spot_unit"])

    def spot_value(key: str, target_unit: str) -> float | None:
        return _convert_spot_value(
            spot_summary.get(key),
            source_unit=spot_unit,
            target_unit=target_unit,
        )

    metrics.update(
        {
            "zemax_metric_source": zemax_report["metric_source"],
            "zemax_field_count": zemax_report.get("field_count"),
            "zemax_wavelength_count": zemax_report.get("wavelength_count"),
            "zemax_spot_unit": spot_unit,
            "zemax_spot_unit_source": zemax_report.get("spot_unit_source"),
            "zemax_efl_mm": system_metrics.get("efl_mm"),
            "zemax_efl_unit": system_metrics.get("efl_unit"),
            "zemax_efl_source": system_metrics.get("efl_source"),
            "zemax_fnum": system_metrics.get("fnum"),
            "zemax_fnum_source": system_metrics.get("fnum_source"),
            "zemax_real_working_fnum": system_metrics.get("real_working_fnum"),
            "zemax_primary_wavelength_number": system_metrics.get(
                "primary_wavelength_number"
            ),
            "zemax_pupil": system_metrics.get("pupil"),
            "zemax_fov_deg": system_metrics.get("fov_deg"),
            "zemax_fov_unit": system_metrics.get("fov_unit"),
            "zemax_fov_source": system_metrics.get("fov_source"),
            "zemax_distortion_pct_edge": distortion_metrics.get("edge_pct"),
            "zemax_distortion_pct_abs_max": distortion_metrics.get("abs_max_pct"),
            "zemax_distortion_unit": distortion_metrics.get("unit"),
            "zemax_distortion_source": distortion_metrics.get("source"),
            "zemax_mtf_definition": "polychromatic diffraction FFT MTF",
            "zemax_geometric_mtf_definition": (
                "primary-wavelength geometric MTF without diffraction-limit multiplication"
            ),
            "zemax_spot_definition": (
                "polychromatic Standard Spot radius referenced to centroid"
            ),
            "zemax_mtf50_center_tan_cy_mm": mtf_summary.get("mtf50_center_tangential"),
            "zemax_mtf50_center_sag_cy_mm": mtf_summary.get("mtf50_center_sagittal"),
            "zemax_mtf50_edge_tan_cy_mm": mtf_summary.get("mtf50_edge_tangential"),
            "zemax_mtf50_edge_sag_cy_mm": mtf_summary.get("mtf50_edge_sagittal"),
            "zemax_geometric_mtf50_center_tan_cy_mm": geometric_mtf_summary.get(
                "mtf50_center_tangential"
            ),
            "zemax_geometric_mtf50_center_sag_cy_mm": geometric_mtf_summary.get(
                "mtf50_center_sagittal"
            ),
            "zemax_geometric_mtf50_edge_tan_cy_mm": geometric_mtf_summary.get(
                "mtf50_edge_tangential"
            ),
            "zemax_geometric_mtf50_edge_sag_cy_mm": geometric_mtf_summary.get(
                "mtf50_edge_sagittal"
            ),
            "zemax_spot_rms_min_um": spot_value("rms_spot_radius_min", "um"),
            "zemax_spot_rms_edge_um": spot_value("rms_spot_radius_edge", "um"),
            "zemax_spot_rms_max_um": spot_value("rms_spot_radius_max", "um"),
            "zemax_spot_geo_min_um": spot_value("geo_spot_radius_min", "um"),
            "zemax_spot_geo_edge_um": spot_value("geo_spot_radius_edge", "um"),
            "zemax_spot_geo_max_um": spot_value("geo_spot_radius_max", "um"),
            "zemax_spot_rms_min_mm": spot_value("rms_spot_radius_min", "mm"),
            "zemax_spot_rms_edge_mm": spot_value("rms_spot_radius_edge", "mm"),
            "zemax_spot_rms_max_mm": spot_value("rms_spot_radius_max", "mm"),
            "zemax_spot_geo_min_mm": spot_value("geo_spot_radius_min", "mm"),
            "zemax_spot_geo_edge_mm": spot_value("geo_spot_radius_edge", "mm"),
            "zemax_spot_geo_max_mm": spot_value("geo_spot_radius_max", "mm"),
            "zemax_report_file": zemax_report.get("report_file"),
            "zemax_figure_files": zemax_report.get("figure_files", []),
        }
    )


def _convert_spot_value(value: Any, *, source_unit: str, target_unit: str) -> float | None:
    number = _finite_float(value)
    if number is None:
        return None

    normalized_source = _normalize_length_unit(source_unit)
    normalized_target = _normalize_length_unit(target_unit)
    if normalized_source == normalized_target:
        return number
    if normalized_source == "um" and normalized_target == "mm":
        return number / 1000.0
    if normalized_source == "mm" and normalized_target == "um":
        return number * 1000.0
    return None


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalize_length_unit(unit: str) -> str:
    text = str(unit).strip().lower()
    if text in {"um", "micron", "microns", "micrometer", "micrometers"}:
        return "um"
    if text in {"mm", "millimeter", "millimeters"}:
        return "mm"
    return text


def _zemax_status(zemax_report: dict[str, Any]) -> str:
    status = str(zemax_report.get("status") or "").strip().lower()
    if status in {"complete", "unavailable", "failed", "skipped"}:
        return status
    return "complete" if zemax_report.get("ok") else "unavailable"


__all__ = ["AnalysisNode"]
