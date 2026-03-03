# 🎙️ RFCListen

A web application for Network Engineers to **listen to IETF RFCs** using Text-to-Speech — with smart parsing that skips boilerplate, detects ASCII diagrams, and lets you jump between sections like podcast chapters.

> **AI contributors**: Read [`Agent.md`](./Agent.md) before making any changes.

<!-- > 🌐 **Live Demo**: [rfclisten on GitHub Pages](https://ayush-mishra-7.github.io/RFCListen/) -->

---

## Features

- 📚 Browse & search all 9,000+ IETF RFCs via the official Datatracker API
- 🔊 TTS playback using the browser-native Web Speech API (no API key needed)
- ⏭️ Section-based navigation — jump to any RFC section like a podcast timestamp
- 🖼️ ASCII diagram detection — visual figures are displayed in the UI, not garbled audio
- ⚡ Adjustable playback speed (0.5×–2×) and voice selection
- 💾 Resume where you left off (localStorage persistence)
- ⌨️ Keyboard shortcuts (Space, arrows, M) for hands-free control
- ♿ Full accessibility support (ARIA labels, keyboard nav, screen reader compatible)

---

## Tech Stack

| Layer     | Technology                         |
|-----------|-------------------------------------|
| Frontend  | HTML5, Vanilla CSS, Vanilla JS     |
| Backend   | Python · FastAPI · httpx            |
| TTS       | Web Speech API (browser-native)    |
| RFC Data  | IETF Datatracker API + ietf.org    |
| Hosting   | GitHub Pages (frontend) + Render (backend) |

---

## Project Structure

```
RFCListen/
├── Agent.md              # AI coding assistant guide
├── PURPOSE.md            # Application purpose & goals
├── CONTRIBUTING.md       # Contribution guide
├── task.md               # Implementation progress tracker
├── render.yaml           # Render deployment blueprint
├── README.md             # This file
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── backend/
│   ├── Dockerfile        # Container image for deployment
│   ├── .dockerignore
│   ├── server.py         # FastAPI app entrypoint
│   ├── rfc_fetcher.py    # IETF API + RFC text fetching
│   ├── rfc_parser.py     # RFC text → structured JSON
│   ├── tts_service.py    # TTS abstraction layer
│   ├── requirements.txt
│   └── tests/
│       ├── test_parser.py              # Unit tests (15)
│       └── test_parser_integration.py  # Integration tests (30)
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

## Deployment

### Backend (Render)

The backend is containerized with Docker and configured for [Render](https://render.com):

1. Push your code to GitHub
2. Connect the repo on Render → select **Docker** runtime
3. Set the root directory to `backend/`
4. Configure environment variables in the Render dashboard:
   - `PORT=3000`
   - `RFC_CACHE_DIR=/app/cache`
   - `ALLOWED_ORIGINS=https://your-frontend-domain.com,http://localhost:8080`

Or use the included `render.yaml` for one-click Blueprint deploy.

### Frontend (GitHub Pages)

1. Go to your repo Settings → Pages
2. Set source to `main` branch, folder `/frontend`
3. Your site will be available at `https://your-username.github.io/RFCListen/`
4. Update `API_BASE` in `frontend/app.js` with your Render backend URL

### Local Docker Build

```bash
cd backend
docker build -t rfclisten-api .
docker run -p 3000:3000 -e ALLOWED_ORIGINS="http://localhost:8080" rfclisten-api
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in any optional values:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Backend server port | `3000` |
| `RFC_CACHE_DIR` | Directory for cached RFC texts | `./cache` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `http://localhost:8080` |
| `GOOGLE_TTS_API_KEY` | (Optional) Google Cloud TTS key | — |

---

## Testing

```bash
cd backend

# Unit tests — parser logic (15 tests)
python -m pytest tests/test_parser.py -v

# Integration tests — real RFC parsing via live API (30 tests)
python -m pytest tests/test_parser_integration.py -v
```

---

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for setup instructions, code style, and PR guidelines.
Track progress in [`task.md`](./task.md).

---

## References

- [IETF Datatracker API](https://datatracker.ietf.org/api/v1/?format=json)
- [RFC Editor](https://www.rfc-editor.org/)
- [Web Speech API — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [RFC 7322 — RFC Style Guide](https://www.rfc-editor.org/rfc/rfc7322.txt)
