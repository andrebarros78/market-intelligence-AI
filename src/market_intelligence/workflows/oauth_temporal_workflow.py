from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

from market_intelligence.workflows.names import ACTIVITY_OAUTH_REFRESH, WORKFLOW_OAUTH_REFRESH
from market_intelligence.workflows.oauth_safety import validate_safe_oauth_temporal_payload


@workflow.defn(name=WORKFLOW_OAUTH_REFRESH)
class SyntheticOAuthRefreshWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe = validate_safe_oauth_temporal_payload(payload)
        activity_input: dict[str, str] = {
            "account_id": safe["account_id"],
            "idempotency_key": workflow.info().workflow_id,
        }
        correlation_id = safe.get("correlation_id")
        if correlation_id:
            activity_input["correlation_id"] = correlation_id
        result = await workflow.execute_activity(
            ACTIVITY_OAUTH_REFRESH,
            activity_input,
            start_to_close_timeout=timedelta(seconds=30),
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=15),
                maximum_attempts=6,
            ),
        )
        if not isinstance(result, dict):
            raise RuntimeError("Invalid OAuth refresh result")
        version = result.get("credential_version")
        if set(result) != {"credential_version"} or not isinstance(version, int) or version < 1:
            raise RuntimeError("Invalid OAuth refresh result")
        return {"credential_version": version}
