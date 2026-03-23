/* eslint-disable no-restricted-globals */
const CACHE_NAME = '5812-crm-v2';
const STATIC_ASSETS = ['/', '/index.html', '/manifest.json', '/logo192.png', '/logo512.png'];
const DB_NAME = '5812-offline-queue';
const STORE_NAME = 'messages';

// ---- IndexedDB helpers for offline queue ----
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => { req.result.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true }); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function addToQueue(data) {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  tx.objectStore(STORE_NAME).add(data);
  return new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = rej; });
}

async function getQueuedItems() {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, 'readonly');
  const store = tx.objectStore(STORE_NAME);
  return new Promise((res, rej) => {
    const req = store.getAll();
    req.onsuccess = () => res(req.result);
    req.onerror = () => rej(req.error);
  });
}

async function clearQueue() {
  const db = await openDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  tx.objectStore(STORE_NAME).clear();
  return new Promise((res) => { tx.oncomplete = res; });
}

// ---- Install ----
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

// ---- Activate ----
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

// ---- Fetch: network-first for API, cache-first for static ----
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.protocol === 'ws:' || url.protocol === 'wss:') return;

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      }).catch(() => caches.match(request).then((cached) => cached || new Response(JSON.stringify({ error: 'Offline', offline: true }), { status: 503, headers: { 'Content-Type': 'application/json' } })))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok && (url.pathname.endsWith('.js') || url.pathname.endsWith('.css') || url.pathname.endsWith('.png') || url.pathname.endsWith('.svg') || url.pathname.endsWith('.woff2'))) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      }).catch(() => {
        if (request.mode === 'navigate') return caches.match('/index.html');
        return new Response('', { status: 503 });
      });
    })
  );
});

// ---- Background Sync: flush offline message queue ----
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-messages') {
    event.waitUntil(syncOfflineMessages());
  }
});

async function syncOfflineMessages() {
  try {
    const items = await getQueuedItems();
    if (items.length === 0) return;
    const messages = items.map(i => i.payload);
    // Try to sync with backend
    const response = await fetch('/api/sync/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${items[0]?.token || ''}` },
      body: JSON.stringify({ messages }),
    });
    if (response.ok) {
      await clearQueue();
      // Notify all clients
      const clients = await self.clients.matchAll();
      clients.forEach(client => client.postMessage({ type: 'sync-complete', synced: messages.length }));
    }
  } catch (e) {
    // Will retry automatically
  }
}

// ---- Push Notifications ----
self.addEventListener('push', (event) => {
  const data = event.data?.json() || {};
  event.waitUntil(
    self.registration.showNotification(data.title || '58:12 Global', {
      body: data.body || 'New notification',
      icon: '/logo192.png',
      badge: '/logo192.png',
      tag: data.tag || 'default',
      data: { url: data.url || '/' },
      actions: data.actions || [],
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((list) => {
      for (const client of list) {
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});

// ---- Message from main thread (queue offline messages) ----
self.addEventListener('message', (event) => {
  if (event.data?.type === 'queue-message') {
    addToQueue({ payload: event.data.payload, token: event.data.token, timestamp: Date.now() }).then(() => {
      // Request background sync
      if (self.registration.sync) self.registration.sync.register('sync-messages');
    });
  }
});
