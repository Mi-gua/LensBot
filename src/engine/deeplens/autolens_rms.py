from __future__ import annotations

import json
import logging
import math
import random
import sys
from pathlib import Path
from typing import Callable

from agent.settings import LensDesignParams
from engine.deeplens.runtime import ensure_deeplens_import


DEEPLENS_ORIGINAL_LRS = [1e-3, 1e-4, 1e-2, 1e-4]


def _deeplens_cosine_schedule_with_warmup(optimizer, num_warmup_steps: int, num_training_steps: int):
    """DeepLens GeoLensOptim cosine warmup scheduler."""
    import torch

    def lr_lambda(current_step):
        if current_step < num_warmup_steps:
            return float(current_step) / float(max(1, num_warmup_steps))
        progress = float(current_step - num_warmup_steps) / float(
            max(1, num_training_steps - num_warmup_steps)
        )
        return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


def patch_zmx_export_from_final_json(final_json: str | Path, final_zmx: str | Path) -> None:
    """Patch DeepLens ZMX export gaps without modifying the external DeepLens package."""
    final_json = Path(final_json)
    final_zmx = Path(final_zmx)
    data = json.loads(final_json.read_text(encoding="utf-8-sig"))
    surfaces = data.get("surfaces", [])

    aperture_by_surf = {
        int(surface["idx"]) + 1: float(surface["r"])
        for surface in surfaces
        if surface.get("type") in {"Aperture", "Stop"} and surface.get("r") is not None
    }
    if not aperture_by_surf:
        return

    text = final_zmx.read_text(encoding="utf-8")
    lines = text.splitlines()
    patched: list[str] = []
    current_surf: int | None = None
    pending_stop_diam: float | None = None
    current_has_diam = False

    def flush_pending() -> None:
        nonlocal pending_stop_diam
        if pending_stop_diam is not None and not current_has_diam:
            patched.append(f'    DIAM {pending_stop_diam:.10g} 1 0 0 1 ""')
        pending_stop_diam = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SURF "):
            flush_pending()
            parts = stripped.split()
            current_surf = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            current_has_diam = False
        elif stripped.startswith("DIAM "):
            current_has_diam = True

        if stripped == "STOP" and current_surf in aperture_by_surf:
            pending_stop_diam = aperture_by_surf[current_surf]

        patched.append(line)

    flush_pending()

    patched = _patch_zmx_aperture_header(patched, data, aperture_by_surf)
    final_zmx.write_text("\n".join(patched) + "\n", encoding="utf-8")


def _patch_zmx_aperture_header(
    lines: list[str], data: dict, aperture_by_surf: dict[int, float]
) -> list[str]:
    enpd = data.get("enpd")
    if enpd is None:
        foclen = _as_float(data.get("foclen"))
        fnum = _as_float(data.get("fnum"))
        enpd = abs(foclen) / fnum if foclen and fnum and fnum > 0 else None
    if enpd is None and aperture_by_surf:
        enpd = 2.0 * next(iter(aperture_by_surf.values()))
    if enpd is None:
        return lines

    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("ENVD "):
            result.append(f"    ENVD {float(enpd):.10g} 1 0")
        else:
            result.append(line)
    return result


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optimize_autolens_rms(
    params: LensDesignParams,
    result_dir: str | Path,
    artifact_cb: Callable[[], None] | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    ensure_deeplens_import(Path(__file__))
    result_dir = Path(result_dir)

    import torch
    from torch.nn.functional import softplus
    from tqdm import tqdm

    try:
        from deeplens.optics import GeoLens
        from deeplens.optics.config import DEPTH, EPSILON, WAVE_RGB
        from deeplens.optics.geolens_pkg.utils import create_lens
    except ModuleNotFoundError:
        from deeplens import GeoLens
        from deeplens.config import DEPTH, EPSILON, WAVE_RGB
        from deeplens.geolens_pkg.optim_init import create_lens
    from deeplens.utils import set_seed

    if params.seed is None:
        params.seed = random.randint(0, 100000)
    set_seed(params.seed)
    progress_marks: dict[str, int] = {}

    def emit_progress(stage: str, step: int, total: int, **metrics: float) -> None:
        if not progress_cb:
            return
        if total <= 0:
            return
        mark = progress_marks.get(stage, 1)
        threshold = math.ceil(total * mark / 5)
        if step < threshold and step < total:
            return
        stage_labels = {
            "Curriculum": "\u8bfe\u7a0b\u5b66\u4e60",
            "FineTune": "\u5fae\u8c03",
        }
        percent = min(100, int(round(step / total * 100)))
        progress_cb(
            f"{stage_labels.get(stage, stage)}\u8fdb\u5ea6 {percent}%\uff1a"
            f"\u7b2c {step}/{total} \u8f6e\u3002"
        )
        while mark <= 5 and step >= math.ceil(total * mark / 5):
            mark += 1
        progress_marks[stage] = mark
    logging.info("EXP: %s", params.exp_name)
    logging.info("Seed: %s", params.seed)

    lens = create_lens(
        foclen=params.foclen,
        fov=params.fov,
        fnum=params.fnum,
        bfl=params.bfl,
        thickness=params.thickness,
        surf_list=params.surf_list,
        save_dir=str(result_dir),
    )
    if artifact_cb:
        artifact_cb()
    lens.set_target_fov_fnum(rfov=params.fov / 2 / 57.3, fnum=params.fnum)

    def curriculum_design(self: GeoLens, stage_params, result_path: str):
        iter_dir = Path(result_path) / "curriculum"
        iter_dir.mkdir(parents=True, exist_ok=True)
        depth = DEPTH
        spp = int(stage_params.spp)
        if progress_cb:
            progress_cb(f"\u5f00\u59cb\u8bfe\u7a0b\u5b66\u4e60\uff1a\u5171 {int(stage_params.iterations)} \u8f6e\u3002")
        optimizer = self.get_optimizer(DEEPLENS_ORIGINAL_LRS, optim_mat=True)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimizer, T_0=int(stage_params.iterations) // 4, T_mult=1
        )
        aper_start = self.surfaces[self.aper_idx].r * 0.25
        aper_final = self.surfaces[self.aper_idx].r

        pbar = tqdm(
            total=int(stage_params.iterations) + 1,
            desc="Curriculum",
            postfix={"loss_rms": 0},
            disable=False,
            file=sys.stdout,
        )
        total_iters = int(stage_params.iterations)
        for i in range(total_iters + 1):
            if i % int(stage_params.test_per_iter) == 0:
                with torch.no_grad():
                    progress = 0.5 * (1 + math.cos(math.pi * (1 - i / total_iters)))
                    aper_r = min(aper_start + (aper_final - aper_start) * progress, aper_final)
                    self.surfaces[self.aper_idx].update_r(aper_r)
                    self.calc_pupil()
                    if i > 0:
                        self.correct_shape()
                    iter_base = iter_dir / f"iter{i}"
                    self.write_lens_json(str(iter_base.with_suffix(".json")))
                    self.analysis(str(iter_base))
                    if artifact_cb:
                        artifact_cb()

                    rays_backup = []
                    for wv in WAVE_RGB:
                        ray = self.sample_ring_arm_rays(
                            num_ring=int(stage_params.num_ring),
                            num_arm=int(stage_params.num_arm),
                            depth=depth,
                            spp=spp,
                            wvln=wv,
                            scale_pupil=1.10,
                        )
                        rays_backup.append(ray)
                    center_ref = -self.psf_center(points_obj=ray.o[:, :, 0, :], method="pinhole")
                    center_ref = center_ref.unsqueeze(-2).repeat(1, 1, spp, 1)

            loss_rms = []
            for wv_idx, _wv in enumerate(WAVE_RGB):
                ray = rays_backup[wv_idx].clone()
                ray = self.trace2sensor(ray)
                ray_xy = ray.o[..., :2]
                ray_valid = ray.is_valid
                ray_err = ray_xy - center_ref
                if wv_idx == 0:
                    with torch.no_grad():
                        weight_mask = ((ray_err**2).sum(-1) * ray_valid).sum(-1)
                        weight_mask /= ray_valid.sum(-1) + EPSILON
                        weight_mask /= weight_mask.mean()
                        dropout_mask = torch.rand_like(weight_mask) < 0.1
                        weight_mask = weight_mask * (~dropout_mask)
                l_rms = ((ray_err**2).sum(-1) * ray_valid).sum(-1)
                l_rms /= ray_valid.sum(-1) + EPSILON
                l_rms = (l_rms + EPSILON).sqrt()
                l_rms_weighted = (l_rms * weight_mask).sum()
                l_rms_weighted /= weight_mask.sum() + EPSILON
                loss_rms.append(l_rms_weighted)

            loss_rms = sum(loss_rms) / len(loss_rms)
            loss_focus = self.loss_infocus()
            loss_reg, _loss_dict = self.loss_reg()
            total_loss = loss_rms + 0.1 * loss_focus + 0.05 * loss_reg
            optimizer.zero_grad()
            total_loss.backward()
            optimizer.step()
            scheduler.step()
            pbar.set_postfix(loss_rms=loss_rms.item())
            pbar.update(1)
            emit_progress("Curriculum", i, total_iters, loss_rms=loss_rms.item())
        pbar.close()

    def fine_tune_design(self: GeoLens, stage_params, result_path: str):
        result_dir = Path(result_path)
        result_dir.mkdir(parents=True, exist_ok=True)
        depth = self.obj_depth
        spp = int(stage_params.spp)
        if progress_cb:
            progress_cb(f"\u5f00\u59cb\u4f18\u5316\u5fae\u8c03\uff1a\u5171 {int(stage_params.iterations)} \u8f6e\u3002")
        optimizer = self.get_optimizer(DEEPLENS_ORIGINAL_LRS, optim_mat=False)
        scheduler = _deeplens_cosine_schedule_with_warmup(
            optimizer,
            num_warmup_steps=100,
            num_training_steps=int(stage_params.iterations),
        )

        pbar = tqdm(
            total=int(stage_params.iterations) + 1,
            desc="FineTune",
            postfix={"loss_rms": 0},
            disable=False,
            file=sys.stdout,
        )
        total_iters = int(stage_params.iterations)
        for i in range(total_iters + 1):
            if i % int(stage_params.test_per_iter) == 0:
                with torch.no_grad():
                    logging.info("FineTune checkpoint start: iter=%s", i)
                    if i > 0:
                        self.correct_shape()
                    iter_path = str(result_dir / f"iter{i}")
                    self.write_lens_json(f"{iter_path}.json")
                    self.analysis(iter_path)
                    if artifact_cb:
                        artifact_cb()
                    logging.info("FineTune checkpoint done: iter=%s", i)
                    self.calc_pupil()
                    rays_backup = []
                    for wv in self.wvln_rgb:
                        ray = self.sample_ring_arm_rays(
                            num_ring=int(stage_params.num_ring),
                            num_arm=int(stage_params.num_arm),
                            spp=spp,
                            depth=depth,
                            wvln=wv,
                            scale_pupil=1.05,
                            sample_more_off_axis=False,
                        )
                        rays_backup.append(ray)
                    pinhole_ref = -self.psf_center(points_obj=ray.o[:, :, 0, :], method="pinhole")

            loss_rms_ls = []
            loss_distortion = torch.tensor(0.0, device=self.device)
            weight_mask = None
            center_ref = None
            wvln_order = [1, 0, 2]
            for wv_idx in wvln_order:
                ray = rays_backup[wv_idx].clone()
                ray = self.trace2sensor(ray)

                if center_ref is None:
                    centroid_xy = ray.centroid()[..., :2]
                    ideal_height = pinhole_ref.norm(dim=-1)
                    field_mask = ideal_height > EPSILON
                    distortion = (centroid_xy - pinhole_ref).norm(dim=-1)
                    distortion = distortion / ideal_height.clamp_min(EPSILON)
                    violation = distortion - self.distortion_max
                    penalty = softplus(violation / self.distortion_max, beta=20.0)
                    n_fields = field_mask.sum().clamp_min(1)
                    loss_distortion = (penalty * field_mask.float()).sum() / n_fields
                    center_ref = centroid_xy.detach().unsqueeze(-2)

                ray_valid = ray.is_valid
                ray_err = ray.o[..., :2] - center_ref
                ray_err = torch.where(ray_valid.bool().unsqueeze(-1), ray_err, torch.zeros_like(ray_err))

                mse = (ray_err**2).sum(-1).sum(-1) / (ray_valid.sum(-1) + EPSILON)
                if weight_mask is None:
                    weight_mask = mse.detach().sqrt().clone()
                    weight_mask = weight_mask / (weight_mask.mean() + EPSILON)
                    weight_mask[0, :] = 1.0

                l_rms = torch.clamp(mse, min=EPSILON).sqrt()
                l_rms_weighted = (l_rms * weight_mask).sum()
                l_rms_weighted /= weight_mask.sum() + EPSILON
                loss_rms_ls.append(l_rms_weighted)

            loss_rms = sum(loss_rms_ls) / len(loss_rms_ls)
            loss_reg, loss_dict = self.loss_reg()
            total_loss = loss_rms + 0.1 * (loss_reg + loss_distortion)
            optimizer.zero_grad()
            total_loss.backward()
            optimizer.step()
            scheduler.step()
            pbar.set_postfix(loss_rms=loss_rms.item(), loss_dist=loss_distortion.item(), **loss_dict)
            pbar.update(1)
            emit_progress(
                "FineTune",
                i,
                total_iters,
                loss_rms=loss_rms.item(),
            )
        pbar.close()

    GeoLens.curriculum_design = curriculum_design
    GeoLens.fine_tune_design = fine_tune_design

    lens.curriculum_design(stage_params=params.curriculum, result_path=str(result_dir))
    lens.match_materials()
    lens.set_fnum(params.fnum)
    lens.write_lens_json(f"{result_dir}/curriculum.json")
    lens.analysis(save_name=f"{result_dir}/curriculum")
    if artifact_cb:
        artifact_cb()

    lens = GeoLens(filename=f"{result_dir}/curriculum.json")
    lens.set_target_fov_fnum(rfov=params.fov / 2 / 57.3, fnum=params.fnum)
    lens.set_fnum(params.fnum)
    lens.fine_tune_design(stage_params=params.fine_tune, result_path=f"{result_dir}/fine-tune")
    lens.prune_surf(expand_factor=0.05)
    lens.post_computation()
    lens.write_lens_json(f"{result_dir}/final.json")
    final_zmx = result_dir / "final.zmx"
    lens.write_lens_zmx(str(final_zmx))
    patch_zmx_export_from_final_json(result_dir / "final.json", final_zmx)
    lens.analysis(save_name=f"{result_dir}/final")
    if artifact_cb:
        artifact_cb()

    return {
        "curriculum_json": str(result_dir / "curriculum.json"),
        "final_json": str(result_dir / "final.json"),
        "final_zmx": str(final_zmx),
        "rfov": str(lens.rfov),
        "rfov_deg": float(math.degrees(float(lens.rfov))),
        "fov_deg": float(2.0 * math.degrees(float(lens.rfov))),
        "fnum": float(lens.fnum),
        "r_sensor": float(lens.r_sensor),
        "structure_group_count": len(params.surf_list),
    }
