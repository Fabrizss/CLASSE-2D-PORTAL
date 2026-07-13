import { api } from "@/lib/api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export async function enablePush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    throw new Error("Notifiche push non supportate su questo browser/dispositivo.");
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Permesso notifiche negato.");
  const reg = await navigator.serviceWorker.ready;
  const { data } = await api.get("/push/vapid-public");
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(data.key),
  });
  await api.post("/push/subscribe", { subscription: sub.toJSON() });
  return true;
}
