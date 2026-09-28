from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agent.tools import ToolArtifact, ToolContext, ToolResult
from engine.zemax.analysis import ZemaxAnalysisEngine
from runtime.artifacts import refresh_run_manifest


class ZemaxAnalysisTool:
    name = "zemax_analysis"
    description = "Run OpticStudio/Zemax analysis for a final.zmx file."
    category = "algorithm"
    scope = "analysis"
    input_schema = {
        "type": "object",
        "properties": {
            "final_zmx": {"type": "string"},
            "result_dir": {"type": "string"},
        },
    }
    output_schema = {"type": "object", "description": "Zemax analysis report."}
    metadata = {"engine": "zemax", "kind": "external_analysis"}

    def __init__(self) -> None:
        self.engine = ZemaxAnalysisEngine()

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        report = self._analyze(
            kwargs.get("final_zmx"),
            result_dir=kwargs.get("result_dir"),
            progress_cb=ctx.progress_cb,
        )
        status = _normalize_status(report)
        report.setdefault("status", status)
        report.setdefault("final_zmx", kwargs.get("final_zmx"))
        if report.get("ok"):
            report["status"] = "complete"
            refresh_run_manifest(kwargs.get("result_dir"))
            artifacts = [
                ToolArtifact(
                    item.get("path", ""),
                    kind="image",
                    source="zemax",
                    role=_figure_role(item.get("key")),
                    stage="analysis",
                    label=item.get("title", "Zemax figure"),
                    order=50,
                )
                for item in report.get("figures", [])
                if item.get("path")
            ]
            if report.get("report_file"):
                artifacts.append(
                    ToolArtifact(
                        report["report_file"],
                        kind="report",
                        source="zemax",
                        role="zemax_report",
                        stage="analysis",
                        label="Zemax report",
                        order=54,
                    )
                )
            return ToolResult.success("Zemax analysis completed.", report, artifacts=artifacts)
        observation = {
            "skipped": "Zemax analysis skipped.",
            "failed": "Zemax analysis failed.",
            "unavailable": "Zemax analysis unavailable.",
        }.get(status, "Zemax analysis unavailable.")
        code = {
            "skipped": "zemax_skipped",
            "failed": "zemax_failed",
            "unavailable": "zemax_unavailable",
        }.get(status, "zemax_unavailable")
        return ToolResult.failure(
            observation,
            code=code,
            data=report,
            error={"code": code, "message": str(report.get("error") or observation)},
        )

    def _analyze(
        self,
        final_zmx: str | Path | None,
        *,
        result_dir: str | Path | None,
        progress_cb: Callable[[str], None] | None,
    ) -> dict[str, Any]:
        return self.engine.analyze(final_zmx, result_dir=result_dir, progress_cb=progress_cb)


def _figure_role(key: Any) -> str:
    return {
        "fft_mtf": "zemax_mtf",
        "distortion": "zemax_distortion",
        "spot_diagram": "zemax_spot_diagram",
    }.get(str(key or ""), "zemax_figure")


def _normalize_status(report: dict[str, Any]) -> str:
    status = str(report.get("status") or "").strip().lower()
    if status in {"complete", "unavailable", "failed", "skipped"}:
        return status
    if report.get("ok"):
        return "complete"
    if not report.get("final_zmx") and not report.get("lens_file"):
        return "skipped"
    return "unavailable"


__all__ = ["ZemaxAnalysisTool"]
