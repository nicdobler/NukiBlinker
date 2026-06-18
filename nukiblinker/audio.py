"""Audio generation — TTS via gTTS and the single bundled chime."""

from __future__ import annotations

import os
import re
import unicodedata
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

# Single, fixed chime (#179). It is a WAV generated at Docker build time by
# ``script/generate_chime.py`` (pure stdlib, no transcoding) and served as-is to
# the speakers — the fastest path during event processing, with no fallback and
# no per-event configuration.
CHIME_FILENAME = "chime.wav"

# Persistent TTS cache directory (#178). Generated mp3s are stored here keyed by
# the spoken message so repeated announcements replay instantly across restarts.
# In Docker this resolves to ``/app/cache/tts`` and is mounted as a volume.
_TTS_CACHE_DIR = Path(os.environ.get("NUKIBLINKER_TTS_CACHE_DIR", "cache/tts"))

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


def _chime_path() -> Path:
    """Return the path to the single fixed chime file (#179)."""
    return _SOUNDS_DIR / CHIME_FILENAME


def tts_cache_filename(message: str) -> str:
    """Build a filesystem/URL-safe cache filename for a TTS ``message`` (#178).

    The name is the message without spaces, ASCII-normalised so it is safe both
    as a filename and inside the ``/audio/{filename}`` URL served to speakers.
    """
    normalized = unicodedata.normalize("NFKD", message)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    no_spaces = re.sub(r"\s+", "", ascii_str)
    safe = re.sub(r"[^A-Za-z0-9._-]", "", no_spaces)
    return (safe or "tts") + ".mp3"


def get_audio(audio_config: AudioConfig, context: dict) -> Path:
    """Return path to an audio file for the given audio configuration.

    - mode="chime": returns the single fixed chime file (no fallback, #179).
    - mode="tts": renders the message template and generates TTS audio, served
      from a persistent on-disk cache keyed by the message (#178).
    """
    if audio_config.mode == "chime":
        chime_path = _chime_path()
        _register_file(chime_path)
        return chime_path  # caller checks existence before playback

    # TTS mode — persistent disk cache keyed by the spoken message (#178)
    message = render_message(audio_config.message, context, audio_config.fallback_name)
    cache_path = _TTS_CACHE_DIR / tts_cache_filename(message)

    if cache_path.exists():
        logger.debug("TTS cache hit (persistent) for message: '%s'", message)
        _register_file(cache_path)
        return cache_path

    if gTTS is None:
        logger.warning("gTTS not installed — falling back to chime")
        fallback = _chime_path()
        _register_file(fallback)
        return fallback

    logger.info("Generating TTS for message: '%s'", message)
    try:
        tts = gTTS(text=message, lang="es")
        _TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tts.save(str(cache_path))
        logger.info("TTS audio cached: %s (%d bytes)", cache_path.name, cache_path.stat().st_size)
        _register_file(cache_path)
        return cache_path
    except Exception:
        logger.error(
            "TTS generation failed (gTTS needs internet) for: '%s' — falling back to chime",
            message, exc_info=True,
        )
        fallback = _chime_path()
        _register_file(fallback)
        return fallback
