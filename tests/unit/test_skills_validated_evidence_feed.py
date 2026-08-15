from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_intelligence.skills.evidence_feed import build_validated_status_cycle_evidence


def test_validated_status_cycle_becomes_fact() -> None:
    evidence = build_validated_status_cycle_evidence(
        item_id="MLB123",
        observed_at=datetime.now(timezone.utc),
        before_status="active",
        paused_status="paused",
        after_status="active",
        webhook_validated=True,
        official_get_validated=True,
        proof_id="proof-1",
    )
    assert evidence.marketplace == "mercadolivre"
    assert evidence.evidence["classification"] == "FATO"
    assert evidence.evidence["webhook_validated"] is True
    assert evidence.evidence["official_get_validated"] is True


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("before_status", "paused", "before_status_not_active"),
        ("paused_status", "active", "pause_not_confirmed"),
        ("after_status", "paused", "reactivation_not_confirmed"),
        ("webhook_validated", False, "webhook_not_validated"),
        ("official_get_validated", False, "official_get_not_validated"),
    ],
)
def test_unvalidated_cycle_never_enters_skills(field: str, value: object, error: str) -> None:
    kwargs: dict[str, object] = {
        "item_id": "MLB123",
        "observed_at": datetime.now(timezone.utc),
        "before_status": "active",
        "paused_status": "paused",
        "after_status": "active",
        "webhook_validated": True,
        "official_get_validated": True,
        "proof_id": "proof-1",
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=error):
        build_validated_status_cycle_evidence(**kwargs)  # type: ignore[arg-type]
