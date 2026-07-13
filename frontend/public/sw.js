self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = { title: "NOI DI 2D", body: "Nuova notifica", url: "/" };
  try { data = { ...data, ...event.data.json() }; } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "https://customer-assets.emergentagent.com/job_fd8a2fce-eb5b-4ab8-a990-d9b853fdd702/artifacts/oxjy3e6l_Gemini_Generated_Image_.png",
      badge: "https://customer-assets.emergentagent.com/job_fd8a2fce-eb5b-4ab8-a990-d9b853fdd702/artifacts/oxjy3e6l_Gemini_Generated_Image_.png",
      data: { url: data.url },
      vibrate: [80, 40, 80],
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
