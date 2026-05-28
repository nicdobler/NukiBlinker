"""Philips Hue Bridge v1 REST API client — light control, pairing, discovery."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from nukiblinker.logging_config import get_logger

logger = get_logger("hue_client")


class HueClient:
    """Async client for the Philips Hue Bridge v1 REST API."""

    def __init__(self, bridge_ip: str, api_key: str) -> None:
        self._base = f"http://{bridge_ip}/api/{api_key}"
        self._bridge_ip = bridge_ip
        self._api_key = api_key

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    # ------------------------------------------------------------------
    # Alert mode
    # ------------------------------------------------------------------

    async def trigger_alert(self, light_ids: list[int], group_ids: list[int]) -> None:
        """Send Hue built-in lselect alert to lights and groups."""
        body = {"alert": "lselect"}
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
    # Custom blink
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

    async def trigger_custom_blink(self, light_ids: list[int], blink_config) -> None:
        """Custom blink: save state → flash loop → restore."""
        saved_states: dict[int, dict] = {}

        # Save current states
        for lid in light_ids:
            try:
                saved_states[lid] = await self.get_light_state(lid)
            except Exception:
                logger.warning("Could not save state for light %s", lid, exc_info=True)

        flash_state = {
            "on": True,
            "hue": blink_config.hue,
            "sat": blink_config.saturation,
            "bri": blink_config.brightness,
            "transitiontime": 0,
        }
        off_state = {"on": False, "transitiontime": 0}
        interval_s = blink_config.interval_ms / 1000.0

        # Flash loop
        for _ in range(blink_config.flashes):
            for lid in light_ids:
                try:
                    await self.set_light_state(lid, flash_state)
                except Exception:
                    logger.warning("Flash on failed for light %s", lid, exc_info=True)
            await asyncio.sleep(interval_s)
            for lid in light_ids:
                try:
                    await self.set_light_state(lid, off_state)
                except Exception:
                    logger.warning("Flash off failed for light %s", lid, exc_info=True)
            await asyncio.sleep(interval_s)

        # Restore
        for lid, orig in saved_states.items():
            restore = {
                "on": orig.get("on", False),
                "bri": orig.get("bri", 254),
                "hue": orig.get("hue", 0),
                "sat": orig.get("sat", 0),
                "transitiontime": 4,
            }
            try:
                await self.set_light_state(lid, restore)
                logger.debug("Restored light %s", lid)
            except Exception:
                logger.warning("Could not restore light %s", lid, exc_info=True)

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
        url = f"http://{bridge_ip}/api"
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
