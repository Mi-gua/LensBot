from __future__ import annotations

import json
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from engine.deeplens.autolens_rms import (
    DEEPLENS_ORIGINAL_LRS,
    _deeplens_cosine_schedule_with_warmup,
    patch_zmx_export_from_final_json,
    prune_lens_surfaces,
)
from engine.deeplens.runtime import ensure_deeplens_import
from runtime.artifacts import refresh_run_manifest
from runtime.result import ResultWorkspace
from subagents.types import LensDesignParams, public_params_dict


ProgressCallback = Callable[[str], None]
ArtifactCallback = Callable[[str], None]


@dataclass
class SessionStrategy:
    lr_scale: float = 1.0
    rollback_count: int = 0
    notes: list[str] = field(default_factory=list)


class DeepLensOptimizationSession:
    """Chunked DeepLens optimizer that preserves the original loss path by default."""

    def __init__(
        self,
        *,
        params: LensDesignParams,
        result_dir: Path,
        session_id: str | None = None,
        progress_cb: ProgressCallback | None = None,
        artifact_cb: ArtifactCallback | None = None,
    ) -> None:
        self.params = params
        self.result_dir = result_dir
        self.workspace = ResultWorkspace.from_result_dir(result_dir)
        attempt_index = self._next_attempt_index()
        self.curriculum_dir = self.workspace.deeplens_attempt_dir("curriculum", attempt_index)
        self.finetune_dir = self.workspace.deeplens_attempt_dir("finetune", attempt_index + 1)
        self.curriculum_dir.mkdir(parents=True, exist_ok=False)
        self.finetune_dir.mkdir(parents=True, exist_ok=False)
        self.session_id = session_id or uuid.uuid4().hex[:10]
        self.progress_cb = progress_cb
        self.artifact_cb = artifact_cb
        self.phase = "created"
        self.curriculum_iter = 0
        self.fine_tune_iter = 0
        self.strategy = SessionStrategy(lr_scale=float(params.lr_scale))
        self.checkpoints: list[dict[str, Any]] = []
        self.last_losses: dict[str, float] = {}
        self.last_diagnostics: dict[str, Any] = {}
        self.last_strategy: dict[str, Any] = {"action": "idle", "reason": "session created"}
        self.last_candidate: dict[str, Any] | None = None
        self.last_execution: dict[str, Any] = {}

        self.lens: Any = None
        self.optimizer: Any = None
        self.scheduler: Any = None
        self._torch: Any = None
        self._softplus: Any = None
        self._GeoLens: Any = None
        self._DEPTH: Any = None
        self._EPSILON: float = 1e-8
        self._WAVE_RGB: Any = None
        self._aper_start: float | None = None
        self._aper_final: float | None = None
        self._curriculum_rays: list[Any] | None = None
        self._curriculum_center_ref: Any = None
        self._fine_tune_rays: list[Any] | None = None
        self._fine_tune_pinhole_ref: Any = None

    def attach_callbacks(
        self,
        *,
        progress_cb: ProgressCallback | None = None,
        artifact_cb: ArtifactCallback | None = None,
    ) -> None:
        self.progress_cb = progress_cb or self.progress_cb
        self.artifact_cb = artifact_cb or self.artifact_cb

    def start(self) -> dict[str, Any]:
        self._load_deeplens()
        self.workspace.ensure()
        (self.curriculum_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
        (self.finetune_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

        from deeplens.utils import set_seed

        if self.params.seed is None:
            self.params.seed = random.randint(0, 100000)
        set_seed(self.params.seed)
        logging.info("EXP: %s", self.params.exp_name)
        logging.info("Seed: %s", self.params.seed)

        self.lens = self._create_lens()
        self.lens.set_target_fov_fnum(rfov=self.params.fov / 2 / 57.3, fnum=self.params.fnum)
        self.phase = "curriculum"
        self._init_curriculum_optimizer()
        self._write_lens_artifact(self.curriculum_dir / "starting-point")
        self._write_checkpoint("starting-point")
        self._archive_state()
        self._emit_artifact()
        return self.describe()

    def run_curriculum_chunk(self, iteration_count: int) -> dict[str, Any]:
        if self.phase != "curriculum":
            return self.describe()
        total = max(1, int(self.params.curriculum.iterations))
        remaining = max(0, total - self.curriculum_iter)
        iteration_count = min(max(1, int(iteration_count)), remaining)

        for _ in range(iteration_count):
            i = self.curriculum_iter
            if i >= total:
                break
            if i % int(self.params.curriculum.test_per_iter) == 0 or i == total - 1 or self._curriculum_rays is None:
                self._prepare_curriculum_checkpoint(i)
            self._curriculum_step()
            self.curriculum_iter += 1

        if self.curriculum_iter >= total:
            self._finish_curriculum()

        self._archive_state()
        return self.describe()

    def _run_finetune_steps(self, iteration_count: int) -> int:
        if self.phase != "fine_tune":
            raise RuntimeError(f"Fine-tune steps require phase=fine_tune, received {self.phase}.")
        iteration_count = int(iteration_count)
        if iteration_count < 1:
            raise ValueError("Fine-tune iterations must be a positive integer.")

        for _ in range(iteration_count):
            i = self.fine_tune_iter
            if i % int(self.params.fine_tune.test_per_iter) == 0 or self._fine_tune_rays is None:
                self._prepare_fine_tune_checkpoint(i)
            self._fine_tune_step()
            self.fine_tune_iter += 1

        self.phase = "ready_to_finalize"
        self._archive_state()
        return iteration_count

    def inspect_checkpoint(self) -> dict[str, Any]:
        diagnostics = self._diagnostics()
        self.last_diagnostics = diagnostics
        self._archive_state()
        return diagnostics

    def adjust_strategy(self, strategy: dict[str, Any]) -> dict[str, Any]:
        action = str(strategy.get("action") or "")
        result = {**strategy, "applied": False}
        if action == "reduce_lr":
            old_scale = self.strategy.lr_scale
            new_scale = max(0.1, old_scale * 0.5)
            if new_scale < old_scale:
                self.strategy.lr_scale = new_scale
                self._scale_optimizer_lr(new_scale / old_scale)
                self.strategy.notes.append("Reduced learning rate scale.")
                result.update({
                    "applied": True,
                    "effect_scope": "current_optimizer" if self.phase in {"curriculum", "fine_tune"} else "next_optimizer_pass",
                })
            else:
                result["effect_scope"] = "none"
        elif action == "rollback_to_best_checkpoint":
            if self.phase not in {"curriculum", "fine_tune"}:
                raise ValueError(f"Rollback requires an active optimizer phase, received {self.phase}.")
            rolled = self._rollback_to_best_checkpoint()
            if not rolled:
                raise ValueError("Rollback found no compatible checkpoint for the active phase.")
            self.strategy.rollback_count += 1
            self.strategy.notes.append("Rolled back to best stable checkpoint.")
            result.update({"applied": True, "effect_scope": "current_optimizer"})
        else:
            raise ValueError(f"Unsupported strategy action: {action}")
        self.last_strategy = result
        self._archive_state()
        return self.describe()

    def run_finetune(self, source_lens: str | Path | None = None) -> dict[str, Any]:
        """Execute a pass, then export. Repeated calls refine the last candidate.

        An exported prescription is a new pass with fresh optimizer/scheduler,
        not continuation of stale optimizer state after pruning/material changes.
        """
        iterations_requested = int(self.params.fine_tune.iterations)
        if iterations_requested < 1:
            raise ValueError("Fine-tune iterations must be a positive integer.")
        phase_before = self.phase
        if source_lens is None and self.phase == "candidate_exported":
            if self.last_candidate is None:
                raise ValueError("Exported session has no recorded candidate source.")
            source_lens = self.last_candidate["candidate_json"]
        if source_lens is not None:
            source_lens = Path(source_lens)
            if not source_lens.is_file():
                raise ValueError(f"Fine-tune source does not exist: {source_lens}")
            self._load_deeplens()
            self.workspace.ensure()
            self._init_fine_tune(source_lens=source_lens, attempt_stage="refine")
        elif self.phase == "curriculum_complete":
            self._init_fine_tune()
        elif self.phase != "fine_tune":
            raise ValueError(f"Cannot fine-tune session in phase {self.phase}; supply a lens artifact.")

        executed = self._run_finetune_steps(iterations_requested)
        self.last_execution = {
            "phase_before": phase_before,
            "source_lens": str(source_lens or (self.curriculum_dir / "curriculum.json")),
            "iterations_requested": iterations_requested,
            "iterations_executed": executed,
            "lr_scale": self.strategy.lr_scale,
            "optimizer_reinitialized": phase_before != "fine_tune" or source_lens is not None,
        }
        return {**self.export_candidate(), **self.last_execution}

    def export_candidate(self) -> dict[str, Any]:
        """Export a completed pass once; never perform optimization here."""
        if self.phase == "candidate_exported" and self.last_candidate is not None:
            return dict(self.last_candidate)
        if self.phase != "ready_to_finalize":
            raise ValueError(f"Cannot export unfinished session in phase {self.phase}.")
        if not self.last_execution:
            raise ValueError("Cannot export a candidate without a completed optimizer pass.")

        prune_lens_surfaces(self.lens)
        self.lens.post_computation()
        candidate_dir = self.workspace.candidate_dir(self._next_candidate_index())
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_json = candidate_dir / "lens.json"
        candidate_zmx = candidate_dir / "lens.zmx"
        self.lens.write_lens_json(str(candidate_json))
        self.lens.write_lens_zmx(str(candidate_zmx))
        patch_zmx_export_from_final_json(candidate_json, candidate_zmx)
        self.lens.analysis(save_name=str(candidate_dir / "lens"))
        self.phase = "candidate_exported"
        self._emit_artifact()
        self.last_candidate = {
            **self.describe(),
            "curriculum_json": str(self.curriculum_dir / "curriculum.json"),
            "candidate_id": candidate_dir.name,
            "candidate_json": str(candidate_json),
            "candidate_zmx": str(candidate_zmx),
            "candidate_png": str(candidate_dir / "lens.png"),
            "rfov": str(self.lens.rfov),
            "rfov_deg": float(math.degrees(float(self.lens.rfov))),
            "fov_deg": float(2.0 * math.degrees(float(self.lens.rfov))),
            "fnum": float(self.lens.fnum),
            "r_sensor": float(self.lens.r_sensor),
            "structure_group_count": len(self.params.surf_list),
        }
        execution = {
            "candidate_id": candidate_dir.name,
            "candidate_json": str(candidate_json.resolve()),
            "optimizer_pass_id": f"{self.session_id}/{candidate_dir.name}",
            "source_lens": self.last_execution.get("source_lens"),
            "iterations_requested": self.last_execution.get("iterations_requested"),
            "iterations_executed": self.last_execution.get("iterations_executed"),
            "lr_scale": self.last_execution.get("lr_scale"),
            "optimizer_reinitialized": self.last_execution.get("optimizer_reinitialized"),
        }
        (candidate_dir / "execution.json").write_text(
            json.dumps(execution, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.last_candidate["execution"] = execution
        self._archive_state()
        (candidate_dir / "session.json").write_text(
            json.dumps(self.describe(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return dict(self.last_candidate)

    def refine_from_lens(self, source_lens: str | Path) -> dict[str, Any]:
        """Start a new fine-tune pass from an explicit clean lens artifact."""
        return self.run_finetune(source_lens)

    def describe(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "result_dir": str(self.result_dir),
            "phase": self.phase,
            "curriculum_iter": self.curriculum_iter,
            "fine_tune_iter": self.fine_tune_iter,
            "curriculum_total": int(self.params.curriculum.iterations),
            "fine_tune_total": int(self.params.fine_tune.iterations),
            "strategy": {
                "lr_scale": self.strategy.lr_scale,
                "rollback_count": self.strategy.rollback_count,
                "notes": self.strategy.notes[-5:],
            },
            "checkpoints": self.checkpoints[-8:],
            "last_losses": self.last_losses,
            "last_diagnostics": self.last_diagnostics,
            "last_strategy": self.last_strategy,
            "last_execution": dict(self.last_execution),
            "last_candidate_json": self.last_candidate.get("candidate_json") if self.last_candidate else None,
            "params": public_params_dict(self.params),
        }

    def _load_deeplens(self) -> None:
        ensure_deeplens_import(Path(__file__))
        import torch
        from torch.nn.functional import softplus

        try:
            from deeplens.optics import GeoLens
            from deeplens.optics.config import DEPTH, EPSILON, WAVE_RGB
            from deeplens.optics.geolens_pkg.utils import create_lens
        except ModuleNotFoundError:
            from deeplens import GeoLens
            from deeplens.config import DEPTH, EPSILON, WAVE_RGB
            from deeplens.geolens_pkg.optim_init import create_lens

        self._torch = torch
        self._softplus = softplus
        self._GeoLens = GeoLens
        self._DEPTH = DEPTH
        self._EPSILON = EPSILON
        self._WAVE_RGB = WAVE_RGB
        self._create_lens_fn = create_lens

    def _create_lens(self) -> Any:
        return self._create_lens_fn(
            foclen=self.params.foclen,
            fov=self.params.fov,
            fnum=self.params.fnum,
            bfl=self.params.bfl,
            thickness=self.params.thickness,
            surf_list=self.params.surf_list,
            save_dir=str(self.curriculum_dir),
        )

    def _init_curriculum_optimizer(self) -> None:
        lrs = [lr * self.strategy.lr_scale for lr in DEEPLENS_ORIGINAL_LRS]
        self.optimizer = self.lens.get_optimizer(lrs, optim_mat=True)
        total = max(1, int(self.params.curriculum.iterations))
        self.scheduler = self._torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer, T_0=max(1, total // 4), T_mult=1
        )
        self._aper_start = float(self.lens.surfaces[self.lens.aper_idx].r) * 0.25
        self._aper_final = float(self.lens.surfaces[self.lens.aper_idx].r)

    def _init_fine_tune(self, source_lens: Path | None = None, attempt_stage: str = "finetune") -> None:
        self.lens = self._GeoLens(filename=str(source_lens or (self.curriculum_dir / "curriculum.json")))
        self._init_fine_tune_from_loaded_lens(attempt_stage=attempt_stage)

    def _init_fine_tune_from_loaded_lens(self, attempt_stage: str = "finetune") -> None:
        if attempt_stage != "finetune":
            self.finetune_dir = self.workspace.deeplens_attempt_dir(attempt_stage, self._next_attempt_index())
            (self.finetune_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
        self.lens.set_target_fov_fnum(rfov=self.params.fov / 2 / 57.3, fnum=self.params.fnum)
        self.lens.set_fnum(self.params.fnum)
        lrs = [lr * self.strategy.lr_scale for lr in DEEPLENS_ORIGINAL_LRS]
        self.optimizer = self.lens.get_optimizer(lrs, optim_mat=False)
        total = max(1, int(self.params.fine_tune.iterations))
        self.scheduler = _deeplens_cosine_schedule_with_warmup(
            self.optimizer,
            num_warmup_steps=min(100, total),
            num_training_steps=total,
        )
        self._fine_tune_rays = None
        self._fine_tune_pinhole_ref = None
        self.fine_tune_iter = 0
        self.phase = "fine_tune"

    def _next_attempt_index(self) -> int:
        attempts_root = self.workspace.deeplens_dir / "attempts"
        indices: list[int] = []
        for path in attempts_root.glob("attempt-*"):
            parts = path.name.split("-", 2)
            if len(parts) >= 2:
                try:
                    indices.append(int(parts[1]))
                except ValueError:
                    pass
        return (max(indices) + 1) if indices else 1

    def _next_candidate_index(self) -> int:
        indices: list[int] = []
        for path in self.workspace.candidates_dir.glob("candidate-*"):
            try:
                indices.append(int(path.name.split("-", 1)[1]))
            except (IndexError, ValueError):
                pass
        return (max(indices) + 1) if indices else 1

    def _prepare_curriculum_checkpoint(self, i: int) -> None:
        total = max(1, int(self.params.curriculum.iterations))
        with self._torch.no_grad():
            fraction = i / (total - 1) if total > 1 else 1.0
            progress = 0.5 * (1 + math.cos(math.pi * (1 - fraction)))
            aper_r = min(self._aper_start + (self._aper_final - self._aper_start) * progress, self._aper_final)
            self.lens.surfaces[self.lens.aper_idx].update_r(aper_r)
            self.lens.calc_pupil()
            if i > 0:
                self.lens.correct_shape()
            self._write_lens_artifact(self.workspace.deeplens_live_dir / "current")
            self._write_checkpoint(f"curriculum_{i:06d}")
            self._archive_state()
            self._curriculum_rays = []
            for wv in self._WAVE_RGB:
                ray = self.lens.sample_ring_arm_rays(
                    num_ring=int(self.params.curriculum.num_ring),
                    num_arm=int(self.params.curriculum.num_arm),
                    depth=self._DEPTH,
                    spp=int(self.params.curriculum.spp),
                    wvln=wv,
                    scale_pupil=1.10,
                )
                self._curriculum_rays.append(ray)
            ray = self._curriculum_rays[-1]
            self._curriculum_center_ref = -self.lens.psf_center(points_obj=ray.o[:, :, 0, :], method="pinhole")
            self._curriculum_center_ref = self._curriculum_center_ref.unsqueeze(-2).repeat(
                1, 1, int(self.params.curriculum.spp), 1
            )

    def _curriculum_step(self) -> None:
        loss_rms = []
        weight_mask = None
        for wv_idx, _wv in enumerate(self._WAVE_RGB):
            ray = self._curriculum_rays[wv_idx].clone()
            ray = self.lens.trace2sensor(ray)
            ray_xy = ray.o[..., :2]
            ray_valid = ray.is_valid
            ray_err = ray_xy - self._curriculum_center_ref
            if wv_idx == 0:
                with self._torch.no_grad():
                    weight_mask = ((ray_err**2).sum(-1) * ray_valid).sum(-1)
                    weight_mask /= ray_valid.sum(-1) + self._EPSILON
                    weight_mask /= weight_mask.mean()
                    dropout_mask = self._torch.rand_like(weight_mask) < 0.1
                    weight_mask = weight_mask * (~dropout_mask)
            l_rms = ((ray_err**2).sum(-1) * ray_valid).sum(-1)
            l_rms /= ray_valid.sum(-1) + self._EPSILON
            l_rms = (l_rms + self._EPSILON).sqrt()
            l_rms_weighted = (l_rms * weight_mask).sum()
            l_rms_weighted /= weight_mask.sum() + self._EPSILON
            loss_rms.append(l_rms_weighted)

        loss_rms_value = sum(loss_rms) / len(loss_rms)
        loss_focus = self.lens.loss_infocus()
        loss_reg, _loss_dict = self.lens.loss_reg()
        total_loss = (
            loss_rms_value
            + 0.1 * loss_focus
            + 0.05 * loss_reg
        )
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()
        self.scheduler.step()
        self.last_losses = {
            "loss_rms": float(loss_rms_value.item()),
            "loss_focus": float(loss_focus.item()),
            "loss_reg": float(loss_reg.item()),
            "total_loss": float(total_loss.item()),
        }

    def _finish_curriculum(self) -> None:
        self.lens.match_materials()
        self.lens.set_fnum(self.params.fnum)
        self.lens.write_lens_json(str(self.curriculum_dir / "curriculum.json"))
        self.lens.analysis(save_name=str(self.curriculum_dir / "curriculum"))
        self._emit_artifact()
        self.phase = "curriculum_complete"

    def _prepare_fine_tune_checkpoint(self, i: int) -> None:
        with self._torch.no_grad():
            if i > 0:
                self.lens.correct_shape()
            self._write_lens_artifact(self.workspace.deeplens_live_dir / "current")
            self._write_checkpoint(f"finetune_{i:06d}")
            self._archive_state()
            self.lens.calc_pupil()
            self._fine_tune_rays = []
            for wv in self.lens.wvln_rgb:
                ray = self.lens.sample_ring_arm_rays(
                    num_ring=int(self.params.fine_tune.num_ring),
                    num_arm=int(self.params.fine_tune.num_arm),
                    spp=int(self.params.fine_tune.spp),
                    depth=self.lens.obj_depth,
                    wvln=wv,
                    scale_pupil=1.05,
                    sample_more_off_axis=False,
                )
                self._fine_tune_rays.append(ray)
            ray = self._fine_tune_rays[-1]
            self._fine_tune_pinhole_ref = -self.lens.psf_center(points_obj=ray.o[:, :, 0, :], method="pinhole")

    def _fine_tune_step(self) -> None:
        loss_rms_ls = []
        loss_distortion = self._torch.tensor(0.0, device=self.lens.device)
        weight_mask = None
        center_ref = None
        for wv_idx in [1, 0, 2]:
            ray = self._fine_tune_rays[wv_idx].clone()
            ray = self.lens.trace2sensor(ray)
            if center_ref is None:
                centroid_xy = ray.centroid()[..., :2]
                ideal_height = self._fine_tune_pinhole_ref.norm(dim=-1)
                field_mask = ideal_height > self._EPSILON
                distortion = (centroid_xy - self._fine_tune_pinhole_ref).norm(dim=-1)
                distortion = distortion / ideal_height.clamp_min(self._EPSILON)
                violation = distortion - self.lens.distortion_max
                penalty = self._softplus(violation / self.lens.distortion_max, beta=20.0)
                n_fields = field_mask.sum().clamp_min(1)
                loss_distortion = (penalty * field_mask.float()).sum() / n_fields
                center_ref = centroid_xy.detach().unsqueeze(-2)

            ray_valid = ray.is_valid
            ray_err = ray.o[..., :2] - center_ref
            ray_err = self._torch.where(ray_valid.bool().unsqueeze(-1), ray_err, self._torch.zeros_like(ray_err))
            mse = (ray_err**2).sum(-1).sum(-1) / (ray_valid.sum(-1) + self._EPSILON)
            if weight_mask is None:
                weight_mask = mse.detach().sqrt().clone()
                weight_mask = weight_mask / (weight_mask.mean() + self._EPSILON)
                weight_mask[0, :] = 1.0
            l_rms = self._torch.clamp(mse, min=self._EPSILON).sqrt()
            l_rms_weighted = (l_rms * weight_mask).sum()
            l_rms_weighted /= weight_mask.sum() + self._EPSILON
            loss_rms_ls.append(l_rms_weighted)

        loss_rms = sum(loss_rms_ls) / len(loss_rms_ls)
        loss_reg, loss_dict = self.lens.loss_reg()
        total_loss = loss_rms + 0.1 * (loss_reg + loss_distortion)
        self.optimizer.zero_grad()
        total_loss.backward()
        self.optimizer.step()
        self.scheduler.step()
        self.last_losses = {
            "loss_rms": float(loss_rms.item()),
            "loss_distortion": float(loss_distortion.item()),
            "loss_reg": float(loss_reg.item()),
            "total_loss": float(total_loss.item()),
            **{key: float(value) for key, value in loss_dict.items() if hasattr(value, "__float__")},
        }

    def _diagnostics(self) -> dict[str, Any]:
        efl = self._safe_float(getattr(self.lens, "foclen", None))
        fnum = self._safe_float(getattr(self.lens, "fnum", None))
        rfov = self._safe_float(getattr(self.lens, "rfov", None))
        fov_deg = None if rfov is None else 2.0 * math.degrees(rfov)
        diagnostics = {
            "session_id": self.session_id,
            "phase": self.phase,
            "curriculum_iter": self.curriculum_iter,
            "fine_tune_iter": self.fine_tune_iter,
            "efl_mm": efl,
            "fnum": fnum,
            "fov_deg": fov_deg,
            "efl_drift": self._drift(efl, self.params.foclen),
            "fnum_drift": self._drift(fnum, self.params.fnum),
            "fov_drift": self._drift(fov_deg, self.params.fov),
            "last_losses": self.last_losses,
            "strategy": self.describe()["strategy"],
        }
        return diagnostics

    def _write_checkpoint(self, name: str) -> Path:
        checkpoint_root = self.finetune_dir if name.startswith("finetune") or self.phase == "fine_tune" else self.curriculum_dir
        path = checkpoint_root / "checkpoints" / f"{name}.json"
        self.lens.write_lens_json(str(path))
        self.checkpoints.append(
            {
                "name": name,
                "path": str(path),
                "phase": self.phase,
                "curriculum_iter": self.curriculum_iter,
                "fine_tune_iter": self.fine_tune_iter,
                "diagnostics": self._diagnostics_minimal(),
            }
        )
        return path

    def _write_lens_artifact(self, base_path: Path) -> None:
        self.lens.write_lens_json(str(base_path.with_suffix(".json")))
        self.lens.analysis(str(base_path))
        self._emit_artifact()

    def _diagnostics_minimal(self) -> dict[str, Any]:
        efl = self._safe_float(getattr(self.lens, "foclen", None))
        fnum = self._safe_float(getattr(self.lens, "fnum", None))
        rfov = self._safe_float(getattr(self.lens, "rfov", None))
        fov_deg = None if rfov is None else 2.0 * math.degrees(rfov)
        return {
            "efl_drift": self._drift(efl, self.params.foclen),
            "fnum_drift": self._drift(fnum, self.params.fnum),
            "fov_drift": self._drift(fov_deg, self.params.fov),
        }

    def _rollback_to_best_checkpoint(self) -> bool:
        candidates = [item for item in self.checkpoints if item.get("phase") == self.phase]
        if not candidates:
            return False

        def score(item: dict[str, Any]) -> float:
            diagnostics = item.get("diagnostics") or {}
            values = [
                diagnostics.get("efl_drift"),
                diagnostics.get("fnum_drift"),
                diagnostics.get("fov_drift"),
            ]
            return sum(float(value) for value in values if value is not None)

        best = min(candidates, key=score)
        path = Path(str(best.get("path")))
        if not path.exists():
            return False
        self.lens = self._GeoLens(filename=str(path))
        self.lens.set_target_fov_fnum(rfov=self.params.fov / 2 / 57.3, fnum=self.params.fnum)
        self.curriculum_iter = int(best.get("curriculum_iter") or self.curriculum_iter)
        self.fine_tune_iter = int(best.get("fine_tune_iter") or self.fine_tune_iter)
        if self.phase == "curriculum":
            self._init_curriculum_optimizer()
            self._curriculum_rays = None
        elif self.phase == "fine_tune":
            self.optimizer = self.lens.get_optimizer(
                [lr * self.strategy.lr_scale for lr in DEEPLENS_ORIGINAL_LRS],
                optim_mat=False,
            )
            self.scheduler = _deeplens_cosine_schedule_with_warmup(
                self.optimizer,
                num_warmup_steps=min(100, max(1, int(self.params.fine_tune.iterations))),
                num_training_steps=max(1, int(self.params.fine_tune.iterations)),
            )
            self._fine_tune_rays = None
        return True

    def _scale_optimizer_lr(self, scale: float) -> None:
        if self.optimizer is None:
            return
        for group in self.optimizer.param_groups:
            group["lr"] = float(group.get("lr", 0.0)) * scale

    def _archive_state(self, extra: dict[str, Any] | None = None) -> None:
        payload = self.describe()
        if extra:
            payload.update(extra)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        for directory in (self.curriculum_dir, self.finetune_dir, self.workspace.deeplens_dir):
            (directory / "session.json").write_text(text, encoding="utf-8")

    def _emit_artifact(self) -> None:
        refresh_run_manifest(
            self.result_dir,
            params=public_params_dict(self.params),
            phase=self.phase,
        )
        if self.artifact_cb:
            self.artifact_cb(str(self.result_dir))

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _drift(value: float | None, target: float) -> float | None:
        if value is None or target <= 0:
            return None
        return abs(value - target) / target
