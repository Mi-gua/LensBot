from __future__ import annotations

from typing import Any

from agent.tools import ToolContext, ToolResult
from tools.deeplens.curriculum import SESSIONS, quiet_engine_output


class DeepLensInspectCheckpointTool:
    name = "deeplens_inspect_checkpoint"
    description = "Inspect the active DeepLens session checkpoint and report first-order drift diagnostics."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["session_id"],
        "additionalProperties": False,
        "properties": {
            "session_id": {"type": "string", "minLength": 1},
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
                "Inspect checkpoint diagnostics when deciding whether to proceed, reduce learning rate, "
                "increase first-order lock, rollback, or stop with caveats."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_id = str(kwargs.get("session_id") or "")
        session = SESSIONS.get(session_id)
        if session is None:
            return ToolResult.failure(
                f"Unknown DeepLens session: {session_id}",
                code="unknown_session",
                error={"code": "unknown_session", "session_id": session_id},
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
    description = "Apply a bounded DeepLens strategy adjustment to the active optimization session."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["session_id", "action"],
        "additionalProperties": False,
        "properties": {
            "session_id": {"type": "string", "minLength": 1},
            "action": {
                "type": "string",
                "enum": [
                    "reduce_lr",
                    "increase_first_order_lock",
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
                "Use only bounded actions: reduce_lr, increase_first_order_lock, "
                "or rollback_to_best_checkpoint."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_id = str(kwargs.get("session_id") or "")
        session = SESSIONS.get(session_id)
        if session is None:
            return ToolResult.failure(
                f"Unknown DeepLens session: {session_id}",
                code="unknown_session",
                error={"code": "unknown_session", "session_id": session_id},
            )

        action = str(kwargs.get("action") or "")
        if action not in {
            "reduce_lr",
            "increase_first_order_lock",
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
        with quiet_engine_output(result_dir):
            data = session.adjust_strategy(strategy_request)
        metrics = _strategy_metrics(data)
        data = {**data, **metrics}
        return ToolResult.success(
            (
                "DeepLens strategy updated: "
                f"action={action}, "
                f"lr_scale={metrics.get('strategy_lr_scale')}, "
                f"first_order_lock={metrics.get('strategy_focus_weight_scale')}, "
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
        "strategy_focus_weight_scale": strategy.get("focus_weight_scale"),
        "strategy_rollback_count": strategy.get("rollback_count"),
        "last_strategy_action": (data.get("last_strategy") or {}).get("action")
        if isinstance(data.get("last_strategy"), dict)
        else None,
    }


__all__ = [
    "DeepLensAdjustStrategyTool",
    "DeepLensInspectCheckpointTool",
]
