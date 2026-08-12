from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from market_intelligence.workflows.names import (
    ACTIVITY_EVALUATE_RADAR,
    ACTIVITY_FETCH_RESOURCE,
    ACTIVITY_PERSIST_RAW_EVENT,
    ACTIVITY_PERSIST_RESOURCE,
    WORKFLOW_INGESTION,
)


def _retry_policy(*, maximum_attempts: int, maximum_interval_seconds: int) -> RetryPolicy:
    return RetryPolicy(
        initial_interval=timedelta(seconds=1),
        backoff_coefficient=2.0,
        maximum_interval=timedelta(seconds=maximum_interval_seconds),
        maximum_attempts=maximum_attempts,
    )


@workflow.defn(name=WORKFLOW_INGESTION)
class MarketIntelligenceIngestionWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_event = payload.get("raw_event")
        if not isinstance(raw_event, dict):
            raise ApplicationError("raw_event is required", non_retryable=True)

        marketplace = str(payload.get("marketplace") or raw_event.get("source") or "")
        if not marketplace:
            raise ApplicationError("marketplace is required", non_retryable=True)

        raw_event_inserted = await workflow.execute_activity(
            ACTIVITY_PERSIST_RAW_EVENT,
            raw_event,
            start_to_close_timeout=timedelta(seconds=30),
            schedule_to_close_timeout=timedelta(minutes=2),
            retry_policy=_retry_policy(maximum_attempts=5, maximum_interval_seconds=8),
        )

        result: dict[str, Any] = {
            "raw_event_inserted": bool(raw_event_inserted),
            "resource_fetched": False,
            "snapshot_changed": False,
            "radar_evaluated": False,
            "radar_finding": None,
        }

        resource = payload.get("resource") or raw_event.get("resource")
        if resource:
            entity_type = payload.get("entity_type")
            entity_id = payload.get("entity_id")
            if not entity_type or not entity_id:
                raise ApplicationError(
                    "entity_type and entity_id are required when resource is present",
                    non_retryable=True,
                )

            resource_payload = await workflow.execute_activity(
                ACTIVITY_FETCH_RESOURCE,
                {"marketplace": marketplace, "resource": str(resource)},
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=3),
                retry_policy=_retry_policy(maximum_attempts=6, maximum_interval_seconds=30),
            )
            result["resource_fetched"] = True

            result["snapshot_changed"] = bool(
                await workflow.execute_activity(
                    ACTIVITY_PERSIST_RESOURCE,
                    {
                        "marketplace": marketplace,
                        "entity_type": str(entity_type),
                        "entity_id": str(entity_id),
                        "payload": resource_payload,
                        "observed_at": workflow.now().isoformat(),
                    },
                    start_to_close_timeout=timedelta(seconds=30),
                    schedule_to_close_timeout=timedelta(minutes=2),
                    retry_policy=_retry_policy(maximum_attempts=5, maximum_interval_seconds=8),
                )
            )

        radar_observation = payload.get("radar_observation")
        if radar_observation is not None:
            if not isinstance(radar_observation, dict):
                raise ApplicationError(
                    "radar_observation must be an object",
                    non_retryable=True,
                )
            result["radar_finding"] = await workflow.execute_activity(
                ACTIVITY_EVALUATE_RADAR,
                radar_observation,
                start_to_close_timeout=timedelta(seconds=30),
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=_retry_policy(maximum_attempts=3, maximum_interval_seconds=4),
            )
            result["radar_evaluated"] = True

        return result
