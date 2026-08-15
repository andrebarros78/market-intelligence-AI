from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SECRET_KEYS = {
    "access_token", "refresh_token", "token", "secret", "client_secret",
    "password", "authorization", "api_key", "apikey",
}


class LearningState(StrEnum):
    UNDER_INVESTIGATION = "under_investigation"
    VALIDATED_FACT = "validated_fact"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class FeedbackTarget(StrEnum):
    RADAR_RULE_CANDIDATE = "radar_rule_candidate"
    SKILL_UPDATE_CANDIDATE = "skill_update_candidate"
    KNOWLEDGE_MEMORY = "knowledge_memory"


class SovereignLearningDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dedupe_key: str = Field(min_length=64, max_length=64)
    marketplace: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    state: LearningState
    confidence: float = Field(ge=0.0, le=1.0)
    observation_count: int = Field(ge=0)
    official_resource_fetched: bool
    causal_claim: bool
    evidence_summary: dict[str, Any]
    hypotheses: list[dict[str, Any]]
    feedback_targets: tuple[FeedbackTarget, ...]
    watchdogs: dict[str, bool]
    reason: str = Field(min_length=1)


class LearningPromotionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approved: bool
    target: FeedbackTarget
    regression_passed: bool
    independent_verifier_passed: bool
    watchdog_passed: bool
    reason: str


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                return True
            if _contains_secret(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    return False


def _dedupe_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SovereignLearningEngine:
    """Fail-closed policy engine for the Radar Universal Soberano learning loop.

    The engine never writes to a marketplace and never hot-modifies live Radar rules.
    It only produces guarded learning decisions and promotion candidates.
    """

    version = "sovereign-learning@1.0.0"

    def evaluate(
        self,
        *,
        marketplace: str,
        entity_type: str,
        entity_id: str,
        finding: dict[str, Any],
        investigation: dict[str, Any] | None,
        official_resource_fetched: bool,
        marketplace_read_only: bool,
        marketplace_writes: int = 0,
    ) -> SovereignLearningDecision:
        if not marketplace_read_only or marketplace_writes != 0:
            raise RuntimeError("sovereign_learning_read_only_violation")
        if _contains_secret(finding) or _contains_secret(investigation or {}):
            raise RuntimeError("sovereign_learning_secret_contamination")

        finding_hash = str((investigation or {}).get("finding_hash") or "")
        if not finding_hash:
            finding_hash = _dedupe_key(finding)
        observation_count = int((investigation or {}).get("observation_count") or 0)
        confidence = float((investigation or {}).get("confidence_after") or finding.get("score") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        status = str((investigation or {}).get("status_after") or "")
        causal_claim = bool((investigation or {}).get("causal_claim", False))
        evidence_summary = dict((investigation or {}).get("evidence_summary") or {})
        hypotheses = list((investigation or {}).get("hypotheses") or [])

        repeated = observation_count >= 2
        confirmed = status == "confirmed"
        confidence_ok = confidence >= 0.80
        watchdogs = {
            "read_only": marketplace_read_only and marketplace_writes == 0,
            "no_secret_contamination": True,
            "official_resource_confirmed": bool(official_resource_fetched),
            "repeated_observation": repeated,
            "investigation_confirmed": confirmed,
            "confidence_gate": confidence_ok,
            "no_causal_overclaim": not causal_claim,
        }

        if causal_claim:
            state = LearningState.QUARANTINED
            targets = (FeedbackTarget.KNOWLEDGE_MEMORY,)
            reason = "causal_claim_requires_independent_causal_validation"
        elif status in {"rejected", "inconclusive"}:
            state = LearningState.REJECTED
            targets = (FeedbackTarget.KNOWLEDGE_MEMORY,)
            reason = "investigation_did_not_confirm_signal"
        elif all((official_resource_fetched, repeated, confirmed, confidence_ok)):
            state = LearningState.VALIDATED_FACT
            targets = (
                FeedbackTarget.KNOWLEDGE_MEMORY,
                FeedbackTarget.RADAR_RULE_CANDIDATE,
                FeedbackTarget.SKILL_UPDATE_CANDIDATE,
            )
            reason = "official_read_plus_repetition_plus_confirmed_investigation"
        else:
            state = LearningState.UNDER_INVESTIGATION
            targets = (FeedbackTarget.KNOWLEDGE_MEMORY,)
            reason = "insufficient_evidence_for_promotion_candidate"

        key_payload = {
            "marketplace": marketplace.strip().lower(),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "finding_hash": finding_hash,
            "state": state.value,
        }
        return SovereignLearningDecision(
            dedupe_key=_dedupe_key(key_payload),
            marketplace=marketplace.strip().lower(),
            entity_type=entity_type,
            entity_id=entity_id,
            state=state,
            confidence=confidence,
            observation_count=observation_count,
            official_resource_fetched=bool(official_resource_fetched),
            causal_claim=causal_claim,
            evidence_summary=evidence_summary,
            hypotheses=hypotheses,
            feedback_targets=targets,
            watchdogs=watchdogs,
            reason=reason,
        )

    @staticmethod
    def decide_promotion(
        *,
        target: FeedbackTarget,
        regression_passed: bool,
        independent_verifier_passed: bool,
        watchdog_passed: bool,
    ) -> LearningPromotionDecision:
        approved = bool(regression_passed and independent_verifier_passed and watchdog_passed)
        return LearningPromotionDecision(
            approved=approved,
            target=target,
            regression_passed=regression_passed,
            independent_verifier_passed=independent_verifier_passed,
            watchdog_passed=watchdog_passed,
            reason=(
                "all_promotion_gates_passed"
                if approved
                else "promotion_blocked_until_all_gates_pass"
            ),
        )
