from __future__ import annotations

import json

import pytest

from market_intelligence.marketplaces.mercadolivre.webhook_surface_probe import (
    resolve_safe_notification_resource,
    schema_only_observation,
)


@pytest.mark.parametrize(
    ("topic", "resource", "expected"),
    [
        ("items", "/items/MLB123", "/items/MLB123"),
        ("price_suggestion", "suggestions/items/MLB123/details", "/suggestions/items/MLB123/details"),
        ("catalog_item_competition_status", "/items/MLB123/price_to_win", "/items/MLB123/price_to_win"),
        ("catalog_suggestions", "/catalog_suggestions/MLB123", "/catalog_suggestions/MLB123"),
        ("public_offers", "/seller-promotions/offers/OFFER-123", "/seller-promotions/offers/OFFER-123"),
        ("public_candidates", "/seller-promotions/candidates/CANDIDATE-MLB123-1", "/seller-promotions/candidates/CANDIDATE-MLB123-1"),
        ("items_prices", "/items/MLB123", "/items/MLB123/prices"),
        ("stock-location", "/user-products/MLBU123/stock", "/user-products/MLBU123/stock"),
        ("user-products-families", "/sites/MLB/user-products-families/987123", "/sites/MLB/user-products-families/987123"),
        ("fbm_stock_operations", "/stock/fulfillment/operations/9876", "/stock/fulfillment/operations/9876"),
        ("flex-handshakes", "/flex/sites/MLB/shipments/407323124706/assignment/v1", "/flex/sites/MLB/shipments/407323124706/assignment/v1"),
    ],
)
def test_safe_notification_surfaces_are_resolved(topic: str, resource: str, expected: str) -> None:
    assert resolve_safe_notification_resource(topic, resource) == expected


@pytest.mark.parametrize(
    ("topic", "resource"),
    [
        ("messages", "3f6da1e35ac84f70a24af7360d24c7bc"),
        ("orders", "/orders/123"),
        ("payments", "/payments/123"),
        ("claims", "/v1/claims/123"),
        ("items", "/items/MLB123/description"),
        ("catalog_item_competition_status", "/items/MLB123"),
        ("stock-location", "/user-products/MLBU123"),
        ("public_candidates", "/seller-promotions/offers/123"),
        ("items_prices", "/items/MLB123?access_token=secret"),
        ("items", "https://evil.example/items/MLB123"),
        ("items", "/items/../../users/me"),
    ],
)
def test_pii_rich_unsupported_or_wrong_shape_resources_are_not_followed(topic: str, resource: str) -> None:
    assert resolve_safe_notification_resource(topic, resource) is None


def test_schema_only_observation_never_persists_values() -> None:
    payload = {
        "id": "MLB123",
        "buyer": {
            "email": "private@example.com",
            "phone": "+5511999999999",
            "address": {"street": "Rua Privada", "number": 42},
        },
        "prices": [{"amount": 123.45, "currency_id": "BRL"}],
        "access_token": "must-never-persist",
    }
    observation = schema_only_observation(payload)
    encoded = json.dumps(observation, sort_keys=True, ensure_ascii=False)

    assert "private@example.com" not in encoded
    assert "+5511999999999" not in encoded
    assert "Rua Privada" not in encoded
    assert "123.45" not in encoded
    assert "must-never-persist" not in encoded
    assert observation["schema_fingerprint"]
    assert "buyer" in observation["top_level_fields"]
    assert any(path.startswith("$.buyer.email:") for path in observation["schema_paths"])


def test_schema_path_collection_is_bounded() -> None:
    payload = {f"field_{index}": {"nested": index} for index in range(2000)}
    observation = schema_only_observation(payload)
    assert len(observation["schema_paths"]) <= 512
