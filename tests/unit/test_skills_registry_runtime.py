from __future__ import annotations

from datetime import UTC, datetime

import pytest

from market_intelligence.skills import SKILL_REGISTRY
from market_intelligence.skills.evidence_feed import ValidatedMarketplaceEvidence
from market_intelligence.skills.executor import execute_validated_evidence
from market_intelligence.skills.registry import SkillExecutionStatus, SkillLicenseStatus


def _valid_evidence() -> ValidatedMarketplaceEvidence:
    return ValidatedMarketplaceEvidence(
        marketplace="mercadolivre",
        entity_type="listing",
        entity_id="MLB-SMOKE",
        observed_at=datetime.now(UTC),
        statement="validated status observation",
        source="official_api_get_plus_webhook",
        evidence={
            "classification": "FATO",
            "webhook_validated": True,
            "official_get_validated": True,
            "proof_id": "smoke-proof",
        },
    )


def test_global_registry_bootstraps_only_approved_executable_licenses() -> None:
    items = SKILL_REGISTRY.all()
    executable = [item for item in items if item.executable]
    assert items
    assert len(executable) == 13
    assert all(
        item.execution_status is SkillExecutionStatus.APPROVED_ACTIVE for item in executable
    )
    assert all(
        item.license_status in {SkillLicenseStatus.INTERNAL, SkillLicenseStatus.OPEN_SOURCE}
        for item in executable
    )
    assert not [
        item
        for item in executable
        if item.license_status in {SkillLicenseStatus.PROPRIETARY, SkillLicenseStatus.QUARANTINE}
    ]
    nexscope = SKILL_REGISTRY.get("nexscope-proprietary-reference")
    assert nexscope.license_status is SkillLicenseStatus.PROPRIETARY
    assert nexscope.execution_status is SkillExecutionStatus.REFERENCE_ONLY
    assert nexscope.executable is False


def test_validated_fact_routes_to_active_analytical_skills() -> None:
    insights = execute_validated_evidence(_valid_evidence())
    assert insights
    assert {item.function for item in insights} == {
        "evidence",
        "marketplace_analysis",
        "radar_anomalies",
        "investigation",
        "alerts_explanation",
    }
    assert {item.proof_id for item in insights} == {"smoke-proof"}


def test_hypothesis_or_raw_cannot_enter_skills() -> None:
    evidence = _valid_evidence()
    bad = ValidatedMarketplaceEvidence(
        marketplace=evidence.marketplace,
        entity_type=evidence.entity_type,
        entity_id=evidence.entity_id,
        observed_at=evidence.observed_at,
        statement=evidence.statement,
        source=evidence.source,
        evidence={**evidence.evidence, "classification": "HIPOTESE"},
    )
    with pytest.raises(ValueError, match="skill_evidence_not_fact"):
        execute_validated_evidence(bad)
