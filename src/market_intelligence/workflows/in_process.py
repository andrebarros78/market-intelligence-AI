from __future__ import annotations

import hashlib
import json
from typing import Any


class InProcessWorkflowEngine:
    """Sandbox-only workflow engine. Production implementation is Temporal."""

    def __init__(self) -> None:
        self.started: dict[str, dict[str, Any]] = {}

    async def start(self, workflow_name: str, payload: dict[str, Any], *, idempotency_key: str) -> str:
        material = json.dumps({"workflow": workflow_name, "key": idempotency_key}, sort_keys=True).encode("utf-8")
        workflow_id = hashlib.sha256(material).hexdigest()[:24]
        self.started.setdefault(workflow_id, dict(payload))
        return workflow_id
