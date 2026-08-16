from __future__ import annotations

import argparse
import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from market_intelligence.core.event_loop import psycopg_compatible_loop
from market_intelligence.missions.models import (
    FollowUpCreate,
    HumanDomainHypothesisCreate,
    MissionCreate,
)
from market_intelligence.missions.orchestrator import SovereignMissionOrchestrator
from market_intelligence.missions.persistence import PostgresMissionRepository
from market_intelligence.persistence.database import create_database_engine, create_session_factory

HOST = "127.0.0.1"
DEFAULT_PORT = 8785


def _token(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise RuntimeError("mission_api_token_invalid")
    return value


def build_app(database_url: str, runtime_root: Path, token_path: Path, step_delay_seconds: float = 0.5) -> FastAPI:
    engine = create_database_engine(database_url); sessions = create_session_factory(engine); repo = PostgresMissionRepository(sessions)
    orchestrator = SovereignMissionOrchestrator(repo, database_url, runtime_root, step_delay_seconds); token = _token(token_path); worker: asyncio.Task | None = None

    async def auth(authorization: str | None = Header(default=None)) -> None:
        if authorization != f"Bearer {token}": raise HTTPException(status_code=401, detail="unauthorized")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal worker
        SovereignMissionOrchestrator.assert_security(); worker = asyncio.create_task(orchestrator.run_forever(), name="sovereign-mission-orchestrator")
        try:
            yield
        finally:
            if worker: worker.cancel()
            if worker:
                try: await worker
                except asyncio.CancelledError: pass
            await engine.dispose()

    app = FastAPI(title="Sovereign Mission Protocol", version="1.1.0", lifespan=lifespan)

    @app.post("/v1/missions", dependencies=[Depends(auth)])
    async def create_mission(request: MissionCreate) -> dict[str, Any]:
        mission, created = await repo.create(request); return {"created": created, "mission": mission}

    @app.get("/v1/missions", dependencies=[Depends(auth)])
    async def list_missions(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]: return await repo.list(limit)

    @app.get("/v1/missions/{mission_id}", dependencies=[Depends(auth)])
    async def get_mission(mission_id: str) -> dict[str, Any]:
        item = await repo.get(mission_id)
        if not item: raise HTTPException(status_code=404, detail="mission_not_found")
        return item

    @app.get("/v1/missions/{mission_id}/status", dependencies=[Depends(auth)])
    async def get_status(mission_id: str) -> dict[str, Any]:
        item = await repo.get(mission_id)
        if not item: raise HTTPException(status_code=404, detail="mission_not_found")
        return {"mission": item, "steps": await repo.steps(mission_id), "iterations": await repo.iterations(mission_id), "plan": await repo.get_plan(mission_id)}

    @app.get("/v1/missions/{mission_id}/report", dependencies=[Depends(auth)])
    async def get_report(mission_id: str) -> dict[str, Any]:
        item = await repo.get_report(mission_id)
        if not item: raise HTTPException(status_code=404, detail="report_not_found")
        return item

    @app.post("/v1/missions/{mission_id}/follow-ups", dependencies=[Depends(auth)])
    async def create_follow_up(mission_id: str, request: FollowUpCreate) -> dict[str, Any]:
        try: mission, created = await repo.create_follow_up(mission_id, request)
        except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"created": created, "mission": mission}

    @app.get("/v1/missions/{mission_id}/timeline", dependencies=[Depends(auth)])
    async def get_timeline(mission_id: str) -> dict[str, Any]:
        try: return await repo.timeline(mission_id)
        except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/missions/{mission_id}/evidence", dependencies=[Depends(auth)])
    async def get_evidence(mission_id: str) -> list[dict[str, Any]]:
        if not await repo.get(mission_id): raise HTTPException(status_code=404, detail="mission_not_found")
        return await repo.evidence(mission_id)

    @app.get("/v1/missions/{mission_id}/findings", dependencies=[Depends(auth)])
    async def get_findings(mission_id: str) -> list[dict[str, Any]]:
        if not await repo.get(mission_id): raise HTTPException(status_code=404, detail="mission_not_found")
        return await repo.findings(mission_id)

    @app.get("/v1/threads/{thread_id}", dependencies=[Depends(auth)])
    async def get_thread(thread_id: str) -> dict[str, Any]:
        item = await repo.thread(thread_id)
        if not item: raise HTTPException(status_code=404, detail="thread_not_found")
        return item

    @app.get("/v1/reports/latest", dependencies=[Depends(auth)])
    async def latest_report() -> dict[str, Any]:
        item = await repo.latest_report()
        if not item: raise HTTPException(status_code=404, detail="report_not_found")
        return item

    @app.get("/v1/intelligence/context", dependencies=[Depends(auth)])
    async def intelligence_context() -> dict[str, Any]: return await repo.intelligence_context()

    @app.get("/v1/intelligence/inbox", dependencies=[Depends(auth)])
    async def intelligence_inbox(status: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        if status and status not in {"UNREAD", "READ", "ACKNOWLEDGED"}: raise HTTPException(status_code=400, detail="invalid_inbox_status")
        return await repo.inbox(status=status, limit=limit)

    @app.get("/v1/intelligence/brief", dependencies=[Depends(auth)])
    async def intelligence_brief() -> dict[str, Any]: return await repo.executive_brief(unread_only=False)

    @app.get("/v1/intelligence/brief/unread", dependencies=[Depends(auth)])
    async def intelligence_brief_unread() -> dict[str, Any]: return await repo.executive_brief(unread_only=True)

    @app.post("/v1/intelligence/inbox/{inbox_id}/read", dependencies=[Depends(auth)])
    async def mark_inbox_read(inbox_id: str) -> dict[str, Any]:
        try: item = await repo.mark_inbox_read(inbox_id)
        except (ValueError, TypeError) as exc: raise HTTPException(status_code=400, detail="invalid_inbox_id") from exc
        if not item: raise HTTPException(status_code=404, detail="inbox_item_not_found")
        return item

    @app.get("/v1/evolution/snapshot", dependencies=[Depends(auth)])
    async def evolution_snapshot() -> dict[str, Any]:
        return await orchestrator.evolution.executive_snapshot()

    @app.get("/v1/evolution/report", dependencies=[Depends(auth)])
    async def evolution_report() -> dict[str, Any]:
        path = await orchestrator.evolution.write_report()
        return {"report_path": str(path), "snapshot": await orchestrator.evolution.executive_snapshot(), "marketplace_writes": 0}

    @app.post("/v1/evolution/run", dependencies=[Depends(auth)])
    async def run_evolution_cycle() -> dict[str, Any]:
        result = await orchestrator.evolution.run_due(force=True)
        return result

    @app.post("/v1/evolution/human-hypotheses", dependencies=[Depends(auth)])
    async def record_human_hypothesis(request: HumanDomainHypothesisCreate) -> dict[str, Any]:
        return await orchestrator.evolution.record_human_hypothesis(
            request.statement,
            request.signal_family,
            request.confidence_initial,
        )
    @app.get("/v1/mission-system/health", dependencies=[Depends(auth)])
    async def health() -> dict[str, Any]:
        state = await repo.health(); state.update({"status": "PASS", "orchestrator": "ACTIVE", "version": orchestrator.version, "api_version": "1.1.0", "read_only": True, "marketplace_writes": 0, "pid": os.getpid()}); return state

    return app


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default=HOST); parser.add_argument("--port", type=int, default=DEFAULT_PORT); parser.add_argument("--step-delay-seconds", type=float, default=0.5); args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}: raise RuntimeError("mission_api_must_bind_loopback")
    database_url = os.getenv("MI_DATABASE_URL", "").strip()
    if not database_url: raise RuntimeError("MI_DATABASE_URL_missing")
    repo_root = Path(__file__).resolve().parents[1]; runtime_root = repo_root / "runtime"; token_path = runtime_root / "config" / "mission-api-token.txt"
    app = build_app(database_url, runtime_root, token_path, args.step_delay_seconds)
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning", access_log=False); server = uvicorn.Server(config)
    with asyncio.Runner(loop_factory=psycopg_compatible_loop) as runner: runner.run(server.serve())
    return 0


if __name__ == "__main__": raise SystemExit(main())
