"""Tests for nukiblinker.notifier — channel dispatch and failure isolation."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from nukiblinker.config import AppConfig, EventRuleConfig, BlinkConfig, AudioConfig
from nukiblinker.notifier import notify


def _make_clients(**overrides):
    clients = MagicMock()
    clients.hue = overrides.get("hue", AsyncMock())
    clients.chromecast = overrides.get("chromecast", AsyncMock())
    clients.airplay = overrides.get("airplay", AsyncMock())
    clients.homekit = overrides.get("homekit", AsyncMock())
    return clients


class TestNotify:
    @pytest.mark.asyncio
    async def test_fires_hue_alert(self):
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="alert"),
            audio=AudioConfig(enabled=False),
            homekit=False,
        )
        cfg = AppConfig()
        cfg.hue.lights = [1]
        clients = _make_clients()

        await notify(rule, cfg, clients)
        clients.hue.trigger_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_fires_audio_tts(self, tmp_path):
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="none"),
            audio=AudioConfig(enabled=True, mode="tts", message="hola {name}"),
            homekit=False,
        )
        cfg = AppConfig()
        cfg.speakers.chromecast = ["Kitchen"]
        clients = _make_clients()

        fake_path = tmp_path / "audio.mp3"
        fake_path.write_bytes(b"audio")

        with patch("nukiblinker.notifier.audio_mod") as mock_audio:
            mock_audio.get_audio.return_value = fake_path
            await notify(rule, cfg, clients, context={"name": "Nico"})
            mock_audio.get_audio.assert_called_once()
            clients.chromecast.play.assert_called_once()

    @pytest.mark.asyncio
    async def test_fires_homekit(self):
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="none"),
            audio=AudioConfig(enabled=False),
            homekit=True,
        )
        cfg = AppConfig()
        cfg.homekit.enabled = True
        clients = _make_clients()

        await notify(rule, cfg, clients)
        clients.homekit.trigger_ring.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_homekit_when_disabled(self):
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="none"),
            audio=AudioConfig(enabled=False),
            homekit=True,
        )
        cfg = AppConfig()
        cfg.homekit.enabled = False
        clients = _make_clients()

        await notify(rule, cfg, clients)
        clients.homekit.trigger_ring.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_isolation(self):
        """One channel failing should not block others."""
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="alert"),
            audio=AudioConfig(enabled=False),
            homekit=True,
        )
        cfg = AppConfig()
        cfg.hue.lights = [1]
        cfg.homekit.enabled = True

        hue = AsyncMock()
        hue.trigger_alert.side_effect = Exception("hue down")
        homekit = AsyncMock()
        clients = _make_clients(hue=hue, homekit=homekit)

        # Should not raise despite hue failure
        await notify(rule, cfg, clients)
        homekit.trigger_ring.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_channels_fires_nothing(self):
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="none"),
            audio=AudioConfig(enabled=False),
            homekit=False,
        )
        cfg = AppConfig()
        clients = _make_clients()
        await notify(rule, cfg, clients)  # Should not raise

    @pytest.mark.asyncio
    async def test_fires_both_speaker_types(self, tmp_path):
        rule = EventRuleConfig(
            blink=BlinkConfig(mode="none"),
            audio=AudioConfig(enabled=True, mode="chime"),
            homekit=False,
        )
        cfg = AppConfig()
        cfg.speakers.chromecast = ["Nest"]
        cfg.speakers.airplay = ["HomePod"]
        clients = _make_clients()

        fake_path = tmp_path / "chime.mp3"
        fake_path.write_bytes(b"chime")

        with patch("nukiblinker.notifier.audio_mod") as mock_audio:
            mock_audio.get_audio.return_value = fake_path
            await notify(rule, cfg, clients)
            clients.chromecast.play.assert_called_once()
            clients.airplay.play.assert_called_once()
