from __future__ import annotations

import contextlib
import math
import random
import shutil
import string
from datetime import datetime
from pathlib import Path
from typing import Callable

from engine.deeplens import ensure_deeplens_import
from schema import LensDesignParams


ProgressCallback = Callable[[str], None] | None


def _mk_result_dir(base: Path | None = None) -> Path:
    result_root = base or Path(__file__).resolve().parents[2] / "results"
    result_root.mkdir(parents=True, exist_ok=True)
    random_string = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(4))
    current_time = datetime.now().strftime("%m%d-%H%M%S")
    result_dir = result_root / f"{current_time}-{random_string}"
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


@contextlib.contextmanager
def _redirect_engine_output(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_fp:
        with contextlib.redirect_stdout(log_fp), contextlib.redirect_stderr(log_fp):
            yield


def _cleanup_intermediate_results(result_dir: Path) -> None:
    for iter_file in result_dir.glob("iter*.json"):
        iter_file.unlink(missing_ok=True)

    fine_tune_dir = result_dir / "fine-tune"
    if fine_tune_dir.exists():
        shutil.rmtree(fine_tune_dir)


def run_rms_design(params: LensDesignParams, progress_cb: ProgressCallback = None) -> dict:
    ensure_deeplens_import(Path(__file__))

    result_dir = _mk_result_dir()
    log_file = result_dir / "run.log"

    if progress_cb:
        progress_cb("Action: 初始化 DeepLens 设计任务")

    with _redirect_engine_output(log_file):
        import torch
        from tqdm import tqdm

        from deeplens.optics import GeoLens
        from deeplens.optics.config import DEPTH, EPSILON, WAVE_RGB
        from deeplens.optics.geolens_pkg.utils import create_lens

        lens = create_lens(
            foclen=params.foclen,
            fov=params.fov,
            fnum=params.fnum,
            bfl=params.bfl,
            thickness=params.thickness,
            surf_list=params.surf_list,
            save_dir=str(result_dir),
        )

        lens.set_target_fov_fnum(rfov=params.fov / 2 / 57.3, fnum=params.fnum)

        def curriculum_design(
            self: GeoLens,
            lrs=None,
            iterations: int = 50,
            test_per_iter: int = 5,
            optim_mat: bool = False,
            match_mat: bool = False,
            shape_control: bool = True,
            spp: int = 128,
            result_dir: str = "./results",
        ):
            if lrs is None:
                lrs = [1e-4, 1e-4, 1e-2, 1e-4]

            depth = DEPTH
            num_ring = 16
            num_arm = 8

            aper_start = self.surfaces[self.aper_idx].r * 0.25
            aper_final = self.surfaces[self.aper_idx].r

            optimizer = self.get_optimizer(lrs, optim_mat=optim_mat)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
                optimizer, T_0=max(1, iterations // 4), T_mult=1
            )

            pbar = tqdm(total=iterations + 1, desc="Curriculum", postfix={"loss_rms": 0})
            for i in range(iterations + 1):
                if i % test_per_iter == 0:
                    with torch.no_grad():
                        progress = 0.5 * (1 + math.cos(math.pi * (1 - i / max(1, iterations))))
                        aper_r = min(aper_start + (aper_final - aper_start) * progress, aper_final)
                        self.surfaces[self.aper_idx].update_r(aper_r)
                        self.calc_pupil()

                        if i > 0:
                            if shape_control:
                                self.correct_shape()
                            if optim_mat and match_mat:
                                self.match_materials()

                        self.write_lens_json(f"{result_dir}/iter{i}.json")

                        rays_backup = []
                        for wv in WAVE_RGB:
                            ray = self.sample_ring_arm_rays(
                                num_ring=num_ring,
                                num_arm=num_arm,
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
                w_focus = 0.1
                w_reg = 0.05
                loss_focus = self.loss_infocus()
                loss_reg, _loss_dict = self.loss_reg()
                total_loss = loss_rms + w_focus * loss_focus + w_reg * loss_reg

                optimizer.zero_grad()
                total_loss.backward()
                optimizer.step()
                scheduler.step()

                pbar.set_postfix(loss_rms=loss_rms.item())
                pbar.update(1)

            pbar.close()

        GeoLens.curriculum_design = curriculum_design

        if progress_cb:
            progress_cb("Action: 执行课程学习阶段")

        lens.curriculum_design(
            lrs=[float(v) for v in params.lrs],
            iterations=int(params.iterations),
            test_per_iter=int(params.test_per_iter),
            optim_mat=False,
            match_mat=False,
            shape_control=True,
            spp=int(params.spp),
            result_dir=str(result_dir),
        )

        lens.match_materials()
        lens.set_fnum(params.fnum)
        lens.write_lens_json(f"{result_dir}/curriculum.json")

        if progress_cb:
            progress_cb("Action: 执行微调阶段")

        lens = GeoLens(filename=f"{result_dir}/curriculum.json")
        lens.optimize(
            lrs=[float(v) * 0.1 for v in params.lrs],
            iterations=int(params.iterations),
            test_per_iter=int(params.test_per_iter),
            centroid=False,
            optim_mat=False,
            shape_control=True,
            result_dir=f"{result_dir}/fine-tune",
        )

        lens.prune_surf(expand_factor=0.05)
        lens.post_computation()
        lens.write_lens_json(f"{result_dir}/final.json")
        lens.analysis(save_name=f"{result_dir}/final")

        rfov = str(lens.rfov)
        fnum = float(lens.fnum)
        r_sensor = float(lens.r_sensor)

    curriculum_final = result_dir / "curriculum.json"
    final_json = result_dir / "final.json"
    _cleanup_intermediate_results(result_dir)

    if progress_cb:
        progress_cb("Observation: 设计完成，详细过程已写入日志文件")

    return {
        "result_dir": str(result_dir),
        "curriculum_json": str(curriculum_final),
        "final_json": str(final_json),
        "log_file": str(log_file),
        "rfov": rfov,
        "fnum": fnum,
        "r_sensor": r_sensor,
    }
