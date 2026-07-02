from __future__ import annotations

"""Runtime-owned timeline events for the dashboard.

The agent workflow records structured facts: node names, tool calls, result
codes, and compact data. This module is the only place that turns those facts
into user-facing Chinese progress text.
"""

from dataclasses import dataclass, field
from string import Formatter
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class TimelineEvent:
    key: str
    fields: JsonObject = field(default_factory=dict)
    message: str = ""
    source: str = "workflow"
    level: str = "info"
    visible: bool = True
    title: str = ""

    def for_trace(self) -> JsonObject:
        return {
            "key": self.key,
            "fields": self.fields,
            "message": self.message,
            "source": self.source,
            "level": self.level,
            "visible": self.visible,
            "title": self.title or source_label(self.source),
        }


@dataclass(frozen=True)
class TimelineTemplate:
    text: str
    source: str = "workflow"
    level: str = "info"
    visible: bool = True
    title: str = ""


class TimelineCatalog:
    """Central message catalog and formatter for run timeline entries."""

    def __init__(self, templates: dict[str, TimelineTemplate] | None = None) -> None:
        self.templates = templates or DEFAULT_TEMPLATES

    def event(self, key: str, **fields: Any) -> TimelineEvent:
        template = self.templates.get(key)
        if template is None:
            template = DEFAULT_TEMPLATES["runtime.unknown"]
            fields = {"key": key, **fields}
        safe_fields = _safe_fields(template.text, fields)
        return TimelineEvent(
            key=key,
            fields=dict(fields),
            message=template.text.format(**safe_fields),
            source=template.source,
            level=template.level,
            visible=template.visible,
            title=template.title,
        )


DEFAULT_TEMPLATES: dict[str, TimelineTemplate] = {
    "runtime.unknown": TimelineTemplate("运行事件：{key}", source="runtime", title="事件运行"),
    "run.ready": TimelineTemplate("LensBot 已就绪。", source="system", title="任务接收"),
    "run.accepted": TimelineTemplate("任务已接收，正在启动设计流程。", source="system", title="任务接收"),
    "run.error": TimelineTemplate("镜头设计失败：{error}", source="system", level="error", title="运行错误"),
    "workflow.node.start": TimelineTemplate("{node_label}开始。", source="workflow", title="流程执行"),
    "workflow.node.done": TimelineTemplate("{node_label}完成。", source="workflow", title="流程执行"),
    "workflow.node.failed": TimelineTemplate("{node_label}失败：{error}", source="workflow", level="error", title="流程执行"),
    "workflow.done": TimelineTemplate("流程已完成。", source="workflow", title="流程执行"),
    "workflow.memory.skipped": TimelineTemplate("记忆更新跳过：{error}", source="workflow", level="warning", title="记忆更新"),
    "tool.parse_requirements.done": TimelineTemplate("需求已解析为结构化光学参数。", source="tool", title="需求解析"),
    "seeding.candidates.enter": TimelineTemplate("已从索引选择 {count} 个候选：{case_ids}。", source="seeding", title="初始结构"),
    "seeding.cases.reading": TimelineTemplate("正在一次性读取 {count} 个参考案例：{case_ids}。", source="seeding", title="初始结构"),
    "seeding.initializations.generating": TimelineTemplate("正在批量生成 {count} 个初始结构。", source="seeding", title="初始结构"),
    "seeding.initializations.done": TimelineTemplate("已生成 {applied}/{count} 个初始结构，{status}。", source="seeding", title="初始结构"),
    "seeding.references.published": TimelineTemplate("候选初始结构已发送到优化页。", source="seeding", title="初始结构"),
    "optimization.tool.start": TimelineTemplate("优化工具开始：{tool}。", source="optimization", title="镜头优化"),
    "tool.deeplens_curriculum.done": TimelineTemplate("DeepLens 课程学习完成，当前阶段：{phase}。", source="optimization", title="镜头优化"),
    "tool.deeplens_finetune.done": TimelineTemplate("DeepLens 微调完成，已导出最终结构。", source="optimization", title="镜头优化"),
    "tool.deeplens_analysis.done": TimelineTemplate("DeepLens 指标分析完成。", source="optimization", title="性能分析"),
    "tool.deeplens_analysis.missing": TimelineTemplate("DeepLens 分析等待 final.json 或 curriculum.json。", source="optimization", level="warning", title="性能分析"),
    "tool.zemax_analysis.done": TimelineTemplate("Zemax 性能分析完成。", source="analysis", title="性能分析"),
    "tool.zemax_analysis.unavailable": TimelineTemplate("Zemax 性能分析不可用，保留 DeepLens 指标。", source="analysis", level="warning", title="性能分析"),
    "tool.zemax_analysis.skipped": TimelineTemplate("Zemax 性能分析跳过：{reason}", source="analysis", level="warning", title="性能分析"),
    "tool.zemax_analysis.failed": TimelineTemplate("Zemax 性能分析失败：{reason}", source="analysis", level="warning", title="性能分析"),
    "tool.read_file.done": TimelineTemplate("已读取文件：{path}", source="tool", title="文件操作"),
    "tool.write_file.done": TimelineTemplate("已写入文件：{path}", source="tool", title="文件操作"),
    "tool.edit_file.done": TimelineTemplate("已编辑文件：{path}", source="tool", title="文件操作"),
    "tool.powershell.done": TimelineTemplate("PowerShell 命令执行完成，退出码 {returncode}。", source="tool", title="命令执行"),
}


SOURCE_LABELS: dict[str, str] = {
    "system": "任务接收",
    "runtime": "运行事件",
    "workflow": "流程执行",
    "seeding": "初始结构",
    "optimization": "镜头优化",
    "analysis": "性能分析",
    "reporting": "报告归档",
    "tool": "工具调用",
    "agent": "智能回合",
}


AGENT_LABELS: dict[str, str] = {
    "Intake": "需求解析",
    "Seeding": "初始结构选择",
    "Optimization": "优化智能体",
    "Analysis": "性能分析",
    "Reporting": "报告归档",
}


TOOL_LABELS: dict[str, str] = {
    "parse_requirements": "需求解析",
    "retrieve_seed_cases": "候选检索",
    "read_seed_cases": "案例批量读取",
    "deeplens_curriculum": "DeepLens 课程学习",
    "deeplens_finetune": "DeepLens 微调",
    "deeplens_analysis": "DeepLens 分析",
    "zemax_analysis": "Zemax 分析",
    "read_file": "读取文件",
    "write_file": "写入文件",
    "edit_file": "编辑文件",
    "powershell": "PowerShell",
}


def source_label(source: str) -> str:
    return SOURCE_LABELS.get(str(source or ""), "运行")


def agent_label(agent: str) -> str:
    return AGENT_LABELS.get(str(agent or ""), str(agent or "Agent"))


def agent_source(agent: str) -> str:
    mapping = {
        "Seeding": "seeding",
        "Optimization": "optimization",
        "Analysis": "analysis",
        "Reporting": "reporting",
    }
    return mapping.get(str(agent or ""), "workflow")


def tool_label(tool: str) -> str:
    return TOOL_LABELS.get(str(tool or ""), str(tool or "工具"))

def _safe_fields(template: str, fields: JsonObject) -> JsonObject:
    values: JsonObject = {}
    for _, name, _, _ in Formatter().parse(template):
        if not name:
            continue
        values[name] = fields.get(name, "")
    return values


__all__ = [
    "TimelineCatalog",
    "TimelineEvent",
    "TimelineTemplate",
    "agent_label",
    "source_label",
    "tool_label",
]
