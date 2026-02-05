"""LensBot - LLM-Powered Automatic Lens Design Agent."""

__version__ = "0.1.0"

# Lazy imports to avoid requiring torch/deeplens at module load time
def get_agent():
    from .agent import LensDesignAgent
    return LensDesignAgent

def get_tools():
    from .tools import LensDesignTools
    return LensDesignTools

def get_llm_client():
    from .llm_client import LLMClient
    return LLMClient

def get_config():
    from .config import LensBotConfig
    return LensBotConfig

__all__ = ["get_agent", "get_tools", "get_llm_client", "get_config", "__version__"]

