"""Quick test to see what word boundary data edge_tts provides."""
import asyncio
import json
import edge_tts

async def main():
    text = "Hello world, this is a test of word boundary timing data from Edge TTS."
    # KEY: Must set boundary='WordBoundary' to get word-level timing!
    comm = edge_tts.Communicate(text, "en-US-GuyNeural", boundary="WordBoundary")

    boundaries = []
    audio_size = 0

    async for chunk in comm.stream():
        if chunk["type"] == "WordBoundary":
            boundaries.append({
                "text": chunk.get("text"),
                "offset": chunk.get("offset"),
                "duration": chunk.get("duration"),
            })
        elif chunk["type"] == "audio":
            audio_size += len(chunk["data"])

    print(f"Audio size: {audio_size} bytes")
    print(f"Number of word boundaries: {len(boundaries)}")
    print()
    for b in boundaries:
        offset_ms = b["offset"] / 10000 if b["offset"] else 0  # 100-nanosecond units to ms
        duration_ms = b["duration"] / 10000 if b["duration"] else 0
        print(f"  Word: {b['text']:20s}  offset: {offset_ms:8.1f}ms  duration: {duration_ms:8.1f}ms")

asyncio.run(main())
