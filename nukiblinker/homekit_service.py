"""Apple HomeKit doorbell accessory via HAP-python."""

from __future__ import annotations

import random
import string
import threading
from pathlib import Path

from nukiblinker.logging_config import get_logger

logger = get_logger("homekit")

try:
    from pyhap.accessory import Accessory
    from pyhap.accessory_driver import AccessoryDriver

    _HAP_AVAILABLE = True
except ImportError as _exc:
    logger.warning("HAP-python import failed: %s", _exc)
    Accessory = None  # type: ignore[assignment,misc]
    AccessoryDriver = None  # type: ignore[assignment,misc]
    _HAP_AVAILABLE = False


# Setup codes Apple rejects as too trivial (HAP spec).
_FORBIDDEN_CODES = {
    "000-00-000",
    "111-11-111",
    "222-22-222",
    "333-33-333",
    "444-44-444",
    "555-55-555",
    "666-66-666",
    "777-77-777",
    "888-88-888",
    "999-99-999",
    "123-45-678",
    "876-54-321",
}


class HomeKitService:
    """Exposes a virtual HomeKit doorbell accessory."""

    def __init__(
        self,
        setup_code: str = "",
        persist_dir: str = ".homekit",
        address: str = "",
    ) -> None:
        self._address = address
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._setup_code = setup_code or self._load_or_create_code()
        self._driver: AccessoryDriver | None = None
        self._accessory: Accessory | None = None
        self._thread: threading.Thread | None = None

    def _load_or_create_code(self) -> str:
        """Reuse the persisted setup code, or generate and persist a new one.

        HAP-python persists the pincode inside accessory.state, so the code
        must stay stable across restarts — otherwise the logged code diverges
        from the one the accessory actually accepts.
        """
        code_file = self._persist_dir / "setup_code"
        if code_file.exists():
            code = code_file.read_text().strip()
            if len(code) == 10 and code not in _FORBIDDEN_CODES:
                return code
        code = self._generate_code()
        code_file.write_text(code)
        return code

    @staticmethod
    def _generate_code() -> str:
        """Generate a random 8-digit HomeKit setup code (XXX-XX-XXX format).

        Re-rolls if the code is one of the trivial codes Apple rejects.
        """
        while True:
            digits = "".join(random.choices(string.digits, k=8))
            code = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
            if code not in _FORBIDDEN_CODES:
                return code

    def start(self) -> bool:
        """Start the HAP accessory driver in a background thread.

        Returns True if started successfully, False if HAP-python is missing.
        """
        if not _HAP_AVAILABLE:
            logger.error("HAP-python not installed — HomeKit disabled")
            return False

        persist_file = self._persist_dir / "accessory.state"
        self._driver = AccessoryDriver(
            address=self._address or None,
            port=51826,
            persist_file=str(persist_file),
            pincode=self._setup_code.encode(),
        )

        self._accessory = Accessory(self._driver, "NukiBlinker Doorbell")
        self._accessory.add_preload_service("Doorbell")
        self._driver.add_accessory(self._accessory)

        self._thread = threading.Thread(target=self._run_driver, daemon=True)
        self._thread.start()
        logger.info(
            "HomeKit doorbell started (setup code: %s, address: %s)",
            self._setup_code,
            self._address or "auto",
        )
        return True

    def _run_driver(self) -> None:
        """Run the AccessoryDriver, catching mDNS errors."""
        try:
            self._driver.start()
        except OSError as e:
            if "5353" in str(e) or "Address already in use" in str(e):
                logger.error(
                    "HomeKit cannot advertise — port 5353 conflict. "
                    "Stop the host mDNS service (Bonjour) to use HomeKit. "
                    "See README troubleshooting."
                )
            else:
                logger.error("HomeKit driver failed: %s", e)
        except Exception:
            logger.error("HomeKit driver failed", exc_info=True)

    def stop(self) -> None:
        """Stop the HAP accessory driver."""
        if self._driver:
            self._driver.stop()
            logger.info("HomeKit doorbell stopped")

    async def trigger_ring(self) -> None:
        """Fire a doorbell ring event to all paired Apple devices."""
        if not self._accessory:
            logger.warning("HomeKit accessory not started — cannot trigger ring")
            return

        service = self._accessory.get_service("Doorbell")
        if service:
            char = service.get_characteristic("ProgrammableSwitchEvent")
            if char:
                char.set_value(0)  # Single press
        logger.info("HomeKit doorbell ring triggered")

    def get_setup_code(self) -> str:
        """Return the 8-digit setup code for pairing."""
        return self._setup_code

    def get_qr_code(self) -> str | None:
        """Return an SVG QR code for the HomeKit setup URI, or None if unavailable."""
        try:
            import pyqrcode
            import base36

            digits = self._setup_code.replace("-", "")
            category = 10  # CATEGORY_SENSOR value

            # Use the setup_id from driver state when available so the QR URI
            # matches exactly what HAP-python has advertised.
            setup_id = "0000"
            if self._driver and hasattr(self._driver, "state"):
                sid = getattr(self._driver.state, "setup_id", None)
                if sid:
                    setup_id = sid

            uri = f"X-HM://{base36.dumps(int(digits) | (category << 31)):>09}{setup_id}"
            qr = pyqrcode.create(uri, error="M")
            return qr.svg(scale=4, xmldecl=False, omithw=True)
        except Exception as exc:
            logger.warning("QR code generation failed: %s", exc)
            return None

    def is_paired(self) -> bool:
        """Whether any Apple device has paired with the accessory."""
        if self._driver and hasattr(self._driver, "state"):
            return bool(self._driver.state.paired_clients)
        return False
