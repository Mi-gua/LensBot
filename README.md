# LensBot - LLM-Powered Automatic Lens Design Agent

An intelligent agent that uses LLM reasoning with DeepLens optimization to automatically design optical lenses.

## Features

- 🤖 **ReAct Agent Architecture** - Reasoning + Acting pattern for intelligent design decisions
- 🔧 **7 Design Tools** - Create, optimize, evaluate, and export lens designs
- 🌐 **Gradio Web UI** - Interactive design interface
- 🔬 **DeepLens Integration** - State-of-the-art curriculum learning optimization

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export OPENAI_API_KEY="your-key-here"

# Run the agent
python main.py
```

Then open http://localhost:7860 in your browser.

## Usage Example

Enter your lens requirements in natural language:

> "Design a 50mm F/2.8 camera lens with 40 degree field of view"

The agent will:
1. Create an initial lens design
2. Run curriculum learning optimization
3. Fine-tune for better performance
4. Report metrics (RMS, spot size)
5. Save the final design

## Project Structure

```
LensBot/
├── lensbot/
│   ├── __init__.py      # Package init
│   ├── agent.py         # ReAct agent core
│   ├── tools.py         # Lens design tools
│   ├── llm_client.py    # LLM API client
│   ├── prompts.py       # System prompts & schemas
│   └── config.py        # Configuration
├── main.py              # Gradio UI entry point
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.9+
- CUDA GPU (recommended for fast optimization)
- OpenAI API key (or local Ollama)
