"""Nuki Web API client (optional, read-only).

The local Nuki Bridge ``/log`` endpoint cannot reliably identify *who* triggered
an action (and is unavailable on the software bridge). When a Nuki **Web API**
token is configured, this client queries the cloud activity log, which returns
``name``, ``trigger`` and ``source`` for each entry — letting NukiBlinker
resolve real names and tell how the door was opened.

This client is read-only: it never performs lock/unlock/open actions.
"""

from __future__ import annotations

import httpx

from nukiblinker.logging_config import get_logger

logger = get_logger("nuki_web_client")

# Nuki Web API activity-log source codes.
# source=2 means the action was performed by the door sensor (no user identity).
SOURCE_DOOR_SENSOR = 2

# Nuki Web API activity-log trigger codes (for human-readable logging).
TRIGGER_NAMES = {
    0: "system",
    1: "manual",
    2: "button",
    3: "automatic",
    4: "web",
    5: "app",
    6: "autoLock",
    7: "accessory",
}


class NukiWebClient:
    """Async client for the read-only parts of the Nuki Web API."""

    BASE = "https://api.nuki.io"

    def __init__(self, api_token: str, base_url: str | None = None) -> None:
        self._token = api_token
        self._base = (base_url or self.BASE).rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def get_recent_log(self, smartlock_id: int | None = None,
                             limit: int = 20) -> list[dict]:
        """Fetch recent activity-log entries from the Nuki Web API.

        Args:
            smartlock_id: Optional smartlock id to scope the query to.
            limit: Maximum number of entries to retrieve.

        Returns:
            List of log entry dicts (may be empty). Each entry typically
            contains ``smartlockId``, ``name``, ``action``, ``trigger``,
            ``state``, ``source`` and ``date``.
        """
        if smartlock_id is not None:
            url = f"{self._base}/smartlock/{smartlock_id}/log"
        else:
            url = f"{self._base}/smartlock/log"
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(url, headers=self._headers(), params={"limit": limit})
                r.raise_for_status()
                data = r.json()
                return data if isinstance(data, list) else []
        except Exception:
            logger.warning("Nuki Web API log request failed", exc_info=True)
            return []
