from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ReactTurn:
    thought: str
    action: str | None = None
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    done: bool = False
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReactState:
    objective: str
    turn: int
    trace: list[dict[str, Any]]
    memory: dict[str, Any] = field(default_factory=dict)
    available_tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    context: dict[str, Any] = field(default_factory=dict)


ReactStep = Callable[[ReactState], ReactTurn]
ReactEmit = Callable[[str], None]


ACTION_LABELS: dict[str, str] = {
    "parse_requirements": "解析需求",
    "seed_from_cases": "检索参考案例",
    "optimize_lens": "运行镜头优化",
    "evaluate_lens": "评估优化结果",
    "evaluate_acceptance": "验收设计结果",
    "analyze_zemax": "分析 Zemax 结果",
    "record_memory": "记录经验记忆",
    "archive_report_and_memory": "归档报告和记忆",
}


OBJECTIVE_MESSAGES: dict[str, str] = {
    "将用户意图解析为光学设计上下文": "需求解析：准备上下文。",
    "选择并验证初始光学结构": "初始结构选择：准备参考检索。",
    "优化、评估并判断光学性能": "优化与评估：准备运行优化。",
    "归档运行结果并更新分层记忆": "报告归档：准备归档结果。",
}


ACTION_MESSAGES: dict[str, str] = {
    "parse_requirements": "解析需求：整理结构化参数。",
    "seed_from_cases": "初始结构选择：生成参考初始结构。",
    "optimize_lens": "优化与评估：运行镜头优化。",
    "evaluate_lens": "优化与评估：评估优化结果。",
    "evaluate_acceptance": "验收设计结果：对比目标指标。",
    "analyze_zemax": "Zemax 分析：完成独立评估。",
    "record_memory": "报告归档：记录失败记忆。",
    "archive_report_and_memory": "报告归档：归档报告和记忆。",
}


def _action_label(action: str | None) -> str:
    if not action:
        return ""
    return ACTION_LABELS.get(action, action.replace("_", ""))


def _objective_message(objective: str) -> str:
    return OBJECTIVE_MESSAGES.get(objective, f"正在处理：{objective}。")


def _action_message(action: str | None) -> str:
    if not action:
        return ""
    return ACTION_MESSAGES.get(action, f"{_action_label(action)}：已完成。")


class ReactAgentLoop:
    """Bounded ReAct loop used inside workflow nodes."""

    def __init__(self, name: str, *, max_turns: int = 4) -> None:
        self.name = name
        self.max_turns = max(1, int(max_turns))

    def run(
        self,
        objective: str,
        step: ReactStep,
        emit: ReactEmit | None = None,
        *,
        memory: dict[str, Any] | None = None,
        available_tools: list[str] | None = None,
        system_prompt: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        state_context = context or {}
        if emit:
            emit(_objective_message(objective))

        for turn in range(self.max_turns):
            state = ReactState(
                objective=objective,
                turn=turn,
                trace=trace,
                memory=memory or {},
                available_tools=available_tools or [],
                system_prompt=system_prompt,
                context=state_context,
            )
            decision = step(state)
            row = {
                "agent": self.name,
                "turn": turn,
                "objective": objective,
                "system_prompt": state.system_prompt,
                "context": state.context,
                "available_tools": state.available_tools,
                "thought": decision.thought,
                "action": decision.action,
                "action_input": decision.action_input,
                "observation": decision.observation,
                "done": decision.done,
                "data": decision.data,
            }
            trace.append(row)

            if emit:
                emit(self._format_turn(decision))
            if decision.done:
                break

        return trace

    @staticmethod
    def _format_turn(turn: ReactTurn) -> str:
        thought = turn.thought.strip().rstrip("。")
        if turn.action:
            return _action_message(turn.action)
        return f"检查：{thought}。" if thought else "继续处理中。"
