from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from .crypto import EnvelopeCrypto, generate_pkce, state_digest
from .settings import OAuthRuntimeSettings
from .stores import OAuthAuditStore, OAuthCredentialStore, OAuthOperationStore, OAuthTransactionStore
from .synthetic_client import SyntheticOAuthClient
from .types import AuthorizationPlan, CredentialHealth, CredentialHealthReport

Clock = Callable[[], datetime]


class OAuthTransactionService:
    def __init__(self, *, settings: OAuthRuntimeSettings, crypto: EnvelopeCrypto,
                 store: OAuthTransactionStore, credentials: OAuthCredentialStore,
                 audit: OAuthAuditStore, client: SyntheticOAuthClient, clock: Clock) -> None:
        self.settings = settings
        self.crypto = crypto
        self.store = store
        self.credentials = credentials
        self.audit = audit
        self.client = client
        self.clock = clock

    async def start(self, *, account_id: str, redirect_uri: str | None = None,
                    correlation_id: str | None = None) -> AuthorizationPlan:
        self.settings.validate_for_r11()
        now = self.clock()
        pkce = generate_pkce()
        expires_at = now + timedelta(seconds=self.settings.transaction_ttl_seconds)
        verifier_envelope = self.crypto.seal(pkce.verifier, context=f"oauth-state:{pkce.state_hash}")
        correlation = correlation_id or uuid4().hex
        await self.store.create(
            marketplace=self.settings.marketplace, state_hash=pkce.state_hash,
            verifier_envelope=verifier_envelope, expires_at=expires_at,
            redirect_uri=redirect_uri, metadata={"account_id": account_id, "pkce_method": "S256"},
            created_at=now,
        )
        await self.audit.append(correlation_id=correlation, marketplace=self.settings.marketplace,
                                action="transaction_start", outcome="success",
                                metadata={"account_id": account_id, "pkce_method": "S256"})
        return AuthorizationPlan(state=pkce.state, code_challenge=pkce.challenge,
                                 code_challenge_method="S256", expires_at=expires_at)

    async def callback(self, *, account_id: str, state: str, code: str,
                       correlation_id: str | None = None) -> int:
        self.settings.validate_for_r11()
        correlation = correlation_id or uuid4().hex
        digest = state_digest(state)
        transaction = await self.store.consume(state_hash=digest, consumed_at=self.clock())
        if transaction is None:
            await self.audit.append(correlation_id=correlation, marketplace=self.settings.marketplace,
                                    action="synthetic_callback", outcome="rejected",
                                    reason="state_invalid_expired_or_replayed",
                                    metadata={"account_id": account_id})
            raise PermissionError("oauth_callback_rejected")
        try:
            verifier = self.crypto.open(transaction.verifier_envelope, context=f"oauth-state:{digest}")
            tokens = await self.client.exchange(code=code, verifier=verifier)
            version = await self.credentials.put(
                marketplace=self.settings.marketplace, account_id=account_id,
                access_envelope=self.crypto.seal(tokens.access_token,
                    context=f"oauth-access:{self.settings.marketplace}:{account_id}"),
                refresh_envelope=self.crypto.seal(tokens.refresh_token,
                    context=f"oauth-refresh:{self.settings.marketplace}:{account_id}"),
                expires_at=tokens.expires_at, scopes=tokens.scopes, key_version=self.crypto.key_version,
            )
        except Exception as exc:
            await self.audit.append(correlation_id=correlation, marketplace=self.settings.marketplace,
                                    action="synthetic_callback", outcome="failed",
                                    reason=type(exc).__name__, metadata={"account_id": account_id})
            raise
        await self.audit.append(correlation_id=correlation, marketplace=self.settings.marketplace,
                                action="synthetic_callback", outcome="success",
                                metadata={"account_id": account_id, "credential_version": version})
        return version


class OAuthRefreshService:
    def __init__(self, *, settings: OAuthRuntimeSettings, crypto: EnvelopeCrypto,
                 credentials: OAuthCredentialStore, audit: OAuthAuditStore,
                 client: SyntheticOAuthClient, clock: Clock) -> None:
        self.settings = settings
        self.crypto = crypto
        self.credentials = credentials
        self.audit = audit
        self.client = client
        self.clock = clock

    async def refresh(self, *, account_id: str, correlation_id: str | None = None) -> int:
        self.settings.validate_for_r11()
        if not self.settings.synthetic_refresh_enabled:
            raise PermissionError("synthetic_refresh_blocked")
        correlation = correlation_id or uuid4().hex
        now = self.clock()
        claim_id = uuid4().hex
        claim = await self.credentials.claim_refresh(
            marketplace=self.settings.marketplace,
            account_id=account_id,
            claim_id=claim_id,
            now=now,
            claim_ttl_seconds=self.settings.refresh_claim_ttl_seconds,
            dedup_seconds=self.settings.refresh_dedup_seconds,
        )
        if claim is None:
            current = await self.credentials.get(
                marketplace=self.settings.marketplace, account_id=account_id
            )
            if current is None:
                raise LookupError("credential_missing")
            await self.audit.append(
                correlation_id=correlation,
                marketplace=self.settings.marketplace,
                action="synthetic_refresh",
                outcome="rejected",
                reason="refresh_conflict_or_deduplicated",
                metadata={"account_id": account_id, "credential_version": current.version},
            )
            raise RuntimeError("refresh_conflict")

        current = claim.credential
        try:
            refresh_token = self.crypto.open(
                current.refresh_envelope,
                context=f"oauth-refresh:{self.settings.marketplace}:{account_id}",
            )
            tokens = await self.client.refresh(refresh_token=refresh_token)
            next_version = await self.credentials.rotate_claimed(
                marketplace=self.settings.marketplace,
                account_id=account_id,
                claim_id=claim.claim_id,
                expected_version=current.version,
                access_envelope=self.crypto.seal(
                    tokens.access_token,
                    context=f"oauth-access:{self.settings.marketplace}:{account_id}",
                ),
                refresh_envelope=self.crypto.seal(
                    tokens.refresh_token,
                    context=f"oauth-refresh:{self.settings.marketplace}:{account_id}",
                ),
                expires_at=tokens.expires_at,
                scopes=tokens.scopes,
                key_version=self.crypto.key_version,
                refreshed_at=now,
            )
            if next_version is None:
                raise RuntimeError("refresh_claim_lost")
        except Exception as exc:
            await self.credentials.release_refresh_claim(
                marketplace=self.settings.marketplace,
                account_id=account_id,
                claim_id=claim.claim_id,
                expected_version=current.version,
            )
            await self.audit.append(
                correlation_id=correlation,
                marketplace=self.settings.marketplace,
                action="synthetic_refresh",
                outcome="failed",
                reason=type(exc).__name__,
                metadata={"account_id": account_id, "previous_version": current.version},
            )
            raise
        await self.audit.append(
            correlation_id=correlation,
            marketplace=self.settings.marketplace,
            action="synthetic_refresh",
            outcome="success",
            metadata={"account_id": account_id, "credential_version": next_version},
        )
        return next_version


class CredentialHealthService:
    def __init__(self, *, settings: OAuthRuntimeSettings, credentials: OAuthCredentialStore,
                 clock: Clock) -> None:
        self.settings = settings
        self.credentials = credentials
        self.clock = clock

    async def get(self, *, account_id: str) -> CredentialHealthReport:
        try:
            self.settings.validate_for_r11()
        except Exception:
            return CredentialHealthReport(status=CredentialHealth.CONFIGURATION_INCOMPLETE,
                                          reasons=("settings_invalid",))
        current = await self.credentials.get(marketplace=self.settings.marketplace, account_id=account_id)
        if current is None:
            return CredentialHealthReport(status=CredentialHealth.MISSING, reasons=("credential_missing",))
        if current.status != "active":
            return CredentialHealthReport(status=CredentialHealth.INVALID, expires_at=current.expires_at,
                                          reasons=("credential_not_active",))
        now = self.clock()
        if current.expires_at <= now:
            status = CredentialHealth.EXPIRED if self.settings.synthetic_refresh_enabled else CredentialHealth.REFRESH_BLOCKED
            return CredentialHealthReport(status=status, expires_at=current.expires_at,
                                          refresh_eligible=self.settings.synthetic_refresh_enabled,
                                          reasons=("credential_expired",))
        if current.expires_at <= now + timedelta(seconds=self.settings.refresh_margin_seconds):
            status = CredentialHealth.REFRESH_REQUIRED if self.settings.synthetic_refresh_enabled else CredentialHealth.REFRESH_BLOCKED
            return CredentialHealthReport(status=status, expires_at=current.expires_at,
                                          refresh_eligible=self.settings.synthetic_refresh_enabled,
                                          reasons=("within_refresh_margin",))
        if current.expires_at <= now + timedelta(seconds=self.settings.refresh_margin_seconds * 2):
            return CredentialHealthReport(status=CredentialHealth.NEAR_EXPIRY,
                                          expires_at=current.expires_at, reasons=("near_expiry",))
        return CredentialHealthReport(status=CredentialHealth.HEALTHY, expires_at=current.expires_at)


class OAuthOperationService:
    def __init__(self, *, settings: OAuthRuntimeSettings, store: OAuthOperationStore,
                 audit: OAuthAuditStore, clock: Clock) -> None:
        self.settings = settings
        self.store = store
        self.audit = audit
        self.clock = clock

    async def begin(self, *, operation: str, idempotency_key: str,
                    correlation_id: str | None = None) -> bool:
        correlation = correlation_id or uuid4().hex
        if operation in {"real_oauth", "marketplace_write"}:
            await self.audit.append(correlation_id=correlation, marketplace=self.settings.marketplace,
                                    action=operation, outcome="blocked", reason="policy_gate")
            raise PermissionError("operation_blocked_by_policy")
        created = await self.store.begin(idempotency_key=idempotency_key, correlation_id=correlation,
                                         marketplace=self.settings.marketplace, operation=operation,
                                         requested_at=self.clock())
        if not created:
            return False
        await self.audit.append(correlation_id=correlation, marketplace=self.settings.marketplace,
                                action=operation, outcome="started")
        return True
