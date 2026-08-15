from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.intelligence.sovereign.models import CoreCycleReport


def _hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PostgresSovereignIntelligenceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def persist_report(self, report: CoreCycleReport) -> bool:
        if report.marketplace_writes != 0 or report.action_intent.direct_marketplace_write:
            raise RuntimeError("sovereign_intelligence_persistence_write_boundary_violation")
        payload = report.model_dump(mode="json")
        dedupe_key = _hash(
            {
                "core_version": report.core_version,
                "signal_id": report.signal.signal_id,
                "knowledge_state": report.validation.state.value,
                "prediction": report.prediction.statement,
            }
        )
        inserted = False
        async with self._sessions() as session:
            result = await session.execute(
                text(
                    """
                    INSERT INTO sovereign_intelligence (
                        id, dedupe_key, marketplace, entity_type, entity_id, signal_kind,
                        knowledge_state, severity, confidence, summary, report_json, observed_at
                    ) VALUES (
                        :id, :dedupe_key, :marketplace, :entity_type, :entity_id, :signal_kind,
                        :knowledge_state, :severity, :confidence, :summary,
                        CAST(:report_json AS jsonb), :observed_at
                    )
                    ON CONFLICT (dedupe_key) DO UPDATE SET
                        confidence = GREATEST(sovereign_intelligence.confidence, EXCLUDED.confidence),
                        report_json = EXCLUDED.report_json,
                        summary = EXCLUDED.summary,
                        updated_at = now()
                    RETURNING (xmax = 0) AS inserted
                    """
                ),
                {
                    "id": uuid4(),
                    "dedupe_key": dedupe_key,
                    "marketplace": report.signal.marketplace,
                    "entity_type": report.signal.entity_type,
                    "entity_id": report.signal.entity_id,
                    "signal_kind": report.signal.kind,
                    "knowledge_state": report.validation.state.value,
                    "severity": report.intelligence.severity.value,
                    "confidence": report.validation.confidence,
                    "summary": report.intelligence.summary,
                    "report_json": json.dumps(payload, sort_keys=True, ensure_ascii=False),
                    "observed_at": report.signal.observed_at,
                },
            )
            inserted = bool(result.scalar_one())
            for exposure in report.counterintelligence:
                exposure_payload = exposure.model_dump(mode="json")
                exposure_key = _hash(
                    {
                        "marketplace": report.signal.marketplace,
                        "data_point": exposure.data_point,
                        "platform_observes": exposure.platform_observes,
                    }
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO exposure_map (
                            id, exposure_key, marketplace, data_point, platform_observes,
                            possible_inferences, risk_level, mitigation, evidence_json,
                            first_observed_at, last_observed_at
                        ) VALUES (
                            :id, :exposure_key, :marketplace, :data_point, :platform_observes,
                            CAST(:possible_inferences AS jsonb), :risk_level, :mitigation,
                            CAST(:evidence_json AS jsonb), :observed_at, :observed_at
                        )
                        ON CONFLICT (exposure_key) DO UPDATE SET
                            possible_inferences = EXCLUDED.possible_inferences,
                            risk_level = EXCLUDED.risk_level,
                            mitigation = EXCLUDED.mitigation,
                            evidence_json = EXCLUDED.evidence_json,
                            last_observed_at = GREATEST(exposure_map.last_observed_at, EXCLUDED.last_observed_at),
                            updated_at = now()
                        """
                    ),
                    {
                        "id": uuid4(),
                        "exposure_key": exposure_key,
                        "marketplace": report.signal.marketplace,
                        "data_point": exposure.data_point,
                        "platform_observes": exposure.platform_observes,
                        "possible_inferences": json.dumps(exposure_payload["possible_inferences"], ensure_ascii=False),
                        "risk_level": exposure.risk.value,
                        "mitigation": exposure.mitigation,
                        "evidence_json": json.dumps(exposure_payload["evidence"], ensure_ascii=False),
                        "observed_at": report.signal.observed_at,
                    },
                )

            audit_key = _hash(
                {
                    "signal_id": report.signal.signal_id,
                    "audit": report.audit.model_dump(mode="json"),
                    "core_version": report.core_version,
                }
            )
            await session.execute(
                text(
                    """
                    INSERT INTO cognitive_audits (
                        id, dedupe_key, signal_id, passed, audit_json
                    ) VALUES (
                        :id, :dedupe_key, :signal_id, :passed, CAST(:audit_json AS jsonb)
                    )
                    ON CONFLICT (dedupe_key) DO NOTHING
                    """
                ),
                {
                    "id": uuid4(),
                    "dedupe_key": audit_key,
                    "signal_id": report.signal.signal_id,
                    "passed": report.audit.passed,
                    "audit_json": json.dumps(report.audit.model_dump(mode="json"), ensure_ascii=False),
                },
            )
            await session.commit()
        return inserted

    async def save_checkpoint(
        self,
        *,
        mission_id: str,
        cursor: dict[str, Any],
        processed_count: int,
        marketplace_writes: int = 0,
    ) -> None:
        if marketplace_writes != 0:
            raise RuntimeError("sovereign_core_checkpoint_marketplace_write")
        async with self._sessions() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO sovereign_core_checkpoints (
                        mission_id, cursor_json, processed_count, marketplace_writes
                    ) VALUES (
                        :mission_id, CAST(:cursor_json AS jsonb), :processed_count, 0
                    )
                    ON CONFLICT (mission_id) DO UPDATE SET
                        cursor_json = EXCLUDED.cursor_json,
                        processed_count = GREATEST(
                            sovereign_core_checkpoints.processed_count,
                            EXCLUDED.processed_count
                        ),
                        marketplace_writes = 0,
                        updated_at = now()
                    """
                ),
                {
                    "mission_id": mission_id,
                    "cursor_json": json.dumps(cursor, sort_keys=True, ensure_ascii=False),
                    "processed_count": int(processed_count),
                },
            )
            await session.commit()
