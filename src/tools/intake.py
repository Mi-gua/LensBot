from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from agent.llm import OpenAIExtractor
from agent.tools import ToolContext, ToolResult
from subagents.types import LensDesignParams


class ParseRequirementsTool:
    name = "parse_requirements"
    description = "Parse natural-language or structured user input into LensDesignParams."
    category = "general"
    scope = "intake"
    input_schema = {
        "type": "object",
        "required": ["request"],
        "properties": {"request": {"type": "AgentInput"}},
    }
    output_schema = {"type": "LensDesignParams"}
    metadata = {"kind": "llm_parser"}

    def __init__(self, default_params: LensDesignParams):
        self.default_params = default_params
        self.extractor = OpenAIExtractor()

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        request = kwargs["request"]
        if request.mode == "nl":
            if not request.prompt:
                return ToolResult.failure("Natural-language input is empty.", code="empty_prompt")
            params = self._parse_text(request.prompt, request.params, system_prompt=ctx.system_prompt)
            return ToolResult.success("Parsed natural-language requirements.", params)
        if request.params is None:
            return ToolResult.failure("Structured parameter input is empty.", code="empty_structured_params")
        return ToolResult.success("Loaded structured parameters.", request.params)

    def _parse_text(
        self,
        prompt: str,
        base_params: LensDesignParams | None,
        *,
        system_prompt: str,
    ) -> LensDesignParams:
        payload = {"task": "extract_requirements", "user_request": prompt}
        extracted = self.extractor.extract_json(json.dumps(payload, ensure_ascii=False), system_prompt) or {}
        params = deepcopy(base_params or self.default_params)
        for key in ("foclen", "fov", "fnum", "bfl", "thickness"):
            if key in extracted:
                setattr(params, key, float(extracted[key]))
        for key in ("iterations", "spp", "test_per_iter"):
            if key in extracted:
                setattr(params.curriculum, key, int(extracted[key]))
        return params


RequirementTool = ParseRequirementsTool


__all__ = ["ParseRequirementsTool", "RequirementTool"]
