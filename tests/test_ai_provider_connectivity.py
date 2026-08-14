from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from market_intelligence.ai import (
    AIProviderConfig,
    GeminiDriver,
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
async def test_gemini_probe_uses_google_header_and_no_inference() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["api_key"] = request.headers.get("x-goog-api-key")
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            request=request,
            json={
                "models": [
                    {
                        "name": "models/gemini-3.6-flash",
                        "baseModelId": "gemini-3.6-flash",
                    }
                ]
            },
        )

    config = AIProviderConfig(
        role="system",
        provider="gemini",
        model="gemini-3.6-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key=SecretStr("synthetic-gemini-credential"),
    )
    driver = GeminiDriver(config, transport=httpx.MockTransport(handler))
    result = await driver.probe()

    assert result.role == "system"
    assert result.provider == "gemini"
    assert result.authenticated is True
    assert result.model_available is True
    assert result.inference_executed is False
    assert result.business_data_sent is False
    assert seen == {
        "method": "GET",
        "host": "generativelanguage.googleapis.com",
        "path": "/v1beta/models",
        "api_key": "synthetic-gemini-credential",
        "authorization": None,
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


def test_gemini_driver_rejects_credential_exfiltration_host() -> None:
    config = AIProviderConfig(
        role="system",
        provider="gemini",
        model="gemini-3.6-flash",
        base_url="https://attacker.invalid/v1beta",
        api_key=SecretStr("synthetic-gemini-credential"),
    )
    with pytest.raises(ProviderConfigurationError) as caught:
        GeminiDriver(config)
    assert caught.value.code == "gemini_base_url_policy_violation"


def test_provider_manager_keeps_provider_selection_configurable() -> None:
    manager = ProviderManager()
    assert manager.supported_providers == ("gemini", "openai")
    with pytest.raises(ProviderConfigurationError) as caught:
        manager.build(AIProviderConfig(provider="unknown", api_key=SecretStr("synthetic")))
    assert caught.value.code == "ai_provider_not_supported"


def test_system_and_agents_read_separate_gemini_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_AI_SYSTEM_PROVIDER", "gemini")
    monkeypatch.setenv("MI_AI_SYSTEM_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-secret")
    monkeypatch.setenv("MI_AI_AGENTS_PROVIDER", "gemini")
    monkeypatch.setenv("MI_AI_AGENTS_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("MI_AI_AGENTS_API_KEY", "agents-secret")

    system = AIProviderConfig.from_env(role="system")
    agents = AIProviderConfig.from_env(role="agents")

    assert system.role == "system"
    assert agents.role == "agents"
    assert system.provider == agents.provider == "gemini"
    assert system.api_key is not None
    assert agents.api_key is not None
    assert system.api_key.get_secret_value() == "system-secret"
    assert agents.api_key.get_secret_value() == "agents-secret"


def test_agents_never_fall_back_to_system_or_legacy_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_AI_SYSTEM_API_KEY", "system-secret")
    monkeypatch.setenv("MI_AI_API_KEY", "legacy-system-secret")
    monkeypatch.delenv("MI_AI_AGENTS_API_KEY", raising=False)

    agents = AIProviderConfig.from_env(role="agents")
    assert agents.api_key is None


def test_legacy_ai_names_are_system_only_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MI_AI_PROVIDER", "openai")
    monkeypatch.setenv("MI_AI_MODEL", "gpt-5-mini")
    monkeypatch.setenv("MI_AI_API_KEY", "legacy-system-secret")

    system = AIProviderConfig.from_env(role="system")
    agents = AIProviderConfig.from_env(role="agents")

    assert system.provider == "openai"
    assert system.api_key is not None
    assert system.api_key.get_secret_value() == "legacy-system-secret"
    assert agents.provider == "gemini"
    assert agents.api_key is None


def test_secret_is_redacted_from_config_repr() -> None:
    secret = "synthetic-provider-credential"
    rendered = repr(AIProviderConfig(api_key=SecretStr(secret)))
    assert secret not in rendered
    assert "**********" in rendered
