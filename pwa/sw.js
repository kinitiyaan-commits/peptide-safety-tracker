/* Service worker for the static PWA.
 *
 * The app has NO server-side data: all user records live in IndexedDB on
 * this device. The worker only caches the static app shell so the app
 * opens offline. Any future API call for USER data must bypass this cache
 * (see tests/test_pwa.py — no fetch() of user data is allowed in the app).
 *
 * Controlled update strategy:
 * - Install is STRICT: every release asset must cache successfully before
 *   the new worker installs. If any asset fails, this worker never takes
 *   over and the previous working version (and its cache) stays in place.
 * - The worker does NOT skipWaiting on its own. It stays "waiting" until
 *   the user accepts the update (postMessage ACCEPT_UPDATE), so an
 *   unfinished form is never interrupted by a mid-session swap.
 * - Activation deletes ONLY caches owned by this app (prefix below) —
 *   never unrelated caches on the same origin.
 */

const CACHE_PREFIX = "peptide-safety-static-";
const CACHE = CACHE_PREFIX + "v8";
const ASSETS = [
  "./",
  "./index.html",
  "./app.js",
  "./store.js",
  "./data.js",
  "./styles.css",
  "./privacy.html",
  "./terms.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  // Strict: if ANY release asset fails to cache, install fails and the
  // previous worker keeps serving the working app.
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS))
  );
});

// The page sends ACCEPT_UPDATE only when the user taps "Reload & update".
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "ACCEPT_UPDATE") self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys
        .filter((k) => k.startsWith(CACHE_PREFIX) && k !== CACHE)
        .map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Cache-first for GET requests. FDA/DailyMed/Drugs@FDA pages the user
// opens are not pre-cached and simply fail offline like any navigation.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request, { ignoreVary: true }).then((hit) => {
      if (hit) return hit;
      return fetch(event.request).then((resp) => {
        if (resp.ok && event.request.url.startsWith(self.location.origin)) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
        }
        return resp;
      }).catch(() =>
        event.request.mode === "navigate"
          ? caches.match("./index.html") : Response.error());
    })
  );
});
