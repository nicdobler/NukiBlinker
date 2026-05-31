"""Apple HomePod / AirPlay 2 audio playback via pyatv."""

from __future__ import annotations

import asyncio

from nukiblinker.logging_config import get_logger

logger = get_logger("airplay")

try:
    import pyatv
except ImportError:  # pragma: no cover
    pyatv = None  # type: ignore[assignment]


class AirPlayClient:
    """Plays audio files on AirPlay 2 / HomePod speakers."""

    async def play(self, speaker_names: list[str], audio_path: str, volume: float = 0.5) -> None:
        """Stream an audio file to all named AirPlay speakers."""
        if pyatv is None:
            logger.error("pyatv not installed — cannot play audio")
            return

        devices = await pyatv.scan(asyncio.get_running_loop())
        matched = [d for d in devices if d.name in speaker_names]
        if not matched:
            logger.warning("No AirPlay speakers found matching: %s (discovered %d total)", speaker_names, len(devices))
            return
        for dev in matched:
            await self._play_on_device(dev, audio_path, volume)

    async def _play_on_device(self, device_config, audio_path: str, volume: float) -> None:
        """Connect to a single device and stream audio."""
        atv = await pyatv.connect(device_config, asyncio.get_running_loop())
        try:
            audio_iface = atv.stream
            await audio_iface.stream_file(audio_path)
            logger.info("Played audio on %s", device_config.name)
        finally:
            atv.close()

    async def list_speakers(self) -> list[dict]:
        """Discover AirPlay 2 devices on LAN."""
        if pyatv is None:
            return []

        devices = await pyatv.scan(asyncio.get_running_loop())
        result = [
            {
                "name": d.name,
                "ip": str(d.address),
                "port": 7000,
                "type": "airplay",
            }
            for d in devices
        ]
        logger.info("AirPlay discovery found %d device(s)", len(result))
        return result
