/* Leadsrat PWA: cache only the public static shell, never authenticated API data. */
const CACHE_NAME = "leadsrat-shell-v2";
const SHELL = [
  "/leadsrat/",
  "/leadsrat/manifest.webmanifest",
  "/leadsrat/icon.svg",
  "/leadsrat/icon-192.png",
  "/leadsrat/icon-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key.startsWith("leadsrat-shell-") && key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/leadsrat/api/")) return;

  if (request.mode === "navigate" && url.pathname === "/leadsrat/") {
    event.respondWith(fetch(request).catch(() => caches.match("/leadsrat/")));
    return;
  }

  if (SHELL.includes(url.pathname)) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request))
    );
  }
});
