from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import func, select

from market_intelligence.core.contracts import Evidence, EvidenceLevel, Severity
from market_intelligence.ingestion.channel import ChannelEvent
from market_intelligence.ingestion.events import build_raw_event
from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.channel_regime import ChannelRegimeCorrelationDetector
from market_intelligence.intelligence.radar.counterfactual import OperationalCounterfactualDetector
from market_intelligence.intelligence.radar.detectors import KnownRuleDetector, RobustZScoreDetector
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.intelligence.radar.priority import prioritize_alerts
from market_intelligence.intelligence.radar.regime import RegimeChangeDetector
from market_intelligence.intelligence.radar.residual import UnexplainedResidualDetector
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import (
    AlertRecord,
    ChannelEventRecord,
    EvidenceRecord,
    RawEventRecord,
    SnapshotRecord,
)
from market_intelligence.persistence.postgresql import (
    PostgresAlertRepository,
    PostgresChannelEventRepository,
    PostgresEntityRepository,
    PostgresRawEventRepository,
    PostgresSnapshotRepository,
)
from market_intelligence.core.contracts import EntityRef


DIGITAL_TWIN_VERSION = "radar-v1-digital-twin@1.0.0"
SANDBOX_FALSE_POSITIVE_THRESHOLD = 0.05
_FIXED_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
_STABLE_HISTORY = [100.0, 101.0, 99.0, 100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 100.0]


class DigitalTwinCheck(BaseModel):
    criterion: str
    passed: bool
    evidence: dict[str, object]


class RadarV1DigitalTwinReport(BaseModel):
    version: str = DIGITAL_TWIN_VERSION
    run_id: str
    synthetic_only: bool = True
    checks: list[DigitalTwinCheck]
    sandbox_false_positive_rate: float
    sandbox_false_positive_threshold: float = SANDBOX_FALSE_POSITIVE_THRESHOLD
    sandbox_passed: bool
    authorized_real_read_required: bool = True
    real_historical_false_positive_homologation_required: bool = True
    production_ready: bool = False


def _check(criterion: str, passed: bool, **evidence: object) -> DigitalTwinCheck:
    return DigitalTwinCheck(criterion=criterion, passed=bool(passed), evidence=evidence)


def _controls() -> list[dict[str, object]]:
    return [
        {
            "entity_id": f"CONTROL-{index}",
            "metrics": {"visits": current},
            "history": {"visits": _STABLE_HISTORY},
        }
        for index, current in enumerate((100.0, 101.0, 99.0), start=1)
    ]


def _channel_events(now: datetime) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    start = now - timedelta(minutes=11)
    for index in range(12):
        degraded = index >= 8
        events.append(
            {
                "marketplace": "mercadolivre",
                "direction": "inbound",
                "operation": "/items/MLB-DT",
                "observed_at": start + timedelta(minutes=index),
                "status_code": 503 if degraded else 200,
                "latency_ms": 420.0 if degraded else 90.0,
                "attempt": 2 if degraded else 1,
                "attributes": (
                    {"partial_content": True, "schema_changed": index == 11}
                    if degraded
                    else {}
                ),
            }
        )
    return events


def run_detector_acceptance() -> tuple[list[DigitalTwinCheck], float, object]:
    checks: list[DigitalTwinCheck] = []

    known_observation = RadarObservation(
        entity_id="MLB-KNOWN",
        observed_at=_FIXED_NOW,
        metrics={"visits": 100.0},
        history={"visits": _STABLE_HISTORY},
        context={
            "known_rule_violation": True,
            "known_rule_summary": "Synthetic stock/business rule violation",
        },
    )
    known = KnownRuleDetector().evaluate(known_observation)
    checks.append(
        _check(
            "known_rule_detection",
            known is not None and known.level is EvidenceLevel.FACT and known.score == 1.0,
            detector=known.detector if known else None,
            evidence_level=known.level.value if known else None,
        )
    )

    unknown_observation = RadarObservation(
        entity_id="MLB-UNKNOWN",
        observed_at=_FIXED_NOW,
        metrics={"visits": 55.0},
        history={"visits": _STABLE_HISTORY},
        context={},
    )
    unknown = RobustZScoreDetector().evaluate(unknown_observation)
    checks.append(
        _check(
            "unknown_anomaly_detection",
            unknown is not None and unknown.score >= 0.60 and not unknown_observation.context,
            detector=unknown.detector if unknown else None,
            score=unknown.score if unknown else None,
        )
    )

    regime_observation = RadarObservation(
        entity_id="MLB-REGIME",
        observed_at=_FIXED_NOW,
        metrics={"visits": 69.0},
        history={
            "visits": [100.0, 101.0, 99.0, 100.0, 100.0, 101.0, 70.0, 69.0, 71.0, 68.0, 70.0]
        },
    )
    regime = RegimeChangeDetector().evaluate(regime_observation)
    checks.append(
        _check(
            "regime_shift_detection",
            regime is not None
            and regime.score >= 0.60
            and regime.attributes.get("cause_status") == "unknown_not_inferred",
            detector=regime.detector if regime else None,
            pattern=regime.attributes.get("pattern") if regime else None,
            causal_cause_inferred=False,
        )
    )

    control_observation = RadarObservation(
        entity_id="MLB-CONTROL-TARGET",
        observed_at=_FIXED_NOW,
        metrics={"visits": 75.0},
        history={"visits": _STABLE_HISTORY},
        context={"control_candidates": _controls()},
    )
    control = OperationalCounterfactualDetector().evaluate(control_observation)
    checks.append(
        _check(
            "control_comparison",
            control is not None
            and control.level is EvidenceLevel.INFERENCE
            and control.attributes.get("causal_claim") is False
            and float(control.attributes.get("counterfactual_expected") or 0.0) == 100.0,
            detector=control.detector if control else None,
            expected=control.attributes.get("counterfactual_expected") if control else None,
            gap=control.attributes.get("counterfactual_gap") if control else None,
        )
    )

    target = [100.0, 110.0, 105.0, 115.0, 110.0, 120.0, 115.0, 125.0, 120.0, 130.0]
    associated = [50.0, 55.0, 52.5, 57.5, 55.0, 60.0, 57.5, 62.5, 60.0, 65.0]
    residual_observation = RadarObservation(
        entity_id="MLB-RESIDUAL",
        observed_at=_FIXED_NOW,
        metrics={"visits": 80.0},
        history={"visits": target},
        context={
            "factor_attribution": {
                "metric": "visits",
                "expected": 130.0,
                "factors": [
                    {
                        "name": "competition",
                        "current": 60.0,
                        "history": associated,
                        "source": "market",
                    }
                ],
            }
        },
    )
    residual = UnexplainedResidualDetector().evaluate(residual_observation)
    checks.append(
        _check(
            "unexplained_residual",
            residual is not None
            and residual.level is EvidenceLevel.INFERENCE
            and float(residual.attributes.get("unexplained_residual") or 0.0) < 0
            and residual.attributes.get("cause_status") == "unknown_not_inferred",
            detector=residual.detector if residual else None,
            residual=residual.attributes.get("unexplained_residual") if residual else None,
            observable_causes=residual.attributes.get("observable_causes") if residual else None,
        )
    )

    channel_observation = RadarObservation(
        entity_id="MLB-DT",
        observed_at=_FIXED_NOW,
        metrics={"visits": 55.0},
        history={"visits": _STABLE_HISTORY},
        context={"channel_events": _channel_events(_FIXED_NOW)},
    )
    channel = ChannelRegimeCorrelationDetector().evaluate(channel_observation)
    checks.append(
        _check(
            "sanitized_channel_correlation",
            channel is not None
            and channel.level is EvidenceLevel.INFERENCE
            and channel.attributes.get("causal_claim") is False
            and channel.attributes.get("internal_platform_cause_confirmed") is False,
            detector=channel.detector if channel else None,
            correlation_status=channel.attributes.get("correlation_status") if channel else None,
        )
    )

    hypothesis_evidence = Evidence(
        level=EvidenceLevel.HYPOTHESIS,
        statement="Synthetic hypothesis requiring confirmation",
        source="digital-twin",
        observed_at=_FIXED_NOW,
    )
    levels = {
        known.level if known else None,
        control.level if control else None,
        hypothesis_evidence.level,
    }
    checks.append(
        _check(
            "epistemic_separation",
            {EvidenceLevel.FACT, EvidenceLevel.INFERENCE, EvidenceLevel.HYPOTHESIS} <= levels,
            levels=sorted(level.value for level in levels if level is not None),
        )
    )

    full_finding = build_default_radar().evaluate(unknown_observation)
    complete_alert = alert_from_finding(
        finding=full_finding,
        marketplace="mercadolivre",
        entity_type="listing",
        observed_at=_FIXED_NOW,
        context={
            "estimated_impact": 12500.0,
            "observable_causes": ["competition_stable"],
            "unexplained_residual": -45.0,
            "hypotheses": ["distribution_change_requires_investigation"],
            "control_comparison": {"controls": 3, "target_gap": -45.0},
            "recommended_action": "Investigar controles e acompanhar novas observações.",
            "responsible": "radar-operator",
            "deadline": (_FIXED_NOW + timedelta(hours=4)).isoformat(),
            "first_observed_at": (_FIXED_NOW - timedelta(minutes=30)).isoformat(),
            "last_observed_at": _FIXED_NOW.isoformat(),
            "detector_version": "digital-twin-detector-set@1",
        },
    )
    complete = complete_alert is not None and all(
        [
            complete_alert.entity.entity_id,
            complete_alert.observed_change,
            complete_alert.evidence,
            complete_alert.evidence_classification,
            complete_alert.severity,
            complete_alert.estimated_impact is not None,
            complete_alert.confidence >= 0.60,
            complete_alert.observable_causes,
            complete_alert.unexplained_residual is not None,
            complete_alert.hypotheses,
            complete_alert.control_comparison,
            complete_alert.recommended_action,
            complete_alert.responsible,
            complete_alert.deadline,
            complete_alert.first_observed_at,
            complete_alert.last_observed_at,
            complete_alert.detector_version,
        ]
    )
    checks.append(
        _check(
            "complete_alert_contract",
            bool(complete),
            evidence_class=(
                complete_alert.evidence_classification.value if complete_alert else None
            ),
            severity=complete_alert.severity.value if complete_alert else None,
            estimated_impact=complete_alert.estimated_impact if complete_alert else None,
        )
    )

    if complete_alert is None:
        raise RuntimeError("digital_twin_complete_alert_not_created")
    lower_impact = complete_alert.model_copy(
        update={"estimated_impact": 500.0, "severity": Severity.CRITICAL}
    )
    higher_impact = complete_alert.model_copy(
        update={"estimated_impact": 25000.0, "severity": Severity.MEDIUM}
    )
    ranked = prioritize_alerts([lower_impact, higher_impact])
    checks.append(
        _check(
            "business_impact_prioritization",
            ranked[0].estimated_impact == 25000.0,
            first_impact=ranked[0].estimated_impact,
            first_severity=ranked[0].severity.value,
            second_impact=ranked[1].estimated_impact,
        )
    )

    radar = build_default_radar()
    false_positives = 0
    normal_count = 100
    for index in range(normal_count):
        current = (99.0, 100.0, 101.0)[index % 3]
        normal = RadarObservation(
            entity_id=f"NORMAL-{index:03d}",
            observed_at=_FIXED_NOW,
            metrics={"visits": current},
            history={"visits": _STABLE_HISTORY},
            context={},
        )
        if radar.evaluate(normal).anomalous:
            false_positives += 1
    false_positive_rate = false_positives / normal_count
    checks.append(
        _check(
            "sandbox_false_positive_threshold",
            false_positive_rate <= SANDBOX_FALSE_POSITIVE_THRESHOLD,
            false_positives=false_positives,
            observations=normal_count,
            rate=false_positive_rate,
            threshold=SANDBOX_FALSE_POSITIVE_THRESHOLD,
            scope="synthetic_only_not_production_homologation",
        )
    )

    first = radar.evaluate(unknown_observation).model_dump(mode="json")
    second = radar.evaluate(unknown_observation).model_dump(mode="json")
    checks.append(
        _check(
            "reproducible_evidence",
            first == second,
            finding_sha256=_sha_json(first),
        )
    )
    return checks, false_positive_rate, complete_alert


def _sha_json(value: object) -> str:
    import hashlib

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


async def run_radar_v1_digital_twin(
    database_url: str,
    *,
    run_id: str | None = None,
) -> RadarV1DigitalTwinReport:
    run_id = run_id or uuid4().hex[:16]
    checks, false_positive_rate, complete_alert = run_detector_acceptance()

    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    raw_repo = PostgresRawEventRepository(sessions)
    channel_repo = PostgresChannelEventRepository(sessions)
    entity_repo = PostgresEntityRepository(sessions)
    snapshot_repo = PostgresSnapshotRepository(sessions)
    alert_repo = PostgresAlertRepository(sessions)

    entity = EntityRef(
        marketplace="mercadolivre",
        entity_type="listing",
        entity_id=f"MLB-DT-{run_id}",
    )
    raw_payload = {"id": entity.entity_id, "status": "active", "available_quantity": 10}
    raw = build_raw_event(
        source="mercadolivre",
        event_type="items",
        payload=raw_payload,
        external_id=f"digital-twin-event-{run_id}",
        resource=f"/items/{entity.entity_id}",
        occurred_at=_FIXED_NOW,
        received_at=_FIXED_NOW,
    )
    try:
        raw_inserted = await raw_repo.append_if_new(raw)
        await entity_repo.upsert(entity, raw_payload, _FIXED_NOW)
        snapshot_inserted = await snapshot_repo.append_if_changed(entity, raw_payload, _FIXED_NOW)

        channel_secret = f"Bearer-DIGITAL-TWIN-SECRET-{run_id}"
        channel_event = ChannelEvent(
            marketplace="mercadolivre",
            direction="inbound",
            operation=f"/items/{entity.entity_id}",
            observed_at=_FIXED_NOW,
            status_code=200,
            latency_ms=85.0,
            attempt=1,
            correlation_id=f"corr-{run_id}",
            request_id=f"req-{run_id}",
            attributes={
                "authorization": channel_secret,
                "access_token": f"token-{run_id}",
                "response_size": 321,
                "schema_changed": False,
            },
        )
        channel_inserted = await channel_repo.append_if_new(channel_event)

        persisted_alert = complete_alert.model_copy(
            update={"entity": entity, "detector_version": "digital-twin-detector-set@1"}
        )
        alert_inserted = await alert_repo.save_if_new(persisted_alert)

        async with sessions() as session:
            raw_count = int(
                (await session.execute(
                    select(func.count()).select_from(RawEventRecord).where(
                        RawEventRecord.external_id == f"digital-twin-event-{run_id}"
                    )
                )).scalar_one()
            )
            snapshot_count = int(
                (await session.execute(
                    select(func.count()).select_from(SnapshotRecord).where(
                        SnapshotRecord.entity_id == entity.entity_id
                    )
                )).scalar_one()
            )
            channel_record = (
                await session.execute(
                    select(ChannelEventRecord).where(
                        ChannelEventRecord.request_id == f"req-{run_id}"
                    )
                )
            ).scalar_one()
            alert_record = (
                await session.execute(
                    select(AlertRecord).where(AlertRecord.entity_id == entity.entity_id)
                )
            ).scalar_one()
            evidence_count = int(
                (await session.execute(
                    select(func.count()).select_from(EvidenceRecord).where(
                        EvidenceRecord.alert_id == alert_record.id
                    )
                )).scalar_one()
            )

        rendered_channel = json.dumps(channel_record.attributes, sort_keys=True)
        channel_sanitized = (
            channel_secret not in rendered_channel
            and f"token-{run_id}" not in rendered_channel
            and channel_record.attributes.get("authorization") == "[REDACTED]"
            and channel_record.attributes.get("access_token") == "[REDACTED]"
        )
        checks.append(
            _check(
                "event_snapshot_ingestion",
                raw_inserted and snapshot_inserted and raw_count == 1 and snapshot_count == 1,
                raw_count=raw_count,
                snapshot_count=snapshot_count,
                raw_hash=raw.payload_hash,
            )
        )
        checks.append(
            _check(
                "sanitized_channel_telemetry_persistence",
                channel_inserted and channel_sanitized,
                authorization_value=channel_record.attributes.get("authorization"),
                access_token_value=channel_record.attributes.get("access_token"),
                response_size=channel_record.attributes.get("response_size"),
            )
        )
        checks.append(
            _check(
                "complete_alert_persistence",
                alert_inserted
                and alert_record.estimated_impact == 12500.0
                and evidence_count > 0
                and alert_record.evidence_classification is not None,
                evidence_count=evidence_count,
                evidence_classification=alert_record.evidence_classification,
                impact=alert_record.estimated_impact,
            )
        )
    finally:
        await engine.dispose()

    # Simulate process restart with a new SQLAlchemy engine/session/repository set.
    restarted_engine = create_database_engine(database_url)
    restarted_sessions = create_session_factory(restarted_engine)
    try:
        restarted_raw_repo = PostgresRawEventRepository(restarted_sessions)
        restarted_snapshot_repo = PostgresSnapshotRepository(restarted_sessions)
        restarted_entity_repo = PostgresEntityRepository(restarted_sessions)
        duplicate_raw = await restarted_raw_repo.append_if_new(raw)
        duplicate_snapshot = await restarted_snapshot_repo.append_if_changed(
            entity, raw_payload, _FIXED_NOW + timedelta(minutes=1)
        )
        restored_entity = await restarted_entity_repo.get(entity)
        checks.append(
            _check(
                "restart_without_history_loss",
                duplicate_raw is False
                and duplicate_snapshot is False
                and restored_entity is not None
                and restored_entity.current_payload == raw_payload,
                duplicate_raw_inserted=duplicate_raw,
                duplicate_snapshot_inserted=duplicate_snapshot,
                entity_restored=restored_entity is not None,
            )
        )
    finally:
        await restarted_engine.dispose()

    sandbox_passed = all(item.passed for item in checks)
    return RadarV1DigitalTwinReport(
        run_id=run_id,
        checks=checks,
        sandbox_false_positive_rate=false_positive_rate,
        sandbox_passed=sandbox_passed,
        production_ready=False,
    )
