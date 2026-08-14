import pytest
from pydantic import ValidationError

from market_intelligence.agents.runtime import (
    AGENT_AI_ROLE,
    AGENT_RUNTIME,
    INSTALLED_OPERATIONAL_AGENTS,
    AgentProfile,
    build_agent_inference_job,
)
from market_intelligence.ai.temporal_queue import ai_queue_config


def test_operational_agents_are_installed_read_only_and_provider_neutral() -> None:
    installed = AGENT_RUNTIME.installed()
    assert len(installed) == 20
    assert installed == tuple(sorted(INSTALLED_OPERATIONAL_AGENTS, key=lambda item: item.agent_id))
    assert all(item.ai_role == "agents" for item in installed)
    assert all(item.authority == "read_only" for item in installed)
    assert all("provider" not in item.model_fields for item in installed)


def test_agent_profile_cannot_escalate_to_system_ai() -> None:
    with pytest.raises(ValidationError):
        AgentProfile(
            agent_id="invalid",
            function="invalid",
            description="synthetic",
            ai_role="system",  # type: ignore[arg-type]
        )


def test_agent_dispatch_always_uses_agents_temporal_plane() -> None:
    envelope = build_agent_inference_job(
        agent_id="risk-anomaly-investigator",
        request_id="synthetic-001",
        purpose="synthetic_test",
        data={
            "entity_type": "offer",
            "entity_alias": "synthetic-offer",
            "metric_name": "price",
            "observed_value": 120,
            "expected_value": 100,
            "deviation_percent": 20,
            "evidence_class": "fact",
            "severity": "high",
            "confidence": 0.9,
        },
    )
    assert envelope["ai_job"]["role"] == AGENT_AI_ROLE
    assert envelope["authority"] == "read_only"
    assert ai_queue_config("agents").task_queue == "market-intelligence-ai-agents-v1"
    assert ai_queue_config("system").task_queue == "market-intelligence-ai-system-v1"
    assert ai_queue_config("agents").task_queue != ai_queue_config("system").task_queue
