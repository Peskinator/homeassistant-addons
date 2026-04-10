const ASSET_VERSION = "0.1.0-22";
const CACHE_NAME = `chewie-walk-tracker-${ASSET_VERSION}`;
const APP_SHELL = [
  "/",
  `/styles.css?v=${ASSET_VERSION}`,
  `/app.js?v=${ASSET_VERSION}`,
  `/manifest.webmanifest?v=${ASSET_VERSION}`,
  `/icon-192.png?v=${ASSET_VERSION}`,
  `/icon-512.png?v=${ASSET_VERSION}`,
  `/chewie-icon.jpg?v=${ASSET_VERSION}`,
  `/frank.jpg?v=${ASSET_VERSION}`,
  `/kurt.jpg?v=${ASSET_VERSION}`,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (request.url.startsWith(self.location.origin) && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) => {
          if (cached) {
            return cached;
          }
          if (request.mode === "navigate") {
            return caches.match("/");
          }
          return Response.error();
        })
      )
  );
});
