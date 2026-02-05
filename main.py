"""
LensBot - LLM-Powered Automatic Lens Design Agent

Gradio web interface for interactive lens design.
"""

import os
import sys
import logging
from pathlib import Path

import gradio as gr

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from lensbot.agent import LensDesignAgent, DesignResult
from lensbot.config import LensBotConfig, LENS_PRESETS
from lensbot.prompts import get_tool_descriptions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Global agent instance
agent: LensDesignAgent = None


def initialize_agent(api_key: str, model: str, use_mock: bool = False) -> str:
    """Initialize the agent with API key."""
    global agent
    
    if not api_key and not use_mock:
        return "❌ Please provide a DeepSeek API key or enable Mock Mode for testing."
    
    try:
        config = LensBotConfig(
            api_key=api_key if not use_mock else None,
            llm_provider="deepseek",
            llm_model=model,
            llm_base_url="https://api.deepseek.com",
        )
        agent = LensDesignAgent(config=config, use_mock=use_mock)
        
        mode = "Mock Mode (no API calls)" if use_mock else f"Connected to {config.llm_model}"
        return f"✅ LensBot initialized! Mode: {mode}"
    except Exception as e:
        return f"❌ Initialization failed: {str(e)}"


def run_design(
    user_request: str,
    api_key: str,
    model: str,
    use_mock: bool,
    progress=gr.Progress()
) -> tuple:
    """Run the lens design agent."""
    global agent
    
    # Initialize agent if needed
    if agent is None:
        init_msg = initialize_agent(api_key, model, use_mock)
        if init_msg.startswith("❌"):
            return init_msg, "", None, ""
    
    if not user_request.strip():
        return "❌ Please enter your lens design requirements.", "", None, ""
    
    # Progress tracking
    progress_messages = []
    
    def progress_callback(msg: str):
        progress_messages.append(msg)
        progress(len(progress_messages) / 10, desc=msg)
    
    try:
        # Run the agent
        result = agent.run(user_request, progress_callback=progress_callback)
        
        # Format output
        summary = result.summary
        
        # Format metrics
        if result.metrics:
            metrics_lines = ["### 📊 Design Metrics\n"]
            for key, value in result.metrics.items():
                key_pretty = key.replace("_", " ").title()
                metrics_lines.append(f"- **{key_pretty}**: {value}")
            metrics_text = "\n".join(metrics_lines)
        else:
            metrics_text = "No metrics available."
        
        # Format steps
        steps_lines = ["### 🔄 Design Steps\n"]
        for step in agent.get_design_steps():
            action = step.get("action", "thinking")
            steps_lines.append(f"**Step {step['step']}**: {action}")
            if step.get("thought"):
                thought_preview = step["thought"][:150] + "..." if len(step.get("thought", "")) > 150 else step.get("thought", "")
                steps_lines.append(f"  - Thought: {thought_preview}")
        steps_text = "\n".join(steps_lines)
        
        # Get result images
        result_image = None
        if result.result_dir:
            # Look for analysis images
            for img_name in ["final_lens_spot_radial.png", "final_lens_layout2d.png", "evaluation_spot_radial.png"]:
                img_path = os.path.join(result.result_dir, img_name)
                if os.path.exists(img_path):
                    result_image = img_path
                    break
        
        progress_log = "\n".join(progress_messages)
        
        return summary, metrics_text, result_image, steps_text
        
    except Exception as e:
        logging.error(f"Design error: {e}")
        return f"❌ Design failed: {str(e)}", "", None, ""


def get_preset_info(preset_name: str) -> str:
    """Get information about a preset."""
    if preset_name in LENS_PRESETS:
        preset = LENS_PRESETS[preset_name]
        return f"""### {preset['name']}
- **Focal Length**: {preset['focal_length']}mm
- **Field of View**: {preset['fov']}°
- **F-Number**: F/{preset['f_number']}
- **Type**: {preset['lens_type']}"""
    return ""


def use_preset(preset_name: str) -> str:
    """Generate request text from preset."""
    if preset_name in LENS_PRESETS:
        preset = LENS_PRESETS[preset_name]
        return f"Design a {preset['focal_length']}mm F/{preset['f_number']} {preset['lens_type']} lens with {preset['fov']} degree field of view"
    return ""


# Build Gradio UI
def create_ui():
    with gr.Blocks(
        title="LensBot - AI Lens Design",
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="slate",
        ),
        css="""
        .gradio-container { max-width: 1200px; margin: auto; }
        .header { text-align: center; padding: 20px; }
        .status-box { padding: 10px; border-radius: 8px; }
        """
    ) as demo:
        
        # Header
        gr.Markdown(
            """
            # 🔬 LensBot - AI Lens Design Assistant
            
            Design optical lenses using natural language. Powered by LLM reasoning and DeepLens optimization.
            """,
            elem_classes="header"
        )
        
        with gr.Row():
            # Left column - Input
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ Configuration")
                
                api_key = gr.Textbox(
                    label="DeepSeek API Key",
                    type="password",
                    placeholder="sk-...",
                    value=os.getenv("OPENAI_API_KEY", ""),
                )

                model = gr.Textbox(
                    label="Model",
                    placeholder="e.g. deepseek-chat",
                    value=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                )
                
                use_mock = gr.Checkbox(
                    label="🧪 Mock Mode (for testing, no API calls)",
                    value=False,
                )
                
                gr.Markdown("### 📐 Lens Presets")
                
                preset_dropdown = gr.Dropdown(
                    choices=list(LENS_PRESETS.keys()),
                    label="Quick Presets",
                    value=None,
                )
                
                preset_info = gr.Markdown("")
                
                use_preset_btn = gr.Button("Use This Preset", size="sm")
                
                gr.Markdown("### 💬 Design Request")
                
                user_input = gr.Textbox(
                    label="Describe your lens requirements",
                    placeholder="Example: Design a 50mm F/2.8 camera lens with 47 degree field of view",
                    lines=3,
                )
                
                with gr.Row():
                    run_btn = gr.Button("🚀 Design Lens", variant="primary", scale=2)
                    clear_btn = gr.Button("🗑️ Clear", scale=1)
            
            # Right column - Output
            with gr.Column(scale=1):
                gr.Markdown("### 📊 Results")
                
                status_output = gr.Markdown(
                    "Ready to design. Enter your requirements and click 'Design Lens'.",
                    elem_classes="status-box"
                )
                
                metrics_output = gr.Markdown("")
                
                result_image = gr.Image(
                    label="Lens Analysis",
                    type="filepath",
                    height=300,
                )
                
                with gr.Accordion("Design Steps", open=False):
                    steps_output = gr.Markdown("")
        
        # Available tools info
        with gr.Accordion("🔧 Available Design Tools", open=False):
            tools_info = "\n".join([
                f"- **{name}**: {desc}" 
                for name, desc in get_tool_descriptions().items()
            ])
            gr.Markdown(tools_info)
        
        # Event handlers
        preset_dropdown.change(
            get_preset_info,
            inputs=[preset_dropdown],
            outputs=[preset_info]
        )
        
        use_preset_btn.click(
            use_preset,
            inputs=[preset_dropdown],
            outputs=[user_input]
        )
        
        run_btn.click(
            run_design,
            inputs=[user_input, api_key, model, use_mock],
            outputs=[status_output, metrics_output, result_image, steps_output]
        )
        
        clear_btn.click(
            lambda: ("", "", None, ""),
            outputs=[status_output, metrics_output, result_image, steps_output]
        )
        
        # Examples
        gr.Markdown("### 💡 Example Requests")
        gr.Examples(
            examples=[
                ["Design a 50mm F/2.8 portrait camera lens with 47 degree field of view"],
                ["Create a mobile phone lens with 5.5mm focal length, F/2.0, 70 degree FOV"],
                ["Design an 85mm F/4.0 telephoto lens for portraits"],
                ["Create a compact wide-angle lens with 35mm focal length and F/2.0"],
            ],
            inputs=[user_input],
        )
        
        gr.Markdown(
            """
            ---
            **Note**: Lens design optimization may take several minutes depending on iteration count.
            Use Mock Mode for quick testing without API calls.
            """
        )
    
    return demo


if __name__ == "__main__":
    print("=" * 60)
    print("🔬 LensBot - AI Lens Design Assistant")
    print("=" * 60)
    
    demo = create_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
