"""
tts_service.py — Edge TTS integration with audio caching and word boundaries.

Synthesises RFC section text into MP3 audio using Microsoft Edge's
free neural TTS service. Audio is cached to disk so repeated requests
for the same section are served instantly.

Word boundary timing data is captured during synthesis and cached
alongside the audio as a companion JSON file, enabling precise
text-highlight synchronization on the frontend.
"""
import hashlib
import json
import os
from pathlib import Path

import edge_tts

from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

# Voice to use.
# Default is BrianMultilingual Online (Natural): en-US-BrianMultilingualNeural
# Run `edge-tts --list-voices` to see all available voices.
DEFAULT_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-BrianMultilingualNeural")

# Cache directory for generated audio files
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "./cache/tts"))


def _ensure_cache():
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(text: str, voice: str) -> str:
    """Generate a deterministic cache key from text + voice."""
    content = f"{voice}:{text}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_audio_cache_path(text: str, voice: str = "") -> Path | None:
    """Check if the audio and boundaries are cached; return audio path if so."""
    voice = voice or DEFAULT_VOICE
    key = _cache_key(text, voice)
    audio_path = TTS_CACHE_DIR / f"{key}.mp3"
    boundaries_path = TTS_CACHE_DIR / f"{key}.json"
    if audio_path.exists() and boundaries_path.exists():
        return audio_path
    return None


def get_boundaries_cache_path(text: str, voice: str = "") -> Path | None:
    """Return the path to the cached word-boundaries JSON if it exists."""
    voice = voice or DEFAULT_VOICE
    key = _cache_key(text, voice)
    path = TTS_CACHE_DIR / f"{key}.json"
    return path if path.exists() else None


async def synthesize_stream(text: str, voice: str = ""):
    """
    Stream audio from Edge TTS to the client while simultaneously
    saving it and the word boundaries to the cache.
    """
    _ensure_cache()
    voice = voice or DEFAULT_VOICE
    key = _cache_key(text, voice)
    audio_path = TTS_CACHE_DIR / f"{key}.mp3"
    boundaries_path = TTS_CACHE_DIR / f"{key}.json"

    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")

    audio_chunks: list[bytes] = []
    boundaries: list[dict] = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data = chunk["data"]
            audio_chunks.append(audio_data)
            yield audio_data
        elif chunk["type"] == "WordBoundary":
            # offset and duration come in 100-nanosecond units; convert to ms
            boundaries.append({
                "text": chunk.get("text", ""),
                "offset": chunk.get("offset", 0) / 10_000,
                "duration": chunk.get("duration", 0) / 10_000,
            })

    # Write audio file
    audio_path.write_bytes(b"".join(audio_chunks))

    # Write companion word boundaries JSON
    boundaries_path.write_text(
        json.dumps(boundaries, ensure_ascii=False),
        encoding="utf-8",
    )


async def synthesize(text: str, voice: str = "") -> tuple[Path, list[dict]]:
    """
    Synthesise text to MP3 using Edge TTS with word boundary data.

    Returns a tuple of:
      - Path to the cached MP3 file
      - List of word boundary dicts: [{"text", "offset", "duration"}, ...]
        where offset and duration are in milliseconds.

    If the audio is already cached, loads boundaries from the companion
    JSON file and returns immediately.
    """
    _ensure_cache()
    voice = voice or DEFAULT_VOICE
    key = _cache_key(text, voice)
    audio_path = TTS_CACHE_DIR / f"{key}.mp3"
    boundaries_path = TTS_CACHE_DIR / f"{key}.json"

    # Return from cache if both files exist
    if audio_path.exists() and boundaries_path.exists():
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        return audio_path, boundaries

    # Stream audio + word boundaries from Edge TTS
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")

    audio_chunks: list[bytes] = []
    boundaries: list[dict] = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            # offset and duration come in 100-nanosecond units; convert to ms
            boundaries.append({
                "text": chunk.get("text", ""),
                "offset": chunk.get("offset", 0) / 10_000,
                "duration": chunk.get("duration", 0) / 10_000,
            })

    # Write audio file
    audio_path.write_bytes(b"".join(audio_chunks))

    # Write companion word boundaries JSON
    boundaries_path.write_text(
        json.dumps(boundaries, ensure_ascii=False),
        encoding="utf-8",
    )

    return audio_path, boundaries


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
