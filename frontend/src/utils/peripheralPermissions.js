/**
 * Peripheral permission helpers + comprehensive diagnostics.
 *
 * Two API surfaces:
 *   1. Permission-model APIs (camera/mic/NFC/geo) — silent probe + explicit request
 *      via `requestCameraAccess()` / `requestNfcAccess()` / `requestGeoAccess()`.
 *   2. User-gesture APIs (Serial, HID, USB, Bluetooth) — we report SUPPORT + any
 *      previously-granted devices via `.getDevices()` / `.getPorts()` / `.getDevices()`,
 *      but new pairing still needs `posPeripherals.js` (user click required).
 *
 * Plus a one-shot `detectFullDiagnostics()` for the Diagnostics dialog that
 * folds everything into a single object so the UI can render a clean status grid.
 */

const STORAGE_PREFIX = '5812:peripheral-asked:';

export const markAsked = (kind) => {
  try { localStorage.setItem(STORAGE_PREFIX + kind, '1'); } catch { /* ignore */ }
};
export const wasAsked = (kind) => {
  try { return localStorage.getItem(STORAGE_PREFIX + kind) === '1'; } catch { return false; }
};


/* ============================================================
 * BASIC PERMISSION-MODEL PROBES
 * ============================================================ */

export async function getPermissionState(name) {
  if (typeof navigator === 'undefined' || !navigator.permissions?.query) return 'unknown';
  try {
    const status = await navigator.permissions.query({ name });
    return status.state;
  } catch {
    return 'unknown';
  }
}

export async function detectPeripheralAvailability() {
  const out = {
    cameras: [],
    hasMicrophone: false,
    speakers: 0,
    nfcSupported: typeof window !== 'undefined' && 'NDEFReader' in window,
    serialSupported: typeof navigator !== 'undefined' && 'serial' in navigator,
    hidSupported: typeof navigator !== 'undefined' && 'hid' in navigator,
  };
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) return out;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    for (const d of devices) {
      if (d.kind === 'videoinput') out.cameras.push({ deviceId: d.deviceId, label: d.label || '' });
      if (d.kind === 'audioinput') out.hasMicrophone = true;
      if (d.kind === 'audiooutput') out.speakers += 1;
    }
  } catch { /* ignore */ }
  return out;
}

export async function requestCameraAccess() {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return { state: 'error', error: 'mediaDevices.getUserMedia unavailable' };
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    stream.getTracks().forEach(t => t.stop());
    markAsked('camera');
    return { state: 'granted' };
  } catch (err) {
    markAsked('camera');
    if (err && (err.name === 'NotAllowedError' || err.name === 'SecurityError')) {
      return { state: 'denied', error: err.message };
    }
    return { state: 'error', error: err?.message || String(err) };
  }
}

export async function requestNfcAccess() {
  if (typeof window === 'undefined' || !('NDEFReader' in window)) {
    return { state: 'error', error: 'Web NFC not supported in this browser' };
  }
  try {
    const reader = new window.NDEFReader();
    await reader.scan();
    markAsked('nfc');
    return { state: 'granted', reader };
  } catch (err) {
    markAsked('nfc');
    if (err && err.name === 'NotAllowedError') return { state: 'denied', error: err.message };
    return { state: 'error', error: err?.message || String(err) };
  }
}

export async function requestGeoAccess() {
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    return { state: 'error', error: 'Geolocation unavailable' };
  }
  return await new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => { markAsked('geo'); resolve({ state: 'granted', coords: { lat: pos.coords.latitude, lng: pos.coords.longitude } }); },
      (err) => {
        markAsked('geo');
        const denied = err && err.code === 1;
        resolve({ state: denied ? 'denied' : 'error', error: err?.message });
      },
      { timeout: 8000 },
    );
  });
}


/* ============================================================
 * USER-GESTURE APIs (Web Serial / HID / USB / Bluetooth)
 *
 * These don't have a permission model — devices are listed AFTER the user has
 * paired one in the past via posPeripherals.js. We report (supported, previouslyPaired).
 * ============================================================ */

async function _listSerialPorts() {
  if (typeof navigator === 'undefined' || !('serial' in navigator)) return null;
  try {
    const ports = await navigator.serial.getPorts();
    return ports.map(p => {
      const info = p.getInfo?.() || {};
      return {
        vendorId: info.usbVendorId ? `0x${info.usbVendorId.toString(16).padStart(4, '0')}` : null,
        productId: info.usbProductId ? `0x${info.usbProductId.toString(16).padStart(4, '0')}` : null,
      };
    });
  } catch { return null; }
}

async function _listHIDDevices() {
  if (typeof navigator === 'undefined' || !('hid' in navigator)) return null;
  try {
    const devs = await navigator.hid.getDevices();
    return devs.map(d => ({
      vendorId: d.vendorId ? `0x${d.vendorId.toString(16).padStart(4, '0')}` : null,
      productId: d.productId ? `0x${d.productId.toString(16).padStart(4, '0')}` : null,
      productName: d.productName || '',
    }));
  } catch { return null; }
}

async function _listUSBDevices() {
  if (typeof navigator === 'undefined' || !('usb' in navigator)) return null;
  try {
    const devs = await navigator.usb.getDevices();
    return devs.map(d => ({
      vendorId: d.vendorId ? `0x${d.vendorId.toString(16).padStart(4, '0')}` : null,
      productId: d.productId ? `0x${d.productId.toString(16).padStart(4, '0')}` : null,
      productName: d.productName || '',
      manufacturerName: d.manufacturerName || '',
    }));
  } catch { return null; }
}

async function _listBluetoothDevices() {
  if (typeof navigator === 'undefined' || !navigator.bluetooth?.getDevices) return null;
  try {
    // getDevices() is only available on Chrome ≥85 behind a flag in some versions.
    const devs = await navigator.bluetooth.getDevices();
    return devs.map(d => ({ id: d.id, name: d.name || '' }));
  } catch { return null; }
}


/* ============================================================
 * BATTERY / NETWORK / SCREEN INFO
 * ============================================================ */

async function _getBattery() {
  if (typeof navigator === 'undefined' || !navigator.getBattery) return null;
  try {
    const b = await navigator.getBattery();
    return {
      level: b.level,
      charging: b.charging,
      chargingTime: b.chargingTime,
      dischargingTime: b.dischargingTime,
    };
  } catch { return null; }
}

function _getNetwork() {
  if (typeof navigator === 'undefined') return null;
  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  return {
    online: !!navigator.onLine,
    effectiveType: conn?.effectiveType || null,
    downlinkMbps: conn?.downlink || null,
    rttMs: conn?.rtt || null,
    saveData: !!conn?.saveData,
  };
}

async function _getStorage() {
  if (typeof navigator === 'undefined' || !navigator.storage?.estimate) return null;
  try {
    const est = await navigator.storage.estimate();
    return { quotaMB: Math.round((est.quota || 0) / 1024 / 1024), usedMB: Math.round((est.usage || 0) / 1024 / 1024) };
  } catch { return null; }
}

function _getScreen() {
  if (typeof window === 'undefined') return null;
  return {
    width: window.screen?.width || null,
    height: window.screen?.height || null,
    pixelRatio: window.devicePixelRatio || 1,
    touch: ('ontouchstart' in window) || (navigator.maxTouchPoints || 0) > 0,
    standalone: window.matchMedia?.('(display-mode: standalone)').matches || false,
  };
}


/* ============================================================
 * FULL DIAGNOSTICS — used by the Device Diagnostics dialog
 * ============================================================ */

export async function detectFullDiagnostics() {
  const avail = await detectPeripheralAvailability();
  const [cameraPerm, micPerm, nfcPerm, geoPerm] = await Promise.all([
    getPermissionState('camera'),
    getPermissionState('microphone'),
    getPermissionState('nfc'),
    getPermissionState('geolocation'),
  ]);
  const [serialPorts, hidDevs, usbDevs, btDevs] = await Promise.all([
    _listSerialPorts(),
    _listHIDDevices(),
    _listUSBDevices(),
    _listBluetoothDevices(),
  ]);
  const battery = await _getBattery();
  const network = _getNetwork();
  const storage = await _getStorage();
  const screen = _getScreen();
  const wakeLockSupported = typeof navigator !== 'undefined' && 'wakeLock' in navigator;
  return {
    runtime: {
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
      platform: typeof navigator !== 'undefined' ? (navigator.platform || '') : '',
      languages: typeof navigator !== 'undefined' ? (navigator.languages || []) : [],
      isHttps: typeof window !== 'undefined' ? window.location.protocol === 'https:' : false,
    },
    media: {
      cameras: avail.cameras,
      cameraPermission: cameraPerm,
      microphones: avail.hasMicrophone ? 1 : 0,
      microphonePermission: micPerm,
      speakers: avail.speakers,
    },
    nfc: { supported: avail.nfcSupported, permission: nfcPerm },
    serial: { supported: avail.serialSupported, pairedPorts: serialPorts },
    hid: { supported: avail.hidSupported, pairedDevices: hidDevs },
    usb: { supported: typeof navigator !== 'undefined' && 'usb' in navigator, pairedDevices: usbDevs },
    bluetooth: { supported: typeof navigator !== 'undefined' && 'bluetooth' in navigator, pairedDevices: btDevs },
    geolocation: { supported: typeof navigator !== 'undefined' && !!navigator.geolocation, permission: geoPerm },
    battery,
    network,
    storage,
    screen,
    wakeLockSupported,
    serviceWorker: typeof navigator !== 'undefined' && 'serviceWorker' in navigator,
    clipboard: typeof navigator !== 'undefined' && !!navigator.clipboard?.writeText,
    detectedAt: new Date().toISOString(),
  };
}
