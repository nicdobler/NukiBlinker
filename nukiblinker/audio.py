"""Audio generation — TTS via gTTS and bundled chime selection."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from nukiblinker.logging_config import get_logger

if TYPE_CHECKING:
    from nukiblinker.config import AudioConfig

logger = get_logger("audio")

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover
    gTTS = None  # type: ignore[assignment,misc]

_SOUNDS_DIR = Path(__file__).parent / "sounds"
_tts_cache: dict[str, Path] = {}

# Set by the notifier at dispatch time so get_audio can register files
_audio_registry: dict[str, Path] | None = None


def render_message(template: str, context: dict, fallback_name: str = "Alguien") -> str:
    """Render a message template, replacing {name} with the resolved name."""
    name = context.get("name", fallback_name) or fallback_name
    try:
        return template.format(name=name)
    except (KeyError, IndexError):
        return template


def _register_file(path: Path) -> str:
    """Register a file in the audio registry and return its serving filename."""
    filename = path.name
    if _audio_registry is not None:
        _audio_registry[filename] = path
    return filename


def get_audio(audio_config: AudioConfig, context: dict) -> Path:
    """Return path to an .mp3 file for the given audio configuration.

    - mode="chime": returns the bundled chime file.
    - mode="tts": renders the message template and generates TTS audio.
    """
    if audio_config.mode == "chime":
        chime_path = _SOUNDS_DIR / audio_config.chime
        if not chime_path.exists():
            default = _SOUNDS_DIR / "chime.wav"
            if default.exists():
                logger.warning("Chime file not found: %s — falling back to default", chime_path)
                chime_path = default
            else:
                logger.warning("No chime files found in %s — audio will be skipped", _SOUNDS_DIR)
                return chime_path  # caller must handle missing file
        _register_file(chime_path)
        return chime_path

    # TTS mode
    message = render_message(audio_config.message, context, audio_config.fallback_name)
    cache_key = hashlib.md5(message.encode("utf-8")).hexdigest()

    if cache_key in _tts_cache:
        cached = _tts_cache[cache_key]
        if cached.exists():
            logger.debug("TTS cache hit for message: %s", message)
            _register_file(cached)
            return cached

    if gTTS is None:
        logger.warning("gTTS not installed — falling back to chime")
        fallback = _SOUNDS_DIR / "chime.wav"
        _register_file(fallback)
        return fallback

    logger.info("Generating TTS for message: '%s'", message)
    try:
        tts = gTTS(text=message, lang="es")
        tmp_fd = tempfile.NamedTemporaryFile(suffix=".mp3", prefix="nukiblinker_tts_", delete=False)
        tmp = Path(tmp_fd.name)
        tmp_fd.close()
        tts.save(str(tmp))
        logger.info("TTS audio saved: %s (%d bytes)", tmp.name, tmp.stat().st_size)
        _tts_cache[cache_key] = tmp
        _register_file(tmp)
        return tmp
    except Exception:
        logger.error(
            "TTS generation failed (gTTS needs internet) for: '%s' — falling back to chime",
            message, exc_info=True,
        )
        fallback = _SOUNDS_DIR / "chime.wav"
        _register_file(fallback)
        return fallback
