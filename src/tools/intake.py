from __future__ import annotations

import json
import math
from typing import Any

from agent.llm import OpenAIExtractor
from agent.tools import ToolContext, ToolResult
from subagents.types import LensDesignParams, params_from_payload, public_params_dict


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
        defaults = public_params_dict(base_params or self.default_params)
        payload = {
            "task": "normalize_requirements",
            "user_request": prompt,
            "defaults": {key: defaults[key] for key in ("foclen", "fov", "fnum", "bfl", "thickness")},
        }
        extracted = self.extractor.extract_json(json.dumps(payload, ensure_ascii=False), system_prompt)
        if not isinstance(extracted, dict) or not extracted:
            raise ValueError(self.extractor.last_error or "Intake 未返回有效的需求 JSON。")
        if extracted.get("error"):
            raise ValueError(str(extracted["error"]))
        required = {"foclen", "imgh", "fov", "fnum", "bfl", "thickness", "_meta"}
        allowed = required | {"iterations", "spp", "test_per_iter", "constraints"}
        if required - extracted.keys() or extracted.keys() - allowed:
            raise ValueError(
                f"Intake JSON 字段不符合标准：缺少 {sorted(required - extracted.keys())}，"
                f"未知字段 {sorted(extracted.keys() - allowed)}。"
            )
        metadata = extracted["_meta"]
        sources = metadata.get("parameter_sources") if isinstance(metadata, dict) else None
        if not isinstance(sources, dict) or any(
            sources.get(key) not in {"user_input", "derived", "suggested_default"}
            for key in required - {"_meta"}
        ):
            raise ValueError("Intake JSON 必须标明各参数为用户输入、推导值或默认值。")
        extracted["_meta"] = {"parameter_sources": sources}
        for key in ("foclen", "imgh", "fov", "fnum", "bfl", "thickness"):
            if key not in extracted:
                continue
            value = extracted[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"Intake JSON 字段 {key} 必须是有限正数，收到 {value!r}。")
        if "fov" in extracted and extracted["fov"] >= 180:
            raise ValueError("Intake JSON 的全视场 fov 必须小于 180°。")
        return params_from_payload(
            extracted,
            base_params or self.default_params,
            present_values_are_user_input=True,
        )


RequirementTool = ParseRequirementsTool


__all__ = ["ParseRequirementsTool", "RequirementTool"]
