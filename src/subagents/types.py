from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CurriculumParams:
    iterations: int = 3000
    test_per_iter: int = 100
    num_ring: int = 16
    num_arm: int = 8
    spp: int = 512


@dataclass
class FineTuneParams:
    iterations: int = 2000
    test_per_iter: int = 100
    num_ring: int = 32
    num_arm: int = 8
    spp: int = 512


@dataclass
class LensDesignParams:
    exp_name: str
    seed: int | None
    foclen: float
    fov: float
    fnum: float
    bfl: float
    thickness: float
    surf_list: list[list[str]]
    curriculum: CurriculumParams = field(default_factory=CurriculumParams)
    fine_tune: FineTuneParams = field(default_factory=FineTuneParams)


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
    "foclen": 85.0,
    "fov": 40.0,
    "fnum": 4.0,
    "bfl": 18.0,
    "thickness": 120.0,
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
        "iterations": 3000,
        "test_per_iter": 100,
        "num_ring": 16,
        "num_arm": 8,
        "spp": 512,
    },
    "fine_tune": {
        "iterations": 2000,
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
        fov=float(cfg["fov"]),
        fnum=float(cfg["fnum"]),
        bfl=float(cfg["bfl"]),
        thickness=float(cfg["thickness"]),
        surf_list=cfg["surf_list"],
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
    )


def build_agent_input(
    project_root: Path,
    *,
    payload: dict[str, Any],
):
    from agent.settings import AgentInput

    defaults = load_default_params(project_root)
    base_params = params_from_payload(payload, defaults)

    mode = str(payload["mode"])
    if mode in {"natural", "nl"}:
        return AgentInput(
            mode="nl",
            prompt=payload.get("nl_prompt", "").strip(),
            params=base_params,
        )

    return AgentInput(
        mode="params",
        params=base_params,
    )


def params_from_payload(payload: dict[str, Any], defaults: LensDesignParams) -> LensDesignParams:
    params = deepcopy(defaults)

    params.exp_name = str(payload.get("exp_name", defaults.exp_name))
    params.seed = None if payload.get("seed") in (None, "") else int(payload["seed"])
    params.foclen = float(payload.get("foclen", defaults.foclen))
    params.fov = float(payload.get("fov", defaults.fov))
    params.fnum = float(payload.get("fnum", defaults.fnum))
    params.bfl = float(payload.get("bfl", defaults.bfl))
    params.thickness = float(payload.get("thickness", defaults.thickness))
    params.surf_list = payload.get("surf_list", defaults.surf_list)

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
    return params


def params_from_public_dict(payload: dict[str, Any], defaults: LensDesignParams) -> LensDesignParams:
    """Build `LensDesignParams` from the JSON-safe shape exposed to agent tools."""
    return params_from_payload(payload, defaults)


def clone_params(params: LensDesignParams) -> LensDesignParams:
    return deepcopy(params)


def public_params_dict(params: LensDesignParams | None) -> dict[str, Any] | None:
    """Return only target fields and the budget knobs LensBot is allowed to expose."""
    if params is None:
        return None
    return {
        "exp_name": params.exp_name,
        "seed": params.seed,
        "foclen": params.foclen,
        "fov": params.fov,
        "fnum": params.fnum,
        "bfl": params.bfl,
        "thickness": params.thickness,
        "surf_list": params.surf_list,
        "curriculum": _stage_budget_dict(params.curriculum),
        "fine_tune": _stage_budget_dict(params.fine_tune),
    }


def target_params_dict(params: LensDesignParams | None) -> dict[str, Any] | None:
    if params is None:
        return None
    return {
        "foclen": params.foclen,
        "fov": params.fov,
        "fnum": params.fnum,
        "bfl": params.bfl,
        "thickness": params.thickness,
        "surf_list": params.surf_list,
    }


def _stage_budget_dict(stage: Any) -> dict[str, Any]:
    return {
        "iterations": int(getattr(stage, "iterations")),
        "test_per_iter": int(getattr(stage, "test_per_iter")),
        "num_ring": int(getattr(stage, "num_ring")),
        "num_arm": int(getattr(stage, "num_arm")),
        "spp": int(getattr(stage, "spp")),
    }


__all__ = [
    "CurriculumParams",
    "DEFAULT_CONFIG",
    "FineTuneParams",
    "LensDesignParams",
    "SeedCandidate",
    "build_agent_input",
    "clone_params",
    "load_default_config",
    "load_default_params",
    "params_from_payload",
    "params_from_public_dict",
    "public_params_dict",
    "target_params_dict",
]
