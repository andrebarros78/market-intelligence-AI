from market_intelligence.marketplaces.mercadolivre.schema import (
    SchemaBaselineRegistry,
    schema_fingerprint,
)


def test_schema_fingerprint_ignores_values_but_detects_shape_changes() -> None:
    first = {"id": "MLB1", "status": "active", "seller": {"id": 10}}
    same_shape = {"id": "MLB2", "status": "paused", "seller": {"id": 99}}
    changed = {
        "id": "MLB2",
        "status": "paused",
        "seller": {"id": 99},
        "new_field": {"enabled": True},
    }
    assert schema_fingerprint(first) == schema_fingerprint(same_shape)
    assert schema_fingerprint(first) != schema_fingerprint(changed)


def test_registry_reports_added_and_removed_paths_without_claiming_cause() -> None:
    registry = SchemaBaselineRegistry()
    initial = registry.observe("order", {"id": 1, "buyer": {"id": 2}})
    assert initial.baseline_created is True
    assert initial.changed is False

    stable = registry.observe("order", {"id": 3, "buyer": {"id": 4}})
    assert stable.changed is False

    drift = registry.observe("order", {"id": 3, "seller": {"id": 5}})
    assert drift.changed is True
    assert any("seller" in path for path in drift.added_paths)
    assert any("buyer" in path for path in drift.removed_paths)
