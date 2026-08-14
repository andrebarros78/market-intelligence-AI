from __future__ import annotations

from collections.abc import Iterable

from market_intelligence.core.contracts import Alert, Severity


_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def alert_business_priority_key(alert: Alert) -> tuple[float, int, float, str, str]:
    """Return a stable descending-priority key with business impact first.

    A missing impact is treated as zero; statistical confidence or severity can
    never outrank a larger explicitly estimated business impact.
    """

    impact = max(0.0, float(alert.estimated_impact or 0.0))
    return (
        impact,
        _SEVERITY_RANK[alert.severity],
        float(alert.confidence),
        alert.entity.entity_type,
        alert.entity.entity_id,
    )


def prioritize_alerts(alerts: Iterable[Alert]) -> list[Alert]:
    return sorted(alerts, key=alert_business_priority_key, reverse=True)
