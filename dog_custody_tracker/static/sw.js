const ASSET_VERSION = "0.1.41";
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

self.addEventListener("push", (event) => {
  const payload = (() => {
    try {
      return event.data?.json() || {};
    } catch (_error) {
      return { body: event.data?.text() || "" };
    }
  })();

  event.waitUntil(
    self.registration.showNotification(payload.title || "Chewie Walk Tracker", {
      body: payload.body || "There is an update in Chewie Walk Tracker.",
      icon: payload.icon || `/icon-192.png?v=${ASSET_VERSION}`,
      badge: payload.badge || `/icon-192.png?v=${ASSET_VERSION}`,
      tag: payload.tag || "chewie-notification",
      data: {
        url: payload.url || "/?source=notification",
      },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = new URL(event.notification.data?.url || "/?source=notification", self.location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === targetUrl && "focus" in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
      return undefined;
    })
  );
});
