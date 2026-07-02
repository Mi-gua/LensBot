from __future__ import annotations

import json
import os
import re


OPENAI_BASE_URL_DEFAULT = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL_DEFAULT = "https://api.anthropic.com/v1"
ZHIPU_BASE_URL_DEFAULT = "https://open.bigmodel.cn/api/paas/v4"
DEEPSEEK_BASE_URL_DEFAULT = "https://api.deepseek.com"

DEFAULT_OPENAI_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_OPENAI_MODEL = "glm-5.1"
LLM_PROVIDERS = [
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": OPENAI_BASE_URL_DEFAULT,
        "model_placeholder": "gpt-5.5",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "base_url": ANTHROPIC_BASE_URL_DEFAULT,
        "model_placeholder": "claude-sonnet-4.5",
    },
    {
        "id": "zhipu",
        "label": "Zhipu",
        "base_url": ZHIPU_BASE_URL_DEFAULT,
        "model_placeholder": "glm-5.1",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": DEEPSEEK_BASE_URL_DEFAULT,
        "model_placeholder": "deepseek-v4-flash",
    },
    {
        "id": "custom",
        "label": "其他",
        "base_url": "",
        "model_placeholder": "GPT-5.5",
    },
]


def normalize_base_url(value: str | None) -> str:
    return str(value or "").strip().rstrip("/").lower()


def resolve_provider_id(base_url: str | None) -> str:
    normalized = normalize_base_url(base_url)
    for provider in LLM_PROVIDERS:
        if provider["id"] == "custom":
            continue
        if normalized and normalized == normalize_base_url(provider.get("base_url")):
            return provider["id"]
    return "custom"


OPENAI_BASE_URL = os.getenv("LENSBOT_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
OPENAI_MODEL = os.getenv("LENSBOT_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)


class OpenAIExtractor:
    def __init__(self) -> None:
        self.base_url = os.getenv("LENSBOT_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
        self.api_key = os.getenv("LENSBOT_OPENAI_API_KEY", "").strip()
        self.model = os.getenv("LENSBOT_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.temperature = float(os.getenv("LENSBOT_OPENAI_TEMPERATURE", "0.3"))
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
