from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import BaseModel

from market_intelligence.ai.providers import ProviderConfigurationError


AI_DATA_GATEWAY_VERSION = "ai-data-gateway@1.0.0"
AI_DATA_GATEWAY_MAX_BYTES = 8192
AI_DATA_GATEWAY_MAX_STRING_CHARS = 512
AI_DATA_GATEWAY_MAX_LIST_ITEMS = 50


# Explicit purpose contracts. Unknown fields are discarded rather than recursively
# redacted. This keeps external AI input on an allowlist instead of attempting to
# guess which fields in a raw marketplace object might be sensitive.
_PURPOSE_FIELDS: dict[str, frozenset[str]] = {
    "radar_alert_explanation": frozenset(
        {
            "entity_type",
            "entity_alias",
            "period_start",
            "period_end",
            "observed_change",
            "evidence_class",
            "severity",
            "estimated_impact",
            "confidence",
            "observable_causes",
            "unexplained_residual",
            "control_comparison",
            "hypotheses",
            "recommendation",
            "detector_version",
            "metric_name",
            "observed_value",
            "expected_value",
            "deviation_percent",
            "sample_size",
            "data_freshness_seconds",
        }
    ),
    "radar_investigation_summary": frozenset(
        {
            "entity_type",
            "entity_alias",
            "period_start",
            "period_end",
            "investigation_stage",
            "evidence_class",
            "severity",
            "confidence",
            "observable_causes",
            "unexplained_residual",
            "control_comparison",
            "hypotheses",
            "recommended_next_step",
            "detector_version",
            "case_age_seconds",
            "observation_count",
            "data_freshness_seconds",
        }
    ),
    "synthetic_test": frozenset(
        {
            "entity_type",
            "entity_alias",
            "metric_name",
            "observed_value",
            "expected_value",
            "deviation_percent",
            "evidence_class",
            "severity",
            "confidence",
        }
    ),
}

# These names are forbidden even if a future purpose accidentally attempts to add
# them. The allowlist and denylist are independent defenses.
_BLOCKED_KEY_FRAGMENTS = (
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "private_key",
    "service_account",
    "email",
    "phone",
    "telephone",
    "cpf",
    "cnpj",
    "document",
    "address",
    "street",
    "zipcode",
    "postal",
    "buyer",
    "seller_name",
    "first_name",
    "last_name",
    "nickname",
    "message_text",
    "question_text",
    "tracking_number",
    "access_code",
)

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET_PREFIX_RE = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{12,}|\bAIza[A-Za-z0-9_-]{20,}|\beyJ[A-Za-z0-9_-]{16,}\.)"
)


class AIDataGatewayResult(BaseModel):
    policy_version: str
    purpose: str
    sensitivity: str
    payload: dict[str, Any]
    input_sha256: str
    output_sha256: str
    input_field_count: int
    output_field_count: int
    removed_field_count: int
    credential_exposed: bool = False
    pii_exposed: bool = False
    business_data_minimized: bool = True


@dataclass(frozen=True, slots=True)
class AIDataGateway:
    version: str = AI_DATA_GATEWAY_VERSION
    max_bytes: int = AI_DATA_GATEWAY_MAX_BYTES
    max_string_chars: int = AI_DATA_GATEWAY_MAX_STRING_CHARS
    max_list_items: int = AI_DATA_GATEWAY_MAX_LIST_ITEMS

    @property
    def supported_purposes(self) -> tuple[str, ...]:
        return tuple(sorted(_PURPOSE_FIELDS))

    def minimize(self, *, purpose: str, data: Mapping[str, Any]) -> AIDataGatewayResult:
        normalized_purpose = purpose.strip().lower()
        allowed = _PURPOSE_FIELDS.get(normalized_purpose)
        if allowed is None:
            raise ProviderConfigurationError("ai_data_gateway_purpose_not_allowed")
        if not isinstance(data, Mapping):
            raise ProviderConfigurationError("ai_data_gateway_payload_invalid")

        input_hash = _hash_mapping(data)
        sanitized: dict[str, Any] = {}
        input_field_count = len(data)
        removed = 0

        for raw_key, raw_value in data.items():
            key = str(raw_key).strip()
            lowered = key.lower()
            if not key or _is_blocked_key(lowered) or lowered not in allowed:
                removed += 1
                continue
            sanitized[lowered] = self._sanitize_allowed_value(raw_value)

        if not sanitized:
            raise ProviderConfigurationError("ai_data_gateway_no_allowed_data")

        encoded = _canonical_json(sanitized).encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise ProviderConfigurationError("ai_data_gateway_payload_too_large")

        return AIDataGatewayResult(
            policy_version=self.version,
            purpose=normalized_purpose,
            sensitivity="minimized_business_analytics",
            payload=sanitized,
            input_sha256=input_hash,
            output_sha256=hashlib.sha256(encoded).hexdigest(),
            input_field_count=input_field_count,
            output_field_count=len(sanitized),
            removed_field_count=removed,
            credential_exposed=False,
            pii_exposed=False,
            business_data_minimized=True,
        )

    def _sanitize_allowed_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            if value != value or value in {float("inf"), float("-inf")}:
                raise ProviderConfigurationError("ai_data_gateway_non_finite_number")
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if len(normalized) > self.max_string_chars:
                raise ProviderConfigurationError("ai_data_gateway_string_too_large")
            if _contains_sensitive_text(normalized):
                raise ProviderConfigurationError("ai_data_gateway_sensitive_content_blocked")
            return normalized
        if isinstance(value, (list, tuple)):
            if len(value) > self.max_list_items:
                raise ProviderConfigurationError("ai_data_gateway_list_too_large")
            return [self._sanitize_allowed_scalar(item) for item in value]
        # Nested dictionaries and arbitrary objects are deliberately rejected in an
        # allowed field. Callers must derive a flat analytical contract first.
        raise ProviderConfigurationError("ai_data_gateway_nested_or_complex_value_blocked")

    def _sanitize_allowed_scalar(self, value: Any) -> Any:
        if isinstance(value, (dict, list, tuple, set)):
            raise ProviderConfigurationError("ai_data_gateway_nested_or_complex_value_blocked")
        return self._sanitize_allowed_value(value)


def _is_blocked_key(lowered: str) -> bool:
    compact = lowered.replace("-", "_").replace(" ", "_")
    return any(fragment in compact for fragment in _BLOCKED_KEY_FRAGMENTS)


def _contains_sensitive_text(value: str) -> bool:
    return bool(
        _EMAIL_RE.search(value)
        or _BEARER_RE.search(value)
        or _SECRET_PREFIX_RE.search(value)
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_safe_json_fallback,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProviderConfigurationError("ai_data_gateway_payload_invalid") from exc


def _safe_json_fallback(value: Any) -> str:
    # Do not stringify arbitrary object contents into hashes/loggable output.
    return f"<{type(value).__name__}>"


def _hash_mapping(data: Mapping[str, Any]) -> str:
    rendered = _canonical_json(dict(data)).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


AI_DATA_GATEWAY = AIDataGateway()
