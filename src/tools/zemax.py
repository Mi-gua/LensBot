from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from engine.zemax.analysis import ZemaxAnalysisEngine
from agent.tools import ToolContext, ToolResult


class ZemaxAnalysisTool:
    """Thin tool adapter for the Zemax analysis engine."""

    name = "analyze_zemax"
    description = "Run OpticStudio/Zemax analysis for final.zmx."
    category = "algorithm"
    metadata = {"engine": "zemax", "kind": "external_evaluator"}

    def __init__(self) -> None:
        self.engine = ZemaxAnalysisEngine()

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        report = self.analyze(
            kwargs.get("final_zmx"),
            result_dir=kwargs.get("result_dir"),
            progress_cb=ctx.progress_cb,
        )
        return ToolResult(bool(report.get("ok")), "Zemax analysis finished.", report)

    def analyze(
        self,
        final_zmx: str | Path | None,
        result_dir: str | Path | None = None,
        progress_cb: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        return self.engine.analyze(final_zmx, result_dir=result_dir, progress_cb=progress_cb)
