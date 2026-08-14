from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy

from market_intelligence.ai.data_gateway import AI_DATA_GATEWAY, AIDataGateway
from market_intelligence.ai.inference_contract import build_minimized_inference_prompt
from market_intelligence.ai.providers import AI_ROLES, ProviderConfigurationError
from market_intelligence.workflows.names import WORKFLOW_AI_MINIMIZED, WORKFLOW_AI_SANDBOX


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
    normalized_role = role.strip().lower()
    return {
        "request_key": ai_request_key(request_id=request_id, role=normalized_role),
        "role": normalized_role,
        "mode": "sandbox",
    }


def build_minimized_ai_job(
    *,
    request_id: str,
    role: str,
    purpose: str,
    data: Mapping[str, Any],
    gateway: AIDataGateway = AI_DATA_GATEWAY,
) -> dict[str, Any]:
    """Minimize data before it can enter Temporal Workflow history."""

    normalized_role = role.strip().lower()
    ai_queue_config(normalized_role)
    minimized = gateway.minimize(purpose=purpose, data=data)
    # Build the IA-05 contract locally as an additional gate. The prompt itself is
    # deliberately NOT added to Temporal history; Activity rebuilds it from the
    # attested minimized envelope.
    build_minimized_inference_prompt(minimized)
    return {
        "request_key": ai_request_key(request_id=request_id, role=normalized_role),
        "role": normalized_role,
        "mode": "minimized",
        "gateway_result": minimized.model_dump(mode="json"),
    }


async def start_sandbox_ai_job(
    client: Client,
    *,
    request_id: str,
    role: str,
) -> WorkflowHandle:
    queue = ai_queue_config(role)
    payload = build_sandbox_ai_job(request_id=request_id, role=role)
    return await client.start_workflow(
        WORKFLOW_AI_SANDBOX,
        payload,
        id=ai_workflow_id(request_id=request_id, role=role),
        task_queue=queue.task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )


async def start_minimized_ai_job(
    client: Client,
    *,
    request_id: str,
    role: str,
    purpose: str,
    data: Mapping[str, Any],
    gateway: AIDataGateway = AI_DATA_GATEWAY,
) -> WorkflowHandle:
    """Start a durable AI job after mandatory minimization outside Temporal."""

    queue = ai_queue_config(role)
    payload = build_minimized_ai_job(
        request_id=request_id,
        role=role,
        purpose=purpose,
        data=data,
        gateway=gateway,
    )
    return await client.start_workflow(
        WORKFLOW_AI_MINIMIZED,
        payload,
        id=ai_workflow_id(request_id=request_id, role=role),
        task_queue=queue.task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
    )
