from __future__ import annotations

import pytest
from temporalio.exceptions import ApplicationError

from market_intelligence.workflows.oauth_safety import validate_safe_oauth_temporal_payload


def test_oauth_workflow_payload_accepts_only_non_secret_identifiers() -> None:
    safe = validate_safe_oauth_temporal_payload(
        {"account_id": "ML-123", "correlation_id": "corr-123"}
    )
    assert safe == {"account_id": "ML-123", "correlation_id": "corr-123"}


@pytest.mark.parametrize(
    "field",
    [
        "state",
        "code",
        "code_verifier",
        "access_token",
        "refresh_token",
        "client_secret",
        "authorization",
        "encryption_key",
        "access_envelope",
        "refresh_envelope",
    ],
)
def test_oauth_workflow_payload_rejects_sensitive_fields(field: str) -> None:
    with pytest.raises(ApplicationError):
        validate_safe_oauth_temporal_payload(
            {"account_id": "ML-123", field: "must-never-enter-history"}
        )


def test_oauth_workflow_payload_rejects_unknown_fields() -> None:
    with pytest.raises(ApplicationError):
        validate_safe_oauth_temporal_payload(
            {"account_id": "ML-123", "unexpected": "value"}
        )


def test_oauth_activity_requires_hashed_workflow_idempotency_identifier() -> None:
    safe = validate_safe_oauth_temporal_payload(
        {"account_id": "ML-123", "idempotency_key": "mi-abc123"},
        activity_payload=True,
    )
    assert safe["idempotency_key"] == "mi-abc123"
