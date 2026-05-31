"""Tests for nukiblinker.config — validation, defaults, load, save."""

import pytest
import yaml

from nukiblinker.config import AppConfig, load_config, save_config, summarize_config


class TestDefaults:
    """AppConfig with no input should produce sensible defaults."""

    def test_default_config_is_valid(self):
        cfg = AppConfig()
        assert cfg.server.port == 8080
        assert cfg.nuki.bridge_port == 8080
        assert cfg.hue.lights == []
        assert cfg.speakers.volume == 0.5

    def test_event_rules_defaults(self):
        cfg = AppConfig()
        assert cfg.events.ring.blink.mode == "alert"
        assert cfg.events.ring.audio.enabled is False
        assert cfg.events.ring.homekit is True

        assert cfg.events.ring_to_open.blink.mode == "custom"
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


class TestValidation:
    """Pydantic validation on config values."""

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):
            AppConfig.model_validate({"server": {"port": "not_a_number"}})

    def test_extra_fields_ignored_by_default(self):
        cfg = AppConfig.model_validate({"unknown_key": True})
        assert cfg.server.port == 8080
