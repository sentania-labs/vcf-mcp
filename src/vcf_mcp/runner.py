"""Uvicorn runner with an application-owned clean restart control."""

from __future__ import annotations

import uvicorn

from vcf_mcp.main import create_production_app


def run(
    *,
    host: str = "0.0.0.0",
    port: int = 8000,
    graceful_shutdown_seconds: int = 10,
) -> None:
    """Run the appliance until Uvicorn or the admin console requests exit."""

    holder: dict[str, uvicorn.Server] = {}

    def request_restart() -> None:
        holder["server"].should_exit = True

    def application_factory():
        return create_production_app(restart_requester=request_restart)

    config = uvicorn.Config(
        application_factory,
        factory=True,
        host=host,
        port=port,
        timeout_graceful_shutdown=graceful_shutdown_seconds,
    )
    server = uvicorn.Server(config)
    holder["server"] = server
    server.run()


if __name__ == "__main__":
    run()
