const KEY = "noi_app_mode"; // "pwa" | "cloud"

export function getAppMode() {
  return localStorage.getItem(KEY) || "pwa";
}

export function setAppMode(mode) {
  localStorage.setItem(KEY, mode);
}

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

export async function applyAppMode(mode) {
  setAppMode(mode);
  await clearServiceWorkerCache();
  if (mode === "pwa" && "serviceWorker" in navigator) {
    try { await navigator.serviceWorker.register("/sw.js"); } catch (e) {}
  }
}
