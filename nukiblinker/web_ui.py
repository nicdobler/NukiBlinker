"""Web configuration UI — API routes with private-network access control."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from nukiblinker import discovery, event_router
from nukiblinker.config import save_config, AppConfig
from nukiblinker.logging_config import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("web_ui")

_STATIC_DIR = Path(__file__).parent / "static"


def _bridge_error(exc: Exception, bridge_label: str = "Bridge") -> tuple[dict, int]:
    """Convert bridge communication exceptions to (body, status_code)."""
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout)):
        return {"error": f"{bridge_label} unreachable — connection timed out"}, 502
    if isinstance(exc, httpx.ConnectError):
        return {"error": f"{bridge_label} unreachable — cannot connect"}, 502
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return {"error": f"{bridge_label} rejected the API token — check your credentials"}, 401
        if code == 403:
            return {"error": f"{bridge_label} denied access (403 Forbidden)"}, 403
        return {"error": f"{bridge_label} returned HTTP {code}"}, 502
    msg = str(exc) or repr(exc)
    return {"error": msg}, 500


# ---------------------------------------------------------------------------
# Private-network middleware
# ---------------------------------------------------------------------------


def _is_allowed(client_ip: str, allowed: set[str] | None) -> bool:
    """Check if client IP may access the admin API.

    If *allowed* is an explicit set, check membership.
    Otherwise allow any private / loopback IP (covers localhost,
    Docker gateway 172.17.x.x, and LAN 192.168.x.x / 10.x.x.x).
    """
    if allowed is not None:
        return client_ip in allowed
    try:
        return ipaddress.ip_address(client_ip).is_private
    except ValueError:
        return False


class PrivateNetworkMiddleware(BaseHTTPMiddleware):
    """Block API requests from non-private-network clients (403)."""

    async def dispatch(self, request: Request, call_next):
        # Allow health and callback endpoints from anywhere
        path = request.url.path
        if path.startswith("/api/") or path == "/":
            allowed = getattr(request.app.state, "allowed_hosts", None)
            client_ip = request.client.host if request.client else ""
            if not _is_allowed(client_ip, allowed):
                logger.warning("Blocked request from %s to %s", client_ip, path)
                return JSONResponse({"error": "forbidden"}, status_code=403)
        return await call_next(request)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


def mount_web_ui(app: FastAPI, config_path: str) -> None:
    """Mount the web UI routes and static files on the FastAPI app."""
    app.add_middleware(PrivateNetworkMiddleware)
    app.state.config_path = config_path

    @router.get("/config")
    async def get_config(request: Request) -> JSONResponse:
        cfg = request.app.state.config
        data = cfg.model_dump(mode="json")
        # Mask secrets
        if data.get("nuki", {}).get("api_token"):
            data["nuki"]["api_token"] = "***"
        if data.get("hue", {}).get("api_key"):
            data["hue"]["api_key"] = "***"
        return JSONResponse(data)

    @router.put("/config")
    async def put_config(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            current = request.app.state.config
            # Preserve masked secrets — GET returns "***"
            nuki = body.get("nuki", {})
            if nuki.get("api_token") in ("***", ""):
                nuki["api_token"] = current.nuki.api_token
            hue = body.get("hue", {})
            if hue.get("api_key") in ("***", ""):
                hue["api_key"] = current.hue.api_key
            # Preserve server config if not provided by the UI
            if "server" not in body:
                body["server"] = current.server.model_dump()
            new_config = AppConfig.model_validate(body)
            request.app.state.config = new_config
            save_config(new_config, request.app.state.config_path)
            return JSONResponse({"status": "saved"})
        except Exception as e:
            logger.warning("Config update failed: %s", e)
            return JSONResponse({"error": str(e)}, status_code=400)

    @router.get("/discover/nuki")
    async def discover_nuki() -> JSONResponse:
        bridges = await discovery.discover_nuki_bridges()
        return JSONResponse(bridges)

    @router.get("/discover/hue")
    async def discover_hue() -> JSONResponse:
        bridges = await discovery.discover_hue_bridges()
        return JSONResponse(bridges)

    @router.get("/discover/speakers")
    async def discover_speakers() -> JSONResponse:
        cc = await discovery.discover_chromecast_speakers()
        ap = await discovery.discover_airplay_speakers()
        return JSONResponse(cc + ap)

    # ------------------------------------------------------------------
    # Nuki pairing & device discovery
    # ------------------------------------------------------------------

    @router.post("/nuki/pair")
    async def nuki_pair(request: Request) -> JSONResponse:
        """Register NukiBlinker callback with the Nuki Bridge."""
        config = request.app.state.config
        if not config.nuki.bridge_ip or not config.nuki.api_token:
            return JSONResponse(
                {"error": "Configure Nuki Bridge IP and API Token first"},
                status_code=400,
            )
        try:
            from nukiblinker.nuki_client import NukiClient

            client = NukiClient(
                config.nuki.bridge_ip, config.nuki.bridge_port, config.nuki.api_token
            )
            from nukiblinker.config import get_public_host

            host = get_public_host(config)
            callback_url = f"http://{host}:{config.server.port}/nuki/callback"
            cb_id = await client.register_callback(callback_url)
            if cb_id is not None:
                request.app.state.callback_id = cb_id
                return JSONResponse({
                    "status": "paired",
                    "callback_id": cb_id,
                    "callback_url": callback_url,
                })
            return JSONResponse(
                {"error": "Registration failed \u2014 check Nuki Bridge logs"},
                status_code=500,
            )
        except Exception as e:
            logger.error("Nuki pairing failed: %s", e, exc_info=True)
            body, status = _bridge_error(e, "Nuki Bridge")
            return JSONResponse(body, status_code=status)

    @router.get("/nuki/devices")
    async def nuki_devices(request: Request) -> JSONResponse:
        """List Nuki devices visible to the configured bridge."""
        config = request.app.state.config
        if not config.nuki.bridge_ip or not config.nuki.api_token:
            return JSONResponse({"error": "Nuki not configured"}, status_code=400)
        try:
            from nukiblinker.nuki_client import NukiClient

            client = NukiClient(
                config.nuki.bridge_ip, config.nuki.bridge_port, config.nuki.api_token
            )
            devices = await client.list_devices()
            return JSONResponse(devices)
        except Exception as e:
            body, status = _bridge_error(e, "Nuki Bridge")
            return JSONResponse(body, status_code=status)

    @router.get("/nuki/callbacks")
    async def nuki_callbacks(request: Request) -> JSONResponse:
        """List registered callbacks on the Nuki Bridge."""
        config = request.app.state.config
        if not config.nuki.bridge_ip or not config.nuki.api_token:
            return JSONResponse({"error": "Nuki not configured"}, status_code=400)
        try:
            from nukiblinker.nuki_client import NukiClient

            client = NukiClient(
                config.nuki.bridge_ip, config.nuki.bridge_port, config.nuki.api_token
            )
            callbacks = await client.list_callbacks()
            return JSONResponse(callbacks)
        except Exception as e:
            body, status = _bridge_error(e, "Nuki Bridge")
            return JSONResponse(body, status_code=status)

    # ------------------------------------------------------------------
    # Hue pairing & device discovery
    # ------------------------------------------------------------------

    @router.get("/hue/status")
    async def hue_status(request: Request) -> JSONResponse:
        """Check Hue Bridge connection and API key validity."""
        config = request.app.state.config
        if not config.hue.bridge_ip:
            return JSONResponse({
                "connected": False,
                "has_api_key": False,
                "error": "Hue Bridge IP not configured",
            })
        if not config.hue.api_key:
            return JSONResponse({
                "connected": False,
                "has_api_key": False,
                "error": "No API key \u2014 pairing required",
            })
        try:
            from nukiblinker.hue_client import HueClient

            client = HueClient(config.hue.bridge_ip, config.hue.api_key)
            result = await client.check_connection()
            result["has_api_key"] = True
            result["bridge_ip"] = config.hue.bridge_ip
            return JSONResponse(result)
        except Exception as e:
            err_body, _ = _bridge_error(e, "Hue Bridge")
            return JSONResponse({
                "connected": False,
                "has_api_key": True,
                "error": err_body.get("error", str(e)),
            })

    @router.post("/hue/pair")
    async def hue_pair(request: Request) -> JSONResponse:
        """Pair with Hue Bridge.

        If an API key already exists, validates it first and returns
        success without re-pairing.  Otherwise (or if the key is
        invalid) attempts the standard press-button pairing flow.
        """
        body = await request.json()
        bridge_ip = body.get("bridge_ip") or request.app.state.config.hue.bridge_ip
        if not bridge_ip:
            return JSONResponse(
                {"error": "Hue Bridge IP is required"}, status_code=400
            )
        try:
            from nukiblinker.hue_client import HueClient

            # Try existing API key first
            existing_key = request.app.state.config.hue.api_key
            if existing_key:
                client = HueClient(bridge_ip, existing_key)
                check = await client.check_connection()
                if check.get("connected"):
                    logger.info("Hue Bridge \u2014 existing API key still valid")
                    config = request.app.state.config
                    config.hue.bridge_ip = bridge_ip
                    save_config(config, request.app.state.config_path)
                    return JSONResponse({
                        "status": "paired",
                        "method": "existing_key",
                        "api_key_preview": existing_key[:8] + "...",
                        "bridge_name": check.get("name", ""),
                    })
                logger.info(
                    "Hue Bridge \u2014 existing API key invalid (%s), attempting new pairing",
                    check.get("error", ""),
                )

            # Full pairing flow (press button)
            api_key = await HueClient.pair(bridge_ip)
            if api_key:
                config = request.app.state.config
                config.hue.api_key = api_key
                config.hue.bridge_ip = bridge_ip
                save_config(config, request.app.state.config_path)
                return JSONResponse({
                    "status": "paired",
                    "method": "new_pairing",
                    "api_key_preview": api_key[:8] + "...",
                })
            return JSONResponse(
                {"error": "Pairing failed \u2014 press the button on the Hue Bridge and try again within 30s"},
                status_code=400,
            )
        except Exception as e:
            logger.error("Hue pairing failed: %s", e, exc_info=True)
            body, status = _bridge_error(e, "Hue Bridge")
            return JSONResponse(body, status_code=status)

    @router.get("/hue/lights")
    async def hue_lights(request: Request) -> JSONResponse:
        """List lights from the configured Hue Bridge."""
        config = request.app.state.config
        if not config.hue.bridge_ip or not config.hue.api_key:
            return JSONResponse(
                {"error": "Hue not configured or not paired"}, status_code=400
            )
        try:
            from nukiblinker.hue_client import HueClient

            client = HueClient(config.hue.bridge_ip, config.hue.api_key)
            lights = await client.list_lights()
            return JSONResponse(lights)
        except Exception as e:
            body, status = _bridge_error(e, "Hue Bridge")
            return JSONResponse(body, status_code=status)

    @router.get("/hue/groups")
    async def hue_groups(request: Request) -> JSONResponse:
        """List groups from the configured Hue Bridge."""
        config = request.app.state.config
        if not config.hue.bridge_ip or not config.hue.api_key:
            return JSONResponse(
                {"error": "Hue not configured or not paired"}, status_code=400
            )
        try:
            from nukiblinker.hue_client import HueClient

            client = HueClient(config.hue.bridge_ip, config.hue.api_key)
            groups = await client.list_groups()
            return JSONResponse(groups)
        except Exception as e:
            body, status = _bridge_error(e, "Hue Bridge")
            return JSONResponse(body, status_code=status)

    @router.get("/status")
    async def status(request: Request) -> JSONResponse:
        last = request.app.state.last_event
        return JSONResponse({
            "paused": request.app.state.paused,
            "last_event": last,
        })

    @router.post("/pause")
    async def pause(request: Request) -> JSONResponse:
        request.app.state.paused = True
        # Deregister Nuki callback
        nuki = getattr(request.app.state.clients, "nuki", None)
        cb_id = getattr(request.app.state, "callback_id", None)
        if nuki and cb_id:
            try:
                await nuki.remove_callback(cb_id)
            except Exception:
                logger.warning("Failed to deregister callback on pause", exc_info=True)
        logger.info("Service paused")
        return JSONResponse({"status": "paused"})

    @router.post("/resume")
    async def resume(request: Request) -> JSONResponse:
        request.app.state.paused = False
        logger.info("Service resumed")
        return JSONResponse({"status": "resumed"})

    @router.post("/test/event/{event_type}")
    async def test_event(event_type: str, request: Request) -> JSONResponse:
        if event_type not in ("ring", "ring_to_open", "door_opened"):
            return JSONResponse({"error": f"unknown event type: {event_type}"}, status_code=400)
        try:
            # Accept optional ?name= to simulate known vs unknown visitor
            name = request.query_params.get("name")
            payload: dict = {}
            context_override: dict | None = None
            if name is not None:
                context_override = {"name": name}
            await event_router.dispatch(
                event_type, payload, request.app.state.config,
                request.app.state.clients, context_override=context_override,
            )
            return JSONResponse({"status": "fired", "event": event_type})
        except Exception as e:
            logger.error("Test event failed: %s", e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)

    app.include_router(router)

    # Serve static files (index.html)
    @app.get("/")
    async def index():
        index_file = _STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"message": "Web UI not available"}, status_code=404)
