from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from market_intelligence.ai.minimized_runtime import AIMinimizedInferenceResult
from market_intelligence.persistence.ai_models import AIInferenceAuditRecord


class PostgresAIInferenceAuditRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save_if_new(
        self,
        *,
        request_key: str,
        result: AIMinimizedInferenceResult,
    ) -> bool:
        if len(request_key) != 64 or any(ch not in "0123456789abcdef" for ch in request_key):
            raise ValueError("ai_request_key_invalid")
        if result.store_enabled:
            raise ValueError("ai_audit_store_enabled_forbidden")
        if not result.business_data_minimized:
            raise ValueError("ai_audit_non_minimized_payload_forbidden")
        if result.credential_exposed or result.pii_exposed or result.analysis.causal_claim:
            raise ValueError("ai_audit_safety_attestation_failed")

        statement = (
            pg_insert(AIInferenceAuditRecord)
            .values(
                request_key=request_key,
                role=result.role,
                provider=result.provider,
                model=result.model,
                endpoint_host=result.endpoint_host,
                purpose=result.purpose,
                gateway_policy_version=result.gateway_policy_version,
                gateway_output_sha256=result.gateway_output_sha256,
                contract_version=result.contract_version,
                prompt_sha256=result.prompt_sha256,
                output_sha256=result.output_sha256,
                evidence_class=result.analysis.evidence_class,
                response_json=result.analysis.model_dump(mode="json"),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
            )
            .on_conflict_do_nothing(constraint="uq_ai_inference_audits_request_key")
            .returning(AIInferenceAuditRecord.id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalar_one_or_none() is not None

    async def get_by_request_key(self, request_key: str) -> AIInferenceAuditRecord | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(AIInferenceAuditRecord).where(
                    AIInferenceAuditRecord.request_key == request_key
                )
            )
            return result.scalar_one_or_none()
