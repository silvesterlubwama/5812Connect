// Offline POS queue — cash-only sales queued in IndexedDB when network is down,
// auto-synced when connection returns. Refuses non-cash payments offline.

const DB_NAME = '5812_pos_offline';
const DB_VERSION = 1;
const STORE_QUEUE = 'pending_sales';

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_QUEUE)) {
        const store = db.createObjectStore(STORE_QUEUE, { keyPath: 'id', autoIncrement: true });
        store.createIndex('synced', 'synced');
        store.createIndex('created_at', 'created_at');
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Queue a sale locally. Returns the offline sale record with a temp_id.
 * Called when network is offline AND payment_method === 'cash'.
 */
export async function queueOfflineSale(payload) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite');
    const store = tx.objectStore(STORE_QUEUE);
    const record = {
      ...payload,
      temp_id: `OFFLINE-${Date.now()}-${Math.random().toString(36).slice(2, 7).toUpperCase()}`,
      created_at: new Date().toISOString(),
      synced: 0,
      sync_attempts: 0,
    };
    const req = store.add(record);
    req.onsuccess = () => resolve(record);
    req.onerror = () => reject(req.error);
  });
}

/** List all pending (unsynced) offline sales. */
export async function listPendingOfflineSales() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readonly');
    const store = tx.objectStore(STORE_QUEUE);
    const req = store.getAll();
    req.onsuccess = () => resolve((req.result || []).filter(r => !r.synced));
    req.onerror = () => reject(req.error);
  });
}

/** Mark an offline sale as synced (after successful POST to /api/sales). */
export async function markOfflineSaleSynced(id, serverId, serverReceiptNumber) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite');
    const store = tx.objectStore(STORE_QUEUE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const rec = getReq.result;
      if (!rec) return resolve(null);
      rec.synced = 1;
      rec.server_id = serverId;
      rec.server_receipt = serverReceiptNumber;
      rec.synced_at = new Date().toISOString();
      const putReq = store.put(rec);
      putReq.onsuccess = () => resolve(rec);
      putReq.onerror = () => reject(putReq.error);
    };
    getReq.onerror = () => reject(getReq.error);
  });
}

/** Increment sync_attempts on a failed sync (kept for retries). */
export async function bumpSyncAttempt(id, errorMsg = '') {
  const db = await openDB();
  return new Promise((resolve) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite');
    const store = tx.objectStore(STORE_QUEUE);
    const getReq = store.get(id);
    getReq.onsuccess = () => {
      const rec = getReq.result;
      if (!rec) return resolve();
      rec.sync_attempts = (rec.sync_attempts || 0) + 1;
      rec.last_sync_error = errorMsg;
      store.put(rec);
      resolve();
    };
  });
}

/** Sync all pending offline sales to the server. Called on reconnect. */
export async function syncOfflineSales(salesApi, onProgress = () => {}) {
  const pending = await listPendingOfflineSales();
  let succeeded = 0;
  let failed = 0;
  for (const sale of pending) {
    try {
      const payload = { ...sale };
      delete payload.id; delete payload.synced; delete payload.sync_attempts; delete payload.last_sync_error; delete payload.temp_id;
      payload.offline_temp_id = sale.temp_id;
      payload.offline_created_at = sale.created_at;
      const res = await salesApi.create(payload);
      await markOfflineSaleSynced(sale.id, res.data.id, res.data.receipt_number);
      succeeded++;
      onProgress({ done: succeeded + failed, total: pending.length, last: res.data });
    } catch (e) {
      await bumpSyncAttempt(sale.id, e.message || String(e));
      failed++;
    }
  }
  return { succeeded, failed, total: pending.length };
}

/** Count unsynced offline sales (used to show a badge on POS). */
export async function offlineQueueCount() {
  const pending = await listPendingOfflineSales();
  return pending.length;
}

/** Listen for online/offline state changes. Returns a cleanup fn. */
export function onConnectivityChange(onOnline, onOffline) {
  const handleOnline = () => onOnline && onOnline();
  const handleOffline = () => onOffline && onOffline();
  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);
  return () => {
    window.removeEventListener('online', handleOnline);
    window.removeEventListener('offline', handleOffline);
  };
}
