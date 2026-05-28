"""Tests for nukiblinker.chromecast_client — mock pychromecast."""

from unittest.mock import MagicMock, patch

import pytest

from nukiblinker.chromecast_client import ChromecastClient


@pytest.fixture
def client():
    return ChromecastClient()


def _make_cc(name="Living Room", host="10.0.0.5", port=8009):
    cc = MagicMock()
    cc.cast_info.friendly_name = name
    cc.cast_info.host = host
    cc.cast_info.port = port
    cc.status.volume_level = 0.3
    cc.media_controller.status.player_is_idle = True
    return cc


class TestPlay:
    @pytest.mark.asyncio
    async def test_plays_on_matching_speaker(self, client):
        cc = _make_cc("Kitchen")
        browser = MagicMock()

        with patch("nukiblinker.chromecast_client.pychromecast") as mock_pycc:
            mock_pycc.get_chromecasts.return_value = ([cc], browser)
            await client.play(["Kitchen"], "http://audio.mp3", 0.7)
            cc.set_volume.assert_called()
            cc.media_controller.play_media.assert_called_once_with("http://audio.mp3", "audio/mp3")

    @pytest.mark.asyncio
    async def test_skips_non_matching_speaker(self, client):
        cc = _make_cc("Bedroom")
        browser = MagicMock()

        with patch("nukiblinker.chromecast_client.pychromecast") as mock_pycc:
            mock_pycc.get_chromecasts.return_value = ([cc], browser)
            await client.play(["Kitchen"], "http://audio.mp3", 0.5)
            cc.media_controller.play_media.assert_not_called()


class TestListSpeakers:
    @pytest.mark.asyncio
    async def test_returns_discovered_speakers(self, client):
        cc1 = _make_cc("Living Room", "10.0.0.5", 8009)
        cc2 = _make_cc("Kitchen", "10.0.0.6", 8009)
        browser = MagicMock()

        with patch("nukiblinker.chromecast_client.pychromecast") as mock_pycc:
            mock_pycc.get_chromecasts.return_value = ([cc1, cc2], browser)
            result = await client.list_speakers()
            assert len(result) == 2
            assert result[0]["name"] == "Living Room"
            assert result[0]["type"] == "chromecast"
            browser.stop_discovery.assert_called_once()
