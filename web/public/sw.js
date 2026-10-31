/* Service worker del panel: recibe el Web Push del personal.
 *
 * El backend cifra el aviso con la clave pública del navegador y lo entrega al
 * servicio de push; este archivo solo lo muestra. Al tocar la notificación se
 * enfoca el panel abierto o se abre uno nuevo con la bandeja de avisos, donde
 * vive el detalle y el enlace a la pantalla que lo originó.
 */

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = {};
  }
  const title = typeof payload.title === "string" && payload.title ? payload.title : "Centro Fit";
  const body = typeof payload.body === "string" && payload.body ? payload.body : "Tienes un aviso nuevo en el panel.";
  const data = payload.data && typeof payload.data === "object" ? payload.data : {};
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      data,
      tag: data.notification_id || undefined,
      icon: "/icon.png",
      badge: "/icon.png",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL("/?avisos=1", self.location.origin).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const existing = windows.find((client) => client.url.startsWith(self.location.origin));
      if (existing) {
        await existing.focus();
        if (typeof existing.navigate === "function") {
          await existing.navigate(target).catch(() => undefined);
        }
        return;
      }
      await self.clients.openWindow(target);
    })(),
  );
});
