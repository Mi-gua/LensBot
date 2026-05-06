from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from agent.llm import OpenAIExtractor
from agent.settings import LensDesignParams
from agent.tools import ToolContext, ToolResult


class RequirementTool:
    name = "parse_requirements"
    description = "Parse user input into LensDesignParams."
    category = "general"
    metadata = {"kind": "llm_parser"}

    def __init__(self, default_params: LensDesignParams):
        self.default_params = default_params
        self.extractor = OpenAIExtractor()

    def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        request = kwargs["request"]
        if request.mode == "nl":
            if not request.prompt:
                return ToolResult(False, "Natural-language input is empty.")
            params = self.parse(request.prompt, base_params=request.params, system_prompt=ctx.system_prompt)
            return ToolResult(True, "Parsed natural-language requirements.", params)
        if request.params is None:
            return ToolResult(False, "Structured parameter input is empty.")
        return ToolResult(True, "Loaded structured parameters.", request.params)

    def parse(
        self,
        prompt: str,
        base_params: LensDesignParams | None = None,
        *,
        system_prompt: str = "",
    ) -> LensDesignParams:
        extracted = self._parse_with_llm(prompt, system_prompt=system_prompt) or {}
        params = deepcopy(base_params or self.default_params)

        for key in ("foclen", "fov", "fnum", "bfl", "thickness"):
            if key in extracted:
                setattr(params, key, float(extracted[key]))

        for key in ("iterations", "spp", "test_per_iter"):
            if key in extracted:
                setattr(params.curriculum, key, int(extracted[key]))

        return params

    def _parse_with_llm(self, prompt: str, *, system_prompt: str) -> dict | None:
        payload = {
            "task": "extract_requirements",
            "user_request": prompt,
        }
        return self.extractor.extract_json(json.dumps(payload, ensure_ascii=False), system_prompt)
