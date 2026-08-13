from __future__ import annotations

from market_intelligence.intelligence.radar.counterfactual import OperationalCounterfactualDetector
from market_intelligence.intelligence.radar.detectors import (
    KnownRuleDetector,
    RobustZScoreDetector,
    TemporalPatternDetector,
)
from market_intelligence.intelligence.radar.factor_attribution import ObservableFactorAttributionDetector
from market_intelligence.intelligence.radar.multivariate import MultivariateRelationshipDetector
from market_intelligence.intelligence.radar.regime import RegimeChangeDetector
from market_intelligence.intelligence.radar.relational import RelationalControlDetector
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector
from market_intelligence.intelligence.radar.seasonality import SeasonalityDetector
from market_intelligence.intelligence.radar.service import RadarService


def build_default_radar() -> RadarService:
    return RadarService(
        [
            KnownRuleDetector(),
            SeasonalityDetector(),
            RobustZScoreDetector(),
            TemporalPatternDetector(),
            RegimeChangeDetector(),
            MultivariateRelationshipDetector(),
            RelationalControlDetector(),
            OperationalCounterfactualDetector(),
            ObservableFactorAttributionDetector(),
            UnexplainedResidualDetector(),
        ]
    )
