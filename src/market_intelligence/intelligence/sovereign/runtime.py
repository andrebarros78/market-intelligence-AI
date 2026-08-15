from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.sovereign_learning import SovereignLearningDecision
from market_intelligence.intelligence.sovereign.core import SovereignIntelligenceCore
from market_intelligence.intelligence.sovereign.models import SignalEnvelope
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.learning import PostgresLearningRepository
from market_intelligence.persistence.models import (
    ChannelEventRecord,
    InvestigationCaseRecord,
    RawEventRecord,
    SnapshotRecord,
)
from market_intelligence.persistence.postgresql import database_healthcheck
from market_intelligence.persistence.sovereign_intelligence import PostgresSovereignIntelligenceRepository


EXPECTED_ALEMBIC_HEAD = "0009_sovereign_intelligence_core"
MISSION_ID = "sovereign-intelligence-core-runtime"
_SURFACE_SOURCES = ("mercadolivre_surface_probe", "mercadolivre_observation_lab")


def _assert_read_only_policy() -> None:
    if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true":
        raise RuntimeError("sovereign_core_runtime_requires_read_only")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false":
        raise RuntimeError("sovereign_core_runtime_forbids_marketplace_writes")


def _signal_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _safe_snapshot_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    allowed = {
        "price",
        "available_quantity",
        "sold_quantity",
        "visits",
        "status",
        "listing_type_id",
        "catalog_listing",
        "condition",
    }
    result: dict[str, Any] = {}
    for key in allowed:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = value
    return result


def _snapshot_signal(row: SnapshotRecord) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=_signal_id(
            row.marketplace,
            row.entity_type,
            row.entity_id,
            row.payload_hash,
            row.captured_at.isoformat(),
        ),
        marketplace=row.marketplace,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        kind=f"snapshot_{row.entity_type}",
        source="universal_sensor_snapshot",
        observed_at=row.captured_at,
        payload=_safe_snapshot_payload(row.payload),
        provenance={
            "record": "snapshots",
            "payload_hash": row.payload_hash,
            "capture": "official_read_sensor",
        },
        official_resource_fetched=True,
        confidence=0.70,
    )


def _channel_signal(row: ChannelEventRecord) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=_signal_id(
            row.marketplace,
            row.operation,
            row.dedupe_key,
            row.observed_at.isoformat(),
        ),
        marketplace=row.marketplace,
        entity_type="channel_operation",
        entity_id=row.operation[:160],
        kind=row.operation,
        source="universal_sensor_channel",
        observed_at=row.observed_at,
        payload={
            "direction": row.direction,
            "status_code": row.status_code,
            "latency_ms": row.latency_ms,
            "attempt": row.attempt,
        },
        provenance={
            "record": "channel_events",
            "dedupe_key": row.dedupe_key,
            "request_id_present": bool(row.request_id),
            "correlation_id_present": bool(row.correlation_id),
        },
        official_resource_fetched=bool(
            row.status_code is not None and 200 <= row.status_code < 300
        ),
        confidence=0.60,
    )


def _surface_signal(row: RawEventRecord) -> SignalEnvelope:
    payload = row.payload if isinstance(row.payload, dict) else {}
    if row.source == "mercadolivre_observation_lab":
        host = str(payload.get("host") or "")[:160]
        method = str(payload.get("method") or "")[:16]
        path_template = str(payload.get("path_template") or row.resource or "")[:512]
        safe_payload = {
            "host": host,
            "method": method,
            "path_template": path_template,
            "status": payload.get("status") if isinstance(payload.get("status"), int) else None,
            "request_query_keys": list(payload.get("request_query_keys") or [])[:128],
            "request_metadata": dict(payload.get("request_metadata") or {}),
            "request_body_schema": dict(payload.get("request_body_schema") or {}),
            "response_metadata": dict(payload.get("response_metadata") or {}),
            "capture_mode": "har_schema_metadata_only",
            "values_persisted": False,
        }
        material = f"{host}|{method}|{path_template}"
        official_resource_fetched = False
        confidence = 0.80
        provenance = {
            "record": "raw_events",
            "payload_hash": row.payload_hash,
            "capture": "authorized_browser_har_offline_analysis",
            "privacy_mode": "schema_metadata_only_no_values",
        }
    else:
        official_get = payload.get("official_get") is True
        resource = str(payload.get("resolved_resource") or row.resource or "")[:512]
        safe_payload = {
            "schema_fingerprint": payload.get("schema_fingerprint"),
            "schema_paths": list(payload.get("schema_paths") or [])[:512],
            "top_level_fields": list(payload.get("top_level_fields") or [])[:256],
            "topic": payload.get("topic"),
            "known_topic": payload.get("known_topic"),
            "resolution_status": payload.get("resolution_status"),
            "capture_modes": list(payload.get("capture_modes") or [])[:32],
            "resource_root": payload.get("resource_root"),
            "resource_segments": payload.get("resource_segments"),
            "official_get": official_get,
            "values_persisted": False,
        }
        material = f"{row.event_type}|{resource}"
        official_resource_fetched = official_get
        confidence = 1.0 if official_get else 0.65
        provenance = {
            "record": "raw_events",
            "payload_hash": row.payload_hash,
            "resource": resource,
            "privacy_mode": "schema_only_no_values",
        }

    return SignalEnvelope(
        signal_id=_signal_id(
            "surface",
            row.source,
            row.event_type,
            row.dedupe_key,
            row.received_at.isoformat(),
        ),
        marketplace="mercadolivre",
        entity_type="surface",
        entity_id=_signal_id(row.source, material)[:40],
        kind=row.event_type,
        source=row.source,
        observed_at=row.occurred_at or row.received_at,
        payload=safe_payload,
        provenance=provenance,
        official_resource_fetched=official_resource_fetched,
        confidence=confidence,
    )


async def _snapshot_history(
    sessions: async_sessionmaker[AsyncSession], row: SnapshotRecord, *, limit: int = 8
) -> tuple[SignalEnvelope, ...]:
    async with sessions() as session:
        rows = (
            await session.execute(
                select(SnapshotRecord)
                .where(
                    SnapshotRecord.marketplace == row.marketplace,
                    SnapshotRecord.entity_type == row.entity_type,
                    SnapshotRecord.entity_id == row.entity_id,
                    SnapshotRecord.captured_at < row.captured_at,
                )
                .order_by(desc(SnapshotRecord.captured_at))
                .limit(limit)
            )
        ).scalars().all()
    return tuple(_snapshot_signal(item) for item in reversed(rows))


async def _channel_history(
    sessions: async_sessionmaker[AsyncSession], row: ChannelEventRecord, *, limit: int = 8
) -> tuple[SignalEnvelope, ...]:
    async with sessions() as session:
        rows = (
            await session.execute(
                select(ChannelEventRecord)
                .where(
                    ChannelEventRecord.marketplace == row.marketplace,
                    ChannelEventRecord.operation == row.operation,
                    ChannelEventRecord.observed_at < row.observed_at,
                )
                .order_by(desc(ChannelEventRecord.observed_at))
                .limit(limit)
            )
        ).scalars().all()
    return tuple(_channel_signal(item) for item in reversed(rows))


async def _surface_history(
    sessions: async_sessionmaker[AsyncSession], row: RawEventRecord, *, limit: int = 8
) -> tuple[SignalEnvelope, ...]:
    async with sessions() as session:
        rows = (
            await session.execute(
                select(RawEventRecord)
                .where(
                    RawEventRecord.source == row.source,
                    RawEventRecord.event_type == row.event_type,
                    RawEventRecord.received_at < row.received_at,
                )
                .order_by(desc(RawEventRecord.received_at))
                .limit(limit)
            )
        ).scalars().all()
    return tuple(_surface_signal(item) for item in reversed(rows))


async def _investigation_for(
    sessions: async_sessionmaker[AsyncSession],
    *,
    marketplace: str,
    entity_type: str,
    entity_id: str,
) -> dict[str, Any] | None:
    async with sessions() as session:
        case = (
            await session.execute(
                select(InvestigationCaseRecord)
                .where(
                    InvestigationCaseRecord.marketplace == marketplace,
                    InvestigationCaseRecord.entity_type == entity_type,
                    InvestigationCaseRecord.entity_id == entity_id,
                )
                .order_by(desc(InvestigationCaseRecord.updated_at))
                .limit(1)
            )
        ).scalar_one_or_none()
    if case is None:
        return None
    return {
        "status_after": case.status,
        "confidence_after": case.confidence,
        "observation_count": case.observation_count,
        "hypotheses": list(case.hypotheses or []),
        "causal_claim": False,
        "evidence_summary": {
            "investigation_case_id": str(case.id),
            "anomalous_observation_count": case.anomalous_observation_count,
            "ever_confirmed": case.ever_confirmed,
            "engine_version": case.engine_version,
        },
    }


async def _persist_cognitive_report(
    *,
    report,
    repository: PostgresSovereignIntelligenceRepository,
    learning_repository: PostgresLearningRepository,
) -> bool:
    inserted = await repository.persist_report(report)
    learning_decision = SovereignLearningDecision.model_validate(report.learning)
    episode_id = await learning_repository.persist_episode(learning_decision)
    await learning_repository.ensure_promotion_candidates(
        episode_id=episode_id,
        decision=learning_decision,
    )
    return inserted


async def run_cycle(database_url: str, *, max_records: int = 32) -> dict[str, Any]:
    _assert_read_only_policy()
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    core = SovereignIntelligenceCore()
    repository = PostgresSovereignIntelligenceRepository(sessions)
    learning_repository = PostgresLearningRepository(sessions)

    try:
        if not await database_healthcheck(sessions):
            raise RuntimeError("sovereign_core_database_health_failed")
        async with sessions() as session:
            head = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            if str(head) != EXPECTED_ALEMBIC_HEAD:
                raise RuntimeError(f"sovereign_core_schema_head_mismatch:{head}")
            snapshots = (
                await session.execute(
                    select(SnapshotRecord)
                    .order_by(desc(SnapshotRecord.captured_at))
                    .limit(max_records)
                )
            ).scalars().all()
            channels = (
                await session.execute(
                    select(ChannelEventRecord)
                    .order_by(desc(ChannelEventRecord.observed_at))
                    .limit(max_records)
                )
            ).scalars().all()
            surfaces = (
                await session.execute(
                    select(RawEventRecord)
                    .where(RawEventRecord.source.in_(_SURFACE_SOURCES))
                    .order_by(desc(RawEventRecord.received_at))
                    .limit(max_records)
                )
            ).scalars().all()

        processed = inserted = validated = quarantined = audit_failures = exposure_updates = 0
        surface_signals_processed = 0
        latest_signal_id: str | None = None

        for row in reversed(snapshots):
            signal = _snapshot_signal(row)
            history = await _snapshot_history(sessions, row)
            investigation = await _investigation_for(
                sessions,
                marketplace=row.marketplace,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
            )
            report = core.process(signal, history=history, investigation=investigation)
            inserted += int(
                await _persist_cognitive_report(
                    report=report,
                    repository=repository,
                    learning_repository=learning_repository,
                )
            )
            processed += 1
            latest_signal_id = signal.signal_id
            exposure_updates += len(report.counterintelligence)
            validated += int(report.validation.state.value == "validated")
            quarantined += int(report.validation.state.value == "quarantined")
            audit_failures += int(not report.audit.passed)

        for row in reversed(channels):
            signal = _channel_signal(row)
            history = await _channel_history(sessions, row)
            report = core.process(signal, history=history)
            inserted += int(
                await _persist_cognitive_report(
                    report=report,
                    repository=repository,
                    learning_repository=learning_repository,
                )
            )
            processed += 1
            latest_signal_id = signal.signal_id
            exposure_updates += len(report.counterintelligence)
            validated += int(report.validation.state.value == "validated")
            quarantined += int(report.validation.state.value == "quarantined")
            audit_failures += int(not report.audit.passed)

        for row in reversed(surfaces):
            signal = _surface_signal(row)
            history = await _surface_history(sessions, row)
            report = core.process(signal, history=history)
            inserted += int(
                await _persist_cognitive_report(
                    report=report,
                    repository=repository,
                    learning_repository=learning_repository,
                )
            )
            processed += 1
            surface_signals_processed += 1
            latest_signal_id = signal.signal_id
            exposure_updates += len(report.counterintelligence)
            validated += int(report.validation.state.value == "validated")
            quarantined += int(report.validation.state.value == "quarantined")
            audit_failures += int(not report.audit.passed)

        await repository.save_checkpoint(
            mission_id=MISSION_ID,
            cursor={
                "latest_signal_id": latest_signal_id,
                "completed_at": datetime.now(UTC).isoformat(),
            },
            processed_count=processed,
            marketplace_writes=0,
        )

        async with sessions() as session:
            intelligence_total = int(
                (await session.execute(text("SELECT count(*) FROM sovereign_intelligence"))).scalar_one()
            )
            exposure_total = int(
                (await session.execute(text("SELECT count(*) FROM exposure_map"))).scalar_one()
            )
            learning_total = int(
                (await session.execute(text("SELECT count(*) FROM learning_episodes"))).scalar_one()
            )
            surface_total = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(RawEventRecord)
                        .where(RawEventRecord.source.in_(_SURFACE_SOURCES))
                    )
                ).scalar_one()
            )

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "core_active": True,
            "core_health": "PASS",
            "core_version": core.version,
            "radar_subsystem": True,
            "processed_this_cycle": processed,
            "surface_signals_processed_this_cycle": surface_signals_processed,
            "surface_observations_total": surface_total,
            "new_intelligence_records": inserted,
            "intelligence_records_total": intelligence_total,
            "exposure_map_records_total": exposure_total,
            "learning_episodes_total": learning_total,
            "validated_this_cycle": validated,
            "quarantined_this_cycle": quarantined,
            "cognitive_audit_failures": audit_failures,
            "exposure_assessments_this_cycle": exposure_updates,
            "marketplace_writes": 0,
            "permanent_read_only": True,
            "action_gateway_required_for_external_actions": True,
            "runtime_scope": "universal_multimarketplace",
            "alembic_head": EXPECTED_ALEMBIC_HEAD,
        }
    finally:
        await engine.dispose()


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


async def run_forever(
    database_url: str,
    *,
    status_path: Path,
    interval_seconds: float = 60.0,
    max_records: int = 32,
) -> None:
    _assert_read_only_policy()
    while True:
        try:
            status = await run_cycle(database_url, max_records=max_records)
            status["lifecycle"] = "always_on"
            status["unit_state"] = "ACTIVE"
            _write_status(status_path, status)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _write_status(
                status_path,
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "core_active": False,
                    "core_health": "FAIL",
                    "unit_state": "DEGRADED_RETRYING",
                    "permanent_read_only": True,
                    "marketplace_writes": 0,
                    "error": type(exc).__name__,
                },
            )
        await asyncio.sleep(interval_seconds)
