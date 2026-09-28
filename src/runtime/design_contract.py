from __future__ import annotations

import math
from typing import Any


MEASURED_METRICS = {
    "foclen": "deeplens_efl_mm",
    "imgh": "deeplens_imgh_mm",
    "fov": "deeplens_fov_deg",
    "fnum": "deeplens_fnum",
    "bfl": "deeplens_bfl_mm",
    "thickness": "deeplens_ttl_mm",
}


def evaluate_design_contract(metrics: dict[str, Any], contract: dict[str, Any] | None) -> dict[str, Any]:
    """Compare measured values with stated tolerances without inventing defaults."""
    contract = contract if isinstance(contract, dict) else {}
    requirements: list[tuple[str, dict[str, Any], str]] = []
    for key, spec in _objects(contract.get("optical_targets")):
        requirements.append((key, spec, "optical_target"))
    for key, spec in _objects(contract.get("packaging_constraints")):
        requirements.append((key, spec, "packaging_constraint"))

    rows: dict[str, dict[str, Any]] = {}
    pass_blockers: list[str] = []
    packaging_constraint_blockers: list[str] = []
    violated_requirements: list[str] = []
    uncertain_requirements: list[str] = []
    for key, spec, role in requirements:
        metric_key = MEASURED_METRICS.get(key)
        measured = _number(metrics.get(metric_key)) if metric_key else None
        target = _number(spec.get("value"))
        tolerance = _number(spec.get("tolerance"))
        relation = str(spec.get("relation") or "exact").lower()
        if relation not in {"exact", "minimum", "maximum"}:
            relation = "exact"
        absolute_error = abs(measured - target) if measured is not None and target is not None else None
        relative_error = absolute_error / abs(target) if absolute_error is not None and target not in (None, 0.0) else None
        if measured is None or target is None:
            status = "missing_measurement"
            margin = None
        elif relation == "exact":
            margin = None if tolerance is None else tolerance - absolute_error
            status = "unknown_tolerance" if tolerance is None else ("satisfied" if margin >= 0 else "violated")
        elif relation == "minimum":
            boundary = target - (tolerance or 0.0)
            margin = measured - boundary
            status = "satisfied" if margin >= 0 else "violated"
        else:
            boundary = target + (tolerance or 0.0)
            margin = boundary - measured
            status = "satisfied" if margin >= 0 else "violated"
        if status != "satisfied":
            pass_blockers.append(key)
        if role == "packaging_constraint" and status != "satisfied":
            packaging_constraint_blockers.append(key)
        if status == "violated":
            violated_requirements.append(key)
        elif status in {"missing_measurement", "unknown_tolerance"}:
            uncertain_requirements.append(key)
        rows[key] = {
            "role": role,
            "source": spec.get("source"),
            "constraint_source": spec.get("constraint_source"),
            "constraint_source": spec.get("constraint_source"),
            "target": target,
            "measured": measured,
            "metric_key": metric_key,
            "relation": relation,
            "absolute_error": absolute_error,
            "relative_error": relative_error,
            "tolerance": tolerance,
            "margin": margin,
            "status": status,
        }
    return {
        "requirements": rows,
        "pass_blockers": pass_blockers,
        "packaging_constraint_blockers": packaging_constraint_blockers,
        "violated_requirements": violated_requirements,
        "uncertain_requirements": uncertain_requirements,
        "packaging_constraints_satisfied": not packaging_constraint_blockers,
        "pass_eligible": not pass_blockers,
        "policy": (
            "Exact targets need a stated tolerance. Minimum and maximum relations "
            "define their own boundary; an optional tolerance is an explicit allowance."
        ),
    }


def _objects(value: Any):
    if not isinstance(value, dict):
        return []
    return [(str(key), spec) for key, spec in value.items() if isinstance(spec, dict)]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


__all__ = ["MEASURED_METRICS", "evaluate_design_contract"]
