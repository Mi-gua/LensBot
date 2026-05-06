from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from copy import deepcopy

import yaml


@dataclass
class CurriculumParams:
    lrs: list[float] = field(default_factory=lambda: [1e-3, 1e-4, 1e-2, 1e-4])
    iterations: int = 3000
    test_per_iter: int = 100
    optim_mat: bool = True
    match_mat: bool = False
    shape_control: bool = True
    num_ring: int = 16
    num_arm: int = 8
    spp: int = 512
    scale_pupil: float = 1.10
    aper_start_ratio: float = 0.25
    weight_dropout: float = 0.1
    w_focus: float = 0.1
    w_reg: float = 0.05


@dataclass
class FineTuneParams:
    lrs: list[float] = field(default_factory=lambda: [1e-4, 1e-5, 1e-3, 1e-5])
    iterations: int = 2000
    test_per_iter: int = 100
    centroid: bool = False
    optim_mat: bool = False
    shape_control: bool = True
    num_ring: int = 32
    num_arm: int = 8
    spp: int = 512
    scale_pupil: float = 1.05
    weight_dropout: float = 0.0
    w_focus: float = 1.0
    w_reg: float = 0.1
    num_warmup_steps: int = 100


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
class AgentInput:
    mode: str
    prompt: str | None = None
    params: LensDesignParams | None = None


@dataclass
class AgentResult:
    ok: bool
    summary: str
    result_dir: str | None = None
    curriculum_json: str | None = None
    final_json: str | None = None
    final_zmx: str | None = None
    summary_report_file: str | None = None
    log_file: str | None = None
    metrics_file: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[str] = field(default_factory=list)
    memory_snapshot: dict[str, Any] = field(default_factory=dict)


def load_default_config(project_root: Path) -> dict[str, Any]:
    config_path = project_root / "src" / "agent" / "defaults.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_default_params(project_root: Path) -> LensDesignParams:
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
            lrs=[float(v) for v in cfg["curriculum"]["lrs"]],
            iterations=int(cfg["curriculum"]["iterations"]),
            test_per_iter=int(cfg["curriculum"]["test_per_iter"]),
            optim_mat=bool(cfg["curriculum"]["optim_mat"]),
            match_mat=bool(cfg["curriculum"]["match_mat"]),
            shape_control=bool(cfg["curriculum"]["shape_control"]),
            num_ring=int(cfg["curriculum"]["num_ring"]),
            num_arm=int(cfg["curriculum"]["num_arm"]),
            spp=int(cfg["curriculum"]["spp"]),
            scale_pupil=float(cfg["curriculum"]["scale_pupil"]),
            aper_start_ratio=float(cfg["curriculum"]["aper_start_ratio"]),
            weight_dropout=float(cfg["curriculum"]["weight_dropout"]),
            w_focus=float(cfg["curriculum"]["w_focus"]),
            w_reg=float(cfg["curriculum"]["w_reg"]),
        ),
        fine_tune=FineTuneParams(
            lrs=[float(v) for v in cfg["fine_tune"]["lrs"]],
            iterations=int(cfg["fine_tune"]["iterations"]),
            test_per_iter=int(cfg["fine_tune"]["test_per_iter"]),
            centroid=bool(cfg["fine_tune"]["centroid"]),
            optim_mat=bool(cfg["fine_tune"]["optim_mat"]),
            shape_control=bool(cfg["fine_tune"]["shape_control"]),
            num_ring=int(cfg["fine_tune"]["num_ring"]),
            num_arm=int(cfg["fine_tune"]["num_arm"]),
            spp=int(cfg["fine_tune"]["spp"]),
            scale_pupil=float(cfg["fine_tune"]["scale_pupil"]),
            weight_dropout=float(cfg["fine_tune"]["weight_dropout"]),
            w_focus=float(cfg["fine_tune"]["w_focus"]),
            w_reg=float(cfg["fine_tune"]["w_reg"]),
            num_warmup_steps=int(cfg["fine_tune"]["num_warmup_steps"]),
        ),
    )


def _params_from_payload(payload: dict[str, Any], defaults: LensDesignParams) -> LensDesignParams:
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
    params.curriculum.lrs = [float(v) for v in curriculum.get("lrs", defaults.curriculum.lrs)]
    params.curriculum.iterations = int(
        curriculum.get("iterations", payload.get("iterations", defaults.curriculum.iterations))
    )
    params.curriculum.test_per_iter = int(
        curriculum.get("test_per_iter", payload.get("test_per_iter", defaults.curriculum.test_per_iter))
    )
    params.curriculum.optim_mat = bool(curriculum.get("optim_mat", defaults.curriculum.optim_mat))
    params.curriculum.match_mat = bool(curriculum.get("match_mat", defaults.curriculum.match_mat))
    params.curriculum.shape_control = bool(curriculum.get("shape_control", defaults.curriculum.shape_control))
    params.curriculum.num_ring = int(curriculum.get("num_ring", defaults.curriculum.num_ring))
    params.curriculum.num_arm = int(curriculum.get("num_arm", defaults.curriculum.num_arm))
    params.curriculum.spp = int(curriculum.get("spp", payload.get("spp", defaults.curriculum.spp)))
    params.curriculum.scale_pupil = float(curriculum.get("scale_pupil", defaults.curriculum.scale_pupil))
    params.curriculum.aper_start_ratio = float(
        curriculum.get("aper_start_ratio", defaults.curriculum.aper_start_ratio)
    )
    params.curriculum.weight_dropout = float(
        curriculum.get("weight_dropout", defaults.curriculum.weight_dropout)
    )
    params.curriculum.w_focus = float(curriculum.get("w_focus", defaults.curriculum.w_focus))
    params.curriculum.w_reg = float(curriculum.get("w_reg", defaults.curriculum.w_reg))

    fine_tune = payload.get("fine_tune", {})
    params.fine_tune.lrs = [float(v) for v in fine_tune.get("lrs", defaults.fine_tune.lrs)]
    params.fine_tune.iterations = int(fine_tune.get("iterations", defaults.fine_tune.iterations))
    params.fine_tune.test_per_iter = int(fine_tune.get("test_per_iter", defaults.fine_tune.test_per_iter))
    params.fine_tune.centroid = bool(fine_tune.get("centroid", defaults.fine_tune.centroid))
    params.fine_tune.optim_mat = bool(fine_tune.get("optim_mat", defaults.fine_tune.optim_mat))
    params.fine_tune.shape_control = bool(fine_tune.get("shape_control", defaults.fine_tune.shape_control))
    params.fine_tune.num_ring = int(fine_tune.get("num_ring", defaults.fine_tune.num_ring))
    params.fine_tune.num_arm = int(fine_tune.get("num_arm", defaults.fine_tune.num_arm))
    params.fine_tune.spp = int(fine_tune.get("spp", payload.get("spp", defaults.fine_tune.spp)))
    params.fine_tune.scale_pupil = float(fine_tune.get("scale_pupil", defaults.fine_tune.scale_pupil))
    params.fine_tune.weight_dropout = float(
        fine_tune.get("weight_dropout", defaults.fine_tune.weight_dropout)
    )
    params.fine_tune.w_focus = float(fine_tune.get("w_focus", defaults.fine_tune.w_focus))
    params.fine_tune.w_reg = float(fine_tune.get("w_reg", defaults.fine_tune.w_reg))
    params.fine_tune.num_warmup_steps = int(
        fine_tune.get("num_warmup_steps", defaults.fine_tune.num_warmup_steps)
    )
    return params


def build_agent_input(
    project_root: Path,
    *,
    payload: dict[str, Any],
) -> AgentInput:
    defaults = load_default_params(project_root)
    base_params = _params_from_payload(payload, defaults)

    mode = payload["mode"]
    if mode == "自然语言输入":
        return AgentInput(
            mode="nl",
            prompt=payload.get("nl_prompt", "").strip(),
            params=base_params,
        )

    return AgentInput(
        mode="params",
        params=base_params,
    )


__all__ = [
    "AgentInput",
    "AgentResult",
    "CurriculumParams",
    "FineTuneParams",
    "LensDesignParams",
    "build_agent_input",
    "load_default_config",
    "load_default_params",
]
