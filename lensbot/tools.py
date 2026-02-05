"""Lens design tools for the LensBot agent.

This module provides the core lens design functionality that the LLM agent
can call through function calling. Each tool is a self-contained operation.
"""

import os
import sys
import json
import math
import logging
import random
import string
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict

import torch
import numpy as np

# Add DeepLens to path
DEEPLENS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../DeepLens"))
if DEEPLENS_PATH not in sys.path:
    sys.path.insert(0, DEEPLENS_PATH)

from deeplens.geolens import GeoLens
from deeplens.geolens_pkg.utils import create_lens
from deeplens.basics import DEPTH, EPSILON, WAVE_RGB
from deeplens.utils import create_video_from_images, set_logger, set_seed

from .config import (
    LensSpecification,
    OptimizationConfig,
    LensBotConfig,
    get_surface_list_for_specs,
    LENS_PRESETS,
)


@dataclass
class ToolResult:
    """Standard result format for all tools."""
    success: bool
    message: str
    data: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def __str__(self) -> str:
        if self.success:
            return f"✅ {self.message}\n{json.dumps(self.data, indent=2, default=str)}" if self.data else f"✅ {self.message}"
        return f"❌ {self.message}"


class LensDesignTools:
    """Collection of lens design tools callable by the LLM agent."""
    
    def __init__(self, config: LensBotConfig = None):
        self.config = config or LensBotConfig()
        self.current_lens: Optional[GeoLens] = None
        self.current_spec: Optional[LensSpecification] = None
        self.design_history: List[Dict] = []
        self.result_dir: Optional[str] = None
        
        # Initialize device
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            logging.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            self.device = torch.device("cpu")
            logging.info("Using CPU")
    
    def _create_result_dir(self, prefix: str = "design") -> str:
        """Create a unique result directory."""
        characters = string.ascii_letters + string.digits
        random_string = "".join(random.choice(characters) for _ in range(4))
        current_time = datetime.now().strftime("%m%d-%H%M%S")
        exp_name = f"{current_time}-{prefix}-{random_string}"
        result_dir = os.path.join(self.config.result_dir, exp_name)
        os.makedirs(result_dir, exist_ok=True)
        return result_dir
    
    # =========================================================================
    # Tool 1: Create Lens Design
    # =========================================================================
    def create_lens_design(
        self,
        focal_length: float,
        fov: float,
        f_number: float,
        lens_type: str = "camera",
        preset: Optional[str] = None,
    ) -> ToolResult:
        """
        Create initial lens design with target specifications.
        
        Args:
            focal_length: Target focal length in mm
            fov: Diagonal field of view in degrees
            f_number: Target F-number
            lens_type: "camera" or "mobile"
            preset: Optional preset name to use (overrides other params)
            
        Returns:
            ToolResult with lens creation status and initial metrics
        """
        try:
            # Use preset if specified
            if preset and preset in LENS_PRESETS:
                preset_config = LENS_PRESETS[preset]
                focal_length = preset_config["focal_length"]
                fov = preset_config["fov"]
                f_number = preset_config["f_number"]
                lens_type = preset_config["lens_type"]
                surf_list = preset_config["surf_list"]
            else:
                # Create specification and generate surface list
                self.current_spec = LensSpecification(
                    focal_length=focal_length,
                    fov=fov,
                    f_number=f_number,
                    lens_type=lens_type,
                )
                surf_list = get_surface_list_for_specs(self.current_spec)
            
            # Create result directory
            self.result_dir = self._create_result_dir(
                f"f{int(focal_length)}mm_F{f_number}"
            )
            set_logger(self.result_dir)
            
            # Calculate derived parameters
            if lens_type == "mobile":
                flange = 1.0
                thickness = max(focal_length * 1.5, 8.0)
            else:
                flange = 18.0
                thickness = max(focal_length * 1.2, 50.0)
            
            # Create the lens
            self.current_lens = create_lens(
                foclen=focal_length,
                fov=fov,
                fnum=f_number,
                flange=flange,
                thickness=thickness,
                surf_list=surf_list,
                save_dir=self.result_dir,
            )
            
            self.current_lens.set_target_fov_fnum(
                rfov=fov / 2 / 57.3,
                fnum=f_number,
            )
            
            # Record in history
            self.design_history.append({
                "action": "create",
                "timestamp": datetime.now().isoformat(),
                "spec": {
                    "focal_length": focal_length,
                    "fov": fov,
                    "f_number": f_number,
                    "lens_type": lens_type,
                }
            })
            
            # Get initial metrics
            num_surfaces = len(self.current_lens.surfaces)
            
            return ToolResult(
                success=True,
                message=f"Created {lens_type} lens design: {focal_length}mm F/{f_number}",
                data={
                    "focal_length_mm": focal_length,
                    "fov_degrees": fov,
                    "f_number": f_number,
                    "lens_type": lens_type,
                    "num_surfaces": num_surfaces,
                    "result_dir": self.result_dir,
                    "status": "ready_for_optimization",
                }
            )
            
        except Exception as e:
            logging.error(f"Error creating lens: {e}")
            return ToolResult(
                success=False,
                message=f"Failed to create lens: {str(e)}"
            )
    
    # =========================================================================
    # Tool 2: Run Curriculum Optimization
    # =========================================================================
    def run_curriculum_optimization(
        self,
        iterations: int = 2000,
        learning_rates: Optional[List[float]] = None,
        optimize_materials: bool = True,
    ) -> ToolResult:
        """
        Run curriculum learning optimization on the current lens.
        
        This is the main optimization phase that gradually increases aperture
        size while optimizing the lens.
        
        Args:
            iterations: Number of optimization iterations
            learning_rates: Learning rates [curvature, thickness, aspheric, material]
            optimize_materials: Whether to optimize glass materials
            
        Returns:
            ToolResult with optimization metrics
        """
        if self.current_lens is None:
            return ToolResult(
                success=False,
                message="No lens design exists. Call create_lens_design first."
            )
        
        try:
            lrs = learning_rates or self.config.optimization.learning_rates
            
            # Bind curriculum design function to lens
            GeoLens.curriculum_design = curriculum_design
            
            # Run optimization
            logging.info(f"Starting curriculum optimization: {iterations} iterations")
            
            self.current_lens.curriculum_design(
                lrs=lrs,
                decay=self.config.optimization.decay,
                iterations=iterations,
                test_per_iter=max(50, iterations // 20),
                optim_mat=optimize_materials,
                match_mat=False,
                shape_control=True,
                result_dir=self.result_dir,
            )
            
            # Match materials and save
            self.current_lens.match_materials()
            self.current_lens.set_fnum(self.current_spec.f_number if self.current_spec else 4.0)
            self.current_lens.write_lens_json(f"{self.result_dir}/curriculum_final.json")
            
            # Evaluate result
            rms_avg = self._calculate_rms()
            
            self.design_history.append({
                "action": "curriculum_optimization",
                "timestamp": datetime.now().isoformat(),
                "iterations": iterations,
                "rms_avg_um": rms_avg,
            })
            
            return ToolResult(
                success=True,
                message=f"Curriculum optimization completed ({iterations} iterations)",
                data={
                    "iterations": iterations,
                    "rms_avg_um": round(rms_avg, 2),
                    "status": "curriculum_complete",
                    "saved_to": f"{self.result_dir}/curriculum_final.json",
                }
            )
            
        except Exception as e:
            logging.error(f"Optimization error: {e}")
            return ToolResult(
                success=False,
                message=f"Optimization failed: {str(e)}"
            )
    
    # =========================================================================
    # Tool 3: Run Fine-Tuning
    # =========================================================================
    def run_fine_tuning(
        self,
        iterations: int = 3000,
        learning_rate_scale: float = 0.1,
    ) -> ToolResult:
        """
        Fine-tune the lens with smaller learning rates for better performance.
        
        Should be called after curriculum optimization.
        
        Args:
            iterations: Number of fine-tuning iterations
            learning_rate_scale: Scale factor for learning rates (default 0.1x)
            
        Returns:
            ToolResult with fine-tuning metrics
        """
        if self.current_lens is None:
            return ToolResult(
                success=False,
                message="No lens design exists."
            )
        
        try:
            # Load the curriculum result
            curriculum_file = f"{self.result_dir}/curriculum_final.json"
            if not os.path.exists(curriculum_file):
                return ToolResult(
                    success=False,
                    message="Curriculum optimization not completed. Run curriculum optimization first."
                )
            
            self.current_lens = GeoLens(filename=curriculum_file)
            
            # Fine-tune with smaller learning rates
            lrs = [lr * learning_rate_scale for lr in self.config.optimization.learning_rates]
            finetune_dir = os.path.join(self.result_dir, "fine-tune")
            
            self.current_lens.optimize(
                lrs=lrs,
                decay=self.config.optimization.decay,
                iterations=iterations,
                test_per_iter=max(100, iterations // 30),
                centroid=False,
                optim_mat=False,
                shape_control=True,
                result_dir=finetune_dir,
            )
            
            # Post-processing
            self.current_lens.prune_surf(expand_factor=0.05)
            self.current_lens.post_computation()
            
            # Evaluate and save
            rms_avg = self._calculate_rms()
            
            self.current_lens.write_lens_json(f"{self.result_dir}/final_lens.json")
            self.current_lens.analysis(save_name=f"{self.result_dir}/final_lens")
            
            self.design_history.append({
                "action": "fine_tuning",
                "timestamp": datetime.now().isoformat(),
                "iterations": iterations,
                "rms_avg_um": rms_avg,
            })
            
            return ToolResult(
                success=True,
                message=f"Fine-tuning completed ({iterations} iterations)",
                data={
                    "iterations": iterations,
                    "rms_avg_um": round(rms_avg, 2),
                    "actual_fov": round(self.current_lens.rfov * 57.3 * 2, 1),
                    "actual_fnum": round(self.current_lens.fnum, 2),
                    "status": "design_complete",
                    "saved_to": f"{self.result_dir}/final_lens.json",
                }
            )
            
        except Exception as e:
            logging.error(f"Fine-tuning error: {e}")
            return ToolResult(
                success=False,
                message=f"Fine-tuning failed: {str(e)}"
            )
    
    # =========================================================================
    # Tool 4: Evaluate Lens Performance
    # =========================================================================
    def evaluate_lens_performance(self) -> ToolResult:
        """
        Evaluate current lens design performance.
        
        Returns:
            ToolResult with comprehensive performance metrics
        """
        if self.current_lens is None:
            return ToolResult(
                success=False,
                message="No lens design to evaluate."
            )
        
        try:
            with torch.no_grad():
                # RMS spot size
                rms_avg = self._calculate_rms()
                
                # Get lens properties
                self.current_lens.post_computation()
                
                # Distortion (approximate)
                distortion = 0.0
                try:
                    distortion = self.current_lens.calc_distortion_2D(
                        rfov=self.current_lens.rfov * 57.3,
                        wvln=0.587
                    )
                except:
                    pass
                
                # Create analysis images
                if self.result_dir:
                    self.current_lens.analysis(save_name=f"{self.result_dir}/evaluation")
                
                metrics = {
                    "rms_spot_um": round(rms_avg, 2),
                    "focal_length_mm": round(self.current_lens.foclen, 2),
                    "fov_degrees": round(self.current_lens.rfov * 57.3 * 2, 1),
                    "f_number": round(self.current_lens.fnum, 2),
                    "num_surfaces": len(self.current_lens.surfaces),
                    "distortion_percent": round(distortion * 100, 2),
                    "quality_rating": self._quality_rating(rms_avg),
                }
                
                return ToolResult(
                    success=True,
                    message="Lens performance evaluated",
                    data=metrics
                )
                
        except Exception as e:
            logging.error(f"Evaluation error: {e}")
            return ToolResult(
                success=False,
                message=f"Evaluation failed: {str(e)}"
            )
    
    # =========================================================================
    # Tool 5: Analyze Lens Structure
    # =========================================================================
    def analyze_lens_structure(self) -> ToolResult:
        """
        Analyze current lens structure (surfaces, materials, geometry).
        
        Returns:
            ToolResult with lens structure details
        """
        if self.current_lens is None:
            return ToolResult(
                success=False,
                message="No lens design to analyze."
            )
        
        try:
            surfaces_info = []
            for i, surf in enumerate(self.current_lens.surfaces):
                surf_type = type(surf).__name__
                info = {
                    "index": i,
                    "type": surf_type,
                    "radius": round(float(surf.r), 2) if hasattr(surf, 'r') else None,
                    "position_mm": round(float(surf.d), 2) if hasattr(surf, 'd') else None,
                }
                if hasattr(surf, 'mat2') and surf.mat2 is not None:
                    info["material"] = str(surf.mat2.name) if hasattr(surf.mat2, 'name') else str(surf.mat2)
                surfaces_info.append(info)
            
            return ToolResult(
                success=True,
                message=f"Lens has {len(surfaces_info)} surfaces",
                data={
                    "total_surfaces": len(surfaces_info),
                    "surfaces": surfaces_info,
                    "total_length_mm": round(float(self.current_lens.d_sensor), 2),
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Analysis failed: {str(e)}"
            )
    
    # =========================================================================
    # Tool 6: Adjust Design Parameters
    # =========================================================================
    def adjust_design_parameters(
        self,
        curriculum_iterations: Optional[int] = None,
        finetune_iterations: Optional[int] = None,
        learning_rate_scale: Optional[float] = None,
    ) -> ToolResult:
        """
        Adjust optimization parameters for the next run.
        
        Args:
            curriculum_iterations: New iteration count for curriculum phase
            finetune_iterations: New iteration count for fine-tuning
            learning_rate_scale: Scale factor for learning rates
            
        Returns:
            ToolResult with updated configuration
        """
        try:
            if curriculum_iterations:
                self.config.optimization.curriculum_iterations = curriculum_iterations
            if finetune_iterations:
                self.config.optimization.finetune_iterations = finetune_iterations
            if learning_rate_scale:
                self.config.optimization.learning_rates = [
                    lr * learning_rate_scale 
                    for lr in [1e-3, 1e-4, 1e-2, 1e-4]
                ]
            
            return ToolResult(
                success=True,
                message="Optimization parameters updated",
                data={
                    "curriculum_iterations": self.config.optimization.curriculum_iterations,
                    "finetune_iterations": self.config.optimization.finetune_iterations,
                    "learning_rates": self.config.optimization.learning_rates,
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to update parameters: {str(e)}"
            )
    
    # =========================================================================
    # Tool 7: Export Lens
    # =========================================================================
    def export_lens(self, format: str = "json") -> ToolResult:
        """
        Export the current lens design to file.
        
        Args:
            format: Export format ("json" or "zemax")
            
        Returns:
            ToolResult with export file path
        """
        if self.current_lens is None:
            return ToolResult(
                success=False,
                message="No lens design to export."
            )
        
        try:
            if format == "json":
                filename = f"{self.result_dir}/exported_lens.json"
                self.current_lens.write_lens_json(filename)
            else:
                return ToolResult(
                    success=False,
                    message=f"Unsupported format: {format}. Use 'json'."
                )
            
            return ToolResult(
                success=True,
                message=f"Lens exported to {format.upper()} format",
                data={
                    "file_path": filename,
                    "format": format,
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Export failed: {str(e)}"
            )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    def _calculate_rms(self) -> float:
        """Calculate average RMS spot size in micrometers."""
        try:
            with torch.no_grad():
                rms_total = 0.0
                count = 0
                for wv in WAVE_RGB:
                    ray = self.current_lens.sample_radial_rays(
                        num_field=5,
                        depth=DEPTH,
                        num_rays=2048,
                        wvln=wv,
                    )
                    ray = self.current_lens.trace2sensor(ray)
                    
                    # Calculate RMS per field
                    ray_xy = ray.o[..., :2]
                    ray_valid = ray.is_valid
                    center = (ray_xy * ray_valid.unsqueeze(-1)).sum(dim=-2)
                    center = center / (ray_valid.sum(dim=-1, keepdim=True) + EPSILON)
                    
                    err = ray_xy - center.unsqueeze(-2)
                    rms = ((err**2).sum(-1) * ray_valid).sum(-1)
                    rms = rms / (ray_valid.sum(-1) + EPSILON)
                    rms = rms.sqrt().mean()
                    
                    rms_total += rms.item()
                    count += 1
                
                return (rms_total / count) * 1000  # Convert to micrometers
        except:
            return 999.0
    
    def _quality_rating(self, rms_um: float) -> str:
        """Rate lens quality based on RMS spot size."""
        if rms_um < 5:
            return "Excellent (diffraction-limited)"
        elif rms_um < 15:
            return "Good"
        elif rms_um < 30:
            return "Acceptable"
        elif rms_um < 50:
            return "Needs improvement"
        else:
            return "Poor - requires more optimization"
    
    def get_design_history(self) -> List[Dict]:
        """Return the design history."""
        return self.design_history
    
    def get_available_presets(self) -> Dict[str, str]:
        """Return available lens presets."""
        return {k: v["name"] for k, v in LENS_PRESETS.items()}


# =============================================================================
# Curriculum Design Function (from DeepLens)
# =============================================================================
def curriculum_design(
    self: GeoLens,
    lrs=[1e-4, 1e-4, 1e-2, 1e-4],
    decay=0.01,
    iterations=5000,
    test_per_iter=100,
    optim_mat=False,
    match_mat=False,
    shape_control=True,
    result_dir="./results",
):
    """Optimize the lens by minimizing RMS errors with curriculum learning."""
    from tqdm import tqdm
    
    depth = DEPTH
    num_ring = 8
    num_arm = 8
    spp = 2048

    aper_start = self.surfaces[self.aper_idx].r * 0.2
    aper_final = self.surfaces[self.aper_idx].r

    if not logging.getLogger().hasHandlers():
        set_logger(result_dir)
    logging.info(
        f"lr:{lrs}, iterations:{iterations}, spp:{spp}, num_ring:{num_ring}, num_arm:{num_arm}."
    )

    optimizer = self.get_optimizer(lrs, decay=decay, optim_mat=optim_mat)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=iterations)

    pbar = tqdm(
        total=iterations + 1, desc="Curriculum Learning", postfix={"loss_rms": 0, "loss_reg": 0}
    )
    
    for i in range(iterations + 1):
        if i % test_per_iter == 0:
            with torch.no_grad():
                progress = 0.5 * (1 + math.cos(math.pi * (1 - i / iterations)))
                aper_r = min(
                    aper_start + (aper_final - aper_start) * progress,
                    aper_final,
                )
                self.surfaces[self.aper_idx].update_r(aper_r)
                self.calc_pupil()

                if i > 0:
                    if shape_control:
                        self.correct_shape()

                    if optim_mat and match_mat:
                        self.match_materials()

                self.write_lens_json(f"{result_dir}/iter{i}.json")
                self.analysis(f"{result_dir}/iter{i}")

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
        for wv_idx, wv in enumerate(WAVE_RGB):
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

                    dropout_mask = torch.rand_like(weight_mask) < 0.2
                    weight_mask = weight_mask * (~dropout_mask)

            l_rms = (((ray_err**2).sum(-1) + EPSILON).sqrt() * ray_valid).sum(-1)
            l_rms /= ray_valid.sum(-1) + EPSILON

            l_rms_weighted = (l_rms * weight_mask).sum()
            l_rms_weighted /= weight_mask.sum() + EPSILON
            loss_rms.append(l_rms_weighted)

        loss_rms = sum(loss_rms) / len(loss_rms)

        loss_reg, loss_dict = self.loss_reg()
        w_reg = 0.05
        L_total = loss_rms + w_reg * loss_reg

        optimizer.zero_grad()
        L_total.backward()
        optimizer.step()
        scheduler.step()

        pbar.set_postfix(loss_rms=loss_rms.item(), **loss_dict)
        pbar.update(1)

    pbar.close()
