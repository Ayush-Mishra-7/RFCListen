"""
rfc_fetcher.py — Fetches RFC data from:
  - IETF Datatracker API  (metadata / lists)
  - rfc-editor.org        (raw plain-text RFC content)

Caches plain-text files to disk to avoid redundant network calls.
"""
import os
import re
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
import httpx
from pathlib import Path
from dotenv import load_dotenv

import json

DATATRACKER_BASE = "https://datatracker.ietf.org"
RFC_TEXT_BASE = "https://www.ietf.org/rfc"  # rfc-editor.org has Cloudflare bot protection
_BASE_DIR = Path(__file__).resolve().parent
_cache_dir_raw = os.getenv("RFC_CACHE_DIR")
CACHE_DIR = Path(_cache_dir_raw) if _cache_dir_raw else (_BASE_DIR / "cache")
if not CACHE_DIR.is_absolute():
    CACHE_DIR = (_BASE_DIR / CACHE_DIR).resolve()
INDEX_MAX_AGE_SECONDS = int(os.getenv("RFC_INDEX_MAX_AGE_SECONDS", "86400"))
INDEX_REFRESH_MIN_INTERVAL_SECONDS = int(
    os.getenv("RFC_INDEX_REFRESH_MIN_INTERVAL_SECONDS", "3600")
)

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
_RFC_INDEX_MTIME = None
_RFC_INDEX_REFRESH_LOCK = threading.Lock()
_RFC_INDEX_LAST_REFRESH_ATTEMPT = 0.0
_RFC_INDEX_LAST_REFRESH_ATTEMPT_AT = None
_RFC_INDEX_LAST_REFRESH_COMPLETED_AT = None
_RFC_INDEX_LAST_REFRESH_ERROR = None


def _get_index_path() -> Path:
    return CACHE_DIR / "rfc_index.json"


def _get_refresh_script_path() -> Path:
    return Path(__file__).parent / "scripts" / "refresh_rfc_data.py"


def _get_mtime(path: Path) -> float | None:
    if not path.exists():
        return None
    return path.stat().st_mtime


def _to_iso8601(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat().replace("+00:00", "Z")


def _is_index_stale(index_path: Path) -> bool:
    mtime = _get_mtime(index_path)
    if mtime is None:
        return True
    return (time.time() - mtime) > INDEX_MAX_AGE_SECONDS


def _run_refresh_script(blocking: bool) -> bool:
    global _RFC_INDEX_LAST_REFRESH_COMPLETED_AT, _RFC_INDEX_LAST_REFRESH_ERROR

    script = _get_refresh_script_path()
    if not script.exists():
        print(f"Index refresh script not found at {script}")
        return False

    command = [sys.executable, str(script)]

    if blocking:
        try:
            subprocess.run(command, check=True, timeout=300)
            _RFC_INDEX_LAST_REFRESH_COMPLETED_AT = time.time()
            _RFC_INDEX_LAST_REFRESH_ERROR = None
        except Exception as exc:
            _RFC_INDEX_LAST_REFRESH_ERROR = str(exc)
            raise
        return True

    def _background_refresh() -> None:
        global _RFC_INDEX, _RFC_INDEX_MTIME, _RFC_INDEX_LAST_REFRESH_COMPLETED_AT, _RFC_INDEX_LAST_REFRESH_ERROR
        try:
            subprocess.run(command, check=True, timeout=300)
            _RFC_INDEX = None
            _RFC_INDEX_MTIME = None
            _RFC_INDEX_LAST_REFRESH_COMPLETED_AT = time.time()
            _RFC_INDEX_LAST_REFRESH_ERROR = None
            print("RFC index refresh completed in background.")
        except Exception as exc:
            _RFC_INDEX_LAST_REFRESH_ERROR = str(exc)
            print(f"Background RFC index refresh failed: {exc}")
        finally:
            _RFC_INDEX_REFRESH_LOCK.release()

    thread = threading.Thread(target=_background_refresh, daemon=True)
    thread.start()
    return True


def _maybe_refresh_index(index_path: Path, blocking: bool) -> bool:
    global _RFC_INDEX_LAST_REFRESH_ATTEMPT, _RFC_INDEX_LAST_REFRESH_ATTEMPT_AT

    if not _is_index_stale(index_path):
        return False

    if blocking:
        with _RFC_INDEX_REFRESH_LOCK:
            _RFC_INDEX_LAST_REFRESH_ATTEMPT_AT = time.time()
            _run_refresh_script(blocking=True)
            _RFC_INDEX_LAST_REFRESH_ATTEMPT = time.monotonic()
            return True

    now = time.monotonic()
    if (now - _RFC_INDEX_LAST_REFRESH_ATTEMPT) < INDEX_REFRESH_MIN_INTERVAL_SECONDS:
        return False

    if not _RFC_INDEX_REFRESH_LOCK.acquire(blocking=False):
        return False

    _RFC_INDEX_LAST_REFRESH_ATTEMPT = now
    _RFC_INDEX_LAST_REFRESH_ATTEMPT_AT = time.time()
    if _run_refresh_script(blocking=False):
        return True

    _RFC_INDEX_REFRESH_LOCK.release()
    return False


def kickoff_index_refresh() -> None:
    """Start a background refresh when the cached RFC index is stale."""
    index_path = _get_index_path()
    try:
        _maybe_refresh_index(index_path, blocking=False)
    except Exception as exc:
        print(f"Failed to start background RFC index refresh: {exc}")


def get_index_status() -> dict:
    """Return cache freshness and refresh metadata for the RFC index."""
    index_path = _get_index_path()
    xml_path = CACHE_DIR / "rfc_index.xml"
    index_mtime = _get_mtime(index_path)
    xml_mtime = _get_mtime(xml_path)
    now = time.time()
    age_seconds = None if index_mtime is None else max(0.0, now - index_mtime)

    return {
        "cachePath": str(index_path),
        "xmlCachePath": str(xml_path),
        "exists": index_path.exists(),
        "xmlExists": xml_path.exists(),
        "stale": _is_index_stale(index_path),
        "ageSeconds": None if age_seconds is None else round(age_seconds, 1),
        "maxAgeSeconds": INDEX_MAX_AGE_SECONDS,
        "refreshIntervalSeconds": INDEX_REFRESH_MIN_INTERVAL_SECONDS,
        "lastUpdatedAt": _to_iso8601(index_mtime),
        "xmlLastUpdatedAt": _to_iso8601(xml_mtime),
        "lastRefreshAttemptAt": _to_iso8601(_RFC_INDEX_LAST_REFRESH_ATTEMPT_AT),
        "lastRefreshCompletedAt": _to_iso8601(_RFC_INDEX_LAST_REFRESH_COMPLETED_AT),
        "refreshInProgress": _RFC_INDEX_REFRESH_LOCK.locked(),
        "lastRefreshError": _RFC_INDEX_LAST_REFRESH_ERROR,
    }

def _load_index():
    global _RFC_INDEX, _RFC_INDEX_MTIME

    index_path = _get_index_path()

    if not index_path.exists():
        print("Warning: rfc_index.json not found in cache. Attempting to generate...")
        try:
            _maybe_refresh_index(index_path, blocking=True)
            print("rfc_index.json generated successfully.")
        except Exception as e:
            print(f"Failed to auto-generate rfc_index.json: {e}")
    else:
        try:
            _maybe_refresh_index(index_path, blocking=False)
        except Exception as e:
            print(f"Failed to trigger background RFC index refresh: {e}")

    if not index_path.exists():
        print("Error: rfc_index.json still not available. RFC list will be empty.")
        return []

    current_mtime = _get_mtime(index_path)
    if _RFC_INDEX is not None and _RFC_INDEX_MTIME == current_mtime:
        return _RFC_INDEX

    with open(index_path, "r", encoding="utf-8") as f:
        _RFC_INDEX = json.load(f)
    _RFC_INDEX_MTIME = current_mtime
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
            if (search_lower in str(rfc.get("rfcNumber")) or 
                search_lower in f"rfc {rfc.get('rfcNumber')}" or
                search_lower in f"rfc{rfc.get('rfcNumber')}" or
                search_lower in rfc.get("title", "").lower())
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


RFC_PDF_BASE = "https://www.ietf.org/rfc"  # same host as .txt — rfc-editor.org blocks via Cloudflare


async def get_rfc_pdf_url(rfc_number: int) -> str | None:
    """
    Check if a PDF version of the RFC exists at rfc-editor.org.

    Returns the full URL if the PDF exists (HTTP 200), otherwise None.
    """
    url = f"{RFC_PDF_BASE}/rfc{rfc_number}.pdf"
    try:
        async with _client(timeout=10.0) as client:
            response = await client.head(url)
            if response.status_code == 200:
                return url
    except httpx.HTTPError:
        pass
    return None


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
