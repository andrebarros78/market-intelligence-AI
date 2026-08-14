from __future__ import annotations

from typing import Any

from market_intelligence.intelligence.radar.channel_regime import ChannelRegimeCorrelationDetector
from market_intelligence.intelligence.radar.counterfactual import OperationalCounterfactualDetector
from market_intelligence.intelligence.radar.detectors import (
    KnownRuleDetector,
    RobustZScoreDetector,
    TemporalPatternDetector,
)
from market_intelligence.intelligence.radar.factor_attribution import ObservableFactorAttributionDetector
from market_intelligence.intelligence.radar.iad import DistributionAnomalyIndex, IADCalibrationProfile
from market_intelligence.intelligence.radar.multivariate import MultivariateRelationshipDetector
from market_intelligence.intelligence.radar.pyod_ensemble import (
    PyODBenchmarkProfile,
    PyODEnsembleDetector,
)
from market_intelligence.intelligence.radar.regime import RegimeChangeDetector
from market_intelligence.intelligence.radar.relational import RelationalControlDetector
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector
from market_intelligence.intelligence.radar.seasonality import SeasonalityDetector
from market_intelligence.intelligence.radar.service import RadarService


def build_default_radar(
    *,
    iad_profile: IADCalibrationProfile | dict[str, Any] | None = None,
    pyod_profile: PyODBenchmarkProfile | dict[str, Any] | None = None,
) -> RadarService:
    return RadarService(
        [
            KnownRuleDetector(),
            SeasonalityDetector(),
            RobustZScoreDetector(),
            TemporalPatternDetector(),
            RegimeChangeDetector(),
            MultivariateRelationshipDetector(),
            PyODEnsembleDetector(trusted_profile=pyod_profile),
            RelationalControlDetector(),
            OperationalCounterfactualDetector(),
            ObservableFactorAttributionDetector(),
            UnexplainedResidualDetector(),
            ChannelRegimeCorrelationDetector(),
        ],
        derived_detectors=[DistributionAnomalyIndex(trusted_profile=iad_profile)],
    )
