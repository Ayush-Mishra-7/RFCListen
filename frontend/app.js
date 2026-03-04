/**
 * app.js — RFCListen Frontend Application
 *
 * Architecture:
 *   Single state object + pure render functions
 *   Player class wrapping Web Speech API
 *
 * Sections:
 *   1. Config
 *   2. State (with localStorage persistence + recently played)
 *   3. Player (Web Speech API wrapper)
 *   4. API client
 *   5. Render helpers
 *   6. Event wiring (including keyboard shortcuts)
 *   7. Data loaders
 *   8. Init
 */

'use strict';

// ── 1. Config ─────────────────────────────────────────────────────────────────

const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? 'http://localhost:3000/api'
  : 'https://rfclisten-api.onrender.com/api';
const RECENTS_KEY = 'rfclisten_recents';
const MAX_RECENTS = 10;

// ── 2. State ──────────────────────────────────────────────────────────────────

let state = {
  rfcList: [],
  totalCount: 0,
  page: 1,
  limit: 50,
  search: '',
  sortOrder: 'desc',

  currentRFC: null,       // { rfcNumber, title, sections: [] }
  currentSectionIdx: 0,
  isPlaying: false,
  playbackRate: 1.0,
  selectedVoiceURI: '',

  recentRFCs: [],         // [{ rfcNumber, title, lastPlayed: ISO string }]
};

function setState(patch) {
  state = { ...state, ...patch };
  _persistState();
}

function _persistState() {
  try {
    const persist = {
      currentRFC: state.currentRFC,
      currentSectionIdx: state.currentSectionIdx,
      playbackRate: state.playbackRate,
      selectedVoiceURI: state.selectedVoiceURI,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persist));
  } catch (_) { /* ignore */ }
}

function _persistRecents() {
  try {
    localStorage.setItem(RECENTS_KEY, JSON.stringify(state.recentRFCs));
  } catch (_) { /* ignore */ }
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      state = { ...state, ...saved };
    }
    const recentsRaw = localStorage.getItem(RECENTS_KEY);
    if (recentsRaw) {
      state.recentRFCs = JSON.parse(recentsRaw);
    }
  } catch (_) { /* ignore */ }
}

function addToRecents(rfcNumber, title) {
  // Remove if already exists
  state.recentRFCs = state.recentRFCs.filter(r => r.rfcNumber !== rfcNumber);
  // Push to front
  state.recentRFCs.unshift({
    rfcNumber,
    title,
    lastPlayed: new Date().toISOString(),
  });
  // Cap at MAX_RECENTS
  if (state.recentRFCs.length > MAX_RECENTS) {
    state.recentRFCs = state.recentRFCs.slice(0, MAX_RECENTS);
  }
  _persistRecents();
}

// ── 3. Player (Web Speech API) ────────────────────────────────────────────────

class Player {
  constructor() {
    this._utterance = null;
    this._sectionQueue = [];
    this._currentIdx = 0;
    this._pauseCharIdx = 0;   // char offset where we paused
    this._charOffset = 0;     // offset added to boundary events for resumed utterances
    this._isPaused = false;   // true when paused (so resume knows to continue)
    this._lastBoundaryChar = 0; // last char index from boundary event
  }

  /** Load sections and optionally start from a given index. */
  load(sections, startIdx = 0) {
    this.stop();
    this._sectionQueue = sections;
    this._currentIdx = startIdx;
    this._pauseCharIdx = 0;
    this._charOffset = 0;
    this._isPaused = false;
  }

  play() {
    if (!this._sectionQueue.length) return;
    this._isPaused = false;
    this._pauseCharIdx = 0;
    this._charOffset = 0;
    this._speakSection(this._currentIdx);
    setState({ isPlaying: true });
    renderPlayerState();
  }

  pause() {
    // Save the last known char position before cancelling.
    // _lastBoundaryChar tracks the absolute char index (including _charOffset).
    this._pauseCharIdx = this._lastBoundaryChar || 0;
    this._isPaused = true;
    window.speechSynthesis.cancel();
    setState({ isPlaying: false });
    renderPlayerState();
    // Leave word highlights in place so user can see where we stopped
  }

  resume() {
    if (!this._isPaused) { this.play(); return; }
    this._isPaused = false;
    const section = this._sectionQueue[this._currentIdx];
    if (!section) return;

    // Speak from where we left off
    const remainingText = section.content.substring(this._pauseCharIdx);
    if (!remainingText.trim()) {
      // Nothing left in this section, advance to next
      this._pauseCharIdx = 0;
      this._charOffset = 0;
      this._speakSection(this._currentIdx + 1);
      return;
    }

    this._charOffset = this._pauseCharIdx;
    this._speakText(remainingText, this._currentIdx);
    setState({ isPlaying: true });
    renderPlayerState();
  }

  stop() {
    window.speechSynthesis.cancel();
    this._isPaused = false;
    this._pauseCharIdx = 0;
    this._charOffset = 0;
    this._lastBoundaryChar = 0;
    clearWordHighlights();
    setState({ isPlaying: false });
  }

  nextSection() {
    if (this._currentIdx < this._sectionQueue.length - 1) {
      this.stop();
      this._currentIdx++;
      setState({ currentSectionIdx: this._currentIdx });
      this.play();
    }
  }

  prevSection() {
    if (this._currentIdx > 0) {
      this.stop();
      this._currentIdx--;
      setState({ currentSectionIdx: this._currentIdx });
      this.play();
    }
  }

  jumpToSection(idx) {
    this.stop();
    this._currentIdx = idx;
    setState({ currentSectionIdx: idx });
    this.play();
  }

  setRate(rate) {
    setState({ playbackRate: rate });
    document.getElementById('speed-select').value = String(rate);
  }

  setVoice(uri) {
    setState({ selectedVoiceURI: uri });
  }

  get currentIdx() { return this._currentIdx; }
  get totalSections() { return this._sectionQueue.length; }
  get isPaused() { return this._isPaused; }

  _speakSection(idx, startChar = 0) {
    if (idx >= this._sectionQueue.length) {
      clearWordHighlights();
      setState({ isPlaying: false });
      renderPlayerState();
      showToast('Finished reading this RFC.', 'success');
      return;
    }

    const section = this._sectionQueue[idx];
    this._currentIdx = idx;
    this._pauseCharIdx = 0;
    this._charOffset = startChar;
    this._lastBoundaryChar = startChar;
    setState({ currentSectionIdx: idx });
    renderActiveSectionHighlight(idx);
    scrollToSection(idx);
    renderSectionProgress();

    // Show/hide the figure card overlay based on section type
    if (section.type === 'figure' || section.type === 'table') {
      showFigureCard(section);
    } else {
      hideFigureCard();
    }

    const textToSpeak = startChar > 0 ? section.content.substring(startChar) : section.content;
    this._speakText(textToSpeak, idx);

    // Update player bar
    renderPlayerNowPlaying(section);
  }

  /** Internal: create an utterance, wire events, and speak. */
  _speakText(text, sectionIdx) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = state.playbackRate;

    if (state.selectedVoiceURI) {
      const voices = window.speechSynthesis.getVoices();
      const voice = voices.find(v => v.voiceURI === state.selectedVoiceURI);
      if (voice) utterance.voice = voice;
    }

    // ── Word-level highlighting via boundary events ──
    utterance.onboundary = (e) => {
      if (e.name !== 'word') return;
      const absChar = e.charIndex + this._charOffset;
      this._lastBoundaryChar = absChar;
      highlightWordAt(this._currentIdx, absChar, e.charLength);
    };

    utterance.onend = () => {
      clearWordHighlights();
      this._speakSection(sectionIdx + 1);
    };

    utterance.onerror = (e) => {
      if (e.error !== 'interrupted') {
        console.warn('TTS error:', e.error);
      }
      if (e.error !== 'interrupted' && e.error !== 'canceled') {
        clearWordHighlights();
        this._speakSection(sectionIdx + 1);
      }
    };

    this._utterance = utterance;
    window.speechSynthesis.speak(utterance);
  }
}

const player = new Player();

// ── 4. API Client ─────────────────────────────────────────────────────────────

async function fetchRFCList(page = 1, limit = 50, search = '', sort = 'desc') {
  const params = new URLSearchParams({ page, limit, search, sort });
  const res = await fetch(`${API_BASE}/rfcs?${params}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

async function fetchParsedRFC(rfcNumber) {
  const res = await fetch(`${API_BASE}/rfc/${rfcNumber}/parsed`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

// ── 5. Render Helpers ─────────────────────────────────────────────────────────

function renderRFCList(rfcs) {
  const list = document.getElementById('rfc-list');
  if (!rfcs.length) {
    list.innerHTML = '<li class="rfc-list-placeholder">No RFCs found.</li>';
    return;
  }
  list.innerHTML = rfcs.map(rfc => `
    <li
      class="rfc-list-item ${state.currentRFC?.rfcNumber === rfc.rfcNumber ? 'active' : ''}"
      role="option"
      data-rfc="${rfc.rfcNumber}"
      tabindex="0"
      aria-label="RFC ${rfc.rfcNumber}: ${escHtml(rfc.title)}"
    >
      <span class="rfc-item-number">RFC ${rfc.rfcNumber}</span>
      <span class="rfc-item-title">${escHtml(rfc.title)}</span>
      <span class="rfc-item-meta">${escHtml(rfc.status || '')} ${rfc.published ? '· ' + rfc.published.slice(0, 10) : ''}</span>
    </li>
  `).join('');
}

function renderRecentsList() {
  const container = document.getElementById('recents-list');
  if (!container) return;

  if (!state.recentRFCs.length) {
    container.innerHTML = '<div class="recents-empty">No recently played RFCs</div>';
    return;
  }

  container.innerHTML = state.recentRFCs.map(r => `
    <div class="recent-item" data-rfc="${r.rfcNumber}" tabindex="0" role="button"
         aria-label="Resume RFC ${r.rfcNumber}: ${escHtml(r.title)}">
      <span class="recent-number">RFC ${r.rfcNumber}</span>
      <span class="recent-title">${escHtml(r.title)}</span>
      <span class="recent-time">${_timeAgo(r.lastPlayed)}</span>
    </div>
  `).join('');
}

function renderRFCContent(rfc) {
  // Header
  document.getElementById('rfc-header').classList.remove('hidden');
  document.getElementById('rfc-badge').textContent = `RFC ${rfc.rfcNumber}`;
  document.getElementById('rfc-title').textContent = rfc.title;

  // Content
  const content = document.getElementById('rfc-content');
  content.innerHTML = rfc.sections.map((section, idx) => {
    if (section.type === 'figure') {
      return `
        <div class="section-block figure-block" id="section-${idx}" data-idx="${idx}">
          <div class="figure-label">📊 ${escHtml(section.heading)}</div>
          <pre class="figure-pre">${escHtml(section.rawAscii)}</pre>
          <div class="figure-announcement">${escHtml(section.content)}</div>
        </div>`;
    }
    if (section.type === 'table') {
      return `
        <div class="section-block table-block" id="section-${idx}" data-idx="${idx}">
          <div class="table-label">📋 ${escHtml(section.heading)}</div>
          <pre class="table-pre">${escHtml(section.rawTable)}</pre>
          <div class="table-announcement">${escHtml(section.content)}</div>
        </div>`;
    }
    return `
      <div class="section-block" id="section-${idx}" data-idx="${idx}">
        <h3 class="section-heading">${escHtml(section.heading)}</h3>
        <div class="section-content">${wrapWordsForTTS(section.content)}</div>
      </div>`;
  }).join('');

  // Section nav
  renderSectionsNav(rfc.sections);

  // Player bar — enable controls now that an RFC is loaded
  document.getElementById('player-bar').classList.remove('player-bar--disabled');
}

function renderSectionsNav(sections) {
  const nav = document.getElementById('sections-nav');
  const list = document.getElementById('sections-list');
  nav.classList.remove('hidden');
  // Only show text sections, and deduplicate by heading (parser may split
  // a single section around figures, producing multiple entries with the
  // same heading — we only show the first occurrence).
  const seen = new Set();
  list.innerHTML = sections
    .map((s, idx) => ({ s, idx }))
    .filter(({ s }) => s.type === 'text')
    .filter(({ s }) => {
      if (seen.has(s.heading)) return false;
      seen.add(s.heading);
      return true;
    })
    .map(({ s, idx }) => `
    <li
      class="section-nav-item"
      data-idx="${idx}"
      tabindex="0"
      role="button"
      aria-label="Jump to ${escHtml(s.heading)}"
    >${escHtml(s.heading)}</li>
  `).join('');
}

function renderActiveSectionHighlight(idx) {
  document.querySelectorAll('.section-block').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.section-nav-item').forEach(el => el.classList.remove('active'));

  const block = document.getElementById(`section-${idx}`);
  if (block) block.classList.add('active');

  const navItem = document.querySelector(`.section-nav-item[data-idx="${idx}"]`);
  if (navItem) {
    navItem.classList.add('active');
    navItem.scrollIntoView({ block: 'nearest' });
  }
}

function renderPlayerState() {
  const btn = document.getElementById('btn-play-pause');
  btn.textContent = state.isPlaying ? '⏸' : '▶';
  btn.setAttribute('aria-label', state.isPlaying ? 'Pause' : 'Play');
  btn.setAttribute('title', state.isPlaying ? 'Pause (Space)' : 'Play (Space)');
}

function renderPlayerNowPlaying(section) {
  const rfc = state.currentRFC;
  const rfcLabel = document.getElementById('player-rfc-label');
  const sectionLabel = document.getElementById('player-section-label');

  if (!rfc) {
    rfcLabel.textContent = '';
    // Show a hint in the section label when no RFC is loaded
    sectionLabel.innerHTML = '<span class="player-bar--no-rfc-hint">Select an RFC to start listening</span>';
    return;
  }

  rfcLabel.textContent = `RFC ${rfc.rfcNumber}`;
  sectionLabel.textContent = section?.heading || '';
}

function renderSectionProgress() {
  const progressEl = document.getElementById('section-progress');
  if (!progressEl) return;
  const total = player.totalSections;
  const current = player.currentIdx + 1;
  progressEl.textContent = total ? `${current} / ${total}` : '';

  // Update progress bar
  const bar = document.getElementById('progress-fill');
  if (bar && total) {
    bar.style.width = `${(current / total) * 100}%`;
  }
}

function scrollToSection(idx) {
  const el = document.getElementById(`section-${idx}`);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function populateVoices() {
  const select = document.getElementById('voice-select');
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return;

  // Group by language, prefer English voices
  const english = voices.filter(v => v.lang.startsWith('en'));
  const others = voices.filter(v => !v.lang.startsWith('en'));
  const sorted = [...english, ...others];

  select.innerHTML = sorted.map(v =>
    `<option value="${v.voiceURI}" ${state.selectedVoiceURI === v.voiceURI ? 'selected' : ''}>
      ${v.name} (${v.lang})
    </option>`
  ).join('');
}

// ── Toasts ────────────────────────────────────────────────────────────────────

function showToast(message, type = 'error') {
  // Remove any existing toasts
  document.querySelectorAll('.toast').forEach(t => t.remove());

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', 'alert');
  toast.setAttribute('aria-live', 'assertive');
  toast.textContent = message;
  document.body.appendChild(toast);

  // Trigger entrance animation on next frame
  requestAnimationFrame(() => toast.classList.add('toast-visible'));

  setTimeout(() => {
    toast.classList.remove('toast-visible');
    toast.addEventListener('transitionend', () => toast.remove());
  }, 3500);
}

// ── Figure Card Overlay ───────────────────────────────────────────────────────

function showFigureCard(section) {
  // Remove any existing card
  hideFigureCard(true);

  const isFigure = section.type === 'figure';
  const icon = isFigure ? '📊' : '📋';
  const ascii = isFigure ? (section.rawAscii || '') : (section.rawTable || '');

  const card = document.createElement('div');
  card.className = 'figure-card-overlay';
  card.id = 'figure-card';
  card.setAttribute('role', 'complementary');
  card.setAttribute('aria-label', section.heading);

  card.innerHTML = `
    <div class="figure-card-header">
      <span class="figure-card-label">${icon} ${escHtml(section.heading)}</span>
      <button class="figure-card-close" aria-label="Close figure" title="Close">&times;</button>
    </div>
    <div class="figure-card-body">
      <pre class="figure-card-pre">${escHtml(ascii)}</pre>
      ${section.content ? `<div class="figure-card-announcement">${escHtml(section.content)}</div>` : ''}
    </div>
  `;

  document.body.appendChild(card);

  // Wire close button
  card.querySelector('.figure-card-close').addEventListener('click', () => hideFigureCard());

  // Trigger entrance animation on next frame
  requestAnimationFrame(() => card.classList.add('figure-card--visible'));
}

function hideFigureCard(instant = false) {
  const card = document.getElementById('figure-card');
  if (!card) return;

  if (instant) {
    card.remove();
    return;
  }

  card.classList.remove('figure-card--visible');
  card.classList.add('figure-card--exiting');
  card.addEventListener('transitionend', () => card.remove(), { once: true });
  // Safety fallback in case transitionend doesn't fire
  setTimeout(() => { if (card.parentNode) card.remove(); }, 500);
}

// ── Skeleton loaders ──────────────────────────────────────────────────────────

function showListSkeleton() {
  const list = document.getElementById('rfc-list');
  list.innerHTML = Array.from({ length: 8 }, (_, i) => `
    <li class="rfc-list-item skeleton-item" aria-hidden="true">
      <span class="skeleton skeleton-number"></span>
      <span class="skeleton skeleton-title" style="width:${60 + Math.random() * 35}%"></span>
      <span class="skeleton skeleton-meta" style="width:${30 + Math.random() * 30}%"></span>
    </li>
  `).join('');
}

function showContentSkeleton() {
  document.getElementById('rfc-content').innerHTML = `
    <div class="content-skeleton" aria-hidden="true">
      ${Array.from({ length: 6 }, () => `
        <div class="skeleton-section">
          <div class="skeleton skeleton-heading" style="width:${25 + Math.random() * 30}%"></div>
          <div class="skeleton skeleton-line" style="width:${70 + Math.random() * 25}%"></div>
          <div class="skeleton skeleton-line" style="width:${60 + Math.random() * 35}%"></div>
          <div class="skeleton skeleton-line" style="width:${50 + Math.random() * 40}%"></div>
          <div class="skeleton skeleton-line" style="width:${65 + Math.random() * 30}%"></div>
        </div>
      `).join('')}
    </div>
  `;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(str = '') {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Wrap each word in the given text with a <span class="tts-word" data-char="N">
 * so the onboundary handler can highlight words by charIndex.
 * Whitespace (spaces, newlines) is preserved as plain text between spans.
 */
function wrapWordsForTTS(text) {
  if (!text) return '';
  // Split into tokens: alternating (whitespace, word) while tracking char position
  const result = [];
  const regex = /(\S+)/g;
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    // Emit any whitespace before this word
    if (match.index > lastIndex) {
      result.push(escHtml(text.substring(lastIndex, match.index)));
    }
    // Emit the word wrapped in a span
    result.push(
      `<span class="tts-word" data-char="${match.index}">${escHtml(match[0])}</span>`
    );
    lastIndex = regex.lastIndex;
  }
  // Trailing whitespace
  if (lastIndex < text.length) {
    result.push(escHtml(text.substring(lastIndex)));
  }
  return result.join('');
}

/**
 * Highlight the word at the given char index in the active section.
 * Marks all prior words as "spoken" (dimmed) and the current word as "active".
 */
function highlightWordAt(sectionIdx, charIdx, charLen) {
  const block = document.getElementById(`section-${sectionIdx}`);
  if (!block) return;

  const words = block.querySelectorAll('.tts-word');
  let found = false;

  for (const span of words) {
    const spanChar = parseInt(span.dataset.char, 10);
    if (spanChar === charIdx) {
      // This is the active word
      span.classList.add('tts-word--active');
      span.classList.remove('tts-word--spoken');
      found = true;
      // Scroll the word into view if needed (within the scrollable content area)
      span.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } else if (spanChar < charIdx) {
      // Already spoken
      span.classList.remove('tts-word--active');
      span.classList.add('tts-word--spoken');
    } else {
      // Not yet spoken
      span.classList.remove('tts-word--active');
      span.classList.remove('tts-word--spoken');
    }
  }
}

/** Remove all word highlights across all sections. */
function clearWordHighlights() {
  document.querySelectorAll('.tts-word--active').forEach(el => el.classList.remove('tts-word--active'));
  document.querySelectorAll('.tts-word--spoken').forEach(el => el.classList.remove('tts-word--spoken'));
}

function _timeAgo(isoStr) {
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ── 6. Event Wiring ───────────────────────────────────────────────────────────

function wireEvents() {
  // RFC list click
  document.getElementById('rfc-list').addEventListener('click', async (e) => {
    const item = e.target.closest('.rfc-list-item');
    if (!item || item.classList.contains('skeleton-item')) return;
    const rfcNum = Number(item.dataset.rfc);
    await loadRFC(rfcNum);
  });

  // RFC list keyboard navigation (Enter to select)
  document.getElementById('rfc-list').addEventListener('keydown', async (e) => {
    if (e.code === 'Enter') {
      const item = e.target.closest('.rfc-list-item');
      if (item) await loadRFC(Number(item.dataset.rfc));
    }
  });

  // Recently played clicks
  const recents = document.getElementById('recents-list');
  if (recents) {
    recents.addEventListener('click', async (e) => {
      const item = e.target.closest('.recent-item');
      if (!item) return;
      await loadRFC(Number(item.dataset.rfc));
    });
  }

  // Search (debounced)
  let searchTimer;
  document.getElementById('rfc-search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      setState({ search: e.target.value, page: 1 });
      loadRFCList();
    }, 350);
  });

  // Sort dropdown
  const sortSelect = document.getElementById('sort-order');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      setState({ sortOrder: e.target.value, page: 1 });
      loadRFCList();
    });
  }

  // Pagination
  document.getElementById('btn-prev-page').addEventListener('click', () => {
    if (state.page > 1) { setState({ page: state.page - 1 }); loadRFCList(); }
  });
  document.getElementById('btn-next-page').addEventListener('click', () => {
    setState({ page: state.page + 1 });
    loadRFCList();
  });

  // Player controls
  document.getElementById('btn-play-pause').addEventListener('click', () => {
    if (!state.currentRFC) return;
    if (state.isPlaying) player.pause();
    else if (player.isPaused) player.resume();
    else player.play();
  });

  document.getElementById('btn-prev-section').addEventListener('click', () => player.prevSection());
  document.getElementById('btn-next-section').addEventListener('click', () => player.nextSection());

  // Speed
  document.getElementById('speed-select').addEventListener('change', (e) => {
    player.setRate(Number(e.target.value));
  });

  // Voice
  document.getElementById('voice-select').addEventListener('change', (e) => {
    player.setVoice(e.target.value);
  });

  // Section nav clicks
  document.getElementById('sections-list').addEventListener('click', (e) => {
    const item = e.target.closest('.section-nav-item');
    if (!item) return;
    const idx = Number(item.dataset.idx);
    player.jumpToSection(idx);
  });

  // Section nav keyboard
  document.getElementById('sections-list').addEventListener('keydown', (e) => {
    if (e.code === 'Enter') {
      const item = e.target.closest('.section-nav-item');
      if (item) player.jumpToSection(Number(item.dataset.idx));
    }
  });

  // ── Keyboard shortcuts ──────────────────────────────────────────────────────
  document.addEventListener('keydown', (e) => {
    // Skip when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.code) {
      case 'Space':
        e.preventDefault();
        document.getElementById('btn-play-pause').click();
        break;
      case 'ArrowRight':
        e.preventDefault();
        player.nextSection();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        player.prevSection();
        break;
      case 'ArrowUp': {
        e.preventDefault();
        const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2];
        const curIdx = speeds.indexOf(state.playbackRate);
        if (curIdx < speeds.length - 1) {
          player.setRate(speeds[curIdx + 1]);
          showToast(`Speed: ${speeds[curIdx + 1]}×`, 'info');
        }
        break;
      }
      case 'ArrowDown': {
        e.preventDefault();
        const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2];
        const curIdx = speeds.indexOf(state.playbackRate);
        if (curIdx > 0) {
          player.setRate(speeds[curIdx - 1]);
          showToast(`Speed: ${speeds[curIdx - 1]}×`, 'info');
        }
        break;
      }
      case 'KeyM':
        // Mute / unmute (stop / play)
        if (state.isPlaying) { player.stop(); showToast('Stopped', 'info'); }
        break;
    }
  });

  // Voices loaded async in some browsers
  window.speechSynthesis.onvoiceschanged = populateVoices;
}

// ── 7. Data loaders ───────────────────────────────────────────────────────────

async function loadRFCList() {
  showListSkeleton();

  // Flag to track if we've rendered something from cache/static file
  let hasRenderedStatic = false;

  try {
    // HYBRID LOADING: If we are on the first page, with no search, and default sort, try to load the static JSON instantly
    if (state.page === 1 && !state.search && state.sortOrder === 'desc') {
      try {
        const staticRes = await fetch('./top-rfcs.json');
        if (staticRes.ok) {
          const staticData = await staticRes.json();
          setState({ rfcList: staticData.rfcs, totalCount: staticData.count });
          renderRFCList(staticData.rfcs);

          const totalPages = Math.ceil(staticData.count / state.limit) || 1;
          document.getElementById('page-info').textContent = `Page ${state.page} of ${totalPages}`;
          document.getElementById('btn-prev-page').disabled = state.page <= 1;
          document.getElementById('btn-next-page').disabled = state.page >= totalPages;

          hasRenderedStatic = true;
        }
      } catch (staticErr) {
        console.warn('Failed to load static top-rfcs.json, falling back to API only', staticErr);
      }
    }

    // Always fetch live data from the backend in the background (Stale-While-Revalidate)
    const data = await fetchRFCList(state.page, state.limit, state.search, state.sortOrder);

    // Only update and re-render if the state has actually changed, or if we haven't rendered anything yet
    // For simplicity, we just safely re-render with the fresh data
    setState({ rfcList: data.rfcs, totalCount: data.count });
    renderRFCList(data.rfcs);

    // Pagination controls update
    const totalPages = Math.ceil(data.count / state.limit) || 1;
    document.getElementById('page-info').textContent = `Page ${state.page} of ${totalPages}`;
    document.getElementById('btn-prev-page').disabled = state.page <= 1;
    document.getElementById('btn-next-page').disabled = state.page >= totalPages;

  } catch (err) {
    console.error(err);
    if (!hasRenderedStatic) {
      // Only show error visually if we didn't already successfully render the static fallback
      showToast('Could not load target RFC list. Is the backend running?');
      document.getElementById('rfc-list').innerHTML =
        '<li class="rfc-list-placeholder">Failed to load RFCs. Check if the backend is running on port 3000.</li>';
    } else {
      // If we had static data, just silently fail the background update or show a tiny warning
      console.warn("Background revalidation failed, using static data.");
    }
  }
}

async function loadRFC(rfcNumber) {
  player.stop();
  showContentSkeleton();

  // Show header immediately with loading state
  document.getElementById('rfc-header').classList.remove('hidden');
  document.getElementById('rfc-badge').textContent = `RFC ${rfcNumber}`;
  document.getElementById('rfc-title').textContent = 'Loading…';

  try {
    const rfc = await fetchParsedRFC(rfcNumber);
    setState({ currentRFC: rfc, currentSectionIdx: 0 });
    renderRFCContent(rfc);

    player.load(rfc.sections, 0);
    renderPlayerNowPlaying(rfc.sections[0]);
    renderPlayerState();
    renderSectionProgress();

    // Add to recently played
    addToRecents(rfcNumber, rfc.title);
    renderRecentsList();

    // Highlight selected item in left list
    document.querySelectorAll('.rfc-list-item').forEach(el => {
      el.classList.toggle('active', Number(el.dataset.rfc) === rfcNumber);
    });

    showToast(`Loaded RFC ${rfcNumber}: ${rfc.title}`, 'success');
  } catch (err) {
    console.error(err);
    showToast(`Could not load RFC ${rfcNumber}. It may not exist or the backend timed out.`);
    document.getElementById('rfc-content').innerHTML =
      '<div id="welcome-screen"><div class="welcome-icon">⚠️</div><h2>Failed to load RFC</h2><p>Please try another RFC or check the backend.</p></div>';
  }
}

// ── 8. Init ───────────────────────────────────────────────────────────────────

async function init() {
  loadFromStorage();
  wireEvents();
  populateVoices();

  // Show placeholder in the player bar immediately if no RFC is in session
  if (!state.currentRFC) {
    renderPlayerNowPlaying(null);
  }

  // Render recently played
  renderRecentsList();

  await loadRFCList();

  // Restore previous session
  if (state.currentRFC) {
    renderRFCContent(state.currentRFC);
    player.load(state.currentRFC.sections, state.currentSectionIdx);
    renderPlayerNowPlaying(state.currentRFC.sections[state.currentSectionIdx] || state.currentRFC.sections[0]);
    renderPlayerState();
    renderSectionProgress();
    renderActiveSectionHighlight(state.currentSectionIdx);
  }

  // Restore speed selector
  document.getElementById('speed-select').value = String(state.playbackRate);
}

init();
