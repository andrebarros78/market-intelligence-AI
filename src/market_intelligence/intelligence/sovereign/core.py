from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from market_intelligence.intelligence.radar.sovereign_learning import (
    LearningState,
    SovereignLearningEngine,
)
from market_intelligence.intelligence.sovereign.models import (
    CoreCycleReport,
    KnowledgeState,
    SignalEnvelope,
    ValidationVerdict,
)
from market_intelligence.intelligence.sovereign.organs import (
    SovereignCognitiveAuditor,
    SovereignCorrelator,
    SovereignCounterIntelligence,
    SovereignDecisionEngine,
    SovereignExperimenter,
    SovereignInstigator,
    SovereignIntelligenceEngine,
    SovereignPredictor,
    SovereignProbe,
    SovereignValidator,
)

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "client_secret",
    "password",
    "authorization",
    "api_key",
    "apikey",
}


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in _SECRET_KEYS:
                return True
            if _contains_secret(item):
                return True
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_contains_secret(item) for item in value)
    return False


class SovereignIntelligenceCore:
    """Cognitive core above the Radar.

    The core discovers, correlates, investigates, challenges, validates, learns and
    predicts. It never writes directly to a marketplace. External actions are emitted
    only as guarded ActionIntent objects for a separate Action Gateway.
    """

    version = "sovereign-intelligence-core@1.0.0"

    def __init__(self) -> None:
        self.probe = SovereignProbe()
        self.correlator = SovereignCorrelator()
        self.instigator = SovereignInstigator()
        self.experimenter = SovereignExperimenter()
        self.intelligence = SovereignIntelligenceEngine()
        self.counterintelligence = SovereignCounterIntelligence()
        self.validator = SovereignValidator()
        self.learning = SovereignLearningEngine()
        self.predictor = SovereignPredictor()
        self.decision = SovereignDecisionEngine()
        self.auditor = SovereignCognitiveAuditor()

    def process(
        self,
        signal: SignalEnvelope,
        *,
        history: Iterable[SignalEnvelope] = (),
        investigation: dict[str, Any] | None = None,
        experiment_evidence: dict[str, Any] | None = None,
        marketplace_read_only: bool = True,
        marketplace_writes: int = 0,
    ) -> CoreCycleReport:
        if not marketplace_read_only or marketplace_writes != 0:
            raise RuntimeError("sovereign_core_read_only_violation")
        if _contains_secret(signal.payload) or _contains_secret(signal.provenance):
            raise RuntimeError("sovereign_core_secret_contamination")
        if _contains_secret(investigation or {}) or _contains_secret(experiment_evidence or {}):
            raise RuntimeError("sovereign_core_secret_contamination")

        history = tuple(history)
        probe = self.probe.plan(signal, history)
        correlation = self.correlator.correlate(signal, history)
        hypotheses = self.instigator.instigate(signal, probe, correlation)
        experiment = self.experimenter.design(signal, hypotheses)
        intelligence = self.intelligence.assess(signal, correlation, hypotheses)
        counterintelligence = self.counterintelligence.assess(signal)
        validation = self.validator.validate(
            signal,
            correlation,
            investigation,
            experiment_evidence=experiment_evidence,
        )

        learning_input = dict(investigation or {})
        collector_generated = bool(signal.provenance.get("collector_generated_pattern"))
        if collector_generated:
            learning_input["status_after"] = "rejected"
            learning_input["causal_claim"] = False
            learning_input.setdefault("evidence_summary", {})[
                "collector_generated_pattern"
            ] = True
        if "observation_count" not in learning_input:
            learning_input["observation_count"] = len(correlation.related_signal_ids) + 1
        if "confidence_after" not in learning_input:
            learning_input["confidence_after"] = validation.confidence
        if "status_after" not in learning_input:
            learning_input["status_after"] = (
                "confirmed" if validation.state is KnowledgeState.VALIDATED else "open"
            )
        if "evidence_summary" not in learning_input:
            learning_input["evidence_summary"] = {
                "signal_id": signal.signal_id,
                "source": signal.source,
                "provenance_complete": validation.provenance_complete,
                "correlation_strength": correlation.strength,
            }
        if "hypotheses" not in learning_input:
            learning_input["hypotheses"] = [item.model_dump(mode="json") for item in hypotheses]
        learning_input.setdefault("causal_claim", False)

        learning_decision = self.learning.evaluate(
            marketplace=signal.marketplace,
            entity_type=signal.entity_type,
            entity_id=signal.entity_id,
            finding={
                "signal_id": signal.signal_id,
                "kind": signal.kind,
                "score": validation.confidence,
                "source": signal.source,
            },
            investigation=learning_input,
            official_resource_fetched=signal.official_resource_fetched,
            marketplace_read_only=True,
            marketplace_writes=0,
        )

        validation = self._reconcile_validation(validation, learning_decision.state)
        if validation.state is not KnowledgeState.VALIDATED and intelligence.confidence > 0.95:
            intelligence = intelligence.model_copy(update={"confidence": 0.95})
        prediction = self.predictor.predict(signal, correlation, validation, history=history)
        action_intent = self.decision.decide(signal, intelligence, validation, prediction)
        audit = self.auditor.audit(validation, intelligence, prediction, action_intent)

        if not audit.passed and audit.unsafe_authority_detected:
            raise RuntimeError("sovereign_core_cognitive_safety_violation")
        if action_intent.direct_marketplace_write:
            raise RuntimeError("sovereign_core_direct_marketplace_write_forbidden")

        return CoreCycleReport(
            core_version=self.version,
            signal=signal,
            probe=probe,
            correlation=correlation,
            hypotheses=hypotheses,
            experiment=experiment,
            intelligence=intelligence,
            counterintelligence=counterintelligence,
            validation=validation,
            learning=learning_decision.model_dump(mode="json"),
            prediction=prediction,
            action_intent=action_intent,
            audit=audit,
            marketplace_writes=0,
        )

    @staticmethod
    def _reconcile_validation(
        validation: ValidationVerdict,
        learning_state: LearningState,
    ) -> ValidationVerdict:
        if learning_state is LearningState.QUARANTINED:
            target = KnowledgeState.QUARANTINED
            reason = "mclp_quarantined:" + validation.reason
        elif learning_state is LearningState.REJECTED:
            target = KnowledgeState.REJECTED
            reason = "mclp_rejected:" + validation.reason
        elif learning_state is LearningState.VALIDATED_FACT:
            target = KnowledgeState.VALIDATED
            reason = "mclp_validated:" + validation.reason
        else:
            target = validation.state
            if target is KnowledgeState.VALIDATED:
                target = KnowledgeState.CORRELATED
            reason = "mclp_under_investigation:" + validation.reason

        return validation.model_copy(
            update={
                "state": target,
                "evidence_sufficient": target is KnowledgeState.VALIDATED,
                "reason": reason,
            }
        )
