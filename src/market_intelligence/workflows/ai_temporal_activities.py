from __future__ import annotations

from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from market_intelligence.ai import AIVault, ProviderConfigurationError, ProviderManager
from market_intelligence.workflows.names import ACTIVITY_AI_SANDBOX_INFER


_RETRYABLE_PROVIDER_ERRORS = {
    "ai_provider_connectivity_failure",
    "ai_provider_rate_limited",
}


class AIInferenceActivities:
    @activity.defn(name=ACTIVITY_AI_SANDBOX_INFER)
    async def sandbox_infer(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        # No prompt, provider response text, credential, Authorization header, or
        # original request id is returned into Workflow history.
        return public
