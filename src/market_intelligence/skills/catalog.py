from __future__ import annotations

from market_intelligence.skills.registry import (
    SkillDescriptor,
    SkillExecutionStatus,
    SkillLicenseStatus,
    SkillRegistry,
)


_INTERNAL_SKILLS: tuple[tuple[str, str], ...] = (
    ("ingestion-normalization", "ingestion_normalization"),
    ("marketplace-analysis", "marketplace_analysis"),
    ("radar-anomaly-analysis", "radar_anomalies"),
    ("market-competition-analysis", "market_competition"),
    ("pricing-analysis-readonly", "pricing_analysis"),
    ("sales-trend-analysis", "sales_trend"),
    ("statistics-analysis", "statistics"),
    ("economics-analysis", "economics"),
    ("marketing-analysis", "marketing"),
    ("margin-accounts-analysis", "margin_accounts"),
    ("evidence-validation", "evidence"),
    ("investigation-analysis", "investigation"),
    ("alert-analytical-explanation", "alerts_explanation"),
)


def approved_skill_descriptors() -> tuple[SkillDescriptor, ...]:
    internal = tuple(
        SkillDescriptor(
            skill_id=skill_id,
            function=function,
            supported_marketplaces=("*",),
            license_status=SkillLicenseStatus.INTERNAL,
            execution_status=SkillExecutionStatus.APPROVED_ACTIVE,
            source=f"internal:market_intelligence/{function}",
        )
        for skill_id, function in _INTERNAL_SKILLS
    )
    references = (
        SkillDescriptor(
            skill_id="nexscope-proprietary-reference",
            function="marketplace_analysis",
            supported_marketplaces=("*",),
            license_status=SkillLicenseStatus.PROPRIETARY,
            execution_status=SkillExecutionStatus.REFERENCE_ONLY,
            source="external-reference:nexscope",
        ),
    )
    return internal + references


def bootstrap_skill_registry(registry: SkillRegistry) -> SkillRegistry:
    existing = {item.skill_id for item in registry.all()}
    for descriptor in approved_skill_descriptors():
        if descriptor.skill_id not in existing:
            registry.register(descriptor)
            existing.add(descriptor.skill_id)
    return registry
