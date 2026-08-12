from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class PkceMaterial:
    state: str
    state_hash: str
    verifier: str
    challenge: str


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticTokenSet:
    access_token: str
    refresh_token: str
    expires_at: datetime
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorizationPlan:
    state: str
    code_challenge: str
    code_challenge_method: str
    expires_at: datetime


class CredentialHealth(StrEnum):
    HEALTHY = "healthy"
    NEAR_EXPIRY = "near_expiry"
    EXPIRED = "expired"
    REFRESH_REQUIRED = "refresh_required"
    REFRESH_BLOCKED = "refresh_blocked"
    MISSING = "missing"
    INVALID = "invalid"
    CONFIGURATION_INCOMPLETE = "configuration_incomplete"


@dataclass(frozen=True, slots=True)
class CredentialHealthReport:
    status: CredentialHealth
    expires_at: datetime | None = None
    refresh_eligible: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    database_ok: bool
    schema_ok: bool
    settings_ok: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CredentialEnvelope:
    marketplace: str
    account_id: str
    access_envelope: bytes
    refresh_envelope: bytes
    expires_at: datetime
    scopes: tuple[str, ...]
    key_version: str
    version: int
    status: str
    last_refresh_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RefreshClaim:
    claim_id: str
    credential: CredentialEnvelope


@dataclass(frozen=True, slots=True)
class OperationState:
    idempotency_key: str
    correlation_id: str
    marketplace: str
    operation: str
    status: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConsumedTransaction:
    state_hash: str
    verifier_envelope: bytes
    redirect_uri: str | None
    metadata: dict = field(default_factory=dict)
