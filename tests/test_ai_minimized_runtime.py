from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from market_intelligence.ai import AIProviderConfig, OpenAIResponsesDriver, ProviderConfigurationError, ZAIDriver
from market_intelligence.ai.data_gateway import AIDataGateway
from market_intelligence.ai.minimized_runtime import execute_minimized_inference


def _gateway_result():
    return AIDataGateway().minimize(
        purpose="radar_alert_explanation",
        data={
            "entity_type": "listing",
            "entity_alias": "listing-hash-001",
            "observed_change": "traffic_drop",
            "evidence_class": "INFERENCIA",
            "severity": "high",
            "confidence": 0.86,
            "observed_value": 650,
            "expected_value": 2400,
            "deviation_percent": -72.9,
            "buyer_email": "must-not-leave@example.com",
            "raw_marketplace_payload": {"secret": "must-never-leave"},
        },
    )


def _analysis_json() -> str:
    return json.dumps(
        {
            "summary": "A queda de tráfego observada permanece parcialmente sem explicação suficiente.",
            "evidence_class": "INFERENCIA",
            "recommendations": ["Comparar anúncios de controle no mesmo período."],
            "limitations": ["A causa interna específica da plataforma não foi observada."],
            "causal_claim": False,
        }
    )


@pytest.mark.asyncio
async def test_openai_minimized_runtime_sends_only_attested_prompt_and_returns_no_raw_text() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        body = json.loads(request.content)
        seen["body"] = body
        return httpx.Response(
            200,
            request=request,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": _analysis_json()}],
                    }
                ],
                "usage": {"input_tokens": 120, "output_tokens": 52, "total_tokens": 172},
            },
        )

    config = AIProviderConfig(
        role="system",
        provider="openai",
        model="gpt-5-mini",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("synthetic-openai-key"),
        store=False,
        retries=0,
    )
    gateway = _gateway_result()
    result = await execute_minimized_inference(
        config,
        gateway,
        driver=OpenAIResponsesDriver(config, transport=httpx.MockTransport(handler)),
    )

    assert seen["path"] == "/v1/responses"
    assert seen["authorization"] == "Bearer synthetic-openai-key"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "gpt-5-mini"
    assert body["store"] is False
    assert body["max_output_tokens"] == 384
    assert "listing-hash-001" in body["input"]
    assert "must-not-leave@example.com" not in body["input"]
    assert "must-never-leave" not in body["input"]
    assert result.analysis.evidence_class == "INFERENCIA"
    assert result.analysis.causal_claim is False
    assert result.input_tokens == 120
    assert result.output_tokens == 52
    assert result.total_tokens == 172
    rendered = result.model_dump(mode="json")
    assert "raw_text" not in rendered
    assert "synthetic-openai-key" not in repr(result)


@pytest.mark.asyncio
async def test_zai_minimized_runtime_uses_guarded_chat_contract() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        body = json.loads(request.content)
        seen["body"] = body
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"role": "assistant", "content": _analysis_json()}}],
                "usage": {"prompt_tokens": 111, "completion_tokens": 44, "total_tokens": 155},
            },
        )

    config = AIProviderConfig(
        role="agents",
        provider="zai",
        model="glm-4.7-flash",
        base_url="https://api.z.ai/api/paas/v4",
        api_key=SecretStr("synthetic-zai-key"),
        store=False,
        retries=0,
    )
    result = await execute_minimized_inference(
        config,
        _gateway_result(),
        driver=ZAIDriver(config, transport=httpx.MockTransport(handler)),
    )

    assert seen["path"] == "/api/paas/v4/chat/completions"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "glm-4.7-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["stream"] is False
    assert body["max_tokens"] == 384
    assert body["temperature"] == 0.0
    assert result.analysis.evidence_class == "INFERENCIA"
    assert result.business_data_minimized is True
    assert result.credential_exposed is False
    assert result.pii_exposed is False


@pytest.mark.asyncio
async def test_minimized_runtime_rejects_store_and_unsupported_provider_before_network() -> None:
    with pytest.raises(ProviderConfigurationError, match="ai_minimized_store_must_be_false"):
        await execute_minimized_inference(
            AIProviderConfig(
                role="system",
                provider="openai",
                model="gpt-5-mini",
                base_url="https://api.openai.com/v1",
                api_key=SecretStr("synthetic"),
                store=True,
            ),
            _gateway_result(),
        )

    with pytest.raises(ProviderConfigurationError, match="ai_minimized_provider_not_supported"):
        await execute_minimized_inference(
            AIProviderConfig(
                role="agents",
                provider="gemini",
                model="gemini-test",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key=SecretStr("synthetic"),
                store=False,
            ),
            _gateway_result(),
            driver=object(),
        )


@pytest.mark.asyncio
async def test_minimized_runtime_blocks_sensitive_provider_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        unsafe = json.dumps(
            {
                "summary": "Contact leaked-person@example.com",
                "evidence_class": "INFERENCIA",
                "recommendations": [],
                "limitations": [],
                "causal_claim": False,
            }
        )
        return httpx.Response(
            200,
            request=request,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": unsafe}],
                    }
                ]
            },
        )

    config = AIProviderConfig(
        role="system",
        provider="openai",
        model="gpt-5-mini",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("synthetic"),
        store=False,
    )
    with pytest.raises(ProviderConfigurationError, match="ai_inference_sensitive_output_blocked"):
        await execute_minimized_inference(
            config,
            _gateway_result(),
            driver=OpenAIResponsesDriver(config, transport=httpx.MockTransport(handler)),
        )
