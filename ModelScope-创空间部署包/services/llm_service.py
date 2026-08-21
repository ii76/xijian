from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable


class LLMError(RuntimeError):
    """Base error for model transport and response failures."""


class LLMConfigurationError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


Transport = Callable[[str, dict, dict, float], dict]


@dataclass(slots=True)
class LLMConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout: float = 45.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "LLMConfig":
        api_key = os.getenv("LLM_API_KEY", "").strip()
        if not api_key:
            raise LLMConfigurationError("未配置 LLM_API_KEY。")
        return cls(
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            timeout=float(os.getenv("LLM_TIMEOUT", "45")),
            max_retries=max(0, int(os.getenv("LLM_MAX_RETRIES", "2"))),
        )


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig, transport: Transport | None = None) -> None:
        self.config = config
        self.transport = transport or _http_transport

    @classmethod
    def from_env(cls) -> "OpenAICompatibleClient":
        return cls(LLMConfig.from_env())

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.transport(url, payload, headers, self.config.timeout)
                content = response["choices"][0]["message"]["content"]
                if isinstance(content, dict):
                    return content
                return _parse_json_object(str(content))
            except (KeyError, IndexError, TypeError, ValueError, LLMError) as exc:
                last_error = exc
            if attempt < self.config.max_retries:
                time.sleep(min(0.25 * (2**attempt), 1.0))
        raise LLMResponseError(f"模型响应在重试后仍不可用：{last_error}")


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
        if text.startswith("json"):
            text = text[4:].lstrip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise LLMResponseError("模型必须返回 JSON 对象。")
    return parsed


def _http_transport(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(f"模型接口返回 HTTP {exc.code}：{body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LLMError(f"模型接口连接失败：{exc}") from exc

