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
const STORAGE_KEY = 'rfclisten_state';
const RECENTS_KEY = 'rfclisten_recents';
const MAX_RECENTS = 5;
const DEFAULT_EDGE_VOICE_ID = 'en-US-BrianMultilingualNeural';

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
  ttsEngine: 'edge',      // 'edge' or 'browser'
  rfcVoiceLocks: {},      // { [rfcNumber]: { voiceURI: string, ttsEngine: 'edge' | 'browser' } }

  edgeVoices: [],         // array of { id, name }
  browserVoices: [],      // array of browser voice objects

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
      ttsEngine: state.ttsEngine || 'edge',
      rfcVoiceLocks: state.rfcVoiceLocks || {},
      sortOrder: state.sortOrder || 'desc',
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
      // Trim to current MAX_RECENTS (may have been larger before)
      if (state.recentRFCs.length > MAX_RECENTS) {
        state.recentRFCs = state.recentRFCs.slice(0, MAX_RECENTS);
        _persistRecents();
      }
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

    // Word boundary data from Edge TTS (populated per-section)
    this._wordBoundaries = [];  // [{text, offset (ms), duration (ms), charIdx}, ...]

    this._audio = new Audio();
    this._playbackToken = 0;
    this._hasLoadedEdgeAudio = false;
    this._syncDiagnostics = {
      mode: 'none',
      sectionIdx: -1,
      boundariesCount: 0,
      matchRate: 0,
      notFoundCount: 0,
      rejectedCount: 0,
    };
    this._audio.addEventListener('ended', () => this._onAudioEnded());
    this._audio.addEventListener('error', (e) => this._onAudioError(e));
    this._audio.addEventListener('timeupdate', () => this._onAudioTimeUpdate());
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

    lockVoiceForCurrentRFCIfNeeded();
    syncVoiceSelectionForCurrentRFC();

    const canResumeEdge =
      state.ttsEngine === 'edge' &&
      this._isPaused &&
      this._hasLoadedEdgeAudio &&
      !!this._audio.currentSrc;

    this._isPaused = false;

    if (canResumeEdge) {
      this._audio.playbackRate = state.playbackRate;
      this._audio.play().catch(e => {
        console.error("Audio play failed", e);
        this._pauseCharIdx = 0;
        this._charOffset = 0;
        this._speakSection(this._currentIdx);
      });
    } else {
      this._pauseCharIdx = 0;
      this._charOffset = 0;
      this._speakSection(this._currentIdx);
    }

    setState({ isPlaying: true });
    renderPlayerState();
  }

  pause() {
    this._isPaused = true;
    if (state.ttsEngine === 'edge') {
      this._audio.pause();
    } else {
      window.speechSynthesis.pause();
      // Browser TTS pause() is unreliable — retry until it actually pauses
      let retries = 0;
      const retryPause = setInterval(() => {
        retries++;
        if (!window.speechSynthesis.speaking || window.speechSynthesis.paused || retries >= 10) {
          clearInterval(retryPause);
          return;
        }
        window.speechSynthesis.pause();
      }, 50);
    }
    setState({ isPlaying: false });
    renderPlayerState();
    // Leave word highlights in place so user can see where we stopped
  }

  resume() {
    if (!this._isPaused) { this.play(); return; }

    if (state.ttsEngine === 'edge') {
      this._isPaused = false;
      if (!this._hasLoadedEdgeAudio || !this._audio.currentSrc) {
        this._pauseCharIdx = 0;
        this._charOffset = 0;
        this._speakSection(this._currentIdx);
        setState({ isPlaying: true });
        renderPlayerState();
        return;
      }
      this._audio.playbackRate = state.playbackRate;
      this._audio.play().catch(console.error);
      setState({ isPlaying: true });
      renderPlayerState();
      return;
    }

    this._isPaused = false;

    // Attempt native resume
    window.speechSynthesis.resume();
    setState({ isPlaying: true });
    renderPlayerState();

    // Browser bug workaround: Sometimes Chrome/Safari get permanently stuck on pause
    // If we don't receive a boundary event within 1.5 seconds of resuming, fall back
    // to the cancel + respeak strategy.
    clearTimeout(this._resumeTimeout);
    this._resumeTimeout = setTimeout(() => {
      console.warn("TTS engine failed to resume natively. Falling back to cancel+respeak.");
      this._cancelAndRespeakFromLastBoundary();
    }, 1500);
  }

  _cancelAndRespeakFromLastBoundary() {
    window.speechSynthesis.cancel();

    const section = this._sectionQueue[this._currentIdx];
    if (!section) return;

    // Advance _lastBoundaryChar slightly to avoid repeating too much of the last spoken word
    // We assume an average word length of 6 characters
    this._pauseCharIdx = (this._lastBoundaryChar || 0) + 6;

    const remainingText = section.content.substring(this._pauseCharIdx);
    if (!remainingText.trim()) {
      // Nothing left in this section, advance to next
      this._pauseCharIdx = 0;
      this._charOffset = 0;
      this._speakSection(this._currentIdx + 1);
      return;
    }

    this._charOffset = this._pauseCharIdx;
    const maskedText = this._maskInlineReferences(remainingText);
    this._speakText(maskedText, this._currentIdx);
  }

  stop() {
    this._playbackToken += 1;
    if (state.ttsEngine === 'edge') {
      this._audio.pause();
      this._audio.currentTime = 0;
      this._audio.removeAttribute('src');
      this._audio.load();
      this._hasLoadedEdgeAudio = false;
    } else {
      window.speechSynthesis.cancel();
    }
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
    this._playbackToken += 1;
    const token = this._playbackToken;

    if (idx >= this._sectionQueue.length) {
      clearWordHighlights();
      setState({ isPlaying: false });
      renderPlayerState();
      showToast('Finished reading this RFC.', 'success');
      return;
    }

    const section = this._sectionQueue[idx];

    // Automatically skip reference and appendix sections
    const headingLower = (section.heading || "").toLowerCase().trim();
    const isReferenceSection = headingLower === "references" ||
      headingLower === "normative references" ||
      headingLower === "informative references";
    const isAppendixSection = headingLower.includes("appendix") ||
      /^[a-z]\.\s/i.test(section.heading || "");
    if (isReferenceSection || isAppendixSection) {
      showToast(`Skipping ${section.heading} section.`, 'info');

      // Momentarily update UI so the jump is visually tracked
      setState({ currentSectionIdx: idx });
      renderActiveSectionHighlight(idx);
      scrollToSection(idx);

      // Move to the next section immediately
      this._speakSection(idx + 1);
      return;
    }

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
    const maskedText = this._maskInlineReferences(textToSpeak);

    if (state.ttsEngine === 'edge') {
      this._speakEdgeAudio(idx, token);
    } else {
      this._speakText(maskedText, idx, token);
    }

    // Update player bar
    renderPlayerNowPlaying(section);
  }

  /**
   * Replace bracketed references like [1], [RFC 1234], [Moy98] with spaces of
   * the exact same length. This causes the TTS engine to silently skip over them
   * while preserving the exact character indices needed for word highlighting.
   */
  _maskInlineReferences(text) {
    if (!text) return text;
    // Matches bracketed text up to 30 characters long
    return text.replace(/\[[^\]]{1,30}\]/g, match => ' '.repeat(match.length));
  }

  /** Internal: create an utterance, wire events, and speak. */
  _speakText(text, sectionIdx, token) {
    if (!text.trim()) {
      this._speakSection(sectionIdx + 1);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = state.playbackRate;

    if (state.selectedVoiceURI) {
      const voices = window.speechSynthesis.getVoices();
      const voice = voices.find(v => v.voiceURI === state.selectedVoiceURI);
      if (voice) utterance.voice = voice;
    }

    // ── Word-level highlighting via boundary events ──
    utterance.onboundary = (e) => {
      if (token !== this._playbackToken) return;
      if (e.name !== 'word') return;

      // Clear the fallback timeout because the engine is successfully firing events
      if (this._resumeTimeout) {
        clearTimeout(this._resumeTimeout);
        this._resumeTimeout = null;
      }

      const absChar = e.charIndex + this._charOffset;
      this._lastBoundaryChar = absChar;
      highlightWordAt(this._currentIdx, absChar);
    };

    utterance.onend = () => {
      if (token !== this._playbackToken) return;
      clearWordHighlights();
      this._speakSection(sectionIdx + 1);
    };

    utterance.onerror = (e) => {
      if (token !== this._playbackToken) return;
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

  _speakEdgeAudio(sectionIdx, token) {
    const rfcNumber = state.currentRFC.rfcNumber;
    const selectedEdgeVoice =
      state.selectedVoiceURI && state.edgeVoices.some(v => v.id === state.selectedVoiceURI)
        ? state.selectedVoiceURI
        : '';

    let packageUrl = `${API_BASE}/rfc/${rfcNumber}/tts/${sectionIdx}/package`;
    if (selectedEdgeVoice) {
      packageUrl += `?voice=${encodeURIComponent(selectedEdgeVoice)}`;
    }

    // Fetch audio+boundaries package from a single backend synthesis path.
    this._wordBoundaries = [];
    this._syncDiagnostics = {
      mode: 'loading',
      sectionIdx,
      boundariesCount: 0,
      matchRate: 0,
      notFoundCount: 0,
      rejectedCount: 0,
    };

    // Show loading toast
    let loadingToast = document.createElement('div');
    loadingToast.id = 'tts-loading';
    loadingToast.className = 'toast toast-info';
    loadingToast.textContent = 'Generating audio...';
    document.body.appendChild(loadingToast);
    requestAnimationFrame(() => loadingToast.classList.add('toast-visible'));

    const removeLoading = () => {
      const t = document.getElementById('tts-loading');
      if (t) {
        t.classList.remove('toast-visible');
        t.addEventListener('transitionend', () => t.remove());
      }
      this._audio.removeEventListener('canplay', removeLoading);
      this._audio.removeEventListener('playing', removeLoading);
    };

    this._audio.addEventListener('canplay', removeLoading);
    this._audio.addEventListener('playing', removeLoading);

    fetch(packageUrl)
      .then(res => res.ok ? res.json() : Promise.reject(new Error(`Package fetch failed: ${res.status}`)))
      .then(pkg => {
        if (token !== this._playbackToken) return;

        const section = this._sectionQueue[sectionIdx];
        const boundaries = pkg?.boundaries || [];
        const mapped = section
          ? this._mapBoundariesToChars(section.content, boundaries)
          : { mappedBoundaries: [], stats: null };

        this._wordBoundaries = mapped.mappedBoundaries;
        this._syncDiagnostics = {
          mode: this._wordBoundaries.length ? 'boundary' : 'fallback',
          sectionIdx,
          boundariesCount: boundaries.length,
          matchRate: mapped.stats?.matchRate ?? 0,
          notFoundCount: mapped.stats?.notFoundCount ?? 0,
          rejectedCount: mapped.stats?.rejectedCount ?? 0,
        };

        console.info('[RFCListen Sync]', {
          rfcNumber,
          sectionIdx,
          sync: this._syncDiagnostics,
          packageDiagnostics: pkg?.diagnostics || null,
          fromCache: pkg?.fromCache,
        });

        if (!pkg?.audioUrl) {
          throw new Error('Missing audioUrl in TTS package response');
        }

        const apiOrigin = API_BASE.replace(/\/api$/, '');
        this._audio.src = pkg.audioUrl.startsWith('http')
          ? pkg.audioUrl
          : `${apiOrigin}${pkg.audioUrl}`;
        this._hasLoadedEdgeAudio = true;
        this._audio.playbackRate = state.playbackRate;

        return this._audio.play();
      })
      .catch(e => {
        removeLoading();
        console.warn('Audio playback failed', e);
        if (e.name !== 'AbortError') {
          showToast('TTS package failed to load. Skipping section.', 'error');
          this._speakSection(sectionIdx + 1);
        }
      });
  }

  _mapBoundariesToChars(content, boundaries) {
    let searchPos = 0;
    let matchedCount = 0;
    let notFoundCount = 0;
    let rejectedCount = 0;

    const mappedBoundaries = boundaries.map(b => {
      const maxLookahead = 4000;
      const textLower = (b.text || '').toLowerCase();
      const windowStr = content.substring(searchPos, searchPos + maxLookahead).toLowerCase();

      const localIdx = windowStr.indexOf(textLower);
      let charIdx;

      if (textLower && localIdx >= 0) {
        const jumpedText = windowStr.substring(0, localIdx);
        const jumpedWords = jumpedText.match(/[a-z0-9]+/gi);
        const skippedWordCount = jumpedWords ? jumpedWords.length : 0;

        if (skippedWordCount <= 5) {
          charIdx = searchPos + localIdx;
          searchPos = charIdx + textLower.length;
          matchedCount += 1;
        } else {
          charIdx = searchPos;
          rejectedCount += 1;
        }
      } else {
        charIdx = searchPos;
        notFoundCount += 1;
      }

      return { ...b, charIdx };
    });

    const total = boundaries.length || 1;
    return {
      mappedBoundaries,
      stats: {
        matchRate: matchedCount / total,
        matchedCount,
        notFoundCount,
        rejectedCount,
      },
    };
  }

  _onAudioEnded() {
    if (!state.isPlaying) return;
    clearWordHighlights();
    this._speakSection(this._currentIdx + 1);
  }

  _onAudioError(e) {
    if (!state.isPlaying) return;
    if (!this._hasLoadedEdgeAudio) return;
    console.warn("Edge TTS error:", e);
    // Usually means no interactable audio, or server 500
    clearWordHighlights();
    this._speakSection(this._currentIdx + 1);
  }

  _onAudioTimeUpdate() {
    const section = this._sectionQueue[this._currentIdx];
    if (!section || !this._audio.duration) return;

    // If we have real word boundary data, use it for precise highlighting
    if (this._wordBoundaries.length > 0) {
      const currentMs = this._audio.currentTime * 1000;

      // Binary search for the last boundary whose offset <= currentMs
      let lo = 0, hi = this._wordBoundaries.length - 1, bestIdx = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (this._wordBoundaries[mid].offset <= currentMs) {
          bestIdx = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }

      const charIndex = this._wordBoundaries[bestIdx].charIdx;
      highlightWordAt(this._currentIdx, charIndex);
      return;
    }

    // Fallback: linear estimation when boundaries aren't available yet
    const progressPercent = this._audio.currentTime / this._audio.duration;
    const charIndex = Math.floor(progressPercent * section.content.length);
    highlightWordAt(this._currentIdx, charIndex);
  }
}

const player = new Player();
let sectionNavTargets = []; // [{ navIdx, sectionIdx, heading }]

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
      <span class="rfc-item-meta">${rfc.status && rfc.status !== 'Unknown' ? escHtml(rfc.status) : ''}${rfc.published ? (rfc.status && rfc.status !== 'Unknown' ? ' · ' : '') + _formatRfcDate(rfc.published) : ''}</span>
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
  sectionNavTargets = sections
    .map((s, idx) => ({ s, idx }))
    .filter(({ s }) => s.type === 'text')
    .filter(({ s }) => {
      if (seen.has(s.heading)) return false;
      seen.add(s.heading);
      return true;
    })
    .map(({ s, idx }, navIdx) => ({
      navIdx,
      sectionIdx: idx,
      heading: s.heading,
    }));

  list.innerHTML = sectionNavTargets.map(({ navIdx, sectionIdx, heading }) => `
    <li
      class="section-nav-item"
      data-nav-idx="${navIdx}"
      data-section-idx="${sectionIdx}"
      tabindex="0"
      role="button"
      aria-label="Jump to ${escHtml(heading)}"
    >${escHtml(heading)}</li>
  `).join('');
}

function getNavTargetForSectionIdx(sectionIdx) {
  if (!sectionNavTargets.length) return null;

  const exact = sectionNavTargets.find(t => t.sectionIdx === sectionIdx);
  if (exact) return exact;

  let best = sectionNavTargets[0];
  for (const target of sectionNavTargets) {
    if (target.sectionIdx <= sectionIdx) {
      best = target;
      continue;
    }
    break;
  }
  return best;
}

function renderActiveSectionHighlight(idx) {
  document.querySelectorAll('.section-block').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.section-nav-item').forEach(el => el.classList.remove('active'));

  const block = document.getElementById(`section-${idx}`);
  if (block) block.classList.add('active');

  const navTarget = getNavTargetForSectionIdx(idx);
  const navItem = navTarget
    ? document.querySelector(`.section-nav-item[data-nav-idx="${navTarget.navIdx}"]`)
    : null;
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

async function fetchEdgeVoices() {
  if (state.edgeVoices.length) return state.edgeVoices;
  try {
    const res = await fetch(`${API_BASE}/tts/voices`);
    if (res.ok) {
      const data = await res.json();
      state.edgeVoices = data.voices || [];
    }
  } catch (err) {
    console.error("Failed to fetch Edge TTS voices:", err);
  }
  return state.edgeVoices;
}

function populateVoices() {
  const select = document.getElementById('voice-select');

  if (state.ttsEngine === 'edge') {
    if (!state.edgeVoices.length) {
      select.innerHTML = '<option value="">Loading Edge Voices...</option>';
      return;
    }
    select.innerHTML = state.edgeVoices.map(v =>
      `<option value="${v.id}" ${state.selectedVoiceURI === v.id ? 'selected' : ''}>
        ${v.name} (${v.gender}, ${v.locale})
      </option>`
    ).join('');
  } else {
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) {
      select.innerHTML = '<option value="">Default Browser Voice</option>';
      return;
    }

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

  updateVoiceControlsLockState();
}

function getCurrentRFCLock() {
  const rfcNumber = state.currentRFC?.rfcNumber;
  if (!rfcNumber) return null;
  return state.rfcVoiceLocks?.[String(rfcNumber)] || null;
}

function lockVoiceForCurrentRFCIfNeeded() {
  const rfcNumber = state.currentRFC?.rfcNumber;
  if (!rfcNumber) return;

  const key = String(rfcNumber);
  if (state.rfcVoiceLocks?.[key]) return;

  const effectiveVoice = getEffectiveSelectedVoice();
  const nextLocks = {
    ...(state.rfcVoiceLocks || {}),
    [key]: {
      voiceURI: effectiveVoice,
      ttsEngine: state.ttsEngine,
    },
  };

  setState({
    rfcVoiceLocks: nextLocks,
    selectedVoiceURI: effectiveVoice,
  });

  updateVoiceControlsLockState();
}

function getEffectiveSelectedVoice() {
  if (state.ttsEngine === 'edge') {
    const hasCurrent = state.selectedVoiceURI && state.edgeVoices.some(v => v.id === state.selectedVoiceURI);
    if (hasCurrent) return state.selectedVoiceURI;
    const hasBrian = state.edgeVoices.some(v => v.id === DEFAULT_EDGE_VOICE_ID);
    return hasBrian ? DEFAULT_EDGE_VOICE_ID : (state.edgeVoices[0]?.id || DEFAULT_EDGE_VOICE_ID);
  }
  return state.selectedVoiceURI || '';
}

function syncVoiceSelectionForCurrentRFC() {
  const lock = getCurrentRFCLock();
  if (lock) {
    setState({
      ttsEngine: lock.ttsEngine,
      selectedVoiceURI: lock.voiceURI,
    });
    const engineSelect = document.getElementById('engine-select');
    if (engineSelect) engineSelect.value = lock.ttsEngine;
    populateVoices();
    const voiceSelect = document.getElementById('voice-select');
    if (voiceSelect) voiceSelect.value = lock.voiceURI;
    updateVoiceControlsLockState();
    return;
  }

  if (state.ttsEngine === 'edge') {
    const nextVoice = getEffectiveSelectedVoice();
    if (nextVoice !== state.selectedVoiceURI) {
      setState({ selectedVoiceURI: nextVoice });
    }
    const voiceSelect = document.getElementById('voice-select');
    if (voiceSelect) voiceSelect.value = nextVoice;
  }

  updateVoiceControlsLockState();
}

function updateVoiceControlsLockState() {
  const lock = getCurrentRFCLock();
  const voiceSelect = document.getElementById('voice-select');
  const engineSelect = document.getElementById('engine-select');
  if (!voiceSelect || !engineSelect) return;

  const locked = Boolean(lock);
  voiceSelect.disabled = locked;
  engineSelect.disabled = locked;

  const lockMsg = locked
    ? `Voice locked for RFC ${state.currentRFC?.rfcNumber}.`
    : 'TTS voice';

  voiceSelect.setAttribute('aria-label', lockMsg);
  voiceSelect.title = lockMsg;
  engineSelect.title = lockMsg;
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
/**
 * Highlight the word at or near the given char index in the active section.
 * Uses a fuzzy search because TTS engines often report char indices that have
 * drifted from the exact text (due to punctuation, abbreviations, etc).
 */
function highlightWordAt(sectionIdx, targetCharIdx) {
  const block = document.getElementById(`section-${sectionIdx}`);
  if (!block) return;

  const words = Array.from(block.querySelectorAll('.tts-word'));
  if (words.length === 0) return;

  // Find the span closest to the target char index without exceeding it by too much
  let bestIdx = 0;
  for (let i = 0; i < words.length; i++) {
    const spanChar = parseInt(words[i].dataset.char, 10);
    if (spanChar <= targetCharIdx) {
      bestIdx = i;
    } else {
      break;
    }
  }

  // Handle the active word and surrounding words
  for (let i = 0; i < words.length; i++) {
    const span = words[i];
    if (i === bestIdx) {
      // This is the active word
      if (!span.classList.contains('tts-word--active')) {
        span.classList.add('tts-word--active');
        span.classList.remove('tts-word--spoken');
        // Scroll the word into view if needed
        span.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    } else if (i < bestIdx) {
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

/** Format an ISO date string as "Month Year" (e.g. "February 2026"). */
function _formatRfcDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
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

  // Engine Toggle
  const engineSelect = document.getElementById('engine-select');
  if (engineSelect) {
    engineSelect.addEventListener('change', (e) => {
      const lock = getCurrentRFCLock();
      if (lock) {
        engineSelect.value = lock.ttsEngine;
        showToast(`Voice is locked for RFC ${state.currentRFC.rfcNumber}.`, 'info');
        return;
      }

      setState({ ttsEngine: e.target.value });
      populateVoices();

      if (state.ttsEngine === 'edge') {
        const nextVoice = getEffectiveSelectedVoice();
        setState({ selectedVoiceURI: nextVoice });
        const voiceSelect = document.getElementById('voice-select');
        if (voiceSelect) voiceSelect.value = nextVoice;
      }

      if (state.isPlaying) {
        player.stop();
        player.play(); // Restart section with new engine
      }
    });
  }

  // Speed
  document.getElementById('speed-select').addEventListener('change', (e) => {
    player.setRate(Number(e.target.value));
  });

  // Voice
  document.getElementById('voice-select').addEventListener('change', (e) => {
    const lock = getCurrentRFCLock();
    if (lock) {
      e.target.value = lock.voiceURI;
      showToast(`Voice is locked for RFC ${state.currentRFC.rfcNumber}.`, 'info');
      return;
    }
    player.setVoice(e.target.value);
  });

  // Section nav clicks
  document.getElementById('sections-list').addEventListener('click', (e) => {
    const item = e.target.closest('.section-nav-item');
    if (!item) return;
    const idx = Number(item.dataset.sectionIdx);
    player.jumpToSection(idx);
  });

  // Section nav keyboard
  document.getElementById('sections-list').addEventListener('keydown', (e) => {
    if (e.code === 'Enter') {
      const item = e.target.closest('.section-nav-item');
      if (item) player.jumpToSection(Number(item.dataset.sectionIdx));
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

    // ── PDF-only fallback ──────────────────────────────────────────────────
    if (rfc.pdfOnly) {
      setState({ currentRFC: null, currentSectionIdx: 0 });

      document.getElementById('rfc-title').textContent = rfc.title;

      // Render PDF-only content view
      document.getElementById('rfc-content').innerHTML = `
        <div class="pdf-only-view">
          <div class="pdf-only-icon">📄</div>
          <h2 class="pdf-only-heading">PDF Only</h2>
          <p class="pdf-only-message">
            This RFC is only available as a PDF and cannot be read aloud.
          </p>
          <a href="${escHtml(rfc.pdfUrl)}" target="_blank" rel="noopener noreferrer" class="pdf-only-btn">
            View PDF <span class="pdf-only-btn-arrow">→</span>
          </a>
        </div>`;

      // Hide sections nav and keep player disabled
      document.getElementById('sections-nav').classList.add('hidden');
      document.getElementById('sections-list').innerHTML = '';
      document.getElementById('player-bar').classList.add('player-bar--disabled');
      renderPlayerNowPlaying(null);

      // Add to recently played so user can find it again
      addToRecents(rfcNumber, rfc.title);
      renderRecentsList();

      // Highlight selected item in left list
      document.querySelectorAll('.rfc-list-item').forEach(el => {
        el.classList.toggle('active', Number(el.dataset.rfc) === rfcNumber);
      });

      showToast(`RFC ${rfcNumber} is available as PDF only`, 'info');
      return;
    }

    // ── Normal text RFC ────────────────────────────────────────────────────
    setState({ currentRFC: rfc, currentSectionIdx: 0 });
    renderRFCContent(rfc);
    syncVoiceSelectionForCurrentRFC();

    player.load(rfc.sections, 0);
    renderPlayerNowPlaying(rfc.sections[0]);
    setState({ isPlaying: false });
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

  // Set UI elements to match loaded state
  const engineSelect = document.getElementById('engine-select');
  if (engineSelect && state.ttsEngine) {
    engineSelect.value = state.ttsEngine;
  }
  document.getElementById('speed-select').value = String(state.playbackRate);

  // Sync sort dropdown with persisted state
  const sortSelect = document.getElementById('sort-order');
  if (sortSelect && state.sortOrder) {
    sortSelect.value = state.sortOrder;
  }

  // Fetch Edge voices in background, then populate UI
  fetchEdgeVoices().then(() => {
    syncVoiceSelectionForCurrentRFC();
    populateVoices();
  });
  window.speechSynthesis.onvoiceschanged = populateVoices;

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
    syncVoiceSelectionForCurrentRFC();
    player.load(state.currentRFC.sections, state.currentSectionIdx);
    renderPlayerNowPlaying(state.currentRFC.sections[state.currentSectionIdx] || state.currentRFC.sections[0]);
    renderPlayerState();
    renderSectionProgress();
    renderActiveSectionHighlight(state.currentSectionIdx);
  }
}

init();
