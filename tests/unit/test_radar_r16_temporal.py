from __future__ import annotations

from datetime import UTC, datetime

from market_intelligence.intelligence.radar.detectors import TemporalPatternDetector
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.regime import RegimeChangeDetector


def _evaluate(history: list[float], current: float):
    detector = TemporalPatternDetector()
    return detector.evaluate(
        RadarObservation(
            entity_id="MLB-R16",
            observed_at=datetime.now(UTC),
            metrics={"visits": current},
            history={"visits": history},
        )
    )


def _evaluate_regime(history: list[float], current: float):
    return RegimeChangeDetector().evaluate(
        RadarObservation(
            entity_id="MLB-R17",
            observed_at=datetime.now(UTC),
            metrics={"visits": current},
            history={"visits": history},
        )
    )


def test_temporal_detector_requires_sufficient_history() -> None:
    assert _evaluate([100, 101, 99, 100, 101], 40) is None


def test_temporal_detector_ignores_stable_noise() -> None:
    result = _evaluate([100, 101, 99, 100, 102, 98, 101, 99, 100, 101], 99)
    assert result is None


def test_temporal_detector_classifies_isolated_spike() -> None:
    result = _evaluate([100, 101, 99, 100, 100, 101, 99, 100], 55)
    assert result is not None
    assert result.level.value == "fact"
    assert result.attributes["pattern"] == "isolated_spike"
    assert result.attributes["direction"] == "down"
    assert result.attributes["detector_version"] == "temporal-pattern@1.0.0"


def test_temporal_detector_classifies_progressive_trend_before_level_shift() -> None:
    history = [100, 101, 99, 100, 100, 101, 99, 100, 95, 90, 85, 80, 75]
    result = _evaluate(history, 70)
    assert result is not None
    assert result.attributes["pattern"] == "progressive_trend"
    assert result.attributes["direction"] == "down"
    assert result.attributes["monotonic_fraction"] >= 0.8


def test_temporal_detector_classifies_persistent_level_shift() -> None:
    history = [100, 101, 99, 100, 100, 101, 99, 100, 60, 61, 59]
    result = _evaluate(history, 60)
    assert result is not None
    assert result.attributes["pattern"] == "persistent_level_shift"
    assert result.attributes["persistence"] >= 0.75
    assert result.attributes["direction"] == "down"


def test_temporal_detector_classifies_abrupt_break_with_two_shifted_points() -> None:
    history = [100, 99, 101, 100, 100, 99, 100, 101, 60]
    result = _evaluate(history, 59)
    assert result is not None
    assert result.attributes["pattern"] == "abrupt_break"
    assert result.attributes["direction"] == "down"
    assert result.attributes["jump_signal"] >= 3.0


def test_temporal_detector_selects_strongest_metric() -> None:
    detector = TemporalPatternDetector()
    result = detector.evaluate(
        RadarObservation(
            entity_id="MLB-R16-MULTI",
            observed_at=datetime.now(UTC),
            metrics={"visits": 55, "sales": 9},
            history={
                "visits": [100, 101, 99, 100, 100, 101, 99, 100],
                "sales": [10, 10, 9, 10, 10, 11, 10, 10],
            },
        )
    )
    assert result is not None
    assert result.attributes["metric"] == "visits"


def test_regime_detector_requires_two_windows_and_ignores_stable_noise() -> None:
    assert _evaluate_regime([100, 101, 99, 100, 101, 99, 100, 101, 99, 100], 70) is None
    assert _evaluate_regime([100, 101, 99, 100, 101, 99, 100, 99, 101, 100, 101], 99) is None


def test_regime_detector_ignores_single_outlier() -> None:
    assert _evaluate_regime([100, 101, 99, 100, 101, 99, 100, 100, 50, 100, 101], 99) is None


def test_regime_detector_classifies_persistent_level_shift() -> None:
    result = _evaluate_regime([100, 101, 99, 100, 101, 99, 70, 71, 69, 70, 71], 69)
    assert result is not None
    assert result.level.value == "fact"
    assert result.attributes["pattern"] == "level_regime_shift"
    assert result.attributes["persistence"] >= 0.8
    assert result.attributes["cause_status"] == "unknown_not_inferred"
    assert result.attributes["detector_version"] == "regime-change@1.0.0"


def test_regime_detector_classifies_volatility_shift() -> None:
    result = _evaluate_regime([100, 101, 99, 100, 101, 99, 85, 115, 86, 114, 87], 113)
    assert result is not None
    assert result.attributes["pattern"] == "volatility_regime_shift"
    assert result.attributes["volatility_ratio"] >= 2.5


def test_regime_detector_classifies_trend_shift_before_level_shift() -> None:
    result = _evaluate_regime([100, 101, 99, 100, 101, 99, 100, 95, 90, 85, 80], 75)
    assert result is not None
    assert result.attributes["pattern"] == "trend_regime_shift"
    assert result.attributes["persistence"] >= 0.8
    assert result.attributes["cause_status"] == "unknown_not_inferred"
