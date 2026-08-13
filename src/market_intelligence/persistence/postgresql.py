from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.core.contracts import Alert, EntityRef
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import RawEvent, canonical_payload_hash
from market_intelligence.marketplaces.mercadolivre.oauth.sanitize import sanitize_mapping
from market_intelligence.persistence.models import (
    AlertRecord,
    ChannelEventRecord,
    EntityRecord,
    EvidenceRecord,
    OAuthStateRecord,
    RawEventRecord,
    SnapshotRecord,
)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def raw_event_dedupe_key(event: RawEvent) -> str:
    if event.external_id:
        material = "\x1f".join(
            [event.source, event.event_type, "external", event.external_id]
        ).encode("utf-8")
    else:
        occurred = event.occurred_at.isoformat() if event.occurred_at else ""
        material = "\x1f".join(
            [event.source, event.event_type, event.resource or "", occurred, event.payload_hash]
        ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def channel_event_dedupe_key(event: ChannelEvent) -> str:
    safe = event.model_dump(mode="json")
    safe["attributes"] = sanitize_mapping(safe.get("attributes") or {})
    return _stable_hash(safe)


def alert_dedupe_key(alert: Alert) -> str:
    return _stable_hash(alert.model_dump(mode="json"))


class PostgresRawEventRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append_if_new(self, event: RawEvent) -> bool:
        statement = (
            pg_insert(RawEventRecord)
            .values(
                source=event.source,
                event_type=event.event_type,
                external_id=event.external_id,
                resource=event.resource,
                occurred_at=event.occurred_at,
                received_at=event.received_at,
                payload_hash=event.payload_hash,
                dedupe_key=raw_event_dedupe_key(event),
                payload=event.payload,
            )
            .on_conflict_do_nothing(constraint="uq_raw_events_dedupe_key")
            .returning(RawEventRecord.id)
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            return result.scalar_one_or_none() is not None


class PostgresChannelEventRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append_if_new(self, event: ChannelEvent) -> bool:
        attributes = sanitize_mapping(event.attributes)
        statement = (
            pg_insert(ChannelEventRecord)
            .values(
                marketplace=event.marketplace,
                direction=event.direction,
                operation=event.operation,
                observed_at=event.observed_at,
                status_code=event.status_code,
                latency_ms=event.latency_ms,
                attempt=event.attempt,
                correlation_id=event.correlation_id,
                request_id=event.request_id,
                dedupe_key=channel_event_dedupe_key(event),
                attributes=attributes,
            )
            .on_conflict_do_nothing(constraint="uq_channel_events_dedupe_key")
            .returning(ChannelEventRecord.id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalar_one_or_none() is not None


class PostgresEntityRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def upsert(self, entity: EntityRef, payload: dict[str, Any], observed_at: datetime) -> None:
        payload_hash = canonical_payload_hash(payload)
        statement = pg_insert(EntityRecord).values(
            marketplace=entity.marketplace,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            current_hash=payload_hash,
            current_payload=payload,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_entities_natural_key",
            set_={
                "current_hash": statement.excluded.current_hash,
                "current_payload": statement.excluded.current_payload,
                "last_seen_at": statement.excluded.last_seen_at,
            },
        )
        async with self._sessions() as session, session.begin():
            await session.execute(statement)

    async def get(self, entity: EntityRef) -> EntityRecord | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(EntityRecord).where(
                    EntityRecord.marketplace == entity.marketplace,
                    EntityRecord.entity_type == entity.entity_type,
                    EntityRecord.entity_id == entity.entity_id,
                )
            )
            return result.scalar_one_or_none()


class PostgresSnapshotRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append_if_changed(
        self, entity: EntityRef, payload: dict[str, Any], captured_at: datetime
    ) -> bool:
        payload_hash = canonical_payload_hash(payload)
        statement = (
            pg_insert(SnapshotRecord)
            .values(
                marketplace=entity.marketplace,
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                captured_at=captured_at,
                payload_hash=payload_hash,
                payload=payload,
            )
            .on_conflict_do_nothing(constraint="uq_snapshots_entity_hash")
            .returning(SnapshotRecord.id)
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            return result.scalar_one_or_none() is not None


class PostgresAlertRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save_if_new(self, alert: Alert) -> bool:
        dedupe_key = alert_dedupe_key(alert)
        statement = (
            pg_insert(AlertRecord)
            .values(
                marketplace=alert.entity.marketplace,
                entity_type=alert.entity.entity_type,
                entity_id=alert.entity.entity_id,
                dedupe_key=dedupe_key,
                observed_change=alert.observed_change,
                evidence_classification=(
                    alert.evidence_classification.value if alert.evidence_classification else None
                ),
                severity=alert.severity.value,
                estimated_impact=alert.estimated_impact,
                confidence=alert.confidence,
                observable_causes=alert.observable_causes,
                unexplained_residual=alert.unexplained_residual,
                hypotheses=alert.hypotheses,
                control_comparison=alert.control_comparison,
                recommended_action=alert.recommended_action,
                responsible=alert.responsible,
                deadline=alert.deadline,
                state=alert.state.value,
                outcome=alert.outcome,
                first_observed_at=alert.first_observed_at,
                last_observed_at=alert.last_observed_at,
                detector_version=alert.detector_version,
            )
            .on_conflict_do_nothing(constraint="uq_alerts_dedupe_key")
            .returning(AlertRecord.id)
        )
        async with self._sessions() as session, session.begin():
            alert_id = (await session.execute(statement)).scalar_one_or_none()
            if alert_id is None:
                return False
            session.add_all(
                [
                    EvidenceRecord(
                        alert_id=alert_id,
                        marketplace=alert.entity.marketplace,
                        entity_type=alert.entity.entity_type,
                        entity_id=alert.entity.entity_id,
                        level=e.level.value,
                        statement=e.statement,
                        source=e.source,
                        observed_at=e.observed_at,
                        attributes=e.attributes,
                    )
                    for e in alert.evidence
                ]
            )
            return True

    async def save(self, alert: Alert) -> None:
        await self.save_if_new(alert)


class PostgresOAuthStateRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(
        self,
        *,
        marketplace: str,
        state_hash: str,
        expires_at: datetime,
        verifier_envelope: bytes | None = None,
        redirect_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        synthetic: bool = True,
        created_at: datetime | None = None,
    ) -> None:
        statement = pg_insert(OAuthStateRecord).values(
            marketplace=marketplace,
            state_hash=state_hash,
            verifier_envelope=verifier_envelope,
            redirect_uri=redirect_uri,
            synthetic=synthetic,
            metadata_json=metadata or {},
            created_at=created_at or datetime.now(UTC),
            expires_at=expires_at,
        )
        statement = statement.on_conflict_do_nothing(
            constraint="uq_oauth_states_state_hash"
        ).returning(OAuthStateRecord.id)
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            if result.scalar_one_or_none() is None:
                raise ValueError("OAuth state already exists")

    async def consume(self, *, state_hash: str, consumed_at: datetime | None = None) -> bool:
        now = consumed_at or datetime.now(UTC)
        statement = (
            update(OAuthStateRecord)
            .where(
                OAuthStateRecord.state_hash == state_hash,
                OAuthStateRecord.consumed_at.is_(None),
                OAuthStateRecord.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(OAuthStateRecord.id)
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            return result.scalar_one_or_none() is not None


async def database_healthcheck(sessions: async_sessionmaker[AsyncSession]) -> bool:
    async with sessions() as session:
        result = await session.execute(select(1))
        return result.scalar_one() == 1
