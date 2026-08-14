from __future__ import annotations

import asyncio
import hashlib
import os
from uuid import uuid4

import pytest

from market_intelligence.ai.inference_contract import AIAnalysisResponse
from market_intelligence.ai.minimized_runtime import AIMinimizedInferenceResult
from market_intelligence.persistence.ai_audit import PostgresAIInferenceAuditRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory


@pytest.mark.postgres
def test_ai_inference_audit_is_idempotent_and_stores_only_validated_provenance() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")

    async def scenario() -> None:
        engine = create_database_engine(url)
        sessions = create_session_factory(engine)
        request_key = hashlib.sha256(f"ai-audit-{uuid4().hex}".encode()).hexdigest()
        result = AIMinimizedInferenceResult(
            role="system",
            provider="openai",
            model="gpt-5-mini",
            endpoint_host="api.openai.com",
            purpose="radar_alert_explanation",
            gateway_policy_version="ai-data-gateway@1.0.0",
            gateway_output_sha256="a" * 64,
            contract_version="ai-minimized-inference@1.0.0",
            prompt_sha256="b" * 64,
            output_sha256="c" * 64,
            output_length_chars=120,
            analysis=AIAnalysisResponse(
                summary="Queda observada ainda exige investigação por controles adicionais.",
                evidence_class="INFERENCIA",
                recommendations=["Comparar controles equivalentes."],
                limitations=["Causa interna específica não observada."],
                causal_claim=False,
            ),
            input_tokens=100,
            output_tokens=40,
            total_tokens=140,
            latency_ms=321,
            store_enabled=False,
            business_data_minimized=True,
            credential_exposed=False,
            pii_exposed=False,
        )
        repo = PostgresAIInferenceAuditRepository(sessions)
        try:
            assert await repo.save_if_new(request_key=request_key, result=result) is True
            assert await repo.save_if_new(request_key=request_key, result=result) is False
            stored = await repo.get_by_request_key(request_key)
            assert stored is not None
            assert stored.provider == "openai"
            assert stored.model == "gpt-5-mini"
            assert stored.evidence_class == "INFERENCIA"
            assert stored.response_json["causal_claim"] is False
            assert stored.response_json["summary"] == result.analysis.summary
            rendered = repr(stored.response_json)
            assert "Authorization" not in rendered
            assert "api_key" not in rendered.lower()
            assert stored.input_tokens == 100
            assert stored.total_tokens == 140
        finally:
            await engine.dispose()

    asyncio.run(scenario())
