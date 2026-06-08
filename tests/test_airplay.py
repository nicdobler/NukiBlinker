"""Tests for nukiblinker.airplay_client — mock pyatv."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from nukiblinker.airplay_client import AirPlayClient


@pytest.fixture
def client():
    return AirPlayClient()


def _make_device(name="HomePod", address="10.0.0.10"):
    dev = MagicMock()
    dev.name = name
    dev.address = address
    return dev


class TestPlay:
    @pytest.mark.asyncio
    async def test_plays_on_matching_speaker_by_name(self, client):
        dev = _make_device("HomePod")
        atv = AsyncMock()
        atv.stream.stream_file = AsyncMock()

        with patch("nukiblinker.airplay_client.pyatv") as mock_pyatv:
            mock_pyatv.scan = AsyncMock(return_value=[dev])
            mock_pyatv.connect = AsyncMock(return_value=atv)
            await client.play(["HomePod"], "/tmp/test.mp3", 0.5)
            atv.stream.stream_file.assert_called_once_with("/tmp/test.mp3")
            atv.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plays_on_speaker_by_ip(self, client):
        dev = _make_device("HomePod", "10.0.0.10")
        atv = AsyncMock()
        atv.stream.stream_file = AsyncMock()

        with patch("nukiblinker.airplay_client.pyatv") as mock_pyatv:
            mock_pyatv.scan = AsyncMock(return_value=[dev])
            mock_pyatv.connect = AsyncMock(return_value=atv)
            await client.play(["10.0.0.10"], "/tmp/test.mp3", 0.5)
            # Should use unicast scan with hosts=[ip]
            mock_pyatv.scan.assert_called_once()
            call_kwargs = mock_pyatv.scan.call_args
            assert call_kwargs.kwargs.get("hosts") == ["10.0.0.10"]
            atv.stream.stream_file.assert_called_once_with("/tmp/test.mp3")
            atv.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_non_matching_speaker(self, client):
        dev = _make_device("Bedroom Speaker")

        with patch("nukiblinker.airplay_client.pyatv") as mock_pyatv:
            mock_pyatv.scan = AsyncMock(return_value=[dev])
            mock_pyatv.connect = AsyncMock()
            await client.play(["HomePod"], "/tmp/test.mp3", 0.5)
            mock_pyatv.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_ip_scan_port_conflict(self, client):
        """IP-based scan should handle OSError gracefully."""
        with patch("nukiblinker.airplay_client.pyatv") as mock_pyatv:
            mock_pyatv.scan = AsyncMock(side_effect=OSError("Address already in use"))
            await client.play(["10.0.0.10"], "/tmp/test.mp3", 0.5)
            mock_pyatv.connect.assert_not_called()


class TestListSpeakers:
    @pytest.mark.asyncio
    async def test_returns_discovered_speakers(self, client):
        d1 = _make_device("HomePod", "10.0.0.10")
        d2 = _make_device("HomePod Mini", "10.0.0.11")

        with patch("nukiblinker.airplay_client.pyatv") as mock_pyatv:
            mock_pyatv.scan = AsyncMock(return_value=[d1, d2])
            result = await client.list_speakers()
            assert len(result) == 2
            assert result[0]["name"] == "HomePod"
            assert result[0]["type"] == "airplay"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pyatv(self, client):
        with patch("nukiblinker.airplay_client.pyatv", None):
            result = await client.list_speakers()
            assert result == []
