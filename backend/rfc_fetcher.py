"""
rfc_fetcher.py — Fetches RFC data from:
  - IETF Datatracker API  (metadata / lists)
  - rfc-editor.org        (raw plain-text RFC content)

Caches plain-text files to disk to avoid redundant network calls.
"""
import os
import re
import httpx
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATATRACKER_BASE = "https://datatracker.ietf.org"
RFC_EDITOR_BASE = "https://www.rfc-editor.org/rfc"
CACHE_DIR = Path(os.getenv("RFC_CACHE_DIR", "./cache"))


def _ensure_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def get_rfc_list(page: int = 1, limit: int = 50, search: str = "") -> dict:
    """
    Fetch a paginated list of published RFCs from the IETF Datatracker API.

    Returns a dict with keys: `count`, `rfcs` (list of metadata dicts), `next`, `previous`.
    """
    offset = (page - 1) * limit
    params = {
        "type": "rfc",
        "limit": limit,
        "offset": offset,
        "format": "json",
    }
    if search:
        params["name__icontains"] = search

    url = f"{DATATRACKER_BASE}/api/v1/doc/document/"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    rfcs = [
        {
            "rfcNumber": _extract_rfc_number(doc.get("name", "")),
            "name": doc.get("name", ""),
            "title": doc.get("title", ""),
            "abstract": doc.get("abstract", ""),
            "status": doc.get("std_level", ""),
            "published": doc.get("time", ""),
        }
        for doc in data.get("objects", [])
    ]

    return {
        "count": data.get("meta", {}).get("total_count", 0),
        "page": page,
        "limit": limit,
        "rfcs": rfcs,
        "next": data.get("meta", {}).get("next"),
        "previous": data.get("meta", {}).get("previous"),
    }


async def get_rfc_metadata(rfc_number: int) -> dict:
    """
    Fetch simplified metadata for a specific RFC from the Datatracker.

    Uses the /doc/rfcXXXX/doc.json simplified endpoint.
    """
    url = f"{DATATRACKER_BASE}/doc/rfc{rfc_number}/doc.json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()


async def get_rfc_text(rfc_number: int) -> str:
    """
    Fetch the raw plain-text content of an RFC from rfc-editor.org.

    Results are cached to disk at CACHE_DIR/rfcXXXX.txt.
    Raises httpx.HTTPStatusError if the RFC does not exist (404).
    """
    _ensure_cache()
    cache_path = CACHE_DIR / f"rfc{rfc_number}.txt"

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="replace")

    url = f"{RFC_EDITOR_BASE}/rfc{rfc_number}.txt"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        text = response.text

    cache_path.write_text(text, encoding="utf-8")
    return text


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_rfc_number(name: str) -> int | None:
    """Extract the integer RFC number from a name like 'rfc793'."""
    match = re.search(r"rfc(\d+)", name, re.IGNORECASE)
    return int(match.group(1)) if match else None
