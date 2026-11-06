/* DukaanFlow app shell: makes the app installable and lets it open without internet
 * (salesmen in shops without signal).
 * Caches only this app's own files (index.html, built JS/CSS, icons) so the app opens
 * without a connection. API data is never cached here: the salesman's retailers,
 * products and unsent orders live in IndexedDB. */
const CACHE = 'dukaanflow-shell-v2'

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE)
    const html = await (await fetch('/index.html', { cache: 'no-store' })).text()
    const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])
    await cache.addAll(['/', '/index.html', '/favicon.svg', '/manifest.webmanifest', '/icon-192.png', ...assets])
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key)
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return // API calls go straight to the network

  if (request.mode === 'navigate') {
    // Pages: network first (fresh app when online), cached app shell when offline.
    event.respondWith((async () => {
      try {
        const fresh = await fetch(request)
        const cache = await caches.open(CACHE)
        await cache.put('/index.html', fresh.clone())
        return fresh
      } catch {
        return (await caches.match('/index.html')) || Response.error()
      }
    })())
    return
  }

  // Built files are content-hashed: cache first, then network (and remember it).
  event.respondWith((async () => {
    const cached = await caches.match(request)
    if (cached) return cached
    const response = await fetch(request)
    if (response.ok) (await caches.open(CACHE)).put(request, response.clone())
    return response
  })())
})
