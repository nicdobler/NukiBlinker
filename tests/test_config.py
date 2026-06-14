"""Tests for nukiblinker.config — validation, defaults, load, save."""

import pytest
import yaml

from nukiblinker.config import (
    AppConfig,
    BlinkConfig,
    default_secrets_path,
    load_config,
    save_config,
    summarize_config,
)


class TestDefaults:
    """AppConfig with no input should produce sensible defaults."""

    def test_default_config_is_valid(self):
        cfg = AppConfig()
        assert cfg.server.port == 8080
        assert cfg.nuki.bridge_port == 8080
        assert cfg.hue.lights == []
        assert cfg.speakers.volume == 0.5

    def test_github_defaults(self):
        """#124: General/Settings adds a github section with sensible defaults."""
        cfg = AppConfig()
        assert cfg.github.token == ""
        assert cfg.github.repo == "nicdobler/NukiBlinker"
        assert cfg.github.default_window_minutes == 15

    def test_event_rules_defaults(self):
        cfg = AppConfig()
        assert cfg.events.ring.blink.mode == "long"
        assert cfg.events.ring.audio.enabled is False
        assert cfg.events.ring.homekit is True

        assert cfg.events.ring_to_open.blink.mode == "short"
        assert cfg.events.ring_to_open.audio.enabled is True
        assert cfg.events.ring_to_open.audio.mode == "tts"

        assert cfg.events.door_opened.blink.mode == "none"
        assert cfg.events.door_opened.audio.enabled is True
        assert cfg.events.door_opened.audio.mode == "chime"
        assert cfg.events.door_opened.homekit is False

    def test_audio_config_defaults(self):
        cfg = AppConfig()
        audio = cfg.events.ring_to_open.audio
        assert "{name}" in audio.message
        assert audio.fallback_name == "Alguien"
        assert audio.chime == "chime.wav"


class TestLoadConfig:
    """Loading config from YAML files."""

    def test_load_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg == AppConfig()

    def test_load_empty_file_returns_defaults(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        cfg = load_config(f)
        assert cfg == AppConfig()

    def test_load_valid_yaml(self, tmp_path):
        data = {
            "nuki": {"bridge_ip": "10.0.0.1", "api_token": "abc"},
            "hue": {"bridge_ip": "10.0.0.2", "lights": [1, 2]},
            "server": {"port": 9090},
        }
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data), encoding="utf-8")
        cfg = load_config(f)
        assert cfg.nuki.bridge_ip == "10.0.0.1"
        assert cfg.nuki.api_token == "abc"
        assert cfg.hue.lights == [1, 2]
        assert cfg.server.port == 9090
        # Unset fields keep defaults
        assert cfg.speakers.volume == 0.5

    def test_load_partial_events(self, tmp_path):
        data = {
            "events": {
                "ring": {"homekit": False},
            }
        }
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data), encoding="utf-8")
        cfg = load_config(f)
        assert cfg.events.ring.homekit is False
        # Other event rules keep defaults
        assert cfg.events.ring_to_open.audio.enabled is True

    def test_load_non_dict_yaml_returns_defaults(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("just a string", encoding="utf-8")
        cfg = load_config(f)
        assert cfg == AppConfig()

    def test_load_with_lock_id(self, tmp_path):
        data = {"nuki": {"lock_id": 99999}}
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data), encoding="utf-8")
        cfg = load_config(f)
        assert cfg.nuki.lock_id == 99999
        assert cfg.nuki.opener_id is None

    def test_secrets_path_as_directory_does_not_crash(self, tmp_path):
        """#129: Docker auto-creates secrets.yaml as a directory when the host
        file is missing at `up`. load_config must not raise IsADirectoryError —
        it loads the main config and skips the unusable secrets dir."""
        data = {"nuki": {"bridge_ip": "10.0.0.1", "lock_id": 42}}
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data), encoding="utf-8")
        # The paired secrets.yaml exists but is a DIRECTORY.
        (tmp_path / "secrets.yaml").mkdir()

        cfg = load_config(f)  # must not raise
        assert cfg.nuki.bridge_ip == "10.0.0.1"
        assert cfg.nuki.lock_id == 42

    def test_config_path_as_directory_returns_defaults(self, tmp_path):
        """#129: a directory at the config path is treated as missing → defaults."""
        d = tmp_path / "config.yaml"
        d.mkdir()
        cfg = load_config(d)  # must not raise
        assert cfg == AppConfig()


class TestSaveConfig:
    """Persisting config to YAML."""

    def test_save_and_reload(self, tmp_path):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "192.168.1.50"
        cfg.hue.lights = [3, 4, 5]
        f = tmp_path / "out.yaml"
        save_config(cfg, f)

        reloaded = load_config(f)
        assert reloaded.nuki.bridge_ip == "192.168.1.50"
        assert reloaded.hue.lights == [3, 4, 5]

    def test_save_creates_file(self, tmp_path):
        f = tmp_path / "new.yaml"
        assert not f.exists()
        save_config(AppConfig(), f)
        assert f.exists()

    def test_saved_yaml_is_valid(self, tmp_path):
        f = tmp_path / "check.yaml"
        save_config(AppConfig(), f)
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "nuki" in data
        assert "events" in data


class TestSummarizeConfig:
    """Config summary for startup logging."""

    def test_default_config_summary(self):
        summary = summarize_config(AppConfig())
        assert "nuki=<not configured>" in summary
        assert "hue=<not configured>" in summary

    def test_configured_integrations(self):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.nuki.api_token = "tok"
        cfg.hue.bridge_ip = "10.0.0.2"
        cfg.hue.api_key = "key"
        cfg.homekit.enabled = True
        summary = summarize_config(cfg)
        assert "nuki=10.0.0.1" in summary
        assert "hue=10.0.0.2" in summary
        assert "homekit=enabled" in summary

    def test_partial_config(self):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        # No api_token — still not configured
        summary = summarize_config(cfg)
        assert "nuki=<not configured>" in summary


class TestBlinkModeMigration:
    """Legacy blink modes are normalised by the field validator."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("none", "none"),
            ("short", "short"),
            ("long", "long"),
            ("alert", "long"),   # legacy built-in alert was lselect
            ("custom", "long"),  # removed custom pattern → visible blink
            ("bogus", "long"),   # unknown → safe default
        ],
    )
    def test_mode_migration(self, raw, expected):
        assert BlinkConfig(mode=raw).mode == expected

    def test_legacy_custom_yaml_loads(self, tmp_path):
        """A pre-existing config.yaml with custom blink + fields still loads."""
        data = {
            "events": {
                "ring_to_open": {
                    "blink": {
                        "mode": "custom",
                        "custom": {"hue": 25500, "flashes": 3},
                    }
                }
            }
        }
        f = tmp_path / "config.yaml"
        f.write_text(yaml.dump(data), encoding="utf-8")
        cfg = load_config(f)
        # Legacy mode migrated; removed custom fields are ignored.
        assert cfg.events.ring_to_open.blink.mode == "long"
        assert not hasattr(cfg.events.ring_to_open.blink, "custom")


class TestSecretSeparation:
    """Secrets are persisted to a separate secrets.yaml, never inline (#123)."""

    def _read(self, path):
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def test_secrets_written_to_secrets_file_not_config(self, tmp_path):
        cfg = AppConfig()
        cfg.nuki.bridge_ip = "10.0.0.1"
        cfg.nuki.api_token = "nuki-secret"
        cfg.nuki.web_api_token = "web-secret"
        cfg.hue.api_key = "hue-secret"
        config_path = tmp_path / "config.yaml"
        save_config(cfg, config_path)

        config_data = self._read(config_path)
        secrets_data = self._read(default_secrets_path(config_path))

        # Non-secrets stay in config.yaml
        assert config_data["nuki"]["bridge_ip"] == "10.0.0.1"
        # Secrets are stripped from config.yaml
        assert "api_token" not in config_data["nuki"]
        assert "web_api_token" not in config_data["nuki"]
        assert "api_key" not in config_data["hue"]
        # Secrets land in secrets.yaml
        assert secrets_data["nuki"]["api_token"] == "nuki-secret"
        assert secrets_data["nuki"]["web_api_token"] == "web-secret"
        assert secrets_data["hue"]["api_key"] == "hue-secret"

    def test_roundtrip_overlays_secrets(self, tmp_path):
        cfg = AppConfig()
        cfg.nuki.api_token = "tok"
        cfg.hue.api_key = "key"
        config_path = tmp_path / "config.yaml"
        save_config(cfg, config_path)

        reloaded = load_config(config_path)
        assert reloaded.nuki.api_token == "tok"
        assert reloaded.hue.api_key == "key"

    def test_github_token_persisted_as_secret(self, tmp_path):
        """#124: github.token lands in secrets.yaml, never inline in config.yaml."""
        cfg = AppConfig()
        cfg.github.token = "ghp-secret"
        cfg.github.repo = "acme/widgets"
        config_path = tmp_path / "config.yaml"
        save_config(cfg, config_path)

        config_data = self._read(config_path)
        secrets_data = self._read(default_secrets_path(config_path))
        # Non-secret github settings stay in config.yaml
        assert config_data["github"]["repo"] == "acme/widgets"
        assert "token" not in config_data.get("github", {})
        # The token lives in secrets.yaml
        assert secrets_data["github"]["token"] == "ghp-secret"
        # Round-trip overlays it back
        assert load_config(config_path).github.token == "ghp-secret"

    def test_empty_secret_does_not_overwrite_stored(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        # First save stores a real token
        first = AppConfig()
        first.nuki.api_token = "keep-me"
        save_config(first, config_path)

        # Second save comes from a config where the secret is empty (the #116 bug)
        second = AppConfig()
        second.nuki.api_token = ""
        save_config(second, config_path)

        reloaded = load_config(config_path)
        assert reloaded.nuki.api_token == "keep-me"

    def test_masked_secret_does_not_overwrite_stored(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        first = AppConfig()
        first.hue.api_key = "real-key"
        save_config(first, config_path)

        masked = AppConfig()
        masked.hue.api_key = "***"
        save_config(masked, config_path)

        reloaded = load_config(config_path)
        assert reloaded.hue.api_key == "real-key"

    def test_new_secret_value_updates_stored(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        first = AppConfig()
        first.nuki.api_token = "old"
        save_config(first, config_path)

        updated = AppConfig()
        updated.nuki.api_token = "new"
        save_config(updated, config_path)

        reloaded = load_config(config_path)
        assert reloaded.nuki.api_token == "new"

    def test_inline_secrets_migrated_on_save(self, tmp_path):
        # An old config.yaml with inline secrets still loads...
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"nuki": {"bridge_ip": "10.0.0.1", "api_token": "legacy"}}),
            encoding="utf-8",
        )
        cfg = load_config(config_path)
        assert cfg.nuki.api_token == "legacy"

        # ...and on the next save the secret moves out of config.yaml.
        save_config(cfg, config_path)
        config_data = self._read(config_path)
        secrets_data = self._read(default_secrets_path(config_path))
        assert "api_token" not in config_data["nuki"]
        assert secrets_data["nuki"]["api_token"] == "legacy"

    def test_secrets_file_overrides_config_inline(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"nuki": {"api_token": "from-config"}}), encoding="utf-8"
        )
        default_secrets_path(config_path).write_text(
            yaml.dump({"nuki": {"api_token": "from-secrets"}}), encoding="utf-8"
        )
        cfg = load_config(config_path)
        assert cfg.nuki.api_token == "from-secrets"


class TestObsoleteFieldNormalization:
    """message / fallback_name are dropped from ring & door_opened on save (#123)."""

    def _read(self, path):
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def test_obsolete_audio_fields_stripped_on_save(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        save_config(AppConfig(), config_path)
        events = self._read(config_path)["events"]

        for event in ("ring", "door_opened"):
            audio = events[event]["audio"]
            assert "message" not in audio
            assert "fallback_name" not in audio

    def test_ring_to_open_keeps_message(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        save_config(AppConfig(), config_path)
        rto_audio = self._read(config_path)["events"]["ring_to_open"]["audio"]
        assert "message" in rto_audio
        assert "fallback_name" in rto_audio

    def test_legacy_obsolete_fields_cleaned_on_resave(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "events": {
                        "door_opened": {
                            "audio": {
                                "mode": "chime",
                                "message": "stale",
                                "fallback_name": "stale",
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        cfg = load_config(config_path)
        save_config(cfg, config_path)
        audio = self._read(config_path)["events"]["door_opened"]["audio"]
        assert "message" not in audio
        assert "fallback_name" not in audio


class TestValidation:
    """Pydantic validation on config values."""

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            AppConfig.model_validate({"server": {"port": "not_a_number"}})

    def test_extra_fields_ignored_by_default(self):
        cfg = AppConfig.model_validate({"unknown_key": True})
        assert cfg.server.port == 8080
