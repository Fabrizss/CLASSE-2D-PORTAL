// L'app lavora sempre online-first con backup automatico offline (service worker sempre attivo).
// Nessuna modalità manuale: queste funzioni servono solo a forzare un refresh della cache.

export async function clearServiceWorkerCache() {
  if ("serviceWorker" in navigator) {
    const regs = await navigator.serviceWorker.getRegistrations();
    await Promise.all(regs.map((r) => r.unregister()));
  }
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
  }
}

export async function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    try { await navigator.serviceWorker.register("/sw.js"); } catch (e) {}
  }
}
