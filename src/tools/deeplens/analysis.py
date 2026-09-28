from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

from agent.tools import ToolContext, ToolResult
from engine.deeplens.evaluation import analyze_deeplens_final
from runtime.design_contract import evaluate_design_contract
from tools.deeplens.artifacts import find_lens_artifacts


class DeepLensAnalysisTool:
    name = "deeplens_analysis"
    description = "Analyze a resolved DeepLens lens artifact and report optical metrics."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "anyOf": [{"required": ["result_dir"]}, {"required": ["lens_json"]}],
        "additionalProperties": False,
        "properties": {
            "result_dir": {"type": "string", "minLength": 1, "description": "Run directory containing curriculum, candidate, or final artifacts."},
            "lens_json": {"type": "string", "minLength": 1, "description": "Explicit lens JSON to analyze."},
        },
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
            "has_candidate_json": {"type": "boolean"},
            "has_final_json": {"type": "boolean"},
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "analysis",
        "pi": {
            "prompt_snippet": (
                "Compute DeepLens analysis for a trusted lens artifact or result directory. "
                "This produces evidence only; it does not optimize, compare, promote, or finish artifacts."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            artifacts = find_lens_artifacts(
                ctx.project_root,
                result_dir=kwargs.get("result_dir"),
                lens_json=kwargs.get("lens_json"),
            )
        except ValueError as exc:
            return ToolResult.failure(
                str(exc),
                code="missing_lens_artifact_input",
                error={"code": "missing_lens_artifact_input", "message": str(exc)},
            )

        analysis_json = Path(artifacts.analysis_lens_json)
        data: dict[str, Any] = {
            "result_dir": artifacts.result_dir,
            "analysis_json": artifacts.analysis_lens_json,
            "analysis_stage": artifacts.analysis_stage,
            "has_curriculum_json": artifacts.has_curriculum_json,
            "has_candidate_json": artifacts.has_candidate_json,
            "has_final_json": artifacts.has_final_json,
            "candidate_json": artifacts.candidate_json,
            "candidate_zmx": artifacts.candidate_zmx,
            "candidate_png": artifacts.candidate_png,
            "final_json": artifacts.final_json,
            "final_zmx": artifacts.final_zmx,
            "curriculum_json": artifacts.curriculum_json,
        }
        if not analysis_json.exists():
            return ToolResult.failure(
                "DeepLens analysis requires a candidate, final, or curriculum lens JSON.",
                code="missing_lens_json",
                data=data,
            )

        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                data.update(analyze_deeplens_final(analysis_json))
                data["contract_evaluation"] = evaluate_design_contract(
                    data, ctx.agent_context.get("design_contract")
                )
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
                f"has_candidate_json={str(data.get('has_candidate_json')).lower()}, "
                f"has_final_json={str(data.get('has_final_json')).lower()}, "
                f"result_dir={data.get('result_dir')}, "
                f"analysis_json={data.get('analysis_json')}."
            ),
            data,
        )


__all__ = ["DeepLensAnalysisTool"]
