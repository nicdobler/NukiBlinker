"""Philips Hue Bridge v1 REST API client — light control, pairing, discovery."""

from __future__ import annotations

from typing import Any

import httpx

from nukiblinker.logging_config import get_logger
from nukiblinker.network import validate_local_ip

logger = get_logger("hue_client")


class HueClient:
    """Async client for the Philips Hue Bridge v1 REST API."""

    def __init__(self, bridge_ip: str, api_key: str) -> None:
        safe_ip = validate_local_ip(bridge_ip, "Hue Bridge")
        self._base = f"http://{safe_ip}/api/{api_key}"
        self._bridge_ip = safe_ip
        self._api_key = api_key

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    # ------------------------------------------------------------------
    # Connection check
    # ------------------------------------------------------------------

    async def check_connection(self) -> dict:
        """Verify the API key is valid by reading the bridge config.

        Returns a dict with:
        - ``connected``: True if the bridge accepted the API key.
        - ``name``: Bridge friendly name (when connected).
        - ``error``: Error description (when not connected).
        """
        url = f"http://{self._bridge_ip}/api/{self._api_key}/config"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(url)
                r.raise_for_status()
                data = r.json()
                # Hue returns a list with an error object for invalid keys
                if isinstance(data, list):
                    err = data[0].get("error", {}) if data else {}
                    return {
                        "connected": False,
                        "error": err.get("description", "Unknown error"),
                    }
                # Valid key → full config dict returned
                return {
                    "connected": True,
                    "name": data.get("name", "Hue Bridge"),
                    "api_version": data.get("apiversion", ""),
                    "mac": data.get("mac", ""),
                }
        except httpx.ConnectError:
            return {"connected": False, "error": "Bridge unreachable — cannot connect"}
        except (httpx.ConnectTimeout, httpx.ReadTimeout):
            return {"connected": False, "error": "Bridge unreachable — connection timed out"}
        except Exception as exc:
            logger.warning("Unexpected error checking Hue connection: %s", exc, exc_info=True)
            return {"connected": False, "error": "Unexpected error checking bridge connection"}

    # ------------------------------------------------------------------
    # Alert mode
    # ------------------------------------------------------------------

    async def trigger_alert(
        self, light_ids: list[int], group_ids: list[int], alert: str = "lselect",
    ) -> None:
        """Send a Hue built-in alert to lights and groups.

        ``alert`` is ``"select"`` (single breathe cycle, blink mode ``short``)
        or ``"lselect"`` (~15-second breathe cycle, blink mode ``long``). The
        Hue bridge restores each light's previous state when the effect ends.
        """
        body = {"alert": alert}
        async with httpx.AsyncClient(timeout=10) as c:
            for lid in light_ids:
                r = await c.put(self._url(f"/lights/{lid}/state"), json=body)
                r.raise_for_status()
                logger.debug("Alert sent to light %s", lid)
            for gid in group_ids:
                r = await c.put(self._url(f"/groups/{gid}/action"), json=body)
                r.raise_for_status()
                logger.debug("Alert sent to group %s", gid)

    # ------------------------------------------------------------------
    # Low-level state primitives
    #
    # Retained for a possible future hardcoded blink pattern (no config). They
    # are not used by the current dispatch path, which relies on the built-in
    # ``select``/``lselect`` alerts whose state restore is handled by the bridge.
    # ------------------------------------------------------------------

    async def get_light_state(self, light_id: int) -> dict[str, Any]:
        """Read the current state of a light."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self._url(f"/lights/{light_id}"))
            r.raise_for_status()
            return r.json().get("state", {})

    async def set_light_state(self, light_id: int, state: dict) -> None:
        """Set a light to a specific state."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.put(self._url(f"/lights/{light_id}/state"), json=state)
            r.raise_for_status()

    async def _set_group_action(self, group_id: int, action: dict) -> None:
        """Set a group action (same state format as lights, but different endpoint)."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.put(self._url(f"/groups/{group_id}/action"), json=action)
            r.raise_for_status()

    # ------------------------------------------------------------------
    # Discovery / listing
    # ------------------------------------------------------------------

    async def list_lights(self) -> dict:
        """Return all lights from the Hue Bridge."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self._url("/lights"))
            r.raise_for_status()
            return r.json()

    async def list_groups(self) -> dict:
        """Return all groups from the Hue Bridge."""
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(self._url("/groups"))
            r.raise_for_status()
            return r.json()

    # ------------------------------------------------------------------
    # Pairing
    # ------------------------------------------------------------------

    @staticmethod
    async def pair(bridge_ip: str) -> str | None:
        """Create an API key on the Hue Bridge (press button first)."""
        safe_ip = validate_local_ip(bridge_ip, "Hue Bridge")
        url = f"http://{safe_ip}/api"
        body = {"devicetype": "nukiblinker"}
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json=body)
            r.raise_for_status()
            result = r.json()
            if isinstance(result, list) and result:
                entry = result[0]
                if "success" in entry:
                    api_key = entry["success"].get("username", "")
                    logger.info("Hue Bridge paired — API key obtained")
                    return api_key
                if "error" in entry:
                    logger.warning("Hue pairing error: %s", entry["error"].get("description", entry["error"]))
            return None
