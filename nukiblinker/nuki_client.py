"""Nuki Bridge HTTP API client — callback registration, device listing, activity log."""

from __future__ import annotations

import httpx

from nukiblinker.logging_config import get_logger
from nukiblinker.network import validate_local_ip

logger = get_logger("nuki_client")


class NukiClient:
    """Async client for the Nuki Bridge HTTP API."""

    def __init__(self, bridge_ip: str, bridge_port: int, api_token: str) -> None:
        safe_ip = validate_local_ip(bridge_ip, "Nuki Bridge")
        self._base = f"http://{safe_ip}:{bridge_port}"
        self._token = api_token

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    async def list_callbacks(self) -> list[dict]:
        """Return currently registered callbacks."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self._url("/callback/list"), params={"token": self._token})
            r.raise_for_status()
            data = r.json()
            return data.get("callbacks", [])

    async def register_callback(self, callback_url: str) -> int | None:
        """Register a callback URL. Returns the callback ID, or None if already exists.

        Idempotent: skips registration if the URL is already registered.
        """
        existing = await self.list_callbacks()
        for cb in existing:
            if cb.get("url") == callback_url:
                logger.info("Callback already registered (id=%s): %s", cb.get("id"), callback_url)
                return cb.get("id")

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                self._url("/callback/add"),
                params={"url": callback_url, "token": self._token},
            )
            r.raise_for_status()
            data = r.json()
            if data.get("success"):
                cb_id = data.get("id")
                logger.info("Callback registered (id=%s): %s", cb_id, callback_url)
                return cb_id
            logger.warning("Callback registration failed: %s", data.get("message", data))
            return None

    async def remove_callback(self, callback_id: int) -> bool:
        """Remove a callback by its ID."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                self._url("/callback/remove"),
                params={"id": callback_id, "token": self._token},
            )
            r.raise_for_status()
            data = r.json()
            ok = data.get("success", False)
            if ok:
                logger.info("Callback removed: id=%s", callback_id)
            else:
                logger.warning("Callback removal failed: %s", data.get("message", data))
            return ok

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    async def list_devices(self) -> list[dict]:
        """List paired Nuki devices (Openers + Smart Locks)."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self._url("/list"), params={"token": self._token})
            r.raise_for_status()
            return r.json()

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    async def get_last_log(self, nuki_id: int, count: int = 1) -> dict | None:
        """Fetch the latest activity log entry for a device.

        Returns the most recent log entry dict, or None if no logs.
        """
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                self._url("/log"),
                params={"nukiId": nuki_id, "count": count, "token": self._token},
            )
            r.raise_for_status()
            logs = r.json()
            if isinstance(logs, list) and logs:
                return logs[0]
            return None
