"""
tts_service.py — TTS abstraction layer.

MVP: All TTS is handled by the browser's Web Speech API on the frontend.
This module exists as a hook for future server-side TTS (Google Cloud TTS / AWS Polly).

When Cloud TTS is configured (env vars present), this module can be used
to pre-generate audio segments server-side and return URLs to the client.
"""
import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")
AWS_POLLY_ACCESS_KEY = os.getenv("AWS_POLLY_ACCESS_KEY", "")


def is_cloud_tts_configured() -> bool:
    """Return True if a Cloud TTS provider is configured via environment."""
    return bool(GOOGLE_TTS_API_KEY or AWS_POLLY_ACCESS_KEY)


def get_tts_provider() -> str:
    """Return the name of the active TTS provider."""
    if GOOGLE_TTS_API_KEY:
        return "google"
    if AWS_POLLY_ACCESS_KEY:
        return "aws_polly"
    return "web_speech_api"  # browser-native default


# Future implementations:
#
# async def synthesize_google(text: str, voice: str) -> bytes:
#     ...
#
# async def synthesize_polly(text: str, voice: str) -> bytes:
#     ...
