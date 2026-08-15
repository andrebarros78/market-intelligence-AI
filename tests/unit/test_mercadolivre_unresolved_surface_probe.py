from __future__ import annotations

import json

from market_intelligence.marketplaces.mercadolivre.webhook_surface_probe import unresolved_surface_observation


def test_unknown_topic_is_recorded_without_resource_identifier() -> None:
    observation = unresolved_surface_observation(
        "future_hidden_signal",
        "/future-resource/customer-private-id-123/detail",
    )
    encoded = json.dumps(observation, sort_keys=True)
    assert observation["known_topic"] is False
    assert observation["resolution_status"] == "unknown_notification_topic"
    assert observation["official_get"] is False
    assert observation["values_persisted"] is False
    assert observation["resource_root"] == "[REDACTED]"
    assert observation["resource_root_hash"]
    assert "future-resource" not in encoded
    assert "customer-private-id-123" not in encoded


def test_known_pii_topic_is_not_generic_followed_or_persisted() -> None:
    observation = unresolved_surface_observation("messages", "buyer-message-private-id")
    encoded = json.dumps(observation, sort_keys=True)
    assert observation["known_topic"] is True
    assert observation["resolution_status"] == "dedicated_privacy_or_metadata_reader_required"
    assert observation["official_get"] is False
    assert observation["resource_root"] == "[REDACTED]"
    assert "buyer-message-private-id" not in encoded
