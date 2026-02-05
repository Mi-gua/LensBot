"""ReAct Agent for automatic lens design."""

import json
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .tools import LensDesignTools, ToolResult
from .llm_client import LLMClient, LLMResponse, create_llm_client
from .prompts import SYSTEM_PROMPT, TOOL_SCHEMAS, get_tool_names
from .config import LensBotConfig


@dataclass
class AgentStep:
    """A single step in the agent's reasoning process."""
    step_number: int
    thought: Optional[str]
    action: Optional[str]
    action_input: Optional[Dict[str, Any]]
    observation: Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DesignResult:
    """Final result of the lens design process."""
    success: bool
    summary: str
    metrics: Dict[str, Any]
    result_dir: Optional[str]
    steps: List[AgentStep]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "metrics": self.metrics,
            "result_dir": self.result_dir,
            "num_steps": len(self.steps),
        }


class LensDesignAgent:
    """
    ReAct (Reasoning + Acting) Agent for automatic lens design.
    
    The agent follows this loop:
    1. THINK: Reason about current state and what to do next
    2. ACT: Select and call a tool
    3. OBSERVE: Process tool results
    4. Repeat until design is complete or max iterations reached
    """
    
    def __init__(
        self,
        config: LensBotConfig = None,
        api_key: Optional[str] = None,
        use_mock: bool = False,
    ):
        """
        Initialize the lens design agent.
        
        Args:
            config: LensBot configuration
            api_key: OpenAI API key (overrides config)
            use_mock: Use mock LLM for testing
        """
        self.config = config or LensBotConfig()
        
        if api_key:
            self.config.api_key = api_key
        
        # Initialize components
        self.tools = LensDesignTools(self.config)
        self.llm = create_llm_client(
            api_key=self.config.api_key,
            model=self.config.llm_model,
            use_mock=use_mock,
            base_url=self.config.llm_base_url,
            provider=self.config.llm_provider,
        )
        
        # Agent state
        self.steps: List[AgentStep] = []
        self.messages: List[Dict[str, str]] = []
        self.is_complete = False
        
        # Tool name -> method mapping
        self.tool_map: Dict[str, Callable] = {
            "create_lens_design": self.tools.create_lens_design,
            "run_curriculum_optimization": self.tools.run_curriculum_optimization,
            "run_fine_tuning": self.tools.run_fine_tuning,
            "evaluate_lens_performance": self.tools.evaluate_lens_performance,
            "analyze_lens_structure": self.tools.analyze_lens_structure,
            "adjust_design_parameters": self.tools.adjust_design_parameters,
            "export_lens": self.tools.export_lens,
        }
        
        logging.info("LensDesignAgent initialized")
    
    def run(
        self,
        user_request: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> DesignResult:
        """
        Run the agent to design a lens based on user requirements.
        
        Args:
            user_request: Natural language description of lens requirements
            progress_callback: Optional callback for progress updates
            
        Returns:
            DesignResult with final design and metrics
        """
        self._reset_state()
        
        # Initialize conversation
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_request},
        ]
        
        if progress_callback:
            progress_callback(f"🚀 Starting lens design: {user_request[:100]}...")
        
        step_num = 0
        
        # Main agent loop
        while not self.is_complete and step_num < self.config.max_iterations:
            step_num += 1
            
            if progress_callback:
                progress_callback(f"🔄 Step {step_num}: Reasoning...")
            
            # Get LLM response
            try:
                response = self.llm.generate_with_tools(
                    messages=self.messages,
                    tools=TOOL_SCHEMAS,
                )
            except Exception as e:
                logging.error(f"LLM error: {e}")
                return self._create_error_result(f"LLM error: {str(e)}")
            
            # Process response
            step = self._process_response(response, step_num, progress_callback)
            self.steps.append(step)
            
            # Check if done
            if response.finish_reason == "stop" and not response.has_tool_calls:
                self.is_complete = True
        
        # Create final result
        return self._create_final_result()
    
    def _process_response(
        self,
        response: LLMResponse,
        step_num: int,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> AgentStep:
        """Process LLM response and execute tools if needed."""
        
        step = AgentStep(
            step_number=step_num,
            thought=response.content,
            action=None,
            action_input=None,
            observation=None,
        )
        
        # Add assistant message to conversation
        if response.content:
            self.messages.append({
                "role": "assistant",
                "content": response.content,
            })
        
        # Execute tool calls
        if response.has_tool_calls:
            for tool_call in response.tool_calls:
                step.action = tool_call.name
                step.action_input = tool_call.arguments
                
                if progress_callback:
                    progress_callback(f"🔧 Executing: {tool_call.name}")
                
                # Execute the tool
                result = self._execute_tool(tool_call.name, tool_call.arguments)
                step.observation = str(result)
                
                # Add tool result to conversation
                self.messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        }
                    }]
                })
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                })
                
                if progress_callback:
                    status = "✅" if result.success else "❌"
                    progress_callback(f"{status} {tool_call.name}: {result.message}")
        
        return step
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool by name with given arguments."""
        if tool_name not in self.tool_map:
            return ToolResult(
                success=False,
                message=f"Unknown tool: {tool_name}. Available: {get_tool_names()}"
            )
        
        try:
            tool_fn = self.tool_map[tool_name]
            result = tool_fn(**arguments)
            return result
        except Exception as e:
            logging.error(f"Tool execution error: {e}")
            return ToolResult(
                success=False,
                message=f"Tool execution failed: {str(e)}"
            )
    
    def _reset_state(self):
        """Reset agent state for a new design session."""
        self.steps = []
        self.messages = []
        self.is_complete = False
        self.tools.design_history = []
    
    def _create_final_result(self) -> DesignResult:
        """Create the final design result."""
        # Get final metrics
        eval_result = self.tools.evaluate_lens_performance()
        
        if eval_result.success:
            metrics = eval_result.data
            summary = f"✅ Lens design complete! RMS: {metrics.get('rms_spot_um', 'N/A')}μm, Quality: {metrics.get('quality_rating', 'N/A')}"
        else:
            metrics = {}
            summary = "⚠️ Design completed but final evaluation failed."
        
        return DesignResult(
            success=eval_result.success,
            summary=summary,
            metrics=metrics,
            result_dir=self.tools.result_dir,
            steps=self.steps,
        )
    
    def _create_error_result(self, error_msg: str) -> DesignResult:
        """Create an error result."""
        return DesignResult(
            success=False,
            summary=f"❌ Design failed: {error_msg}",
            metrics={},
            result_dir=self.tools.result_dir,
            steps=self.steps,
        )
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Return the conversation history."""
        return self.messages.copy()
    
    def get_design_steps(self) -> List[Dict]:
        """Return design steps as dictionaries."""
        return [
            {
                "step": s.step_number,
                "thought": s.thought,
                "action": s.action,
                "input": s.action_input,
                "result": s.observation[:200] if s.observation else None,
            }
            for s in self.steps
        ]
