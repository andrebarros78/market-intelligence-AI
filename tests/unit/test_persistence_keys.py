from datetime import UTC, datetime

from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.persistence.postgresql import raw_event_dedupe_key


def test_raw_event_dedupe_key_is_stable_for_retry() -> None:
    occurred = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    received = datetime(2026, 8, 12, 12, 1, tzinfo=UTC)
    event = build_raw_event(
        source="mercadolivre",
        event_type="items",
        resource="/items/MLB123",
        occurred_at=occurred,
        received_at=received,
        payload={"id": "MLB123", "status": "active"},
    )
    retry = event.model_copy(update={"received_at": datetime(2026, 8, 12, 12, 2, tzinfo=UTC)})
    assert raw_event_dedupe_key(event) == raw_event_dedupe_key(retry)


def test_raw_event_dedupe_key_changes_for_distinct_occurrence() -> None:
    event_a = build_raw_event(
        source="mercadolivre",
        event_type="items",
        resource="/items/MLB123",
        occurred_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        payload={"id": "MLB123", "status": "active"},
    )
    event_b = event_a.model_copy(update={"occurred_at": datetime(2026, 8, 12, 12, 5, tzinfo=UTC)})
    assert raw_event_dedupe_key(event_a) != raw_event_dedupe_key(event_b)


def test_external_event_id_is_preferred_for_retry_deduplication() -> None:
    event_a = build_raw_event(
        source="mercadolivre",
        event_type="items",
        external_id="notification-123",
        resource="/items/MLB123",
        occurred_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        payload={"attempt": 1},
    )
    event_b = event_a.model_copy(update={"payload": {"attempt": 2}, "payload_hash": "0" * 64})
    assert raw_event_dedupe_key(event_a) == raw_event_dedupe_key(event_b)
