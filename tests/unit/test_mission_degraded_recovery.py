from __future__ import annotations

import asyncio

from market_intelligence.missions.orchestrator import SovereignMissionOrchestrator


class _Repo:
    def __init__(self) -> None:
        self.transitions: list[tuple[str, str, str, dict]] = []

    async def transition(self, mission_id: str, from_state: str, to_state: str, checkpoint: dict) -> bool:
        self.transitions.append((mission_id, from_state, to_state, checkpoint))
        return True


def test_degraded_mission_recovers_to_collecting(monkeypatch) -> None:
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    monkeypatch.setenv("MARKETPLACE_WRITES", "0")
    repo = _Repo()
    orchestrator = object.__new__(SovereignMissionOrchestrator)
    orchestrator.repo = repo
    mission = {
        "mission_id": "MI-RECOVERY-TEST",
        "status": "DEGRADED",
        "checkpoint": {"last_safe_state": "COLLECTING", "marketplace_writes": 0},
    }

    asyncio.run(orchestrator.advance(mission))

    assert len(repo.transitions) == 1
    mission_id, from_state, to_state, checkpoint = repo.transitions[0]
    assert mission_id == "MI-RECOVERY-TEST"
    assert from_state == "DEGRADED"
    assert to_state == "COLLECTING"
    assert checkpoint["last_safe_state"] == "DEGRADED"
    assert checkpoint["marketplace_writes"] == 0