from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.tools import ToolArtifact, ToolContext, ToolResult
from engine.deeplens.session import DeepLensOptimizationSession
from subagents.types import ADAPTIVE
from tools.deeplens.artifacts import find_lens_artifacts, load_artifact_session
from tools.deeplens.curriculum import OPTIMIZATION_STAGE_SCHEMA, SESSIONS, normalize_lens_params, quiet_engine_output
from tools.paths import resolve_under_root


FINE_TUNE_STAGE_KEYS = {"iterations", "test_per_iter", "num_ring", "num_arm", "spp"}


class DeepLensFinetuneTool:
    name = "deeplens_finetune"
    description = "Run DeepLens fine-tuning or refinement to export a candidate lens artifact."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "anyOf": [{"required": ["session_id"]}, {"required": ["result_dir"]}, {"required": ["lens_json"]}],
        "additionalProperties": False,
        "properties": {
            "session_id": {"type": "string", "minLength": 1, "description": "Live DeepLens session to continue and export."},
            "result_dir": {"type": "string", "minLength": 1, "description": "Existing run directory used to restore params and choose a lens artifact."},
            "lens_json": {"type": "string", "minLength": 1, "description": "Explicit lens JSON used as the refinement source."},
            "fine_tune": {
                **OPTIMIZATION_STAGE_SCHEMA,
                "description": "Optional fine-tune budget for this call; the tool runs that budget to candidate export.",
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": ["session_id", "result_dir", "candidate_json", "candidate_zmx"],
        "additionalProperties": True,
        "properties": {
            "session_id": {"type": "string"},
            "result_dir": {"type": "string"},
            "phase": {"type": "string"},
            "curriculum_json": {"type": "string"},
            "candidate_json": {"type": "string"},
            "candidate_zmx": {"type": "string"},
            "candidate_png": {"type": "string"},
            "iterations_requested": {"type": "integer"},
            "iterations_executed": {"type": "integer"},
            "source_lens": {"type": "string"},
            "optimizer_reinitialized": {"type": "boolean"},
            "lr_scale": {"type": "number"},
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "finetune",
        "pi": {
            "prompt_snippet": (
                "Run fine-tune or a new refinement from a trusted active session, result directory, or lens artifact. "
                "This call consumes the configured fine-tune budget and exports a candidate. "
                "Analyze the candidate before finish; use a smaller fine_tune override for incremental refinement."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_id = str(kwargs.get("session_id") or "")
        target = resolve_finetune_target(ctx, session_id=session_id, kwargs=kwargs)
        if isinstance(target, ToolResult):
            return target
        session, source_lens = target

        override_error = apply_fine_tune_override(session, kwargs.get("fine_tune"))
        if override_error is not None:
            return override_error

        try:
            with quiet_engine_output(session.result_dir):
                data = session.run_finetune(source_lens)
        except ValueError as exc:
            return ToolResult.failure(str(exc), code="invalid_finetune_state")
        resolved_session_id = str(data.get("session_id") or getattr(session, "session_id", None) or session_id)
        if resolved_session_id:
            SESSIONS[resolved_session_id] = session

        return ToolResult.success(
            (
                "DeepLens fine-tune completed and a candidate artifact was exported: "
                f"session_id={data.get('session_id')}, "
                f"phase={data.get('phase')}, "
                f"iterations_executed={data['iterations_executed']}, "
                f"result_dir={data.get('result_dir')}, "
                f"candidate_json={data.get('candidate_json')}, "
                f"candidate_zmx={data.get('candidate_zmx')}."
            ),
            data,
            artifacts=finetune_artifacts(data),
        )


def apply_fine_tune_override(session: Any, value: Any) -> ToolResult | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        return ToolResult.failure(
            "fine_tune override must be an object.",
            code="invalid_fine_tune",
            error={"code": "invalid_fine_tune", "received_type": type(value).__name__},
        )

    unknown = sorted(set(value) - FINE_TUNE_STAGE_KEYS)
    if unknown:
        return ToolResult.failure(
            f"Unsupported fine_tune override fields: {', '.join(unknown)}",
            code="invalid_fine_tune",
            error={"code": "invalid_fine_tune", "fields": unknown},
        )

    parsed: dict[str, int] = {}
    for key, raw in value.items():
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return ToolResult.failure(
                f"fine_tune.{key} must be a positive integer.",
                code="invalid_fine_tune",
                error={"code": "invalid_fine_tune", "field": key, "value": raw},
            )
        if number < 1:
            return ToolResult.failure(
                f"fine_tune.{key} must be a positive integer.",
                code="invalid_fine_tune",
                error={"code": "invalid_fine_tune", "field": key, "value": raw},
            )
        parsed[key] = number

    for key, number in parsed.items():
        setattr(session.params.fine_tune, key, number)
    if parsed:
        session.params.budget_sources["fine_tune"] = ADAPTIVE
    return None


def finetune_artifacts(data: dict[str, Any]) -> list[ToolArtifact]:
    artifacts = [
        ToolArtifact(str(data["result_dir"]), kind="directory", source="deeplens", role="run_result_dir", stage="candidate", label="DeepLens result directory", order=1),
    ]
    if data.get("curriculum_json"):
        artifacts.append(ToolArtifact(str(data["curriculum_json"]), kind="lens_json", source="deeplens", role="deeplens_curriculum_json", stage="curriculum", label="Curriculum lens JSON", order=30))
    if data.get("candidate_json"):
        artifacts.append(ToolArtifact(str(data["candidate_json"]), kind="lens_json", source="deeplens", role="deeplens_candidate_json", stage="candidate", label="Candidate lens JSON", order=40))
    if data.get("candidate_zmx"):
        artifacts.append(ToolArtifact(str(data["candidate_zmx"]), kind="lens_zmx", source="deeplens", role="deeplens_candidate_zmx", stage="candidate", label="Candidate Zemax lens", order=42))
    return artifacts


def resolve_finetune_target(
    ctx: ToolContext,
    *,
    session_id: str,
    kwargs: dict[str, Any],
) -> tuple[DeepLensOptimizationSession, Any | None] | ToolResult:
    session = SESSIONS.get(session_id) if session_id else None
    if session is not None:
        lens_json = kwargs.get("lens_json")
        if lens_json:
            source_lens = resolve_under_root(ctx.project_root, lens_json)
            if source_lens is None:
                return ToolResult.failure("Fine-tune source is outside the project root.", code="invalid_finetune_source")
            return session, source_lens
        return session, None

    try:
        artifacts = find_lens_artifacts(
            ctx.project_root,
            result_dir=kwargs.get("result_dir"),
            lens_json=kwargs.get("lens_json"),
        )
    except ValueError as exc:
        return ToolResult.failure(
            "deeplens_finetune requires session_id, result_dir, or lens_json.",
            code="missing_finetune_source",
            error={"code": "missing_finetune_source", "message": str(exc), "session_id": session_id},
        )

    session_json = load_artifact_session(artifacts)
    params = normalize_lens_params(ctx, session_json.get("params"))
    if params is None:
        params = normalize_lens_params(ctx, ctx.agent_context.get("execution_params"))
    if params is None:
        return ToolResult.failure(
            "deeplens_finetune could not restore trusted execution parameters for this artifact.",
            code="missing_params_snapshot",
            error={"code": "missing_params_snapshot", "result_dir": artifacts.result_dir},
        )

    session = DeepLensOptimizationSession(params=params, result_dir=Path(artifacts.result_dir))
    return session, Path(artifacts.analysis_lens_json)


__all__ = ["DeepLensFinetuneTool", "apply_fine_tune_override", "finetune_artifacts"]
