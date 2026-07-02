from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

from agent.tools import ToolContext, ToolResult
from engine.deeplens.evaluation import analyze_deeplens_final


class DeepLensAnalysisTool:
    name = "deeplens_analysis"
    description = "Analyze a DeepLens result directory after curriculum learning or final export."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["result_dir"],
        "additionalProperties": False,
        "properties": {"result_dir": {"type": "string", "minLength": 1}},
    }
    output_schema = {
        "type": "object",
        "required": ["result_dir", "analysis_json"],
        "additionalProperties": True,
        "properties": {
            "result_dir": {"type": "string"},
            "analysis_json": {"type": "string"},
            "analysis_stage": {"type": "string"},
            "has_curriculum_json": {"type": "boolean"},
            "has_final_json": {"type": "boolean"},
        },
    }
    metadata = {"engine": "deeplens", "kind": "analysis"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        result_dir = Path(str(kwargs.get("result_dir") or ""))
        if not result_dir.is_absolute():
            result_dir = ctx.project_root / result_dir

        final_json = result_dir / "final" / "final.json"
        curriculum_json = result_dir / "engines" / "deeplens" / "attempts" / "attempt-001-curriculum" / "curriculum.json"
        analysis_json = final_json if final_json.exists() else curriculum_json
        data: dict[str, Any] = {
            "result_dir": str(result_dir),
            "analysis_json": str(analysis_json),
            "analysis_stage": "final" if final_json.exists() else "curriculum",
            "has_curriculum_json": curriculum_json.exists(),
            "has_final_json": final_json.exists(),
        }
        if not analysis_json.exists():
            return ToolResult.failure(
                "DeepLens analysis requires final.json or curriculum.json.",
                code="missing_lens_json",
                data=data,
            )

        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                data.update(analyze_deeplens_final(analysis_json))
        except Exception as exc:
            return ToolResult.failure(
                f"DeepLens analysis failed: {exc}",
                code="analysis_failed",
                data=data,
                error={"code": "analysis_failed", "message": str(exc)},
            )
        return ToolResult.success(
            (
                "DeepLens analysis completed: "
                f"stage={data.get('analysis_stage')}, "
                f"has_curriculum_json={str(data.get('has_curriculum_json')).lower()}, "
                f"has_final_json={str(data.get('has_final_json')).lower()}, "
                f"result_dir={data.get('result_dir')}, "
                f"analysis_json={data.get('analysis_json')}."
            ),
            data,
        )


__all__ = ["DeepLensAnalysisTool"]
