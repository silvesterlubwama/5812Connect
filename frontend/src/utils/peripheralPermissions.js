/**
 * Peripheral permission helpers — covers camera, microphone, geolocation, and Web NFC.
 *
 * Why a separate module from `posPeripherals.js`?
 *   `posPeripherals.js` deals with USER-INITIATED device selection (Web Serial / Web HID /
 *   Web USB / Web Bluetooth) — the browser only exposes those when the user actively
 *   clicks "select device". Cameras / microphones / NFC reading use the standard
 *   permissions model and CAN be probed silently + asked-on-demand. This module owns
 *   that side of the kiosk experience.
 */

const STORAGE_PREFIX = '5812:peripheral-asked:';

export const markAsked = (kind) => {
  try { localStorage.setItem(STORAGE_PREFIX + kind, '1'); } catch { /* ignore */ }
};

export const wasAsked = (kind) => {
  try { return localStorage.getItem(STORAGE_PREFIX + kind) === '1'; } catch { return false; }
};

/** Returns `granted` | `denied` | `prompt` | `unknown` for the named permission. */
export async function getPermissionState(name) {
  if (typeof navigator === 'undefined' || !navigator.permissions?.query) return 'unknown';
  try {
    const status = await navigator.permissions.query({ name });
    return status.state;
  } catch {
    return 'unknown';
  }
}

/** Silently enumerate cameras + detect whether the runtime supports NFC / Web Serial / HID.
 *  Calling enumerateDevices BEFORE permission is granted returns empty `label` strings —
 *  which is fine, we just need the count. */
export async function detectPeripheralAvailability() {
  const out = {
    cameras: [],
    hasMicrophone: false,
    nfcSupported: typeof window !== 'undefined' && 'NDEFReader' in window,
    serialSupported: typeof navigator !== 'undefined' && 'serial' in navigator,
    hidSupported: typeof navigator !== 'undefined' && 'hid' in navigator,
  };
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) {
    return out;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    for (const d of devices) {
      if (d.kind === 'videoinput') out.cameras.push({ deviceId: d.deviceId, label: d.label || '' });
      if (d.kind === 'audioinput') out.hasMicrophone = true;
    }
  } catch {
    // Some browsers throw if mediaDevices is partly blocked; fall through with empty cameras
  }
  return out;
}

/** Triggers the native camera permission prompt and immediately releases the stream.
 *  Returns the resulting state ('granted' | 'denied' | 'error'). */
export async function requestCameraAccess() {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    return { state: 'error', error: 'mediaDevices.getUserMedia unavailable' };
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    // We only needed the prompt — release immediately so consumers can open their own stream later.
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

/** Trigger the Web NFC permission prompt (Chrome Android only). */
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
