from __future__ import annotations

from datetime import UTC, datetime

from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.relational import RelationalControlDetector
from market_intelligence.workflows.activities import RadarActivities

TARGET_HISTORY = [100, 101, 99, 100, 102, 98, 101, 99, 100, 100]
CONTROL_HISTORY = [100, 100, 101, 99, 100, 101, 100, 99, 100, 100]


def _control(entity_id: str, current: float, *, similarity: float = 0.90) -> dict:
    return {"entity_id": entity_id, "similarity": similarity, "metrics": {"visits": current}, "history": {"visits": CONTROL_HISTORY}, "attributes": {"category": "same"}}


def _observation(target: float, controls: list[dict]) -> RadarObservation:
    return RadarObservation(entity_id="TARGET", observed_at=datetime.now(UTC), metrics={"visits": target}, history={"visits": TARGET_HISTORY}, context={"controls": controls})


def test_relational_detects_target_specific_divergence() -> None:
    result = RelationalControlDetector().evaluate(_observation(94, [_control("C1", 100), _control("C2", 101), _control("C3", 99)]))
    assert result is not None
    assert result.level.value == "fact"
    assert result.attributes["pattern"] == "control_group_divergence"
    assert result.attributes["cause_status"] == "unknown_not_inferred"
    assert result.attributes["detector_version"] == "relational-control@2.0.0"
    comparison = result.attributes["control_comparison"]
    assert comparison["metric"] == "visits"
    assert comparison["control_count"] == 3
    assert comparison["control_consistency"] >= 2 / 3
    assert comparison["divergence"] >= 3.0


def test_relational_does_not_alert_when_controls_move_with_target() -> None:
    assert RelationalControlDetector().evaluate(_observation(94, [_control("C1", 94), _control("C2", 94), _control("C3", 94)])) is None


def test_relational_ignores_low_similarity_controls() -> None:
    controls = [_control("C1", 100, similarity=0.50), _control("C2", 100, similarity=0.60), _control("C3", 100, similarity=0.69), _control("C4", 100, similarity=0.90)]
    assert RelationalControlDetector().evaluate(_observation(94, controls)) is None


def test_relational_rejects_inconsistent_control_group() -> None:
    assert RelationalControlDetector().evaluate(_observation(94, [_control("C1", 70), _control("C2", 100), _control("C3", 130)])) is None


def test_relational_ignores_malformed_controls_and_self_reference() -> None:
    controls = [_control("TARGET", 100), {"entity_id": "BAD", "similarity": 2.0, "metrics": {"visits": 100}}, _control("C1", 100), _control("C2", 100)]
    assert RelationalControlDetector().evaluate(_observation(94, controls)) is None


def test_default_radar_and_alert_contract_keep_control_comparison() -> None:
    observation = _observation(94, [_control("C1", 100), _control("C2", 101), _control("C3", 99)])
    finding = build_default_radar().evaluate(observation)
    relational = [r for r in finding.detector_results if r.detector == "relational_control_v1"]
    assert relational
    alert = alert_from_finding(finding=finding, marketplace="mercadolivre", entity_type="item", observed_at=observation.observed_at, context={})
    assert alert is not None
    assert alert.control_comparison is not None
    assert alert.control_comparison["target_entity_id"] == "TARGET"
    assert alert.control_comparison["control_count"] == 3


async def test_temporal_radar_activity_uses_same_relational_detector() -> None:
    observation = _observation(94, [_control("C1", 100), _control("C2", 101), _control("C3", 99)])
    result = await RadarActivities(build_default_radar()).evaluate(observation.model_dump(mode="json"))
    detectors = {item["detector"]: item for item in result["detector_results"]}
    assert detectors["relational_control_v1"]["attributes"]["detector_version"] == "relational-control@2.0.0"
