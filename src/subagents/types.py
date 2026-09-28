from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RECOMMENDED_OPTIMIZATION_REVIEW_TURNS = 50
# Backward-compatible name. This value is guidance unless max_turns_is_limit is true.
DEFAULT_OPTIMIZATION_MAX_TURNS = RECOMMENDED_OPTIMIZATION_REVIEW_TURNS

SUGGESTED_DEFAULT = "suggested_default"
USER_INPUT = "user_input"
ADAPTIVE = "adaptive"
DERIVED = "derived"
CONSTRAINT_RELATIONS = {"exact", "minimum", "maximum"}
CONSTRAINABLE_FIELDS = {"foclen", "imgh", "fov", "fnum", "bfl", "thickness"}


@dataclass
class DesignConstraint:
    relation: str = "exact"
    tolerance: float | None = None
    source: str = USER_INPUT


@dataclass
class CurriculumParams:
    iterations: int = 2000
    test_per_iter: int = 50
    num_ring: int = 16
    num_arm: int = 4
    spp: int = 512


@dataclass
class FineTuneParams:
    iterations: int = 5000
    test_per_iter: int = 100
    num_ring: int = 32
    num_arm: int = 8
    spp: int = 512


@dataclass
class LensDesignParams:
    """Lens input: optical targets plus DeepLens initialization geometry.

    ``foclen``, ``fov``, and ``fnum`` are optical targets. ``bfl`` and
    ``thickness`` construct the starting lens geometry.
    """

    exp_name: str
    seed: int | None
    foclen: float
    imgh: float
    fov: float
    fnum: float
    bfl: float
    thickness: float
    surf_list: list[list[str]]
    lr_scale: float = 1.0
    curriculum: CurriculumParams = field(default_factory=CurriculumParams)
    fine_tune: FineTuneParams = field(default_factory=FineTuneParams)
    parameter_sources: dict[str, str] = field(default_factory=dict)
    constraints: dict[str, DesignConstraint] = field(default_factory=dict)
    budget_sources: dict[str, str] = field(default_factory=dict)


@dataclass
class SeedCandidate:
    candidate_id: str
    case_id: str
    title: str
    category: str
    path: str | None = None
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    params: LensDesignParams | None = None
    applied: bool = False
    inspected: bool = False


DEFAULT_CONFIG: dict[str, Any] = {
    "EXP_NAME": "Auto lens design",
    "seed": None,
    "foclen": 50.0,
    "fov": 43.0,
    "fnum": 3.0,
    "bfl": 18.0,
    "thickness": 75.0,
    "lr_scale": 1.0,
    "surf_list": [
        ["Spheric", "Spheric"],
        ["Spheric", "Spheric"],
        ["Spheric", "Spheric", "Spheric"],
        ["Aperture"],
        ["Spheric", "Spheric", "Spheric"],
        ["Spheric", "Aspheric"],
        ["Spheric", "Aspheric"],
    ],
    "curriculum": {
        "iterations": 2000,
        "test_per_iter": 50,
        "num_ring": 16,
        "num_arm": 4,
        "spp": 512,
    },
    "fine_tune": {
        "iterations": 5000,
        "test_per_iter": 100,
        "num_ring": 32,
        "num_arm": 8,
        "spp": 512,
    },
}


def load_default_config(project_root: Path | None = None) -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def load_default_params(project_root: Path | None = None) -> LensDesignParams:
    cfg = load_default_config(project_root)
    return LensDesignParams(
        exp_name=str(cfg["EXP_NAME"]),
        seed=None if cfg.get("seed") is None else int(cfg["seed"]),
        foclen=float(cfg["foclen"]),
        imgh=_image_height(float(cfg["foclen"]), float(cfg["fov"])),
        fov=float(cfg["fov"]),
        fnum=float(cfg["fnum"]),
        bfl=float(cfg["bfl"]),
        thickness=float(cfg["thickness"]),
        surf_list=cfg["surf_list"],
        lr_scale=float(cfg["lr_scale"]),
        curriculum=CurriculumParams(
            iterations=int(cfg["curriculum"]["iterations"]),
            test_per_iter=int(cfg["curriculum"]["test_per_iter"]),
            num_ring=int(cfg["curriculum"]["num_ring"]),
            num_arm=int(cfg["curriculum"]["num_arm"]),
            spp=int(cfg["curriculum"]["spp"]),
        ),
        fine_tune=FineTuneParams(
            iterations=int(cfg["fine_tune"]["iterations"]),
            test_per_iter=int(cfg["fine_tune"]["test_per_iter"]),
            num_ring=int(cfg["fine_tune"]["num_ring"]),
            num_arm=int(cfg["fine_tune"]["num_arm"]),
            spp=int(cfg["fine_tune"]["spp"]),
        ),
        parameter_sources={
            **{key: SUGGESTED_DEFAULT for key in ("foclen", "fov", "fnum", "bfl", "thickness", "surf_list")},
            "imgh": DERIVED,
        },
        budget_sources={"curriculum": SUGGESTED_DEFAULT, "fine_tune": SUGGESTED_DEFAULT},
    )


def build_agent_input(
    project_root: Path,
    *,
    payload: dict[str, Any],
):
    from agent.settings import AgentInput

    defaults = load_default_params(project_root)
    natural_mode = str(payload["mode"]) in {"natural", "nl"}
    base_params = params_from_payload(
        payload,
        defaults,
        present_values_are_user_input=not natural_mode,
    )
    max_turns = None
    raw_max_turns = payload.get("max_turns")
    explicit_limit = payload.get("max_turns_is_limit") is True
    if raw_max_turns not in (None, ""):
        try:
            explicit_limit = explicit_limit or int(raw_max_turns) != RECOMMENDED_OPTIMIZATION_REVIEW_TURNS
        except (TypeError, ValueError):
            pass
    if explicit_limit:
        try:
            max_turns = max(1, int(raw_max_turns))
        except (KeyError, TypeError, ValueError):
            max_turns = None

    return AgentInput(
        mode="nl" if natural_mode else "params",
        prompt=payload.get("nl_prompt", "").strip() if natural_mode else None,
        params=base_params,
        max_turns=max_turns,
        recommended_max_turns=RECOMMENDED_OPTIMIZATION_REVIEW_TURNS,
    )


def params_from_payload(
    payload: dict[str, Any],
    defaults: LensDesignParams,
    *,
    present_values_are_user_input: bool = False,
) -> LensDesignParams:
    params = deepcopy(defaults)

    params.exp_name = str(payload.get("exp_name", defaults.exp_name))
    if "seed" in payload:
        params.seed = None if payload.get("seed") in (None, "") else int(payload["seed"])
    params.fov = float(payload.get("fov", defaults.fov))
    metadata = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    supplied_sources = metadata.get("parameter_sources") if isinstance(metadata.get("parameter_sources"), dict) else {}
    params.foclen = float(payload.get("foclen", defaults.foclen))
    params.imgh = float(payload.get("imgh", _image_height(params.foclen, params.fov)))
    params.parameter_sources["imgh"] = str(
        supplied_sources.get("imgh") or (USER_INPUT if "imgh" in payload else DERIVED)
    )

    params.fnum = float(payload.get("fnum", defaults.fnum))
    params.bfl = float(payload.get("bfl", defaults.bfl))
    params.thickness = float(payload.get("thickness", defaults.thickness))
    params.surf_list = payload.get("surf_list", defaults.surf_list)
    raw_lr_scale = payload.get("lr_scale", defaults.lr_scale)
    params.lr_scale = max(
        0.1,
        min(10.0, float(defaults.lr_scale if raw_lr_scale in (None, "") else raw_lr_scale)),
    )

    curriculum = payload.get("curriculum", {})
    params.curriculum.iterations = int(
        curriculum.get("iterations", payload.get("iterations", defaults.curriculum.iterations))
    )
    params.curriculum.test_per_iter = int(
        curriculum.get("test_per_iter", payload.get("test_per_iter", defaults.curriculum.test_per_iter))
    )
    params.curriculum.num_ring = int(curriculum.get("num_ring", defaults.curriculum.num_ring))
    params.curriculum.num_arm = int(curriculum.get("num_arm", defaults.curriculum.num_arm))
    params.curriculum.spp = int(curriculum.get("spp", payload.get("spp", defaults.curriculum.spp)))

    fine_tune = payload.get("fine_tune", {})
    params.fine_tune.iterations = int(fine_tune.get("iterations", defaults.fine_tune.iterations))
    params.fine_tune.test_per_iter = int(fine_tune.get("test_per_iter", defaults.fine_tune.test_per_iter))
    params.fine_tune.num_ring = int(fine_tune.get("num_ring", defaults.fine_tune.num_ring))
    params.fine_tune.num_arm = int(fine_tune.get("num_arm", defaults.fine_tune.num_arm))
    params.fine_tune.spp = int(fine_tune.get("spp", payload.get("spp", defaults.fine_tune.spp)))
    for key in ("foclen", "fov", "fnum", "bfl", "thickness", "surf_list"):
        if key in payload:
            explicit_source = supplied_sources.get(key)
            if explicit_source:
                params.parameter_sources[key] = str(explicit_source)
            elif present_values_are_user_input or payload.get(key) != getattr(defaults, key):
                params.parameter_sources[key] = USER_INPUT
    params.constraints = _constraints_from_payload(payload, metadata, params.constraints)
    supplied_budget_sources = metadata.get("budget_sources") if isinstance(metadata.get("budget_sources"), dict) else {}
    for stage_name, stage_payload, default_stage in (
        ("curriculum", curriculum, defaults.curriculum),
        ("fine_tune", fine_tune, defaults.fine_tune),
    ):
        supplied_stage = dict(stage_payload) if isinstance(stage_payload, dict) else {}
        if stage_name == "curriculum":
            for key in ("iterations", "test_per_iter", "spp"):
                if key in payload and key not in supplied_stage:
                    supplied_stage[key] = payload[key]
        changed = any(
            key in supplied_stage and int(supplied_stage[key]) != int(getattr(default_stage, key))
            for key in ("iterations", "test_per_iter", "num_ring", "num_arm", "spp")
        )
        default_source = USER_INPUT if supplied_stage and (present_values_are_user_input or changed) else SUGGESTED_DEFAULT
        params.budget_sources[stage_name] = str(supplied_budget_sources.get(stage_name) or default_source)
    return params


def params_from_public_dict(payload: dict[str, Any], defaults: LensDesignParams) -> LensDesignParams:
    """Build `LensDesignParams` from the JSON-safe shape exposed to agent tools."""
    return params_from_payload(payload, defaults)


def clone_params(params: LensDesignParams) -> LensDesignParams:
    return deepcopy(params)


def public_params_dict(params: LensDesignParams | None) -> dict[str, Any] | None:
    """Return public targets, initialization geometry, structure, and budgets."""
    if params is None:
        return None
    return {
        "exp_name": params.exp_name,
        "seed": params.seed,
        "foclen": params.foclen,
        "imgh": params.imgh,
        "fov": params.fov,
        "fnum": params.fnum,
        "bfl": params.bfl,
        "thickness": params.thickness,
        "surf_list": params.surf_list,
        "lr_scale": params.lr_scale,
        "curriculum": _stage_budget_dict(params.curriculum),
        "fine_tune": _stage_budget_dict(params.fine_tune),
        "_meta": {
            "parameter_sources": dict(params.parameter_sources),
            "constraints": {
                key: {
                    "relation": spec.relation,
                    "tolerance": spec.tolerance,
                    "source": spec.source,
                }
                for key, spec in sorted(params.constraints.items())
            },
            "budget_sources": dict(params.budget_sources),
        },
    }


def target_params_dict(params: LensDesignParams | None) -> dict[str, Any] | None:
    """Return the compatibility payload used by workflow state.

    Despite the historical function name, ``bfl`` and ``thickness`` are
    initialization geometry rather than exact final targets.
    """
    if params is None:
        return None
    return {
        "foclen": params.foclen,
        "imgh": params.imgh,
        "fov": params.fov,
        "fnum": params.fnum,
        "bfl": params.bfl,
        "thickness": params.thickness,
        "surf_list": params.surf_list,
        "lr_scale": params.lr_scale,
    }


def design_contract_dict(params: LensDesignParams | None) -> dict[str, Any] | None:
    """Describe intent separately from backend execution parameters."""
    if params is None:
        return None

    def item(key: str, value: float, unit: str) -> dict[str, Any]:
        constraint = params.constraints.get(key)
        return {
            "value": value,
            "unit": unit,
            "source": params.parameter_sources.get(key, SUGGESTED_DEFAULT),
            "relation": constraint.relation if constraint else "exact",
            "tolerance": constraint.tolerance if constraint else None,
            "constraint_source": constraint.source if constraint else None,
        }

    constrained = set(params.constraints)
    initialization: dict[str, Any] = {}
    packaging: dict[str, Any] = {}
    for key, value in (("bfl", params.bfl), ("thickness", params.thickness)):
        target = packaging if key in constrained else initialization
        target[key] = {**item(key, value, "mm"), "role": "packaging_constraint" if key in constrained else "starting_geometry"}
    scale_targets = {"foclen": item("foclen", params.foclen, "mm")}
    if params.parameter_sources.get("imgh") == USER_INPUT or "imgh" in constrained:
        scale_targets["imgh"] = item("imgh", params.imgh, "mm_half_diagonal")
    return {
        "optical_targets": {
            **scale_targets,
            "fov": item("fov", params.fov, "degree_full_field"),
            "fnum": item("fnum", params.fnum, "dimensionless"),
        },
        "packaging_constraints": packaging,
        "initialization": initialization,
        "protected_parameter_keys": sorted({"foclen", "imgh", "fov", "fnum"} | constrained),
        "effort_guidance": {
            "curriculum": {**_stage_budget_dict(params.curriculum), "source": params.budget_sources.get("curriculum", SUGGESTED_DEFAULT)},
            "fine_tune": {**_stage_budget_dict(params.fine_tune), "source": params.budget_sources.get("fine_tune", SUGGESTED_DEFAULT)},
            "meaning": "Starting-point guidance with provenance. It is not a required total or hard limit unless represented separately as one.",
        },
    }


def _constraints_from_payload(
    payload: dict[str, Any],
    metadata: dict[str, Any],
    current: dict[str, DesignConstraint],
) -> dict[str, DesignConstraint]:
    """Normalize constraint input once; the rest of the system uses one model."""
    constraints = deepcopy(current)
    raw_constraints = metadata.get("constraints", payload.get("constraints", {}))
    if isinstance(raw_constraints, dict):
        for raw_key, raw_spec in raw_constraints.items():
            key = str(raw_key)
            if key not in CONSTRAINABLE_FIELDS:
                continue
            spec = raw_spec if isinstance(raw_spec, dict) else {"relation": raw_spec}
            relation = str(spec.get("relation") or "exact").lower()
            if relation not in CONSTRAINT_RELATIONS:
                continue
            constraints[key] = DesignConstraint(
                relation=relation,
                tolerance=_optional_nonnegative_float(spec.get("tolerance")),
                source=str(spec.get("source") or USER_INPUT),
            )

    # Boundary compatibility for older callers. These fields are not emitted.
    legacy_hard = metadata.get("hard_constraints", payload.get("hard_constraints", []))
    if isinstance(legacy_hard, list):
        for raw_key in legacy_hard:
            key = str(raw_key)
            if key in CONSTRAINABLE_FIELDS and key not in constraints:
                constraints[key] = DesignConstraint()
    legacy_tolerances = metadata.get("tolerances", payload.get("tolerances", {}))
    if isinstance(legacy_tolerances, dict):
        for raw_key, raw_value in legacy_tolerances.items():
            key = str(raw_key)
            tolerance = _optional_nonnegative_float(raw_value)
            if key not in CONSTRAINABLE_FIELDS or tolerance is None:
                continue
            previous = constraints.get(key, DesignConstraint())
            constraints[key] = DesignConstraint(
                relation=previous.relation,
                tolerance=tolerance,
                source=previous.source,
            )
    return constraints


def _optional_nonnegative_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def _image_height(foclen: float, full_fov_deg: float) -> float:
    return float(foclen) * math.tan(math.radians(float(full_fov_deg) / 2.0))





def _stage_budget_dict(stage: Any) -> dict[str, Any]:
    return {
        "iterations": int(getattr(stage, "iterations")),
        "test_per_iter": int(getattr(stage, "test_per_iter")),
        "num_ring": int(getattr(stage, "num_ring")),
        "num_arm": int(getattr(stage, "num_arm")),
        "spp": int(getattr(stage, "spp")),
    }


__all__ = [
    "ADAPTIVE",
    "DERIVED",
    "CONSTRAINABLE_FIELDS",
    "CONSTRAINT_RELATIONS",
    "CurriculumParams",
    "DEFAULT_CONFIG",
    "DEFAULT_OPTIMIZATION_MAX_TURNS",
    "DesignConstraint",
    "FineTuneParams",
    "LensDesignParams",
    "RECOMMENDED_OPTIMIZATION_REVIEW_TURNS",
    "SeedCandidate",
    "build_agent_input",
    "clone_params",
    "design_contract_dict",
    "load_default_config",
    "load_default_params",
    "params_from_payload",
    "params_from_public_dict",
    "public_params_dict",
    "target_params_dict",
]
