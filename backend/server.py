"""
RFCListen Backend — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(
    title="RFCListen API",
    description="Backend API for fetching, parsing, and serving IETF RFC data to the RFCListen frontend.",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
_origins_raw = os.getenv("ALLOWED_ORIGINS", "https://ayush-mishra-7.github.io,http://localhost:8080,http://127.0.0.1:8080")
origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes (imported after app is created to avoid circular imports) ──────────
from routes import rfcs  # noqa: E402
app.include_router(rfcs.router, prefix="/api")

from rfc_fetcher import get_index_status, kickoff_index_refresh  # noqa: E402


@app.on_event("startup")
async def start_background_index_refresh():
    """Kick off an RFC index refresh in the background when the cache is stale."""
    kickoff_index_refresh()


@app.get("/", tags=["health"])
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "service": "RFCListen API",
        "rfcIndex": get_index_status(),
    }


@app.get("/api/status", tags=["health"])
async def api_status():
    """Return API health plus RFC index cache status."""
    return {
        "status": "ok",
        "service": "RFCListen API",
        "rfcIndex": get_index_status(),
    }


@app.get("/api/rfc-index/status", tags=["health"])
async def rfc_index_status():
    """Return the current RFC index cache freshness and refresh state."""
    return get_index_status()
