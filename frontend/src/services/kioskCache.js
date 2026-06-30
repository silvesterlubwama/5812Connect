// Lightweight LRU-style cache for kiosk lookups so QR/phone/ID scans keep
// working when the venue's wifi drops mid-event. We trade a small bit of
// privacy (lookup payloads in localStorage) for resilience — entries expire
// after 12h and the cache holds at most 200 lookups.
//
// Cached only on SUCCESS — we never poison the cache with a 404. Reads only
// happen as a fallback when the network call fails.

const CACHE_KEY = '5812_kiosk_lookup_cache_v1';
const MAX_ENTRIES = 200;
const TTL_MS = 12 * 60 * 60 * 1000; // 12h

function loadAll() {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}');
  } catch {
    return {};
  }
}

function saveAll(data) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    // Quota exceeded — drop oldest half and retry once.
    try {
      const entries = Object.entries(data).sort((a, b) => a[1].at - b[1].at);
      const half = Object.fromEntries(entries.slice(Math.floor(entries.length / 2)));
      localStorage.setItem(CACHE_KEY, JSON.stringify(half));
    } catch { /* give up */ }
  }
}

function normaliseKey(scope, lookup) {
  return `${scope}:${(lookup || '').trim().toLowerCase()}`;
}

export function rememberLookup(scope, lookup, value) {
  if (!lookup || !value) return;
  const all = loadAll();
  const key = normaliseKey(scope, lookup);
  all[key] = { at: Date.now(), value };
  // Evict oldest if we're over the cap.
  const keys = Object.keys(all);
  if (keys.length > MAX_ENTRIES) {
    const sorted = keys.sort((a, b) => all[a].at - all[b].at);
    sorted.slice(0, keys.length - MAX_ENTRIES).forEach(k => delete all[k]);
  }
  saveAll(all);
}

export function recallLookup(scope, lookup) {
  if (!lookup) return null;
  const all = loadAll();
  const entry = all[normaliseKey(scope, lookup)];
  if (!entry) return null;
  if (Date.now() - entry.at > TTL_MS) return null;
  return entry.value;
}

export function isLikelyOffline(err) {
  // axios sets `response` on HTTP errors; absence usually means network died.
  // We also treat 502/503/504 as offline-ish since the proxy is unreachable.
  if (!err) return false;
  if (!err.response) return true;
  return err.response.status >= 502 && err.response.status <= 504;
}
