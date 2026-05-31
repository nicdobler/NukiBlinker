"""Configuration models and YAML persistence for NukiBlinker."""

from __future__ import annotations

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
    airplay: list[str] = Field(default_factory=list)
    volume: float = 0.5


class AudioConfig(BaseModel):
    enabled: bool = False
    mode: str = "tts"
    message: str = "{name} llegó a casa"
    chime: str = "chime.mp3"
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


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    nuki: NukiConfig = Field(default_factory=NukiConfig)
    hue: HueConfig = Field(default_factory=HueConfig)
    speakers: SpeakersConfig = Field(default_factory=SpeakersConfig)
    homekit: HomeKitConfig = Field(default_factory=HomeKitConfig)
    events: EventRulesConfig = Field(default_factory=EventRulesConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)


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
    if config.speakers.airplay:
        parts.append(f"airplay={len(config.speakers.airplay)} speakers")
    if config.homekit.enabled:
        parts.append("homekit=enabled")
    return ", ".join(parts)
