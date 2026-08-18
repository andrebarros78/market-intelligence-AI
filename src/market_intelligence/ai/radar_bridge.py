from __future__ import annotations

import hashlib
import re
from math import isfinite
from typing import Awaitable, Callable

from temporalio.client import Client, WorkflowHandle

from market_intelligence.ai.providers import ProviderConfigurationError
from market_intelligence.ai.temporal_queue import start_minimized_ai_job
from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation


RADAR_AI_BRIDGE_VERSION = "radar-ai-bridge@1.0.0"
RADAR_AI_PURPOSE = "radar_alert_explanation"
_INTERNAL_LABEL_RE = re.compile(r"^[a-zA-Z0-9_.@:-]{1,80}$")


def radar_entity_alias(entity_id: str) -> str:
    normalized = entity_id.strip()
    if not normalized:
        raise ProviderConfigurationError("radar_ai_entity_id_missing")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"entity-{digest[:20]}"


def _safe_internal_label(value: str, *, prefix: str) -> str:
    normalized = value.strip()
    if _INTERNAL_LABEL_RE.fullmatch(normalized):
        return normalized
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _evidence_class(finding: RadarFinding) -> str:
    levels = {result.level for result in finding.detector_results}
    if EvidenceLevel.HYPOTHESIS in levels:
        return "HIPOTESE"
    if EvidenceLevel.INFERENCE in levels:
        return "INFERENCIA"
    return "FATO"


def _severity(score: float) -> str:
    if score >= 0.85:
        return "critical"
    if score >= 0.70:
        return "high"
    if score >= 0.50:
        return "medium"
    if score >= 0.25:
        return "low"
    return "info"


def _primary_metric(observation: RadarObservation) -> dict[str, object]:
    candidates: list[tuple[float, str, float, float | None, int]] = []
    for raw_name, raw_value in observation.metrics.items():
        value = float(raw_value)
        if not isfinite(value):
            continue
        history = [float(item) for item in observation.history.get(raw_name, []) if isfinite(float(item))]
        expected = sum(history) / len(history) if history else None
        deviation = None
        magnitude = 0.0
        if expected is not None and expected != 0.0:
            deviation = ((value - expected) / abs(expected)) * 100.0
            magnitude = abs(deviation)
        candidates.append((magnitude, raw_name, value, expected, len(history)))

    if not candidates:
        return {}

    _magnitude, raw_name, observed, expected, sample_size = max(
        candidates,
        key=lambda item: (item[0], item[1]),
    )
    result: dict[str, object] = {
        "metric_name": _safe_internal_label(raw_name, prefix="metric"),
        "observed_value": observed,
        "sample_size": sample_size,
    }
    if expected is not None:
        result["expected_value"] = expected
        if expected != 0.0:
            result["deviation_percent"] = ((observed - expected) / abs(expected)) * 100.0
    return result


def radar_finding_to_ai_data(
    *,
    finding: RadarFinding,
    observation: RadarObservation,
) -> dict[str, object]:
    """Build the only Radar payload allowed to cross the IA-04 gateway.

    Raw entity ids, observation context, detector summaries and marketplace payloads
    are deliberately excluded. The returned object is still processed by
    AIDataGateway before entering Temporal history.
    """

    if finding.entity_id != observation.entity_id:
        raise ProviderConfigurationError("radar_ai_entity_mismatch")

    observable_causes: list[str] = []
    hypotheses: list[str] = []
    for result in finding.detector_results:
        label = _safe_internal_label(result.detector, prefix="detector")
        if result.level is EvidenceLevel.HYPOTHESIS:
            hypotheses.append(label)
        else:
            observable_causes.append(label)

    data: dict[str, object] = {
        "entity_type": "marketplace_entity",
        "entity_alias": radar_entity_alias(finding.entity_id),
        "period_end": observation.observed_at.isoformat(),
        "observed_change": "anomaly_detected" if finding.anomalous else "no_anomaly",
        "evidence_class": _evidence_class(finding),
        "severity": _severity(finding.score),
        "confidence": float(finding.score),
        "observable_causes": sorted(set(observable_causes)),
        "hypotheses": sorted(set(hypotheses)),
        "detector_version": RADAR_AI_BRIDGE_VERSION,
    }
    data.update(_primary_metric(observation))
    return data


RadarAIStarter = Callable[..., Awaitable[WorkflowHandle]]


async def start_radar_ai_explanation(
    client: Client,
    *,
    request_id: str,
    finding: RadarFinding,
    observation: RadarObservation,
    role: str = "system",
    starter: RadarAIStarter = start_minimized_ai_job,
) -> WorkflowHandle:
    """Dispatch a Radar explanation through the IA-07 minimized Temporal path."""

    data = radar_finding_to_ai_data(finding=finding, observation=observation)
    return await starter(
        client,
        request_id=request_id,
        role=role,
        purpose=RADAR_AI_PURPOSE,
        data=data,
    )
