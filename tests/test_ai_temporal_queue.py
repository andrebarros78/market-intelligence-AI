import pytest

from market_intelligence.ai.providers import ProviderConfigurationError
from market_intelligence.ai.temporal_queue import (
    ai_queue_config,
    ai_request_key,
    ai_workflow_id,
    build_sandbox_ai_job,
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


def test_ai_queue_rejects_unknown_role_and_missing_request_id() -> None:
    with pytest.raises(ProviderConfigurationError, match="ai_provider_role_not_supported"):
        ai_queue_config("unknown")
    with pytest.raises(ProviderConfigurationError, match="ai_request_id_missing"):
        ai_request_key(request_id="  ", role="agents")
