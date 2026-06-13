"""Web configuration UI — API routes with private-network access control."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
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
    logger.warning("Unexpected bridge error: %s", exc, exc_info=True)
    return {"error": "Unexpected bridge communication error"}, 500


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
        if data.get("nuki", {}).get("web_api_token"):
            data["nuki"]["web_api_token"] = "***"
        if data.get("hue", {}).get("api_key"):
            data["hue"]["api_key"] = "***"
        return JSONResponse(data)

    @router.put("/config")
    async def put_config(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            current = request.app.state.config
            # Preserve whole sections the UI omitted (so a partial PUT never
            # wipes existing credentials), then restore masked secrets — GET
            # returns "***" for secret fields.
            if "nuki" not in body:
                body["nuki"] = current.nuki.model_dump()
            nuki = body["nuki"]
            if nuki.get("api_token") in ("***", ""):
                nuki["api_token"] = current.nuki.api_token
            if nuki.get("web_api_token") in ("***", ""):
                nuki["web_api_token"] = current.nuki.web_api_token
            if "hue" not in body:
                body["hue"] = current.hue.model_dump()
            hue = body["hue"]
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
            return JSONResponse({"error": "Invalid configuration data"}, status_code=400)

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
        return JSONResponse(cc)

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
                "error": err_body.get("error", "Unexpected bridge communication error"),
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

    # ------------------------------------------------------------------
    # Event log endpoints
    # ------------------------------------------------------------------

    @router.get("/events/log")
    async def get_event_log(request: Request) -> JSONResponse:
        """Get recent event log entries."""
        if not request.app.state.config.event_log.enabled:
            return JSONResponse({"error": "Event logging is disabled"}, status_code=400)

        try:
            limit = int(request.query_params.get("limit", 100))
            offset = int(request.query_params.get("offset", 0))
            limit = min(limit, 1000)  # Cap at 1000 to prevent overload

            device_param = request.query_params.get("device_id")
            device_id = int(device_param) if device_param else None

            event_log = request.app.state.clients.event_log
            events = event_log.get_recent_events(limit, offset, device_id=device_id)
            total_count = event_log.get_event_count(device_id=device_id)

            return JSONResponse({
                "events": [event.to_dict() for event in events],
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "device_id": device_id
            })
        except Exception as e:
            logger.error("Failed to get event log: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to retrieve event log"}, status_code=500)

    @router.get("/events/devices")
    async def get_event_log_devices(request: Request) -> JSONResponse:
        """Return the distinct devices seen in the event log (for the UI filter)."""
        if not request.app.state.config.event_log.enabled:
            return JSONResponse({"error": "Event logging is disabled"}, status_code=400)
        try:
            devices = request.app.state.clients.event_log.get_devices()
            return JSONResponse({"devices": devices})
        except Exception as e:
            logger.error("Failed to get event log devices: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to retrieve devices"}, status_code=500)

    @router.get("/events/export")
    async def export_event_log(request: Request) -> FileResponse:
        """Export event log as CSV (optionally filtered by ?device_id=)."""
        if not request.app.state.config.event_log.enabled:
            return JSONResponse({"error": "Event logging is disabled"}, status_code=400)

        try:
            device_param = request.query_params.get("device_id")
            device_id = int(device_param) if device_param else None
            tz = request.app.state.config.event_log.timezone
            csv_content = request.app.state.clients.event_log.export_to_csv(
                device_id=device_id, tz=tz
            )

            # Create temporary file (utf-8 so the BOM is preserved for Excel)
            import tempfile
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nukiblinker_events_{timestamp}.csv"

            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.csv', delete=False, encoding='utf-8'
            ) as f:
                f.write(csv_content)
                temp_path = f.name

            return FileResponse(
                temp_path,
                media_type='text/csv',
                filename=filename,
                background=BackgroundTask(os.unlink, temp_path),
            )
        except Exception as e:
            logger.error("Failed to export event log: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to export event log"}, status_code=500)

    @router.post("/events/clear")
    async def clear_event_log(request: Request) -> JSONResponse:
        """Clear all event log entries."""
        if not request.app.state.config.event_log.enabled:
            return JSONResponse({"error": "Event logging is disabled"}, status_code=400)

        try:
            request.app.state.clients.event_log.clear_log()
            logger.info("Event log cleared via web UI")
            return JSONResponse({"status": "cleared"})
        except Exception as e:
            logger.error("Failed to clear event log: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to clear event log"}, status_code=500)

    # ------------------------------------------------------------------
    # Configuration endpoints for new features
    # ------------------------------------------------------------------

    @router.get("/config/event-validation")
    async def get_event_validation_config(request: Request) -> JSONResponse:
        """Get current event validation configuration."""
        config = request.app.state.config.event_validation
        return JSONResponse({
            "enabled": config.enabled,
            "max_delay_seconds": config.max_delay_seconds
        })

    @router.put("/config/event-validation")
    async def update_event_validation_config(request: Request) -> JSONResponse:
        """Update event validation configuration."""
        try:
            try:
                data = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

            # Validate input
            if "max_delay_seconds" in data:
                delay = data["max_delay_seconds"]
                if not isinstance(delay, int) or delay < 1 or delay > 3600:
                    return JSONResponse({
                        "error": "max_delay_seconds must be an integer between 1 and 3600"
                    }, status_code=400)

            # Update configuration
            config = request.app.state.config
            if "enabled" in data:
                config.event_validation.enabled = bool(data["enabled"])
            if "max_delay_seconds" in data:
                config.event_validation.max_delay_seconds = data["max_delay_seconds"]

            # Update validator service
            if hasattr(request.app.state.clients, 'event_validator'):
                request.app.state.clients.event_validator.max_delay_seconds = config.event_validation.max_delay_seconds

            # Save configuration
            save_config(config, request.app.state.config_path)

            logger.info("Event validation config updated: %s", data)
            return JSONResponse({
                "enabled": config.event_validation.enabled,
                "max_delay_seconds": config.event_validation.max_delay_seconds
            })
        except Exception as e:
            logger.error("Failed to update event validation config: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to update configuration"}, status_code=500)

    @router.get("/config/night-mode")
    async def get_night_mode_config(request: Request) -> JSONResponse:
        """Get current night mode configuration and status."""
        config = request.app.state.config.night_mode
        status = {}

        if hasattr(request.app.state.clients, 'night_mode'):
            status = request.app.state.clients.night_mode.get_status()

        return JSONResponse({
            "enabled": config.enabled,
            "start_time": config.start_time,
            "end_time": config.end_time,
            "brightness_factor": config.brightness_factor,
            "grace_minutes": config.grace_minutes,
            "status": status
        })

    @router.put("/config/night-mode")
    async def update_night_mode_config(request: Request) -> JSONResponse:
        """Update night mode configuration."""
        try:
            try:
                data = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

            # Validate input
            if "start_time" in data:
                start_time = data["start_time"]
                if not isinstance(start_time, str) or len(start_time) != 5:
                    return JSONResponse({"error": "start_time must be in HH:MM format"}, status_code=400)
                try:
                    from datetime import datetime
                    datetime.strptime(start_time, "%H:%M")
                except ValueError:
                    return JSONResponse({"error": "start_time must be in HH:MM format"}, status_code=400)

            if "end_time" in data:
                end_time = data["end_time"]
                if not isinstance(end_time, str) or len(end_time) != 5:
                    return JSONResponse({"error": "end_time must be in HH:MM format"}, status_code=400)
                try:
                    from datetime import datetime
                    datetime.strptime(end_time, "%H:%M")
                except ValueError:
                    return JSONResponse({"error": "end_time must be in HH:MM format"}, status_code=400)

            if "brightness_factor" in data:
                factor = data["brightness_factor"]
                if not isinstance(factor, (int, float)) or factor < 0.0 or factor > 1.0:
                    return JSONResponse({"error": "brightness_factor must be between 0.0 and 1.0"}, status_code=400)

            if "grace_minutes" in data:
                minutes = data["grace_minutes"]
                if not isinstance(minutes, int) or minutes < 0 or minutes > 60:
                    return JSONResponse({"error": "grace_minutes must be an integer between 0 and 60"}, status_code=400)
        # Update configuration
            config = request.app.state.config
            if "enabled" in data:
                config.night_mode.enabled = bool(data["enabled"])
            if "start_time" in data:
                config.night_mode.start_time = data["start_time"]
            if "end_time" in data:
                config.night_mode.end_time = data["end_time"]
            if "brightness_factor" in data:
                config.night_mode.brightness_factor = float(data["brightness_factor"])
            if "grace_minutes" in data:
                config.night_mode.grace_minutes = int(data["grace_minutes"])

            # Update night mode service
            if hasattr(request.app.state.clients, 'night_mode'):
                request.app.state.clients.night_mode.update_settings(
                    start_time=config.night_mode.start_time,
                    end_time=config.night_mode.end_time,
                    brightness_factor=config.night_mode.brightness_factor,
                    grace_minutes=config.night_mode.grace_minutes
                )

            # Save configuration
            save_config(config, request.app.state.config_path)

            logger.info("Night mode config updated: %s", data)
            return JSONResponse({
                "enabled": config.night_mode.enabled,
                "start_time": config.night_mode.start_time,
                "end_time": config.night_mode.end_time,
                "brightness_factor": config.night_mode.brightness_factor,
                "grace_minutes": config.night_mode.grace_minutes
            })
        except Exception as e:
            logger.error("Failed to update night mode config: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to update configuration"}, status_code=500)

    @router.get("/config/event-log")
    async def get_event_log_config(request: Request) -> JSONResponse:
        """Get current event log configuration."""
        config = request.app.state.config.event_log
        stats = {}

        if hasattr(request.app.state.clients, 'event_log'):
            stats = {
                "current_entries": request.app.state.clients.event_log.get_event_count(),
                "max_entries": config.max_entries,
                "retention_days": config.retention_days
            }

        return JSONResponse({
            "enabled": config.enabled,
            "max_entries": config.max_entries,
            "retention_days": config.retention_days,
            "persist_to_file": config.persist_to_file,
            "file_path": config.file_path,
            "timezone": config.timezone,
            "stats": stats
        })

    @router.put("/config/event-log")
    async def update_event_log_config(request: Request) -> JSONResponse:
        """Update event log configuration."""
        try:
            try:
                data = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

            # Validate input
            if "max_entries" in data:
                max_entries = data["max_entries"]
                if not isinstance(max_entries, int) or max_entries < 10 or max_entries > 10000:
                    return JSONResponse(
                        {"error": "max_entries must be an integer between 10 and 10000"},
                        status_code=400
                    )
            if "retention_days" in data:
                retention = data["retention_days"]
                if not isinstance(retention, int) or retention < 1 or retention > 365:
                    return JSONResponse(
                        {"error": "retention_days must be an integer between 1 and 365"},
                        status_code=400
                    )

            # Update configuration
            config = request.app.state.config
            if "enabled" in data:
                config.event_log.enabled = bool(data["enabled"])
            if "max_entries" in data:
                config.event_log.max_entries = data["max_entries"]
            if "retention_days" in data:
                config.event_log.retention_days = data["retention_days"]
            if "persist_to_file" in data:
                config.event_log.persist_to_file = bool(data["persist_to_file"])
            if "timezone" in data:
                config.event_log.timezone = str(data["timezone"])

            # Save configuration
            save_config(config, request.app.state.config_path)

            logger.info("Event log config updated: %s", data)
            return JSONResponse({
                "enabled": config.event_log.enabled,
                "max_entries": config.event_log.max_entries,
                "retention_days": config.event_log.retention_days,
                "persist_to_file": config.event_log.persist_to_file,
                "file_path": config.event_log.file_path,
                "timezone": config.event_log.timezone
            })
        except Exception as e:
            logger.error("Failed to update event log config: %s", e, exc_info=True)
            return JSONResponse({"error": "Failed to update configuration"}, status_code=500)

    @router.get("/homekit/qr")
    async def homekit_qr(request: Request) -> JSONResponse:
        """Return HomeKit setup code and SVG QR code for pairing."""
        homekit = getattr(request.app.state.clients, "homekit", None)
        if homekit is None:
            return JSONResponse({"error": "HomeKit is not enabled"}, status_code=404)
        svg = homekit.get_qr_code()
        return JSONResponse({
            "setup_code": homekit.get_setup_code(),
            "paired": homekit.is_paired(),
            "qr_svg": svg,
        })

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

            config = request.app.state.config
            clients = request.app.state.clients

            # Apply night mode so a test fired at night mirrors real behaviour.
            rule = getattr(config.events, event_type)
            if config.night_mode.enabled and getattr(clients, "night_mode", None) is not None:
                rule = clients.night_mode.apply_night_mode(rule)

            actions = await event_router.dispatch_with_actions(
                event_type, payload, config, clients, rule,
                context_override=context_override,
            )

            # Record test events in the event log, like real callbacks. The
            # detailed actions (which may embed exception text) are kept in the
            # Event Log only — they are deliberately NOT echoed in the HTTP
            # response to avoid leaking internal error detail (CodeQL
            # py/stack-trace-exposure).
            if config.event_log.enabled and getattr(clients, "event_log", None) is not None:
                validation_result = clients.event_validator.validate_event(payload)
                clients.event_log.log_event(
                    payload=payload,
                    event_type=event_type,
                    actions=actions,
                    validation_result=validation_result,
                )
            return JSONResponse({"status": "fired", "event": event_type})
        except Exception as e:
            logger.error("Test event failed: %s", e, exc_info=True)
            return JSONResponse({"error": "Test event failed"}, status_code=500)

    app.include_router(router)

    # Serve static files (index.html)
    @app.get("/")
    async def index():
        index_file = _STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"message": "Web UI not available"}, status_code=404)
