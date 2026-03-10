/**
 * sw.js — RFCListen Service Worker
 *
 * Caching strategy:
 *   - App shell (HTML, CSS, JS, JSON) → Cache first, pre-cached on install
 *   - Google Fonts                    → Stale-while-revalidate
 *   - API requests                    → Network first, fall back to cache
 *   - Everything else                 → Network only
 */

const CACHE_NAME = 'rfclisten-v1';

const APP_SHELL = [
    './',
    './index.html',
    './style.css',
    './app.js',
    './top-rfcs.json',
    './manifest.json',
    './icons/icon-192.png',
    './icons/icon-512.png',
];

// ── Install: pre-cache the app shell ──────────────────────────────────────────
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Pre-caching app shell');
            return cache.addAll(APP_SHELL);
        })
    );
    // Activate immediately without waiting for old SW to retire
    self.skipWaiting();
});

// ── Activate: clean up old caches ─────────────────────────────────────────────
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(
                names
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => {
                        console.log('[SW] Deleting old cache:', name);
                        return caches.delete(name);
                    })
            )
        )
    );
    // Take control of all open tabs immediately
    self.clients.claim();
});

// ── Fetch: route requests to the right strategy ───────────────────────────────
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests (POST, etc.)
    if (event.request.method !== 'GET') return;

    // Strategy 1: Google Fonts — stale-while-revalidate
    if (
        url.hostname === 'fonts.googleapis.com' ||
        url.hostname === 'fonts.gstatic.com'
    ) {
        event.respondWith(staleWhileRevalidate(event.request));
        return;
    }

    // Strategy 2: API requests — network first, fall back to cache
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/api')) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    // Strategy 3: App shell & same-origin assets — cache first
    if (url.origin === self.location.origin) {
        event.respondWith(cacheFirst(event.request));
        return;
    }

    // Everything else: just fetch normally
});

// ── Caching strategies ────────────────────────────────────────────────────────

async function cacheFirst(request) {
    const cached = await caches.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (err) {
        // If both cache and network fail, return a basic offline page
        return new Response('Offline — please reconnect and reload.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain' },
        });
    }
}

async function networkFirst(request) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, response.clone());
        }
        return response;
    } catch (err) {
        const cached = await caches.match(request);
        if (cached) return cached;
        return new Response(JSON.stringify({ error: 'Offline' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
        });
    }
}

async function staleWhileRevalidate(request) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);

    // Fire off network fetch in the background to update cache
    const networkFetch = fetch(request)
        .then((response) => {
            if (response.ok) {
                cache.put(request, response.clone());
            }
            return response;
        })
        .catch(() => null);

    // Return cached version immediately if available, otherwise wait for network
    return cached || (await networkFetch) || new Response('', { status: 503 });
}
