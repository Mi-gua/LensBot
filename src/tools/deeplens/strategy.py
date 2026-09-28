from __future__ import annotations

from typing import Any

from agent.tools import ToolContext, ToolResult
from tools.deeplens.artifacts import find_lens_artifacts, load_artifact_session
from tools.deeplens.curriculum import SESSIONS, quiet_engine_output


class DeepLensInspectCheckpointTool:
    name = "deeplens_inspect_checkpoint"
    description = "Inspect DeepLens session state, losses, iterations, and first-order drift."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "anyOf": [{"required": ["session_id"]}, {"required": ["result_dir"]}, {"required": ["lens_json"]}],
        "additionalProperties": False,
        "properties": {
            "session_id": {"type": "string", "minLength": 1, "description": "Live DeepLens session to inspect."},
            "result_dir": {"type": "string", "minLength": 1, "description": "Archived run directory containing engines/deeplens/session.json."},
            "lens_json": {"type": "string", "minLength": 1, "description": "Lens artifact used to locate its run directory."},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["session_id", "phase"],
        "additionalProperties": True,
        "properties": {
            "session_id": {"type": "string"},
            "phase": {"type": "string"},
            "efl_drift": {"type": ["number", "null"]},
            "fnum_drift": {"type": ["number", "null"]},
            "fov_drift": {"type": ["number", "null"]},
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "diagnostics",
        "pi": {
            "prompt_snippet": (
                "Inspect live or archived session diagnostics when session state can change the next decision. "
                "Use deeplens_analysis for optical metrics on exported lens artifacts."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_id = str(kwargs.get("session_id") or "")
        session = SESSIONS.get(session_id)
        if session is None:
            diagnostics = archived_diagnostics(ctx, kwargs)
            if isinstance(diagnostics, ToolResult):
                return diagnostics
            return ToolResult.success(
                _diagnostics_observation(diagnostics),
                diagnostics,
                metrics=_diagnostic_metrics(diagnostics),
                metadata={"session_id": diagnostics.get("session_id")},
            )

        diagnostics = session.inspect_checkpoint()
        return ToolResult.success(
            _diagnostics_observation(diagnostics),
            diagnostics,
            metrics=_diagnostic_metrics(diagnostics),
            metadata={"session_id": session_id},
        )


class DeepLensAdjustStrategyTool:
    name = "deeplens_adjust_strategy"
    description = "Reduce learning rate or roll back a live DeepLens optimization session."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["session_id", "action"],
        "additionalProperties": False,
        "properties": {
            "session_id": {"type": "string", "minLength": 1, "description": "Live DeepLens session to modify."},
            "action": {
                "type": "string",
                "description": "Allowed live-session adjustment.",
                "enum": [
                    "reduce_lr",
                    "rollback_to_best_checkpoint",
                ],
            },
            "reason": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["session_id", "phase", "strategy"],
        "additionalProperties": True,
        "properties": {
            "session_id": {"type": "string"},
            "phase": {"type": "string"},
            "strategy": {"type": "object"},
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "strategy",
        "pi": {
            "prompt_snippet": (
                "Use only bounded actions: reduce_lr or rollback_to_best_checkpoint. "
                "Choose reduce_lr for unstable loss behavior. Use rollback only for confirmed regression. "
                "This tool does not change structure, targets, constraints, or exported artifacts."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_id = str(kwargs.get("session_id") or "")
        session = SESSIONS.get(session_id)
        if session is None:
            return ToolResult.failure(
                "deeplens_adjust_strategy requires a live session; use deeplens_finetune with an artifact to create a new refinement run.",
                code="live_session_required",
                error={"code": "live_session_required", "session_id": session_id},
            )

        action = str(kwargs.get("action") or "")
        if action not in {
            "reduce_lr",
            "rollback_to_best_checkpoint",
        }:
            return ToolResult.failure(
                f"Unsupported DeepLens strategy action: {action}",
                code="unsupported_strategy_action",
                error={"code": "unsupported_strategy_action", "action": action},
            )

        strategy_request = {
            "action": action,
            "reason": str(kwargs.get("reason") or ""),
        }
        result_dir = getattr(session, "result_dir", ctx.project_root)
        try:
            with quiet_engine_output(result_dir):
                data = session.adjust_strategy(strategy_request)
        except ValueError as exc:
            return ToolResult.failure(str(exc), code="invalid_strategy_state")
        metrics = _strategy_metrics(data)
        data = {**data, **metrics}
        return ToolResult.success(
            (
                "DeepLens strategy updated: "
                f"action={action}, "
                f"applied={data.get('last_strategy', {}).get('applied')}, "
                f"lr_scale={metrics.get('strategy_lr_scale')}, "
                f"rollback_count={metrics.get('strategy_rollback_count')}."
            ),
            data,
            metrics=metrics,
            metadata={"session_id": session_id, "action": action},
        )


def _diagnostics_observation(diagnostics: dict[str, Any]) -> str:
    return (
        "DeepLens checkpoint diagnostics: "
        f"phase={diagnostics.get('phase')}, "
        f"efl_drift={diagnostics.get('efl_drift')}, "
        f"fnum_drift={diagnostics.get('fnum_drift')}, "
        f"fov_drift={diagnostics.get('fov_drift')}."
    )


def archived_diagnostics(ctx: ToolContext, kwargs: dict[str, Any]) -> dict[str, Any] | ToolResult:
    try:
        artifacts = find_lens_artifacts(
            ctx.project_root,
            result_dir=kwargs.get("result_dir"),
            lens_json=kwargs.get("lens_json"),
        )
    except ValueError as exc:
        return ToolResult.failure(
            "deeplens_inspect_checkpoint requires session_id, result_dir, or lens_json.",
            code="missing_checkpoint_source",
            error={"code": "missing_checkpoint_source", "message": str(exc)},
        )
    session_json = load_artifact_session(artifacts)
    if not session_json:
        return ToolResult.failure(
            "No archived DeepLens session diagnostics were found for this result.",
            code="missing_session_snapshot",
            error={"code": "missing_session_snapshot", "result_dir": artifacts.result_dir},
        )
    last_diagnostics = session_json.get("last_diagnostics")
    diagnostics = last_diagnostics if isinstance(last_diagnostics, dict) and last_diagnostics else session_json
    return {
        "session_id": session_json.get("session_id"),
        "phase": session_json.get("phase"),
        "curriculum_iter": session_json.get("curriculum_iter"),
        "fine_tune_iter": session_json.get("fine_tune_iter"),
        "analysis_json": artifacts.analysis_lens_json,
        **diagnostics,
    }


def _diagnostic_metrics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "efl_mm",
        "fnum",
        "fov_deg",
        "efl_drift",
        "fnum_drift",
        "fov_drift",
        "curriculum_iter",
        "fine_tune_iter",
    )
    return {key: diagnostics.get(key) for key in keys if key in diagnostics}


def _strategy_metrics(data: dict[str, Any]) -> dict[str, Any]:
    strategy = data.get("strategy") if isinstance(data.get("strategy"), dict) else {}
    return {
        "strategy_lr_scale": strategy.get("lr_scale"),
        "strategy_rollback_count": strategy.get("rollback_count"),
        "last_strategy_action": (data.get("last_strategy") or {}).get("action")
        if isinstance(data.get("last_strategy"), dict)
        else None,
    }


__all__ = [
    "DeepLensAdjustStrategyTool",
    "DeepLensInspectCheckpointTool",
]
