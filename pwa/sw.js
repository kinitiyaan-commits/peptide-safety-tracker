/* Service worker for the static PWA.
 *
 * The app has NO server-side data: all user records live in IndexedDB on
 * this device. The worker only caches the static app shell so the app
 * opens offline. Any future API call for USER data must bypass this cache
 * (see tests/test_pwa.py — no fetch() of user data is allowed in the app).
 */

const CACHE = "peptide-safety-static-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./app.js",
  "./store.js",
  "./data.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "https://cdn.tailwindcss.com",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    for (const asset of ASSETS) {
      try {
        await cache.add(asset);
      } catch (e) {
        // cross-origin scripts without CORS headers: store the opaque response
        if (asset.startsWith("http")) {
          try {
            await cache.put(asset, await fetch(asset, { mode: "no-cors" }));
          } catch (e2) { /* offline install: shell still precached */ }
        }
      }
    }
    self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Cache-first for GET requests (including the cross-origin app-shell
// dependencies cached at install). FDA/DailyMed pages the user opens are
// not pre-cached and simply fail offline like any normal navigation.
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
