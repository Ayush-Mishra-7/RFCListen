# 🎙️ RFCListen

A web application for Network Engineers to **listen to IETF RFCs** using Text-to-Speech — with smart parsing that skips boilerplate, detects ASCII diagrams, and lets you jump between sections like podcast chapters.

> **AI contributors**: Read [`Agent.md`](./Agent.md) before making any changes.

---

## Features

- 📚 Browse & search all 9,000+ IETF RFCs via the official Datatracker API
- 🔊 TTS playback using the browser-native Web Speech API (no API key needed)
- ⏭️ Section-based navigation — jump to any RFC section like a podcast timestamp
- 🖼️ ASCII diagram detection — visual figures are displayed in the UI, not garbled audio
- ⚡ Adjustable playback speed (0.5×–2×) and voice selection
- 💾 Resume where you left off (localStorage persistence)

---

## Tech Stack

| Layer     | Technology                         |
|-----------|------------------------------------|
| Frontend  | HTML5, Vanilla CSS, Vanilla JS     |
| Backend   | Python · FastAPI · httpx            |
| TTS       | Web Speech API (browser-native)    |
| RFC Data  | IETF Datatracker API + rfc-editor.org |

---

## Project Structure

```
RFCListen/
├── Agent.md              # AI coding assistant guide
├── PURPOSE.md            # Application purpose & goals
├── task.md               # Implementation progress tracker
├── README.md             # This file
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── backend/
│   ├── server.py         # FastAPI app entrypoint
│   ├── rfc_fetcher.py    # IETF API + RFC text fetching
│   ├── rfc_parser.py     # RFC text → structured JSON
│   ├── tts_service.py    # TTS abstraction layer
│   ├── requirements.txt
│   └── tests/
│       └── test_parser.py
└── scripts/              # Utility / one-off scripts
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- A modern browser (Chrome, Edge, Firefox) for Web Speech API support

### Backend Setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn server:app --reload --port 3000
```

Backend API will be available at `http://localhost:3000`.

### Frontend

Open `frontend/index.html` directly in your browser, or use a live-reload server:

```bash
# From the repo root
npx live-server frontend/
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in any optional values:

```bash
cp .env.example .env
```

---

## Contributing

See [`Agent.md`](./Agent.md) for coding conventions, architecture decisions, and the parser spec.
Track progress in [`task.md`](./task.md).

---

## References

- [IETF Datatracker API](https://datatracker.ietf.org/api/v1/?format=json)
- [RFC Editor](https://www.rfc-editor.org/)
- [Web Speech API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [RFC 7322 — RFC Style Guide](https://www.rfc-editor.org/rfc/rfc7322.txt)
