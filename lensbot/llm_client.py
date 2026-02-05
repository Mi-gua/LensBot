"""LLM client for LensBot agent with function calling support."""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Response from the LLM."""
    content: Optional[str]
    tool_calls: List[ToolCall]
    finish_reason: str
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    """OpenAI-compatible LLM client with function calling."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
    ):
        """
        Initialize the LLM client.
        
        Args:
            api_key: OpenAI API key (or compatible)
            model: Model name to use
            base_url: Optional base URL for API (for Ollama or other providers)
        """
        if OpenAI is None:
            raise ImportError("openai package not installed. Run: pip install openai")
        
        self.model = model
        
        # Support for Ollama and other OpenAI-compatible APIs
        if base_url:
            self.client = OpenAI(api_key=api_key or "ollama", base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key)
        
        logging.info(f"LLM Client initialized with model: {model}")
    
    def generate_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """
        Generate a response with optional tool calling.
        
        Args:
            messages: Conversation history
            tools: Available tool definitions
            temperature: Sampling temperature
            
        Returns:
            LLMResponse with content and/or tool calls
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                temperature=temperature,
            )
            
            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason
            
            # Parse tool calls
            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    ))
            
            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
            
        except Exception as e:
            logging.error(f"LLM API error: {e}")
            raise
    
    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a simple text response without tools.
        
        Args:
            messages: Conversation history
            temperature: Sampling temperature
            
        Returns:
            Generated text content
        """
        response = self.generate_with_tools(messages, tools=[], temperature=temperature)
        return response.content or ""


class MockLLMClient:
    """Mock LLM client for testing without API calls."""
    
    def __init__(self, **kwargs):
        self.model = "mock-model"
        self.call_count = 0
        logging.info("Using Mock LLM Client (no API calls)")
    
    def generate_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Return mock responses for testing."""
        self.call_count += 1
        
        # First call: create lens
        if self.call_count == 1:
            return LLMResponse(
                content="I'll create a lens design based on your requirements.",
                tool_calls=[ToolCall(
                    id="call_1",
                    name="create_lens_design",
                    arguments={"focal_length": 50.0, "fov": 47.0, "f_number": 2.8, "lens_type": "camera"}
                )],
                finish_reason="tool_calls"
            )
        
        # Second call: optimize
        elif self.call_count == 2:
            return LLMResponse(
                content="Now I'll run the curriculum optimization.",
                tool_calls=[ToolCall(
                    id="call_2",
                    name="run_curriculum_optimization",
                    arguments={"iterations": 500}
                )],
                finish_reason="tool_calls"
            )
        
        # Third call: evaluate
        elif self.call_count == 3:
            return LLMResponse(
                content="Let me evaluate the lens performance.",
                tool_calls=[ToolCall(
                    id="call_3",
                    name="evaluate_lens_performance",
                    arguments={}
                )],
                finish_reason="tool_calls"
            )
        
        # Final: complete
        else:
            return LLMResponse(
                content="The lens design is complete! I've created a 50mm F/2.8 camera lens with good optical performance.",
                tool_calls=[],
                finish_reason="stop"
            )
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        return "Mock response for testing."


def create_llm_client(
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    use_mock: bool = False,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
) -> LLMClient:
    """
    Factory function to create appropriate LLM client.
    
    Args:
        api_key: API key for the LLM service
        model: Model name
        use_mock: If True, use mock client for testing
        base_url: Optional base URL for alternative providers
        
    Returns:
        LLMClient instance
    """
    if use_mock:
        return MockLLMClient()
    
    return LLMClient(api_key=api_key, model=model, base_url=base_url)
