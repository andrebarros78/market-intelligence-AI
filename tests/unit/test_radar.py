from datetime import UTC, datetime

from market_intelligence.intelligence.radar.detectors import KnownRuleDetector, RobustZScoreDetector
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.service import RadarService


def test_radar_detects_unwritten_statistical_deviation() -> None:
    service = RadarService([KnownRuleDetector(), RobustZScoreDetector()])
    observation = RadarObservation(
        entity_id="MLB1",
        observed_at=datetime.now(UTC),
        metrics={"visits": 20.0},
        history={"visits": [98.0, 101.0, 99.0, 100.0, 102.0, 97.0, 101.0]},
    )
    finding = service.evaluate(observation)
    assert finding.anomalous is True
    assert any(result.detector == "robust_zscore" for result in finding.detector_results)


def test_known_rule_is_fact() -> None:
    service = RadarService([KnownRuleDetector()])
    observation = RadarObservation(
        entity_id="MLB2",
        observed_at=datetime.now(UTC),
        metrics={},
        context={"known_rule_violation": True, "known_rule_summary": "listing paused"},
    )
    finding = service.evaluate(observation)
    assert finding.anomalous is True
    assert finding.detector_results[0].level.value == "fact"
