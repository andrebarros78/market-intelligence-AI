from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from market_intelligence.ai.data_gateway import AI_DATA_GATEWAY_VERSION, AIDataGatewayResult
from market_intelligence.ai.providers import ProviderConfigurationError


AI_INFERENCE_CONTRACT_VERSION = "ai-minimized-inference@1.0.0"
AI_INFERENCE_MAX_OUTPUT_TOKENS = 384
AI_INFERENCE_MAX_PROMPT_BYTES = 12_288

_EVIDENCE_CLASSES = {"FATO", "INFERENCIA", "HIPOTESE"}
_SENSITIVE_OUTPUT_RE = re.compile(
    r"(?i)(?:\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|"
    r"\bsk-[A-Za-z0-9_-]{12,}|"
    r"\bAIza[A-Za-z0-9_-]{20,}|"
    r"\beyJ[A-Za-z0-9_-]{16,}\.)"
)


class AIInferencePromptEnvelope(BaseModel):
    contract_version: str
    gateway_policy_version: str
    purpose: str
    gateway_output_sha256: str
    prompt: str
    prompt_sha256: str
    max_output_tokens: int
    temperature: float
    store: bool


class AIAnalysisResponse(BaseModel):
    summary: str = Field(min_length=1, max_length=1500)
    evidence_class: Literal["FATO", "INFERENCIA", "HIPOTESE"]
    recommendations: list[str] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list, max_length=5)
    causal_claim: Literal[False]


_FIXED_SYSTEM_INSTRUCTIONS = """You are an analytical assistant inside Market Intelligence IA.
Use only the MINIMIZED_DATA JSON supplied below.
Do not invent marketplace facts, internal algorithm intent, hidden penalties, shadow bans, buyer identities, credentials, or personal data.
Preserve epistemic discipline: FATO is directly observed; INFERENCIA is derived; HIPOTESE is unconfirmed.
The response evidence_class MUST equal the source evidence_class when it is supplied.
Return ONLY one JSON object with exactly these semantic fields:
summary: concise explanation grounded in the supplied data;
evidence_class: FATO, INFERENCIA, or HIPOTESE;
recommendations: array with at most 5 human actions;
limitations: array with at most 5 limitations or missing-evidence notes;
causal_claim: false.
Never claim a specific internal Mercado Livre cause unless directly present as a FATO in the supplied data.
"""


def build_minimized_inference_prompt(
    gateway_result: AIDataGatewayResult,
) -> AIInferencePromptEnvelope:
    if gateway_result.policy_version != AI_DATA_GATEWAY_VERSION:
        raise ProviderConfigurationError("ai_inference_gateway_policy_not_trusted")
    if gateway_result.credential_exposed or gateway_result.pii_exposed:
        raise ProviderConfigurationError("ai_inference_gateway_attestation_failed")
    if not gateway_result.business_data_minimized:
        raise ProviderConfigurationError("ai_inference_gateway_attestation_failed")
    if not gateway_result.payload:
        raise ProviderConfigurationError("ai_inference_gateway_payload_empty")

    source_evidence = gateway_result.payload.get("evidence_class")
    if source_evidence is not None and str(source_evidence).upper() not in _EVIDENCE_CLASSES:
        raise ProviderConfigurationError("ai_inference_evidence_class_invalid")

    minimized_json = json.dumps(
        gateway_result.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    prompt = (
        _FIXED_SYSTEM_INSTRUCTIONS
        + "\nCONTRACT_VERSION: "
        + AI_INFERENCE_CONTRACT_VERSION
        + "\nPURPOSE: "
        + gateway_result.purpose
        + "\nMINIMIZED_DATA_SHA256: "
        + gateway_result.output_sha256
        + "\nMINIMIZED_DATA:\n"
        + minimized_json
    )
    encoded = prompt.encode("utf-8")
    if len(encoded) > AI_INFERENCE_MAX_PROMPT_BYTES:
        raise ProviderConfigurationError("ai_inference_prompt_too_large")

    return AIInferencePromptEnvelope(
        contract_version=AI_INFERENCE_CONTRACT_VERSION,
        gateway_policy_version=gateway_result.policy_version,
        purpose=gateway_result.purpose,
        gateway_output_sha256=gateway_result.output_sha256,
        prompt=prompt,
        prompt_sha256=hashlib.sha256(encoded).hexdigest(),
        max_output_tokens=AI_INFERENCE_MAX_OUTPUT_TOKENS,
        temperature=0.0,
        store=False,
    )


def parse_minimized_ai_response(
    raw_text: str,
    *,
    source_gateway: AIDataGatewayResult,
) -> AIAnalysisResponse:
    text = raw_text.strip()
    if not text:
        raise ProviderConfigurationError("ai_inference_response_empty")
    if len(text) > 8_192:
        raise ProviderConfigurationError("ai_inference_response_too_large")
    if _SENSITIVE_OUTPUT_RE.search(text):
        raise ProviderConfigurationError("ai_inference_sensitive_output_blocked")

    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderConfigurationError("ai_inference_response_not_json") from exc
    if not isinstance(payload, dict):
        raise ProviderConfigurationError("ai_inference_response_not_object")
    if set(payload) != {
        "summary",
        "evidence_class",
        "recommendations",
        "limitations",
        "causal_claim",
    }:
        raise ProviderConfigurationError("ai_inference_response_schema_invalid")

    try:
        response = AIAnalysisResponse.model_validate(payload)
    except ValidationError as exc:
        raise ProviderConfigurationError("ai_inference_response_schema_invalid") from exc

    source_class = source_gateway.payload.get("evidence_class")
    if source_class is not None and response.evidence_class != str(source_class).upper():
        raise ProviderConfigurationError("ai_inference_evidence_class_changed")

    for value in [response.summary, *response.recommendations, *response.limitations]:
        if _SENSITIVE_OUTPUT_RE.search(value):
            raise ProviderConfigurationError("ai_inference_sensitive_output_blocked")
    return response
