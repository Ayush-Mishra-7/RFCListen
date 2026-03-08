"""
Routes — /api/rfcs
"""
from fastapi import APIRouter, HTTPException, Query
from rfc_fetcher import get_rfc_list, get_rfc_metadata, get_rfc_text, get_rfc_pdf_url
from rfc_parser import parse_rfc
import httpx
from urllib.parse import quote

router = APIRouter(tags=["rfcs"])


@router.get("/rfcs")
async def list_rfcs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    search: str = Query("", description="Filter by RFC name/title"),
    sort: str = Query("desc", description="Sort order: 'desc' or 'asc'"),
):
    """Return a paginated list of published RFCs."""
    try:
        return await get_rfc_list(page=page, limit=limit, search=search, sort=sort)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")


@router.get("/rfc/{rfc_number}/metadata")
async def rfc_metadata(rfc_number: int):
    """Return metadata for a specific RFC."""
    try:
        data = await get_rfc_metadata(rfc_number)
        if not data:
            raise HTTPException(status_code=404, detail=f"RFC {rfc_number} not found")
        return data
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"RFC {rfc_number} not found")
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")


@router.get("/rfc/{rfc_number}/parsed")
async def rfc_parsed(rfc_number: int):
    """
    Return the structured, parsed RFC content (sections, figures, tables).
    This is the primary endpoint consumed by the frontend player.

    If no plain-text is available but a PDF exists, returns a pdfOnly response
    so the frontend can offer the user a link to the PDF.
    """
    try:
        raw_text = await get_rfc_text(rfc_number)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # No .txt available — check if a PDF exists as fallback
            pdf_url = await get_rfc_pdf_url(rfc_number)
            if pdf_url:
                # Try to get the title from metadata
                meta = await get_rfc_metadata(rfc_number)
                title = meta.get("title", f"RFC {rfc_number}") if meta else f"RFC {rfc_number}"
                return {
                    "rfcNumber": rfc_number,
                    "pdfOnly": True,
                    "pdfUrl": pdf_url,
                    "title": title,
                }
            raise HTTPException(status_code=404, detail=f"RFC {rfc_number} text not found")
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    try:
        parsed = parse_rfc(rfc_number, raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parser error: {e}")

    return parsed


@router.get("/rfc/{rfc_number}/tts/{section_idx}")
async def rfc_section_tts(
    rfc_number: int,
    section_idx: int,
    voice: str = Query("", description="Edge TTS voice ID (e.g. en-US-GuyNeural)"),
):
    """
    Synthesise a single RFC section as MP3 audio using Edge TTS.

    Returns an MP3 audio stream that the frontend can play via <audio>.
    Audio is cached to disk — repeated requests are served instantly.
    """
    from tts_service import synthesize_stream, get_audio_cache_path
    from rfc_parser import parse_rfc
    from rfc_fetcher import get_rfc_text
    from fastapi.responses import FileResponse, StreamingResponse

    # Get the parsed RFC and extract the requested section
    try:
        raw_text = await get_rfc_text(rfc_number)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"RFC {rfc_number} not found")

    parsed = parse_rfc(rfc_number, raw_text)
    sections = parsed["sections"]

    if section_idx < 0 or section_idx >= len(sections):
        raise HTTPException(status_code=404, detail=f"Section {section_idx} not found")

    section = sections[section_idx]
    text = section["content"]

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Section has no speakable content")

    try:
        cache_path = get_audio_cache_path(text, voice)
        if cache_path:
            return FileResponse(
                path=str(cache_path),
                media_type="audio/mpeg",
                filename=f"rfc{rfc_number}_s{section_idx}.mp3",
            )
            
        return StreamingResponse(
            synthesize_stream(text, voice),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="rfc{rfc_number}_s{section_idx}.mp3"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {e}")


@router.get("/rfc/{rfc_number}/tts/{section_idx}/boundaries")
async def rfc_section_boundaries(
    rfc_number: int,
    section_idx: int,
    voice: str = Query("", description="Edge TTS voice ID (e.g. en-US-GuyNeural)"),
):
    """
    Return word boundary timing data for a given RFC section.

    Each boundary contains:
      - text: the word spoken
      - offset: start time in milliseconds
      - duration: word duration in milliseconds

    This endpoint is called by the frontend alongside the audio request
    to enable precise text-highlight synchronization.
    """
    from tts_service import synthesize
    from rfc_parser import parse_rfc
    from rfc_fetcher import get_rfc_text

    try:
        raw_text = await get_rfc_text(rfc_number)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"RFC {rfc_number} not found")

    parsed = parse_rfc(rfc_number, raw_text)
    sections = parsed["sections"]

    if section_idx < 0 or section_idx >= len(sections):
        raise HTTPException(status_code=404, detail=f"Section {section_idx} not found")

    section = sections[section_idx]
    text = section["content"]

    if not text or not text.strip():
        return {"boundaries": []}

    try:
        _audio_path, boundaries = await synthesize(text, voice)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {e}")

    return {"boundaries": boundaries}


@router.get("/rfc/{rfc_number}/tts/{section_idx}/package")
async def rfc_section_tts_package(
    rfc_number: int,
    section_idx: int,
    voice: str = Query("", description="Edge TTS voice ID (e.g. en-US-BrianMultilingualNeural)"),
):
    """
    Generate (or load from cache) both audio and boundaries in a single synthesis path.

    This endpoint guarantees the frontend receives word-boundary timing data that
    corresponds to the same synthesized audio artifact.
    """
    from tts_service import synthesize, get_audio_cache_path
    from rfc_parser import parse_rfc
    from rfc_fetcher import get_rfc_text

    try:
        raw_text = await get_rfc_text(rfc_number)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=404, detail=f"RFC {rfc_number} not found")

    parsed = parse_rfc(rfc_number, raw_text)
    sections = parsed["sections"]

    if section_idx < 0 or section_idx >= len(sections):
        raise HTTPException(status_code=404, detail=f"Section {section_idx} not found")

    section = sections[section_idx]
    text = section["content"]

    if not text or not text.strip():
        return {
            "audioUrl": f"/api/rfc/{rfc_number}/tts/{section_idx}",
            "boundaries": [],
            "fromCache": True,
            "diagnostics": {
                "boundariesCount": 0,
                "textLength": 0,
                "sectionType": section.get("type", "text"),
            },
        }

    cache_before = get_audio_cache_path(text, voice) is not None

    try:
        _audio_path, boundaries = await synthesize(text, voice)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {e}")

    audio_url = f"/api/rfc/{rfc_number}/tts/{section_idx}"
    if voice:
        audio_url += f"?voice={quote(voice, safe='')}"

    return {
        "audioUrl": audio_url,
        "boundaries": boundaries,
        "fromCache": cache_before,
        "diagnostics": {
            "boundariesCount": len(boundaries),
            "textLength": len(text),
            "sectionType": section.get("type", "text"),
            "voice": voice or "default",
        },
    }


@router.get("/tts/voices")
async def tts_voices():
    """Return available Edge TTS English voices."""
    from tts_service import list_voices

    try:
        voices = await list_voices()
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list voices: {e}")

