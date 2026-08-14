from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from temporalio.client import Client, WorkflowHandle

from market_intelligence.ai.temporal_queue import start_minimized_ai_job
from market_intelligence.core.contracts import Alert, EvidenceLevel


_EVIDENCE_CLASS = {
    EvidenceLevel.FACT: "FATO",
    EvidenceLevel.INFERENCE: "INFERENCIA",
    EvidenceLevel.HYPOTHESIS: "HIPOTESE",
}


@dataclass(frozen=True, slots=True)
class RadarAIExplanationRequest:
    """Safe, deterministic bridge from a sovereign Radar alert to IA.

    The object deliberately contains no marketplace entity id and no raw
    evidence attributes. It can only request an explanation; it cannot mutate
    the source Alert or authorize a marketplace action.
    """

    request_id: str
    role: str
    purpose: str
    data: dict[str, Any]


def build_radar_alert_ai_request(
    alert: Alert,
    *,
    role: str = "system",
) -> RadarAIExplanationRequest:
    evidence_class = alert.evidence_classification
    if evidence_class is None:
        raise ValueError("radar_ai_evidence_class_missing")

    entity_alias = _entity_alias(
        marketplace=alert.entity.marketplace,
        entity_type=alert.entity.entity_type,
        entity_id=alert.entity.entity_id,
    )
    payload: dict[str, Any] = {
        "entity_type": alert.entity.entity_type,
        "entity_alias": entity_alias,
        "observed_change": alert.observed_change,
        "evidence_class": _EVIDENCE_CLASS[evidence_class],
        "severity": str(alert.severity.value),
        "confidence": alert.confidence,
        "observable_causes": list(alert.observable_causes),
        "hypotheses": list(alert.hypotheses),
    }
    if alert.first_observed_at is not None:
        payload["period_start"] = alert.first_observed_at.isoformat()
    if alert.last_observed_at is not None:
        payload["period_end"] = alert.last_observed_at.isoformat()
    if alert.estimated_impact is not None:
        payload["estimated_impact"] = alert.estimated_impact
    if alert.unexplained_residual is not None:
        payload["unexplained_residual"] = alert.unexplained_residual
    if alert.control_comparison:
        payload["control_comparison"] = _bounded_canonical_summary(alert.control_comparison)
    if alert.recommended_action:
        payload["recommendation"] = alert.recommended_action
    if alert.detector_version:
        payload["detector_version"] = alert.detector_version

    request_material = json.dumps(
        {
            "entity_alias": entity_alias,
            "purpose": "radar_alert_explanation",
            "evidence_class": payload["evidence_class"],
            "last_observed_at": payload.get("period_end"),
            "detector_version": payload.get("detector_version"),
            "observed_change": alert.observed_change,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_id = "radar-alert:" + hashlib.sha256(request_material.encode("utf-8")).hexdigest()
    return RadarAIExplanationRequest(
        request_id=request_id,
        role=role,
        purpose="radar_alert_explanation",
        data=payload,
    )


async def dispatch_radar_alert_explanation(
    client: Client,
    alert: Alert,
    *,
    role: str = "system",
) -> WorkflowHandle:
    """Dispatch explanation through the only approved minimized Temporal path."""

    request = build_radar_alert_ai_request(alert, role=role)
    return await start_minimized_ai_job(
        client,
        request_id=request.request_id,
        role=request.role,
        purpose=request.purpose,
        data=request.data,
    )


def _entity_alias(*, marketplace: str, entity_type: str, entity_id: str) -> str:
    material = f"{marketplace.strip().lower()}:{entity_type.strip().lower()}:{entity_id}".encode(
        "utf-8"
    )
    return "entity-" + hashlib.sha256(material).hexdigest()[:24]


def _bounded_canonical_summary(value: dict[str, Any]) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: f"<{type(item).__name__}>",
    )
    # AIDataGateway applies the authoritative string-size gate. Keeping this
    # bridge tighter prevents large nested source structures from being copied
    # into the outbound analytical contract in the first place.
    return rendered[:480]
