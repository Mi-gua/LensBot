from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from engine.deeplens.evaluation import analyze_deeplens_final
from agent.tools import ToolContext, ToolResult


class DeepLensEvaluationTool:
    """Tool-layer adapter around DeepLens optical metrics analysis."""

    name = "evaluate_lens"
    description = "Evaluate final optical metrics with the configured algorithm engine."
    category = "algorithm"
    metadata = {"engine": "deeplens", "kind": "evaluator"}

    @staticmethod
    def _prepare_process_output() -> None:
        if getattr(sys.stdout, "closed", False):
            sys.stdout = sys.__stdout__
        if getattr(sys.stderr, "closed", False):
            sys.stderr = sys.__stderr__
        root = logging.getLogger()
        for handler in list(root.handlers):
            stream = getattr(handler, "stream", None)
            nested_stream = getattr(stream, "_stream", None)
            if getattr(stream, "closed", False) or getattr(nested_stream, "closed", False):
                root.removeHandler(handler)

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        metrics = self.evaluate(str(kwargs["result_dir"]))
        return ToolResult(True, "Lens metric evaluation finished.", metrics)

    def evaluate(self, result_dir: str) -> dict:
        root = Path(result_dir)
        final_json = root / "final.json"
        curriculum_json = root / "curriculum.json"

        metrics: dict[str, object] = {
            "has_final_json": final_json.exists(),
            "has_curriculum_json": curriculum_json.exists(),
            "result_dir": str(root),
        }
        if not final_json.exists():
            return metrics

        try:
            self._prepare_process_output()
            metrics.update(analyze_deeplens_final(final_json))
        except Exception as exc:
            metrics["iqa_error"] = str(exc)
        return metrics
