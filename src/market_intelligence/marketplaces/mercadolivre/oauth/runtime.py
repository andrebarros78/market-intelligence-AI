from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .crypto import EnvelopeCrypto
from .services import CredentialHealthService, OAuthOperationService, OAuthRefreshService, OAuthTransactionService
from .settings import OAuthRuntimeSettings
from .stores import OAuthAuditStore, OAuthCredentialStore, OAuthOperationStore, OAuthTransactionStore, current_schema_revision
from .synthetic_client import SyntheticOAuthClient
from .types import ReadinessReport


@dataclass(slots=True)
class SyntheticOAuthRuntime:
    settings: OAuthRuntimeSettings
    transactions: OAuthTransactionService
    refresh: OAuthRefreshService
    health: CredentialHealthService
    operations: OAuthOperationService
    client: SyntheticOAuthClient
    sessions: async_sessionmaker[AsyncSession]

    async def readiness(self) -> ReadinessReport:
        settings_ok = True
        reasons: list[str] = []
        try:
            self.settings.validate_for_r11()
        except Exception:
            settings_ok = False
            reasons.append("settings_invalid")
        database_ok = False
        schema_ok = False
        try:
            async with self.sessions() as session:
                database_ok = bool((await session.execute(select(1))).scalar_one() == 1)
            revision = await current_schema_revision(self.sessions)
            schema_ok = revision == self.settings.expected_schema_revision
            if not schema_ok:
                reasons.append("schema_revision_mismatch")
        except Exception:
            reasons.append("database_unavailable")
        return ReadinessReport(ready=settings_ok and database_ok and schema_ok,
                               database_ok=database_ok, schema_ok=schema_ok,
                               settings_ok=settings_ok, reasons=tuple(reasons))


def build_synthetic_oauth_runtime(*, sessions: async_sessionmaker[AsyncSession], encryption_key: bytes,
                                  settings: OAuthRuntimeSettings | None = None,
                                  clock: Callable[[], datetime] | None = None,
                                  client: SyntheticOAuthClient | None = None) -> SyntheticOAuthRuntime:
    resolved = settings or OAuthRuntimeSettings()
    resolved.validate_for_r11()
    resolved_clock = clock or (lambda: datetime.now(UTC))
    crypto = EnvelopeCrypto(encryption_key)
    transaction_store = OAuthTransactionStore(sessions)
    credential_store = OAuthCredentialStore(sessions)
    audit_store = OAuthAuditStore(sessions)
    operation_store = OAuthOperationStore(sessions)
    resolved_client = client or SyntheticOAuthClient(clock=resolved_clock)
    return SyntheticOAuthRuntime(
        settings=resolved,
        transactions=OAuthTransactionService(settings=resolved, crypto=crypto, store=transaction_store,
            credentials=credential_store, audit=audit_store, client=resolved_client, clock=resolved_clock),
        refresh=OAuthRefreshService(settings=resolved, crypto=crypto, credentials=credential_store,
            audit=audit_store, client=resolved_client, clock=resolved_clock),
        health=CredentialHealthService(settings=resolved, credentials=credential_store, clock=resolved_clock),
        operations=OAuthOperationService(settings=resolved, store=operation_store, audit=audit_store,
            clock=resolved_clock),
        client=resolved_client, sessions=sessions,
    )
