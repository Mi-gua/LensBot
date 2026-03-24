from __future__ import annotations

from pathlib import Path

import yaml

from schema import LensDesignParams, OptimizationControls


def load_default_config(project_root: Path) -> dict:
    config_path = project_root / "configs" / "default.yaml"
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_default_params(project_root: Path) -> LensDesignParams:
    cfg = load_default_config(project_root)
    return LensDesignParams(
        foclen=float(cfg["foclen"]),
        fov=float(cfg["fov"]),
        fnum=float(cfg["fnum"]),
        bfl=float(cfg["bfl"]),
        thickness=float(cfg["thickness"]),
        surf_list=cfg["surf_list"],
        lrs=[float(v) for v in cfg["lrs"]],
        iterations=int(cfg["iterations"]),
        spp=int(cfg["spp"]),
        test_per_iter=int(cfg["test_per_iter"]),
    )


def load_default_controls(project_root: Path) -> OptimizationControls:
    cfg = load_default_config(project_root)
    return OptimizationControls(
        iterations=int(cfg["iterations"]),
        spp=int(cfg["spp"]),
        test_per_iter=int(cfg["test_per_iter"]),
    )
