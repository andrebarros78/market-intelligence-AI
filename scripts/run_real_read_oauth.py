from __future__ import annotations

import os

import uvicorn


def _port_from_env() -> int:
    raw = os.getenv("MI_ML_OAUTH_LOCAL_PORT", "8771")
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("MI_ML_OAUTH_LOCAL_PORT must be an integer") from exc
    if port < 1024 or port > 65535:
        raise RuntimeError("MI_ML_OAUTH_LOCAL_PORT must be between 1024 and 65535")
    return port


def main() -> None:
    # Intentionally bound to loopback. A separately governed HTTPS tunnel/reverse proxy
    # may expose only the registered callback path after its own authorization gate.
    uvicorn.run(
        "market_intelligence.api.real_read_server:create_real_read_app_from_env",
        factory=True,
        host="127.0.0.1",
        port=_port_from_env(),
        access_log=False,
        proxy_headers=False,
        server_header=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
