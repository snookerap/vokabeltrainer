// Service Worker nur für Erinnerungen (Push-Mitteilungen) – kein Offline-Zwischenspeicher.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Vokabeln', {
    body: d.body || '', icon: '/icons/icon-uk-192.png', badge: '/icons/icon-uk-192.png', tag: 'vokabeln-erinnerung', data: { url: d.url || '/' }
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
    for (const c of cs) if ('focus' in c) return c.focus().catch(() => self.clients.openWindow(url));
    return self.clients.openWindow(url);
  }));
});
