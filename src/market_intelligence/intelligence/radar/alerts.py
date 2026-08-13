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
    deadline = details.get("deadline")
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline)
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
        recommended_action=(str(details["recommended_action"])
                            if details.get("recommended_action") else None),
        responsible=(str(details["responsible"])
                     if details.get("responsible") else None),
        deadline=deadline if isinstance(deadline, datetime) else None,
    )
