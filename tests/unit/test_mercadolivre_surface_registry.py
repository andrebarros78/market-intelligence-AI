from market_intelligence.marketplaces.mercadolivre.surface_registry import (
    MERCADOLIVRE_SURFACES,
    SurfaceCaptureMode,
    surface_by_id,
    surfaces_for_topic,
)


def test_surface_registry_has_unique_ids_and_core_intelligence_surfaces() -> None:
    ids = [surface.surface_id for surface in MERCADOLIVRE_SURFACES]
    assert len(ids) == len(set(ids))
    for required in (
        "items",
        "price_suggestion",
        "items_prices",
        "item_competition",
        "catalog_suggestions",
        "stock_locations",
        "user_products_families",
        "questions",
        "orders_v2",
        "public_offers",
        "public_candidates",
        "claims",
        "payments",
        "vis_quotation",
    ):
        assert surface_by_id(required) is not None


def test_privacy_rich_surfaces_never_use_generic_safe_get_mode() -> None:
    for surface in MERCADOLIVRE_SURFACES:
        if surface.contains_or_may_contain_pii:
            assert surface.capture_mode is not SurfaceCaptureMode.WEBHOOK_GET_SAFE


def test_known_safe_topics_resolve_to_registered_surfaces() -> None:
    for topic in (
        "items",
        "price_suggestion",
        "items_prices",
        "catalog_item_competition_status",
        "catalog_suggestions",
        "stock-location",
        "user-products-families",
        "fbm_stock_operations",
        "flex-handshakes",
        "public_offers",
        "public_candidates",
    ):
        assert surfaces_for_topic(topic)


def test_legacy_item_quotations_is_explicitly_deprecated() -> None:
    legacy = surface_by_id("legacy_item_quotations")
    assert legacy is not None
    assert legacy.capture_mode is SurfaceCaptureMode.DEPRECATED
    assert legacy.replacement_surface_id == "vis_quotation"
