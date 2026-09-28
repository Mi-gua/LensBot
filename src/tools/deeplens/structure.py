from __future__ import annotations

from typing import Any

from pathlib import Path

from agent.tools import ToolArtifact, ToolContext, ToolResult
from engine.deeplens.structure_seed import (
    StructureSeedError,
    apply_structure_seed_adjustment,
    dry_run_deeplens_create,
    write_adjusted_structure_preview,
)


class DeepLensAdjustStructureTool:
    name = "deeplens_adjust_structure"
    description = "Create validated structure params for the next DeepLens curriculum run."
    category = "algorithm"
    scope = "optimization"
    input_schema = {
        "type": "object",
        "required": ["params", "action"],
        "additionalProperties": False,
        "properties": {
            "params": {"type": "object", "description": "LensDesignParams object to adjust; the active session is not mutated."},
            "action": {
                "type": "string",
                "description": "Structure-only adjustment to apply before a future curriculum run.",
                "enum": [
                    "set_group_surface_count",
                    "convert_aspheric_to_spheric",
                ],
            },
            "group_index": {"type": "integer", "minimum": 0},
            "surface_count": {"type": "integer", "enum": [2, 3]},
            "surface_type": {"type": "string", "enum": ["Spheric", "Aspheric"]},
            "reason": {"type": "string"},
            "result_dir": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "required": ["params", "surf_list", "structure_summary"],
        "additionalProperties": True,
        "properties": {
            "params": {"type": "object"},
            "surf_list": {"type": "array"},
            "structure_summary": {"type": "object"},
        },
    }
    metadata = {
        "engine": "deeplens",
        "kind": "structure",
        "pi": {
            "prompt_snippet": (
                "Prepare conservative structure params for the next deeplens_curriculum call. "
                "This validates and returns params_override; it does not mutate the active session or optimize a lens."
            )
        },
    }

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        try:
            result = apply_structure_seed_adjustment(kwargs)
            dry_run_deeplens_create(ctx.project_root, result["params"])
        except StructureSeedError as exc:
            return ToolResult.failure(
                str(exc),
                code=exc.code,
                error={"code": exc.code},
                recoverable=True,
            )
        except Exception as exc:
            return ToolResult.failure(
                f"DeepLens rejected adjusted structure: {type(exc).__name__}: {exc}",
                code="deeplens_structure_dry_run_failed",
                error={"code": "deeplens_structure_dry_run_failed", "message": str(exc)},
                recoverable=True,
            )

        summary = result["structure_summary"]
        preview: dict[str, str] = {}
        preview_warning = ""
        result_dir = str(kwargs.get("result_dir") or "").strip()
        if result_dir:
            try:
                preview = write_adjusted_structure_preview(ctx.project_root, result["params"], result_dir)
                result.update(preview)
            except Exception as exc:
                preview_warning = f"{type(exc).__name__}: {exc}"

        artifacts = []
        if preview.get("result_dir"):
            artifacts.append(
                ToolArtifact(
                    path=preview["result_dir"],
                    kind="directory",
                    source="deeplens",
                    role="run_result_dir",
                    stage="starting",
                    label="DeepLens result directory",
                    order=1,
                )
            )
        for key, kind, role, label, order in (
            ("adjusted_structure_json", "lens_json", "deeplens_adjusted_structure_json", "Adjusted structure JSON", 12),
            ("adjusted_structure_image", "image", "deeplens_adjusted_structure_image", "Adjusted structure preview", 13),
        ):
            path = preview.get(key)
            if path and Path(path).exists():
                artifacts.append(
                    ToolArtifact(
                        path=path,
                        kind=kind,
                        source="deeplens",
                        role=role,
                        stage="starting",
                        label=label,
                        order=order,
                    )
                )

        return ToolResult.success(
            (
                ("DeepLens structure adjusted: " if result.get("changed", True) else "DeepLens structure unchanged: ")
                +
                f"action={result['action']}, "
                f"groups={summary['structure_group_count']}, "
                f"surfaces={summary['structure_surface_count']}, "
                f"aspheres={summary['structure_aspheric_count']}."
            ),
            result,
            state_patch={"params_override": result["params"]},
            metrics=summary,
            artifacts=artifacts,
            metadata={
                "action": result["action"],
                "reason": str(kwargs.get("reason") or ""),
                **({"preview_warning": preview_warning} if preview_warning else {}),
            },
        )


__all__ = ["DeepLensAdjustStructureTool"]
