from __future__ import annotations

from typing import Any

from temporalio.exceptions import ApplicationError

WORKFLOW_ALLOWED_KEYS = frozenset({"account_id", "correlation_id"})
ACTIVITY_ALLOWED_KEYS = frozenset({"account_id", "correlation_id", "idempotency_key"})
_FORBIDDEN_KEYS = frozenset({
    "state", "code", "authorization_code", "code_verifier", "access_token",
    "refresh_token", "client_secret", "authorization", "encryption_key",
    "access_envelope", "refresh_envelope", "verifier_envelope",
})


def validate_safe_oauth_temporal_payload(
    payload: Any,
    *,
    activity_payload: bool = False,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ApplicationError("OAuth Temporal payload must be an object", non_retryable=True)
    allowed = ACTIVITY_ALLOWED_KEYS if activity_payload else WORKFLOW_ALLOWED_KEYS
    keys = {str(key) for key in payload}
    lowered = {key.lower() for key in keys}
    if lowered & _FORBIDDEN_KEYS:
        raise ApplicationError("Sensitive OAuth field is forbidden in Temporal history", non_retryable=True)
    if any(key.endswith(("_token", "_secret", "_envelope")) for key in lowered):
        raise ApplicationError("Sensitive OAuth field is forbidden in Temporal history", non_retryable=True)
    unexpected = keys - allowed
    if unexpected:
        raise ApplicationError("Unexpected OAuth Temporal field", non_retryable=True)

    result: dict[str, str] = {}
    for key in allowed:
        if key in payload:
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise ApplicationError("OAuth Temporal identifiers must be non-empty strings", non_retryable=True)
            if len(value) > 160:
                raise ApplicationError("OAuth Temporal identifier is too long", non_retryable=True)
            result[key] = value
    if "account_id" not in result:
        raise ApplicationError("account_id is required", non_retryable=True)
    if activity_payload and "idempotency_key" not in result:
        raise ApplicationError("idempotency_key is required", non_retryable=True)
    return result
