"""NukiBlinker entry point — load config, wire up clients, start server."""

from __future__ import annotations

import argparse
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn

from nukiblinker.config import AppConfig, load_config
from nukiblinker.logging_config import get_logger, setup_logging
from nukiblinker.server import create_app
from nukiblinker.web_ui import mount_web_ui

logger = get_logger("main")


# ---------------------------------------------------------------------------
# Clients container
# ---------------------------------------------------------------------------


@dataclass
class Clients:
    """Lazy container for all external-service clients."""

    nuki: object = None
    hue: object = None
    chromecast: object = None
    airplay: object = None
    homekit: object = None


def _build_clients(config: AppConfig) -> Clients:
    """Instantiate clients based on the current config."""
    clients = Clients()

    if config.nuki.bridge_ip and config.nuki.api_token:
        from nukiblinker.nuki_client import NukiClient

        clients.nuki = NukiClient(config.nuki.bridge_ip, config.nuki.bridge_port, config.nuki.api_token)

    if config.hue.bridge_ip and config.hue.api_key:
        from nukiblinker.hue_client import HueClient

        clients.hue = HueClient(config.hue.bridge_ip, config.hue.api_key)

    from nukiblinker.chromecast_client import ChromecastClient
    from nukiblinker.airplay_client import AirPlayClient

    clients.chromecast = ChromecastClient()
    clients.airplay = AirPlayClient()

    if config.homekit.enabled:
        from nukiblinker.homekit_service import HomeKitService

        clients.homekit = HomeKitService(
            setup_code=config.homekit.setup_code,
            persist_dir=config.homekit.persist_dir,
        )

    return clients


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


async def _register_callback(config: AppConfig, clients: Clients) -> int | None:
    """Register the Nuki callback (idempotent). Returns callback ID or None."""
    if clients.nuki is None:
        logger.warning("Nuki not configured — skipping callback registration")
        return None
    host = config.server.host
    if host in ("0.0.0.0", "::"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((config.nuki.bridge_ip, 80))
            host = s.getsockname()[0]
            s.close()
        except Exception:
            host = "127.0.0.1"
    callback_url = f"http://{host}:{config.server.port}/nuki/callback"
    try:
        return await clients.nuki.register_callback(callback_url)
    except Exception:
        logger.error("Failed to register Nuki callback", exc_info=True)
        return None


async def _deregister_callback(clients: Clients, callback_id: int | None) -> None:
    """Deregister the Nuki callback on shutdown."""
    if clients.nuki is None or callback_id is None:
        return
    try:
        await clients.nuki.remove_callback(callback_id)
        logger.info("Nuki callback deregistered")
    except Exception:
        logger.warning("Failed to deregister Nuki callback", exc_info=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="NukiBlinker")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger.info("Starting NukiBlinker")

    config = load_config(args.config)
    clients = _build_clients(config)

    # Start HomeKit if enabled
    if clients.homekit is not None:
        clients.homekit.start()
        logger.info("HomeKit doorbell started (code: %s)", clients.homekit.get_setup_code())

    # Lifespan: startup + shutdown in a single context manager
    @asynccontextmanager
    async def lifespan(app):
        callback_id = await _register_callback(config, clients)
        app.state.callback_id = callback_id
        yield
        logger.info("Shutting down — deregistering callback")
        await _deregister_callback(clients, callback_id)
        if clients.homekit is not None:
            clients.homekit.stop()
        logger.info("Clean shutdown complete")

    # Create app
    app = create_app(config, clients, lifespan=lifespan)
    mount_web_ui(app, args.config)

    # Run
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
