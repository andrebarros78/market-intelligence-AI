import pytest

from market_intelligence.ai.data_gateway import AIDataGateway
from market_intelligence.ai.providers import ProviderConfigurationError


def test_gateway_keeps_only_explicit_radar_fields_and_reports_removal() -> None:
    gateway = AIDataGateway()
    result = gateway.minimize(
        purpose="radar_alert_explanation",
        data={
            "entity_type": "listing",
            "entity_alias": "listing-hash-001",
            "observed_change": "traffic_drop",
            "evidence_class": "INFERENCIA",
            "severity": "high",
            "confidence": 0.87,
            "unknown_platform_blob": {"raw": "must never leave"},
            "buyer_email": "buyer@example.com",
        },
    )

    assert result.payload == {
        "entity_type": "listing",
        "entity_alias": "listing-hash-001",
        "observed_change": "traffic_drop",
        "evidence_class": "INFERENCIA",
        "severity": "high",
        "confidence": 0.87,
    }
    assert result.removed_field_count == 2
    assert result.credential_exposed is False
    assert result.pii_exposed is False
    assert result.business_data_minimized is True
    assert result.input_sha256 != result.output_sha256


def test_gateway_blocks_sensitive_content_even_inside_allowed_field() -> None:
    gateway = AIDataGateway()
    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_sensitive_content_blocked"):
        gateway.minimize(
            purpose="synthetic_test",
            data={
                "entity_type": "listing",
                "entity_alias": "Bearer very-secret-token-value",
            },
        )

    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_sensitive_content_blocked"):
        gateway.minimize(
            purpose="synthetic_test",
            data={
                "entity_type": "listing",
                "entity_alias": "person@example.com",
            },
        )


def test_gateway_rejects_unknown_purpose_and_empty_allowed_output() -> None:
    gateway = AIDataGateway()
    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_purpose_not_allowed"):
        gateway.minimize(purpose="raw_marketplace_dump", data={"entity_type": "listing"})

    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_no_allowed_data"):
        gateway.minimize(
            purpose="synthetic_test",
            data={"access_token": "secret", "buyer": "person"},
        )


def test_gateway_rejects_nested_complex_values_in_allowed_fields() -> None:
    gateway = AIDataGateway()
    with pytest.raises(
        ProviderConfigurationError,
        match="ai_data_gateway_nested_or_complex_value_blocked",
    ):
        gateway.minimize(
            purpose="radar_alert_explanation",
            data={
                "entity_type": "listing",
                "observable_causes": [{"name": "price", "impact": 0.2}],
            },
        )


def test_gateway_accepts_bounded_scalar_lists_for_analytical_factors() -> None:
    gateway = AIDataGateway()
    result = gateway.minimize(
        purpose="radar_alert_explanation",
        data={
            "entity_type": "listing",
            "observable_causes": ["price_stable", "stock_normal"],
            "hypotheses": ["distribution_change_requires_investigation"],
        },
    )

    assert result.payload["observable_causes"] == ["price_stable", "stock_normal"]
    assert result.payload["hypotheses"] == ["distribution_change_requires_investigation"]


def test_gateway_enforces_string_list_and_total_payload_limits() -> None:
    gateway = AIDataGateway(max_bytes=80, max_string_chars=16, max_list_items=2)

    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_string_too_large"):
        gateway.minimize(
            purpose="synthetic_test",
            data={"entity_type": "x" * 17},
        )

    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_list_too_large"):
        gateway.minimize(
            purpose="radar_alert_explanation",
            data={"entity_type": "listing", "hypotheses": ["a", "b", "c"]},
        )

    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_payload_too_large"):
        gateway.minimize(
            purpose="synthetic_test",
            data={
                "entity_type": "listing",
                "entity_alias": "alias",
                "metric_name": "visits",
                "observed_value": 100,
                "expected_value": 1000,
                "deviation_percent": -90,
                "severity": "high",
            },
        )


def test_gateway_hashes_are_deterministic_and_key_order_independent() -> None:
    gateway = AIDataGateway()
    first = gateway.minimize(
        purpose="synthetic_test",
        data={"entity_type": "listing", "confidence": 0.9},
    )
    second = gateway.minimize(
        purpose="synthetic_test",
        data={"confidence": 0.9, "entity_type": "listing"},
    )

    assert first.input_sha256 == second.input_sha256
    assert first.output_sha256 == second.output_sha256


def test_gateway_rejects_non_finite_numbers() -> None:
    gateway = AIDataGateway()
    with pytest.raises(ProviderConfigurationError, match="ai_data_gateway_non_finite_number"):
        gateway.minimize(
            purpose="synthetic_test",
            data={"entity_type": "listing", "confidence": float("nan")},
        )
