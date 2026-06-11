"""Tests for nukiblinker.homekit_service — mock HAP-python."""

from unittest.mock import MagicMock, patch

import pytest

from nukiblinker.homekit_service import HomeKitService


class TestHapImports:
    def test_hap_imports_succeed(self):
        """Regression #72/#35: imports must resolve against the installed HAP-python."""
        from nukiblinker import homekit_service

        assert homekit_service._HAP_AVAILABLE is True
        assert homekit_service.CATEGORY_PROGRAMMABLE_SWITCH is not None
        assert homekit_service.Bridge is not None


class TestSetupCode:
    def test_generates_valid_format(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        code = svc.get_setup_code()
        assert len(code) == 10  # XXX-XX-XXX
        assert code[3] == "-" and code[6] == "-"
        digits = code.replace("-", "")
        assert digits.isdigit() and len(digits) == 8

    def test_uses_provided_code(self, tmp_path):
        svc = HomeKitService(setup_code="123-45-678", persist_dir=str(tmp_path / "hk"))
        assert svc.get_setup_code() == "123-45-678"

    def test_generated_code_persists_across_restarts(self, tmp_path):
        """Regression: random code per start diverged from the pincode
        HAP-python persisted in accessory.state — pairing always failed."""
        persist = str(tmp_path / "hk")
        first = HomeKitService(persist_dir=persist).get_setup_code()
        second = HomeKitService(persist_dir=persist).get_setup_code()
        assert first == second
        assert (tmp_path / "hk" / "setup_code").read_text().strip() == first

    def test_provided_code_takes_precedence_over_persisted(self, tmp_path):
        persist = tmp_path / "hk"
        persist.mkdir()
        (persist / "setup_code").write_text("111-22-333")
        svc = HomeKitService(setup_code="444-55-666", persist_dir=str(persist))
        assert svc.get_setup_code() == "444-55-666"

    def test_invalid_persisted_code_is_regenerated(self, tmp_path):
        persist = tmp_path / "hk"
        persist.mkdir()
        (persist / "setup_code").write_text("123-45-678")  # Apple-forbidden
        svc = HomeKitService(persist_dir=str(persist))
        assert svc.get_setup_code() != "123-45-678"

    def test_generator_skips_forbidden_codes(self):
        """Regression: iOS rejects trivial codes like 123-45-678."""
        with patch("nukiblinker.homekit_service.random.choices") as mock_choices:
            mock_choices.side_effect = [list("12345678"), list("52941736")]
            code = HomeKitService._generate_code()
        assert code == "529-41-736"
        assert mock_choices.call_count == 2


class TestStart:
    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", True)
    @patch("nukiblinker.homekit_service.Bridge")
    @patch("nukiblinker.homekit_service.AccessoryDriver")
    @patch("nukiblinker.homekit_service.Accessory")
    def test_starts_driver_in_thread(self, mock_acc_cls, mock_driver_cls, mock_bridge_cls, tmp_path):
        mock_driver = MagicMock()
        mock_driver_cls.return_value = mock_driver
        mock_acc = MagicMock()
        mock_acc_cls.return_value = mock_acc
        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge

        svc = HomeKitService(setup_code="111-22-333", persist_dir=str(tmp_path / "hk"))
        result = svc.start()

        assert result is True
        # Regression #72: pincode must keep XXX-XX-XXX format (dashes included)
        assert mock_driver_cls.call_args.kwargs["pincode"] == b"111-22-333"
        # Two child accessories created: Doorbell + StatelessProgrammableSwitch
        acc_names = [c.args[1] for c in mock_acc_cls.call_args_list]
        assert "NukiBlinker Doorbell" in acc_names
        assert "NukiBlinker Button" in acc_names
        # Both added to bridge
        assert mock_bridge.add_accessory.call_count == 2
        # Bridge added to driver
        mock_driver.add_accessory.assert_called_once_with(mock_bridge)
        # Thread started
        assert svc._thread is not None

    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", True)
    @patch("nukiblinker.homekit_service.Bridge")
    @patch("nukiblinker.homekit_service.AccessoryDriver")
    @patch("nukiblinker.homekit_service.Accessory")
    def test_binds_to_explicit_address(self, mock_acc_cls, mock_driver_cls, mock_bridge_cls, tmp_path):
        """Regression: pairing failed because zeroconf advertised the wrong interface."""
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"), address="192.168.1.50")
        svc.start()
        assert mock_driver_cls.call_args.kwargs["address"] == "192.168.1.50"

    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", True)
    @patch("nukiblinker.homekit_service.Bridge")
    @patch("nukiblinker.homekit_service.AccessoryDriver")
    @patch("nukiblinker.homekit_service.Accessory")
    def test_auto_address_when_empty(self, mock_acc_cls, mock_driver_cls, mock_bridge_cls, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        svc.start()
        assert mock_driver_cls.call_args.kwargs["address"] is None

    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", True)
    @patch("nukiblinker.homekit_service.CATEGORY_PROGRAMMABLE_SWITCH", 15)
    @patch("nukiblinker.homekit_service.Bridge")
    @patch("nukiblinker.homekit_service.AccessoryDriver")
    @patch("nukiblinker.homekit_service.Accessory")
    def test_accessory_categories(self, mock_acc_cls, mock_driver_cls, mock_bridge_cls, tmp_path):
        """Both child accessories must use CATEGORY_PROGRAMMABLE_SWITCH."""
        doorbell_acc = MagicMock()
        switch_acc = MagicMock()
        mock_acc_cls.side_effect = [doorbell_acc, switch_acc]
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        svc.start()
        assert doorbell_acc.category == 15   # CATEGORY_PROGRAMMABLE_SWITCH
        assert switch_acc.category == 15     # CATEGORY_PROGRAMMABLE_SWITCH

    @patch("nukiblinker.homekit_service._HAP_AVAILABLE", False)
    def test_skips_when_hap_not_available(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        result = svc.start()  # Should not raise
        assert result is False
        assert svc._driver is None


class TestStop:
    def test_stops_driver(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        svc._driver = MagicMock()
        svc.stop()
        svc._driver.stop.assert_called_once()


class TestTriggerRing:
    @pytest.mark.asyncio
    async def test_fires_switch_event_on_both_accessories(self, tmp_path):
        """Ring fires on Doorbell accessory (notification) and
        StatelessProgrammableSwitch accessory (automation trigger)."""
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        mock_char = MagicMock()
        mock_service = MagicMock()
        mock_service.get_characteristic.return_value = mock_char

        mock_doorbell = MagicMock()
        mock_doorbell.get_service.return_value = mock_service
        mock_switch = MagicMock()
        mock_switch.get_service.return_value = mock_service

        svc._bridge = MagicMock()
        svc._doorbell_acc = mock_doorbell
        svc._switch_acc = mock_switch

        await svc.trigger_ring()
        mock_doorbell.get_service.assert_called_once_with("Doorbell")
        mock_switch.get_service.assert_called_once_with("StatelessProgrammableSwitch")
        assert mock_char.set_value.call_args_list == [((0,),), ((0,),)]

    @pytest.mark.asyncio
    async def test_missing_service_does_not_crash(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        mock_acc = MagicMock()
        mock_acc.get_service.return_value = None
        svc._bridge = MagicMock()
        svc._doorbell_acc = mock_acc
        svc._switch_acc = mock_acc
        await svc.trigger_ring()  # Should not raise

    @pytest.mark.asyncio
    async def test_no_crash_when_not_started(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        await svc.trigger_ring()  # Should not raise


class TestIsPaired:
    def test_not_paired_when_no_driver(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        assert svc.is_paired() is False

    def test_paired_with_clients(self, tmp_path):
        svc = HomeKitService(persist_dir=str(tmp_path / "hk"))
        svc._driver = MagicMock()
        svc._driver.state.paired_clients = {"client1": {}}
        assert svc.is_paired() is True
