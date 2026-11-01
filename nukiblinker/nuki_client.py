"""Nuki Bridge HTTP API client — callback registration, device listing, activity log."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from nukiblinker.logging_config import get_logger
from nukiblinker.network import validate_local_ip

logger = get_logger("nuki_client")

# Bridge allows at most 3 callbacks; one extra iteration of headroom for the
# hard-reset removal loop in case a remove silently fails.
_MAX_RESET_REMOVALS = 4


def _is_own_callback(url: str) -> bool:
    """Return True if *url* points at NukiBlinker's callback path (any host/port)."""
    return urlparse(url).path.rstrip("/") == "/nuki/callback"


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
        return await self._add_callback(callback_url)

    async def _add_callback(self, callback_url: str) -> int | None:
        """`GET /callback/add` — always registers (not idempotent).

        Returns the new callback ID, or None on a Bridge ``success: false``.
        """
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

    async def reset_callbacks(self, callback_url: str) -> dict:
        """Hard reset: remove every NukiBlinker callback, re-register, verify.

        Removes any callback whose URL path is ``/nuki/callback`` on any
        host/port — this also clears stale registrations pointing at old IPs —
        then re-adds *callback_url* and re-lists to confirm the Bridge stored
        it. Other integrations' callbacks are left untouched.

        Bridge callback ids may be positional, so the list is re-fetched after
        every removal. HTTP errors propagate via ``raise_for_status``.

        Returns ``{"removed": [...], "callback_id": int|None,
        "callback_url": str, "verified": bool}``.
        """
        removed: list[int] = []
        for _ in range(_MAX_RESET_REMOVALS):
            cbs = await self.list_callbacks()
            own = next((cb for cb in cbs if _is_own_callback(cb.get("url", ""))), None)
            if own is None:
                break
            cb_id = own.get("id")
            logger.info("Hard reset: removing callback id=%s url=%s", cb_id, own.get("url"))
            await self.remove_callback(cb_id)
            removed.append(cb_id)
        else:
            logger.warning(
                "Hard reset: NukiBlinker callbacks still present after %s removals",
                _MAX_RESET_REMOVALS,
            )

        cb_id = await self._add_callback(callback_url)

        final = await self.list_callbacks()
        match = next((cb for cb in final if cb.get("url") == callback_url), None)
        verified = match is not None
        if match is not None and match.get("id") is not None:
            cb_id = match.get("id")
        logger.info("Hard reset complete: id=%s verified=%s url=%s", cb_id, verified, callback_url)
        if not verified:
            logger.warning(
                "Hard reset: callback not present on Bridge after re-registration: %s",
                callback_url,
            )
        return {
            "removed": removed,
            "callback_id": cb_id,
            "callback_url": callback_url,
            "verified": verified,
        }

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
