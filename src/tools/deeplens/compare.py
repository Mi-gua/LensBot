from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from agent.tools import ToolContext, ToolResult
from engine.deeplens.evaluation import analyze_deeplens_final
from runtime.design_contract import evaluate_design_contract
from tools.paths import resolve_under_root


COMPARISON_FIELDS = (
    "deeplens_efl_mm",
    "deeplens_fov_deg",
    "deeplens_fnum",
    "deeplens_bfl_mm",
    "deeplens_ttl_mm",
    "deeplens_surface_count",
    "deeplens_aspheric_surface_count",
    "deeplens_min_surface_vertex_spacing_mm",
    "deeplens_spot_valid_fraction_min",
    "deeplens_spot_valid_pct_edge",
    "deeplens_rms_spot_um_center",
    "deeplens_rms_spot_um_edge",
    "deeplens_rms_spot_um_max",
    "deeplens_distortion_pct_edge",
    "deeplens_distortion_pct_abs_max",
    "deeplens_distortion_valid_fraction_min",
    "deeplens_mtf50_center_tan_cy_mm",
    "deeplens_mtf50_center_sag_cy_mm",
    "deeplens_mtf50_edge_tan_cy_mm",
    "deeplens_mtf50_edge_sag_cy_mm",
)


class DeepLensCompareCandidatesTool:
    name = "deeplens_compare_candidates"
    description = "Analyze two to eight explicit lens JSON artifacts with one evaluator and return an aligned metric matrix."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["candidates"],
        "additionalProperties": False,
        "properties": {
            "candidates": {
                "type": "array",
                "minItems": 2,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "required": ["candidate_id", "lens_json"],
                    "additionalProperties": False,
                    "properties": {
                        "candidate_id": {"type": "string", "minLength": 1},
                        "lens_json": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": ["comparison_fields", "candidates"],
        "additionalProperties": False,
        "properties": {
            "comparison_fields": {"type": "array", "items": {"type": "string"}},
            "evaluation_protocol": {"type": "string"},
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["candidate_id", "lens_json", "execution", "metrics", "contract_evaluation"],
                    "additionalProperties": False,
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "lens_json": {"type": "string"},
                        "execution": {"type": "object"},
                        "metrics": {"type": "object"},
                        "contract_evaluation": {"type": "object"},
                    },
                },
            },
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "candidate_comparison",
        "pi": {
            "prompt_snippet": (
                "Compare explicit shortlisted lens JSON artifacts under the same deterministic DeepLens evaluator. "
                "This returns aligned evidence and never chooses a winner or changes active state."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        entries = kwargs.get("candidates")
        if not isinstance(entries, list) or not 2 <= len(entries) <= 8:
            return ToolResult.failure("Candidate comparison requires two to eight entries.", code="invalid_candidate_list")

        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        resolved_entries: list[tuple[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                return ToolResult.failure("Each comparison entry must be an object.", code="invalid_candidate")
            candidate_id = str(entry.get("candidate_id") or "").strip()
            path = resolve_under_root(ctx.project_root, entry.get("lens_json"))
            if not candidate_id or candidate_id in seen_ids:
                return ToolResult.failure("Candidate ids must be non-empty and unique.", code="duplicate_candidate_id")
            if path is None or not path.is_file() or path.suffix.lower() != ".json":
                return ToolResult.failure(
                    f"Candidate {candidate_id} does not resolve to a lens JSON file under the project root.",
                    code="invalid_candidate_path",
                )
            resolved = str(path.resolve())
            if resolved in seen_paths:
                return ToolResult.failure("Comparison entries must reference distinct artifacts.", code="duplicate_candidate_path")
            seen_ids.add(candidate_id)
            seen_paths.add(resolved)
            resolved_entries.append((candidate_id, path))

        rows: list[dict[str, Any]] = []
        for candidate_id, path in resolved_entries:
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    metrics = analyze_deeplens_final(path)
            except Exception as exc:
                return ToolResult.failure(
                    f"Candidate {candidate_id} analysis failed: {exc}",
                    code="candidate_analysis_failed",
                    error={"code": "candidate_analysis_failed", "candidate_id": candidate_id, "message": str(exc)},
                )
            rows.append({
                "candidate_id": candidate_id,
                "lens_json": resolved,
                "execution": _execution_evidence(path, candidate_id),
                "metrics": {key: metrics.get(key) for key in COMPARISON_FIELDS},
                "contract_evaluation": evaluate_design_contract(
                    metrics, ctx.agent_context.get("design_contract")
                ),
            })

        data = {
            "comparison_fields": list(COMPARISON_FIELDS),
            "evaluation_protocol": "same LensBot deterministic DeepLens evaluator for every listed artifact",
            "candidates": rows,
        }
        return ToolResult.success(
            f"Compared {len(rows)} distinct candidates with one evaluation protocol; no winner was selected automatically.",
            data,
        )


def _execution_evidence(lens_json: Path, candidate_id: str) -> dict[str, Any]:
    evidence_path = lens_json.with_name("execution.json")
    base = {
        "status": "unavailable",
        "evidence_file": str(evidence_path.resolve()),
        "candidate_id": None,
        "optimizer_pass_id": None,
        "source_lens": None,
        "iterations_executed": None,
        "optimizer_reinitialized": None,
        "blockers": ["missing_execution_record"],
    }
    if not evidence_path.is_file():
        return base
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**base, "status": "invalid", "blockers": ["unreadable_execution_record"]}
    if not isinstance(payload, dict):
        return {**base, "status": "invalid", "blockers": ["invalid_execution_record"]}

    blockers: list[str] = []
    recorded_candidate = str(payload.get("candidate_id") or "")
    recorded_lens = str(payload.get("candidate_json") or "")
    optimizer_pass_id = str(payload.get("optimizer_pass_id") or "")
    source_lens = str(payload.get("source_lens") or "")
    iterations = payload.get("iterations_executed")
    reinitialized = payload.get("optimizer_reinitialized")
    if recorded_candidate != candidate_id:
        blockers.append("candidate_id_mismatch")
    try:
        same_lens = bool(recorded_lens) and Path(recorded_lens).resolve() == lens_json.resolve()
    except OSError:
        same_lens = False
    if not same_lens:
        blockers.append("candidate_artifact_mismatch")
    if not optimizer_pass_id:
        blockers.append("missing_optimizer_pass_id")
    if not source_lens or not Path(source_lens).is_file():
        blockers.append("missing_source_lens")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations <= 0:
        blockers.append("nonpositive_iterations")
    if reinitialized is not True:
        blockers.append("optimizer_not_reinitialized")
    return {
        "status": "verified" if not blockers else "invalid",
        "evidence_file": str(evidence_path.resolve()),
        "candidate_id": recorded_candidate or None,
        "optimizer_pass_id": optimizer_pass_id or None,
        "source_lens": source_lens or None,
        "iterations_executed": iterations,
        "optimizer_reinitialized": reinitialized,
        "blockers": blockers,
    }


__all__ = ["COMPARISON_FIELDS", "DeepLensCompareCandidatesTool"]
