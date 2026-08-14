from datetime import UTC, datetime, timedelta

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.investigation import (
    HypothesisStatus,
    InvestigationState,
    InvestigationStatus,
    ProgressiveInvestigationEngine,
)
from market_intelligence.intelligence.radar.models import (
    DetectorResult,
    RadarFinding,
    RadarObservation,
)


def _observation(at: datetime, *, hypotheses: list[str] | None = None) -> RadarObservation:
    return RadarObservation(
        entity_id="R118-ENTITY",
        observed_at=at,
        metrics={"visits": 40.0, "conversion": 0.04},
        history={"visits": [100.0] * 12, "conversion": [0.10] * 12},
        context={"hypotheses": hypotheses or []},
    )


def _finding(*, anomalous: bool, score: float = 0.85) -> RadarFinding:
    results = []
    if anomalous:
        results = [
            DetectorResult(
                detector="distribution_anomaly_index_v1",
                score=score,
                level=EvidenceLevel.HYPOTHESIS,
                summary="Distribution anomaly requires investigation",
                attributes={
                    "detector_version": "distribution-anomaly-index@1.0.0",
                    "causal_claim": False,
                },
            ),
            DetectorResult(
                detector="channel_regime_correlation_v1",
                score=0.72,
                level=EvidenceLevel.INFERENCE,
                summary="Joint ecosystem regime change detected",
                attributes={
                    "detector_version": "channel-regime-correlation@1.0.0",
                    "control_comparison": {"controls_stable": True},
                    "causal_claim": False,
                },
            ),
        ]
    return RadarFinding(
        entity_id="R118-ENTITY",
        score=score if anomalous else 0.20,
        anomalous=anomalous,
        detector_results=results,
    )


def _state(step) -> InvestigationState:
    return InvestigationState(
        status=step.status_after,
        confidence=step.confidence_after,
        observation_count=step.observation_count,
        anomalous_observation_count=step.anomalous_observation_count,
        anomaly_streak=step.anomaly_streak,
        normal_streak=step.normal_streak,
        ever_confirmed=step.ever_confirmed,
        hypotheses=step.hypotheses,
    )


def test_normal_observation_does_not_open_investigation() -> None:
    engine = ProgressiveInvestigationEngine()
    step = engine.advance(
        finding=_finding(anomalous=False),
        observation=_observation(datetime.now(UTC)),
    )
    assert step is None


def test_repeated_anomaly_confirms_episode_without_claiming_cause() -> None:
    engine = ProgressiveInvestigationEngine()
    started = datetime.now(UTC)
    first = engine.advance(
        finding=_finding(anomalous=True),
        observation=_observation(started, hypotheses=["Ranking/distribution changed"]),
    )
    assert first is not None
    assert first.status_after == InvestigationStatus.OPEN
    assert first.causal_claim is False
    assert first.evidence_summary["counts_by_evidence_level"] == {
        "fact": 0,
        "inference": 1,
        "hypothesis": 1,
    }

    second = engine.advance(
        finding=_finding(anomalous=True, score=0.90),
        observation=_observation(started + timedelta(minutes=30), hypotheses=["Ranking/distribution changed"]),
        previous=_state(first),
    )
    assert second is not None
    assert second.status_after == InvestigationStatus.CONFIRMED
    assert second.ever_confirmed is True
    assert second.observation_count == 2
    assert second.confidence_delta > 0
    assert second.causal_claim is False
    assert any(item.status == HypothesisStatus.SUPPORTED for item in second.hypotheses)
    assert all(item.status != "confirmed" for item in second.hypotheses)


def test_confirmed_episode_resolves_after_two_normal_observations() -> None:
    engine = ProgressiveInvestigationEngine()
    started = datetime.now(UTC)
    first = engine.advance(finding=_finding(anomalous=True), observation=_observation(started))
    assert first is not None
    second = engine.advance(
        finding=_finding(anomalous=True),
        observation=_observation(started + timedelta(minutes=10)),
        previous=_state(first),
    )
    assert second is not None and second.status_after == InvestigationStatus.CONFIRMED
    third = engine.advance(
        finding=_finding(anomalous=False),
        observation=_observation(started + timedelta(minutes=20)),
        previous=_state(second),
    )
    assert third is not None and third.status_after == InvestigationStatus.MONITORING
    fourth = engine.advance(
        finding=_finding(anomalous=False),
        observation=_observation(started + timedelta(minutes=30)),
        previous=_state(third),
    )
    assert fourth is not None
    assert fourth.status_after == InvestigationStatus.RESOLVED
    assert fourth.terminal is True


def test_single_anomaly_followed_by_normal_streak_is_rejected_as_unsustained() -> None:
    engine = ProgressiveInvestigationEngine()
    started = datetime.now(UTC)
    first = engine.advance(finding=_finding(anomalous=True), observation=_observation(started))
    assert first is not None
    second = engine.advance(
        finding=_finding(anomalous=False),
        observation=_observation(started + timedelta(minutes=10)),
        previous=_state(first),
    )
    assert second is not None and second.status_after == InvestigationStatus.MONITORING
    third = engine.advance(
        finding=_finding(anomalous=False),
        observation=_observation(started + timedelta(minutes=20)),
        previous=_state(second),
    )
    assert third is not None
    assert third.status_after == InvestigationStatus.REJECTED
    assert third.terminal is True
    assert all(item.status == HypothesisStatus.REJECTED for item in third.hypotheses)


def test_alternating_signal_can_end_inconclusive_without_false_confirmation() -> None:
    engine = ProgressiveInvestigationEngine(max_monitoring_observations=4)
    started = datetime.now(UTC)
    step = engine.advance(finding=_finding(anomalous=True), observation=_observation(started))
    assert step is not None
    for index, anomalous in enumerate([False, True, False], start=1):
        step = engine.advance(
            finding=_finding(anomalous=anomalous),
            observation=_observation(started + timedelta(minutes=10 * index)),
            previous=_state(step),
        )
        assert step is not None
    assert step.status_after == InvestigationStatus.INCONCLUSIVE
    assert step.ever_confirmed is False
    assert step.terminal is True
