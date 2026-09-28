from __future__ import annotations

import contextlib
import copy
import shutil
import uuid
from pathlib import Path
from typing import Any

from engine.deeplens.runtime import ensure_deeplens_import
from runtime.result import ResultWorkspace


SURFACE_TYPES = {"Spheric", "Aspheric"}


class StructureSeedError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_structure_seed"):
        super().__init__(message)
        self.code = code


def apply_structure_seed_adjustment(args: dict[str, Any]) -> dict[str, Any]:
    params = copy.deepcopy(args.get("params") if isinstance(args.get("params"), dict) else {})
    surf_list = normalize_surf_list(params.get("surf_list"))
    if not params or not surf_list:
        raise StructureSeedError("deeplens_adjust_structure requires valid params.surf_list.", code="invalid_params")

    old_surf_list = [group[:] for group in surf_list]
    action = str(args.get("action") or "")
    changed = True
    if action == "set_group_surface_count":
        _set_group_surface_count(surf_list, args)
    elif action == "convert_aspheric_to_spheric":
        changed = _convert_aspheric_to_spheric(surf_list, args)
    else:
        raise StructureSeedError(f"Unsupported structure action: {action}", code="unsupported_structure_action")

    validate_surf_list(surf_list)
    params["surf_list"] = surf_list
    return {
        "action": action,
        "params": params,
        "old_surf_list": old_surf_list,
        "surf_list": surf_list,
        "changed": changed,
        "structure_summary": structure_summary(surf_list),
    }


def normalize_surf_list(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    groups: list[list[str]] = []
    for item in value:
        group = [item] if isinstance(item, str) else item
        if not isinstance(group, list):
            return []
        group = [str(surface) for surface in group]
        if group == ["Aperture"] or _is_lens_group(group):
            groups.append(group)
        else:
            return []
    return groups


def validate_surf_list(surf_list: list[list[str]]) -> None:
    aperture = [idx for idx, group in enumerate(surf_list) if group == ["Aperture"]]
    if len(aperture) != 1:
        raise StructureSeedError("surf_list must contain exactly one ['Aperture'] group.", code="invalid_aperture")
    if not any(_is_lens_group(group) for group in surf_list):
        raise StructureSeedError("surf_list must contain at least one refractive lens group.", code="missing_lens_group")


def structure_summary(surf_list: list[list[str]]) -> dict[str, Any]:
    flat = [surface for group in surf_list for surface in group]
    return {
        "structure_group_count": len(surf_list),
        "structure_surface_count": len(flat),
        "structure_aspheric_count": flat.count("Aspheric"),
        "structure_spheric_count": flat.count("Spheric"),
    }


def dry_run_deeplens_create(project_root: Path, params: dict[str, Any]) -> None:
    ensure_deeplens_import(project_root)
    try:
        from deeplens.optics.geolens_pkg.utils import create_lens
    except ModuleNotFoundError:
        from deeplens.geolens_pkg.optim_init import create_lens

    root = project_root / ".cache" / "deeplens-structure-dryruns"
    workdir = root / f"dryrun-{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=False)
    try:
        with contextlib.redirect_stdout(_NullWriter()), contextlib.redirect_stderr(_NullWriter()):
            create_lens(
                foclen=float(params["foclen"]),
                fov=float(params["fov"]),
                fnum=float(params["fnum"]),
                bfl=float(params["bfl"]),
                thickness=float(params["thickness"]),
                surf_list=params["surf_list"],
                save_dir=str(workdir),
            )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def write_adjusted_structure_preview(project_root: Path, params: dict[str, Any], result_dir: str | Path) -> dict[str, str]:
    ensure_deeplens_import(project_root)
    try:
        from deeplens.optics.geolens_pkg.utils import create_lens
    except ModuleNotFoundError:
        from deeplens.geolens_pkg.optim_init import create_lens

    root = Path(result_dir)
    if not root.is_absolute():
        root = project_root / root
    display = ResultWorkspace.from_result_dir(root).deeplens_live_dir
    display.mkdir(parents=True, exist_ok=True)
    base = display / "adjusted-structure"
    with contextlib.redirect_stdout(_NullWriter()), contextlib.redirect_stderr(_NullWriter()):
        lens = create_lens(
            foclen=float(params["foclen"]),
            fov=float(params["fov"]),
            fnum=float(params["fnum"]),
            bfl=float(params["bfl"]),
            thickness=float(params["thickness"]),
            surf_list=params["surf_list"],
            save_dir=str(display),
        )
        lens.write_lens_json(str(base.with_suffix(".json")))
        lens.analysis(str(base))
    return {
        "result_dir": str(root),
        "adjusted_structure_json": str(base.with_suffix(".json")),
        "adjusted_structure_image": str(base.with_suffix(".png")),
    }


def _set_group_surface_count(surf_list: list[list[str]], args: dict[str, Any]) -> None:
    group = surf_list[_group_index(args, surf_list)]
    if not _is_lens_group(group):
        raise StructureSeedError("group_index must point to a lens group.", code="invalid_group")
    target = int(args.get("surface_count") or 0)
    if target not in {2, 3}:
        raise StructureSeedError("surface_count must be 2 or 3.", code="invalid_surface_count")
    fill = str(args.get("surface_type") or "Spheric")
    if fill not in SURFACE_TYPES:
        raise StructureSeedError("surface_type must be Spheric or Aspheric.", code="invalid_surface_type")
    surf_list[_group_index(args, surf_list)] = (group[:target] + [fill] * target)[:target]


def _convert_aspheric_to_spheric(surf_list: list[list[str]], args: dict[str, Any]) -> bool:
    indices = range(len(surf_list)) if args.get("group_index") is None else [_group_index(args, surf_list)]
    changed = False
    for idx in indices:
        if _is_lens_group(surf_list[idx]) and "Aspheric" in surf_list[idx]:
            surf_list[idx] = ["Spheric" if surface == "Aspheric" else surface for surface in surf_list[idx]]
            changed = True
    return changed


def _group_index(args: dict[str, Any], surf_list: list[list[str]]) -> int:
    try:
        idx = int(args["group_index"])
    except (KeyError, TypeError, ValueError) as exc:
        raise StructureSeedError("group_index is required.", code="missing_group_index") from exc
    if idx < 0 or idx >= len(surf_list):
        raise StructureSeedError("group_index is out of range.", code="group_index_out_of_range")
    return idx


def _is_lens_group(group: list[str]) -> bool:
    return len(group) in {2, 3} and all(surface in SURFACE_TYPES for surface in group)


class _NullWriter:
    def write(self, _value: str) -> int:
        return 0

    def flush(self) -> None:
        return None
