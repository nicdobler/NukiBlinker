"""Configuration models and YAML persistence for NukiBlinker."""

from __future__ import annotations

import socket
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from nukiblinker.logging_config import get_logger

logger = get_logger("config")


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class NukiConfig(BaseModel):
    bridge_ip: str = ""
    bridge_port: int = 8080
    api_token: str = ""
    opener_id: int | None = None
    lock_id: int | None = None
    web_api_token: str = ""  # optional Nuki Web API token for name/trigger resolution


class HueConfig(BaseModel):
    bridge_ip: str = ""
    api_key: str = ""
    lights: list[int] = Field(default_factory=list)
    groups: list[int] = Field(default_factory=list)


class CustomBlinkConfig(BaseModel):
    hue: int = 0
    saturation: int = 254
    brightness: int = 254
    flashes: int = 3
    interval_ms: int = 500


class BlinkConfig(BaseModel):
    mode: str = "alert"
    custom: CustomBlinkConfig = Field(default_factory=CustomBlinkConfig)


class SpeakersConfig(BaseModel):
    chromecast: list[str] = Field(default_factory=list)
    volume: float = 0.5


class AudioConfig(BaseModel):
    enabled: bool = False
    mode: str = "tts"
    message: str = "{name} llegó a casa"
    chime: str = "chime.wav"
    fallback_name: str = "Alguien"


class EventRuleConfig(BaseModel):
    blink: BlinkConfig = Field(default_factory=BlinkConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    homekit: bool = True


class EventRulesConfig(BaseModel):
    ring: EventRuleConfig = Field(
        default_factory=lambda: EventRuleConfig(
            blink=BlinkConfig(mode="alert"),
            audio=AudioConfig(enabled=False),
            homekit=True,
        )
    )
    ring_to_open: EventRuleConfig = Field(
        default_factory=lambda: EventRuleConfig(
            blink=BlinkConfig(mode="custom"),
            audio=AudioConfig(enabled=True, mode="tts", message="{name} llegó a casa"),
            homekit=True,
        )
    )
    door_opened: EventRuleConfig = Field(
        default_factory=lambda: EventRuleConfig(
            blink=BlinkConfig(mode="none"),
            audio=AudioConfig(enabled=True, mode="chime"),
            homekit=False,
        )
    )


class HomeKitConfig(BaseModel):
    enabled: bool = False
    setup_code: str = ""
    persist_dir: str = ".homekit"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    public_host: str = ""


class EventValidationConfig(BaseModel):
    enabled: bool = True
    max_delay_seconds: int = 60  # Reject events older than 60 seconds


class NightModeConfig(BaseModel):
    enabled: bool = False
    start_time: str = "22:00"    # 10 PM
    end_time: str = "07:00"      # 7 AM
    brightness_factor: float = 0.3  # 30% of normal brightness
    grace_minutes: int = 5       # 5-minute buffer


class EventLogConfig(BaseModel):
    enabled: bool = True
    max_entries: int = 1000
    retention_days: int = 7
    persist_to_file: bool = True
    file_path: str = "logs/event_log.db"  # SQLite DB (legacy .json is auto-migrated)
    timezone: str = "Europe/Madrid"  # IANA tz for CSV Date/Time columns


class DeduplicationConfig(BaseModel):
    enabled: bool = True
    window_seconds: int = 120  # suppress duplicate events within this window


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

_DOCKER_SUBNETS = ("192.168.65.", "172.17.", "172.18.", "172.19.")


class AppConfig(BaseModel):
    nuki: NukiConfig = Field(default_factory=NukiConfig)
    hue: HueConfig = Field(default_factory=HueConfig)
    speakers: SpeakersConfig = Field(default_factory=SpeakersConfig)
    homekit: HomeKitConfig = Field(default_factory=HomeKitConfig)
    events: EventRulesConfig = Field(default_factory=EventRulesConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    event_validation: EventValidationConfig = Field(default_factory=EventValidationConfig)
    night_mode: NightModeConfig = Field(default_factory=NightModeConfig)
    event_log: EventLogConfig = Field(default_factory=EventLogConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)


def get_public_host(config: AppConfig) -> str:
    """Return the LAN IP to use in externally-reachable URLs.

    Priority: public_host config > auto-detect via UDP probe.
    Warns if auto-detected IP looks like a Docker internal address.
    """
    if config.server.public_host:
        return config.server.public_host

    host = config.server.host
    if host in ("0.0.0.0", "::"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host = s.getsockname()[0]
            s.close()
        except Exception:
            host = "127.0.0.1"

    if any(host.startswith(prefix) for prefix in _DOCKER_SUBNETS):
        logger.warning(
            "Auto-detected IP %s looks like a Docker internal address. "
            "Speakers won't be able to fetch audio. "
            "Set server.public_host to your LAN IP in the config.",
            host,
        )
    return host


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_config(path: str | Path) -> AppConfig:
    """Load config from YAML file. Returns defaults if file is missing or empty."""
    path = Path(path)
    if not path.exists():
        logger.warning("Config file %s not found — using defaults", path)
        return AppConfig()
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        logger.warning("Config file %s is empty — using defaults", path)
        return AppConfig()
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        logger.warning("Config file %s is not a dict — using defaults", path)
        return AppConfig()
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: str | Path) -> None:
    """Persist config to YAML file with read-back verification."""
    path = Path(path)
    data = config.model_dump(mode="json")
    yaml_text = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    path.write_text(yaml_text, encoding="utf-8")

    # Verify the write persisted correctly
    readback = path.read_text(encoding="utf-8")
    if readback != yaml_text:
        logger.error(
            "Config verification FAILED — written %d bytes but read back %d bytes at %s",
            len(yaml_text), len(readback), path,
        )
        raise IOError(f"Config verification failed for {path}")
    logger.info("Config saved and verified (%d bytes) to %s", len(yaml_text), path)


def summarize_config(config: AppConfig) -> str:
    """Return a one-line summary of which integrations are configured."""
    parts = []
    if config.nuki.bridge_ip and config.nuki.api_token:
        parts.append(f"nuki={config.nuki.bridge_ip}")
    else:
        parts.append("nuki=<not configured>")
    if config.hue.bridge_ip and config.hue.api_key:
        parts.append(f"hue={config.hue.bridge_ip}")
    else:
        parts.append("hue=<not configured>")
    if config.speakers.chromecast:
        parts.append(f"chromecast={len(config.speakers.chromecast)} speakers")
    if config.homekit.enabled:
        parts.append("homekit=enabled")
    return ", ".join(parts)
