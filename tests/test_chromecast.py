"""Tests for nukiblinker.chromecast_client — mock pychromecast."""

from unittest.mock import MagicMock, patch

import pytest

from nukiblinker.chromecast_client import ChromecastClient, _is_ip_address


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


class TestIsIpAddress:
    def test_valid_ipv4(self):
        assert _is_ip_address("192.168.1.50")

    def test_valid_ipv6(self):
        assert _is_ip_address("::1")

    def test_name_is_not_ip(self):
        assert not _is_ip_address("Living Room")

    def test_empty_string(self):
        assert not _is_ip_address("")


class TestPlay:
    @pytest.mark.asyncio
    async def test_plays_on_matching_speaker_by_name(self, client):
        cc = _make_cc("Kitchen")

        with patch.object(ChromecastClient, "_get_chromecasts_by_name", return_value=[cc]):
            await client.play(["Kitchen"], "http://audio.mp3", 0.7)
            cc.set_volume.assert_called()
            cc.media_controller.play_media.assert_called_once_with("http://audio.mp3", "audio/mp3")

    @pytest.mark.asyncio
    async def test_plays_on_speaker_by_ip(self, client):
        cc = _make_cc("Kitchen")

        with patch.object(ChromecastClient, "_connect_by_ip", return_value=cc) as mock_ip:
            await client.play(["192.168.1.50"], "http://audio.mp3", 0.7)
            mock_ip.assert_called_once_with("192.168.1.50")
            cc.media_controller.play_media.assert_called_once_with("http://audio.mp3", "audio/mp3")

    @pytest.mark.asyncio
    async def test_mixed_ip_and_name(self, client):
        cc_ip = _make_cc("Kitchen")
        cc_name = _make_cc("Living Room")

        with (
            patch.object(ChromecastClient, "_connect_by_ip", return_value=cc_ip),
            patch.object(ChromecastClient, "_get_chromecasts_by_name", return_value=[cc_name]),
        ):
            await client.play(["192.168.1.50", "Living Room"], "http://audio.mp3", 0.5)
            cc_ip.media_controller.play_media.assert_called_once()
            cc_name.media_controller.play_media.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_non_matching_speaker(self, client):
        with patch.object(ChromecastClient, "_get_chromecasts_by_name", return_value=[]):
            await client.play(["Kitchen"], "http://audio.mp3", 0.5)

    @pytest.mark.asyncio
    async def test_ip_connect_failure_returns_none(self, client):
        with patch.object(ChromecastClient, "_connect_by_ip", return_value=None):
            await client.play(["192.168.1.50"], "http://audio.mp3", 0.5)


class TestListSpeakers:
    @pytest.mark.asyncio
    async def test_returns_discovered_speakers(self, client):
        speakers = [
            {"name": "Living Room", "ip": "10.0.0.5", "port": 8009, "type": "chromecast"},
            {"name": "Kitchen", "ip": "10.0.0.6", "port": 8009, "type": "chromecast"},
        ]

        with patch.object(ChromecastClient, "_discover_speakers", return_value=speakers):
            result = await client.list_speakers()
            assert len(result) == 2
            assert result[0]["name"] == "Living Room"
            assert result[0]["type"] == "chromecast"
