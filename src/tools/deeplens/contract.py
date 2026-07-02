from __future__ import annotations

from typing import Any

from agent.tools import ToolResult


def finish_result(state: dict[str, Any]) -> ToolResult:
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    metrics = state.get("metrics") if isinstance(state.get("metrics"), dict) else {}
    missing = [name for name in ("final_json", "final_zmx", "analysis_json") if not artifacts.get(name)]
    if missing:
        return ToolResult.failure(
            f"Finish requires {', '.join(missing)}.",
            code="missing_final_artifacts",
            error={"code": "missing_final_artifacts", "missing": missing},
        )
    if metrics.get("analysis_stage") != "final" or metrics.get("has_final_json") is not True:
        return ToolResult.failure(
            "Finish requires final DeepLens metrics.",
            code="missing_final_metrics",
            error={"code": "missing_final_metrics"},
        )
    return ToolResult.success("Optimization finish validated.", state_patch={"phase": "finished"})


__all__ = ["finish_result"]
