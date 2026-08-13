from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


_BUSINESS_METRICS = {
    "visits",
    "visitas",
    "sales",
    "vendas",
    "orders",
    "pedidos",
    "conversion",
    "conversao",
    "revenue",
    "receita",
    "gmv",
    "clicks",
    "cliques",
    "impressions",
    "impressoes",
    "ctr",
}


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _step(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.median(abs(right - left) for left, right in zip(values, values[1:]))


def _scale(values: list[float]) -> float:
    center = statistics.median(values) if values else 0.0
    return max(_mad(values), _step(values), abs(center) * 0.02, 1e-9)


def _rate(values: list[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _median_latency(events: list[ChannelEvent]) -> float | None:
    values = [float(event.latency_ms) for event in events if event.latency_ms is not None]
    return statistics.median(values) if values else None


def _median_cadence_seconds(events: list[ChannelEvent]) -> float | None:
    if len(events) < 3:
        return None
    ordered = sorted(event.observed_at for event in events)
    gaps = [(right - left).total_seconds() for left, right in zip(ordered, ordered[1:])]
    positive = [gap for gap in gaps if gap > 0]
    return statistics.median(positive) if positive else None


def _schema_signal(event: ChannelEvent) -> bool:
    attrs = event.attributes or {}
    return bool(
        attrs.get("schema_changed")
        or attrs.get("schema_change")
        or attrs.get("new_fields")
        or attrs.get("missing_fields")
        or attrs.get("fields_added")
        or attrs.get("fields_removed")
    )


def _partial_signal(event: ChannelEvent) -> bool:
    attrs = event.attributes or {}
    return bool(
        event.status_code == 206
        or attrs.get("partial_content")
        or attrs.get("content_missing")
        or attrs.get("missing_fields")
    )


def _parse_events(value: Any) -> list[ChannelEvent]:
    if not isinstance(value, list):
        return []
    events: list[ChannelEvent] = []
    for item in value:
        try:
            events.append(ChannelEvent.model_validate(item))
        except Exception:
            continue
    return sorted(events, key=lambda event: event.observed_at)


class ChannelRegimeCorrelationDetector:
    """Correlates an observed channel regime change with business deterioration.

    The detector never claims an internal Mercado Livre cause. Channel telemetry
    is reduced to aggregate operational signals, and raw headers/secrets are not
    propagated into evidence.
    """

    name = "channel_regime_correlation_v1"
    version = "channel-regime-correlation@1.0.0"

    def __init__(
        self,
        *,
        baseline_events: int = 8,
        recent_events: int = 4,
        min_business_history: int = 8,
        min_business_effect: float = 2.5,
        min_business_relative_drop: float = 0.15,
        rate_delta_threshold: float = 0.35,
        latency_ratio_threshold: float = 2.0,
        latency_absolute_delta_ms: float = 100.0,
        cadence_ratio_threshold: float = 2.5,
    ) -> None:
        if baseline_events < 6:
            raise ValueError("baseline_events must be at least 6")
        if recent_events < 3:
            raise ValueError("recent_events must be at least 3")
        self.baseline_events = baseline_events
        self.recent_events = recent_events
        self.min_business_history = min_business_history
        self.min_business_effect = min_business_effect
        self.min_business_relative_drop = min_business_relative_drop
        self.rate_delta_threshold = rate_delta_threshold
        self.latency_ratio_threshold = latency_ratio_threshold
        self.latency_absolute_delta_ms = latency_absolute_delta_ms
        self.cadence_ratio_threshold = cadence_ratio_threshold

    def _channel_signals(
        self, baseline: list[ChannelEvent], recent: list[ChannelEvent]
    ) -> tuple[list[str], dict[str, Any]]:
        baseline_error = _rate([bool(e.status_code is not None and e.status_code >= 400) for e in baseline])
        recent_error = _rate([bool(e.status_code is not None and e.status_code >= 400) for e in recent])
        baseline_retry = _rate([e.attempt > 1 for e in baseline])
        recent_retry = _rate([e.attempt > 1 for e in recent])
        baseline_partial = _rate([_partial_signal(e) for e in baseline])
        recent_partial = _rate([_partial_signal(e) for e in recent])
        baseline_schema = _rate([_schema_signal(e) for e in baseline])
        recent_schema = _rate([_schema_signal(e) for e in recent])
        baseline_rate_limit = _rate([e.status_code == 429 for e in baseline])
        recent_rate_limit = _rate([e.status_code == 429 for e in recent])
        baseline_server_error = _rate([bool(e.status_code is not None and e.status_code >= 500) for e in baseline])
        recent_server_error = _rate([bool(e.status_code is not None and e.status_code >= 500) for e in recent])

        signals: list[str] = []
        if recent_error - baseline_error >= self.rate_delta_threshold:
            signals.append("error_rate_shift")
        if recent_retry - baseline_retry >= self.rate_delta_threshold:
            signals.append("retry_rate_shift")
        if recent_partial - baseline_partial >= self.rate_delta_threshold:
            signals.append("partial_content_shift")
        if recent_rate_limit - baseline_rate_limit >= self.rate_delta_threshold:
            signals.append("rate_limit_shift")
        if recent_server_error - baseline_server_error >= self.rate_delta_threshold:
            signals.append("server_error_shift")
        if recent_schema > baseline_schema and recent_schema > 0:
            signals.append("schema_change_shift")

        baseline_latency = _median_latency(baseline)
        recent_latency = _median_latency(recent)
        latency_ratio: float | None = None
        if baseline_latency is not None and recent_latency is not None:
            latency_ratio = recent_latency / max(baseline_latency, 1.0)
            if (
                latency_ratio >= self.latency_ratio_threshold
                and recent_latency - baseline_latency >= self.latency_absolute_delta_ms
            ):
                signals.append("latency_shift")

        baseline_cadence = _median_cadence_seconds(baseline)
        recent_cadence = _median_cadence_seconds(recent)
        cadence_ratio: float | None = None
        if baseline_cadence is not None and recent_cadence is not None:
            cadence_ratio = max(
                recent_cadence / max(baseline_cadence, 1e-9),
                baseline_cadence / max(recent_cadence, 1e-9),
            )
            if cadence_ratio >= self.cadence_ratio_threshold:
                signals.append("cadence_shift")

        aggregate = {
            "baseline_event_count": len(baseline),
            "recent_event_count": len(recent),
            "baseline_error_rate": baseline_error,
            "recent_error_rate": recent_error,
            "baseline_retry_rate": baseline_retry,
            "recent_retry_rate": recent_retry,
            "baseline_partial_rate": baseline_partial,
            "recent_partial_rate": recent_partial,
            "baseline_rate_limit_rate": baseline_rate_limit,
            "recent_rate_limit_rate": recent_rate_limit,
            "baseline_server_error_rate": baseline_server_error,
            "recent_server_error_rate": recent_server_error,
            "baseline_schema_signal_rate": baseline_schema,
            "recent_schema_signal_rate": recent_schema,
            "baseline_latency_ms": baseline_latency,
            "recent_latency_ms": recent_latency,
            "latency_ratio": latency_ratio,
            "baseline_cadence_seconds": baseline_cadence,
            "recent_cadence_seconds": recent_cadence,
            "cadence_ratio": cadence_ratio,
        }
        return signals, aggregate

    def _business_degradation(self, observation: RadarObservation) -> dict[str, Any] | None:
        configured = observation.context.get("channel_business_metrics")
        if isinstance(configured, list) and configured:
            allowed = {str(metric).strip().lower() for metric in configured if str(metric).strip()}
        else:
            allowed = _BUSINESS_METRICS

        best: dict[str, Any] | None = None
        for metric, current in observation.metrics.items():
            if metric.lower() not in allowed:
                continue
            history = [float(value) for value in observation.history.get(metric, [])]
            if len(history) < self.min_business_history:
                continue
            baseline = statistics.median(history)
            scale = _scale(history)
            drop = baseline - float(current)
            if drop <= 0:
                continue
            effect = drop / scale
            relative_drop = drop / max(abs(baseline), scale)
            if effect < self.min_business_effect or relative_drop < self.min_business_relative_drop:
                continue
            candidate = {
                "metric": metric,
                "baseline": baseline,
                "observed": float(current),
                "absolute_drop": drop,
                "relative_drop": relative_drop,
                "effect_size": effect,
            }
            if best is None or (effect, relative_drop) > (
                float(best["effect_size"]),
                float(best["relative_drop"]),
            ):
                best = candidate
        return best

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        events = _parse_events(observation.context.get("channel_events"))
        required = self.baseline_events + self.recent_events
        if len(events) < required:
            return None

        selected = events[-required:]
        baseline = selected[: self.baseline_events]
        recent = selected[self.baseline_events :]
        signals, aggregate = self._channel_signals(baseline, recent)
        if not signals:
            return None

        operations = sorted({event.operation for event in selected})
        marketplaces = sorted({event.marketplace for event in selected})
        business = self._business_degradation(observation)
        attributes: dict[str, Any] = {
            "detector_version": self.version,
            "channel_regime_detected": True,
            "channel_signals": signals,
            "channel_aggregate": aggregate,
            "operations": operations,
            "marketplaces": marketplaces,
            "correlation_status": "business_signal_absent",
            "causal_claim": False,
            "internal_platform_cause_confirmed": False,
            "epistemic_note": "co-occurrence is not proof of marketplace internal causality",
        }

        if business is None:
            return DetectorResult(
                detector=self.name,
                score=min(0.59, 0.45 + 0.03 * len(signals)),
                level=EvidenceLevel.FACT,
                summary="Observed channel regime change without sufficient correlated business deterioration",
                attributes=attributes,
            )

        attributes["correlation_status"] = "joint_regime_detected"
        attributes["business_degradation"] = business
        attributes["recommended_interpretation"] = (
            "joint ecosystem regime change detected; specific internal cause not confirmed"
        )
        strength = min(1.0, float(business["relative_drop"]) + min(float(business["effect_size"]) / 10.0, 0.5))
        score = min(1.0, 0.70 + 0.04 * min(len(signals), 5) + 0.10 * strength)
        return DetectorResult(
            detector=self.name,
            score=score,
            level=EvidenceLevel.INFERENCE,
            summary=(
                "Joint channel and business regime change detected; specific internal cause not confirmed"
            ),
            attributes=attributes,
        )
