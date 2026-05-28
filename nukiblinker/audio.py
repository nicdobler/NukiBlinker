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


def render_message(template: str, context: dict, fallback_name: str = "Alguien") -> str:
    """Render a message template, replacing {name} with the resolved name."""
    name = context.get("name", fallback_name) or fallback_name
    try:
        return template.format(name=name)
    except (KeyError, IndexError):
        return template


def get_audio(audio_config: AudioConfig, context: dict) -> Path:
    """Return path to an .mp3 file for the given audio configuration.

    - mode="chime": returns the bundled chime file.
    - mode="tts": renders the message template and generates TTS audio.
    """
    if audio_config.mode == "chime":
        chime_path = _SOUNDS_DIR / audio_config.chime
        if not chime_path.exists():
            logger.warning("Chime file not found: %s — falling back to default", chime_path)
            chime_path = _SOUNDS_DIR / "chime.mp3"
        return chime_path

    # TTS mode
    message = render_message(audio_config.message, context, audio_config.fallback_name)
    cache_key = hashlib.md5(message.encode("utf-8")).hexdigest()

    if cache_key in _tts_cache:
        cached = _tts_cache[cache_key]
        if cached.exists():
            logger.debug("TTS cache hit for message: %s", message)
            return cached

    logger.info("Generating TTS for message: %s", message)
    try:
        tts = gTTS(text=message, lang="es")
        tmp = Path(tempfile.mktemp(suffix=".mp3", prefix="nukiblinker_tts_"))
        tts.save(str(tmp))
        _tts_cache[cache_key] = tmp
        return tmp
    except Exception:
        logger.error("TTS generation failed for: %s", message, exc_info=True)
        # Fall back to chime if TTS fails
        return _SOUNDS_DIR / "chime.mp3"
