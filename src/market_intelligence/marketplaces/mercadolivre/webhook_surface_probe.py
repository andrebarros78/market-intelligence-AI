from __future__ import annotations

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
from market_intelligence.persistence.models import RawEventRecord
from market_intelligence.persistence.postgresql import (
    PostgresChannelEventRepository,
    PostgresRawEventRepository,
)
from market_intelligence.sensors.bus import UniversalSensorBus
from market_intelligence.sensors.models import SensorSignal, SensorSignalKind


# Generic surface probing deliberately excludes messages, orders, payments and other
# resources likely to carry buyer PII. Those resources belong to dedicated minimizers.
_DIRECT_SAFE_PREFIXES: dict[str, tuple[str, ...]] = {
    "items": ("/items/",),
    "price_suggestion": ("/suggestions/items/",),
    "catalog_item_competition_status": ("/items/",),
    "catalog_suggestions": ("/catalog_suggestions/",),
    "public_offers": ("/seller-promotions/offers/",),
    "public_candidates": ("/seller-promotions/candidates/",),
    "stock-location": ("/user-products/",),
    "stock_locations": ("/user-products/",),
    "user_products_families": ("/user-products/",),
    "user-products-families": ("/user-products/",),
    "fbm_stock_operations": ("/stock/fulfillment/operations/",),
    "flex-handshakes": ("/flex/sites/",),
}
_ITEMS_RESOURCE = re.compile(r"^/items/([A-Za-z0-9_-]{1,256})$")


def _normalize_path(resource: str) -> str:
    value = resource.strip()
    if not value:
        return ""
    return value if value.startswith("/") else "/" + value


def resolve_safe_notification_resource(topic: str, resource: str) -> str | None:
    """Resolve a notification into a GET-only low-PII resource.

    The result is still validated by Module01SecurityPolicy inside the read adapter.
    Returning None means the topic must be handled by a dedicated privacy-aware reader.
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

    prefixes = _DIRECT_SAFE_PREFIXES.get(normalized_topic)
    if not prefixes:
        return None
    if not any(path.startswith(prefix) for prefix in prefixes):
        return None

    if normalized_topic == "catalog_item_competition_status" and not path.endswith("/price_to_win"):
        return None
    if normalized_topic in {"stock-location", "stock_locations"} and not path.endswith("/stock"):
        return None
    return path


def _schema_paths(value: Any, *, prefix: str = "$", depth: int = 0, max_depth: int = 6) -> tuple[str, ...]:
    if depth > max_depth:
        return (f"{prefix}:max_depth",)
    if isinstance(value, dict):
        paths: list[str] = []
        for key in sorted(str(item) for item in value.keys()):
            child = value.get(key)
            child_prefix = f"{prefix}.{key}"
            paths.append(f"{child_prefix}:{type(child).__name__}")
            paths.extend(_schema_paths(child, prefix=child_prefix, depth=depth + 1, max_depth=max_depth))
        return tuple(paths)
    if isinstance(value, list):
        if not value:
            return (f"{prefix}[]:empty",)
        # Shape only. Never persist list values from a generic surface probe.
        return (f"{prefix}[]:{type(value[0]).__name__}",) + _schema_paths(
            value[0], prefix=f"{prefix}[]", depth=depth + 1, max_depth=max_depth
        )
    return ()


def schema_only_observation(payload: dict[str, Any]) -> dict[str, Any]:
    """Return structure metadata with no source values or buyer content."""

    return {
        "schema_fingerprint": schema_fingerprint(payload),
        "schema_paths": list(dict.fromkeys(_schema_paths(payload))),
        "top_level_fields": sorted(str(key) for key in payload.keys()),
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


class MercadoLivreWebhookSurfaceProbe:
    """Sondador read-only for resource/schema surfaces announced by ML webhooks.

    It follows only an explicit low-PII allowlist and persists schema/shape metadata,
    never the generic response values. This lets the system discover new fields and
    endpoint shape changes without turning PII-rich resources into a broad data lake.
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

        considered = fetched = skipped = already = failures = channels = new_events = 0
        for row in reversed(webhook_rows):
            considered += 1
            marker = f"webhook:{row.dedupe_key}"
            if marker in processed:
                already += 1
                continue
            resolved = resolve_safe_notification_resource(row.event_type, row.resource or "")
            if resolved is None:
                skipped += 1
                continue
            try:
                result = await self.adapter.fetch_resource_observed(resolved)
            except MercadoLivreReadError:
                failures += 1
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
        )
