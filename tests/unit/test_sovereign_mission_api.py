from __future__ import annotations

import os
import time

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


def test_conversational_intelligence_api_contract(tmp_path, monkeypatch) -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return
    monkeypatch.setenv("MI_READ_ONLY", "true")
    monkeypatch.setenv("MI_ALLOW_MARKETPLACE_WRITES", "false")
    monkeypatch.setenv("MARKETPLACE_WRITES", "0")
    token_path = tmp_path / "dialogue-token.txt"
    app = build_app(url, tmp_path, token_path, 0.01)
    token = token_path.read_text().strip()
    headers = {"Authorization": f"Bearer {token}"}

    def wait_completed(client: TestClient, mission_id: str) -> dict:
        latest = {}
        for _ in range(300):
            response = client.get(f"/v1/missions/{mission_id}/status", headers=headers)
            assert response.status_code == 200
            latest = response.json()
            if latest["mission"]["status"] == "COMPLETED":
                return latest
            time.sleep(0.05)
        raise AssertionError(f"mission_not_completed:{mission_id}:{latest}")

    with TestClient(app) as client:
        root_response = client.post(
            "/v1/missions",
            headers=headers,
            json={
                "objective": "Investigate observable visit and channel changes in read-only mode.",
                "origin": "GPT",
                "mission_type": "DIRECTED",
                "marketplace_scope": ["mercadolivre"],
                "authority": "owner_read_only",
                "priority": 100,
            },
        )
        assert root_response.status_code == 200
        root = root_response.json()["mission"]
        wait_completed(client, root["mission_id"])
        report = client.get(f"/v1/missions/{root['mission_id']}/report", headers=headers)
        assert report.status_code == 200 and report.json()["marketplace_writes"] == 0

        follow_response = client.post(
            f"/v1/missions/{root['mission_id']}/follow-ups",
            headers=headers,
            json={
                "question": "Challenge this conclusion and look for alternative explanations and contrary evidence.",
                "mode": "challenge",
                "priority": 100,
            },
        )
        assert follow_response.status_code == 200
        follow = follow_response.json()["mission"]
        assert follow["parent_mission_id"] == root["mission_id"]
        assert follow["thread_id"] == root["thread_id"]
        wait_completed(client, follow["mission_id"])

        assert client.get(f"/v1/missions/{follow['mission_id']}/timeline", headers=headers).status_code == 200
        assert client.get(f"/v1/missions/{follow['mission_id']}/evidence", headers=headers).status_code == 200
        assert client.get(f"/v1/missions/{follow['mission_id']}/findings", headers=headers).status_code == 200
        thread = client.get(f"/v1/threads/{root['thread_id']}", headers=headers)
        assert thread.status_code == 200 and len(thread.json()["missions"]) >= 2
        context = client.get("/v1/intelligence/context", headers=headers)
        assert context.status_code == 200 and context.json()["marketplace_writes"] == 0
        assert "missions_in_progress" in context.json()
        assert context.json()["last_version"]["schema"] == "0011_cognitive_dialogue"
        brief = client.get("/v1/intelligence/brief", headers=headers)
        unread_brief = client.get("/v1/intelligence/brief/unread", headers=headers)
        assert brief.status_code == 200 and brief.json()["marketplace_actions_executed"] == 0
        assert unread_brief.status_code == 200 and unread_brief.json()["marketplace_writes"] == 0
        inbox = client.get("/v1/intelligence/inbox?status=UNREAD&limit=50", headers=headers)
        assert inbox.status_code == 200 and inbox.json()
        item_id = inbox.json()[0]["id"]
        marked = client.post(f"/v1/intelligence/inbox/{item_id}/read", headers=headers)
        assert marked.status_code == 200 and marked.json()["status"] == "READ"
