from __future__ import annotations

import os
from fastapi.testclient import TestClient

from scripts.run_sovereign_mission_orchestrator import build_app


def test_mission_api_contract(tmp_path, monkeypatch) -> None:
    url=os.getenv("TEST_DATABASE_URL")
    if not url: return
    monkeypatch.setenv("MI_READ_ONLY","true"); monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES","false"); monkeypatch.setenv("MARKETPLACE_WRITES","0")
    token_path=tmp_path/"token.txt"; app=build_app(url,tmp_path,token_path,0.01); token=token_path.read_text().strip(); headers={"Authorization":f"Bearer {token}"}
    with TestClient(app) as client:
        assert client.get("/v1/mission-system/health").status_code==401
        health=client.get("/v1/mission-system/health",headers=headers); assert health.status_code==200 and health.json()["marketplace_writes"]==0
        created=client.post("/v1/missions",headers=headers,json={"objective":"API directed mission contract proof in read-only mode.","origin":"GPT","mission_type":"DIRECTED","marketplace_scope":["mercadolivre"],"authority":"owner_read_only","priority":50}).json()
        mid=created["mission"]["mission_id"]
        assert client.get(f"/v1/missions/{mid}",headers=headers).status_code==200
        assert client.get(f"/v1/missions/{mid}/status",headers=headers).status_code==200
        assert client.get("/v1/missions",headers=headers).status_code==200
