from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from agent.tools import ToolArtifact, ToolContext, ToolRegistry, ToolResult
from engine.deeplens.structure_seed import StructureSeedError, apply_structure_seed_adjustment
from runtime.result import ResultWorkspace
from tools.bash import PowerShellTool
from tools.deeplens.contract import finish_result
from tools.edit_file import EditFileTool
from tools.read_file import ReadFileTool
from tools.write_file import WriteFileTool


class FakeDeepLensToolServer:
    """Deterministic DeepLens-compatible tools for explicit fake tool mode."""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)
        self.sessions: dict[str, dict[str, Any]] = {}
        self.registry = ToolRegistry()
        self.registry.register_tool(ReadFileTool())
        self.registry.register_tool(WriteFileTool())
        self.registry.register_tool(EditFileTool())
        self.registry.register_tool(PowerShellTool())

    def dispatch(
        self,
        tool: str,
        arguments: dict[str, Any],
        state: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        context = context or {}
        if tool == "deeplens_curriculum":
            return self.deeplens_curriculum(arguments, state, context)
        if tool == "deeplens_adjust_structure":
            return self.deeplens_adjust_structure(arguments, state)
        if tool == "deeplens_analysis":
            return self.deeplens_analysis(arguments, state)
        if tool == "deeplens_finetune":
            return self.deeplens_finetune(arguments, state)
        if tool == "deeplens_inspect_checkpoint":
            return self.deeplens_inspect_checkpoint(arguments, state)
        if tool == "deeplens_adjust_strategy":
            return self.deeplens_adjust_strategy(arguments, state)
        if tool == "finish":
            return finish_result(state)
        if tool in self.registry.names():
            return self.registry.call(
                tool,
                ctx=ToolContext(project_root=self.project_root, agent_context=context),
                **arguments,
            )
        return ToolResult.failure(
            f"Unknown fake DeepLens tool: {tool}",
            code="unknown_tool",
            error={"code": "unknown_tool", "tool": tool},
        )

    def deeplens_adjust_structure(self, arguments: dict[str, Any], state: dict[str, Any]) -> ToolResult:
        params = arguments.get("params")
        if not isinstance(params, dict):
            params = state.get("params_override") if isinstance(state.get("params_override"), dict) else {}
        try:
            result = apply_structure_seed_adjustment({**arguments, "params": params})
        except StructureSeedError as exc:
            return ToolResult.failure(
                str(exc),
                code=exc.code,
                error={"code": exc.code},
                recoverable=True,
            )
        return ToolResult.success(
            (
                ("Fake DeepLens structure adjusted: " if result.get("changed", True) else "Fake DeepLens structure unchanged: ")
                +
                f"action={result['action']}, "
                f"groups={result['structure_summary']['structure_group_count']}, "
                f"surfaces={result['structure_summary']['structure_surface_count']}."
            ),
            result,
            state_patch={"params_override": result["params"]},
            metrics=result["structure_summary"],
            metadata={"action": result["action"]},
        )

    def deeplens_curriculum(
        self,
        arguments: dict[str, Any],
        state: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        context = context or {}
        run_id = str(context.get("run_id") or state.get("run_id") or "fake-run")
        session_id = f"fake-session-{run_id}"
        result_dir = self.project_root / "results" / run_id
        workspace = ResultWorkspace.from_result_dir(result_dir)
        curriculum_dir = workspace.deeplens_attempt_dir("curriculum", 1)
        curriculum_json = curriculum_dir / "curriculum.json"
        target = _target_from_arguments(arguments)
        curriculum_metrics = _fake_metrics(target, stage="curriculum")
        _write_fake_lens_json(curriculum_json, target, curriculum_metrics, stage="curriculum")
        _write_fake_lens_json(workspace.deeplens_live_dir / "current.json", target, curriculum_metrics, stage="curriculum")
        _write_fake_png_placeholder(curriculum_dir / "curriculum.png")
        _write_fake_png_placeholder(workspace.deeplens_live_dir / "current.png")
        _write_fake_session_json(result_dir, session_id, "running", target, curriculum_metrics)
        self.sessions[session_id] = {
            "session_id": session_id,
            "run_id": run_id,
            "result_dir": result_dir,
            "target": target,
            "strategy": {
                "lr_scale": 1.0,
                "focus_weight_scale": 1.0,
                "rollback_count": 0,
                "notes": [],
            },
            "curriculum_metrics": curriculum_metrics,
            "final_metrics": None,
        }
        return ToolResult.success(
            "Fake DeepLens curriculum completed.",
            state_patch={
                "phase": "running",
                "active_session_id": session_id,
                "active_result_dir": str(result_dir),
                "artifacts": {"curriculum_json": str(curriculum_json)},
            },
            metrics={"has_curriculum_json": True},
            artifacts=[
                ToolArtifact(
                    path=str(result_dir),
                    kind="directory",
                    source="deeplens",
                    role="run_result_dir",
                    stage="curriculum",
                )
            ],
        )

    def deeplens_analysis(self, arguments: dict[str, Any], state: dict[str, Any]) -> ToolResult:
        result_dir = arguments.get("result_dir") or state.get("active_result_dir")
        if not result_dir:
            return ToolResult.failure("Fake DeepLens analysis requires active_result_dir.", code="missing_result_dir")

        result_dir_path = Path(str(result_dir))
        workspace = ResultWorkspace.from_result_dir(result_dir_path)
        artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
        final_json = workspace.final_dir / "final.json"
        curriculum_json = workspace.deeplens_attempt_dir("curriculum", 1) / "curriculum.json"
        is_final = bool(artifacts.get("final_json") or final_json.exists())
        session = self._session_for_state(state)
        target = session.get("target") if session else _target_from_state(state)
        curriculum_metrics = (
            session.get("curriculum_metrics") if session and isinstance(session.get("curriculum_metrics"), dict) else {}
        )
        if is_final:
            metrics = _fake_metrics(target, stage="final", curriculum_metrics=curriculum_metrics)
            if session is not None:
                session["final_metrics"] = metrics
        else:
            metrics = _fake_metrics(target, stage="curriculum")
            if session is not None:
                session["curriculum_metrics"] = metrics
        analysis_json_path = (
            artifacts.get("final_json") or final_json
            if is_final
            else artifacts.get("curriculum_json") or curriculum_json
        )
        metrics.update(
            {
                "analysis_stage": "final" if is_final else "curriculum",
                "has_curriculum_json": bool(artifacts.get("curriculum_json") or curriculum_json.exists()),
                "has_final_json": is_final,
                "result_dir": str(result_dir_path),
                "analysis_json": str(Path(str(analysis_json_path))),
            }
        )
        _write_fake_session_json(
            result_dir_path,
            str(state.get("active_session_id") or (session or {}).get("session_id") or "fake-session"),
            "running",
            target,
            metrics,
            strategy=(session or {}).get("strategy") if session else None,
        )
        return ToolResult.success(
            f"Fake DeepLens {'final' if is_final else 'curriculum'} analysis completed.",
            state_patch={
                "phase": "running",
                "artifacts": {
                    "analysis_json": metrics["analysis_json"],
                },
            },
            metrics=metrics,
        )

    def deeplens_finetune(self, arguments: dict[str, Any], state: dict[str, Any]) -> ToolResult:
        session_id = str(arguments.get("session_id") or state.get("active_session_id") or "")
        session = self.sessions.get(session_id)
        if session is None:
            return ToolResult.failure(
                f"Unknown fake DeepLens session: {session_id}",
                code="unknown_session",
                error={"code": "unknown_session", "session_id": session_id},
            )

        result_dir = Path(str(state.get("active_result_dir") or session.get("result_dir") or self.project_root / "results" / "fake-run"))
        workspace = ResultWorkspace.from_result_dir(result_dir)
        final_json = workspace.final_dir / "final.json"
        final_zmx = workspace.final_dir / "final.zmx"
        final_metrics = _fake_metrics(session["target"], stage="final", curriculum_metrics=session.get("curriculum_metrics") or {})
        result_dir.mkdir(parents=True, exist_ok=True)
        _write_fake_lens_json(final_json, session["target"], final_metrics, stage="final")
        final_zmx.write_text("! Fake LensBot ZMX export for smoke testing\n", encoding="utf-8")
        _write_fake_png_placeholder(workspace.final_dir / "final.png")
        session["final_metrics"] = final_metrics
        _write_fake_session_json(result_dir, session_id, "running", session["target"], final_metrics, strategy=session["strategy"])
        return ToolResult.success(
            "Fake DeepLens fine-tune completed and final artifacts were exported.",
            state_patch={
                "phase": "running",
                "artifacts": {
                    "final_json": str(final_json),
                    "final_zmx": str(final_zmx),
                },
            },
            artifacts=[
                ToolArtifact(
                    path=str(final_json),
                    kind="lens_json",
                    source="deeplens",
                    role="deeplens_final_json",
                    stage="final",
                ),
                ToolArtifact(
                    path=str(final_zmx),
                    kind="lens_zmx",
                    source="deeplens",
                    role="zemax_lens_file",
                    stage="final",
                ),
            ],
        )

    def deeplens_inspect_checkpoint(self, arguments: dict[str, Any], state: dict[str, Any]) -> ToolResult:
        session_id = str(arguments.get("session_id") or state.get("active_session_id") or "")
        session = self.sessions.get(session_id)
        if session is None:
            return ToolResult.failure(
                f"Unknown fake DeepLens session: {session_id}",
                code="unknown_session",
                error={"code": "unknown_session", "session_id": session_id},
            )
        metrics = session.get("final_metrics") or session.get("curriculum_metrics") or _fake_metrics(session["target"], stage="curriculum")
        diagnostics = {
            "session_id": session_id,
            "phase": state.get("phase") or "running",
            "curriculum_iter": 301,
            "fine_tune_iter": 201 if session.get("final_metrics") else 0,
            "efl_mm": metrics.get("deeplens_efl_mm"),
            "fnum": metrics.get("deeplens_fnum"),
            "fov_deg": metrics.get("deeplens_fov_deg"),
            "efl_drift": metrics.get("efl_drift"),
            "fnum_drift": metrics.get("fnum_drift"),
            "fov_drift": metrics.get("fov_drift"),
            "last_losses": {
                "total_loss": 0.18 if session.get("final_metrics") else 0.42,
                "loss_rms": 0.12 if session.get("final_metrics") else 0.31,
            },
            "strategy": dict(session["strategy"]),
        }
        return ToolResult.success(
            "Fake DeepLens checkpoint diagnostics completed.",
            diagnostics,
            metrics={key: diagnostics[key] for key in ("efl_drift", "fnum_drift", "fov_drift", "efl_mm", "fnum", "fov_deg")},
        )

    def deeplens_adjust_strategy(self, arguments: dict[str, Any], state: dict[str, Any]) -> ToolResult:
        session_id = str(arguments.get("session_id") or state.get("active_session_id") or "")
        session = self.sessions.get(session_id)
        if session is None:
            return ToolResult.failure(
                f"Unknown fake DeepLens session: {session_id}",
                code="unknown_session",
                error={"code": "unknown_session", "session_id": session_id},
            )
        action = str(arguments.get("action") or "")
        strategy = session["strategy"]
        if action == "reduce_lr":
            strategy["lr_scale"] = max(0.1, float(strategy["lr_scale"]) * 0.5)
            strategy["notes"].append("Reduced learning rate scale.")
        elif action == "increase_first_order_lock":
            strategy["focus_weight_scale"] = min(5.0, float(strategy["focus_weight_scale"]) * 1.5)
            strategy["notes"].append("Increased first-order lock.")
        elif action == "rollback_to_best_checkpoint":
            strategy["rollback_count"] = int(strategy["rollback_count"]) + 1
            strategy["notes"].append("Rolled back to best fake checkpoint.")
        else:
            return ToolResult.failure(
                f"Unsupported fake DeepLens strategy action: {action}",
                code="unsupported_strategy_action",
                error={"code": "unsupported_strategy_action", "action": action},
            )
        data = {
            "session_id": session_id,
            "phase": state.get("phase") or "running",
            "strategy": dict(strategy),
            "last_strategy": {"action": action, "reason": str(arguments.get("reason") or "")},
            "strategy_lr_scale": strategy["lr_scale"],
            "strategy_focus_weight_scale": strategy["focus_weight_scale"],
            "strategy_rollback_count": strategy["rollback_count"],
            "last_strategy_action": action,
        }
        return ToolResult.success(
            f"Fake DeepLens strategy updated: action={action}.",
            data,
            metrics={
                "strategy_lr_scale": strategy["lr_scale"],
                "strategy_focus_weight_scale": strategy["focus_weight_scale"],
                "strategy_rollback_count": strategy["rollback_count"],
                "last_strategy_action": action,
            },
        )

    def _session_for_state(self, state: dict[str, Any]) -> dict[str, Any] | None:
        session_id = str(state.get("active_session_id") or "")
        return self.sessions.get(session_id)


def _target_from_arguments(arguments: dict[str, Any]) -> dict[str, float]:
    params = arguments.get("params") if isinstance(arguments.get("params"), dict) else {}
    return _target_from_mapping(params)


def _target_from_state(state: dict[str, Any]) -> dict[str, float]:
    target = state.get("target") if isinstance(state.get("target"), dict) else {}
    return _target_from_mapping(target)


def _target_from_mapping(value: dict[str, Any]) -> dict[str, float]:
    return {
        "foclen": _float_or(value.get("foclen"), 85.0),
        "fnum": _float_or(value.get("fnum"), 4.0),
        "fov": _float_or(value.get("fov"), 40.0),
        "bfl": _float_or(value.get("bfl"), 18.0),
        "thickness": _float_or(value.get("thickness"), 120.0),
    }


def _fake_metrics(
    target: dict[str, float],
    *,
    stage: str,
    curriculum_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final = stage == "final"
    efl = target["foclen"] * (1.012 if final else 1.08)
    fnum = target["fnum"] * (1.01 if final else 1.06)
    fov = target["fov"] * (0.995 if final else 0.96)
    rms = 12.4 if final else 20.1
    distortion = 0.8 if final else 1.7
    mtf = 38.0 if final else 24.0
    if final and os.getenv("LENSBOT_FAKE_DEEPLENS_REGRESSION") == "1":
        rms = 26.0
        distortion = 2.4
        mtf = 18.0
    metrics = {
        "deeplens_efl_mm": round(efl, 4),
        "deeplens_fnum": round(fnum, 4),
        "deeplens_fov_deg": round(fov, 4),
        "efl_drift": _drift(efl, target["foclen"]),
        "fnum_drift": _drift(fnum, target["fnum"]),
        "fov_drift": _drift(fov, target["fov"]),
        "rms_spot_um": rms,
        "spot_rms_um_edge": rms,
        "deeplens_rms_spot_um_edge": rms,
        "distortion_pct_abs_max": distortion,
        "deeplens_distortion_pct_abs_max": distortion,
        "mtf50_edge_tan_cy_mm": mtf,
        "deeplens_mtf50_edge_tan_cy_mm": mtf,
    }
    if final and curriculum_metrics:
        metrics["spot_rms_um_edge_delta_from_curriculum"] = round(
            rms - float(curriculum_metrics.get("spot_rms_um_edge", rms)),
            4,
        )
        metrics["rms_spot_um_delta_from_curriculum"] = round(
            rms - float(curriculum_metrics.get("rms_spot_um", rms)),
            4,
        )
        metrics["distortion_pct_abs_max_delta_from_curriculum"] = round(
            distortion - float(curriculum_metrics.get("distortion_pct_abs_max", distortion)),
            4,
        )
        metrics["mtf50_edge_tan_delta_from_curriculum"] = round(
            mtf - float(curriculum_metrics.get("mtf50_edge_tan_cy_mm", mtf)),
            4,
        )
    return metrics


def _write_fake_lens_json(path: Path, target: dict[str, float], metrics: dict[str, Any], *, stage: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": stage,
        "foclen": metrics["deeplens_efl_mm"],
        "fnum": metrics["deeplens_fnum"],
        "fov": metrics["deeplens_fov_deg"],
        "target": target,
        "surfaces": [
            {"type": "Spheric", "mat2": "N-BK7"},
            {"type": "Aperture"},
            {"type": "Aspheric", "mat2": "N-SF5"},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_fake_session_json(
    result_dir: Path,
    session_id: str,
    phase: str,
    target: dict[str, float],
    metrics: dict[str, Any],
    *,
    strategy: dict[str, Any] | None = None,
) -> None:
    workspace = ResultWorkspace.from_result_dir(result_dir)
    payload = {
        "session_id": session_id,
        "phase": phase,
        "params": {
            "foclen": target["foclen"],
            "fnum": target["fnum"],
            "fov": target["fov"],
            "bfl": target["bfl"],
            "thickness": target["thickness"],
        },
        "last_diagnostics": {
            "efl_drift": metrics.get("efl_drift"),
            "fnum_drift": metrics.get("fnum_drift"),
            "fov_drift": metrics.get("fov_drift"),
        },
        "strategy": strategy or {"lr_scale": 1.0, "focus_weight_scale": 1.0, "rollback_count": 0, "notes": []},
    }
    (workspace.deeplens_dir / "session.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_fake_png_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def _float_or(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _drift(value: float, target: float) -> float:
    if target == 0:
        return 0.0
    return round(abs(value - target) / abs(target), 6)


__all__ = ["FakeDeepLensToolServer", "finish_result"]
