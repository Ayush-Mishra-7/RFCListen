"""
tts_service.py — Edge TTS integration with audio caching.

Synthesises RFC section text into MP3 audio using Microsoft Edge's
free neural TTS service. Audio is cached to disk so repeated requests
for the same section are served instantly.
"""
import hashlib
import os
from pathlib import Path

import edge_tts

from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

# Voice to use — "en-US-GuyNeural" is a clear, professional male voice.
# Run `edge-tts --list-voices` to see all available voices.
DEFAULT_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-GuyNeural")

# Cache directory for generated audio files
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "./cache/tts"))


def _ensure_cache():
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(text: str, voice: str) -> str:
    """Generate a deterministic cache key from text + voice."""
    content = f"{voice}:{text}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def synthesize(text: str, voice: str = "") -> Path:
    """
    Synthesise text to MP3 using Edge TTS.

    Returns the Path to the cached MP3 file.
    If the audio is already cached, returns immediately.
    """
    _ensure_cache()
    voice = voice or DEFAULT_VOICE
    key = _cache_key(text, voice)
    cache_path = TTS_CACHE_DIR / f"{key}.mp3"

    if cache_path.exists():
        return cache_path

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(cache_path))
    return cache_path


async def list_voices() -> list[dict]:
    """Return a list of available Edge TTS voices."""
    voices = await edge_tts.list_voices()
    # Filter to English voices and return a simplified list
    english_voices = [
        {
            "id": v["ShortName"],
            "name": v["FriendlyName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
        }
        for v in voices
        if v["Locale"].startswith("en")
    ]
    return english_voices
