from __future__ import annotations

import os

import uvicorn


def _port_from_env() -> int:
    raw = os.getenv("MI_ML_WEBHOOK_LOCAL_PORT", "8772")
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("MI_ML_WEBHOOK_LOCAL_PORT must be an integer") from exc
    if port < 1024 or port > 65535:
        raise RuntimeError("MI_ML_WEBHOOK_LOCAL_PORT must be between 1024 and 65535")
    return port


def main() -> None:
    # Loopback only. Public HTTPS exposure is a separately governed deployment step.
    # Psycopg async mode cannot run on Windows' default ProactorEventLoop, so Uvicorn
    # is given an explicit cross-platform loop factory that selects SelectorEventLoop
    # on Windows and the platform default elsewhere.
    uvicorn.run(
        "market_intelligence.api.webhook_server:create_mercadolivre_webhook_app_from_env",
        factory=True,
        host="127.0.0.1",
        port=_port_from_env(),
        access_log=False,
        proxy_headers=False,
        server_header=False,
        log_level="info",
        loop="market_intelligence.core.event_loop:psycopg_compatible_loop",
    )


if __name__ == "__main__":
    main()
