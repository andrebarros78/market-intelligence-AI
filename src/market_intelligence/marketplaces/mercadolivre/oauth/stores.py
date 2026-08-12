from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.persistence.models import OAuthStateRecord

from .db_models import OAuthAuditRecord, OAuthCredentialRecord, OAuthOperationRecord
from .sanitize import sanitize_mapping
from .types import ConsumedTransaction, CredentialEnvelope, RefreshClaim


class OAuthTransactionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(
        self,
        *,
        marketplace: str,
        state_hash: str,
        verifier_envelope: bytes,
        expires_at: datetime,
        redirect_uri: str | None,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> None:
        statement = (
            pg_insert(OAuthStateRecord)
            .values(
                marketplace=marketplace,
                state_hash=state_hash,
                verifier_envelope=verifier_envelope,
                redirect_uri=redirect_uri,
                synthetic=True,
                metadata_json=sanitize_mapping(metadata),
                created_at=created_at,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(constraint="uq_oauth_states_state_hash")
            .returning(OAuthStateRecord.id)
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            if result.scalar_one_or_none() is None:
                raise ValueError("oauth_transaction_conflict")

    async def consume(
        self, *, state_hash: str, consumed_at: datetime
    ) -> ConsumedTransaction | None:
        statement = (
            update(OAuthStateRecord)
            .where(
                OAuthStateRecord.state_hash == state_hash,
                OAuthStateRecord.consumed_at.is_(None),
                OAuthStateRecord.expires_at > consumed_at,
                OAuthStateRecord.synthetic.is_(True),
            )
            .values(consumed_at=consumed_at)
            .returning(
                OAuthStateRecord.state_hash,
                OAuthStateRecord.verifier_envelope,
                OAuthStateRecord.redirect_uri,
                OAuthStateRecord.metadata_json,
            )
        )
        async with self._sessions() as session, session.begin():
            row = (await session.execute(statement)).one_or_none()
            if row is None or row.verifier_envelope is None:
                return None
            return ConsumedTransaction(
                state_hash=row.state_hash,
                verifier_envelope=row.verifier_envelope,
                redirect_uri=row.redirect_uri,
                metadata=row.metadata_json or {},
            )


class OAuthCredentialStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @staticmethod
    def _envelope_from_row(row: Any) -> CredentialEnvelope:
        return CredentialEnvelope(
            marketplace=row.marketplace,
            account_id=row.account_id,
            access_envelope=row.access_envelope,
            refresh_envelope=row.refresh_envelope,
            expires_at=row.expires_at,
            scopes=tuple(row.scopes_json or []),
            key_version=row.key_version,
            version=row.version,
            status=row.status,
        )

    async def put(
        self,
        *,
        marketplace: str,
        account_id: str,
        access_envelope: bytes,
        refresh_envelope: bytes,
        expires_at: datetime,
        scopes: tuple[str, ...],
        key_version: str,
    ) -> int:
        statement = pg_insert(OAuthCredentialRecord).values(
            marketplace=marketplace,
            account_id=account_id,
            access_envelope=access_envelope,
            refresh_envelope=refresh_envelope,
            expires_at=expires_at,
            scopes_json=list(scopes),
            key_version=key_version,
            version=1,
            status="active",
            refresh_claim_id=None,
            refresh_started_at=None,
            last_refresh_at=None,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_oauth_credentials_account",
            set_={
                "access_envelope": statement.excluded.access_envelope,
                "refresh_envelope": statement.excluded.refresh_envelope,
                "expires_at": statement.excluded.expires_at,
                "scopes_json": statement.excluded.scopes_json,
                "key_version": statement.excluded.key_version,
                "version": OAuthCredentialRecord.version + 1,
                "status": "active",
                "refresh_claim_id": None,
                "refresh_started_at": None,
                "last_refresh_at": None,
                "updated_at": datetime.now(UTC),
            },
        ).returning(OAuthCredentialRecord.version)
        async with self._sessions() as session, session.begin():
            return int((await session.execute(statement)).scalar_one())

    async def get(self, *, marketplace: str, account_id: str) -> CredentialEnvelope | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(OAuthCredentialRecord).where(
                        OAuthCredentialRecord.marketplace == marketplace,
                        OAuthCredentialRecord.account_id == account_id,
                    )
                )
            ).scalar_one_or_none()
            return self._envelope_from_row(row) if row is not None else None

    async def claim_refresh(
        self,
        *,
        marketplace: str,
        account_id: str,
        claim_id: str,
        now: datetime,
        claim_ttl_seconds: int,
        dedup_seconds: int,
    ) -> RefreshClaim | None:
        stale_before = now - timedelta(seconds=claim_ttl_seconds)
        dedup_before = now - timedelta(seconds=dedup_seconds)
        statement = (
            update(OAuthCredentialRecord)
            .where(
                OAuthCredentialRecord.marketplace == marketplace,
                OAuthCredentialRecord.account_id == account_id,
                OAuthCredentialRecord.status == "active",
                or_(
                    OAuthCredentialRecord.refresh_claim_id.is_(None),
                    OAuthCredentialRecord.refresh_started_at.is_(None),
                    OAuthCredentialRecord.refresh_started_at <= stale_before,
                ),
                or_(
                    OAuthCredentialRecord.last_refresh_at.is_(None),
                    OAuthCredentialRecord.last_refresh_at <= dedup_before,
                ),
            )
            .values(refresh_claim_id=claim_id, refresh_started_at=now)
            .returning(
                OAuthCredentialRecord.marketplace,
                OAuthCredentialRecord.account_id,
                OAuthCredentialRecord.access_envelope,
                OAuthCredentialRecord.refresh_envelope,
                OAuthCredentialRecord.expires_at,
                OAuthCredentialRecord.scopes_json,
                OAuthCredentialRecord.key_version,
                OAuthCredentialRecord.version,
                OAuthCredentialRecord.status,
            )
        )
        async with self._sessions() as session, session.begin():
            row = (await session.execute(statement)).one_or_none()
            if row is None:
                return None
            return RefreshClaim(claim_id=claim_id, credential=self._envelope_from_row(row))

    async def rotate_claimed(
        self,
        *,
        marketplace: str,
        account_id: str,
        claim_id: str,
        expected_version: int,
        access_envelope: bytes,
        refresh_envelope: bytes,
        expires_at: datetime,
        scopes: tuple[str, ...],
        key_version: str,
        refreshed_at: datetime,
    ) -> int | None:
        statement = (
            update(OAuthCredentialRecord)
            .where(
                OAuthCredentialRecord.marketplace == marketplace,
                OAuthCredentialRecord.account_id == account_id,
                OAuthCredentialRecord.version == expected_version,
                OAuthCredentialRecord.status == "active",
                OAuthCredentialRecord.refresh_claim_id == claim_id,
            )
            .values(
                access_envelope=access_envelope,
                refresh_envelope=refresh_envelope,
                expires_at=expires_at,
                scopes_json=list(scopes),
                key_version=key_version,
                version=OAuthCredentialRecord.version + 1,
                refresh_claim_id=None,
                refresh_started_at=None,
                last_refresh_at=refreshed_at,
                updated_at=refreshed_at,
            )
            .returning(OAuthCredentialRecord.version)
        )
        async with self._sessions() as session, session.begin():
            value = (await session.execute(statement)).scalar_one_or_none()
            return int(value) if value is not None else None

    async def release_refresh_claim(
        self,
        *,
        marketplace: str,
        account_id: str,
        claim_id: str,
        expected_version: int,
    ) -> bool:
        statement = (
            update(OAuthCredentialRecord)
            .where(
                OAuthCredentialRecord.marketplace == marketplace,
                OAuthCredentialRecord.account_id == account_id,
                OAuthCredentialRecord.version == expected_version,
                OAuthCredentialRecord.refresh_claim_id == claim_id,
            )
            .values(refresh_claim_id=None, refresh_started_at=None)
            .returning(OAuthCredentialRecord.id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalar_one_or_none() is not None


class OAuthAuditStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(
        self,
        *,
        correlation_id: str,
        marketplace: str,
        action: str,
        outcome: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = OAuthAuditRecord(
            correlation_id=correlation_id,
            marketplace=marketplace,
            action=action,
            outcome=outcome,
            reason=reason,
            metadata_json=sanitize_mapping(metadata or {}),
        )
        async with self._sessions() as session, session.begin():
            session.add(record)


class OAuthOperationStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def begin(
        self,
        *,
        idempotency_key: str,
        correlation_id: str,
        marketplace: str,
        operation: str,
        requested_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        statement = (
            pg_insert(OAuthOperationRecord)
            .values(
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                marketplace=marketplace,
                operation=operation,
                status="started",
                metadata_json=sanitize_mapping(metadata or {}),
                requested_at=requested_at,
            )
            .on_conflict_do_nothing(constraint="uq_oauth_operations_idempotency")
            .returning(OAuthOperationRecord.id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalar_one_or_none() is not None

    async def complete(
        self,
        *,
        idempotency_key: str,
        status: str,
        completed_at: datetime,
        reason: str | None = None,
    ) -> bool:
        statement = (
            update(OAuthOperationRecord)
            .where(OAuthOperationRecord.idempotency_key == idempotency_key)
            .values(status=status, completed_at=completed_at, reason=reason)
            .returning(OAuthOperationRecord.id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalar_one_or_none() is not None


async def current_schema_revision(sessions: async_sessionmaker[AsyncSession]) -> str | None:
    async with sessions() as session:
        try:
            return (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
        except Exception:
            return None
