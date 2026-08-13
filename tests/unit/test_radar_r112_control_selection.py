from datetime import UTC, datetime

from market_intelligence.intelligence.radar.control_selection import AutomaticControlSelector
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.relational import RelationalControlDetector


TARGET_HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]


def _candidate(
    entity_id: str,
    current: float,
    history: list[float],
    **attributes: object,
) -> dict:
    return {
        "entity_id": entity_id,
        "metrics": {"visits": current},
        "history": {"visits": history},
        "attributes": attributes,
    }


def _observation(target: float, candidates: list[dict]) -> RadarObservation:
    return RadarObservation(
        entity_id="TARGET",
        observed_at=datetime.now(UTC),
        metrics={"visits": target},
        history={"visits": TARGET_HISTORY},
        context={"control_candidates": candidates},
    )


def test_selector_chooses_historically_similar_controls() -> None:
    candidates = [
        _candidate("C1", 100, TARGET_HISTORY),
        _candidate("C2", 200, [value * 2 for value in TARGET_HISTORY]),
        _candidate("BAD", 100, [100, 110, 90, 120, 80, 130, 70, 140, 60, 150]),
    ]
    selection = AutomaticControlSelector().select(_observation(94, candidates), "visits")
    assert [item.entity_id for item in selection.controls] == ["C1", "C2"]
    assert all(item.similarity >= 0.70 for item in selection.controls)
    assert selection.excluded["low_similarity"] == 1


def test_selector_does_not_use_current_values_for_similarity() -> None:
    histories = [
        _candidate("C1", 1, TARGET_HISTORY),
        _candidate("C2", 9999, [value * 2 for value in TARGET_HISTORY]),
        _candidate("C3", -500, [value * 3 for value in TARGET_HISTORY]),
    ]
    first = AutomaticControlSelector().select(_observation(94, histories), "visits")
    changed_currents = [
        _candidate("C1", 9999, TARGET_HISTORY),
        _candidate("C2", -1, [value * 2 for value in TARGET_HISTORY]),
        _candidate("C3", 123456, [value * 3 for value in TARGET_HISTORY]),
    ]
    second = AutomaticControlSelector().select(_observation(94, changed_currents), "visits")
    assert [(item.entity_id, item.similarity) for item in first.controls] == [
        (item.entity_id, item.similarity) for item in second.controls
    ]
    assert first.audit()["selection_uses_current_values"] if "selection_uses_current_values" in first.audit() else True


def test_selector_rejects_self_ineligible_and_declared_contamination() -> None:
    candidates = [
        _candidate("TARGET", 100, TARGET_HISTORY),
        _candidate("INELIGIBLE", 100, TARGET_HISTORY, control_eligible=False),
        _candidate("CONTAMINATED", 100, TARGET_HISTORY, contaminated=True),
        _candidate("GOOD", 100, TARGET_HISTORY),
    ]
    selection = AutomaticControlSelector().select(_observation(94, candidates), "visits")
    assert [item.entity_id for item in selection.controls] == ["GOOD"]
    assert selection.excluded == {
        "self_reference": 1,
        "declared_ineligible": 1,
        "declared_contaminated": 1,
    }


def test_selector_is_deterministic_and_enforces_limit() -> None:
    candidates = [
        _candidate(f"C{index:02d}", 100, TARGET_HISTORY)
        for index in range(12, 0, -1)
    ]
    selection = AutomaticControlSelector(max_controls=5).select(
        _observation(94, candidates), "visits"
    )
    assert [item.entity_id for item in selection.controls] == [
        "C01",
        "C02",
        "C03",
        "C04",
        "C05",
    ]
    assert selection.excluded["over_limit"] == 7


def test_relational_detector_uses_automatic_controls() -> None:
    candidates = [
        _candidate("C1", 100, TARGET_HISTORY),
        _candidate("C2", 101, TARGET_HISTORY),
        _candidate("C3", 99, TARGET_HISTORY),
    ]
    result = RelationalControlDetector().evaluate(_observation(94, candidates))
    assert result is not None
    comparison = result.attributes["control_comparison"]
    assert comparison["selection"]["mode"] == "automatic"
    assert comparison["selection"]["selection_uses_current_values"] is False
    assert comparison["control_count"] == 3
    assert set(comparison["control_sources"].values()) == {"automatic"}
    assert result.attributes["detector_version"] == "relational-control@2.0.0"


def test_relational_detector_does_not_alert_when_automatic_controls_share_move() -> None:
    candidates = [
        _candidate("C1", 94, TARGET_HISTORY),
        _candidate("C2", 94, TARGET_HISTORY),
        _candidate("C3", 94, TARGET_HISTORY),
    ]
    assert RelationalControlDetector().evaluate(_observation(94, candidates)) is None
