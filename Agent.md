# RFCListen — Agent Guide

> **For AI coding assistants**: Read this file in full before making any changes to the project. After completing any task, mark the relevant items in `task.md` as `[x]` (complete) or `[/]` (in progress). Never leave `task.md` out of sync with the actual state of the codebase.

## Project Overview

RFCListen is a web application that allows Network Engineers to listen to IETF RFCs (Request for Comments) using Text-to-Speech (TTS). It fetches RFC documents from the IETF Datatracker API, parses them into clean, speakable segments, and provides an audio player with section-based navigation (timestamps). Special content such as ASCII diagrams and tables are detected and announced verbally so the user can visually reference them in the UI.

---

## Project Structure

```
RFCListen/
├── Agent.md                  # This file — guide for agentic coding assistants
├── PURPOSE.md                # Application purpose and goals
├── task.md                   # Detailed implementation task tracker
├── frontend/                 # Single-page web app (Vanilla HTML/CSS/JS or React)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── backend/                  # Node.js / Python FastAPI backend
│   ├── server.(js|py)
│   ├── rfc_fetcher.(js|py)   # Fetches RFC data from IETF Datatracker
│   ├── rfc_parser.(js|py)    # Parses raw RFC text into structured sections
│   └── tts_service.(js|py)   # Wraps TTS API (Google Cloud TTS / Web Speech API)
├── scripts/                  # Utility scripts (e.g. batch RFC indexing)
└── README.md
```

---

## Tech Stack

| Layer       | Technology                                      |
|-------------|------------------------------------------------|
| Frontend    | HTML5, Vanilla CSS, Vanilla JS (or React/Vite) |
| Backend     | **Python (FastAPI)** — chosen stack             |
| TTS         | Web Speech API (browser-native) for MVP; Google Cloud TTS / AWS Polly for production |
| Package Mgr | `pip` + `requirements.txt` (or `uv` for speed)  |
| RFC Source  | IETF Datatracker REST API (`https://datatracker.ietf.org/api/v1`) + RFC text from `https://www.rfc-editor.org/rfc/rfcXXXX.txt` |
| Data Format | JSON for API responses; Plain text + Markdown for RFC content |

---

## Core Features

### 1. RFC Browser
- Fetch a paginated list of all published RFCs from the IETF Datatracker API.
- Allow search/filter by RFC number, title, category, working group, and date.
- Display RFC metadata: number, title, authors, date, status (e.g., Standards Track, Informational).

### 2. RFC Parser
The parser is the most critical component. It must:
- Fetch the raw `.txt` version of the RFC from `https://www.rfc-editor.org/rfc/rfcXXXX.txt`.
- Strip **page headers/footers** (e.g., `[Page N]`, author lines that repeat at page breaks).
- Strip the **Table of Contents** section entirely (it is not useful for audio).
- Strip **boilerplate** sections (Copyright Notice, Status of This Memo) — optionally announce them as skippable.
- Detect **section headings** (e.g., `1.  Introduction`, `2.1.  Terminology`) and record them as **named timestamps**.
- Detect **ASCII art / diagrams** (blocks of lines with `+`, `-`, `|`, `.`, `*` or heavy use of whitespace indentation) and replace them with a spoken announcement: *"[Figure N: Description if available — view in the application]"*.
- Detect **tables** (lines with multiple `|` separators) and replace with: *"[Table N — view in the application]"*.
- Normalize whitespace: collapse multiple blank lines, remove soft line wraps, join continuation lines within paragraphs.
- Output a structured JSON object:
  ```json
  {
    "rfcNumber": 793,
    "title": "Transmission Control Protocol",
    "sections": [
      {
        "id": "s1",
        "heading": "1.  Introduction",
        "content": "...",
        "type": "text"
      },
      {
        "id": "fig1",
        "heading": "Figure 1",
        "content": "[Figure 1 — view in the application]",
        "type": "figure",
        "rawAscii": "..."
      }
    ]
  }
  ```

### 3. TTS Audio Player
- At the MVP level, use the **Web Speech API** (`SpeechSynthesis`) available natively in browsers — no API key required.
- Queue each section as a separate utterance so the player can skip between sections.
- Player controls:
  - Play / Pause
  - Skip Forward / Backward (by section)
  - Playback speed control (0.5×–2×)
  - Voice selection (from available system voices)
- **Section timestamps panel**: A sidebar or drawer showing all section headings. Clicking a heading jumps playback to that section.
- When playback reaches a `figure` or `table` section, display it visually in the UI and speak the announcement text.

### 4. RFC Viewer (Visual Panel)
- Render the current section's text in a readable typography panel alongside the audio player.
- Highlight the currently spoken sentence or paragraph.
- When a figure/table is encountered, render the raw ASCII art or table in a monospace font block.

---

## IETF Datatracker API Reference

Base URL: `https://datatracker.ietf.org/api/v1`

| Endpoint | Description |
|----------|-------------|
| `GET /doc/document/?type=rfc&limit=50&offset=0` | Paginated list of RFC documents |
| `GET /doc/document/?name=rfc793` | Fetch a specific RFC's metadata |
| `GET https://www.rfc-editor.org/rfc/rfcXXXX.txt` | Raw plain-text RFC content |
| `GET https://datatracker.ietf.org/doc/rfcXXXX/doc.json` | Simplified RFC metadata JSON |

RFC text files do not require authentication.

---

## Coding Conventions

- **Backend**: Use `async`/`await` with FastAPI and `httpx` for async HTTP calls. Add proper HTTPException handling for RFC-not-found (404) and upstream failures.
- **Parser**: Write `pytest` unit tests in `backend/tests/` using sample RFC snippets — especially edge cases like multi-line ASCII diagrams and continuation-line paragraphs.
- **Frontend**: Keep state management simple. Use a single `state` object and pure functions to update the UI.
- **TTS**: Wrap TTS calls in a service class/module so swapping the engine (Web Speech API → Cloud TTS) requires no changes to the rest of the app.
- **Accessibility**: Ensure all interactive controls have ARIA labels.
- **No external CSS frameworks** unless explicitly approved — use Vanilla CSS with CSS custom properties for theming.
- **task.md hygiene**: After every meaningful code change, update `task.md` — mark items `[/]` when starting, `[x]` when done.

---

## What NOT to Do

- Do **not** read out page headers, footers, or the Table of Contents section.
- Do **not** attempt to speak ASCII diagrams literally — detect and announce them visually instead.
- Do **not** store entire RFC text in the database — always fetch on demand and cache locally.
- Do **not** break section boundaries mid-sentence when chunking for TTS.

---

## Environment Variables (`.env`)

```
# Backend
RFC_CACHE_DIR=./cache
PORT=3000

# Optional: Cloud TTS (leave blank to use Web Speech API)
GOOGLE_TTS_API_KEY=
AWS_POLLY_ACCESS_KEY=
AWS_POLLY_SECRET_KEY=
AWS_POLLY_REGION=
```

---

## Development Setup

```bash
# Create and activate a virtual environment
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# Install backend dependencies
pip install -r requirements.txt

# Start backend dev server
uvicorn server:app --reload --port 3000

# Open frontend (from repo root)
npx live-server frontend/
```

---

## Key References

- [IETF Datatracker API Docs](https://datatracker.ietf.org/api/v1/?format=json)
- [RFC Editor](https://www.rfc-editor.org/)
- [Web Speech API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [RFC 7322 — RFC Style Guide](https://www.rfc-editor.org/rfc/rfc7322.txt) (explains RFC formatting conventions used by the parser)
