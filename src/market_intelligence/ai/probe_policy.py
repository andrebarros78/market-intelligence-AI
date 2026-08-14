from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProbeDecision:
    status: str
    exit_code: int


def classify_probe_result(
    *,
    authenticated: bool,
    model_available: bool,
    allow_model_unlisted: bool,
) -> ProbeDecision:
    """Classify a provider probe without inventing model availability.

    Some provider catalog endpoints are not authoritative for every model tier.
    When `allow_model_unlisted` is explicitly enabled, successful authentication
    remains a pass while the output continues to report `model_available=false`.
    """

    if authenticated and model_available:
        return ProbeDecision(status="ok", exit_code=0)
    if authenticated and allow_model_unlisted:
        return ProbeDecision(status="authenticated_model_unlisted", exit_code=0)
    return ProbeDecision(status="model_unavailable", exit_code=3)
