"""Google Nest / Chromecast audio playback via pychromecast."""

from __future__ import annotations

import asyncio
from functools import partial

from nukiblinker.logging_config import get_logger

logger = get_logger("chromecast")

try:
    import pychromecast
except ImportError:  # pragma: no cover
    pychromecast = None  # type: ignore[assignment]


class ChromecastClient:
    """Plays audio files on Chromecast / Google Nest speakers."""

    async def play(self, speaker_names: list[str], audio_url: str, volume: float = 0.5) -> None:
        """Cast an audio URL to all named speakers."""
        if pychromecast is None:
            logger.error("pychromecast not installed — cannot play audio")
            return

        loop = asyncio.get_running_loop()
        chromecasts = await loop.run_in_executor(
            None, partial(self._get_chromecasts_by_name, speaker_names),
        )
        for cc in chromecasts:
            await loop.run_in_executor(None, partial(self._play_on_device, cc, audio_url, volume))

    @staticmethod
    def _get_chromecasts_by_name(speaker_names: list[str]) -> list:
        """Blocking: discover and connect to named Chromecast devices."""
        import time
        from zeroconf import Zeroconf

        zconf = Zeroconf()
        browser = pychromecast.CastBrowser(
            pychromecast.SimpleCastListener(), zconf,
        )
        browser.start_discovery()
        time.sleep(5)

        targets = []
        for uuid, info in browser.devices.items():
            if info.friendly_name in speaker_names:
                cc = pychromecast.get_chromecast_from_cast_info(info, zconf)
                targets.append(cc)
        browser.stop_discovery()
        # Note: don't close zconf yet — chromecasts need it for communication
        return targets

    @staticmethod
    def _play_on_device(device, audio_url: str, volume: float) -> None:
        """Blocking helper — runs in executor."""
        device.wait()
        mc = device.media_controller

        # Save and set volume
        original_volume = device.status.volume_level if device.status else volume
        device.set_volume(volume)

        mc.play_media(audio_url, "audio/mp3")
        mc.block_until_active(timeout=10)

        # Wait for playback to finish
        import time

        for _ in range(60):
            if mc.status.player_is_idle:
                break
            time.sleep(0.5)

        # Restore volume
        device.set_volume(original_volume)
        logger.info("Played audio on %s", device.cast_info.friendly_name)

    async def list_speakers(self) -> list[dict]:
        """Discover Chromecast devices on LAN using CastBrowser."""
        if pychromecast is None:
            return []

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._discover_speakers)

    @staticmethod
    def _discover_speakers() -> list[dict]:
        """Blocking helper — runs in executor."""
        import time
        from zeroconf import Zeroconf

        zconf = Zeroconf()
        browser = pychromecast.CastBrowser(
            pychromecast.SimpleCastListener(), zconf,
        )
        browser.start_discovery()
        time.sleep(5)
        devices = [
            {
                "name": info.friendly_name,
                "ip": str(info.host),
                "port": info.port,
                "type": "chromecast",
            }
            for info in browser.devices.values()
        ]
        browser.stop_discovery()
        zconf.close()
        return devices
