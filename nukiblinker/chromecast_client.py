"""Google Nest / Chromecast audio playback via pychromecast."""

from __future__ import annotations

import asyncio
import ipaddress
from functools import partial
from threading import Lock

from nukiblinker.logging_config import get_logger

logger = get_logger("chromecast")

try:
    import pychromecast
except ImportError:  # pragma: no cover
    pychromecast = None  # type: ignore[assignment]


def _is_ip_address(value: str) -> bool:
    """Check if a string is a valid IP address."""
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


class ChromecastClient:
    """Plays audio files on Chromecast / Google Nest speakers."""

    def __init__(self) -> None:
        # mDNS discovery resources (browser, Zeroconf) created during a play()
        # call, drained and closed once playback finishes to avoid leaking
        # sockets/threads on every event.
        self._discovery_cleanup: list = []
        self._cleanup_lock = Lock()

    async def play(self, speaker_entries: list[str], audio_url: str, volume: float = 0.5) -> None:
        """Cast an audio URL to speakers identified by name or IP address."""
        if pychromecast is None:
            logger.error("pychromecast not installed — cannot play audio")
            return

        loop = asyncio.get_running_loop()

        # Separate IP addresses from device names
        ips = [s for s in speaker_entries if _is_ip_address(s)]
        names = [s for s in speaker_entries if not _is_ip_address(s)]

        targets = []

        try:
            # Connect to IPs directly (no mDNS broadcast needed)
            for ip in ips:
                cc = await loop.run_in_executor(None, partial(self._connect_by_ip, ip))
                if cc is not None:
                    targets.append(cc)

            # Connect by name via mDNS (may fail with port 5353 conflict)
            if names:
                mdns_targets = await loop.run_in_executor(
                    None, partial(self._get_chromecasts_by_name, names),
                )
                targets.extend(mdns_targets)

            if not targets:
                logger.warning("No Chromecast speakers found matching: %s", speaker_entries)
                return
            for cc in targets:
                await loop.run_in_executor(None, partial(self._play_on_device, cc, audio_url, volume))
        finally:
            # Release per-call resources: cast socket clients and mDNS discovery.
            for cc in targets:
                await loop.run_in_executor(None, partial(self._disconnect_device, cc))
            await loop.run_in_executor(None, self._drain_discovery_cleanup)

    @staticmethod
    def _connect_by_ip(ip: str):
        """Blocking: connect to a Chromecast by IP address (no mDNS broadcast)."""
        try:
            cc = pychromecast.get_chromecast_from_host(
                (ip, None, None, None, None),
                timeout=10,
            )
            logger.info("Connected to Chromecast at %s", ip)
            return cc
        except OSError as e:
            if "5353" in str(e) or "Address already in use" in str(e):
                logger.error(
                    "Port 5353 conflict prevents Chromecast connection at %s. "
                    "Stop the host mDNS service — see README troubleshooting.",
                    ip,
                )
            else:
                logger.warning("OS error connecting to Chromecast at %s: %s", ip, e)
            return None
        except Exception:
            logger.warning("Failed to connect to Chromecast at %s", ip, exc_info=True)
            return None

    def _get_chromecasts_by_name(self, speaker_names: list[str]) -> list:
        """Blocking: discover and connect to named Chromecast devices via mDNS.

        The created browser/Zeroconf are registered for cleanup by ``play()``
        once playback finishes (zeroconf must stay open during playback).
        """
        import time

        try:
            from zeroconf import Zeroconf

            zconf = Zeroconf()
        except OSError:
            logger.warning(
                "Cannot bind mDNS port 5353 — name-based Chromecast discovery unavailable. "
                "Use IP addresses instead, or stop the host mDNS service."
            )
            return []

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
        # Defer closing zconf until playback completes (chromecasts need it).
        with self._cleanup_lock:
            self._discovery_cleanup.append((browser, zconf))
        return targets

    def _drain_discovery_cleanup(self) -> None:
        """Blocking: stop discovery and close any pending Zeroconf instances."""
        with self._cleanup_lock:
            pending = self._discovery_cleanup
            self._discovery_cleanup = []
        for browser, zconf in pending:
            try:
                browser.stop_discovery()
            except Exception:
                logger.debug("Error stopping Chromecast discovery", exc_info=True)
            try:
                zconf.close()
            except Exception:
                logger.debug("Error closing Zeroconf instance", exc_info=True)

    @staticmethod
    def _disconnect_device(device) -> None:
        """Blocking: tear down a cast socket client to free its background thread."""
        try:
            device.disconnect()
        except Exception:
            logger.debug("Error disconnecting Chromecast device", exc_info=True)

    @staticmethod
    def _play_on_device(device, audio_url: str, volume: float) -> None:
        """Blocking helper — runs in executor."""
        device.wait()
        mc = device.media_controller

        # Save and set volume
        original_volume = volume
        if device.status and device.status.volume_level is not None:
            original_volume = device.status.volume_level
        device.set_volume(volume)

        content_type = "audio/wav" if audio_url.endswith(".wav") else "audio/mp3"
        logger.info(
            "Casting %s (type=%s) to %s",
            audio_url, content_type, device.cast_info.friendly_name,
        )
        mc.play_media(audio_url, content_type)
        mc.block_until_active(timeout=10)

        # Wait for playback to finish
        import time

        for _ in range(60):
            if mc.status.player_is_idle:
                break
            time.sleep(0.5)

        # Restore volume
        device.set_volume(original_volume)
        logger.info("Playback finished on %s", device.cast_info.friendly_name)

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

        try:
            from zeroconf import Zeroconf

            zconf = Zeroconf()
        except OSError:
            logger.warning(
                "Cannot bind mDNS port 5353 — Chromecast discovery unavailable. "
                "Enter speaker IPs manually in the config."
            )
            return []

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
        logger.info("Chromecast discovery found %d device(s)", len(devices))
        return devices
