"""Apple HomePod / AirPlay 2 audio playback via pyatv."""

from __future__ import annotations

import asyncio
import ipaddress

from nukiblinker.logging_config import get_logger

logger = get_logger("airplay")

try:
    import pyatv
except ImportError:  # pragma: no cover
    pyatv = None  # type: ignore[assignment]


def _is_ip_address(value: str) -> bool:
    """Check if a string is a valid IP address."""
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


class AirPlayClient:
    """Plays audio files on AirPlay 2 / HomePod speakers."""

    async def play(self, speaker_entries: list[str], audio_path: str, volume: float = 0.5) -> None:
        """Stream an audio file to speakers identified by name or IP address."""
        if pyatv is None:
            logger.error("pyatv not installed — cannot play audio")
            return

        loop = asyncio.get_running_loop()

        # Separate IP addresses from device names
        ips = [s for s in speaker_entries if _is_ip_address(s)]
        names = [s for s in speaker_entries if not _is_ip_address(s)]

        matched = []

        # Scan IPs via unicast (no mDNS port 5353 binding needed)
        for ip in ips:
            try:
                devices = await pyatv.scan(loop, hosts=[ip], timeout=10)
                if devices:
                    matched.extend(devices)
                    logger.info("Found AirPlay device at %s: %s", ip, devices[0].name)
                else:
                    logger.warning("No AirPlay device found at %s", ip)
            except OSError as e:
                logger.warning("AirPlay scan failed for %s: %s", ip, e)

        # Scan by name via mDNS broadcast (may fail with port 5353 conflict)
        if names:
            try:
                devices = await pyatv.scan(loop)
                name_matched = [d for d in devices if d.name in names]
                matched.extend(name_matched)
                if not name_matched:
                    logger.warning(
                        "No AirPlay speakers found matching names: %s (discovered %d total)",
                        names, len(devices),
                    )
            except OSError:
                logger.warning(
                    "Cannot bind mDNS port 5353 — name-based AirPlay scan unavailable. "
                    "Use IP addresses instead, or stop the host mDNS service."
                )

        if not matched:
            logger.warning("No AirPlay speakers found matching: %s", speaker_entries)
            return
        for dev in matched:
            await self._play_on_device(dev, audio_path, volume)

    async def _play_on_device(self, device_config, audio_path: str, volume: float) -> None:
        """Connect to a single device and stream audio."""
        logger.info("Connecting to AirPlay device: %s (%s)", device_config.name, device_config.address)
        atv = await pyatv.connect(device_config, asyncio.get_running_loop())
        try:
            # Set volume if the device supports it
            if hasattr(atv, "audio") and atv.audio is not None:
                await atv.audio.set_volume(volume * 100)  # pyatv uses 0-100 scale
            logger.info("Streaming %s to %s", audio_path, device_config.name)
            await atv.stream.stream_file(audio_path)
            logger.info("Playback finished on %s", device_config.name)
        except Exception:
            logger.error("AirPlay playback failed on %s", device_config.name, exc_info=True)
        finally:
            atv.close()

    async def list_speakers(self) -> list[dict]:
        """Discover AirPlay 2 devices on LAN."""
        if pyatv is None:
            return []

        try:
            devices = await pyatv.scan(asyncio.get_running_loop())
        except OSError:
            logger.warning(
                "Cannot bind mDNS port 5353 — AirPlay discovery unavailable. "
                "Enter speaker IPs manually in the config."
            )
            return []

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
