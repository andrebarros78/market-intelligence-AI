from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from market_intelligence.core.json_safety import json_safe


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _json_serializer(value: Any) -> str:
    return json.dumps(json_safe(value), allow_nan=False, separators=(",", ":"))


def create_database_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(url),
        echo=echo,
        pool_pre_ping=True,
        json_serializer=_json_serializer,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
