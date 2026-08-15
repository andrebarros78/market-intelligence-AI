from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.sovereign.models import SignalEnvelope
from market_intelligence.persistence.investigations import PostgresInvestigationRepository


_SNAPSHOT_NUMERIC_KEYS = (
    "price",
    "available_quantity",
    "sold_quantity",
    "visits",
)
_CHANNEL_NUMERIC_KEYS = ("status_code", "latency_ms", "attempt")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _surface_metrics(payload: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    status = _number(payload.get("status"))
    if status is not None:
        metrics["status_code"] = status
    schema_paths = payload.get("schema_paths")
    if isinstance(schema_paths, list):
        metrics["schema_path_count"] = float(len(schema_paths))
    fields = payload.get("top_level_fields")
    if isinstance(fields, list):
        metrics["top_level_field_count"] = float(len(fields))
    query_keys = payload.get("request_query_keys")
    if isinstance(query_keys, list):
        metrics["request_query_key_count"] = float(len(query_keys))
    resource_segments = _number(payload.get("resource_segments"))
    if resource_segments is not None:
        metrics["resource_segment_count"] = resource_segments

    request_metadata = payload.get("request_metadata")
    if isinstance(request_metadata, dict):
        count = _number(request_metadata.get("header_count"))
        if count is not None:
            metrics["request_header_count"] = count
        metrics["request_credential_header_present"] = float(
            request_metadata.get("credential_header_present") is True
        )

    response_metadata = payload.get("response_metadata")
    if isinstance(response_metadata, dict):
        count = _number(response_metadata.get("header_count"))
        if count is not None:
            metrics["response_header_count"] = count
        response_schema = response_metadata.get("json_schema")
        if isinstance(response_schema, dict):
            paths = response_schema.get("schema_paths")
            fields = response_schema.get("top_level_fields")
            if isinstance(paths, list):
                metrics["response_schema_path_count"] = float(len(paths))
            if isinstance(fields, list):
                metrics["response_top_level_field_count"] = float(len(fields))

    request_body_schema = payload.get("request_body_schema")
    if isinstance(request_body_schema, dict):
        json_schema = request_body_schema.get("json_schema")
        if isinstance(json_schema, dict):
            paths = json_schema.get("schema_paths")
            fields = json_schema.get("top_level_fields")
            if isinstance(paths, list):
                metrics["request_schema_path_count"] = float(len(paths))
            if isinstance(fields, list):
                metrics["request_top_level_field_count"] = float(len(fields))
    return metrics


def signal_metrics(signal: SignalEnvelope) -> dict[str, float]:
    payload = signal.payload
    metrics: dict[str, float] = {}
    if signal.entity_type == "surface":
        return _surface_metrics(payload)

    keys = _CHANNEL_NUMERIC_KEYS if signal.entity_type == "channel_operation" else _SNAPSHOT_NUMERIC_KEYS
    for key in keys:
        value = _number(payload.get(key))
        if value is not None:
            metrics[key] = value
    return metrics


def build_radar_observation(
    signal: SignalEnvelope,
    history: Iterable[SignalEnvelope],
    *,
    hypotheses: Iterable[str] = (),
) -> RadarObservation | None:
    metrics = signal_metrics(signal)
    if not metrics:
        return None

    history_values: dict[str, list[float]] = {metric: [] for metric in metrics}
    for previous in history:
        previous_metrics = signal_metrics(previous)
        for metric in metrics:
            if metric in previous_metrics:
                history_values[metric].append(previous_metrics[metric])
    history_values = {key: values for key, values in history_values.items() if values}

    return RadarObservation(
        entity_id=signal.entity_id,
        observed_at=signal.observed_at,
        metrics=metrics,
        history=history_values,
        context={
            "sovereign_core": True,
            "signal_id": signal.signal_id,
            "signal_kind": signal.kind,
            "signal_source": signal.source,
            "marketplace": signal.marketplace,
            "hypotheses": [text for text in hypotheses if str(text).strip()][:16],
            "causal_claim": False,
        },
    )


def normalize_investigation_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    step = result.get("step") if isinstance(result.get("step"), dict) else {}
    return {
        "finding_hash": step.get("finding_hash"),
        "status_after": result.get("status") or step.get("status_after"),
        "confidence_after": result.get("confidence") if isinstance(result.get("confidence"), (int, float)) else step.get("confidence_after"),
        "observation_count": int(result.get("observation_count") or 0),
        "anomalous_observation_count": int(result.get("anomalous_observation_count") or 0),
        "ever_confirmed": bool(result.get("ever_confirmed")),
        "hypotheses": list(result.get("hypotheses") or []),
        "causal_claim": False,
        "evidence_summary": {
            "case_id": result.get("case_id"),
            "event_id": result.get("event_id"),
            "event_inserted": bool(result.get("event_inserted")),
            "event_ignored": bool(result.get("event_ignored")),
            "progressive_investigation": step.get("evidence_summary") or {},
            "engine_version": result.get("engine_version") or step.get("engine_version"),
        },
    }


class SovereignInvestigationBridge:
    """Connect the sovereign loop to the already-proven progressive investigator.

    It creates no new investigation truth model. The existing Radar +
    PostgresInvestigationRepository remain the authoritative investigator and timeline.
    """

    version = "sovereign-investigation-bridge@1.0.0"

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._repository = PostgresInvestigationRepository(sessions)
        self._radar = build_default_radar()

    async def advance(
        self,
        *,
        signal: SignalEnvelope,
        history: Iterable[SignalEnvelope],
        hypotheses: Iterable[str] = (),
    ) -> dict[str, Any] | None:
        observation = build_radar_observation(signal, history, hypotheses=hypotheses)
        if observation is None:
            return None
        finding = self._radar.evaluate(observation)
        result = await self._repository.advance(
            marketplace=signal.marketplace,
            entity_type=signal.entity_type,
            finding=finding,
            observation=observation,
        )
        return normalize_investigation_result(result)
