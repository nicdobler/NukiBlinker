"""Tests for nukiblinker.audio — template rendering, TTS cache, fixed chime."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from nukiblinker.audio import render_message, get_audio, tts_cache_filename
from nukiblinker.config import AudioConfig


class TestRenderMessage:
    def test_renders_name(self):
        assert render_message("{name} llegó a casa", {"name": "Nico"}) == "Nico llegó a casa"

    def test_renders_fallback_when_name_missing(self):
        assert render_message("{name} llegó", {}, fallback_name="Alguien") == "Alguien llegó"

    def test_renders_fallback_when_name_empty(self):
        assert render_message("{name} llegó", {"name": ""}, fallback_name="Alguien") == "Alguien llegó"

    def test_renders_fallback_when_name_none(self):
        assert render_message("{name} llegó", {"name": None}, fallback_name="Alguien") == "Alguien llegó"

    def test_no_template_variable(self):
        assert render_message("Alguien está en la puerta", {"name": "X"}) == "Alguien está en la puerta"

    def test_bad_template_returns_original(self):
        assert render_message("{unknown} variable", {"name": "X"}) == "{unknown} variable"


class TestGetAudioChime:
    def test_chime_mode_returns_fixed_chime(self, tmp_path):
        """Chime mode always returns the single bundled chime.wav (#179)."""
        chime_file = tmp_path / "chime.wav"
        chime_file.write_bytes(b"fake-audio")

        cfg = AudioConfig(enabled=True, mode="chime")
        with patch("nukiblinker.audio._SOUNDS_DIR", tmp_path):
            result = get_audio(cfg, {})
            assert result == chime_file

    def test_chime_mode_path_is_fixed_when_missing(self, tmp_path):
        """No fallback: chime mode returns the fixed path even if absent (#179)."""
        cfg = AudioConfig(enabled=True, mode="chime")
        with patch("nukiblinker.audio._SOUNDS_DIR", tmp_path):
            result = get_audio(cfg, {})
            assert result == tmp_path / "chime.wav"


class TestTtsCacheFilename:
    def test_strips_spaces(self):
        assert tts_cache_filename("hola que tal") == "holaquetal.mp3"

    def test_normalises_accents_for_url_safety(self):
        assert tts_cache_filename("Nico llegó a casa") == "Nicollegoacasa.mp3"

    def test_empty_message_falls_back(self):
        assert tts_cache_filename("   ") == "tts.mp3"


class TestGetAudioTTS:
    def test_tts_generates_audio(self, tmp_path):
        cfg = AudioConfig(enabled=True, mode="tts", message="{name} llegó a casa")

        mock_tts_instance = MagicMock()
        with patch("nukiblinker.audio._TTS_CACHE_DIR", tmp_path):
            with patch("nukiblinker.audio.gTTS", return_value=mock_tts_instance) as mock_gtts_cls:
                # Make save() create the file
                def fake_save(path):
                    Path(path).write_bytes(b"fake-tts-audio")

                mock_tts_instance.save.side_effect = fake_save

                result = get_audio(cfg, {"name": "Nico"})
                mock_gtts_cls.assert_called_once_with(text="Nico llegó a casa", lang="es")
                assert result.exists()
                # Filename is the message without spaces (#178)
                assert result.name == "Nicollegoacasa.mp3"

    def test_tts_uses_persistent_cache(self, tmp_path):
        """A second call for the same message reuses the cached file (#178)."""
        cfg = AudioConfig(enabled=True, mode="tts", message="hello")

        mock_tts_instance = MagicMock()
        with patch("nukiblinker.audio._TTS_CACHE_DIR", tmp_path):
            with patch("nukiblinker.audio.gTTS", return_value=mock_tts_instance) as mock_gtts_cls:
                def fake_save(path):
                    Path(path).write_bytes(b"audio")

                mock_tts_instance.save.side_effect = fake_save

                result1 = get_audio(cfg, {})
                result2 = get_audio(cfg, {})
                # gTTS generates only once — second call hits the on-disk cache
                mock_gtts_cls.assert_called_once()
                assert result1 == result2

    def test_tts_cache_survives_across_module_state(self, tmp_path):
        """A pre-existing cached file is served without regenerating (#178)."""
        cfg = AudioConfig(enabled=True, mode="tts", message="hola")
        cached = tmp_path / tts_cache_filename("hola")
        cached.write_bytes(b"cached-audio")

        with patch("nukiblinker.audio._TTS_CACHE_DIR", tmp_path):
            with patch("nukiblinker.audio.gTTS") as mock_gtts_cls:
                result = get_audio(cfg, {})
                mock_gtts_cls.assert_not_called()
                assert result == cached

    def test_tts_fallback_on_error(self, tmp_path):
        default_chime = tmp_path / "chime.wav"
        default_chime.write_bytes(b"fallback")

        cfg = AudioConfig(enabled=True, mode="tts", message="test")
        with patch("nukiblinker.audio._SOUNDS_DIR", tmp_path):
            with patch("nukiblinker.audio._TTS_CACHE_DIR", tmp_path / "cache"):
                with patch("nukiblinker.audio.gTTS", side_effect=Exception("network error")):
                    result = get_audio(cfg, {})
                    assert result == default_chime
