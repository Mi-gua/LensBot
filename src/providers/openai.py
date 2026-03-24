from __future__ import annotations

import json
import os


class OpenAIExtractor:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("LENSBOT_LLM_MODEL", "gpt-4o-mini")

    def extract_json(self, prompt: str, system_prompt: str) -> dict | None:
        if not self.api_key:
            return None

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        try:
            rsp = client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return json.loads(rsp.choices[0].message.content or "{}")
        except Exception:
            return None
