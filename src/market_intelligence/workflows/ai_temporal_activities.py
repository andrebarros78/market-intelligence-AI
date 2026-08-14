from __future__ import annotations

from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.ai import (
    AI_DATA_GATEWAY,
    AIVault,
    AIDataGatewayResult,
    ProviderConfigurationError,
    ProviderManager,
    execute_minimized_inference,
)
from market_intelligence.persistence.ai_audit import PostgresAIInferenceAuditRepository
from market_intelligence.workflows.names import (
    ACTIVITY_AI_MINIMIZED_INFER,
    ACTIVITY_AI_SANDBOX_INFER,
)


_RETRYABLE_PROVIDER_ERRORS = {
    "ai_provider_connectivity_failure",
    "ai_provider_rate_limited",
}


def _validate_identity(payload: dict[str, Any]) -> tuple[str, str, str]:
    role = str(payload.get("role") or "").strip().lower()
    request_key = str(payload.get("request_key") or "").strip().lower()
    mode = str(payload.get("mode") or "").strip().lower()
    if role not in {"system", "agents"}:
        raise ApplicationError("ai_role_invalid", type="ai_role_invalid", non_retryable=True)
    if len(request_key) != 64 or any(ch not in "0123456789abcdef" for ch in request_key):
        raise ApplicationError(
            "ai_request_key_invalid",
            type="ai_request_key_invalid",
            non_retryable=True,
        )
    return role, request_key, mode


class AIInferenceActivities:
    def __init__(self, *, audit_repo: PostgresAIInferenceAuditRepository | None = None) -> None:
        self._audit_repo = audit_repo

    @activity.defn(name=ACTIVITY_AI_SANDBOX_INFER)
    async def sandbox_infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        role, request_key, mode = _validate_identity(payload)
        if mode != "sandbox":
            raise ApplicationError(
                "ai_data_gateway_required",
                type="ai_data_gateway_required",
                non_retryable=True,
            )

        try:
            config = AIVault.from_env().resolve(role=role)
            driver = ProviderManager().build(config)
            sandbox_infer = getattr(driver, "sandbox_infer", None)
            if sandbox_infer is None:
                raise ProviderConfigurationError("ai_provider_sandbox_inference_not_supported")
            result = await sandbox_infer()
        except ProviderConfigurationError as exc:
            raise ApplicationError(
                exc.code,
                type=exc.code,
                non_retryable=exc.code not in _RETRYABLE_PROVIDER_ERRORS,
            ) from exc

        public = result.model_dump(mode="json")
        public["request_key"] = request_key
        public["mode"] = "sandbox"
        return public

    @activity.defn(name=ACTIVITY_AI_MINIMIZED_INFER)
    async def minimized_infer(self, payload: dict[str, Any]) -> dict[str, Any]:
        role, request_key, mode = _validate_identity(payload)
        if mode != "minimized":
            raise ApplicationError(
                "ai_minimized_mode_required",
                type="ai_minimized_mode_required",
                non_retryable=True,
            )
        if self._audit_repo is None:
            raise ApplicationError(
                "ai_audit_repository_unavailable",
                type="ai_audit_repository_unavailable",
                non_retryable=True,
            )

        gateway_payload = payload.get("gateway_result")
        if not isinstance(gateway_payload, dict):
            raise ApplicationError(
                "ai_gateway_result_missing",
                type="ai_gateway_result_missing",
                non_retryable=True,
            )

        try:
            gateway_result = AIDataGatewayResult.model_validate(gateway_payload)
            # A direct Temporal caller must not be able to forge an attestation.
            # Re-run the allowlist/sensitive-content policy on the payload that is
            # actually present in Workflow history and require the same canonical
            # output hash/content.
            revalidated = AI_DATA_GATEWAY.minimize(
                purpose=gateway_result.purpose,
                data=gateway_result.payload,
            )
            if (
                gateway_result.policy_version != revalidated.policy_version
                or gateway_result.output_sha256 != revalidated.output_sha256
                or gateway_result.payload != revalidated.payload
                or gateway_result.credential_exposed
                or gateway_result.pii_exposed
                or not gateway_result.business_data_minimized
            ):
                raise ProviderConfigurationError("ai_gateway_attestation_invalid")
        except (ProviderConfigurationError, ValueError) as exc:
            code = getattr(exc, "code", "ai_gateway_result_invalid")
            raise ApplicationError(code, type=code, non_retryable=True) from exc

        # If Temporal retries after a completed database commit, return the already
        # validated audit instead of making another provider call.
        try:
            existing = await self._audit_repo.get_by_request_key(request_key)
        except Exception as exc:  # database lookup occurs before external inference
            raise ApplicationError(
                "ai_audit_lookup_failure",
                type="ai_audit_lookup_failure",
                non_retryable=False,
            ) from exc
        if existing is not None:
            return _public_from_audit(existing, request_key=request_key)

        try:
            config = AIVault.from_env().resolve(role=role)
            result = await execute_minimized_inference(config, gateway_result)
        except ProviderConfigurationError as exc:
            raise ApplicationError(
                exc.code,
                type=exc.code,
                non_retryable=exc.code not in _RETRYABLE_PROVIDER_ERRORS,
            ) from exc

        # A database failure after a successful external response is intentionally
        # non-retryable: retrying could duplicate billable inference in the narrow
        # response->commit crash window.
        try:
            await self._audit_repo.save_if_new(request_key=request_key, result=result)
        except Exception as exc:
            raise ApplicationError(
                "ai_audit_persistence_failure_after_inference",
                type="ai_audit_persistence_failure_after_inference",
                non_retryable=True,
            ) from exc

        public = result.model_dump(mode="json")
        public["request_key"] = request_key
        public["mode"] = "minimized"
        return public


def _public_from_audit(record: Any, *, request_key: str) -> dict[str, Any]:
    return {
        "request_key": request_key,
        "mode": "minimized",
        "role": record.role,
        "provider": record.provider,
        "model": record.model,
        "endpoint_host": record.endpoint_host,
        "purpose": record.purpose,
        "gateway_policy_version": record.gateway_policy_version,
        "gateway_output_sha256": record.gateway_output_sha256,
        "contract_version": record.contract_version,
        "prompt_sha256": record.prompt_sha256,
        "output_sha256": record.output_sha256,
        "analysis": record.response_json,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "total_tokens": record.total_tokens,
        "latency_ms": record.latency_ms,
        "store_enabled": False,
        "business_data_minimized": True,
        "credential_exposed": False,
        "pii_exposed": False,
        "reused_audit": True,
    }
