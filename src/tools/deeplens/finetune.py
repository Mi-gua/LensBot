from __future__ import annotations

from typing import Any

from agent.tools import ToolArtifact, ToolContext, ToolResult
from tools.deeplens.curriculum import OPTIMIZATION_STAGE_SCHEMA, SESSIONS, quiet_engine_output


FINE_TUNE_STAGE_KEYS = {"iterations", "test_per_iter", "num_ring", "num_arm", "spp"}


class DeepLensFinetuneTool:
    name = "deeplens_finetune"
    description = "Run DeepLens fine-tuning for an existing curriculum session and export final artifacts."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["session_id"],
        "additionalProperties": False,
        "properties": {
            "session_id": {"type": "string", "minLength": 1},
            "fine_tune": {
                **OPTIMIZATION_STAGE_SCHEMA,
                "description": "Optional fine-tune stage override applied before fine-tuning starts.",
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": ["session_id", "result_dir", "final_json", "final_zmx"],
        "additionalProperties": True,
        "properties": {
            "session_id": {"type": "string"},
            "result_dir": {"type": "string"},
            "phase": {"type": "string"},
            "curriculum_json": {"type": "string"},
            "final_json": {"type": "string"},
            "final_zmx": {"type": "string"},
        },
    }
    metadata = {"engine": "deeplens", "kind": "finetune"}

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_id = str(kwargs.get("session_id") or "")
        session = SESSIONS.get(session_id)
        if session is None:
            return ToolResult.failure(
                f"Unknown DeepLens session: {session_id}",
                code="unknown_session",
                error={"code": "unknown_session", "session_id": session_id},
            )

        override_error = apply_fine_tune_override(session, kwargs.get("fine_tune"))
        if override_error is not None:
            return override_error

        with quiet_engine_output(session.result_dir):
            data = session.finalize()

        return ToolResult.success(
            (
                "DeepLens fine-tune completed and final artifacts were exported: "
                f"session_id={data.get('session_id')}, "
                f"phase={data.get('phase')}, "
                f"result_dir={data.get('result_dir')}, "
                f"final_json={data.get('final_json')}, "
                f"final_zmx={data.get('final_zmx')}."
            ),
            data,
            artifacts=[
                ToolArtifact(data["result_dir"], kind="directory", source="deeplens", role="run_result_dir", stage="final", label="DeepLens result directory", order=1),
                ToolArtifact(data["curriculum_json"], kind="lens_json", source="deeplens", role="deeplens_curriculum_json", stage="curriculum", label="Curriculum lens JSON", order=30),
                ToolArtifact(data["final_json"], kind="lens_json", source="deeplens", role="deeplens_final_json", stage="final", label="Final lens JSON", order=40),
                ToolArtifact(data["final_zmx"], kind="lens_zmx", source="deeplens", role="zemax_lens_file", stage="final", label="Final Zemax lens", order=42),
            ],
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

    phase = str(getattr(session, "phase", ""))
    if phase not in {"curriculum", "curriculum_complete"}:
        return ToolResult.failure(
            "fine_tune can only be overridden before fine-tuning starts.",
            code="fine_tune_already_started",
            error={"code": "fine_tune_already_started", "phase": phase},
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
    return None


__all__ = ["DeepLensFinetuneTool", "apply_fine_tune_override"]
