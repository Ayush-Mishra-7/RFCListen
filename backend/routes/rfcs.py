"""
Routes — /api/rfcs
"""
from fastapi import APIRouter, HTTPException, Query
from rfc_fetcher import get_rfc_list, get_rfc_metadata, get_rfc_text, get_rfc_pdf_url
from rfc_parser import parse_rfc
import httpx

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
