const CACHE_NAME = "edgealert-v18";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Manejo de Notificaciones Nativas en Android (Bypassea el error de new Notification en móviles)
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SHOW_NOTIFICATION") {
    const { title, options } = event.data;
    const notificationOptions = {
      body: options?.body || "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      vibrate: options?.vibrate || [500, 150, 500],
      tag: options?.tag || "edgealert-signal",
      renotify: true,
      requireInteraction: options?.requireInteraction || false,
      data: {
        url: "/"
      }
    };
    event.waitUntil(
      self.registration.showNotification(title, notificationOptions)
    );
  }
});

// Al pulsar la notificación en Android, enfoca la app abierta o la abre
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url && "focus" in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow("/");
      }
    })
  );
});

// NUNCA interceptar peticiones a la API de Render ni peticiones cross-origin.
// Se dejan pasar directo al stack de red nativo del navegador para eliminar cualquier cuelgue en móviles.
self.addEventListener("fetch", (event) => {
  if (
    !event.request.url.startsWith(self.location.origin) ||
    event.request.url.includes("/signals/") ||
    event.request.url.includes("/health") ||
    event.request.method !== "GET"
  ) {
    return;
  }
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
