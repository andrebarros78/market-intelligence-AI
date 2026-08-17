from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.radar.alerts import alert_from_finding
from market_intelligence.intelligence.radar.factory import build_default_radar
from market_intelligence.intelligence.radar.models import RadarObservation
from market_intelligence.persistence.database import create_database_engine, create_session_factory
from market_intelligence.persistence.models import (
    ChannelEventRecord,
    EvidenceRecord,
    RawEventRecord,
    SnapshotRecord,
)
from market_intelligence.persistence.postgresql import PostgresAlertRepository, database_healthcheck
from market_intelligence.skills import SKILL_REGISTRY, bootstrap_skill_registry
from market_intelligence.skills.evidence_feed import ValidatedMarketplaceEvidence
from market_intelligence.skills.executor import execute_validated_evidence
from market_intelligence.skills.registry import SkillLicenseStatus

EXPECTED_ALEMBIC_HEAD = "0013_semantic_prediction"
_VALIDATED_SOURCE = "official_api_get_plus_webhook"
_NUMERIC_METRICS = ("visits", "sold_quantity", "available_quantity", "price")


def _assert_read_only_policy() -> None:
    if os.getenv("MI_READ_ONLY", "true").strip().lower() != "true":
        raise RuntimeError("radar_runtime_requires_read_only")
    if os.getenv("MI_ALLOW_MARKETPLACE_WRITES", "false").strip().lower() != "false":
        raise RuntimeError("radar_runtime_forbids_marketplace_writes")


def _validated_record(record: EvidenceRecord) -> ValidatedMarketplaceEvidence | None:
    attrs = record.attributes if isinstance(record.attributes, dict) else {}
    if record.level != "fact" or record.source != _VALIDATED_SOURCE:
        return None
    if attrs.get("classification") != "FATO":
        return None
    if attrs.get("webhook_validated") is not True:
        return None
    if attrs.get("official_get_validated") is not True:
        return None
    proof_id = str(attrs.get("proof_id") or "").strip()
    if not proof_id:
        return None
    payload = dict(attrs)
    payload["proof_id"] = proof_id
    return ValidatedMarketplaceEvidence(
        marketplace=record.marketplace,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        observed_at=record.observed_at,
        statement=record.statement,
        evidence=payload,
        source=record.source,
    )


def _numeric_payload(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    result: dict[str, float] = {}
    for key in _NUMERIC_METRICS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            result[key] = float(value)
    return result


async def _snapshots_for_entity(
    sessions: async_sessionmaker[AsyncSession],
    *,
    marketplace: str,
    entity_type: str,
    entity_id: str,
    limit: int = 64,
) -> list[SnapshotRecord]:
    async with sessions() as session:
        rows = (
            await session.execute(
                select(SnapshotRecord)
                .where(
                    SnapshotRecord.marketplace == marketplace,
                    SnapshotRecord.entity_type == entity_type,
                    SnapshotRecord.entity_id == entity_id,
                )
                .order_by(SnapshotRecord.captured_at.asc())
                .limit(limit)
            )
        ).scalars().all()
    return list(rows)


async def _evaluate_validated_entity(
    sessions: async_sessionmaker[AsyncSession],
    evidence: ValidatedMarketplaceEvidence,
) -> tuple[bool, bool]:
    snapshots = await _snapshots_for_entity(
        sessions,
        marketplace=evidence.marketplace,
        entity_type=evidence.entity_type,
        entity_id=evidence.entity_id,
    )
    if not snapshots:
        return False, False
    current = _numeric_payload(snapshots[-1].payload)
    if not current:
        return False, False
    history: dict[str, list[float]] = defaultdict(list)
    for snapshot in snapshots[:-1]:
        for key, value in _numeric_payload(snapshot.payload).items():
            history[key].append(value)
    observation = RadarObservation(
        entity_id=evidence.entity_id,
        observed_at=evidence.observed_at,
        metrics=current,
        history=dict(history),
        context={
            "validated_evidence": True,
            "validated_source": evidence.source,
            "proof_id": evidence.evidence["proof_id"],
            "detector_version": "radar-runtime-readonly@1",
        },
    )
    finding = build_default_radar().evaluate(observation)
    alert = alert_from_finding(
        finding=finding,
        marketplace=evidence.marketplace,
        entity_type=evidence.entity_type,
        observed_at=evidence.observed_at,
        context=observation.context,
    )
    if alert is None:
        return True, False
    return True, await PostgresAlertRepository(sessions).save_if_new(alert)


async def run_cycle(database_url: str) -> dict[str, Any]:
    _assert_read_only_policy()
    bootstrap_skill_registry(SKILL_REGISTRY)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    try:
        if not await database_healthcheck(sessions):
            raise RuntimeError("radar_database_health_failed")
        async with sessions() as session:
            head = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            if str(head) != EXPECTED_ALEMBIC_HEAD:
                raise RuntimeError(f"radar_schema_head_mismatch:{head}")
            raw_count = int(
                (await session.execute(select(func.count()).select_from(RawEventRecord))).scalar_one()
            )
            rows = (
                await session.execute(
                    select(EvidenceRecord)
                    .order_by(EvidenceRecord.observed_at.desc())
                    .limit(500)
                )
            ).scalars().all()
            channel_count = int(
                (await session.execute(select(func.count()).select_from(ChannelEventRecord))).scalar_one()
            )
            channel_marketplaces = tuple(
                sorted(
                    str(value)
                    for value in (
                        await session.execute(
                            select(ChannelEventRecord.marketplace).distinct()
                        )
                    ).scalars().all()
                    if value
                )
            )

        validated = [item for row in rows if (item := _validated_record(row)) is not None]
        insight_count = 0
        alerts_inserted = 0
        radar_entities_evaluated = 0
        for evidence in validated:
            radar_evaluated, alert_inserted = await _evaluate_validated_entity(sessions, evidence)
            if radar_evaluated:
                radar_entities_evaluated += 1
            if alert_inserted:
                alerts_inserted += 1
            insight_count += len(execute_validated_evidence(evidence))

        skills = SKILL_REGISTRY.all()
        executable = [item for item in skills if item.executable]
        proprietary_executable = sum(
            1 for item in executable if item.license_status is SkillLicenseStatus.PROPRIETARY
        )
        quarantine_executable = sum(
            1 for item in executable if item.license_status is SkillLicenseStatus.QUARANTINE
        )
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "radar_active": True,
            "radar_health": "PASS",
            "radar_database": "PROVEN",
            "radar_read_only": True,
            "skills_active": True,
            "skills_approved_active": len(executable),
            "skills_registry_nonempty": bool(skills),
            "proprietary_executable": proprietary_executable,
            "quarantine_executable": quarantine_executable,
            "validated_evidence_seen": len(validated),
            "skill_insights_generated": insight_count,
            "radar_entities_evaluated": radar_entities_evaluated,
            "radar_alerts_inserted": alerts_inserted,
            "raw_events_observed_not_promoted": raw_count,
            "channel_events_observed": channel_count,
            "channel_marketplaces_observed": list(channel_marketplaces),
            "runtime_scope": "universal_multimarketplace",
            "permanent_read_only": True,
            "permanent_marketplace_writes": False,
            "new_marketplace_write_executed": False,
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
    interval_seconds: float = 30.0,
    status_enricher: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    _assert_read_only_policy()
    while True:
        try:
            status = await run_cycle(database_url)
            status["unit_state"] = (
                "ACTIVE" if status["validated_evidence_seen"] else "ACTIVE_IDLE"
            )
            status["internal_executor_state"] = "RUNNING"
            if status_enricher is not None:
                status = status_enricher(status)
            _write_status(status_path, status)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # fail observable, keep retrying read-only health
            _write_status(
                status_path,
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "radar_active": False,
                    "radar_health": "FAIL",
                    "radar_database": "FAILED",
                    "radar_read_only": True,
                    "skills_active": False,
                    "permanent_read_only": True,
                    "permanent_marketplace_writes": False,
                    "new_marketplace_write_executed": False,
                    "unit_state": "DEGRADED_RETRYING",
                    "internal_executor_state": "RETRYING",
                    "error": type(exc).__name__,
                },
            )
        await asyncio.sleep(interval_seconds)
