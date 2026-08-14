from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from market_intelligence.workflows.names import (
    ACTIVITY_AI_SANDBOX_INFER,
    WORKFLOW_AI_SANDBOX,
)


@workflow.defn(name=WORKFLOW_AI_SANDBOX)
class AIProviderSandboxWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = str(payload.get("role") or "").strip().lower()
        request_key = str(payload.get("request_key") or "").strip().lower()
        mode = str(payload.get("mode") or "").strip().lower()

        if role not in {"system", "agents"}:
            raise ApplicationError("ai_role_invalid", non_retryable=True)
        if len(request_key) != 64 or any(ch not in "0123456789abcdef" for ch in request_key):
            raise ApplicationError("ai_request_key_invalid", non_retryable=True)
        if mode != "sandbox":
            raise ApplicationError("ai_data_gateway_required", non_retryable=True)

        return await workflow.execute_activity(
            ACTIVITY_AI_SANDBOX_INFER,
            payload,
            start_to_close_timeout=timedelta(seconds=60),
            schedule_to_close_timeout=timedelta(minutes=20),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=5),
                maximum_attempts=3,
            ),
        )
