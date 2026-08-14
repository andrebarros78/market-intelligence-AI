from __future__ import annotations

import hashlib
from dataclasses import dataclass

from market_intelligence.ai.providers import AI_ROLES, ProviderConfigurationError


@dataclass(frozen=True, slots=True)
class AITemporalQueueConfig:
    role: str
    task_queue: str
    max_concurrent_activities: int
    worker_activities_per_second: float
    task_queue_activities_per_second: float


_AI_QUEUE_CONFIGS: dict[str, AITemporalQueueConfig] = {
    "system": AITemporalQueueConfig(
        role="system",
        task_queue="market-intelligence-ai-system-v1",
        max_concurrent_activities=1,
        worker_activities_per_second=1.0,
        task_queue_activities_per_second=1.0,
    ),
    "agents": AITemporalQueueConfig(
        role="agents",
        task_queue="market-intelligence-ai-agents-v1",
        max_concurrent_activities=1,
        worker_activities_per_second=1.0,
        task_queue_activities_per_second=1.0,
    ),
}


def ai_queue_config(role: str) -> AITemporalQueueConfig:
    normalized = role.strip().lower()
    if normalized not in AI_ROLES:
        raise ProviderConfigurationError("ai_provider_role_not_supported")
    return _AI_QUEUE_CONFIGS[normalized]


def ai_request_key(*, request_id: str, role: str) -> str:
    """Return a stable, non-reversible idempotency key safe for workflow history."""

    normalized_role = role.strip().lower()
    ai_queue_config(normalized_role)
    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        raise ProviderConfigurationError("ai_request_id_missing")
    material = f"{normalized_role}:{normalized_request_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def ai_workflow_id(*, request_id: str, role: str) -> str:
    normalized_role = role.strip().lower()
    return f"api-ml-ai-{normalized_role}-{ai_request_key(request_id=request_id, role=role)}"


def build_sandbox_ai_job(*, request_id: str, role: str) -> dict[str, str]:
    """Build the only IA-03 payload allowed before the data gateway exists.

    The original request id is deliberately not stored in Temporal history and
    arbitrary prompts are not accepted at this phase.
    """

    normalized_role = role.strip().lower()
    return {
        "request_key": ai_request_key(request_id=request_id, role=normalized_role),
        "role": normalized_role,
        "mode": "sandbox",
    }
