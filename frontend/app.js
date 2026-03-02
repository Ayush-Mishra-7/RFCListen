/**
 * app.js — RFCListen Frontend Application
 *
 * Architecture:
 *   state.js-style single state object + pure render functions
 *   player.js-style Player class wrapping Web Speech API
 *
 * Modules in this file (kept in one file for Phase 0 simplicity):
 *   1. Config
 *   2. State
 *   3. Player (Web Speech API wrapper)
 *   4. API client
 *   5. Render helpers
 *   6. Event wiring
 *   7. Init
 */

'use strict';

// ── 1. Config ─────────────────────────────────────────────────────────────────

const API_BASE = 'http://localhost:3000/api';
const STORAGE_KEY = 'rfclisten_state';

// ── 2. State ──────────────────────────────────────────────────────────────────

let state = {
  rfcList: [],
  totalCount: 0,
  page: 1,
  limit: 50,
  search: '',
  filterStatus: '',

  currentRFC: null,       // { rfcNumber, title, sections: [] }
  currentSectionIdx: 0,
  isPlaying: false,
  playbackRate: 1.0,
  selectedVoiceURI: '',
};

function setState(patch) {
  state = { ...state, ...patch };
  saveToStorage();
}

function saveToStorage() {
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

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    state = { ...state, ...saved };
  } catch (_) { /* ignore */ }
}

// ── 3. Player (Web Speech API) ────────────────────────────────────────────────

class Player {
  constructor() {
    this._utterance = null;
    this._sectionQueue = [];
    this._currentIdx = 0;
    this._onSectionChange = null;
  }

  /** Load sections and optionally start from a given index. */
  load(sections, startIdx = 0) {
    this.stop();
    this._sectionQueue = sections;
    this._currentIdx = startIdx;
  }

  play() {
    if (!this._sectionQueue.length) return;
    this._speakSection(this._currentIdx);
    setState({ isPlaying: true });
    renderPlayerState();
  }

  pause() {
    window.speechSynthesis.pause();
    setState({ isPlaying: false });
    renderPlayerState();
  }

  resume() {
    window.speechSynthesis.resume();
    setState({ isPlaying: true });
    renderPlayerState();
  }

  stop() {
    window.speechSynthesis.cancel();
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
    // Will apply on next utterance
  }

  setVoice(uri) {
    setState({ selectedVoiceURI: uri });
  }

  _speakSection(idx) {
    if (idx >= this._sectionQueue.length) {
      setState({ isPlaying: false });
      renderPlayerState();
      return;
    }

    const section = this._sectionQueue[idx];
    this._currentIdx = idx;
    setState({ currentSectionIdx: idx });
    renderActiveSectionHighlight(idx);
    scrollToSection(idx);

    const utterance = new SpeechSynthesisUtterance(section.content);
    utterance.rate = state.playbackRate;

    if (state.selectedVoiceURI) {
      const voices = window.speechSynthesis.getVoices();
      const voice = voices.find(v => v.voiceURI === state.selectedVoiceURI);
      if (voice) utterance.voice = voice;
    }

    utterance.onend = () => {
      this._speakSection(idx + 1);
    };

    utterance.onerror = (e) => {
      console.warn('TTS error:', e.error);
      this._speakSection(idx + 1);
    };

    this._utterance = utterance;
    window.speechSynthesis.speak(utterance);

    // Update player bar
    renderPlayerNowPlaying(section);
  }
}

const player = new Player();

// ── 4. API Client ─────────────────────────────────────────────────────────────

async function fetchRFCList(page = 1, limit = 50, search = '') {
  const params = new URLSearchParams({ page, limit, search });
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
      aria-label="RFC ${rfc.rfcNumber}: ${rfc.title}"
    >
      <span class="rfc-item-number">RFC ${rfc.rfcNumber}</span>
      <span class="rfc-item-title">${escHtml(rfc.title)}</span>
      <span class="rfc-item-meta">${rfc.status || ''} ${rfc.published ? '· ' + rfc.published.slice(0, 10) : ''}</span>
    </li>
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
        <div class="section-content">${escHtml(section.content)}</div>
      </div>`;
  }).join('');

  // Section nav
  renderSectionsNav(rfc.sections);

  // Player bar
  document.getElementById('player-bar').classList.remove('hidden');
}

function renderSectionsNav(sections) {
  const nav = document.getElementById('sections-nav');
  const list = document.getElementById('sections-list');
  nav.classList.remove('hidden');
  list.innerHTML = sections.map((s, idx) => `
    <li
      class="section-nav-item type-${s.type}"
      data-idx="${idx}"
      tabindex="0"
      role="button"
      aria-label="Jump to ${s.heading}"
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
}

function renderPlayerNowPlaying(section) {
  const rfc = state.currentRFC;
  document.getElementById('player-rfc-label').textContent =
    rfc ? `RFC ${rfc.rfcNumber}` : '';
  document.getElementById('player-section-label').textContent = section?.heading || '';
}

function scrollToSection(idx) {
  const el = document.getElementById(`section-${idx}`);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function populateVoices() {
  const select = document.getElementById('voice-select');
  const voices = window.speechSynthesis.getVoices();
  select.innerHTML = voices.map(v =>
    `<option value="${v.voiceURI}" ${state.selectedVoiceURI === v.voiceURI ? 'selected' : ''}>
      ${v.name} (${v.lang})
    </option>`
  ).join('');
}

function showToast(message, type = 'error') {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position:fixed;bottom:88px;right:20px;z-index:9999;
    background:${type === 'error' ? '#da3633' : '#238636'};
    color:#fff;padding:10px 18px;border-radius:8px;
    font-size:14px;box-shadow:0 4px 12px #0004;
    animation:fadeIn 0.2s ease;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escHtml(str = '') {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── 6. Event Wiring ───────────────────────────────────────────────────────────

function wireEvents() {
  // RFC list click
  document.getElementById('rfc-list').addEventListener('click', async (e) => {
    const item = e.target.closest('.rfc-list-item');
    if (!item) return;
    const rfcNum = Number(item.dataset.rfc);
    await loadRFC(rfcNum);
  });

  // Search (debounced)
  let searchTimer;
  document.getElementById('rfc-search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      setState({ search: e.target.value, page: 1 });
      loadRFCList();
    }, 350);
  });

  // Status filter
  document.getElementById('filter-status').addEventListener('change', (e) => {
    setState({ filterStatus: e.target.value, page: 1 });
    loadRFCList();
  });

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
    else if (window.speechSynthesis.paused) player.resume();
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

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.code === 'Space') { e.preventDefault(); document.getElementById('btn-play-pause').click(); }
    if (e.code === 'ArrowRight') player.nextSection();
    if (e.code === 'ArrowLeft') player.prevSection();
  });

  // Voices loaded async in some browsers
  window.speechSynthesis.onvoiceschanged = populateVoices;
}

// ── 7. Data loaders ───────────────────────────────────────────────────────────

async function loadRFCList() {
  const list = document.getElementById('rfc-list');
  list.innerHTML = '<li class="rfc-list-placeholder skeleton" style="height:40px;margin:4px 16px;"></li>'.repeat(8);

  try {
    const data = await fetchRFCList(state.page, state.limit, state.search);
    setState({ rfcList: data.rfcs, totalCount: data.count });
    renderRFCList(data.rfcs);

    // Pagination controls
    document.getElementById('page-info').textContent =
      `Page ${state.page} of ${Math.ceil(data.count / state.limit) || 1}`;
    document.getElementById('btn-prev-page').disabled = state.page <= 1;
    document.getElementById('btn-next-page').disabled =
      state.page >= Math.ceil(data.count / state.limit);
  } catch (err) {
    console.error(err);
    showToast('Could not load RFC list. Is the backend running?');
    list.innerHTML = '<li class="rfc-list-placeholder">Failed to load RFCs.</li>';
  }
}

async function loadRFC(rfcNumber) {
  player.stop();
  document.getElementById('rfc-content').innerHTML =
    '<div class="rfc-list-placeholder skeleton" style="height:32px;margin:16px 0;width:60%;"></div>'.repeat(12);

  try {
    const rfc = await fetchParsedRFC(rfcNumber);
    setState({ currentRFC: rfc, currentSectionIdx: 0 });
    renderRFCContent(rfc);

    player.load(rfc.sections, 0);
    renderPlayerNowPlaying(rfc.sections[0]);
    renderPlayerState();

    // Highlight selected item in list
    document.querySelectorAll('.rfc-list-item').forEach(el => {
      el.classList.toggle('active', Number(el.dataset.rfc) === rfcNumber);
    });
  } catch (err) {
    console.error(err);
    showToast(`Could not load RFC ${rfcNumber}.`);
  }
}

// ── 8. Init ───────────────────────────────────────────────────────────────────

async function init() {
  loadFromStorage();
  wireEvents();
  populateVoices();

  await loadRFCList();

  // Restore previous session
  if (state.currentRFC) {
    renderRFCContent(state.currentRFC);
    player.load(state.currentRFC.sections, state.currentSectionIdx);
    renderPlayerNowPlaying(state.currentRFC.sections[state.currentSectionIdx]);
    renderPlayerState();
  }

  // Restore speed selector
  document.getElementById('speed-select').value = String(state.playbackRate);
}

init();
