"""Auto-discovery for Nuki Bridge, Hue Bridge, Chromecast, and AirPlay speakers."""

from __future__ import annotations

import asyncio

import httpx

from nukiblinker.logging_config import get_logger

logger = get_logger("discovery")


async def discover_nuki_bridges() -> list[dict]:
    """Discover Nuki Bridges via the Nuki Cloud discovery endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("https://api.nuki.io/discover/bridges")
            r.raise_for_status()
            bridges = r.json().get("bridges", [])
            return [
                {"name": f"Nuki Bridge {b.get('bridgeId', '?')}", "ip": b.get("ip", ""), "port": b.get("port", 8080)}
                for b in bridges
            ]
    except Exception:
        logger.warning("Nuki Bridge discovery failed", exc_info=True)
        return []


async def discover_hue_bridges() -> list[dict]:
    """Discover Hue Bridges via the Philips discovery endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("https://discovery.meethue.com")
            r.raise_for_status()
            bridges = r.json()
            return [
                {"name": f"Hue Bridge ({b.get('id', '?')})", "ip": b.get("internalipaddress", ""), "port": 80}
                for b in bridges
            ]
    except Exception:
        logger.warning("Hue Bridge discovery failed", exc_info=True)
        return []


async def discover_chromecast_speakers() -> list[dict]:
    """Discover Chromecast / Google Nest speakers on LAN."""
    try:
        from nukiblinker.chromecast_client import ChromecastClient

        client = ChromecastClient()
        return await client.list_speakers()
    except Exception:
        logger.warning("Chromecast discovery failed", exc_info=True)
        return []


async def discover_airplay_speakers() -> list[dict]:
    """Discover AirPlay 2 / HomePod speakers on LAN."""
    try:
        from nukiblinker.airplay_client import AirPlayClient

        client = AirPlayClient()
        return await client.list_speakers()
    except Exception:
        logger.warning("AirPlay discovery failed", exc_info=True)
        return []
