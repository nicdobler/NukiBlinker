"""Orchestrates notification channels for a given event rule."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nukiblinker import audio as audio_mod
from nukiblinker.logging_config import get_logger

if TYPE_CHECKING:
    from nukiblinker.config import AppConfig, EventRuleConfig

logger = get_logger("notifier")


async def notify(rule: EventRuleConfig, config: AppConfig, clients, context: dict | None = None) -> None:
    """Fire all enabled notification channels for the given event rule.

    Each channel runs concurrently; failures are logged but do not block other channels.
    """
    tasks: list[asyncio.Task] = []

    # Hue lights
    if rule.blink.mode != "none" and (config.hue.lights or config.hue.groups):
        hue = getattr(clients, "hue", None)
        if hue is not None:
            tasks.append(asyncio.ensure_future(_trigger_hue(hue, config.hue, rule.blink)))

    # Audio (chime or TTS)
    if rule.audio.enabled and rule.audio.mode != "none":
        audio_path = audio_mod.get_audio(rule.audio, context or {})
        chromecast = getattr(clients, "chromecast", None)
        airplay = getattr(clients, "airplay", None)
        if config.speakers.chromecast and chromecast is not None:
            tasks.append(asyncio.ensure_future(_trigger_chromecast(chromecast, config.speakers, audio_path)))
        if config.speakers.airplay and airplay is not None:
            tasks.append(asyncio.ensure_future(_trigger_airplay(airplay, config.speakers, audio_path)))

    # HomeKit
    if rule.homekit and config.homekit.enabled:
        hk = getattr(clients, "homekit", None)
        if hk is not None:
            tasks.append(asyncio.ensure_future(_trigger_homekit(hk)))

    if not tasks:
        logger.debug("No notification channels to fire for this rule")
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Notification channel failed: %s", r)


async def _trigger_hue(hue_client, hue_config, blink_config) -> None:
    """Trigger Hue lights blink."""
    if blink_config.mode == "alert":
        await hue_client.trigger_alert(hue_config.lights, hue_config.groups)
    elif blink_config.mode == "custom":
        await hue_client.trigger_custom_blink(hue_config.lights, blink_config.custom)


async def _trigger_chromecast(cc_client, speakers_config, audio_path) -> None:
    """Play audio on Chromecast speakers."""
    await cc_client.play(speakers_config.chromecast, str(audio_path), speakers_config.volume)


async def _trigger_airplay(ap_client, speakers_config, audio_path) -> None:
    """Play audio on AirPlay speakers."""
    await ap_client.play(speakers_config.airplay, str(audio_path), speakers_config.volume)


async def _trigger_homekit(hk_service) -> None:
    """Fire HomeKit doorbell notification."""
    await hk_service.trigger_ring()
