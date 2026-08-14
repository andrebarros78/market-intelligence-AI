from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from market_intelligence.ai import (
    AIProviderConfig,
    OpenAIResponsesDriver,
    ProviderConfigurationError,
    ProviderManager,
)


@pytest.mark.asyncio
async def test_openai_probe_authenticates_and_finds_configured_model_without_inference() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            request=request,
            json={"object": "list", "data": [{"id": "gpt-5-mini", "object": "model"}]},
        )

    config = AIProviderConfig(api_key=SecretStr("synthetic-provider-credential"))
    driver = OpenAIResponsesDriver(config, transport=httpx.MockTransport(handler))
    result = await driver.probe()

    assert result.authenticated is True
    assert result.model_available is True
    assert result.inference_executed is False
    assert result.business_data_sent is False
    assert seen == {
        "method": "GET",
        "host": "api.openai.com",
        "path": "/v1/models",
        "authorization": "Bearer synthetic-provider-credential",
    }


@pytest.mark.asyncio
async def test_probe_fails_closed_when_credential_is_missing() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, request=request, json={"data": []})

    driver = OpenAIResponsesDriver(
        AIProviderConfig(api_key=None),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderConfigurationError) as caught:
        await driver.probe()
    assert caught.value.code == "ai_provider_api_key_missing"
    assert called is False


def test_openai_driver_rejects_credential_exfiltration_host() -> None:
    config = AIProviderConfig(
        base_url="https://attacker.invalid/v1",
        api_key=SecretStr("synthetic-provider-credential"),
    )
    with pytest.raises(ProviderConfigurationError) as caught:
        OpenAIResponsesDriver(config)
    assert caught.value.code == "openai_base_url_policy_violation"


def test_provider_manager_keeps_provider_selection_configurable() -> None:
    manager = ProviderManager()
    assert manager.supported_providers == ("openai",)
    with pytest.raises(ProviderConfigurationError) as caught:
        manager.build(AIProviderConfig(provider="unknown", api_key=SecretStr("synthetic")))
    assert caught.value.code == "ai_provider_not_supported"


def test_secret_is_redacted_from_config_repr() -> None:
    secret = "synthetic-provider-credential"
    rendered = repr(AIProviderConfig(api_key=SecretStr(secret)))
    assert secret not in rendered
    assert "**********" in rendered
