"""Tests for nukiblinker.audio — template rendering, TTS mock, chime resolution."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from nukiblinker.audio import render_message, get_audio
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
    def test_chime_mode_returns_chime_path(self, tmp_path):
        chime_file = tmp_path / "doorbell.mp3"
        chime_file.write_bytes(b"fake-audio")

        cfg = AudioConfig(enabled=True, mode="chime", chime="doorbell.mp3")
        with patch("nukiblinker.audio._SOUNDS_DIR", tmp_path):
            result = get_audio(cfg, {})
            assert result == chime_file

    def test_chime_missing_falls_back_to_default(self, tmp_path):
        default_chime = tmp_path / "chime.mp3"
        default_chime.write_bytes(b"default")

        cfg = AudioConfig(enabled=True, mode="chime", chime="nonexistent.mp3")
        with patch("nukiblinker.audio._SOUNDS_DIR", tmp_path):
            result = get_audio(cfg, {})
            assert result == default_chime


class TestGetAudioTTS:
    def test_tts_generates_audio(self, tmp_path):
        cfg = AudioConfig(enabled=True, mode="tts", message="{name} llegó a casa")

        mock_tts_instance = MagicMock()
        with patch("nukiblinker.audio.gTTS", return_value=mock_tts_instance) as mock_gtts_cls:
            # Make save() create the file
            def fake_save(path):
                Path(path).write_bytes(b"fake-tts-audio")

            mock_tts_instance.save.side_effect = fake_save

            result = get_audio(cfg, {"name": "Nico"})
            mock_gtts_cls.assert_called_once_with(text="Nico llegó a casa", lang="es")
            assert result.exists()

    def test_tts_uses_cache(self, tmp_path):
        cfg = AudioConfig(enabled=True, mode="tts", message="hello")

        mock_tts_instance = MagicMock()
        with patch("nukiblinker.audio.gTTS", return_value=mock_tts_instance):
            def fake_save(path):
                Path(path).write_bytes(b"audio")

            mock_tts_instance.save.side_effect = fake_save

            # Clear cache
            import nukiblinker.audio as audio_mod
            audio_mod._tts_cache.clear()

            result1 = get_audio(cfg, {})
            result2 = get_audio(cfg, {})
            # gTTS should only be called once — second call hits cache
            assert result1 == result2

    def test_tts_fallback_on_error(self, tmp_path):
        default_chime = tmp_path / "chime.mp3"
        default_chime.write_bytes(b"fallback")

        cfg = AudioConfig(enabled=True, mode="tts", message="test")
        with patch("nukiblinker.audio._SOUNDS_DIR", tmp_path):
            with patch("nukiblinker.audio.gTTS", side_effect=Exception("network error")):
                # Clear cache
                import nukiblinker.audio as audio_mod
                audio_mod._tts_cache.clear()

                result = get_audio(cfg, {})
                assert result == default_chime
