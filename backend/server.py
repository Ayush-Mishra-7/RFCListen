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
_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://ayush-mishra-7.github.io,http://localhost:8080,http://127.0.0.1:8080")
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


@app.get("/", tags=["health"])
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "RFCListen API"}
