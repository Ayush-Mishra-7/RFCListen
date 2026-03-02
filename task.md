# RFCListen — Implementation Task Tracker

> **Last Updated**: 2026-03-01
> **Status Legend**: `[ ]` Not Started · `[/]` In Progress · `[x]` Completed

---

## Phase 0 — Project Bootstrap

- [x] Initialize Git repository and push to remote (GitHub/GitLab)
- [x] Create `README.md` with setup instructions and project overview
- [x] Set up monorepo structure: `frontend/`, `backend/`, `scripts/`
- [x] Create `.env.example` with all required environment variables
- [x] Add `.gitignore` (node_modules, __pycache__, .env, cache/)
- [x] Choose and document tech stack decision — **Python (FastAPI)** selected
- [x] Set up a basic `pyproject.toml` (optional; `requirements.txt` created)

---

## Phase 1 — Backend: RFC Data Layer

### 1.1 IETF Datatracker API Integration
- [x] Create `backend/rfc_fetcher.py`
- [x] Implement `getAllRFCs(page, limit)` — paginated list from IETF Datatracker API
- [x] Implement `getRFCMetadata(rfcNumber)` — fetch from Datatracker simplified JSON
- [x] Implement `getRFCText(rfcNumber)` — fetch plain text from rfc-editor.org
- [x] Add filesystem cache (`./cache/rfcXXXX.txt`) to avoid redundant fetches
- [x] Handle error cases: RFC not found (404), network timeout, malformed response

### 1.2 RFC Parser (`backend/rfc_parser.py`)
- [x] **Page break cleanup**: Strip repeated page headers/footers (`[Page N]`)
- [x] **Boilerplate stripping**:
  - [x] Detect and remove "Status of This Memo" section
  - [x] Detect and remove "Copyright Notice" section
  - [x] Detect and remove "Table of Contents" section
- [x] **Section detection**: Regex-match numbered section headings and record as named sections
- [x] **Paragraph normalization**: Join soft-wrapped lines; collapse multiple blank lines
- [x] **ASCII figure detection**: Density-based heuristic (box chars + drawing-char ratio)
  - [x] Replace with spoken announcement
  - [x] Preserve raw ASCII in `rawAscii` field
- [x] **Table detection**: Lines with multiple `|` separators
  - [x] Replace with spoken announcement
  - [x] Preserve raw table in `rawTable` field
- [x] **Output structured JSON** (rfcNumber, title, sections array)
- [x] Write unit tests for the parser (15 tests, all passing):
  - [x] Test page break stripping
  - [x] Test TOC removal
  - [x] Test ASCII diagram detection
  - [x] Test table detection
  - [x] Test paragraph join logic

### 1.3 Backend API Server (`backend/server.py`)
- [x] Create FastAPI server with CORS middleware
- [x] `GET /api/rfcs?page=1&limit=50&search=` — RFC list with search/filter
- [x] `GET /api/rfc/:number/metadata` — RFC metadata
- [x] `GET /api/rfc/:number/parsed` — Parsed RFC JSON
- [x] Add CORS headers for frontend dev server
- [x] `tts_service.py` — TTS abstraction layer (Cloud TTS hook ready)

---

## Phase 2 — Frontend: Core UI

### 2.1 Layout & Design System (`frontend/style.css`)
- [x] Define CSS custom properties (color palette, typography scale, spacing)
- [x] Dark mode as default (engineering aesthetic)
- [x] Responsive grid: sidebar (RFC browser) + main panel (reader + player)
- [x] Monospace font for RFC text rendering (`JetBrains Mono`)
- [x] Sans-serif font for UI chrome (`Inter`)

### 2.2 RFC Browser Panel
- [x] Fetch RFC list from backend API on load
- [x] Render paginated list with RFC number, title, status badge, and date
- [x] Search input with debounce — filters by number or title
- [x] Status filter dropdown
- [x] Click on RFC → load its parsed content into the reader panel

### 2.3 RFC Reader Panel
- [x] Display RFC title and metadata (badge, date)
- [x] Render sections sequentially with proper heading hierarchy
- [x] Scroll to currently playing section automatically
- [x] Highlight currently playing section with accent border
- [x] For `figure` sections: render raw ASCII art in styled `<pre>` monospace block
- [x] For `table` sections: render as `<pre>` block
- [x] Section navigation sidebar with clickable headings

### 2.4 TTS Audio Player (`frontend/app.js`)
- [x] Web Speech API `Player` class with play/pause/resume/stop/jumpToSection/setRate/setVoice
- [x] Player UI bar (fixed bottom):
  - [x] Play/Pause button
  - [x] Previous Section / Next Section buttons
  - [x] Playback speed selector (0.5×–2×)
  - [x] Voice selector (populated from `speechSynthesis.getVoices()`)
  - [x] Current RFC label + section label display
- [x] Section timestamps sidebar:
  - [x] All section headings listed (text, figure, table types styled differently)
  - [x] Active section highlighted
  - [x] Click to jump to section
- [x] Figure/table sections: speak announcement, display visual in reader

### 2.5 State Management (inline in `app.js`)
- [x] Single `state` object (rfcList, currentRFC, currentSectionIdx, isPlaying, playbackRate, selectedVoiceURI)
- [x] `setState()` / `saveToStorage()` / `loadFromStorage()` functions
- [x] Keyboard shortcuts: Space (play/pause), ArrowLeft/Right (skip section)

### 2.6 Bug Fixes (discovered during Phase 2)
- [x] **502 fix**: Switched RFC text source from rfc-editor.org (Cloudflare 403) to ietf.org/rfc/
- [x] **Title extraction**: Rewrote heuristic — centered-line detection, skips metadata/Obsoletes/prepared for
- [x] **Status labels**: Converted API URI slugs to human-readable labels (Proposed Standard, Informational, etc.)
- [x] **User-Agent**: Added proper UA and `follow_redirects=True` to all httpx clients

---

## Phase 3 — Persistence & UX Polish

- [x] Save `currentRFC` and `currentSectionIndex` to `localStorage` — resume on page reload
- [x] Recently played RFCs list (stored in localStorage, max 10 items with timestamps)
- [x] Keyboard shortcuts:
  - `Space` — Play/Pause
  - `←` / `→` — Previous/Next section
  - `↑` / `↓` — Speed up/down (with toast notification)
  - `M` — Stop playback
- [x] Loading skeleton UI while RFC list and content are being fetched
- [x] Toast notifications for success/error/info with slide-in animations
- [x] Section progress bar and counter in player bar (e.g. "3 / 125")
- [x] Accessible ARIA roles and labels on all interactive elements
- [x] English voices sorted first in voice selector
- [x] Responsive layout improvements (hide player options on small screens)

---

## Phase 4 — Testing & Validation

- [ ] Test parser against a set of diverse RFCs:
  - [ ] RFC 793 (TCP) — rich ASCII diagrams
  - [ ] RFC 2616 (HTTP/1.1) — tables and long sections
  - [ ] RFC 8446 (TLS 1.3) — modern, complex structure
  - [ ] RFC 1149 (IP over Avian Carriers) — short, humorous
- [ ] Manual end-to-end test: browse → select → listen → skip → figure announcement
- [ ] Cross-browser TTS test: Chrome, Firefox, Edge (Web Speech API support varies)
- [ ] Mobile browser test (Chrome on Android / Safari on iOS)
- [ ] Accessibility audit (keyboard nav, screen reader compatibility)

---

## Phase 5 — Deployment

- [ ] Create `Dockerfile` for backend (optional)
- [ ] Set up a simple static host for frontend (GitHub Pages, Vercel, or Netlify)
- [ ] Host backend on Railway, Fly.io, or Render (free tier)
- [ ] Update `README.md` with live demo URL
- [ ] Set up environment variable management for production
- [ ] Add `CONTRIBUTING.md` guide

---

## Stretch Goals (Post-MVP)

- [ ] **Cloud TTS integration**: Add Google Cloud TTS or AWS Polly as a higher-quality voice option (requires API key)
- [ ] **RFC Bookmarks / Playlists**: Save a list of RFCs to a personal playlist
- [ ] **Audio Export**: Download generated audio as an MP3 file (requires server-side TTS)
- [ ] **Section Notes**: Add text annotations to sections while listening
- [ ] **RFC Diff Viewer**: Compare two versions of an RFC (updated/obsoleted relationships)
- [ ] **PWA Support**: Make the app installable as a Progressive Web App with offline support

---

## Known Constraints & Decisions

| Decision | Rationale |
|----------|-----------|
| Web Speech API for MVP | Zero cost, no API key, works in all modern browsers |
| Fetch RFC text on demand (no pre-index) | 9,000+ RFCs — pre-processing all is infeasible for a pet project |
| Vanilla JS frontend | Simpler than a framework for this scale; avoids build step complexity |
| Plain text RFC source (`.txt`) | Most complete and consistently formatted; HTML/PDF vary widely |
| No user auth/accounts in MVP | Out of scope; localStorage sufficient for persistence |
