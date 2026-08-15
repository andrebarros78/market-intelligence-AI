from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.core.contracts import EntityRef
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.marketplaces.canonical import EvidenceKind
from market_intelligence.marketplaces.mercadolivre.http_client import MercadoLivreReadError, MercadoLivreReadOnlyAdapter, MercadoLivreReadResult
from market_intelligence.marketplaces.mercadolivre.read_sanitize import safe_claims, safe_item, safe_items_search, safe_orders_search, safe_questions, safe_user
from market_intelligence.marketplaces.mercadolivre.vault_token import load_access_token, refresh_access_token
from market_intelligence.marketplaces.mercadolivre.webhook_surface_probe import MercadoLivreWebhookSurfaceProbe, SurfaceProbeReport
from market_intelligence.persistence.postgresql import PostgresChannelEventRepository, PostgresEntityRepository, PostgresRawEventRepository, PostgresSnapshotRepository
from market_intelligence.sensors.bus import UniversalSensorBus
from market_intelligence.sensors.models import SensorEntity, SensorSignal, SensorSignalKind


@dataclass(frozen=True, slots=True)
class MercadoLivreCollectionReport:
    success: bool
    account_id: str | None
    items_seen: int
    item_snapshots: int
    order_snapshots: int
    questions_seen: int
    claims_seen: int
    channel_events: int
    errors: tuple[str, ...]
    token_refreshed: bool
    surface_events_considered: int = 0
    surface_resources_fetched: int = 0
    surface_events_new: int = 0
    surface_events_skipped_privacy_or_unsupported: int = 0
    surface_probe_failures: int = 0


def _channel_event(result: MercadoLivreReadResult) -> ChannelEvent:
    t = result.telemetry
    return ChannelEvent(
        marketplace="mercadolivre",
        direction="outbound",
        operation=t.endpoint,
        observed_at=t.observed_at,
        status_code=t.status_code,
        latency_ms=t.latency_ms,
        attempt=t.attempts,
        request_id=t.request_id,
        attributes={
            "retry_after": t.retry_after,
            "partial_content": t.partial_content,
            "operational_headers": t.operational_headers,
        },
    )


class MercadoLivreFullReadCollector:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], *, max_items_per_cycle: int = 20) -> None:
        self.sessions = sessions
        self.max_items_per_cycle = max(1, min(max_items_per_cycle, 50))
        self.raw = PostgresRawEventRepository(sessions)
        self.channel = PostgresChannelEventRepository(sessions)
        self.entities = PostgresEntityRepository(sessions)
        self.snapshots = PostgresSnapshotRepository(sessions)
        self.bus = UniversalSensorBus()

    async def _persist_result(
        self,
        *,
        result: MercadoLivreReadResult,
        event_type: str,
        payload: dict[str, Any],
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> tuple[bool, bool]:
        observed_at = result.telemetry.observed_at
        channel_saved = await self.channel.append_if_new(_channel_event(result))
        await self.raw.append_if_new(build_raw_event(
            source="mercadolivre_api",
            event_type=event_type,
            payload=payload,
            external_id=entity_id,
            resource=result.telemetry.endpoint,
            occurred_at=observed_at,
            received_at=observed_at,
        ))
        snapshot_saved = False
        if entity_type and entity_id:
            entity = EntityRef(marketplace="mercadolivre", entity_type=entity_type, entity_id=str(entity_id))
            await self.entities.upsert(entity, payload, observed_at)
            snapshot_saved = await self.snapshots.append_if_changed(entity, payload, observed_at)
        await self.bus.publish(SensorSignal(
            marketplace="mercadolivre",
            kind=SensorSignalKind.BUSINESS_EVENT,
            evidence_kind=EvidenceKind.FACT,
            source=f"official_api_get:{result.telemetry.endpoint}",
            observed_at=observed_at,
            entity=(SensorEntity(entity_type=entity_type, entity_id=str(entity_id)) if entity_type and entity_id else None),
            payload={"event_type": event_type, "schema_fingerprint": result.schema_fingerprint, "partial": result.degraded},
            validated=True,
        ))
        return channel_saved, snapshot_saved

    def _new_adapter(self, token: str | None = None) -> MercadoLivreReadOnlyAdapter:
        return MercadoLivreReadOnlyAdapter(access_token=SecretStr(token or load_access_token()), network_allowed=True)

    async def _collect_surface_probe(self, adapter: MercadoLivreReadOnlyAdapter) -> SurfaceProbeReport:
        return await MercadoLivreWebhookSurfaceProbe(
            self.sessions,
            adapter=adapter,
            max_events_per_cycle=64,
            bus=self.bus,
        ).collect_once()

    async def collect_once(self) -> MercadoLivreCollectionReport:
        errors: list[str] = []
        token_refreshed = False
        adapter = self._new_adapter()
        try:
            try:
                me_result = await adapter.read_user_me()
            except MercadoLivreReadError as exc:
                if exc.status_code != 401:
                    raise
                await adapter.aclose()
                token = await refresh_access_token()
                token_refreshed = token.refreshed
                adapter = self._new_adapter(token.access_token)
                me_result = await adapter.read_user_me()

            me = safe_user(me_result.payload)
            account_id = str(me.get("id") or "")
            if not account_id.isdigit():
                raise RuntimeError("mercadolivre_account_id_invalid")
            channel_count = int((await self._persist_result(result=me_result, event_type="account_snapshot", payload=me, entity_type="account", entity_id=account_id))[0])

            item_search = await adapter.read_user_items(account_id, status="active", limit=50)
            item_search_payload = safe_items_search(item_search.payload)
            channel_count += int((await self._persist_result(result=item_search, event_type="active_items_search", payload=item_search_payload))[0])
            item_ids = [str(item) for item in item_search_payload.get("results") or [] if item][: self.max_items_per_cycle]
            item_snapshots = 0
            for item_id in item_ids:
                try:
                    item_result = await adapter.read_listing(item_id)
                    saved = await self._persist_result(result=item_result, event_type="listing_snapshot", payload=safe_item(item_result.payload), entity_type="listing", entity_id=item_id)
                    channel_count += int(saved[0]); item_snapshots += int(saved[1])
                    visits = await adapter.read_visits(item_id)
                    channel_count += int((await self._persist_result(result=visits, event_type="listing_visits", payload=visits.payload, entity_type="visits", entity_id=item_id))[0])
                    try:
                        competition = await adapter.read_catalog_competition(item_id)
                        channel_count += int((await self._persist_result(result=competition, event_type="catalog_competition", payload=competition.payload, entity_type="catalog_competition", entity_id=item_id))[0])
                    except MercadoLivreReadError as exc:
                        errors.append(f"catalog_competition:{item_id}:{exc.status_code or exc.code}")
                except MercadoLivreReadError as exc:
                    errors.append(f"item:{item_id}:{exc.status_code or exc.code}")

            order_snapshots = 0
            try:
                orders = await adapter.read_orders_search(account_id, limit=20)
                safe_orders = safe_orders_search(orders.payload)
                channel_count += int((await self._persist_result(result=orders, event_type="orders_search", payload=safe_orders))[0])
                for order in safe_orders.get("results") or []:
                    oid = str(order.get("id") or "")
                    if oid:
                        entity = EntityRef(marketplace="mercadolivre", entity_type="order", entity_id=oid)
                        await self.entities.upsert(entity, order, orders.telemetry.observed_at)
                        order_snapshots += int(await self.snapshots.append_if_changed(entity, order, orders.telemetry.observed_at))
            except MercadoLivreReadError as exc:
                errors.append(f"orders:{exc.status_code or exc.code}")

            questions_seen = 0
            try:
                questions = await adapter.read_questions_search(account_id, limit=50)
                safe_questions_payload = safe_questions(questions.payload)
                questions_seen = len(safe_questions_payload.get("questions") or [])
                channel_count += int((await self._persist_result(result=questions, event_type="questions_search", payload=safe_questions_payload))[0])
            except MercadoLivreReadError as exc:
                errors.append(f"questions:{exc.status_code or exc.code}")

            claims_seen = 0
            try:
                claims = await adapter.read_open_claims(limit=30)
                safe_claims_payload = safe_claims(claims.payload)
                claims_seen = len(safe_claims_payload.get("data") or [])
                channel_count += int((await self._persist_result(result=claims, event_type="open_claims", payload=safe_claims_payload))[0])
            except MercadoLivreReadError as exc:
                errors.append(f"claims:{exc.status_code or exc.code}")

            surface_report = SurfaceProbeReport()
            try:
                surface_report = await self._collect_surface_probe(adapter)
                channel_count += surface_report.channel_events
            except Exception as exc:
                # Surface discovery is additive. A probe failure must not stop primary
                # polling, but remains observable instead of being silently swallowed.
                errors.append(f"surface_probe:{type(exc).__name__}")
                surface_report = SurfaceProbeReport(failures=1)

            return MercadoLivreCollectionReport(
                success=True,
                account_id=account_id,
                items_seen=len(item_ids),
                item_snapshots=item_snapshots,
                order_snapshots=order_snapshots,
                questions_seen=questions_seen,
                claims_seen=claims_seen,
                channel_events=channel_count,
                errors=tuple(errors),
                token_refreshed=token_refreshed,
                surface_events_considered=surface_report.considered,
                surface_resources_fetched=surface_report.fetched,
                surface_events_new=surface_report.new_surface_events,
                surface_events_skipped_privacy_or_unsupported=surface_report.skipped_privacy_or_unsupported,
                surface_probe_failures=surface_report.failures,
            )
        finally:
            await adapter.aclose()
