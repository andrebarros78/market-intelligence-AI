from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from market_intelligence.ai import (
    AIProviderConfig,
    OpenAIResponsesDriver,
    ProviderConfigurationError,
    SANDBOX_EXPECTED_OUTPUT,
    SANDBOX_PROMPT,
    ZAIDriver,
)
from market_intelligence.ai.vault import AIVaultProfile


@pytest.mark.asyncio
async def test_openai_sandbox_inference_is_fixed_synthetic_and_not_stored() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "SANDBOX_OK"}],
                    }
                ],
                "usage": {"input_tokens": 18, "output_tokens": 4, "total_tokens": 22},
            },
        )

    config = AIProviderConfig(
        role="system",
        provider="openai",
        model="gpt-5-mini",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("synthetic-openai-credential"),
        max_output_tokens=128,
        store=False,
        retries=0,
    )
    result = await OpenAIResponsesDriver(
        config, transport=httpx.MockTransport(handler)
    ).sandbox_infer()

    assert seen["method"] == "POST"
    assert seen["host"] == "api.openai.com"
    assert seen["path"] == "/v1/responses"
    assert seen["authorization"] == "Bearer synthetic-openai-credential"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body == {
        "model": "gpt-5-mini",
        "input": SANDBOX_PROMPT,
        "max_output_tokens": 128,
        "store": False,
    }
    assert result.authenticated is True
    assert result.inference_executed is True
    assert result.synthetic_data_only is True
    assert result.business_data_sent is False
    assert result.store_enabled is False
    assert result.expected_output_match is True
    assert result.output_length_chars == len(SANDBOX_EXPECTED_OUTPUT)
    assert result.input_tokens == 18
    assert result.output_tokens == 4
    assert result.total_tokens == 22


@pytest.mark.asyncio
async def test_zai_sandbox_inference_disables_thinking_and_is_synthetic() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "SANDBOX_OK"}}
                ],
                "usage": {"prompt_tokens": 16, "completion_tokens": 3, "total_tokens": 19},
            },
        )

    config = AIProviderConfig(
        role="agents",
        provider="zai",
        model="glm-5.1",
        base_url="https://api.z.ai/api/paas/v4",
        api_key=SecretStr("synthetic-zai-credential"),
        max_output_tokens=64,
        store=False,
        retries=0,
    )
    result = await ZAIDriver(config, transport=httpx.MockTransport(handler)).sandbox_infer()

    assert seen["method"] == "POST"
    assert seen["host"] == "api.z.ai"
    assert seen["path"] == "/api/paas/v4/chat/completions"
    assert seen["authorization"] == "Bearer synthetic-zai-credential"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "glm-5.1"
    assert body["messages"] == [{"role": "user", "content": SANDBOX_PROMPT}]
    assert body["thinking"] == {"type": "disabled"}
    assert body["stream"] is False
    assert body["max_tokens"] == 64
    assert body["temperature"] == 0.0
    assert result.inference_executed is True
    assert result.synthetic_data_only is True
    assert result.business_data_sent is False
    assert result.expected_output_match is True
    assert result.input_tokens == 16
    assert result.output_tokens == 3
    assert result.total_tokens == 19


@pytest.mark.asyncio
async def test_sandbox_inference_fails_before_network_when_key_missing() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, request=request, json={})

    driver = OpenAIResponsesDriver(
        AIProviderConfig(api_key=None),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderConfigurationError) as caught:
        await driver.sandbox_infer()
    assert caught.value.code == "ai_provider_api_key_missing"
    assert called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("store", "retries", "max_tokens", "expected_code"),
    [
        (True, 0, 64, "ai_provider_sandbox_store_must_be_false"),
        (False, 2, 64, "ai_provider_sandbox_retries_exceeded"),
        (False, 0, 257, "ai_provider_sandbox_token_limit_invalid"),
    ],
)
async def test_sandbox_safety_limits_fail_closed_before_network(
    store: bool,
    retries: int,
    max_tokens: int,
    expected_code: str,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, request=request, json={})

    driver = OpenAIResponsesDriver(
        AIProviderConfig(
            api_key=SecretStr("synthetic"),
            store=store,
            retries=retries,
            max_output_tokens=max_tokens,
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderConfigurationError) as caught:
        await driver.sandbox_infer()
    assert caught.value.code == expected_code
    assert called is False


@pytest.mark.asyncio
async def test_inference_result_never_contains_api_key_or_raw_output() -> None:
    secret = "never-render-this-api-key"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "output_text": "SANDBOX_OK",
                "usage": {"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
            },
        )

    result = await OpenAIResponsesDriver(
        AIProviderConfig(api_key=SecretStr(secret), max_output_tokens=64),
        transport=httpx.MockTransport(handler),
    ).sandbox_infer()
    rendered = repr(result)

    assert secret not in rendered
    assert SANDBOX_EXPECTED_OUTPUT not in rendered
    assert result.output_sha256
    assert result.expected_output_match is True


def test_vault_profile_preserves_inference_limits_for_adapter() -> None:
    profile = AIVaultProfile(
        slot=1,
        enabled=True,
        provider="openai",
        model="gpt-5-mini",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("synthetic"),
        max_output_tokens=96,
        temperature=0.25,
        retries=1,
        store=False,
    )

    config = profile.to_provider_config(role="system")

    assert config.max_output_tokens == 96
    assert config.temperature == 0.25
    assert config.retries == 1
    assert config.store is False
