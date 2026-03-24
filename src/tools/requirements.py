from __future__ import annotations

import re
from dataclasses import asdict

from providers import OpenAIExtractor
from schema import LensDesignParams


class RequirementTool:
    def __init__(self, default_params: LensDesignParams):
        self.default_params = default_params
        self.extractor = OpenAIExtractor()

    def parse(self, prompt: str) -> LensDesignParams:
        extracted = self._parse_with_llm(prompt) or self._parse_with_rules(prompt)
        merged = asdict(self.default_params)
        merged.update(extracted)
        return LensDesignParams(**merged)

    def _parse_with_llm(self, prompt: str) -> dict | None:
        system_prompt = (
            "你是光学镜头需求参数抽取器。"
            "只返回 JSON 对象，可用字段："
            "foclen,fov,fnum,bfl,thickness,iterations,spp,test_per_iter。"
            "缺失字段不要输出。"
        )
        return self.extractor.extract_json(prompt, system_prompt)

    @staticmethod
    def _parse_with_rules(prompt: str) -> dict:
        text = prompt.lower()
        output: dict[str, float | int] = {}
        patterns = {
            "foclen": r"(\d+(?:\.\d+)?)\s*mm\s*(?:焦距|focal|foclen)?|(?:焦距|focal)\s*(\d+(?:\.\d+)?)",
            "fov": r"(?:fov|视场|视场角)\s*(\d+(?:\.\d+)?)",
            "fnum": r"f\s*/\s*(\d+(?:\.\d+)?)",
            "bfl": r"(?:bfl|后焦距)\s*(\d+(?:\.\d+)?)",
            "thickness": r"(?:thickness|总厚度)\s*(\d+(?:\.\d+)?)",
            "iterations": r"(?:iterations|轮数|迭代)\s*(\d+)",
            "spp": r"(?:spp|采样)\s*(\d+)",
            "test_per_iter": r"(?:test_per_iter|测试间隔)\s*(\d+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if not match:
                continue
            value = next((group for group in match.groups() if group), None)
            if value is None:
                continue
            output[key] = int(value) if key in {"iterations", "spp", "test_per_iter"} else float(value)
        return output
