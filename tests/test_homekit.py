"""Tests for nukiblinker.homekit_service — mock HAP-python."""

from unittest.mock import MagicMock, patch

import pytest

from nukiblinker.homekit_service import HomeKitService


class TestSetupCode:
    def test_generates_valid_format(self):
        svc = HomeKitService()
        code = svc.get_setup_code()
        assert len(code) == 10  # XXX-XX-XXX
        assert code[3] == "-" and code[6] == "-"
        digits = code.replace("-", "")
        assert digits.isdigit() and len(digits) == 8

    def test_uses_provided_code(self):
        svc = HomeKitService(setup_code="123-45-678")
        assert svc.get_setup_code() == "123-45-678"


class TestStart:
    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", True)
    @patch("nukiblinker.homekit_service.AccessoryDriver")
    @patch("nukiblinker.homekit_service.Accessory")
    @patch("nukiblinker.homekit_service.service_loader")
    def test_starts_driver_in_thread(self, mock_loader, mock_acc_cls, mock_driver_cls, tmp_path):
        mock_driver = MagicMock()
        mock_driver_cls.return_value = mock_driver
        mock_acc = MagicMock()
        mock_acc_cls.return_value = mock_acc
        mock_service = MagicMock()
        mock_loader.get_serv_loader.return_value.get_service.return_value = mock_service

        svc = HomeKitService(setup_code="111-22-333", persist_dir=str(tmp_path / "hk"))
        svc.start()

        mock_driver.add_accessory.assert_called_once()
        # Thread started
        assert svc._thread is not None

    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", False)
    def test_skips_when_hap_not_available(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        svc.start()  # Should not raise
        assert svc._driver is None


class TestStop:
    def test_stops_driver(self):
        svc = HomeKitService()
        svc._driver = MagicMock()
        svc.stop()
        svc._driver.stop.assert_called_once()


class TestTriggerRing:
    @pytest.mark.asyncio
    async def test_fires_switch_event(self):
        svc = HomeKitService()
        mock_acc = MagicMock()
        mock_service = MagicMock()
        mock_char = MagicMock()
        mock_acc.get_service.return_value = mock_service
        mock_service.get_characteristic.return_value = mock_char
        svc._accessory = mock_acc

        await svc.trigger_ring()
        mock_char.set_value.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_no_crash_when_not_started(self):
        svc = HomeKitService()
        await svc.trigger_ring()  # Should not raise


class TestIsPaired:
    def test_not_paired_when_no_driver(self):
        svc = HomeKitService()
        assert svc.is_paired() is False

    def test_paired_with_clients(self):
        svc = HomeKitService()
        svc._driver = MagicMock()
        svc._driver.state.paired_clients = {"client1": {}}
        assert svc.is_paired() is True
