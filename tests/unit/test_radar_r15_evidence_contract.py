from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from market_intelligence.core.contracts import (
    Alert,
    EntityRef,
    Evidence,
    EvidenceLevel,
    Severity,
)
from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.models import DetectorResult, RadarFinding


def test_alert_derives_fact_classification_and_observation_window() -> None:
    observed = datetime.now(UTC)
    alert = Alert(
        entity=EntityRef(marketplace="mercadolivre", entity_type="item", entity_id="MLB1"),
        observed_change="estoque zerado",
        evidence=[
            Evidence(
                level=EvidenceLevel.FACT,
                statement="available_quantity=0",
                source="snapshot",
                observed_at=observed,
            )
        ],
        severity=Severity.HIGH,
        confidence=0.98,
    )
    assert alert.evidence_classification == EvidenceLevel.FACT
    assert alert.first_observed_at == observed
    assert alert.last_observed_at == observed
    assert alert.observable_causes == []
    assert alert.hypotheses == []


def test_hypothesis_never_defaults_to_fact() -> None:
    observed = datetime.now(UTC)
    alert = Alert(
        entity=EntityRef(marketplace="mercadolivre", entity_type="item", entity_id="MLB2"),
        observed_change="queda não explicada",
        evidence=[
            Evidence(
                level=EvidenceLevel.INFERENCE,
                statement="variáveis observáveis não explicam a queda",
                source="radar:residual",
                observed_at=observed,
            )
        ],
        hypotheses=["mudança de distribuição merece investigação"],
        severity=Severity.HIGH,
        confidence=0.82,
    )
    assert alert.evidence_classification == EvidenceLevel.HYPOTHESIS


def test_invalid_observation_window_is_rejected() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        Alert(
            entity=EntityRef(marketplace="mercadolivre", entity_type="item", entity_id="MLB3"),
            observed_change="janela inválida",
            evidence=[],
            severity=Severity.LOW,
            confidence=0.5,
            first_observed_at=now,
            last_observed_at=now - timedelta(seconds=1),
        )


def test_finding_mapper_preserves_investigation_context() -> None:
    observed = datetime.now(UTC)
    finding = RadarFinding(
        entity_id="MLB4",
        score=0.91,
        anomalous=True,
        detector_results=[
            DetectorResult(
                detector="residual-detector",
                score=0.91,
                level=EvidenceLevel.INFERENCE,
                summary="queda observada não foi suficientemente explicada",
                attributes={"residual": -0.61},
            )
        ],
    )
    alert = alert_from_finding(
        finding=finding,
        marketplace="mercadolivre",
        entity_type="item",
        observed_at=observed,
        context={
            "observable_causes": ["sazonalidade parcial"],
            "unexplained_residual": -0.61,
            "hypotheses": ["mudança de distribuição merece investigação"],
            "control_comparison": {"control_delta": -0.04, "investigated_delta": -0.65},
            "detector_version": "residual-detector@1.0.0",
        },
    )
    assert alert is not None
    assert alert.evidence_classification == EvidenceLevel.HYPOTHESIS
    assert alert.observable_causes == ["sazonalidade parcial"]
    assert alert.unexplained_residual == -0.61
    assert alert.hypotheses == ["mudança de distribuição merece investigação"]
    assert alert.control_comparison == {"control_delta": -0.04, "investigated_delta": -0.65}
    assert alert.detector_version == "residual-detector@1.0.0"
