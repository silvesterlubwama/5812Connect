/**
 * Device Role Registry — persistent pairing of paired Web Serial / HID / USB
 * peripherals to functional roles (receipt printer, NFC reader, barcode
 * scanner, scale, etc.).
 *
 * The browser already grants per-origin permission via the picker calls
 * (`navigator.serial.requestPort`, `navigator.hid.requestDevice`,
 * `navigator.usb.requestDevice`). What's MISSING is the layer that says
 * "this paired Epson port is the RECEIPT PRINTER" — that's what this module
 * provides.
 *
 * Storage: localStorage (per origin, per device). Hardware identifiers
 * (vendor_id / product_id / serial_number / product_name) are persisted so on
 * page reload we can match the same physical device to its assigned role
 * without re-prompting the user.
 *
 * Consumers call `getDeviceForRole('receipt_printer')` and get back either:
 *   - the live Serial port / HID device / USB device handle (already opened
 *     by the browser cache when possible), OR
 *   - null if no device is paired to that role.
 *
 * They then talk to the device using the right protocol (ESC/POS over Serial,
 * NDEF over HID, ZPL over USB, …) — that's transport-specific and out of
 * scope here.
 */

const STORAGE_KEY = '5812:device-role-pairings';

// Canonical roles — the source of truth. Adding a new role here makes it
// available everywhere (pairing dialog, lookup helpers, consumers).
export const DEVICE_ROLES = {
  receipt_printer: {
    label: 'Receipt printer',
    description: 'ESC/POS thermal printer for POS receipts (e.g. Epson TM-T20, Star TSP).',
    transports: ['serial', 'usb'],
    hint: 'Plug in via USB → click Pair → pick the printer.',
  },
  label_printer: {
    label: 'Label printer',
    description: 'ZPL / barcode label printer for product / badge labels (e.g. Zebra, Brother QL).',
    transports: ['usb', 'serial'],
    hint: 'Plug in via USB → click Pair → pick the label printer.',
  },
  barcode_scanner: {
    label: 'Barcode scanner',
    description: 'USB / Bluetooth barcode scanner. Most scanners emulate a keyboard ("wedge") and need no pairing — only pair here if your scanner exposes a HID interface and you want native control.',
    transports: ['hid'],
    hint: 'Keyboard-wedge scanners work automatically — no pairing needed.',
  },
  nfc_reader: {
    label: 'NFC reader (USB)',
    description: 'USB NFC reader for desktop / kiosk (e.g. ACR122U, OMNIKEY 5022). On Android Chrome the built-in NFC works without pairing.',
    transports: ['hid', 'usb'],
    hint: 'Plug in the NFC reader → click Pair → pick it from the list.',
  },
  signature_pad: {
    label: 'Signature pad',
    description: 'Customer-signature capture device (e.g. Topaz, Wacom STU).',
    transports: ['hid', 'usb'],
    hint: 'Plug in via USB → click Pair → pick the signature pad.',
  },
  cash_drawer: {
    label: 'Cash drawer',
    description: 'Cash drawer triggered via printer kick-out or direct Serial connection.',
    transports: ['serial'],
    hint: 'Often driven by the receipt printer — pair only if connected separately.',
  },
  customer_display: {
    label: 'Customer display',
    description: 'Pole / line-display showing prices to the customer side of the POS counter.',
    transports: ['serial', 'usb'],
    hint: 'Plug in via USB / Serial → click Pair.',
  },
  scale: {
    label: 'Weighing scale',
    description: 'Bench scale for weight-priced items (e.g. produce, deli).',
    transports: ['serial'],
    hint: 'Plug in via USB-to-Serial → click Pair → pick the scale.',
  },
};

/* ============================================================
 * Storage helpers
 * ============================================================ */

function _read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function _write(map) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(map)); } catch { /* quota / disabled */ }
}

function _deviceFingerprint(transport, raw) {
  // Stable cross-reload identifier: vendor+product+(serial when available).
  if (transport === 'serial') {
    const info = (typeof raw.getInfo === 'function') ? raw.getInfo() : {};
    return `serial:${info.usbVendorId ?? '?'}:${info.usbProductId ?? '?'}`;
  }
  if (transport === 'hid') {
    return `hid:${raw.vendorId}:${raw.productId}:${raw.productName || ''}`;
  }
  if (transport === 'usb') {
    return `usb:${raw.vendorId}:${raw.productId}:${raw.serialNumber || ''}`;
  }
  return `${transport}:unknown`;
}

function _summarise(transport, raw) {
  if (transport === 'serial') {
    const info = (typeof raw.getInfo === 'function') ? raw.getInfo() : {};
    return {
      transport: 'serial',
      vendor_id: info.usbVendorId ?? null,
      product_id: info.usbProductId ?? null,
      product_name: '(serial port)',
      manufacturer: '',
      serial_number: '',
      fingerprint: _deviceFingerprint('serial', raw),
    };
  }
  if (transport === 'hid') {
    return {
      transport: 'hid',
      vendor_id: raw.vendorId,
      product_id: raw.productId,
      product_name: raw.productName || '',
      manufacturer: '',
      serial_number: '',
      fingerprint: _deviceFingerprint('hid', raw),
    };
  }
  if (transport === 'usb') {
    return {
      transport: 'usb',
      vendor_id: raw.vendorId,
      product_id: raw.productId,
      product_name: raw.productName || '',
      manufacturer: raw.manufacturerName || '',
      serial_number: raw.serialNumber || '',
      fingerprint: _deviceFingerprint('usb', raw),
    };
  }
  return null;
}

/* ============================================================
 * Public API
 * ============================================================ */

export function listRoles() {
  return Object.entries(DEVICE_ROLES).map(([key, meta]) => ({ key, ...meta }));
}

export function listPairings() {
  return _read();
}

export function getPairing(role) {
  return _read()[role] || null;
}

/**
 * Open the browser picker for the requested transport and persist the
 * selected device against `role`. Throws if the user cancels or the
 * transport is unsupported by this browser.
 */
export async function pairDeviceForRole(role, transport) {
  if (!DEVICE_ROLES[role]) throw new Error(`Unknown role: ${role}`);
  if (!DEVICE_ROLES[role].transports.includes(transport)) {
    throw new Error(`${role} does not support transport ${transport}`);
  }
  let raw;
  if (transport === 'serial') {
    if (!('serial' in navigator)) throw new Error('Web Serial not supported in this browser');
    raw = await navigator.serial.requestPort();
  } else if (transport === 'hid') {
    if (!('hid' in navigator)) throw new Error('Web HID not supported in this browser');
    const devices = await navigator.hid.requestDevice({ filters: [] });
    raw = devices?.[0];
    if (!raw) throw new Error('No device picked');
  } else if (transport === 'usb') {
    if (!('usb' in navigator)) throw new Error('Web USB not supported in this browser');
    raw = await navigator.usb.requestDevice({ filters: [] });
  } else {
    throw new Error(`Unsupported transport: ${transport}`);
  }
  const summary = _summarise(transport, raw);
  const record = {
    role,
    ...summary,
    paired_at: new Date().toISOString(),
  };
  const map = _read();
  map[role] = record;
  _write(map);
  return record;
}

export function unpairRole(role) {
  const map = _read();
  delete map[role];
  _write(map);
}

/**
 * Look up the live device handle for a role. Returns null if no pairing exists
 * OR the previously-paired device is no longer present (e.g. unplugged).
 * Matches on the persisted fingerprint, so the user does NOT need to re-pair
 * after a browser restart.
 */
export async function getDeviceForRole(role) {
  const rec = _read()[role];
  if (!rec) return null;
  try {
    if (rec.transport === 'serial' && 'serial' in navigator) {
      const ports = await navigator.serial.getPorts();
      const match = ports.find(p => _deviceFingerprint('serial', p) === rec.fingerprint);
      return match || null;
    }
    if (rec.transport === 'hid' && 'hid' in navigator) {
      const devices = await navigator.hid.getDevices();
      return devices.find(d => _deviceFingerprint('hid', d) === rec.fingerprint) || null;
    }
    if (rec.transport === 'usb' && 'usb' in navigator) {
      const devices = await navigator.usb.getDevices();
      return devices.find(d => _deviceFingerprint('usb', d) === rec.fingerprint) || null;
    }
  } catch (e) {
    console.warn(`[device-roles] lookup ${role}:`, e?.message || e);
  }
  return null;
}

/** Convenience: is a given role currently usable (paired + device present)? */
export async function isRoleAvailable(role) {
  const d = await getDeviceForRole(role);
  return !!d;
}

/** For dashboards: each role + its current device handle status. */
export async function probeAllRoles() {
  const map = _read();
  const out = {};
  for (const role of Object.keys(DEVICE_ROLES)) {
    const rec = map[role];
    if (!rec) {
      out[role] = { paired: false, available: false };
      continue;
    }
    const handle = await getDeviceForRole(role);
    out[role] = {
      paired: true,
      available: !!handle,
      pairing: rec,
    };
  }
  return out;
}
