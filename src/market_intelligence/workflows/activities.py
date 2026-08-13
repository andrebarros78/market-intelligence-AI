from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.core.contracts import EntityRef
from market_intelligence.ingestion.events import RawEvent
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.marketplaces.base import MarketplaceAdapter
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import SyntheticOAuthRuntime
from market_intelligence.persistence.contracts import EntityRepository, RawEventRepository, SnapshotRepository
from market_intelligence.workflows.names import (
    ACTIVITY_EVALUATE_RADAR,
    ACTIVITY_FETCH_RESOURCE,
    ACTIVITY_OAUTH_REFRESH,
    ACTIVITY_PERSIST_RAW_EVENT,
    ACTIVITY_PERSIST_RESOURCE,
)
from market_intelligence.workflows.oauth_safety import validate_safe_oauth_temporal_payload


class PersistenceActivities:
    def __init__(self, raw_events: RawEventRepository, entities: EntityRepository,
                 snapshots: SnapshotRepository) -> None:
        self._raw_events, self._entities, self._snapshots = raw_events, entities, snapshots

    @activity.defn(name=ACTIVITY_PERSIST_RAW_EVENT)
    async def persist_raw_event(self, payload: dict[str, Any]) -> bool:
        try:
            event = RawEvent.model_validate(payload)
        except Exception as exc:
            raise ApplicationError("invalid raw event payload", non_retryable=True) from exc
        return await self._raw_events.append_if_new(event)

    @activity.defn(name=ACTIVITY_PERSIST_RESOURCE)
    async def persist_resource_snapshot(self, payload: dict[str, Any]) -> bool:
        try:
            entity = EntityRef(marketplace=str(payload["marketplace"]),
                               entity_type=str(payload["entity_type"]),
                               entity_id=str(payload["entity_id"]))
            resource_payload = payload["payload"]
            if not isinstance(resource_payload, dict):
                raise TypeError("payload must be an object")
            observed_at = datetime.fromisoformat(str(payload["observed_at"]))
        except Exception as exc:
            raise ApplicationError("invalid resource snapshot payload", non_retryable=True) from exc
        await self._entities.upsert(entity, resource_payload, observed_at)
        return await self._snapshots.append_if_changed(entity, resource_payload, observed_at)


class MarketplaceActivities:
    def __init__(self, adapters: Mapping[str, MarketplaceAdapter]) -> None:
        self._adapters = dict(adapters)

    @activity.defn(name=ACTIVITY_FETCH_RESOURCE)
    async def fetch_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        marketplace = str(payload.get("marketplace") or "")
        resource = str(payload.get("resource") or "")
        adapter = self._adapters.get(marketplace)
        if adapter is None:
            raise ApplicationError(f"marketplace adapter not registered: {marketplace}", non_retryable=True)
        if not resource:
            raise ApplicationError("resource is required", non_retryable=True)
        result = await adapter.fetch_resource(resource)
        if not isinstance(result, dict):
            raise ApplicationError("marketplace resource response must be an object", non_retryable=True)
        return result


class RadarActivities:
    def __init__(self, radar: RadarService) -> None:
        self._radar = radar

    @activity.defn(name=ACTIVITY_EVALUATE_RADAR)
    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            observation = RadarObservation.model_validate(payload)
        except Exception as exc:
            raise ApplicationError("invalid radar observation", non_retryable=True) from exc
        return self._radar.evaluate(observation).model_dump(mode="json")


class OAuthActivities:
    """Durable OAuth activities. Secret material never leaves activity memory."""

    def __init__(self, runtime: SyntheticOAuthRuntime) -> None:
        self._runtime = runtime

    async def _current_version(self, account_id: str) -> int:
        current = await self._runtime.refresh.credentials.get(
            marketplace=self._runtime.settings.marketplace,
            account_id=account_id,
        )
        if current is None:
            raise ApplicationError("credential_missing", non_retryable=True)
        return current.version

    @activity.defn(name=ACTIVITY_OAUTH_REFRESH)
    async def refresh(self, payload: dict[str, Any]) -> dict[str, int]:
        safe = validate_safe_oauth_temporal_payload(payload, activity_payload=True)
        account_id = safe["account_id"]
        idempotency_key = safe["idempotency_key"]
        correlation_id = safe.get("correlation_id")

        existing = await self._runtime.operations.get(idempotency_key=idempotency_key)
        if existing is not None:
            if existing.operation != "synthetic_refresh_temporal" or existing.metadata.get("account_id") != account_id:
                raise ApplicationError("OAuth operation idempotency collision", non_retryable=True)
            if existing.status == "completed":
                version = existing.metadata.get("credential_version")
                if isinstance(version, int) and version > 0:
                    return {"credential_version": version}
                raise ApplicationError("Completed OAuth operation lacks safe result", non_retryable=True)
            base_version = existing.metadata.get("base_version")
            if not isinstance(base_version, int) or base_version < 1:
                raise ApplicationError("OAuth operation lacks version baseline", non_retryable=True)
            current_version = await self._current_version(account_id)
            if current_version > base_version:
                completed = await self._runtime.operations.complete(
                    idempotency_key=idempotency_key,
                    status="completed",
                    metadata={"account_id": account_id, "base_version": base_version,
                              "credential_version": current_version},
                )
                if not completed:
                    raise RuntimeError("OAuth operation result persistence failed")
                return {"credential_version": current_version}
        else:
            base_version = await self._current_version(account_id)
            created = await self._runtime.operations.begin(
                operation="synthetic_refresh_temporal",
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                metadata={"account_id": account_id, "base_version": base_version},
            )
            if not created:
                raise ApplicationError("OAuth operation registration race")

        try:
            version = await self._runtime.refresh.refresh(
                account_id=account_id,
                correlation_id=correlation_id,
                coalesce_recent=True,
            )
        except (LookupError, PermissionError) as exc:
            raise ApplicationError(str(exc), non_retryable=True) from exc
        except RuntimeError as exc:
            if str(exc) == "refresh_conflict":
                raise ApplicationError("OAuth refresh currently claimed") from exc
            raise

        completed = await self._runtime.operations.complete(
            idempotency_key=idempotency_key,
            status="completed",
            metadata={"account_id": account_id, "base_version": base_version,
                      "credential_version": version},
        )
        if not completed:
            raise RuntimeError("OAuth operation result persistence failed")
        return {"credential_version": version}
