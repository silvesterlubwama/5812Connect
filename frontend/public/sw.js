/* eslint-disable no-restricted-globals */
const CACHE_NAME = '5812-crm-v3';
const WALLET_CACHE = '5812-wallet-v1';
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

// ---- Activate: purge old caches, keep wallet cache ----
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE_NAME && k !== WALLET_CACHE).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

// ---- Wallet Pass detection: these must always work offline ----
function isWalletRequest(url) {
  const p = url.pathname;
  // Public badge viewer page, wallet-badge endpoint, and QR image endpoints
  return p.startsWith('/badge/')
      || p.startsWith('/api/wallet-badge/')
      || p.startsWith('/api/members/') && p.includes('/qr-code')
      || p.startsWith('/api/members/') && p.includes('/profile-photo');
}

// ---- Fetch: wallet-first for passes, network-first for API, cache-first for static ----
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.protocol === 'ws:' || url.protocol === 'wss:') return;

  // Wallet Pass: cache-first with stale-while-revalidate — must always render offline
  if (isWalletRequest(url)) {
    event.respondWith(
      caches.open(WALLET_CACHE).then((cache) =>
        cache.match(request).then((cached) => {
          const fetchPromise = fetch(request).then((response) => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          }).catch(() => cached);
          return cached || fetchPromise;
        })
      )
    );
    return;
  }

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
    const response = await fetch('/api/sync/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${items[0]?.token || ''}` },
      body: JSON.stringify({ messages }),
    });
    if (response.ok) {
      await clearQueue();
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

// ---- Message from main thread: queue offline messages, or prefetch wallet passes ----
self.addEventListener('message', (event) => {
  if (event.data?.type === 'queue-message') {
    addToQueue({ payload: event.data.payload, token: event.data.token, timestamp: Date.now() }).then(() => {
      if (self.registration.sync) self.registration.sync.register('sync-messages');
    });
  }
  if (event.data?.type === 'prefetch-wallet-pass') {
    // Pre-cache wallet pass URLs so they're guaranteed offline
    const urls = event.data.urls || [];
    caches.open(WALLET_CACHE).then(async (cache) => {
      await Promise.all(urls.map(async (u) => {
        try {
          const res = await fetch(u, { credentials: 'include' });
          if (res.ok) await cache.put(u, res.clone());
        } catch (e) {}
      }));
      const clients = await self.clients.matchAll();
      clients.forEach(c => c.postMessage({ type: 'wallet-pass-cached', count: urls.length }));
    });
  }
});
