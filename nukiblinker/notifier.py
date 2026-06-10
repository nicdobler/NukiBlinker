"""Orchestrates notification channels for a given event rule."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from nukiblinker import audio as audio_mod
from nukiblinker.logging_config import get_logger

if TYPE_CHECKING:
    from nukiblinker.config import AppConfig, EventRuleConfig

logger = get_logger("notifier")


def _build_audio_url(config: AppConfig, filename: str) -> str:
    """Build an HTTP URL for an audio file served by this instance."""
    from nukiblinker.config import get_public_host

    host = get_public_host(config)
    return f"http://{host}:{config.server.port}/audio/{filename}"


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
        # Wire up the audio registry so files get registered for HTTP serving
        app = getattr(clients, "_app", None)
        if app is not None:
            audio_mod._audio_registry = app.state.audio_files
        audio_path = audio_mod.get_audio(rule.audio, context or {})
        if not audio_path.exists():
            logger.warning("Audio file not found: %s — skipping speaker playback", audio_path)
        else:
            audio_url = _build_audio_url(config, audio_path.name)
            logger.info("Audio URL for speakers: %s", audio_url)
            chromecast = getattr(clients, "chromecast", None)
            airplay = getattr(clients, "airplay", None)
            if config.speakers.chromecast and chromecast is not None:
                tasks.append(asyncio.ensure_future(_trigger_chromecast(chromecast, config.speakers, audio_url)))
            if config.speakers.airplay and airplay is not None:
                # AirPlay uses pyatv stream_file — needs local path, not HTTP URL
                tasks.append(asyncio.ensure_future(_trigger_airplay(airplay, config.speakers, str(audio_path))))

    # HomeKit
    if rule.homekit and config.homekit.enabled:
        hk = getattr(clients, "homekit", None)
        if hk is not None:
            tasks.append(asyncio.ensure_future(_trigger_homekit(hk)))

    if not tasks:
        logger.info("No notification channels active for this rule")
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Notification channel failed: %s", r)


async def notify_with_actions(rule: EventRuleConfig, config: AppConfig, clients, context: dict | None = None) -> list[str]:
        """Fire all enabled notification channels and return detailed action results.

    Returns:
        List of action descriptions (e.g., ["Hue lights blinked", "TTS played"])
    """
    actions: list[str] = []
    tasks: list[asyncio.Task] = []

    # Hue lights
    if rule.blink.mode != "none" and (config.hue.lights or config.hue.groups):
        hue = getattr(clients, "hue", None)
        if hue is not None:
            tasks.append(asyncio.ensure_future(_trigger_hue_with_result(hue, config.hue, rule.blink, actions)))

    # Audio (chime or TTS)
    if rule.audio.enabled and rule.audio.mode != "none":
        # Wire up the audio registry so files get registered for HTTP serving
        app = getattr(clients, "_app", None)
        if app is not None:
            audio_mod._audio_registry = app.state.audio_files
        audio_path = audio_mod.get_audio(rule.audio, context or {})
        if not audio_path.exists():
            logger.warning("Audio file not found: %s — skipping speaker playback", audio_path)
            actions.append(f"Audio skipped: {audio_path.name} not found")
        else:
            audio_url = _build_audio_url(config, audio_path.name)
            logger.info("Audio URL for speakers: %s", audio_url)
            chromecast = getattr(clients, "chromecast", None)
            airplay = getattr(clients, "airplay", None)
            if config.speakers.chromecast and chromecast is not None:
                tasks.append(asyncio.ensure_future(_trigger_chromecast_with_result(chromecast, config.speakers, audio_url, actions)))
        if config.speakers.airplay and airplay is not None:
                # AirPlay uses pyatv stream_file — needs local path, not HTTP URL
                tasks.append(asyncio.ensure_future(_trigger_airplay_with_result(airplay, config.speakers, str(audio_path), actions)))
        # HomeKit
    if rule.homekit and config.homekit.enabled:
        hk = getattr(clients, "homekit", None)
        if hk is not None:
            tasks.append(asyncio.ensure_future(_trigger_homekit_with_result(hk, actions)))

    if not tasks:
        logger.info("No notification channels active for this rule")
        return actions

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Notification channel failed: %s", r)
            actions.append(f"Error: {str(r)}")

    return actions


async def _trigger_hue(hue_client, hue_config, blink_config) -> None:
    """Trigger Hue lights blink."""
    if blink_config.mode == "alert":
        await hue_client.trigger_alert(hue_config.lights, hue_config.groups)
    elif blink_config.mode == "custom":
        await hue_client.trigger_custom_blink(hue_config.lights, hue_config.groups, blink_config.custom)


async def _trigger_chromecast(cc_client, speakers_config, audio_url) -> None:
    """Play audio on Chromecast speakers."""
    await cc_client.play(speakers_config.chromecast, audio_url, speakers_config.volume)


async def _trigger_airplay(ap_client, speakers_config, audio_url) -> None:
    """Play audio on AirPlay speakers."""
    await ap_client.play(speakers_config.airplay, audio_url, speakers_config.volume)


async def _trigger_homekit(hk_service) -> None:
    """Fire HomeKit doorbell notification."""
    await hk_service.trigger_ring()


async def _trigger_hue_with_result(hue_client, hue_config, blink_config, actions: list[str]) -> None:
    """Trigger Hue lights blink and add action result."""
    try:
        if blink_config.mode == "alert":
            await hue_client.trigger_alert(hue_config.lights, hue_config.groups)
            actions.append("Hue lights blinked (alert)")
        elif blink_config.mode == "custom":
            await hue_client.trigger_custom_blink(hue_config.lights, hue_config.groups, blink_config.custom)
            actions.append(f"Hue lights blinked (custom: H={blink_config.custom.hue}, S={blink_config.custom.saturation}, B={blink_config.custom.brightness})")
        except Exception as e:
        actions.append(f"Hue lights failed: {str(e)}")
        raise


async def _trigger_chromecast_with_result(cc_client, speakers_config, audio_url, actions: list[str]) -> None:
    """Play audio on Chromecast speakers and add action result."""
    try:
        await cc_client.play(speakers_config.chromecast, audio_url, speakers_config.volume)
        actions.append(f"Audio played on Chromecast: {', '.join(speakers_config.chromecast)}")
    except Exception as e:
        actions.append(f"Chromecast failed: {str(e)}")
        raise


async def _trigger_airplay_with_result(ap_client, speakers_config, audio_url, actions: list[str]) -> None:
    """Play audio on AirPlay speakers and add action result."""
    try:
        await ap_client.play(speakers_config.airplay, audio_url, speakers_config.volume)
        actions.append(f"Audio played on AirPlay: {', '.join(speakers_config.airplay)}")
    except Exception as e:
        actions.append(f"AirPlay failed: {str(e)}")
        raise


async def _trigger_homekit_with_result(hk_service, actions: list[str]) -> None:
    """Fire HomeKit doorbell notification and add action result."""
    try:
        await hk_service.trigger_ring()
        actions.append("HomeKit doorbell notification sent")
    except Exception as e:
        actions.append(f"HomeKit failed: {str(e)}")
        raise
