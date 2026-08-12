from __future__ import annotations

from .crypto import state_digest
from .runtime import SyntheticOAuthRuntime


async def run_synthetic_acceptance(runtime: SyntheticOAuthRuntime, *, account_id: str) -> dict[str, bool | int | str]:
    plan = await runtime.transactions.start(account_id=account_id)
    first_version = await runtime.transactions.callback(account_id=account_id, state=plan.state, code="synthetic-code")
    replay_rejected = False
    try:
        await runtime.transactions.callback(account_id=account_id, state=plan.state, code="synthetic-code")
    except PermissionError:
        replay_rejected = True
    health_before = await runtime.health.get(account_id=account_id)
    next_version = await runtime.refresh.refresh(account_id=account_id)
    health_after = await runtime.health.get(account_id=account_id)
    readiness = await runtime.readiness()
    return {
        "pkce_s256": plan.code_challenge_method == "S256",
        "state_digest_length": len(state_digest(plan.state)),
        "callback_version": first_version,
        "replay_rejected": replay_rejected,
        "health_before": health_before.status.value,
        "refresh_rotated": next_version > first_version,
        "health_after": health_after.status.value,
        "network_blocked": runtime.settings.network_blocked,
        "writes_blocked": runtime.settings.writes_blocked,
        "ready": readiness.ready,
    }
