"""Web configuration UI — API routes with localhost access control."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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
_LOCALHOST = {"127.0.0.1", "::1", "localhost"}


# ---------------------------------------------------------------------------
# Localhost-only middleware
# ---------------------------------------------------------------------------


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """Block API requests from non-localhost clients (403)."""

    async def dispatch(self, request: Request, call_next):
        # Allow health and callback endpoints from anywhere
        path = request.url.path
        if path.startswith("/api/") or path == "/":
            allowed = getattr(request.app.state, "allowed_hosts", _LOCALHOST)
            client_ip = request.client.host if request.client else ""
            if client_ip not in allowed:
                logger.warning("Blocked request from %s to %s", client_ip, path)
                return JSONResponse({"error": "forbidden"}, status_code=403)
        return await call_next(request)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api")


def mount_web_ui(app: FastAPI, config_path: str) -> None:
    """Mount the web UI routes and static files on the FastAPI app."""
    app.add_middleware(LocalhostOnlyMiddleware)
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
            await event_router.dispatch(
                event_type, {}, request.app.state.config, request.app.state.clients
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
