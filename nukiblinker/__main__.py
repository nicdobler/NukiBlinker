"""NukiBlinker entry point — load config, wire up clients, start server."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn

from nukiblinker.config import AppConfig, load_config, summarize_config
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


_RETRY_DELAYS = [10, 20, 40]  # then 60s indefinitely


def _resolve_callback_url(config: AppConfig) -> str:
    """Build the callback URL, auto-detecting LAN IP if needed."""
    host = config.server.host
    if host in ("0.0.0.0", "::"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((config.nuki.bridge_ip, 80))
            host = s.getsockname()[0]
            s.close()
        except Exception:
            host = "127.0.0.1"
    return f"http://{host}:{config.server.port}/nuki/callback"


async def _register_callback_loop(config: AppConfig, clients: Clients, app) -> None:
    """Register the Nuki callback with infinite retry.

    Retries after 10s, 20s, 40s, then every 60s until success or cancellation.
    Runs as a background task so server startup is not blocked.
    """
    if clients.nuki is None:
        logger.warning("Nuki not configured — skipping callback registration")
        return
    callback_url = _resolve_callback_url(config)
    bridge_url = f"http://{config.nuki.bridge_ip}:{config.nuki.bridge_port}"
    attempt = 0
    while True:
        try:
            logger.info(
                "Registering Nuki callback (attempt %d): bridge=%s callback=%s",
                attempt + 1, bridge_url, callback_url,
            )
            cb_id = await clients.nuki.register_callback(callback_url)
            app.state.callback_id = cb_id
            logger.info("Nuki callback registered successfully (id=%s)", cb_id)
            return
        except Exception:
            delay = _RETRY_DELAYS[attempt] if attempt < len(_RETRY_DELAYS) else 60
            logger.warning(
                "Failed to reach Nuki Bridge at %s — retrying in %ds",
                bridge_url, delay,
            )
            attempt += 1
            await asyncio.sleep(delay)


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
    logger.info("Config loaded from %s: %s", args.config, summarize_config(config))
    clients = _build_clients(config)

    # Start HomeKit if enabled
    if clients.homekit is not None:
        if clients.homekit.start():
            logger.info("HomeKit doorbell started (code: %s)", clients.homekit.get_setup_code())

    # Lifespan: startup + shutdown in a single context manager
    @asynccontextmanager
    async def lifespan(app):
        app.state.callback_id = None
        registration_task = asyncio.create_task(
            _register_callback_loop(config, clients, app)
        )
        yield
        logger.info("Shutting down — cancelling registration & deregistering callback")
        registration_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await registration_task
        await _deregister_callback(clients, app.state.callback_id)
        if clients.homekit is not None:
            clients.homekit.stop()
        logger.info("Clean shutdown complete")

    # Create app
    app = create_app(config, clients, lifespan=lifespan)
    clients._app = app  # allow notifier to register audio files for serving
    mount_web_ui(app, args.config)

    # Run
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
