self.addEventListener('push', event => {
  let draftId;
  try { draftId = event.data?.json().draftId; } catch { return; }
  if (typeof draftId !== 'string' || !/^[a-f0-9]{64}$/.test(draftId)) return;
  event.waitUntil(self.registration.showNotification('КопиКэш', {
    body: 'Подтвердите покупку, если вы её оплатили.',
    icon: '/static/kopicash-192.png',
    tag: 'purchase-' + draftId,
    data: { draftId },
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const draftId = event.notification.data?.draftId;
  if (typeof draftId !== 'string' || !/^[a-f0-9]{64}$/.test(draftId)) return;
  const target = new URL('/', self.location.origin);
  target.searchParams.set('draft', draftId);
  target.hash = 'home';
  event.waitUntil(self.clients.openWindow(target.href));
});
