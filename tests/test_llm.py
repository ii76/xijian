import json

import pytest

from services.llm_service import LLMConfig, LLMResponseError, OpenAICompatibleClient


def test_llm_parses_fenced_json() -> None:
    def transport(url, payload, headers, timeout):
        return {"choices": [{"message": {"content": "```json\n{\"results\": []}\n```"}}]}

    client = OpenAICompatibleClient(LLMConfig(api_key="test", max_retries=0), transport)
    assert client.complete_json("system", "user") == {"results": []}


def test_llm_retries_invalid_json() -> None:
    calls = []

    def transport(url, payload, headers, timeout):
        calls.append(url)
        content = "not-json" if len(calls) == 1 else json.dumps({"results": []})
        return {"choices": [{"message": {"content": content}}]}

    client = OpenAICompatibleClient(LLMConfig(api_key="test", max_retries=1), transport)
    assert client.complete_json("system", "user") == {"results": []}
    assert len(calls) == 2


def test_llm_raises_after_retry_limit() -> None:
    client = OpenAICompatibleClient(
        LLMConfig(api_key="test", max_retries=1),
        lambda *args: {"choices": [{"message": {"content": "bad"}}]},
    )
    with pytest.raises(LLMResponseError):
        client.complete_json("system", "user")

