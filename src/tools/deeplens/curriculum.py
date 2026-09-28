from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.tools import ToolArtifact, ToolContext, ToolResult
from engine.deeplens.session import DeepLensOptimizationSession
from runtime.result import ResultWorkspace
from runtime.result import safe_run_id
from subagents.types import LensDesignParams, load_default_params, params_from_public_dict


SESSIONS: dict[str, DeepLensOptimizationSession] = {}


OPTIMIZATION_STAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "iterations": {"type": "integer", "minimum": 1},
        "test_per_iter": {"type": "integer", "minimum": 1},
        "num_ring": {"type": "integer", "minimum": 1},
        "num_arm": {"type": "integer", "minimum": 1},
        "spp": {"type": "integer", "minimum": 1},
    },
}


LENS_PARAMS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "exp_name": {"type": "string"},
        "seed": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "lr_scale": {
            "type": "number",
            "minimum": 0.1,
            "maximum": 10.0,
            "description": "Initial multiplier applied to the canonical DeepLens learning rates.",
        },
        "foclen": {
            "type": "number",
            "description": "Target effective focal length in millimeters.",
        },
        "fov": {
            "type": "number",
            "description": "Target diagonal full field of view in degrees.",
        },
        "fnum": {
            "type": "number",
            "description": "Target working F-number.",
        },
        "bfl": {
            "type": "number",
            "description": "Initial back focal length used to construct the starting geometry.",
        },
        "thickness": {
            "type": "number",
            "description": "Initial first-surface-to-sensor total track used to construct the starting geometry.",
        },
        "surf_list": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "imgh": {
            "type": "number",
            "description": "Sensor half-diagonal in millimeters, retained for evaluation; initialization uses foclen and fov.",
        },
        "curriculum": OPTIMIZATION_STAGE_SCHEMA,
        "fine_tune": OPTIMIZATION_STAGE_SCHEMA,
        "_meta": {
            "type": "object",
            "description": "Runtime-owned provenance and constraint metadata; agent proposals are ignored.",
        },
    },
}


class DeepLensCurriculumTool:
    name = "deeplens_curriculum"
    description = "Start a new DeepLens session and run curriculum optimization for one lens candidate."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["params"],
        "additionalProperties": False,
        "properties": {
            "seed_candidate_id": {
                "type": "string",
                "description": "Choose a supplied initial_structures candidate. Its surf_list is used for this new session; omit for a custom structure.",
            },
            "params": {
                **LENS_PARAMS_SCHEMA,
                "description": "Runnable LensDesignParams for a new session. Stage settings are starting guidance and may be overridden by the corresponding call.",
            },
        },
    }
    output_schema = {
        "type": "object",
        "required": ["session_id", "result_dir", "phase"],
        "additionalProperties": True,
        "properties": {
            "session_id": {"type": "string"},
            "result_dir": {"type": "string"},
            "phase": {"type": "string"},
            "curriculum_json": {"type": "string"},
            "curriculum_iter": {"type": "integer"},
            "curriculum_total": {"type": "integer"},
            "iterations_requested": {"type": "integer"},
            "iterations_executed": {"type": "integer"},
            "source_lens": {"type": "string"},
            "optimizer_reinitialized": {"type": "boolean"},
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "curriculum",
        "pi": {
            "prompt_snippet": (
                "Start or restart DeepLens curriculum optimization from trusted LensDesignParams. "
                "Use it to create a coarse viable baseline or to test a justified params_override. "
                "This creates a new session/result path; use deeplens_finetune to continue from the resulting session or artifact."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        params = normalize_lens_params(ctx, kwargs.get("params"))
        if params is None:
            return ToolResult.failure(
                "Expected params as LensDesignParams or JSON object.",
                code="invalid_params",
                error={"code": "invalid_params", "received_type": type(kwargs.get("params")).__name__},
            )

        seed_id = kwargs.get("seed_candidate_id")
        if seed_id:
            candidate = next(
                (item for item in ctx.agent_context.get("initial_structures", []) if item.get("candidate_id") == seed_id),
                None,
            )
            if candidate is None:
                return ToolResult.failure(f"Unknown seed candidate: {seed_id}", code="unknown_seed")
            params.surf_list = candidate["params"]["surf_list"]
        result_dir = result_dir_for_run(ctx.project_root, ctx.agent_context.get("run_id"))
        session = DeepLensOptimizationSession(
            params=params,
            result_dir=result_dir,
            progress_cb=ctx.progress_cb,
            artifact_cb=ctx.artifact_cb,
        )
        with quiet_engine_output(result_dir):
            data = session.start()
            total = int(data.get("curriculum_total") or params.curriculum.iterations)
            before = int(data.get("curriculum_iter") or 0)
            data = session.run_curriculum_chunk(total)
        data.update({
            "seed_candidate_id": seed_id,
            "iterations_requested": total,
            "iterations_executed": int(data.get("curriculum_iter") or 0) - before,
            "source_lens": "generated_starting_point",
            "optimizer_reinitialized": True,
        })

        SESSIONS[session.session_id] = session
        return ToolResult.success(
            curriculum_observation(data),
            data,
            artifacts=[
                ToolArtifact(
                    path=data["result_dir"],
                    kind="directory",
                    source="deeplens",
                    role="run_result_dir",
                    stage="curriculum",
                    label="DeepLens result directory",
                    order=1,
                )
            ],
        )

def curriculum_observation(data: dict[str, Any]) -> str:
    curriculum_json = data.get("curriculum_json") or ""
    has_curriculum_json = bool(curriculum_json and Path(str(curriculum_json)).exists())
    return (
        "DeepLens curriculum completed: "
        f"session_id={data.get('session_id')}, "
        f"phase={data.get('phase')}, "
        f"curriculum_iter={data.get('curriculum_iter')}/{data.get('curriculum_total')}, "
        f"iterations_executed={data.get('iterations_executed')}, "
        f"result_dir={data.get('result_dir')}, "
        f"curriculum_json={curriculum_json or 'not_ready'}, "
        f"has_curriculum_json={str(has_curriculum_json).lower()}."
    )


def normalize_lens_params(ctx: ToolContext, value: Any) -> LensDesignParams | None:
    if isinstance(value, LensDesignParams):
        return value
    if isinstance(value, dict):
        try:
            defaults = load_default_params(ctx.project_root)
            return params_from_public_dict(value, defaults)
        except Exception:
            return None
    return None


def new_result_dir(project_root: Path) -> Path:
    root = project_root / "results"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = root / stamp
    index = 2
    while path.exists():
        path = root / f"{stamp}-{index}"
        index += 1
    return path


def result_dir_for_run(project_root: Path, run_id: Any) -> Path:
    if not str(run_id or "").strip():
        return new_result_dir(project_root)
    root = project_root / "results"
    root.mkdir(parents=True, exist_ok=True)
    return root / safe_run_id(run_id)


@contextlib.contextmanager
def quiet_engine_output(result_dir: Path):
    result_dir.mkdir(parents=True, exist_ok=True)
    log_path = ResultWorkspace.from_result_dir(result_dir).deeplens_dir / "deeplens.log"
    root = logging.getLogger()
    old_level = root.level
    with log_path.open("a", encoding="utf-8", buffering=1) as sink:
        try:
            root.setLevel(max(old_level, logging.ERROR))
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
        finally:
            root.setLevel(old_level)


__all__ = [
    "DeepLensCurriculumTool",
    "SESSIONS",
    "curriculum_observation",
    "normalize_lens_params",
    "quiet_engine_output",
    "result_dir_for_run",
]
