from __future__ import annotations

from datetime import datetime
from typing import Any

from market_intelligence.core.contracts import Alert, EntityRef, Evidence, Severity
from market_intelligence.intelligence.radar.models import RadarFinding


def _severity(score: float) -> Severity:
    if score >= 0.95:
        return Severity.CRITICAL
    if score >= 0.85:
        return Severity.HIGH
    if score >= 0.70:
        return Severity.MEDIUM
    return Severity.LOW


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _control_comparison(
    finding: RadarFinding, context: dict[str, Any]
) -> dict[str, Any] | None:
    explicit = context.get("control_comparison")
    if explicit is not None:
        return explicit if isinstance(explicit, dict) else {"summary": str(explicit)}
    for result in finding.detector_results:
        comparison = result.attributes.get("control_comparison")
        if isinstance(comparison, dict):
            return comparison
    return None


def _residual_value(finding: RadarFinding, context: dict[str, Any]) -> float | None:
    explicit = context.get("unexplained_residual")
    if explicit is not None:
        return float(explicit)
    for result in finding.detector_results:
        value = result.attributes.get("unexplained_residual")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _observable_causes(finding: RadarFinding, context: dict[str, Any]) -> list[str]:
    explicit = _strings(context.get("observable_causes"))
    if explicit:
        return explicit
    for result in finding.detector_results:
        values = _strings(result.attributes.get("observable_causes"))
        if values:
            return values
    return []


def _detector_version(finding: RadarFinding, context: dict[str, Any]) -> str:
    explicit = context.get("detector_version")
    if explicit:
        return str(explicit)
    versions = sorted(
        {
            str(result.attributes["detector_version"])
            for result in finding.detector_results
            if result.attributes.get("detector_version")
        }
    )
    return "+".join(versions) if versions else "radar-core-v1"


def alert_from_finding(
    *,
    finding: RadarFinding,
    marketplace: str,
    entity_type: str,
    observed_at: datetime,
    context: dict[str, Any] | None = None,
) -> Alert | None:
    if not finding.anomalous:
        return None
    details = context or {}
    evidence = [
        Evidence(
            level=result.level,
            statement=result.summary,
            source=f"radar:{result.detector}",
            observed_at=observed_at,
            attributes=result.attributes,
        )
        for result in finding.detector_results
    ]
    summaries = [item.statement for item in evidence]
    observed_change = " | ".join(summaries) or "Radar anomaly detected"
    estimated_impact = details.get("estimated_impact")
    if estimated_impact is not None:
        estimated_impact = float(estimated_impact)
    return Alert(
        entity=EntityRef(
            marketplace=marketplace,
            entity_type=entity_type,
            entity_id=finding.entity_id,
        ),
        observed_change=observed_change,
        evidence=evidence,
        severity=_severity(finding.score),
        estimated_impact=estimated_impact,
        confidence=finding.score,
        observable_causes=_observable_causes(finding, details),
        unexplained_residual=_residual_value(finding, details),
        hypotheses=_strings(details.get("hypotheses")),
        control_comparison=_control_comparison(finding, details),
        recommended_action=(
            str(details["recommended_action"])
            if details.get("recommended_action")
            else None
        ),
        responsible=(str(details["responsible"]) if details.get("responsible") else None),
        deadline=_datetime(details.get("deadline")),
        first_observed_at=_datetime(details.get("first_observed_at")) or observed_at,
        last_observed_at=_datetime(details.get("last_observed_at")) or observed_at,
        detector_version=_detector_version(finding, details),
    )
