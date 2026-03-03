# Contributing to RFCListen

Thanks for considering contributing to RFCListen! This project is open source and we welcome contributions of all kinds — bug reports, feature improvements, documentation, and code.

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **A modern browser** (Chrome, Edge, or Firefox) with Web Speech API support
- **Git**

### Development Setup

```bash
# Clone the repo
git clone https://github.com/Ayush-Mishra-7/RFCListen.git
cd RFCListen

# Backend
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp ../.env.example ../.env    # Copy and edit environment variables
uvicorn server:app --reload --port 3000

# Frontend (in a separate terminal, from the repo root)
npx live-server frontend/
```

The backend runs at `http://localhost:3000` and the frontend at `http://127.0.0.1:8080`.

---

## Running Tests

```bash
cd backend

# Unit tests (parser logic)
.venv/Scripts/python -m pytest tests/test_parser.py -v

# Integration tests (requires backend running on port 3000)
.venv/Scripts/python -m pytest tests/test_parser_integration.py -v
```

---

## Code Style & Conventions

- **Backend**: Python with type hints. Follow PEP 8. Use `async`/`await` for all HTTP operations.
- **Frontend**: Vanilla JS (no frameworks). Use `'use strict'` mode. HTML entities should be escaped via `escHtml()`.
- **CSS**: Vanilla CSS with custom properties. Dark mode is the default theme.
- **Architecture**: Read [`Agent.md`](./Agent.md) for the full coding conventions and parser specification.

---

## Project Structure

```
frontend/         Vanilla HTML/CSS/JS — no build step
backend/          Python FastAPI — RFC fetching, parsing, and API
  ├── server.py         FastAPI entry point
  ├── rfc_fetcher.py    IETF API client with disk caching
  ├── rfc_parser.py     RFC text → structured JSON
  ├── tts_service.py    TTS abstraction (Cloud TTS ready)
  └── tests/            Unit + integration tests
scripts/          Utility scripts
```

---

## How to Contribute

1. **Fork** the repo and create a topic branch from `main`
2. **Make your changes** — keep commits focused and descriptive
3. **Run tests** and ensure they pass before submitting
4. **Open a Pull Request** with a clear description of what you changed and why

### Good First Issues

Look for issues tagged `good first issue` on the GitHub Issues page.

### Reporting Bugs

Open a GitHub Issue with:
- Steps to reproduce
- Expected vs. actual behavior
- Browser and OS version (for frontend/TTS issues)

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
