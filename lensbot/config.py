"""Configuration management for LensBot."""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LensSpecification:
    """Target lens specification from user requirements."""
    focal_length: float  # mm
    fov: float  # degrees (diagonal)
    f_number: float
    lens_type: str = "camera"  # camera, mobile, wide_angle
    flange: Optional[float] = None  # mm, auto-calculated if not specified
    thickness: Optional[float] = None  # mm, auto-calculated if not specified
    
    def __post_init__(self):
        """Auto-calculate defaults based on lens type."""
        if self.lens_type == "mobile":
            self.flange = self.flange or 1.0
            self.thickness = self.thickness or max(self.focal_length * 1.5, 8.0)
        else:  # camera lens
            self.flange = self.flange or 18.0
            self.thickness = self.thickness or max(self.focal_length * 1.2, 50.0)


@dataclass
class OptimizationConfig:
    """Optimization hyperparameters."""
    curriculum_iterations: int = 2000
    finetune_iterations: int = 3000
    test_per_iter: int = 100
    learning_rates: List[float] = field(default_factory=lambda: [1e-3, 1e-4, 1e-2, 1e-4])
    decay: float = 0.01
    optim_materials: bool = True
    shape_control: bool = True

@dataclass
class LensBotConfig:
    """Global LensBot configuration."""
    # LLM settings
    llm_provider: str = "deepseek"  # deepseek, openai, ollama
    llm_model: str = "deepseek-chat"
    llm_base_url: Optional[str] = "https://api.deepseek.com"
    api_key: Optional[str] = None
    
    # Paths
    result_dir: str = "./results"
    
    # Optimization defaults
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    
    # Agent settings
    max_iterations: int = 10  # max reasoning loops
    verbose: bool = True
    
    def __post_init__(self):
        """Initialize from environment variables."""
        if self.api_key is None:
            if self.llm_provider == "deepseek":
                self.api_key = os.getenv("DEEPSEEK_API_KEY")
            else:
                self.api_key = os.getenv("OPENAI_API_KEY")
        
        os.makedirs(self.result_dir, exist_ok=True)


# Preset lens configurations
LENS_PRESETS = {
    "camera_85mm": {
        "name": "85mm Portrait Lens",
        "focal_length": 85.0,
        "fov": 40.0,
        "f_number": 4.0,
        "lens_type": "camera",
        "surf_list": [
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric", "Spheric"],
            ["Aperture"],
            ["Spheric", "Spheric", "Spheric"],
            ["Spheric", "Aspheric"],
            ["Spheric", "Aspheric"]
        ],
    },
    "camera_50mm": {
        "name": "50mm Standard Lens",
        "focal_length": 50.0,
        "fov": 47.0,
        "f_number": 2.8,
        "lens_type": "camera",
        "surf_list": [
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Aperture"],
            ["Spheric", "Spheric"],
            ["Spheric", "Aspheric"]
        ],
    },
    "camera_35mm": {
        "name": "35mm Wide Angle Lens",
        "focal_length": 35.0,
        "fov": 63.0,
        "f_number": 2.0,
        "lens_type": "camera",
        "surf_list": [
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Aperture"],
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"],
            ["Spheric", "Spheric"]
        ],
    },
    "mobile_standard": {
        "name": "Mobile Standard Lens",
        "focal_length": 5.5,
        "fov": 70.0,
        "f_number": 2.0,
        "lens_type": "mobile",
        "surf_list": [
            ["Aperture"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"]
        ],
    },
    "mobile_ultrawide": {
        "name": "Mobile Ultra-Wide Lens",
        "focal_length": 5.0,
        "fov": 90.0,
        "f_number": 2.0,
        "lens_type": "mobile",
        "surf_list": [
            ["Aperture"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"],
            ["Aspheric", "Aspheric"]
        ],
    },
}


def get_surface_list_for_specs(spec: LensSpecification) -> List:
    """Generate appropriate surface list based on lens specifications."""
    if spec.lens_type == "mobile":
        # Mobile lenses use aspheric surfaces, aperture first
        num_elements = max(5, int(spec.fov / 15))  # More FOV = more elements
        return [["Aperture"]] + [["Aspheric", "Aspheric"] for _ in range(num_elements)]
    else:
        # Camera lenses use mix of spheric and aspheric
        if spec.fov >= 60:  # Wide angle
            return [
                ["Spheric", "Spheric"],
                ["Spheric", "Spheric"],
                ["Spheric", "Spheric"],
                ["Aperture"],
                ["Spheric", "Spheric"],
                ["Spheric", "Aspheric"],
                ["Spheric", "Aspheric"]
            ]
        elif spec.fov >= 40:  # Standard
            return [
                ["Spheric", "Spheric"],
                ["Spheric", "Spheric"],
                ["Aperture"],
                ["Spheric", "Spheric"],
                ["Spheric", "Aspheric"]
            ]
        else:  # Telephoto
            return [
                ["Spheric", "Spheric"],
                ["Spheric", "Spheric"],
                ["Spheric", "Spheric", "Spheric"],
                ["Aperture"],
                ["Spheric", "Spheric", "Spheric"],
                ["Spheric", "Aspheric"],
                ["Spheric", "Aspheric"]
            ]
