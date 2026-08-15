from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from market_intelligence.skills.evidence_feed import ValidatedMarketplaceEvidence
from market_intelligence.skills.registry import SKILL_REGISTRY, SkillRegistry


@dataclass(frozen=True, slots=True)
class SkillInsight:
    skill_id: str
    function: str
    marketplace: str
    entity_type: str
    entity_id: str
    summary: str
    proof_id: str
    generated_at: datetime


def _require_validated_fact(evidence: ValidatedMarketplaceEvidence) -> None:
    payload = evidence.evidence
    if evidence.source != "official_api_get_plus_webhook":
        raise ValueError("skill_evidence_source_not_validated")
    if payload.get("classification") != "FATO":
        raise ValueError("skill_evidence_not_fact")
    if payload.get("webhook_validated") is not True:
        raise ValueError("skill_evidence_webhook_not_validated")
    if payload.get("official_get_validated") is not True:
        raise ValueError("skill_evidence_official_get_not_validated")
    if not str(payload.get("proof_id") or "").strip():
        raise ValueError("skill_evidence_proof_id_missing")


def execute_validated_evidence(
    evidence: ValidatedMarketplaceEvidence,
    *,
    registry: SkillRegistry = SKILL_REGISTRY,
) -> tuple[SkillInsight, ...]:
    """Route a validated marketplace fact to approved analytical skills only.

    This executor has no marketplace HTTP client and therefore cannot perform
    external writes. Raw events, hypotheses and unvalidated evidence are rejected.
    """

    _require_validated_fact(evidence)
    functions = (
        "evidence",
        "marketplace_analysis",
        "radar_anomalies",
        "investigation",
        "alerts_explanation",
    )
    proof_id = str(evidence.evidence["proof_id"])
    generated_at = datetime.now(UTC)
    insights: list[SkillInsight] = []
    for function in functions:
        for skill in registry.resolve(
            function=function,
            marketplace=evidence.marketplace,
            executable_only=True,
        ):
            insights.append(
                SkillInsight(
                    skill_id=skill.skill_id,
                    function=skill.function,
                    marketplace=evidence.marketplace,
                    entity_type=evidence.entity_type,
                    entity_id=evidence.entity_id,
                    summary=(
                        f"{skill.function}: fato validado recebido para "
                        f"{evidence.entity_type}/{evidence.entity_id}."
                    ),
                    proof_id=proof_id,
                    generated_at=generated_at,
                )
            )
    return tuple(insights)
