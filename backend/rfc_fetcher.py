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

import json

DATATRACKER_BASE = "https://datatracker.ietf.org"
RFC_TEXT_BASE = "https://www.ietf.org/rfc"  # rfc-editor.org has Cloudflare bot protection
CACHE_DIR = Path(os.getenv("RFC_CACHE_DIR", "./cache"))

# rfc-editor.org blocks the default httpx user-agent (403).
_HEADERS = {
    "User-Agent": "RFCListen/0.1 (https://github.com/rfclisten; educational project)",
}


def _ensure_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _client(**kwargs) -> httpx.AsyncClient:
    """Create a pre-configured async HTTP client."""
    return httpx.AsyncClient(
        headers=_HEADERS,
        follow_redirects=True,
        timeout=kwargs.pop("timeout", 15.0),
        **kwargs,
    )


_RFC_INDEX = None

def _load_index():
    global _RFC_INDEX
    if _RFC_INDEX is not None:
        return _RFC_INDEX
        
    index_path = CACHE_DIR / "rfc_index.json"
    if not index_path.exists():
        # Fallback to empty list or ideally we'd trigger an index generation here,
        # but to keep it simple we just return empty list.
        print("Warning: rfc_index.json not found in cache. Run scripts/update_rfc_index.py")
        return []
        
    with open(index_path, "r", encoding="utf-8") as f:
        _RFC_INDEX = json.load(f)
    return _RFC_INDEX

async def get_rfc_list(page: int = 1, limit: int = 50, search: str = "", sort: str = "desc") -> dict:
    """
    Fetch a paginated list of published RFCs from the local rfc_index.json.

    Returns a dict with keys: `count`, `rfcs` (list of metadata dicts), `next`, `previous`.
    """
    index = _load_index()
    
    # Filter
    filtered = index
    if search:
        search_lower = search.lower()
        filtered = [
            rfc for rfc in filtered 
            if search_lower in str(rfc.get("rfcNumber")) or search_lower in rfc.get("title", "").lower()
        ]
        
    # Sort
    is_reverse = (sort == "desc")
    # rfcNumber is an integer locally we can sort on reliably safely
    filtered = sorted(filtered, key=lambda x: x.get("rfcNumber", 0), reverse=is_reverse)
    
    # Paginate
    total_count = len(filtered)
    offset = (page - 1) * limit
    paginated = filtered[offset:offset+limit]
    
    # Generate next/prev mock URLs just for frontend compat if needed
    base_query = f"?limit={limit}&search={search}&sort={sort}"
    has_next = (offset + limit) < total_count
    has_prev = page > 1
    
    return {
        "count": total_count,
        "page": page,
        "limit": limit,
        "rfcs": paginated,
        "next": base_query + f"&page={page+1}" if has_next else None,
        "previous": base_query + f"&page={page-1}" if has_prev else None,
    }


async def get_rfc_metadata(rfc_number: int) -> dict:
    """
    Fetch simplified metadata for a specific RFC from the local index.
    """
    index = _load_index()
    for rfc in index:
        if rfc.get("rfcNumber") == rfc_number:
            return rfc
    return {}


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

    url = f"{RFC_TEXT_BASE}/rfc{rfc_number}.txt"
    async with _client(timeout=30.0) as client:
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


# Map IETF Datatracker slug → human-readable label
_STATUS_MAP = {
    "ps": "Proposed Standard",
    "ds": "Draft Standard",
    "std": "Internet Standard",
    "bcp": "Best Current Practice",
    "inf": "Informational",
    "exp": "Experimental",
    "hist": "Historic",
    "unkn": "Unknown",
}


def _clean_status(raw: str) -> str:
    """Convert API resource URIs like '/api/v1/name/stdlevelname/ps/' to labels."""
    if not raw:
        return ""
    # Extract the slug from URIs like /api/v1/name/stdlevelname/ps/
    slug = raw.rstrip("/").rsplit("/", 1)[-1].lower()
    return _STATUS_MAP.get(slug, slug.upper())
