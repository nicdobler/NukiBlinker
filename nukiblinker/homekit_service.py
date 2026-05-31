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
    from pyhap.const import CATEGORY_DOORBELL
    from pyhap import loader as service_loader

    _HAP_AVAILABLE = True
except ImportError:
    Accessory = None  # type: ignore[assignment,misc]
    AccessoryDriver = None  # type: ignore[assignment,misc]
    CATEGORY_DOORBELL = None  # type: ignore[assignment]
    service_loader = None  # type: ignore[assignment]
    _HAP_AVAILABLE = False


class HomeKitService:
    """Exposes a virtual HomeKit doorbell accessory."""

    def __init__(self, setup_code: str = "", persist_dir: str = ".homekit") -> None:
        self._setup_code = setup_code or self._generate_code()
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._driver: AccessoryDriver | None = None
        self._accessory: Accessory | None = None
        self._thread: threading.Thread | None = None

    @staticmethod
    def _generate_code() -> str:
        """Generate a random 8-digit HomeKit setup code (XXX-XX-XXX format)."""
        digits = "".join(random.choices(string.digits, k=8))
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"

    def start(self) -> bool:
        """Start the HAP accessory driver in a background thread.

        Returns True if started successfully, False if HAP-python is missing.
        """
        if not _HAP_AVAILABLE:
            logger.error("HAP-python not installed — HomeKit disabled")
            return False

        persist_file = self._persist_dir / "accessory.state"
        self._driver = AccessoryDriver(
            port=51826,
            persist_file=str(persist_file),
            pincode=self._setup_code.replace("-", "").encode(),
        )

        self._accessory = Accessory(self._driver, "NukiBlinker Doorbell")
        doorbell_service = service_loader.get_serv_loader().get_service("Doorbell")
        self._accessory.add_service(doorbell_service)
        self._driver.add_accessory(self._accessory)

        self._thread = threading.Thread(target=self._run_driver, daemon=True)
        self._thread.start()
        logger.info("HomeKit doorbell started (setup code: %s)", self._setup_code)
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

        doorbell = self._accessory.get_service("Doorbell")
        if doorbell:
            switch_event = doorbell.get_characteristic("ProgrammableSwitchEvent")
            if switch_event:
                switch_event.set_value(0)  # Single press
                logger.info("HomeKit doorbell ring triggered")

    def get_setup_code(self) -> str:
        """Return the 8-digit setup code for pairing."""
        return self._setup_code

    def is_paired(self) -> bool:
        """Whether any Apple device has paired with the accessory."""
        if self._driver and hasattr(self._driver, "state"):
            return bool(self._driver.state.paired_clients)
        return False
