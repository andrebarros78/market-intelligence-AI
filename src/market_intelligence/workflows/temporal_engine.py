from __future__ import annotations

import hashlib
from typing import Any

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError


def deterministic_workflow_id(workflow_name: str, idempotency_key: str) -> str:
    if not workflow_name or not idempotency_key:
        raise ValueError("workflow_name and idempotency_key are required")
    material = f"{workflow_name}\x1f{idempotency_key}".encode("utf-8")
    return f"mi-{hashlib.sha256(material).hexdigest()[:40]}"


class TemporalWorkflowEngine:
    def __init__(self, client: Client, *, task_queue: str) -> None:
        if not task_queue:
            raise ValueError("task_queue is required")
        self._client = client
        self._task_queue = task_queue

    @classmethod
    async def connect(
        cls,
        *,
        target: str,
        namespace: str,
        task_queue: str,
        tls: bool = False,
    ) -> "TemporalWorkflowEngine":
        client = await Client.connect(target, namespace=namespace, tls=tls)
        return cls(client, task_queue=task_queue)

    async def start(
        self,
        workflow_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> str:
        workflow_id = deterministic_workflow_id(workflow_name, idempotency_key)
        try:
            await self._client.start_workflow(
                workflow_name,
                payload,
                id=workflow_id,
                task_queue=self._task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowAlreadyStartedError:
            pass
        return workflow_id
