from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from market_intelligence.ai.temporal_queue import ai_queue_config
from market_intelligence.persistence.ai_audit import PostgresAIInferenceAuditRepository
from market_intelligence.workflows.ai_temporal_activities import AIInferenceActivities
from market_intelligence.workflows.ai_temporal_workflow import (
    AIMinimizedInferenceWorkflow,
    AIProviderSandboxWorkflow,
)


def build_ai_temporal_worker(
    client: Client,
    *,
    role: str,
    audit_repo: PostgresAIInferenceAuditRepository | None = None,
) -> Worker:
    """Build a dedicated, server-rate-limited AI worker."""

    queue = ai_queue_config(role)
    activities = AIInferenceActivities(audit_repo=audit_repo)
    return Worker(
        client,
        task_queue=queue.task_queue,
        workflows=[AIProviderSandboxWorkflow, AIMinimizedInferenceWorkflow],
        activities=[activities.sandbox_infer, activities.minimized_infer],
        max_concurrent_activities=queue.max_concurrent_activities,
        max_activities_per_second=queue.worker_activities_per_second,
        max_task_queue_activities_per_second=queue.task_queue_activities_per_second,
        disable_eager_activity_execution=True,
    )
