from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.marketplaces.mercadolivre.http_client import (
    MercadoLivreReadOnlyAdapter,
    MercadoLivreReadResult,
)
from market_intelligence.persistence.models import ChannelEventRecord, OAuthStateRecord
from market_intelligence.persistence.postgresql import channel_event_dedupe_key

from .crypto import EnvelopeCrypto, generate_pkce, state_digest
from .db_models import OAuthAuditRecord, OAuthCredentialRecord
from .sanitize import sanitize_mapping
from .stores import OAuthAuditStore, current_schema_revision
from .types import ConsumedTransaction

Clock = Callable[[], datetime]
_AUTH_BASE = "https://auth.mercadolivre.com.br"
_API_BASE = "https://api.mercadolibre.com"
_TOKEN_PATH = "/oauth/token"
_EXPECTED_SCHEMA = "0008_sovereign_learning"


class RealReadOAuthError(RuntimeError):
    """Stable fail-closed error that never embeds external payloads or credentials."""

    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True, repr=False)
class RealOAuthTokenSet:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RealAuthorizationPlan:
    authorization_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RealOAuthIdentity:
    account_id: str
    site_id: str | None
    nickname: str | None
    status: str | None
    credential_version: int
    schema_fingerprint: str
    channel_event_persisted: bool


@dataclass(frozen=True, slots=True)
class RealReadinessReport:
    ready: bool
    enabled: bool
    database_ok: bool
    schema_ok: bool
    settings_ok: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class RealReadOAuthSettings:
    app_id: str
    client_secret: SecretStr
    redirect_uri: str
    real_read_enabled: bool = False
    transaction_ttl_seconds: int = 600
    expected_schema_revision: str = _EXPECTED_SCHEMA

    @classmethod
    def from_env(cls) -> "RealReadOAuthSettings":
        return cls(
            app_id=os.getenv("MI_ML_APP_ID", ""),
            client_secret=SecretStr(os.getenv("MI_ML_CLIENT_SECRET", "")),
            redirect_uri=os.getenv("MI_ML_REDIRECT_URI", ""),
            real_read_enabled=(
                os.getenv("MI_ML_REAL_READ_ENABLED", "false").lower() == "true"
            ),
        )

    def validate_configuration(self) -> None:
        if not self.app_id or len(self.app_id) > 64 or not self.app_id.isdigit():
            raise ValueError("mercadolivre_real_oauth_app_id_invalid")
        if not self.client_secret.get_secret_value():
            raise ValueError("mercadolivre_real_oauth_client_secret_missing")
        if self.transaction_ttl_seconds <= 0:
            raise ValueError("mercadolivre_real_oauth_ttl_invalid")
        parsed = urlsplit(self.redirect_uri)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("mercadolivre_real_oauth_redirect_uri_invalid")

    def assert_enabled(self) -> None:
        self.validate_configuration()
        if not self.real_read_enabled:
            raise PermissionError("mercadolivre_real_read_disabled")


def _parse_and_validate_read_only_scopes(raw_scope: Any) -> tuple[str, ...]:
    if isinstance(raw_scope, str):
        scopes = tuple(part for part in raw_scope.replace(",", " ").split() if part)
    elif isinstance(raw_scope, list):
        scopes = tuple(str(part) for part in raw_scope if str(part))
    else:
        scopes = ()
    normalized = {scope.strip().lower() for scope in scopes if scope.strip()}
    if "write" in normalized:
        raise RealReadOAuthError("mercadolivre_real_oauth_write_scope_rejected")
    if "read" not in normalized:
        raise RealReadOAuthError("mercadolivre_real_oauth_read_scope_missing")
    return tuple(sorted(normalized))


class MercadoLivreRealOAuthClient:
    """OAuth-only client. It exposes no marketplace mutation operation."""

    def __init__(
        self,
        settings: RealReadOAuthSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 20.0,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._synthetic_transport = isinstance(transport, httpx.MockTransport)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._client: httpx.AsyncClient | None = None
        if settings.real_read_enabled or self._synthetic_transport:
            self._client = httpx.AsyncClient(
                base_url=_API_BASE,
                transport=transport,
                timeout=timeout_seconds,
                follow_redirects=False,
            )

    @property
    def synthetic_transport(self) -> bool:
        return self._synthetic_transport

    def assert_operation_enabled(self) -> None:
        if self._synthetic_transport:
            self.settings.validate_configuration()
        else:
            self.settings.assert_enabled()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _require_transport(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RealReadOAuthError("mercadolivre_real_network_blocked")
        if not self.settings.real_read_enabled and not self._synthetic_transport:
            raise RealReadOAuthError("mercadolivre_real_network_blocked")
        return self._client

    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        self.assert_operation_enabled()
        if not state or not code_challenge:
            raise RealReadOAuthError("mercadolivre_real_oauth_pkce_invalid")
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.app_id,
                "redirect_uri": self.settings.redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{_AUTH_BASE}/authorization?{query}"

    async def exchange(self, *, code: str, verifier: str) -> RealOAuthTokenSet:
        self.assert_operation_enabled()
        if not code or not verifier:
            raise RealReadOAuthError("mercadolivre_real_oauth_exchange_input_invalid")
        client = self._require_transport()
        try:
            response = await client.post(
                _TOKEN_PATH,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.settings.app_id,
                    "client_secret": self.settings.client_secret.get_secret_value(),
                    "code": code,
                    "redirect_uri": self.settings.redirect_uri,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RealReadOAuthError("mercadolivre_real_oauth_transport_failure") from exc
        if response.status_code >= 300:
            raise RealReadOAuthError(
                "mercadolivre_real_oauth_exchange_rejected",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RealReadOAuthError("mercadolivre_real_oauth_invalid_json") from exc
        if not isinstance(payload, dict):
            raise RealReadOAuthError("mercadolivre_real_oauth_invalid_payload")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in")
        if not isinstance(access_token, str) or not access_token:
            raise RealReadOAuthError("mercadolivre_real_oauth_access_token_missing")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise RealReadOAuthError("mercadolivre_real_oauth_refresh_token_missing")
        try:
            lifetime = int(expires_in)
        except (TypeError, ValueError) as exc:
            raise RealReadOAuthError("mercadolivre_real_oauth_expiry_invalid") from exc
        if lifetime <= 0:
            raise RealReadOAuthError("mercadolivre_real_oauth_expiry_invalid")
        scopes = _parse_and_validate_read_only_scopes(payload.get("scope"))
        return RealOAuthTokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=self._clock() + timedelta(seconds=lifetime),
            scopes=scopes,
        )

    async def read_users_me(self, access_token: str) -> MercadoLivreReadResult:
        adapter = MercadoLivreReadOnlyAdapter(
            access_token=SecretStr(access_token),
            transport=self._transport if self._synthetic_transport else None,
            network_allowed=self.settings.real_read_enabled,
        )
        try:
            return await adapter.read_user_me()
        finally:
            await adapter.aclose()


class RealOAuthTransactionStore:
    """Real OAuth states are isolated from the synthetic state namespace."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(
        self,
        *,
        state_hash: str,
        verifier_envelope: bytes,
        redirect_uri: str,
        expires_at: datetime,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> None:
        statement = (
            pg_insert(OAuthStateRecord)
            .values(
                marketplace="mercadolivre",
                state_hash=state_hash,
                verifier_envelope=verifier_envelope,
                redirect_uri=redirect_uri,
                synthetic=False,
                metadata_json=sanitize_mapping(metadata),
                created_at=created_at,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(constraint="uq_oauth_states_state_hash")
            .returning(OAuthStateRecord.id)
        )
        async with self._sessions() as session, session.begin():
            if (await session.execute(statement)).scalar_one_or_none() is None:
                raise ValueError("oauth_transaction_conflict")

    async def consume(
        self,
        *,
        state_hash: str,
        consumed_at: datetime,
    ) -> ConsumedTransaction | None:
        statement = (
            update(OAuthStateRecord)
            .where(
                OAuthStateRecord.marketplace == "mercadolivre",
                OAuthStateRecord.state_hash == state_hash,
                OAuthStateRecord.consumed_at.is_(None),
                OAuthStateRecord.expires_at > consumed_at,
                OAuthStateRecord.synthetic.is_(False),
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


class RealOAuthFinalizationStore:
    """Atomically stores encrypted credentials, /users/me telemetry and success audit."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def finalize(
        self,
        *,
        account_id: str,
        access_envelope: bytes,
        refresh_envelope: bytes,
        expires_at: datetime,
        scopes: tuple[str, ...],
        key_version: str,
        event: ChannelEvent,
        correlation_id: str,
        site_id: str | None,
        schema_fingerprint: str,
        finalized_at: datetime,
    ) -> tuple[int, bool]:
        normalized_scopes = {scope.lower() for scope in scopes}
        if "write" in normalized_scopes or "read" not in normalized_scopes:
            raise PermissionError("mercadolivre_real_oauth_scope_policy_violation")

        credential = pg_insert(OAuthCredentialRecord).values(
            marketplace="mercadolivre",
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
        credential = credential.on_conflict_do_update(
            constraint="uq_oauth_credentials_account",
            set_={
                "access_envelope": credential.excluded.access_envelope,
                "refresh_envelope": credential.excluded.refresh_envelope,
                "expires_at": credential.excluded.expires_at,
                "scopes_json": credential.excluded.scopes_json,
                "key_version": credential.excluded.key_version,
                "version": OAuthCredentialRecord.version + 1,
                "status": "active",
                "refresh_claim_id": None,
                "refresh_started_at": None,
                "last_refresh_at": None,
                "updated_at": finalized_at,
            },
        ).returning(OAuthCredentialRecord.version)

        safe_attributes = sanitize_mapping(event.attributes)
        channel = (
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
                attributes=safe_attributes,
            )
            .on_conflict_do_nothing(constraint="uq_channel_events_dedupe_key")
            .returning(ChannelEventRecord.id)
        )

        async with self._sessions() as session, session.begin():
            version = int((await session.execute(credential)).scalar_one())
            event_persisted = (await session.execute(channel)).scalar_one_or_none() is not None
            session.add(
                OAuthAuditRecord(
                    correlation_id=correlation_id,
                    marketplace="mercadolivre",
                    action="real_read_callback",
                    outcome="success",
                    metadata_json=sanitize_mapping(
                        {
                            "account_id": account_id,
                            "site_id": site_id,
                            "credential_version": version,
                            "users_me_status": event.status_code,
                            "request_id": event.request_id,
                            "schema_fingerprint": schema_fingerprint,
                            "channel_event_persisted": event_persisted,
                            "scope_policy": "read-only",
                        }
                    ),
                )
            )
            return version, event_persisted


class RealReadOAuthService:
    def __init__(
        self,
        *,
        settings: RealReadOAuthSettings,
        crypto: EnvelopeCrypto,
        transactions: RealOAuthTransactionStore,
        finalization: RealOAuthFinalizationStore,
        audit: OAuthAuditStore,
        client: MercadoLivreRealOAuthClient,
        clock: Clock,
    ) -> None:
        self.settings = settings
        self.crypto = crypto
        self.transactions = transactions
        self.finalization = finalization
        self.audit = audit
        self.client = client
        self.clock = clock

    async def start(
        self,
        *,
        expected_account_id: str | None = None,
        correlation_id: str | None = None,
    ) -> RealAuthorizationPlan:
        self.client.assert_operation_enabled()
        if expected_account_id and (
            not expected_account_id.isdigit() or len(expected_account_id) > 32
        ):
            raise ValueError("mercadolivre_expected_account_id_invalid")
        now = self.clock()
        pkce = generate_pkce()
        expires_at = now + timedelta(seconds=self.settings.transaction_ttl_seconds)
        verifier_envelope = self.crypto.seal(
            pkce.verifier,
            context=f"oauth-real-state:{pkce.state_hash}",
        )
        metadata: dict[str, Any] = {"pkce_method": "S256"}
        if expected_account_id:
            metadata["expected_account_id"] = expected_account_id
        await self.transactions.create(
            state_hash=pkce.state_hash,
            verifier_envelope=verifier_envelope,
            redirect_uri=self.settings.redirect_uri,
            expires_at=expires_at,
            metadata=metadata,
            created_at=now,
        )
        await self.audit.append(
            correlation_id=correlation_id or uuid4().hex,
            marketplace="mercadolivre",
            action="real_read_transaction_start",
            outcome="success",
            metadata={
                "pkce_method": "S256",
                "expected_account_bound": bool(expected_account_id),
            },
        )
        return RealAuthorizationPlan(
            authorization_url=self.client.authorization_url(
                state=pkce.state,
                code_challenge=pkce.challenge,
            ),
            expires_at=expires_at,
        )

    @staticmethod
    def _identity(
        payload: dict[str, Any],
    ) -> tuple[str, str | None, str | None, str | None]:
        raw_id = payload.get("id")
        if isinstance(raw_id, bool) or raw_id is None:
            raise RealReadOAuthError("mercadolivre_users_me_identity_missing")
        account_id = str(raw_id)
        if not account_id.isdigit() or len(account_id) > 32:
            raise RealReadOAuthError("mercadolivre_users_me_identity_invalid")
        site_id = payload.get("site_id") if isinstance(payload.get("site_id"), str) else None
        nickname = payload.get("nickname") if isinstance(payload.get("nickname"), str) else None
        status = payload.get("status") if isinstance(payload.get("status"), str) else None
        return account_id, site_id, nickname, status

    async def callback(
        self,
        *,
        state: str,
        code: str,
        correlation_id: str | None = None,
    ) -> RealOAuthIdentity:
        self.client.assert_operation_enabled()
        correlation = correlation_id or uuid4().hex
        digest = state_digest(state)
        transaction = await self.transactions.consume(
            state_hash=digest,
            consumed_at=self.clock(),
        )
        if transaction is None:
            await self.audit.append(
                correlation_id=correlation,
                marketplace="mercadolivre",
                action="real_read_callback",
                outcome="rejected",
                reason="state_invalid_expired_or_replayed",
            )
            raise PermissionError("oauth_callback_rejected")
        try:
            if transaction.redirect_uri != self.settings.redirect_uri:
                raise PermissionError("oauth_redirect_binding_mismatch")
            verifier = self.crypto.open(
                transaction.verifier_envelope,
                context=f"oauth-real-state:{digest}",
            )
            tokens = await self.client.exchange(code=code, verifier=verifier)
            users_me = await self.client.read_users_me(tokens.access_token)
            account_id, site_id, nickname, status = self._identity(users_me.payload)
            expected = transaction.metadata.get("expected_account_id")
            if expected is not None and str(expected) != account_id:
                raise PermissionError("oauth_identity_binding_mismatch")

            event = ChannelEvent(
                marketplace="mercadolivre",
                direction="outbound",
                operation="/users/me",
                observed_at=users_me.telemetry.observed_at,
                status_code=users_me.telemetry.status_code,
                latency_ms=users_me.telemetry.latency_ms,
                attempt=users_me.telemetry.attempts,
                correlation_id=correlation,
                request_id=users_me.telemetry.request_id,
                attributes={
                    "partial_content": users_me.telemetry.partial_content,
                    "operational_headers": users_me.telemetry.operational_headers,
                },
            )
            version, event_persisted = await self.finalization.finalize(
                account_id=account_id,
                access_envelope=self.crypto.seal(
                    tokens.access_token,
                    context=f"oauth-access:mercadolivre:{account_id}",
                ),
                refresh_envelope=self.crypto.seal(
                    tokens.refresh_token,
                    context=f"oauth-refresh:mercadolivre:{account_id}",
                ),
                expires_at=tokens.expires_at,
                scopes=tokens.scopes,
                key_version=self.crypto.key_version,
                event=event,
                correlation_id=correlation,
                site_id=site_id,
                schema_fingerprint=users_me.schema_fingerprint,
                finalized_at=self.clock(),
            )
        except Exception as exc:
            await self.audit.append(
                correlation_id=correlation,
                marketplace="mercadolivre",
                action="real_read_callback",
                outcome="failed",
                reason=type(exc).__name__,
            )
            raise
        return RealOAuthIdentity(
            account_id=account_id,
            site_id=site_id,
            nickname=nickname,
            status=status,
            credential_version=version,
            schema_fingerprint=users_me.schema_fingerprint,
            channel_event_persisted=event_persisted,
        )


@dataclass(slots=True)
class RealReadOAuthRuntime:
    settings: RealReadOAuthSettings
    service: RealReadOAuthService
    sessions: async_sessionmaker[AsyncSession]

    async def readiness(self) -> RealReadinessReport:
        reasons: list[str] = []
        settings_ok = True
        try:
            self.settings.validate_configuration()
        except Exception:
            settings_ok = False
            reasons.append("settings_invalid")
        if not self.settings.real_read_enabled:
            reasons.append("real_read_disabled")
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
        return RealReadinessReport(
            ready=(
                settings_ok
                and self.settings.real_read_enabled
                and database_ok
                and schema_ok
            ),
            enabled=self.settings.real_read_enabled,
            database_ok=database_ok,
            schema_ok=schema_ok,
            settings_ok=settings_ok,
            reasons=tuple(reasons),
        )


async def close_real_read_oauth_runtime(runtime: RealReadOAuthRuntime) -> None:
    await runtime.service.client.aclose()


def build_real_read_oauth_runtime(
    *,
    sessions: async_sessionmaker[AsyncSession],
    encryption_key: bytes,
    settings: RealReadOAuthSettings,
    clock: Clock | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RealReadOAuthRuntime:
    settings.validate_configuration()
    resolved_clock = clock or (lambda: datetime.now(UTC))
    crypto = EnvelopeCrypto(encryption_key)
    transactions = RealOAuthTransactionStore(sessions)
    finalization = RealOAuthFinalizationStore(sessions)
    audit = OAuthAuditStore(sessions)
    client = MercadoLivreRealOAuthClient(
        settings,
        transport=transport,
        clock=resolved_clock,
    )
    service = RealReadOAuthService(
        settings=settings,
        crypto=crypto,
        transactions=transactions,
        finalization=finalization,
        audit=audit,
        client=client,
        clock=resolved_clock,
    )
    return RealReadOAuthRuntime(
        settings=settings,
        service=service,
        sessions=sessions,
    )
