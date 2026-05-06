from __future__ import annotations

import json
import os
import re


OPENAI_BASE_URL = os.getenv("LENSBOT_OPENAI_BASE_URL", "https://api.z.ai/api/paas/v4/")
OPENAI_API_KEY = os.getenv("LENSBOT_OPENAI_API_KEY", "79cffcb78bca4cbbb115c220babd9feb.CIqJ6dBx8yyJwuVO")
OPENAI_MODEL = os.getenv("LENSBOT_OPENAI_MODEL", "glm-5.1")
OPENAI_TEMPERATURE = float(os.getenv("LENSBOT_OPENAI_TEMPERATURE", "1"))


class OpenAIExtractor:
    def __init__(self) -> None:
        self.base_url = OPENAI_BASE_URL
        self.api_key = OPENAI_API_KEY
        self.model = OPENAI_MODEL
        self.temperature = OPENAI_TEMPERATURE
        self.last_error = ""
        self.last_content = ""

    def extract_json(self, prompt: str, system_prompt: str) -> dict | None:
        if not self.api_key:
            self.last_error = "missing api key"
            return None

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        try:
            rsp = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            self.last_content = rsp.choices[0].message.content or ""
            return self._parse_json_object(self.last_content)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    def _parse_json_object(self, content: str) -> dict | None:
        text = content.strip()
        if not text:
            self.last_error = "empty response"
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                self.last_error = f"invalid JSON object: {exc}"
                return None

        self.last_error = "response did not contain a JSON object"
        return None
