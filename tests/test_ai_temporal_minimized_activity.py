from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from temporalio.exceptions import ApplicationError

from market_intelligence.ai.data_gateway import AIDataGateway
from market_intelligence.ai.inference_contract import AIAnalysisResponse
from market_intelligence.ai.minimized_runtime import AIMinimizedInferenceResult
from market_intelligence.workflows import ai_temporal_activities as activities_module
from market_intelligence.workflows.ai_temporal_activities import AIInferenceActivities


def _payload() -> dict:
    gateway = AIDataGateway().minimize(
        purpose="synthetic_test",
        data={
            "entity_type": "listing",
            "entity_alias": "safe-alias",
            "metric_name": "visits",
            "observed_value": 100,
            "expected_value": 250,
            "evidence_class": "INFERENCIA",
        },
    )
    return {
        "request_key": "a" * 64,
        "role": "system",
        "mode": "minimized",
        "gateway_result": gateway.model_dump(mode="json"),
    }


def _result() -> AIMinimizedInferenceResult:
    return AIMinimizedInferenceResult(
        role="system",
        provider="openai",
        model="gpt-5-mini",
        endpoint_host="api.openai.com",
        purpose="synthetic_test",
        gateway_policy_version="ai-data-gateway@1.0.0",
        gateway_output_sha256="b" * 64,
        contract_version="ai-minimized-inference@1.0.0",
        prompt_sha256="c" * 64,
        output_sha256="d" * 64,
        output_length_chars=80,
        analysis=AIAnalysisResponse(
            summary="A métrica está abaixo do valor esperado.",
            evidence_class="INFERENCIA",
            recommendations=["Investigar controles equivalentes."],
            limitations=["Teste sintético."],
            causal_claim=False,
        ),
        input_tokens=50,
        output_tokens=20,
        total_tokens=70,
        latency_ms=100,
    )


@pytest.mark.asyncio
async def test_minimized_activity_executes_validated_envelope_and_persists_audit(monkeypatch) -> None:
    calls: list[object] = []

    class FakeRepo:
        async def get_by_request_key(self, key):
            calls.append(("get", key))
            return None

        async def save_if_new(self, *, request_key, result):
            calls.append(("save", request_key, result.provider))
            return True

    class FakeVault:
        @classmethod
        def from_env(cls):
            return cls()

        def resolve(self, *, role):
            return SimpleNamespace(role=role, provider="openai")

    async def fake_execute(config, gateway_result):
        calls.append(("infer", config.role, gateway_result.purpose))
        result = _result()
        return result.model_copy(update={"gateway_output_sha256": gateway_result.output_sha256})

    monkeypatch.setattr(activities_module, "AIVault", FakeVault)
    monkeypatch.setattr(activities_module, "execute_minimized_inference", fake_execute)

    public = await AIInferenceActivities(audit_repo=FakeRepo()).minimized_infer(_payload())

    assert public["mode"] == "minimized"
    assert public["request_key"] == "a" * 64
    assert public["analysis"]["causal_claim"] is False
    assert calls[0] == ("get", "a" * 64)
    assert calls[1][0] == "infer"
    assert calls[2][0] == "save"
    rendered = json.dumps(public)
    assert "api_key" not in rendered.lower()
    assert "authorization" not in rendered.lower()


@pytest.mark.asyncio
async def test_direct_temporal_forgery_with_disallowed_field_is_rejected_before_inference(monkeypatch) -> None:
    called = False

    class FakeRepo:
        async def get_by_request_key(self, key):
            return None

    async def fake_execute(config, gateway_result):
        nonlocal called
        called = True
        return _result()

    monkeypatch.setattr(activities_module, "execute_minimized_inference", fake_execute)
    payload = _payload()
    payload["gateway_result"]["payload"]["buyer_email"] = "forged@example.com"

    with pytest.raises(ApplicationError):
        await AIInferenceActivities(audit_repo=FakeRepo()).minimized_infer(payload)
    assert called is False


@pytest.mark.asyncio
async def test_existing_audit_is_returned_without_provider_call(monkeypatch) -> None:
    called = False
    existing = SimpleNamespace(
        role="system",
        provider="openai",
        model="gpt-5-mini",
        endpoint_host="api.openai.com",
        purpose="synthetic_test",
        gateway_policy_version="ai-data-gateway@1.0.0",
        gateway_output_sha256="b" * 64,
        contract_version="ai-minimized-inference@1.0.0",
        prompt_sha256="c" * 64,
        output_sha256="d" * 64,
        response_json={
            "summary": "already validated",
            "evidence_class": "INFERENCIA",
            "recommendations": [],
            "limitations": [],
            "causal_claim": False,
        },
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        latency_ms=42,
    )

    class FakeRepo:
        async def get_by_request_key(self, key):
            return existing

    async def fake_execute(config, gateway_result):
        nonlocal called
        called = True
        return _result()

    monkeypatch.setattr(activities_module, "execute_minimized_inference", fake_execute)
    public = await AIInferenceActivities(audit_repo=FakeRepo()).minimized_infer(_payload())

    assert public["reused_audit"] is True
    assert public["analysis"]["summary"] == "already validated"
    assert called is False


@pytest.mark.asyncio
async def test_minimized_activity_requires_audit_repository() -> None:
    with pytest.raises(ApplicationError) as caught:
        await AIInferenceActivities(audit_repo=None).minimized_infer(_payload())
    assert "ai_audit_repository_unavailable" in str(caught.value)
