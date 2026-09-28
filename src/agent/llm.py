from __future__ import annotations

import json
import os
from urllib.parse import urlsplit


OPENAI_BASE_URL_DEFAULT = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL_DEFAULT = "https://api.anthropic.com/v1"
ZHIPU_BASE_URL_DEFAULT = "https://open.bigmodel.cn/api/paas/v4"
DEEPSEEK_BASE_URL_DEFAULT = "https://api.deepseek.com"

DEFAULT_OPENAI_BASE_URL = DEEPSEEK_BASE_URL_DEFAULT
DEFAULT_OPENAI_MODEL = "deepseek-flash"
LLM_PROVIDERS = [
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": OPENAI_BASE_URL_DEFAULT,
        "default_model": "gpt-5.5",
        "model_placeholder": "gpt-5.5",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "base_url": ANTHROPIC_BASE_URL_DEFAULT,
        "default_model": "claude-sonnet-4.5",
        "model_placeholder": "claude-sonnet-4.5",
    },
    {
        "id": "zhipu",
        "label": "Zhipu",
        "base_url": ZHIPU_BASE_URL_DEFAULT,
        "default_model": "glm-5.2",
        "model_placeholder": "glm-5.2",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": DEEPSEEK_BASE_URL_DEFAULT,
        "default_model": "deepseek-flash",
        "model_placeholder": "deepseek-flash",
    },
    {
        "id": "custom",
        "label": "其他",
        "base_url": "",
        "default_model": "",
        "model_placeholder": "GPT-5.5",
    },
]


def normalize_base_url(value: str | None) -> str:
    return str(value or "").strip().rstrip("/").lower()


def _base_url_host(value: str | None) -> str:
    normalized = normalize_base_url(value)
    if not normalized:
        return ""
    try:
        return (urlsplit(normalized).hostname or "").lower()
    except ValueError:
        return ""


def resolve_provider_id(base_url: str | None) -> str:
    normalized = normalize_base_url(base_url)
    host = _base_url_host(normalized)
    for provider in LLM_PROVIDERS:
        if provider["id"] == "custom":
            continue
        provider_url = normalize_base_url(provider.get("base_url"))
        if normalized and normalized == provider_url:
            return provider["id"]
        if host and host == _base_url_host(provider_url):
            return provider["id"]
    return "custom"


def get_runtime_llm_config() -> dict[str, str | float]:
    base_url = os.getenv("LENSBOT_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
    model = os.getenv("LENSBOT_OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
    try:
        temperature = float(os.getenv("LENSBOT_OPENAI_TEMPERATURE", "0.3"))
    except ValueError:
        temperature = 0.3
    return {
        "provider": resolve_provider_id(base_url),
        "base_url": base_url,
        "model": model,
        "temperature": temperature,
    }


class OpenAIExtractor:
    def __init__(self) -> None:
        config = get_runtime_llm_config()
        self.base_url = str(config["base_url"])
        self.api_key = os.getenv("LENSBOT_OPENAI_API_KEY", "").strip()
        self.model = str(config["model"])
        self.temperature = float(config["temperature"])
        self.last_error = ""
        self.last_content = ""
        self.last_finish_reason = ""
        self.last_usage: dict[str, int] = {}

    def extract_json(self, prompt: str, system_prompt: str) -> dict | None:
        self.last_error = ""
        self.last_content = ""
        self.last_finish_reason = ""
        self.last_usage = {}
        if not self.api_key:
            self.last_error = "missing api key"
            return None

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        try:
            request: dict[str, object] = {
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            }
            if "deepseek.com" in self.base_url.lower():
                request["response_format"] = {"type": "json_object"}
            for attempt in range(2):
                rsp = client.chat.completions.create(**request)
                self.last_content = rsp.choices[0].message.content or ""
                self.last_finish_reason = str(rsp.choices[0].finish_reason or "")
                usage = getattr(rsp, "usage", None)
                for key, value in {
                    "input_tokens": getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }.items():
                    if value is not None:
                        self.last_usage[key] = self.last_usage.get(key, 0) + int(value)
                if self.last_finish_reason != "stop":
                    self.last_error = f"Incomplete JSON response: finish_reason={self.last_finish_reason!r}."
                    return None
                result = self._parse_json_object(self.last_content)
                if result is not None:
                    self.last_error = ""
                    return result
                if attempt == 0:
                    request["messages"] = [
                        *request["messages"],
                        {"role": "assistant", "content": self.last_content},
                        {"role": "user", "content": (
                            f"The response failed JSON validation: {self.last_error}. "
                            "Generate the complete answer again as one valid JSON object. "
                            "Preserve the original task requirements. Keep explanations concise; "
                            "return no Markdown or text outside the JSON object."
                        )},
                    ]
            return None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    def _parse_json_object(self, content: str) -> dict | None:
        text = content.strip()
        if not text:
            self.last_error = "empty response"
            return None
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            self.last_error = f"invalid JSON object: {exc}"
            return None
        if not isinstance(result, dict):
            self.last_error = "Expected one JSON object."
            return None
        return result
