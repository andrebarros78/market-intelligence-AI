from __future__ import annotations

from market_intelligence.intelligence.radar.detectors import (
    KnownRuleDetector,
    RobustZScoreDetector,
    TemporalPatternDetector,
)
from market_intelligence.intelligence.radar.multivariate import MultivariateRelationshipDetector
from market_intelligence.intelligence.radar.regime import RegimeChangeDetector
from market_intelligence.intelligence.radar.service import RadarService


def build_default_radar() -> RadarService:
    return RadarService(
        [
            KnownRuleDetector(),
            RobustZScoreDetector(),
            TemporalPatternDetector(),
            RegimeChangeDetector(),
            MultivariateRelationshipDetector(),
        ]
    )
