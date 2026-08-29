const SHELL_CACHE = "noi-shell-v2";
const API_CACHE = "noi-api-v2";
const LOGO = "https://customer-assets.emergentagent.com/job_fd8a2fce-eb5b-4ab8-a990-d9b853fdd702/artifacts/oxjy3e6l_Gemini_Generated_Image_.png";

// Endpoint GET da mettere in cache per la modalità offline (sola lettura)
const CACHEABLE_API = ["/api/chat/messages", "/api/news", "/api/events"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(["/"]).catch(() => {})));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => ![SHELL_CACHE, API_CACHE].includes(k)).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

async function networkFirst(req, cacheName, fallbackUrl) {
  try {
    const res = await fetch(req);
    if (res && res.status === 200) {
      const cache = await caches.open(cacheName);
      cache.put(req, res.clone());
    }
    return res;
  } catch (e) {
    const cached = await caches.match(req);
    if (cached) return cached;
    if (fallbackUrl) {
      const shell = await caches.match(fallbackUrl);
      if (shell) return shell;
    }
    throw e;
  }
}

async function cacheFirst(req, cacheName) {
  const cached = await caches.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res && res.status === 200) {
    const cache = await caches.open(cacheName);
    cache.put(req, res.clone());
  }
  return res;
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // le scritture non vengono toccate/cacheate
  const url = new URL(req.url);

  if (url.pathname && CACHEABLE_API.includes(url.pathname)) {
    event.respondWith(networkFirst(req, API_CACHE));
    return;
  }
  // Altre chiamate /api: solo rete (no cache), per non servire dati stantii/protetti
  if (url.pathname.startsWith("/api/")) return;

  if (url.origin === self.location.origin) {
    if (req.mode === "navigate") {
      event.respondWith(networkFirst(req, SHELL_CACHE, "/"));
      return;
    }
    event.respondWith(cacheFirst(req, SHELL_CACHE));
  }
});

self.addEventListener("push", (event) => {
  let data = { title: "NOI DI 2D", body: "Nuova notifica", url: "/" };
  try { data = { ...data, ...event.data.json() }; } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body, icon: LOGO, badge: LOGO,
      data: { url: data.url }, vibrate: [80, 40, 80],
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) { if ("focus" in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
