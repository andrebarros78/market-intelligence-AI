from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.core.contracts import EntityRef
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import RawEvent
from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation
from market_intelligence.intelligence.radar.service import RadarService
from market_intelligence.marketplaces.base import (
    MarketplaceAdapter,
    MarketplaceFetchResult,
    MarketplaceReadError,
)
from market_intelligence.marketplaces.mercadolivre.oauth.runtime import SyntheticOAuthRuntime
from market_intelligence.marketplaces.mercadolivre.oauth.sanitize import sanitize_mapping
from market_intelligence.persistence.contracts import (
    AlertRepository,
    ChannelEventRepository,
    EntityRepository,
    RawEventRepository,
    SnapshotRepository,
)
from market_intelligence.persistence.models import ChannelEventRecord
from market_intelligence.workflows.names import (
    ACTIVITY_EVALUATE_RADAR,
    ACTIVITY_FETCH_RESOURCE,
    ACTIVITY_OAUTH_REFRESH,
    ACTIVITY_PERSIST_CHANNEL_EVENT,
    ACTIVITY_PERSIST_RADAR_ALERT,
    ACTIVITY_PERSIST_RAW_EVENT,
    ACTIVITY_PERSIST_RESOURCE,
)
from market_intelligence.workflows.oauth_safety import validate_safe_oauth_temporal_payload


def _current_activity_attempt() -> int:
    try:
        return max(1, int(activity.info().attempt))
    except RuntimeError:
        return 1


class PersistenceActivities:
    def __init__(
        self,
        raw_events: RawEventRepository,
        channel_events: ChannelEventRepository,
        entities: EntityRepository,
        snapshots: SnapshotRepository,
        alerts: AlertRepository,
    ) -> None:
        self._raw_events = raw_events
        self._channel_events = channel_events
        self._entities = entities
        self._snapshots = snapshots
        self._alerts = alerts

    @activity.defn(name=ACTIVITY_PERSIST_RAW_EVENT)
    async def persist_raw_event(self, payload: dict[str, Any]) -> bool:
        try:
            event = RawEvent.model_validate(payload)
        except Exception as exc:
            raise ApplicationError("invalid raw event payload", non_retryable=True) from exc
        return await self._raw_events.append_if_new(event)

    @activity.defn(name=ACTIVITY_PERSIST_CHANNEL_EVENT)
    async def persist_channel_event(self, payload: dict[str, Any]) -> bool:
        try:
            event = ChannelEvent.model_validate(payload)
        except Exception as exc:
            raise ApplicationError("invalid channel event payload", non_retryable=True) from exc
        return await self._channel_events.append_if_new(event)

    @activity.defn(name=ACTIVITY_PERSIST_RESOURCE)
    async def persist_resource_snapshot(self, payload: dict[str, Any]) -> bool:
        try:
            entity = EntityRef(
                marketplace=str(payload["marketplace"]),
                entity_type=str(payload["entity_type"]),
                entity_id=str(payload["entity_id"]),
            )
            resource_payload = payload["payload"]
            if not isinstance(resource_payload, dict):
                raise TypeError("payload must be an object")
            observed_at = datetime.fromisoformat(str(payload["observed_at"]))
        except Exception as exc:
            raise ApplicationError("invalid resource snapshot payload", non_retryable=True) from exc
        await self._entities.upsert(entity, resource_payload, observed_at)
        return await self._snapshots.append_if_changed(entity, resource_payload, observed_at)

    @activity.defn(name=ACTIVITY_PERSIST_RADAR_ALERT)
    async def persist_radar_alert(self, payload: dict[str, Any]) -> bool:
        try:
            finding = RadarFinding.model_validate(payload["finding"])
            observed_at = datetime.fromisoformat(str(payload["observed_at"]))
            context = payload.get("context") or {}
            if not isinstance(context, dict):
                raise TypeError("context must be an object")
            alert = alert_from_finding(
                finding=finding,
                marketplace=str(payload["marketplace"]),
                entity_type=str(payload["entity_type"]),
                observed_at=observed_at,
                context=context,
            )
        except Exception as exc:
            raise ApplicationError("invalid radar alert payload", non_retryable=True) from exc
        if alert is None:
            return False
        return await self._alerts.save_if_new(alert)


class MarketplaceActivities:
    def __init__(
        self,
        adapters: Mapping[str, MarketplaceAdapter],
        *,
        channel_events: ChannelEventRepository | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self._channel_events = channel_events

    async def _persist_channel_event(self, event: ChannelEvent | None) -> None:
        if event is not None and self._channel_events is not None:
            await self._channel_events.append_if_new(event)

    @activity.defn(name=ACTIVITY_FETCH_RESOURCE)
    async def fetch_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        marketplace = str(payload.get("marketplace") or "")
        resource = str(payload.get("resource") or "")
        adapter = self._adapters.get(marketplace)
        if adapter is None:
            raise ApplicationError(f"marketplace adapter not registered: {marketplace}", non_retryable=True)
        if not resource:
            raise ApplicationError("resource is required", non_retryable=True)
        try:
            observed_reader = getattr(adapter, "fetch_resource_observed", None)
            if callable(observed_reader):
                observed = await observed_reader(
                    resource,
                    attempt=_current_activity_attempt(),
                )
                if not isinstance(observed, MarketplaceFetchResult):
                    raise ApplicationError(
                        "marketplace observed response must use MarketplaceFetchResult",
                        non_retryable=True,
                    )
                await self._persist_channel_event(observed.channel_event)
                result = observed.payload
            else:
                result = await adapter.fetch_resource(resource)
        except MarketplaceReadError as exc:
            await self._persist_channel_event(exc.channel_event)
            raise ApplicationError(exc.code, non_retryable=not exc.retryable) from exc
        if not isinstance(result, dict):
            raise ApplicationError("marketplace resource response must be an object", non_retryable=True)
        return result


class RadarActivities:
    def __init__(
        self,
        radar: RadarService,
        *,
        channel_sessions: async_sessionmaker[AsyncSession] | None = None,
        channel_history_limit: int = 64,
    ) -> None:
        self._radar = radar
        self._channel_sessions = channel_sessions
        self._channel_history_limit = max(12, min(int(channel_history_limit), 256))

    async def _with_persisted_channel_history(
        self, observation: RadarObservation
    ) -> RadarObservation:
        if self._channel_sessions is None or "channel_events" in observation.context:
            return observation
        operation_value = observation.context.get("channel_operation")
        if not operation_value:
            return observation
        marketplace = str(observation.context.get("marketplace") or "mercadolivre")
        operation = str(operation_value)
        statement = (
            select(ChannelEventRecord)
            .where(
                ChannelEventRecord.marketplace == marketplace,
                ChannelEventRecord.operation == operation,
                ChannelEventRecord.observed_at <= observation.observed_at,
            )
            .order_by(ChannelEventRecord.observed_at.desc())
            .limit(self._channel_history_limit)
        )
        async with self._channel_sessions() as session:
            rows = list((await session.execute(statement)).scalars())
        if not rows:
            return observation
        events = [
            ChannelEvent(
                marketplace=row.marketplace,
                direction=row.direction,
                operation=row.operation,
                observed_at=row.observed_at,
                status_code=row.status_code,
                latency_ms=row.latency_ms,
                attempt=row.attempt,
                correlation_id=row.correlation_id,
                request_id=row.request_id,
                attributes=sanitize_mapping(row.attributes or {}),
            ).model_dump(mode="python")
            for row in reversed(rows)
        ]
        payload = observation.model_dump(mode="python")
        context = dict(observation.context)
        context["channel_events"] = events
        context["channel_history_source"] = "postgresql"
        context["channel_history_count"] = len(events)
        payload["context"] = context
        return RadarObservation.model_validate(payload)

    @activity.defn(name=ACTIVITY_EVALUATE_RADAR)
    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            observation = RadarObservation.model_validate(payload)
        except Exception as exc:
            raise ApplicationError("invalid radar observation", non_retryable=True) from exc
        observation = await self._with_persisted_channel_history(observation)
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
