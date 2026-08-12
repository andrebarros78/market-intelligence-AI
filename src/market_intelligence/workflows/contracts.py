from __future__ import annotations

from typing import Any, Protocol


class WorkflowEngine(Protocol):
    async def start(self, workflow_name: str, payload: dict[str, Any], *, idempotency_key: str) -> str: ...
