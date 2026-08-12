from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.core.contracts import Alert, EntityRef
from market_intelligence.ingestion.events import RawEvent, canonical_payload_hash
from market_intelligence.persistence.models import (
    AlertRecord,
    EntityRecord,
    EvidenceRecord,
    OAuthStateRecord,
    RawEventRecord,
    SnapshotRecord,
)


def raw_event_dedupe_key(event: RawEvent) -> str:
    if event.external_id:
        material = "\x1f".join([event.source, event.event_type, "external", event.external_id]).encode("utf-8")
    else:
        occurred = event.occurred_at.isoformat() if event.occurred_at else ""
        material = "\x1f".join(
            [event.source, event.event_type, event.resource or "", occurred, event.payload_hash]
        ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


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
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            return result.rowcount == 1


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
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            return result.rowcount == 1


class PostgresAlertRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, alert: Alert) -> None:
        alert_record = AlertRecord(
            marketplace=alert.entity.marketplace,
            entity_type=alert.entity.entity_type,
            entity_id=alert.entity.entity_id,
            observed_change=alert.observed_change,
            severity=alert.severity.value,
            estimated_impact=alert.estimated_impact,
            confidence=alert.confidence,
            recommended_action=alert.recommended_action,
            responsible=alert.responsible,
            deadline=alert.deadline,
            state=alert.state.value,
            outcome=alert.outcome,
        )
        async with self._sessions() as session, session.begin():
            session.add(alert_record)
            await session.flush()
            session.add_all(
                [
                    EvidenceRecord(
                        alert_id=alert_record.id,
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
        statement = statement.on_conflict_do_nothing(constraint="uq_oauth_states_state_hash")
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            if result.rowcount != 1:
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
