"""Configuration models and YAML persistence for NukiBlinker."""

from __future__ import annotations

import socket
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

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
    # Friendly names for the configured devices (#115). Real callbacks carry no
    # `name`, so these let the Event Log label events by name instead of nukiId.
    opener_name: str = ""
    lock_name: str = ""
    web_api_token: str = ""  # optional Nuki Web API token for name/trigger resolution


class HueConfig(BaseModel):
    bridge_ip: str = ""
    api_key: str = ""
    lights: list[int] = Field(default_factory=list)
    groups: list[int] = Field(default_factory=list)


class BlinkConfig(BaseModel):
    """Hue blink behaviour for an event.

    Modes map to the Hue built-in ``alert`` effect, which restores each light's
    previous state automatically when the sequence ends:

    - ``none``  — no blink.
    - ``short`` — ``select`` (single breathe cycle, one blink).
    - ``long``  — ``lselect`` (~15-second breathe cycle).
    """

    mode: str = "long"

    @field_validator("mode", mode="before")
    @classmethod
    def _migrate_mode(cls, value: object) -> str:
        """Normalise legacy values (``alert``/``custom``) and unknown modes."""
        if value in ("none", "short", "long"):
            return value  # type: ignore[return-value]
        # Legacy configs: the old built-in alert was lselect (long); the old
        # configurable custom pattern was removed — map it to a visible blink.
        if value in ("alert", "custom"):
            return "long"
        return "long"


class SpeakersConfig(BaseModel):
    chromecast: list[str] = Field(default_factory=list)
    volume: float = 0.5


class AudioConfig(BaseModel):
    enabled: bool = False
    mode: str = "tts"
    message: str = "{name} llegó a casa"
    fallback_name: str = "Alguien"


class EventRuleConfig(BaseModel):
    blink: BlinkConfig = Field(default_factory=BlinkConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    homekit: bool = True


class EventRulesConfig(BaseModel):
    ring: EventRuleConfig = Field(
        default_factory=lambda: EventRuleConfig(
            blink=BlinkConfig(mode="long"),
            audio=AudioConfig(enabled=False),
            homekit=True,
        )
    )
    ring_to_open: EventRuleConfig = Field(
        default_factory=lambda: EventRuleConfig(
            blink=BlinkConfig(mode="short"),
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
    enabled: bool = False
    window_seconds: int = 120  # suppress duplicate events within this window


class OpenerCorrelationConfig(BaseModel):
    """Correlate otherwise-ignored Opener status callbacks with Nuki Web (#180).

    The Nuki Bridge does not always emit a ``ring_to_open`` (state 7) callback
    when a user opens the gate from the app — only routine status callbacks
    (e.g. ``state=1`` online / ``state=3`` rto active with ``ringactionState``
    false) arrive, which classify as ``opener_status`` and would otherwise be
    ignored. When enabled, NukiBlinker polls the Nuki Web activity log for a
    short window after such a callback; if a user-attributed open appears, it
    dispatches the ``ring_to_open`` rule. Requires a ``nuki.web_api_token``.
    """
    enabled: bool = True
    window_seconds: int = 10            # how long to keep polling Nuki Web
    poll_interval_seconds: float = 2.0  # delay between polls
    recency_seconds: int = 60           # max age of a Web entry to count as "this open"


class GithubConfig(BaseModel):
    """GitHub integration settings (#124).

    Used by the support-bundle feature (#117) to open an issue with a diagnostic
    bundle. ``token`` is a PAT (scopes ``contents:write`` + ``issues:write``)
    and is persisted as a secret in ``secrets.yaml`` — never inline in
    ``config.yaml``.
    """
    token: str = ""                       # PAT; secret (see SECRET_FIELDS)
    repo: str = "nicdobler/NukiBlinker"   # owner/repo target for issues
    default_window_minutes: int = 15      # default +/- window for the bundle


class LoggingConfig(BaseModel):
    """Application log file settings (#115).

    The app log is written to a rotating file under the mounted ``logs/`` volume
    in addition to the console, with basic weekly housekeeping.
    """
    file_path: str = "logs/nukiblinker.log"  # empty disables file logging
    rotation_when: str = "W0"                # TimedRotatingFileHandler `when` (weekly, Monday)
    backup_count: int = 4                    # number of rotated files kept


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
    opener_correlation: OpenerCorrelationConfig = Field(default_factory=OpenerCorrelationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    github: GithubConfig = Field(default_factory=GithubConfig)


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

# Secret fields are persisted to a dedicated ``secrets.yaml`` next to
# ``config.yaml`` (never inline), so rewriting the main config can never wipe a
# stored secret (#123). Each entry is a (section, key) path into the config dict.
SECRET_FIELDS: tuple[tuple[str, str], ...] = (
    ("nuki", "api_token"),
    ("nuki", "web_api_token"),
    ("hue", "api_key"),
    ("github", "token"),
)

# Value used by the web UI to mask a secret on GET; it must never be persisted
# as an actual secret value.
MASK_SENTINEL = "***"

# Obsolete per-event audio fields dropped from the persisted config on save
# (#123): a bare ring has no known visitor name, and ``door_opened`` only plays a
# chime. The shared ``AudioConfig`` model keeps the fields for ``ring_to_open``.
_OBSOLETE_AUDIO_EVENTS: tuple[str, ...] = ("ring", "door_opened")
_OBSOLETE_AUDIO_FIELDS: tuple[str, ...] = ("message", "fallback_name")


def default_secrets_path(config_path: str | Path) -> Path:
    """Return the secrets file path that pairs with ``config_path``."""
    config_path = Path(config_path)
    return config_path.parent / "secrets.yaml"


def _read_yaml_dict(path: Path) -> dict:
    """Read a YAML file into a dict. Returns ``{}`` if missing/empty/invalid.

    Resilient to ``path`` being a *directory* (#129): Docker auto-creates a
    bind-mount target as an empty directory when the host file does not exist
    at ``docker compose up`` time, which previously crashed startup with
    ``IsADirectoryError``. A directory is treated as "no usable file" and a
    clear, actionable error is logged instead of raising.
    """
    if not path.is_file():
        if path.is_dir():
            logger.error(
                "%s is a directory, not a file — this is a Docker bind-mount "
                "artifact created when the host file was missing at "
                "'docker compose up'. Stop the stack, remove the directory, "
                "recreate it as a file, and restart: "
                "`docker compose down && rmdir %s && touch %s && docker compose up -d` "
                "(or re-run ./update.sh). Continuing without it.",
                path, path, path,
            )
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        logger.warning("YAML file %s is not a dict — ignoring", path)
        return {}
    return data


def _overlay_secrets(base: dict, secrets: dict) -> dict:
    """Overlay non-empty secret values from ``secrets`` onto ``base`` in place."""
    for section, key in SECRET_FIELDS:
        value = secrets.get(section, {}).get(key)
        if value:
            base.setdefault(section, {})[key] = value
    return base


def _strip_obsolete_fields(data: dict) -> dict:
    """Remove obsolete per-event audio fields from a config dict in place (#123)."""
    events = data.get("events")
    if not isinstance(events, dict):
        return data
    for event in _OBSOLETE_AUDIO_EVENTS:
        audio = events.get(event, {}).get("audio")
        if isinstance(audio, dict):
            for field in _OBSOLETE_AUDIO_FIELDS:
                audio.pop(field, None)
    return data


def _split_secrets(data: dict, existing_secrets: dict) -> tuple[dict, dict]:
    """Split secrets out of ``data`` (mutated in place) into a secrets dict.

    Secret preservation: an empty or masked (``***``) incoming value never
    overwrites a stored secret — the existing value is kept. Only a new
    non-empty value updates a secret. Returns ``(main_data, secrets)``.
    """
    secrets: dict = {}
    for section, key in SECRET_FIELDS:
        new_value = data.get(section, {}).pop(key, "")
        if new_value and new_value != MASK_SENTINEL:
            kept = new_value
        else:
            kept = existing_secrets.get(section, {}).get(key, "")
        if kept:
            secrets.setdefault(section, {})[key] = kept
    return data, secrets


def _write_yaml_verified(path: Path, data: dict) -> int:
    """Write ``data`` as YAML to ``path`` with read-back verification."""
    yaml_text = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    path.write_text(yaml_text, encoding="utf-8")
    readback = path.read_text(encoding="utf-8")
    if readback != yaml_text:
        logger.error(
            "Config verification FAILED — written %d bytes but read back %d bytes at %s",
            len(yaml_text), len(readback), path,
        )
        raise IOError(f"Config verification failed for {path}")
    return len(yaml_text)


def load_config(path: str | Path, secrets_path: str | Path | None = None) -> AppConfig:
    """Load config from YAML, overlaying secrets from ``secrets.yaml``.

    Non-secret settings come from ``path``; secrets are overlaid from
    ``secrets_path`` (defaults to ``secrets.yaml`` beside ``path``). An old
    config that still carries inline secrets loads unchanged and is migrated to
    ``secrets.yaml`` on the next save. Returns defaults if the main file is
    missing or empty.
    """
    path = Path(path)
    secrets_path = Path(secrets_path) if secrets_path else default_secrets_path(path)

    if not path.is_file():
        if path.is_dir():
            logger.error(
                "Config file %s is a directory, not a file — likely a Docker "
                "bind-mount artifact (#129). Using defaults. Replace it with a "
                "file and restart (re-run ./update.sh).", path,
            )
        else:
            logger.warning("Config file %s not found — using defaults", path)
        data: dict = {}
    else:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            logger.warning("Config file %s is empty — using defaults", path)
            data = {}
        else:
            loaded = yaml.safe_load(text)
            if not isinstance(loaded, dict):
                logger.warning("Config file %s is not a dict — using defaults", path)
                data = {}
            else:
                data = loaded

    secrets = _read_yaml_dict(secrets_path)
    data = _overlay_secrets(data, secrets)
    return AppConfig.model_validate(data)


def save_config(
    config: AppConfig,
    path: str | Path,
    secrets_path: str | Path | None = None,
) -> None:
    """Persist config, splitting secrets into ``secrets.yaml`` (#123).

    Non-secret settings are written to ``path`` (with secret fields and obsolete
    audio fields stripped); secrets are written to ``secrets_path`` (defaults to
    ``secrets.yaml`` beside ``path``). Empty/masked secrets never overwrite a
    stored value. Both writes are read-back verified.
    """
    path = Path(path)
    secrets_path = Path(secrets_path) if secrets_path else default_secrets_path(path)

    data = config.model_dump(mode="json")
    data = _strip_obsolete_fields(data)
    existing_secrets = _read_yaml_dict(secrets_path)
    main_data, secrets = _split_secrets(data, existing_secrets)

    main_bytes = _write_yaml_verified(path, main_data)
    _write_yaml_verified(secrets_path, secrets)
    # Log only the non-secret config write — never log secret values, sizes, or
    # paths derived from the secrets dict (CodeQL py/clear-text-logging).
    logger.info("Config saved and verified (%d bytes) to %s", main_bytes, path)
    logger.info("Secrets persisted (%d fields) to a separate file", len(SECRET_FIELDS))


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
