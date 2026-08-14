import json

import pytest

from market_intelligence.ai.data_gateway import AIDataGateway, AIDataGatewayResult
from market_intelligence.ai.inference_contract import (
    AI_INFERENCE_CONTRACT_VERSION,
    build_minimized_inference_prompt,
    parse_minimized_ai_response,
)
from market_intelligence.ai.providers import ProviderConfigurationError


def _gateway_result(evidence_class: str = "INFERENCIA"):
    return AIDataGateway().minimize(
        purpose="radar_alert_explanation",
        data={
            "entity_type": "listing",
            "entity_alias": "listing-hash-01",
            "observed_change": "traffic_drop",
            "evidence_class": evidence_class,
            "severity": "high",
            "confidence": 0.88,
            "observed_value": 680,
            "expected_value": 2500,
            "deviation_percent": -72.8,
            "hypotheses": ["distribution_change_requires_investigation"],
        },
    )


def test_prompt_is_deterministic_contains_only_minimized_payload_and_fixed_policy() -> None:
    source = _gateway_result()
    first = build_minimized_inference_prompt(source)
    second = build_minimized_inference_prompt(source)

    assert first.contract_version == AI_INFERENCE_CONTRACT_VERSION
    assert first.prompt == second.prompt
    assert first.prompt_sha256 == second.prompt_sha256
    assert first.gateway_output_sha256 == source.output_sha256
    assert first.store is False
    assert first.temperature == 0.0
    assert first.max_output_tokens == 384
    assert "listing-hash-01" in first.prompt
    assert "traffic_drop" in first.prompt
    assert "Authorization" not in first.prompt
    assert "buyer" not in first.prompt.lower()


def test_prompt_rejects_untrusted_or_failed_gateway_attestation() -> None:
    source = _gateway_result()
    untrusted = source.model_copy(update={"policy_version": "unknown@9"})
    with pytest.raises(ProviderConfigurationError, match="ai_inference_gateway_policy_not_trusted"):
        build_minimized_inference_prompt(untrusted)

    exposed = source.model_copy(update={"pii_exposed": True})
    with pytest.raises(ProviderConfigurationError, match="ai_inference_gateway_attestation_failed"):
        build_minimized_inference_prompt(exposed)


def test_parse_accepts_exact_structured_noncausal_response() -> None:
    source = _gateway_result("INFERENCIA")
    response = parse_minimized_ai_response(
        json.dumps(
            {
                "summary": "A queda observada permanece parcialmente sem explicação suficiente.",
                "evidence_class": "INFERENCIA",
                "recommendations": ["Comparar anúncios de controle no mesmo período."],
                "limitations": ["A causa interna específica da plataforma não foi observada."],
                "causal_claim": False,
            }
        ),
        source_gateway=source,
    )

    assert response.evidence_class == "INFERENCIA"
    assert response.causal_claim is False
    assert len(response.recommendations) == 1


def test_parse_blocks_evidence_upgrade_or_change() -> None:
    source = _gateway_result("HIPOTESE")
    with pytest.raises(ProviderConfigurationError, match="ai_inference_evidence_class_changed"):
        parse_minimized_ai_response(
            json.dumps(
                {
                    "summary": "Conclusão mais forte que a fonte.",
                    "evidence_class": "FATO",
                    "recommendations": [],
                    "limitations": [],
                    "causal_claim": False,
                }
            ),
            source_gateway=source,
        )


def test_parse_requires_exact_schema_and_causal_claim_false() -> None:
    source = _gateway_result()
    with pytest.raises(ProviderConfigurationError, match="ai_inference_response_schema_invalid"):
        parse_minimized_ai_response(
            json.dumps(
                {
                    "summary": "text",
                    "evidence_class": "INFERENCIA",
                    "recommendations": [],
                    "limitations": [],
                    "causal_claim": True,
                }
            ),
            source_gateway=source,
        )

    with pytest.raises(ProviderConfigurationError, match="ai_inference_response_schema_invalid"):
        parse_minimized_ai_response(
            json.dumps(
                {
                    "summary": "text",
                    "evidence_class": "INFERENCIA",
                    "recommendations": [],
                    "limitations": [],
                    "causal_claim": False,
                    "raw_provider_data": "forbidden",
                }
            ),
            source_gateway=source,
        )


def test_parse_blocks_sensitive_material_in_model_output() -> None:
    source = _gateway_result()
    with pytest.raises(ProviderConfigurationError, match="ai_inference_sensitive_output_blocked"):
        parse_minimized_ai_response(
            json.dumps(
                {
                    "summary": "Contact person@example.com",
                    "evidence_class": "INFERENCIA",
                    "recommendations": [],
                    "limitations": [],
                    "causal_claim": False,
                }
            ),
            source_gateway=source,
        )


def test_prompt_rejects_invalid_source_evidence_class() -> None:
    source = _gateway_result()
    invalid = AIDataGatewayResult.model_validate(
        {
            **source.model_dump(),
            "payload": {**source.payload, "evidence_class": "CERTEZA"},
        }
    )
    with pytest.raises(ProviderConfigurationError, match="ai_inference_evidence_class_invalid"):
        build_minimized_inference_prompt(invalid)
