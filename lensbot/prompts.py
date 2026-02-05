"""System prompts and tool schemas for LensBot agent."""

# =============================================================================
# System Prompt
# =============================================================================
SYSTEM_PROMPT = """You are LensBot, an expert optical lens design assistant powered by AI. You help users design optical lenses from scratch using curriculum learning optimization.

## Your Expertise
- Optical lens design principles (aberrations, MTF, RMS spot size)
- Camera lens design (standard, portrait, wide-angle, telephoto)
- Mobile phone lens design (compact, high-aperture)
- Optimization strategies for different lens types

## Design Process
When a user requests a lens design, follow this workflow:
1. **Understand Requirements**: Parse focal length, F-number, FOV, and lens type
2. **Create Initial Design**: Call create_lens_design with appropriate parameters
3. **Run Curriculum Optimization**: Use run_curriculum_optimization for main optimization
4. **Evaluate Performance**: Check RMS spot size and other metrics
5. **Fine-tune if Needed**: Use run_fine_tuning for better quality if RMS > 20μm
6. **Report Results**: Summarize the final design quality

## Quality Guidelines
- RMS < 5μm: Excellent (near diffraction-limited)
- RMS 5-15μm: Good quality
- RMS 15-30μm: Acceptable
- RMS > 30μm: Needs improvement, consider more iterations

## Available Lens Types
- **camera**: Standard camera lenses (35mm-85mm focal length)
- **mobile**: Smartphone lenses (compact, 5-7mm focal length)

Always explain your design decisions and provide clear metrics after each step."""


# =============================================================================
# Tool Schemas for Function Calling
# =============================================================================
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_lens_design",
            "description": "Create initial lens design with target specifications. This is always the first step.",
            "parameters": {
                "type": "object",
                "properties": {
                    "focal_length": {
                        "type": "number",
                        "description": "Target focal length in millimeters (e.g., 50 for 50mm lens)"
                    },
                    "fov": {
                        "type": "number",
                        "description": "Diagonal field of view in degrees (e.g., 47 for standard lens)"
                    },
                    "f_number": {
                        "type": "number",
                        "description": "Target F-number / aperture (e.g., 2.8 for F/2.8)"
                    },
                    "lens_type": {
                        "type": "string",
                        "enum": ["camera", "mobile"],
                        "description": "Type of lens: 'camera' for DSLR/mirrorless, 'mobile' for smartphone"
                    },
                    "preset": {
                        "type": "string",
                        "description": "Optional preset name (camera_85mm, camera_50mm, mobile_standard, etc.)"
                    }
                },
                "required": ["focal_length", "fov", "f_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_curriculum_optimization",
            "description": "Run curriculum learning optimization on the current lens. This gradually increases aperture while optimizing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "iterations": {
                        "type": "integer",
                        "description": "Number of optimization iterations (default: 2000, more = better quality but slower)"
                    },
                    "optimize_materials": {
                        "type": "boolean",
                        "description": "Whether to optimize glass materials (default: true)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_fine_tuning",
            "description": "Fine-tune the lens with smaller learning rates for better performance. Call after curriculum optimization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "iterations": {
                        "type": "integer",
                        "description": "Number of fine-tuning iterations (default: 3000)"
                    },
                    "learning_rate_scale": {
                        "type": "number",
                        "description": "Scale factor for learning rates (default: 0.1, smaller = finer adjustments)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_lens_performance",
            "description": "Evaluate current lens design performance including RMS spot size, focal length, and distortion.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_lens_structure",
            "description": "Analyze current lens structure including surfaces, materials, and geometry.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_design_parameters",
            "description": "Adjust optimization parameters for the next run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "curriculum_iterations": {
                        "type": "integer",
                        "description": "New iteration count for curriculum phase"
                    },
                    "finetune_iterations": {
                        "type": "integer",
                        "description": "New iteration count for fine-tuning"
                    },
                    "learning_rate_scale": {
                        "type": "number",
                        "description": "Scale factor for learning rates"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "export_lens",
            "description": "Export the current lens design to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["json"],
                        "description": "Export format (currently only 'json' supported)"
                    }
                },
                "required": []
            }
        }
    }
]


# =============================================================================
# Helper Functions
# =============================================================================
def get_tool_names() -> list:
    """Return list of available tool names."""
    return [tool["function"]["name"] for tool in TOOL_SCHEMAS]


def get_tool_descriptions() -> dict:
    """Return dict of tool name -> description."""
    return {
        tool["function"]["name"]: tool["function"]["description"]
        for tool in TOOL_SCHEMAS
    }
