from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.marketplaces.canonical import EvidenceKind
from market_intelligence.marketplaces.mercadolivre.http_client import (
    MercadoLivreReadError,
    MercadoLivreReadOnlyAdapter,
)
from market_intelligence.marketplaces.mercadolivre.schema import schema_fingerprint
from market_intelligence.marketplaces.mercadolivre.surface_registry import (
    SurfaceCaptureMode,
    surfaces_for_topic,
)
from market_intelligence.persistence.models import RawEventRecord
from market_intelligence.persistence.postgresql import (
    PostgresChannelEventRepository,
    PostgresRawEventRepository,
)
from market_intelligence.sensors.bus import UniversalSensorBus
from market_intelligence.sensors.models import SensorSignal, SensorSignalKind

_IDENTIFIER = r"[A-Za-z0-9_-]{1,256}"
_SITE_ID = r"[A-Z0-9_-]{2,16}"
_SAFE_RESOURCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "items": re.compile(rf"^/items/{_IDENTIFIER}$"),
    "price_suggestion": re.compile(rf"^/suggestions/items/{_IDENTIFIER}/details$"),
    "catalog_item_competition_status": re.compile(rf"^/items/{_IDENTIFIER}/price_to_win$"),
    "catalog_suggestions": re.compile(rf"^/catalog_suggestions/{_IDENTIFIER}$"),
    "public_offers": re.compile(rf"^/seller-promotions/offers/{_IDENTIFIER}$"),
    "public_candidates": re.compile(rf"^/seller-promotions/candidates/{_IDENTIFIER}$"),
    "stock-location": re.compile(rf"^/user-products/{_IDENTIFIER}/stock$"),
    "stock_locations": re.compile(rf"^/user-products/{_IDENTIFIER}/stock$"),
    "user-products-families": re.compile(
        rf"^/sites/{_SITE_ID}/user-products-families/{_IDENTIFIER}$"
    ),
    "user_products_families": re.compile(
        rf"^/sites/{_SITE_ID}/user-products-families/{_IDENTIFIER}$"
    ),
    "fbm_stock_operations": re.compile(rf"^/stock/fulfillment/operations/{_IDENTIFIER}$"),
    "flex-handshakes": re.compile(
        rf"^/flex/sites/{_SITE_ID}/shipments/{_IDENTIFIER}/assignment/v1$"
    ),
}
_ITEMS_RESOURCE = re.compile(rf"^/items/({_IDENTIFIER})$")
_MAX_SCHEMA_PATHS = 512


def _normalize_path(resource: str) -> str:
    value = resource.strip()
    if not value:
        return ""
    return value if value.startswith("/") else "/" + value


def resolve_safe_notification_resource(topic: str, resource: str) -> str | None:
    """Resolve a notification into a GET-only low-PII resource.

    The result is still validated by Module01SecurityPolicy inside the read adapter.
    Returning None means the topic must be handled by a dedicated privacy-aware reader
    or registered as an unrecognized/changing surface without following its resource.
    """

    normalized_topic = topic.strip().lower()
    path = _normalize_path(resource)
    if not path:
        return None

    if normalized_topic == "items_prices":
        match = _ITEMS_RESOURCE.fullmatch(path)
        if not match:
            return None
        return f"/items/{match.group(1)}/prices"

    pattern = _SAFE_RESOURCE_PATTERNS.get(normalized_topic)
    if pattern is None or pattern.fullmatch(path) is None:
        return None
    return path



def notification_query_params(topic: str) -> dict[str, str] | None:
    normalized = topic.strip().lower()
    if normalized in {"public_offers", "public_candidates"}:
        return {"app_version": "v2"}
    return None


def _schema_paths(
    value: Any,
    *,
    prefix: str = "$",
    depth: int = 0,
    max_depth: int = 6,
) -> tuple[str, ...]:
    if depth > max_depth:
        return (f"{prefix}:max_depth",)
    if isinstance(value, dict):
        paths: list[str] = []
        for key in sorted(str(item) for item in value):
            child = value.get(key)
            child_prefix = f"{prefix}.{key}"
            paths.append(f"{child_prefix}:{type(child).__name__}")
            if len(paths) >= _MAX_SCHEMA_PATHS:
                break
            paths.extend(
                _schema_paths(
                    child,
                    prefix=child_prefix,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )
            if len(paths) >= _MAX_SCHEMA_PATHS:
                break
        return tuple(paths[:_MAX_SCHEMA_PATHS])
    if isinstance(value, list):
        if not value:
            return (f"{prefix}[]:empty",)
        return (
            f"{prefix}[]:{type(value[0]).__name__}",
        ) + _schema_paths(
            value[0],
            prefix=f"{prefix}[]",
            depth=depth + 1,
            max_depth=max_depth,
        )
    return ()


def schema_only_observation(payload: dict[str, Any]) -> dict[str, Any]:
    """Return structure metadata with no source values or buyer content."""

    return {
        "schema_fingerprint": schema_fingerprint(payload),
        "schema_paths": list(dict.fromkeys(_schema_paths(payload)))[:_MAX_SCHEMA_PATHS],
        "top_level_fields": sorted(str(key) for key in payload),
    }


def _resource_metadata_only(resource: str) -> dict[str, Any]:
    path = _normalize_path(resource)
    segments = [segment for segment in path.split("/") if segment]
    root = segments[0] if segments else ""
    root_hash = hashlib.sha256(root.encode("utf-8")).hexdigest()[:16] if root else None
    return {
        "resource_root": "[REDACTED]" if root else None,
        "resource_root_hash": root_hash,
        "resource_segments": min(len(segments), 32),
        "resource_has_leading_slash": resource.strip().startswith("/"),
    }


def unresolved_surface_observation(topic: str, resource: str) -> dict[str, Any]:
    registered = surfaces_for_topic(topic)
    capture_modes = {surface.capture_mode for surface in registered}
    if not registered:
        resolution_status = "unknown_notification_topic"
    elif SurfaceCaptureMode.WEBHOOK_GET_SAFE in capture_modes:
        resolution_status = "known_topic_resource_shape_changed_or_invalid"
    else:
        resolution_status = "dedicated_privacy_or_metadata_reader_required"
    return {
        "topic": topic.strip().lower(),
        "known_topic": bool(registered),
        "resolution_status": resolution_status,
        "capture_modes": sorted(mode.value for mode in capture_modes),
        "official_get": False,
        "values_persisted": False,
        **_resource_metadata_only(resource),
    }


@dataclass(frozen=True, slots=True)
class SurfaceProbeReport:
    considered: int = 0
    fetched: int = 0
    skipped_privacy_or_unsupported: int = 0
    already_observed: int = 0
    failures: int = 0
    channel_events: int = 0
    new_surface_events: int = 0
    unresolved_surface_events: int = 0


class MercadoLivreWebhookSurfaceProbe:
    """Sondador read-only for resource/schema surfaces announced by ML webhooks.

    It follows only an explicit low-PII allowlist and persists schema/shape metadata,
    never generic response values. Unknown topics and unexpected resource shapes are
    recorded as metadata-only discoveries instead of being followed automatically.
    """

    source = "mercadolivre_surface_probe"

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        adapter: MercadoLivreReadOnlyAdapter,
        max_events_per_cycle: int = 64,
        bus: UniversalSensorBus | None = None,
    ) -> None:
        self.sessions = sessions
        self.adapter = adapter
        self.max_events_per_cycle = max(1, min(int(max_events_per_cycle), 200))
        self.raw = PostgresRawEventRepository(sessions)
        self.channel = PostgresChannelEventRepository(sessions)
        self.bus = bus or UniversalSensorBus()

    async def _persist_non_retryable_failure(
        self,
        row: RawEventRecord,
        marker: str,
        *,
        resolved: str,
        exc: MercadoLivreReadError,
    ) -> bool:
        observation = unresolved_surface_observation(row.event_type, row.resource or "")
        observation.update(
            {
                "resolution_status": "official_get_rejected_non_retryable",
                "resolved_resource": resolved,
                "error_code": exc.code,
                "status_code": exc.status_code,
                "retryable": False,
            }
        )
        event = build_raw_event(
            source=self.source,
            event_type=f"surface_failed:{row.event_type}",
            external_id=marker,
            resource=None,
            occurred_at=row.occurred_at,
            received_at=datetime.now(UTC),
            payload=observation,
        )
        inserted = await self.raw.append_if_new(event)
        if inserted:
            await self.bus.publish(
                SensorSignal(
                    marketplace="mercadolivre",
                    kind=SensorSignalKind.SCHEMA_CHANGE,
                    evidence_kind=EvidenceKind.FACT,
                    source="webhook_surface_non_retryable_failure",
                    observed_at=row.occurred_at or row.received_at,
                    declared=False,
                    payload=observation,
                    confidence=1.0,
                    validated=True,
                )
            )
        return inserted

    async def _persist_unresolved(self, row: RawEventRecord, marker: str) -> bool:
        observation = unresolved_surface_observation(row.event_type, row.resource or "")
        event = build_raw_event(
            source=self.source,
            event_type=f"surface_unresolved:{row.event_type}",
            external_id=marker,
            resource=None,
            occurred_at=row.occurred_at,
            received_at=datetime.now(UTC),
            payload=observation,
        )
        inserted = await self.raw.append_if_new(event)
        if inserted:
            await self.bus.publish(
                SensorSignal(
                    marketplace="mercadolivre",
                    kind=SensorSignalKind.SCHEMA_CHANGE,
                    evidence_kind=EvidenceKind.FACT,
                    source="webhook_surface_metadata_only",
                    observed_at=row.occurred_at or row.received_at,
                    declared=False,
                    payload=observation,
                    confidence=1.0,
                    validated=True,
                )
            )
        return inserted

    async def collect_once(self) -> SurfaceProbeReport:
        async with self.sessions() as session:
            webhook_rows = (
                await session.execute(
                    select(RawEventRecord)
                    .where(RawEventRecord.source == "mercadolivre_webhook")
                    .order_by(desc(RawEventRecord.received_at))
                    .limit(self.max_events_per_cycle)
                )
            ).scalars().all()
            processed = set(
                (
                    await session.execute(
                        select(RawEventRecord.external_id).where(
                            RawEventRecord.source == self.source,
                            RawEventRecord.external_id.is_not(None),
                        )
                    )
                ).scalars().all()
            )

        considered = fetched = skipped = already = failures = channels = new_events = unresolved = 0
        for row in reversed(webhook_rows):
            considered += 1
            marker = f"webhook:{row.dedupe_key}"
            if marker in processed:
                already += 1
                continue
            resolved = resolve_safe_notification_resource(row.event_type, row.resource or "")
            if resolved is None:
                skipped += 1
                inserted = await self._persist_unresolved(row, marker)
                new_events += int(inserted)
                unresolved += int(inserted)
                if inserted:
                    processed.add(marker)
                continue
            try:
                result = await self.adapter.fetch_resource_observed(
                    resolved,
                    params=notification_query_params(row.event_type),
                )
            except MercadoLivreReadError as exc:
                failures += 1
                if not exc.retryable:
                    inserted = await self._persist_non_retryable_failure(
                        row, marker, resolved=resolved, exc=exc
                    )
                    new_events += int(inserted)
                    if inserted:
                        processed.add(marker)
                continue

            fetched += 1
            channels += int(await self.channel.append_if_new(result.channel_event))
            observation = schema_only_observation(result.payload)
            observation.update(
                {
                    "topic": row.event_type,
                    "notification_resource": row.resource,
                    "resolved_resource": resolved,
                    "official_get": True,
                    "values_persisted": False,
                    "resolution_status": "official_get_schema_observed",
                }
            )
            event = build_raw_event(
                source=self.source,
                event_type=f"surface:{row.event_type}",
                external_id=marker,
                resource=resolved,
                occurred_at=row.occurred_at,
                received_at=datetime.now(UTC),
                payload=observation,
            )
            inserted = await self.raw.append_if_new(event)
            new_events += int(inserted)
            if inserted:
                await self.bus.publish(
                    SensorSignal(
                        marketplace="mercadolivre",
                        kind=SensorSignalKind.SCHEMA_CHANGE,
                        evidence_kind=EvidenceKind.FACT,
                        source=f"official_webhook_get:{resolved}",
                        observed_at=result.channel_event.observed_at,
                        declared=False,
                        payload=observation,
                        confidence=1.0,
                        validated=True,
                    )
                )
                processed.add(marker)

        return SurfaceProbeReport(
            considered=considered,
            fetched=fetched,
            skipped_privacy_or_unsupported=skipped,
            already_observed=already,
            failures=failures,
            channel_events=channels,
            new_surface_events=new_events,
            unresolved_surface_events=unresolved,
        )
