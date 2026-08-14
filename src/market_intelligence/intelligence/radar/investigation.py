from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation


class InvestigationStatus(StrEnum):
    OPEN = "open"
    MONITORING = "monitoring"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    RESOLVED = "resolved"


class HypothesisStatus(StrEnum):
    ACTIVE = "active"
    SUPPORTED = "supported"
    REJECTED = "rejected"


class InvestigationHypothesis(BaseModel):
    key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    status: HypothesisStatus = HypothesisStatus.ACTIVE
    support_count: int = Field(default=1, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_sources: list[str] = Field(default_factory=list)
    last_supported_at: datetime | None = None


class InvestigationState(BaseModel):
    status: InvestigationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    observation_count: int = Field(default=0, ge=0)
    anomalous_observation_count: int = Field(default=0, ge=0)
    anomaly_streak: int = Field(default=0, ge=0)
    normal_streak: int = Field(default=0, ge=0)
    ever_confirmed: bool = False
    hypotheses: list[InvestigationHypothesis] = Field(default_factory=list)


class InvestigationStep(BaseModel):
    engine_version: str
    observed_at: datetime
    finding_hash: str
    status_before: InvestigationStatus | None
    status_after: InvestigationStatus
    anomalous: bool
    finding_score: float = Field(ge=0.0, le=1.0)
    confidence_before: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_after: float = Field(ge=0.0, le=1.0)
    confidence_delta: float
    observation_count: int = Field(ge=1)
    anomalous_observation_count: int = Field(ge=0)
    anomaly_streak: int = Field(ge=0)
    normal_streak: int = Field(ge=0)
    ever_confirmed: bool
    evidence_summary: dict[str, Any]
    hypotheses: list[InvestigationHypothesis]
    recommended_action: str
    terminal: bool
    causal_claim: bool = False


class ProgressiveInvestigationEngine:
    """Consolidate Radar evidence across observations without inventing causality."""

    version = "progressive-investigation@1.0.0"

    def __init__(
        self,
        *,
        confirmation_streak: int = 2,
        rejection_normal_streak: int = 2,
        max_monitoring_observations: int = 8,
    ) -> None:
        self.confirmation_streak = max(2, int(confirmation_streak))
        self.rejection_normal_streak = max(2, int(rejection_normal_streak))
        self.max_monitoring_observations = max(4, int(max_monitoring_observations))

    @staticmethod
    def finding_hash(finding: RadarFinding) -> str:
        payload = finding.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _evidence_summary(finding: RadarFinding) -> dict[str, Any]:
        counts = {level.value: 0 for level in EvidenceLevel}
        residual: float | None = None
        control_comparison: dict[str, Any] | None = None
        observable_causes: list[str] = []
        detector_versions: list[str] = []
        for result in finding.detector_results:
            counts[result.level.value] += 1
            if residual is None and isinstance(result.attributes.get("unexplained_residual"), (int, float)):
                residual = float(result.attributes["unexplained_residual"])
            if control_comparison is None and isinstance(result.attributes.get("control_comparison"), dict):
                control_comparison = dict(result.attributes["control_comparison"])
            values = result.attributes.get("observable_causes")
            if isinstance(values, list):
                observable_causes.extend(str(value) for value in values if str(value).strip())
            version = result.attributes.get("detector_version")
            if version:
                detector_versions.append(str(version))
        return {
            "counts_by_evidence_level": counts,
            "detectors": [result.detector for result in finding.detector_results],
            "detector_versions": sorted(set(detector_versions)),
            "summaries": [result.summary for result in finding.detector_results],
            "observable_causes": sorted(set(observable_causes)),
            "unexplained_residual": residual,
            "control_comparison": control_comparison,
            "causal_claim": False,
        }

    @staticmethod
    def _candidate_hypotheses(
        finding: RadarFinding,
        observation: RadarObservation,
    ) -> dict[str, tuple[str, float, list[str]]]:
        candidates: dict[str, tuple[str, float, list[str]]] = {}

        explicit = observation.context.get("hypotheses")
        if isinstance(explicit, list):
            for index, statement in enumerate(explicit):
                text = str(statement).strip()
                if text:
                    key = f"context:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"
                    candidates[key] = (text, finding.score, ["context:hypothesis"])

        mappings = {
            "distribution_anomaly_index_v1": (
                "distribution_exposure_change",
                "Mudança de distribuição ou exposição merece investigação prioritária; causa interna específica não confirmada.",
            ),
            "channel_regime_correlation_v1": (
                "joint_ecosystem_regime_change",
                "Mudança conjunta de regime no ecossistema/canal pode estar associada ao desvio de negócio; causa interna específica não confirmada.",
            ),
            "unexplained_residual_v1": (
                "unobserved_factor_contribution",
                "Fator ainda não observado pode contribuir para o resíduo não explicado.",
            ),
            "pyod_ensemble_v1": (
                "multivariate_outlier_state",
                "Estado multivariado anômalo merece investigação; detecção de outlier não identifica causa.",
            ),
        }
        for result in finding.detector_results:
            mapped = mappings.get(result.detector)
            if mapped is None:
                continue
            key, statement = mapped
            prior = candidates.get(key)
            score = max(result.score, prior[1] if prior else 0.0)
            sources = sorted(set((prior[2] if prior else []) + [f"radar:{result.detector}"]))
            candidates[key] = (statement, score, sources)
        return candidates

    def _merge_hypotheses(
        self,
        previous: InvestigationState | None,
        finding: RadarFinding,
        observation: RadarObservation,
        status_after: InvestigationStatus,
    ) -> list[InvestigationHypothesis]:
        current = self._candidate_hypotheses(finding, observation)
        by_key = {
            item.key: item.model_copy(deep=True)
            for item in (previous.hypotheses if previous is not None else [])
        }
        for key, (statement, score, sources) in current.items():
            item = by_key.get(key)
            if item is None:
                by_key[key] = InvestigationHypothesis(
                    key=key,
                    statement=statement,
                    status=HypothesisStatus.ACTIVE,
                    support_count=1,
                    confidence=score,
                    evidence_sources=sources,
                    last_supported_at=observation.observed_at,
                )
                continue
            item.support_count += 1
            item.confidence = max(item.confidence, score)
            item.evidence_sources = sorted(set(item.evidence_sources + sources))
            item.last_supported_at = observation.observed_at
            if item.support_count >= 2:
                item.status = HypothesisStatus.SUPPORTED

        if status_after == InvestigationStatus.REJECTED:
            for item in by_key.values():
                item.status = HypothesisStatus.REJECTED
        return sorted(by_key.values(), key=lambda item: item.key)

    def _next_status(
        self,
        previous: InvestigationState | None,
        *,
        anomalous: bool,
        observation_count: int,
        anomaly_streak: int,
        normal_streak: int,
    ) -> InvestigationStatus:
        if previous is None:
            return InvestigationStatus.OPEN
        if anomalous:
            if previous.ever_confirmed or anomaly_streak >= self.confirmation_streak:
                return InvestigationStatus.CONFIRMED
            return InvestigationStatus.MONITORING
        if normal_streak >= self.rejection_normal_streak:
            return (
                InvestigationStatus.RESOLVED
                if previous.ever_confirmed
                else InvestigationStatus.REJECTED
            )
        if observation_count >= self.max_monitoring_observations and not previous.ever_confirmed:
            return InvestigationStatus.INCONCLUSIVE
        return InvestigationStatus.MONITORING

    @staticmethod
    def _recommendation(
        status: InvestigationStatus,
        observation: RadarObservation,
    ) -> str:
        explicit = observation.context.get("recommended_action")
        if explicit:
            return str(explicit)
        if status == InvestigationStatus.OPEN:
            return "Reunir nova observação comparável e revisar causas observáveis antes de qualquer conclusão causal."
        if status == InvestigationStatus.MONITORING:
            return "Continuar observando o episódio e confrontar histórico, controles, resíduo e sinais do canal."
        if status == InvestigationStatus.CONFIRMED:
            return "Priorizar revisão humana da anomalia persistente e das hipóteses suportadas; causa interna específica continua não confirmada."
        if status == InvestigationStatus.REJECTED:
            return "Encerrar o episódio como anomalia não sustentada e registrar como candidato a falso positivo."
        if status == InvestigationStatus.RESOLVED:
            return "Registrar recuperação após anomalia confirmada e preservar a linha do tempo para análise posterior."
        return "Encerrar como inconclusivo e preservar evidências para nova investigação se o sinal reaparecer."

    def advance(
        self,
        *,
        finding: RadarFinding,
        observation: RadarObservation,
        previous: InvestigationState | None = None,
    ) -> InvestigationStep | None:
        if previous is None and not finding.anomalous:
            return None

        observation_count = (previous.observation_count if previous else 0) + 1
        anomalous_count = (previous.anomalous_observation_count if previous else 0) + int(
            finding.anomalous
        )
        anomaly_streak = (previous.anomaly_streak + 1) if previous and finding.anomalous else int(finding.anomalous)
        normal_streak = (previous.normal_streak + 1) if previous and not finding.anomalous else int(not finding.anomalous)
        status_after = self._next_status(
            previous,
            anomalous=finding.anomalous,
            observation_count=observation_count,
            anomaly_streak=anomaly_streak,
            normal_streak=normal_streak,
        )
        ever_confirmed = bool(
            (previous and previous.ever_confirmed) or status_after == InvestigationStatus.CONFIRMED
        )
        confidence_before = previous.confidence if previous is not None else None
        confidence_after = finding.score
        hypotheses = self._merge_hypotheses(previous, finding, observation, status_after)
        terminal = status_after in {
            InvestigationStatus.REJECTED,
            InvestigationStatus.INCONCLUSIVE,
            InvestigationStatus.RESOLVED,
        }
        return InvestigationStep(
            engine_version=self.version,
            observed_at=observation.observed_at,
            finding_hash=self.finding_hash(finding),
            status_before=previous.status if previous else None,
            status_after=status_after,
            anomalous=finding.anomalous,
            finding_score=finding.score,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            confidence_delta=confidence_after - (confidence_before or 0.0),
            observation_count=observation_count,
            anomalous_observation_count=anomalous_count,
            anomaly_streak=anomaly_streak,
            normal_streak=normal_streak,
            ever_confirmed=ever_confirmed,
            evidence_summary=self._evidence_summary(finding),
            hypotheses=hypotheses,
            recommended_action=self._recommendation(status_after, observation),
            terminal=terminal,
            causal_claim=False,
        )
