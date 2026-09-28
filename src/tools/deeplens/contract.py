from __future__ import annotations

import shutil
import math
from pathlib import Path
from typing import Any

from agent.tools import ToolResult


def finish_result(state: dict[str, Any], verdict: Any) -> ToolResult:
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    metrics = state.get("metrics") if isinstance(state.get("metrics"), dict) else {}
    if not isinstance(verdict, dict) or verdict.get("status") not in {"pass", "fail", "uncertain"}:
        return ToolResult.failure("Finish requires a pass, fail or uncertain verdict.", code="invalid_verdict")
    if any(not isinstance(verdict.get(key), str) or not verdict[key].strip() for key in ("reason", "stop_reason")):
        return ToolResult.failure(
            "Finish requires an optical reason and a separate stop reason.",
            code="missing_stop_reason",
            error={"code": "missing_stop_reason"},
        )
    contract_evaluation = metrics.get("contract_evaluation") if isinstance(metrics.get("contract_evaluation"), dict) else {}
    requirements = contract_evaluation.get("requirements") or {}
    blockers = [
        key for key, row in requirements.items()
        if row.get("status") == "violated" and row.get("constraint_source") == "user_input"
    ]
    if verdict.get("status") == "pass" and blockers:
        detail = ", ".join(blockers)
        return ToolResult.failure(
            f"A pass verdict conflicts with unresolved contract requirements: {detail}.",
            code="contract_verdict_conflict",
            error={"code": "contract_verdict_conflict", "pass_blockers": blockers},
        )

    unresolved_evidence = _unresolved_verdict_evidence(verdict, metrics, artifacts)
    if unresolved_evidence:
        return ToolResult.failure(
            f"Verdict evidence keys do not resolve in current state: {', '.join(unresolved_evidence)}.",
            code="invalid_verdict_evidence",
            error={"code": "invalid_verdict_evidence", "unresolved": unresolved_evidence},
        )

    if (
        artifacts.get("candidate_json")
        and artifacts.get("candidate_zmx")
        and _same_path(artifacts.get("analysis_json"), artifacts.get("candidate_json"))
    ):
        result = _finish_candidate(state, artifacts, metrics)
    elif artifacts.get("final_json") or artifacts.get("final_zmx"):
        result = _finish_existing_final(artifacts, metrics)
    else:
        result = _finish_candidate(state, artifacts, metrics)
    if result.ok:
        result.state_patch["final_verdict"] = {
            "status": verdict["status"],
            "reason": verdict["reason"].strip(),
            "stop_reason": verdict["stop_reason"].strip(),
            "evidence": list(dict.fromkeys(verdict["evidence"])),
            "source": "optimization_agent",
        }
    return result


def _finish_candidate(state: dict[str, Any], artifacts: dict[str, Any], metrics: dict[str, Any]) -> ToolResult:
    missing = _missing_artifact_files(artifacts, ("candidate_json", "candidate_zmx", "analysis_json"))
    if missing:
        return ToolResult.failure(
            f"Finish requires {', '.join(missing)}.",
            code="missing_finish_artifacts",
            error={"code": "missing_finish_artifacts", "missing": missing},
        )
    if str(metrics.get("analysis_stage") or "") not in {"candidate", "final"}:
        return ToolResult.failure(
            "Finish requires analyzed candidate or final DeepLens metrics.",
            code="missing_finish_metrics",
            error={"code": "missing_finish_metrics"},
        )
    if not _same_path(artifacts.get("analysis_json"), artifacts.get("candidate_json")):
        return ToolResult.failure(
            "Finish requires analysis evidence for the chosen candidate artifact.",
            code="analysis_artifact_mismatch",
            error={"code": "analysis_artifact_mismatch"},
        )
    try:
        final_artifacts = _promote_candidate_to_final(state, artifacts)
    except OSError as exc:
        return ToolResult.failure(
            f"Finish could not promote candidate artifacts: {exc}",
            code="final_promotion_failed",
            error={"code": "final_promotion_failed", "message": str(exc)},
        )
    return ToolResult.success(
        "Optimization finish validated and candidate promoted to final artifacts.",
        state_patch={
            "phase": "finished",
            "artifacts": final_artifacts,
            "metrics": {
                "analysis_stage": "final",
                "has_final_json": True,
                "has_candidate_json": True,
            },
        },
    )


def _finish_existing_final(artifacts: dict[str, Any], metrics: dict[str, Any]) -> ToolResult:
    missing = _missing_artifact_files(artifacts, ("final_json", "final_zmx", "analysis_json"))
    if missing:
        return ToolResult.failure(
            f"Finish requires {', '.join(missing)}.",
            code="missing_finish_artifacts",
            error={"code": "missing_finish_artifacts", "missing": missing},
        )
    if metrics.get("analysis_stage") != "final" or metrics.get("has_final_json") is not True:
        return ToolResult.failure(
            "Finish requires final DeepLens metrics.",
            code="missing_finish_metrics",
            error={"code": "missing_finish_metrics"},
        )
    if not _same_path(artifacts.get("analysis_json"), artifacts.get("final_json")):
        return ToolResult.failure(
            "Finish requires analysis evidence for the chosen final artifact.",
            code="analysis_artifact_mismatch",
            error={"code": "analysis_artifact_mismatch"},
        )
    return ToolResult.success("Optimization finish validated.", state_patch={"phase": "finished"})


def _promote_candidate_to_final(state: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, str]:
    active_result_dir = str(state.get("active_result_dir") or "").strip()
    result_dir = Path(active_result_dir).resolve() if active_result_dir else Path(str(artifacts["candidate_json"])).resolve().parents[2]
    final_dir = result_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_json = final_dir / "final.json"
    final_zmx = final_dir / "final.zmx"
    final_png = final_dir / "final.png"
    shutil.copy2(Path(str(artifacts["candidate_json"])), final_json)
    shutil.copy2(Path(str(artifacts["candidate_zmx"])), final_zmx)
    candidate_png = artifacts.get("candidate_png")
    final_png_value = ""
    if candidate_png and Path(str(candidate_png)).exists():
        shutil.copy2(Path(str(candidate_png)), final_png)
        final_png_value = str(final_png)
    analysis_json = artifacts.get("analysis_json")
    promoted = {
        "final_json": str(final_json),
        "final_zmx": str(final_zmx),
        "analysis_json": str(analysis_json),
    }
    if final_png_value:
        promoted["final_png"] = final_png_value
    return promoted


def _same_path(left: Any, right: Any) -> bool:
    if not left or not right:
        return False
    return Path(str(left)).resolve() == Path(str(right)).resolve()


def _missing_artifact_files(artifacts: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for name in names:
        value = artifacts.get(name)
        if not value or not Path(str(value)).is_file():
            missing.append(name)
    return missing


def _unresolved_verdict_evidence(
    verdict: dict[str, Any],
    metrics: dict[str, Any],
    artifacts: dict[str, Any],
) -> list[str]:
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return ["<missing>"]
    return [str(key) for key in evidence if not isinstance(key, str) or not _resolves_evidence_key(key, metrics, artifacts)]


def _resolves_evidence_key(key: str, metrics: dict[str, Any], artifacts: dict[str, Any]) -> bool:
    path = [segment for segment in key.split(".") if segment]
    if not path:
        return False
    if path[0] == "metrics":
        return _has_evidence_at_path(metrics, path[1:])
    if path[0] == "artifacts":
        return _has_evidence_at_path(artifacts, path[1:])
    if path[0] == "contract_evaluation":
        contract = metrics.get("contract_evaluation")
        return _has_evidence_at_path(contract if isinstance(contract, dict) else {}, path[1:])
    return _has_evidence_at_path(metrics, path) or _has_evidence_at_path(artifacts, path)


def _has_evidence_at_path(root: Any, path: list[str]) -> bool:
    value = root
    for segment in path:
        if not isinstance(value, dict) or segment not in value:
            return False
        value = value[segment]
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


__all__ = ["finish_result"]
