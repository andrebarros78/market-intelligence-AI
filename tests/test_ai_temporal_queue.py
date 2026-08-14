import json

import pytest
from temporalio.common import WorkflowIDReusePolicy

from market_intelligence.ai.providers import ProviderConfigurationError
from market_intelligence.ai.temporal_queue import (
    ai_queue_config,
    ai_request_key,
    ai_workflow_id,
    build_minimized_ai_job,
    build_sandbox_ai_job,
    start_minimized_ai_job,
    start_sandbox_ai_job,
)


def test_ai_queue_configuration_is_conservative_and_role_isolated() -> None:
    system = ai_queue_config("system")
    agents = ai_queue_config("agents")

    assert system.task_queue != agents.task_queue
    assert system.max_concurrent_activities == 1
    assert agents.max_concurrent_activities == 1
    assert system.task_queue_activities_per_second == 1.0
    assert agents.task_queue_activities_per_second == 1.0


def test_ai_request_key_is_stable_role_scoped_and_hides_original_id() -> None:
    first = ai_request_key(request_id="external-order-123", role="agents")
    second = ai_request_key(request_id="external-order-123", role="agents")
    system = ai_request_key(request_id="external-order-123", role="system")

    assert first == second
    assert first != system
    assert len(first) == 64
    assert "external-order-123" not in first
    assert ai_workflow_id(request_id="external-order-123", role="agents").endswith(first)


def test_sandbox_job_contains_no_prompt_or_raw_request_identifier() -> None:
    job = build_sandbox_ai_job(request_id="customer-sensitive-id", role="agents")

    assert job["mode"] == "sandbox"
    assert job["role"] == "agents"
    assert len(job["request_key"]) == 64
    assert "customer-sensitive-id" not in str(job)
    assert "prompt" not in job


def test_minimized_job_discards_raw_sensitive_fields_before_temporal_history() -> None:
    job = build_minimized_ai_job(
        request_id="customer-sensitive-id",
        role="system",
        purpose="radar_alert_explanation",
        data={
            "entity_type": "listing",
            "entity_alias": "listing-hash-01",
            "observed_change": "traffic_drop",
            "evidence_class": "INFERENCIA",
            "severity": "high",
            "confidence": 0.91,
            "buyer_email": "sensitive@example.com",
            "authorization": "Bearer should-never-enter-history",
            "raw_marketplace_payload": {"buyer": "secret"},
        },
    )

    rendered = json.dumps(job, sort_keys=True)
    assert job["mode"] == "minimized"
    assert job["role"] == "system"
    assert "customer-sensitive-id" not in rendered
    assert "sensitive@example.com" not in rendered
    assert "should-never-enter-history" not in rendered
    assert "raw_marketplace_payload" not in rendered
    assert "prompt" not in job
    gateway = job["gateway_result"]
    assert gateway["business_data_minimized"] is True
    assert gateway["credential_exposed"] is False
    assert gateway["pii_exposed"] is False
    assert gateway["payload"]["entity_alias"] == "listing-hash-01"


@pytest.mark.asyncio
async def test_sandbox_dispatch_uses_stable_workflow_id_and_rejects_duplicate_reuse() -> None:
    calls: list[dict[str, object]] = []
    sentinel = object()

    class FakeClient:
        async def start_workflow(self, workflow_name, payload, **kwargs):
            calls.append({"workflow_name": workflow_name, "payload": payload, **kwargs})
            return sentinel

    result = await start_sandbox_ai_job(
        FakeClient(),
        request_id="synthetic-request-001",
        role="agents",
    )

    assert result is sentinel
    call = calls[0]
    assert call["workflow_name"] == "market-intelligence.ai.sandbox.v1"
    assert call["task_queue"] == "market-intelligence-ai-agents-v1"
    assert call["id_reuse_policy"] is WorkflowIDReusePolicy.REJECT_DUPLICATE
    assert call["id"] == ai_workflow_id(request_id="synthetic-request-001", role="agents")
    assert "synthetic-request-001" not in str(call["payload"])


@pytest.mark.asyncio
async def test_minimized_dispatch_never_passes_raw_data_to_client() -> None:
    calls: list[dict[str, object]] = []
    sentinel = object()

    class FakeClient:
        async def start_workflow(self, workflow_name, payload, **kwargs):
            calls.append({"workflow_name": workflow_name, "payload": payload, **kwargs})
            return sentinel

    result = await start_minimized_ai_job(
        FakeClient(),
        request_id="real-internal-request-123",
        role="system",
        purpose="synthetic_test",
        data={
            "entity_type": "listing",
            "entity_alias": "safe-hash",
            "metric_name": "visits",
            "observed_value": 100,
            "expected_value": 250,
            "buyer_email": "never@example.com",
        },
    )

    assert result is sentinel
    call = calls[0]
    assert call["workflow_name"] == "market-intelligence.ai.minimized.v1"
    assert call["task_queue"] == "market-intelligence-ai-system-v1"
    assert call["id_reuse_policy"] is WorkflowIDReusePolicy.REJECT_DUPLICATE
    rendered = json.dumps(call["payload"], sort_keys=True)
    assert "real-internal-request-123" not in rendered
    assert "never@example.com" not in rendered
    assert "buyer_email" not in rendered


def test_ai_queue_rejects_unknown_role_and_missing_request_id() -> None:
    with pytest.raises(ProviderConfigurationError, match="ai_provider_role_not_supported"):
        ai_queue_config("unknown")
    with pytest.raises(ProviderConfigurationError, match="ai_request_id_missing"):
        ai_request_key(request_id="  ", role="agents")
