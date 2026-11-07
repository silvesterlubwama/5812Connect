/**
 * tillPrinter.js — send a receipt straight to the thermal printer, no browser
 * print dialog (iter411).
 *
 * Three ways in, because tills differ:
 *   • usb       — Web Serial (desktop Chrome/Edge) or WebUSB (Android Chrome)
 *   • bluetooth — Web Bluetooth GATT, the usual thermal-printer write services
 *   • network   — the printer's own IP on port 9100; browsers cannot open a raw
 *                 socket, so the bytes go via the server (/api/pos/print-raw)
 *
 * Nothing here throws at the caller: every path returns
 * { printed, transport, reason } so the POS can fall back to the print dialog.
 * On iPhone/iPad none of these exist — capabilities() says so and the caller
 * keeps using the dialog.
 */
import api from '../services/api';
import { printHtmlDocument } from './printHtml';
import { pairDeviceForRole, getDeviceForRole } from './deviceRoles';

const CONFIG_KEY = '5812:till-printer';

// ---------------------------------------------------------------- ESC/POS
const ESC = 0x1b;
const GS = 0x1d;
const enc = new TextEncoder();

function bytes(...parts) {
  const chunks = parts.map(p => (typeof p === 'string' ? enc.encode(p) : Uint8Array.from(p)));
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  chunks.forEach(c => { out.set(c, at); at += c.length; });
  return out;
}

const INIT = [ESC, 0x40];
const ALIGN_LEFT = [ESC, 0x61, 0x00];
const ALIGN_CENTER = [ESC, 0x61, 0x01];
const BOLD_ON = [ESC, 0x45, 0x01];
const BOLD_OFF = [ESC, 0x45, 0x00];
const DOUBLE_ON = [GS, 0x21, 0x11];
const DOUBLE_OFF = [GS, 0x21, 0x00];
const CUT = [GS, 0x56, 0x01];
const DRAWER_KICK = [ESC, 0x70, 0x00, 0x32, 0xc8];   // ESC p 0 25 250

/** Native ESC/POS QR (GS ( k). Printers that don't know it ignore it. */
function qrBytes(text) {
  const data = enc.encode(text);
  const len = data.length + 3;
  return bytes(
    [GS, 0x28, 0x6b, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00],       // model 2
    [GS, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x43, 0x06],             // module size 6
    [GS, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x45, 0x31],             // error correction M
    [GS, 0x28, 0x6b, len & 0xff, (len >> 8) & 0xff, 0x31, 0x50, 0x30], data,
    [GS, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x51, 0x30],             // print
  );
}

/** "Item            2  4,000" — right-aligned amount on a fixed-width roll. */
function row(left, right, width) {
  const l = String(left ?? '');
  const r = String(right ?? '');
  if (l.length + r.length + 1 > width) {
    return `${l.slice(0, Math.max(0, width - r.length - 1))} ${r}\n`;
  }
  return `${l}${' '.repeat(width - l.length - r.length)}${r}\n`;
}

const money = (n, currency) => `${currency} ${Number(n || 0).toLocaleString()}`;

/**
 * Turn a sale into ESC/POS bytes.
 * @param {object} sale  the saved sale (receipt_number, items, total…)
 * @param {object} opts  { storeName, currency, columns, footer, showQr, trackingUrl }
 */
export function buildReceiptBytes(sale, opts = {}) {
  const {
    storeName = '58:12 Global Connect',
    currency = 'UGX',
    columns = 48,
    footer = 'Thank you for your purchase!',
    showQr = true,
    trackingUrl = '',
  } = opts;
  const items = sale.items || sale.line_items || [];
  const parts = [bytes(INIT, ALIGN_CENTER, BOLD_ON, DOUBLE_ON, `${storeName}\n`, DOUBLE_OFF, BOLD_OFF)];
  const push = (...p) => parts.push(bytes(...p));

  if (sale.receipt_number) push(`${sale.receipt_number}\n`);
  push(ALIGN_LEFT, '-'.repeat(columns) + '\n');
  const when = (sale.created_at || new Date().toISOString()).slice(0, 19).replace('T', ' ');
  push(row('Date', when, columns));
  if (sale.cashier) push(row('Served by', String(sale.cashier).slice(0, 20), columns));
  if (sale.customer_name) push(row('Customer', String(sale.customer_name).slice(0, 20), columns));
  push('-'.repeat(columns) + '\n');

  items.forEach(it => {
    const name = String(it.product_name || it.name || 'Item');
    const qty = it.qty ?? it.quantity ?? 1;
    const line = it.line_total ?? (Number(it.price || 0) * qty);
    push(`${name.slice(0, columns)}\n`);
    push(row(`  ${qty} x ${Number(it.price || 0).toLocaleString()}`, Number(line).toLocaleString(), columns));
  });

  push('-'.repeat(columns) + '\n');
  if (sale.subtotal != null) push(row('Subtotal', money(sale.subtotal, currency), columns));
  if (sale.discount) push(row('Discount', `-${money(sale.discount, currency)}`, columns));
  if (sale.tax) push(row('Tax', money(sale.tax, currency), columns));
  push(BOLD_ON, DOUBLE_ON, row('TOTAL', money(sale.total, currency), Math.floor(columns / 2)), DOUBLE_OFF, BOLD_OFF);
  if (sale.payment_method) push(row('Paid by', String(sale.payment_method).toUpperCase(), columns));
  if (sale.amount_tendered) push(row('Cash', money(sale.amount_tendered, currency), columns));
  if (sale.change_due) push(row('Change', money(sale.change_due, currency), columns));

  push('\n', ALIGN_CENTER);
  if (showQr && trackingUrl) {
    parts.push(qrBytes(trackingUrl));
    push('Scan to verify\n');
  }
  push(`${footer}\n`, '\n\n\n', CUT);
  return bytes(...parts.map(p => p));
}

// ---------------------------------------------------------------- config
const DEFAULTS = {
  connection: 'none',          // none | usb | bluetooth | network
  paper: '80mm',               // 80mm → 48 cols, 58mm → 32 cols
  openDrawerOnCash: true,
  network: { host: '', port: 9100 },
  bluetoothName: '',
};

export function getTillConfig() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}') };
  } catch { return { ...DEFAULTS }; }
}

export function saveTillConfig(patch) {
  const next = { ...getTillConfig(), ...patch };
  try { localStorage.setItem(CONFIG_KEY, JSON.stringify(next)); } catch { /* private mode */ }
  return next;
}

export const columnsFor = (paper) => (paper === '58mm' ? 32 : 48);

/** What this particular browser can actually do. */
export function capabilities() {
  const nav = typeof navigator === 'undefined' ? {} : navigator;
  return {
    usbSerial: !!nav.serial,
    usbRaw: !!nav.usb,
    bluetooth: !!nav.bluetooth,
    network: true,                        // goes through the server
    anyDirect: !!(nav.serial || nav.usb || nav.bluetooth),
  };
}

/** True when the configured connection is ready to receive bytes right now. */
export async function isReady() {
  const cfg = getTillConfig();
  if (cfg.connection === 'network') return !!cfg.network?.host;
  if (cfg.connection === 'bluetooth') return !!btChar || !!cfg.bluetoothName;
  if (cfg.connection === 'usb') return !!(await getDeviceForRole('receipt_printer'));
  return false;
}

// ---------------------------------------------------------------- transports
async function sendUsb(payload) {
  const device = await getDeviceForRole('receipt_printer');
  if (!device) return { printed: false, transport: 'usb', reason: 'No printer paired on this computer' };

  if (device.writable !== undefined || 'getInfo' in device) {
    // Web Serial port
    try {
      try {
        await device.open({ baudRate: 9600, dataBits: 8, stopBits: 1, parity: 'none', flowControl: 'none' });
      } catch (e) {
        if (!/already open/i.test(String(e?.message || e))) throw e;
      }
      const writer = device.writable.getWriter();
      try { await writer.write(payload); } finally { writer.releaseLock(); }
      return { printed: true, transport: 'usb-serial' };
    } catch (e) {
      return { printed: false, transport: 'usb-serial', reason: e?.message || String(e) };
    }
  }

  // WebUSB printer (Android Chrome and desktop alike)
  try {
    await device.open();
    if (device.configuration === null) await device.selectConfiguration(1);
    const iface = device.configuration.interfaces[0];
    await device.claimInterface(iface.interfaceNumber);
    const out = iface.alternate.endpoints.find(e => e.direction === 'out');
    await device.transferOut(out.endpointNumber, payload);
    try { await device.releaseInterface(iface.interfaceNumber); } catch { /* ignore */ }
    return { printed: true, transport: 'usb' };
  } catch (e) {
    return { printed: false, transport: 'usb', reason: e?.message || String(e) };
  }
}

// Thermal printers expose one of these write services over BLE.
const BT_SERVICES = [
  0xffe0,
  0x18f0,
  '000018f0-0000-1000-8000-00805f9b34fb',
  '49535343-fe7d-4ae5-8fa9-9fafd205e455',
  'e7810a71-73ae-499d-8c15-faa9aef0c3f2',
];
let btChar = null;      // cached GATT characteristic for this session

export async function connectBluetooth() {
  if (!navigator.bluetooth) return { ok: false, reason: 'This browser cannot use Bluetooth printers' };
  try {
    const device = await navigator.bluetooth.requestDevice({
      filters: BT_SERVICES.map(s => ({ services: [s] })),
      optionalServices: BT_SERVICES,
    });
    btChar = await _btCharacteristic(device);
    saveTillConfig({ connection: 'bluetooth', bluetoothName: device.name || 'Bluetooth printer' });
    return { ok: true, name: device.name || 'Bluetooth printer' };
  } catch (e) {
    return { ok: false, reason: e?.message || String(e) };
  }
}

async function _btCharacteristic(device) {
  const server = await device.gatt.connect();
  for (const svc of BT_SERVICES) {
    try {
      const service = await server.getPrimaryService(svc);
      const chars = await service.getCharacteristics();
      const writable = chars.find(c => c.properties.write || c.properties.writeWithoutResponse);
      if (writable) return writable;
    } catch { /* try the next service */ }
  }
  throw new Error('No writable service on this printer');
}

async function sendBluetooth(payload) {
  try {
    if (!btChar || !btChar.service?.device?.gatt?.connected) {
      // Reconnect silently if the browser still remembers the device.
      const known = navigator.bluetooth?.getDevices ? await navigator.bluetooth.getDevices() : [];
      const cfg = getTillConfig();
      const device = known.find(d => d.name === cfg.bluetoothName) || known[0];
      if (!device) return { printed: false, transport: 'bluetooth', reason: 'Printer not connected — tap Connect printer' };
      btChar = await _btCharacteristic(device);
    }
    // BLE writes cap out around 20 bytes per packet on cheap printers.
    for (let i = 0; i < payload.length; i += 180) {
      const chunk = payload.slice(i, i + 180);
      if (btChar.properties.writeWithoutResponse) await btChar.writeValueWithoutResponse(chunk);
      else await btChar.writeValue(chunk);
    }
    return { printed: true, transport: 'bluetooth' };
  } catch (e) {
    btChar = null;
    return { printed: false, transport: 'bluetooth', reason: e?.message || String(e) };
  }
}

async function sendNetwork(payload) {
  const { network } = getTillConfig();
  if (!network?.host) return { printed: false, transport: 'network', reason: 'No printer address set' };
  let binary = '';
  payload.forEach(b => { binary += String.fromCharCode(b); });
  try {
    const r = await api.post('/pos/print-raw', {
      host: network.host,
      port: Number(network.port) || 9100,
      data_b64: btoa(binary),
    });
    return { printed: !!r.data?.sent, transport: 'network', reason: r.data?.sent ? undefined : 'Printer did not accept the job' };
  } catch (e) {
    // Only trust the server's wording for a rejected job (400/413). A 502/504
    // can come from the proxy in front of the server, whose text is about
    // itself ("the origin web server did not respond"), not about the printer.
    const status = e.response?.status;
    const detail = e.response?.data?.detail;
    const where = `${network.host}:${Number(network.port) || 9100}`;
    let reason;
    if ((status === 400 || status === 413) && typeof detail === 'string') reason = detail;
    else if (status === 504) reason = `The printer at ${where} did not answer — check it is switched on and on the same network as the server`;
    else reason = `Could not reach the printer at ${where}`;
    return { printed: false, transport: 'network', reason };
  }
}

/** Route raw bytes to whichever printer this till is set up with. */
export async function sendBytes(payload) {
  const cfg = getTillConfig();
  if (cfg.connection === 'usb') return sendUsb(payload);
  if (cfg.connection === 'bluetooth') return sendBluetooth(payload);
  if (cfg.connection === 'network') return sendNetwork(payload);
  return { printed: false, transport: 'none', reason: 'No till printer set up' };
}

export async function connectUsb() {
  const caps = capabilities();
  const transport = caps.usbSerial ? 'serial' : (caps.usbRaw ? 'usb' : null);
  if (!transport) return { ok: false, reason: 'This browser cannot talk to a USB printer' };
  try {
    const res = await pairDeviceForRole('receipt_printer', transport);
    if (!res) return { ok: false, reason: 'No printer chosen' };
    saveTillConfig({ connection: 'usb' });
    return { ok: true, name: res.label || res.name || 'USB printer' };
  } catch (e) {
    return { ok: false, reason: /cancel|no port|no device/i.test(String(e?.message)) ? 'No printer chosen' : (e?.message || String(e)) };
  }
}

/**
 * Print a sale. Returns printed:false (with a reason) when the caller should
 * fall back to the browser print dialog.
 */
export async function printSaleReceipt(sale, storeSettings = {}, extra = {}) {
  const cfg = getTillConfig();
  if (cfg.connection === 'none') return { printed: false, transport: 'none', reason: 'No till printer set up' };
  const payload = buildReceiptBytes(sale, {
    storeName: storeSettings.store_name || extra.storeName || '58:12 Global Connect',
    currency: storeSettings.currency || 'UGX',
    columns: columnsFor(cfg.paper),
    footer: storeSettings.receipt_footer || 'Thank you for your purchase!',
    showQr: storeSettings.receipt_show_qr !== false,
    trackingUrl: extra.trackingUrl || (sale.receipt_number ? `${window.location.origin}/receipt/${sale.receipt_number}` : ''),
  });
  return sendBytes(payload);
}

/** ESC/POS drawer pulse down the same cable as the receipt. */
export async function openDrawer() {
  return sendBytes(bytes(DRAWER_KICK));
}

/**
 * Refund / void slip — the customer's paper trail for money given back
 * (iter414). Deliberately says REFUND in big letters and carries the original
 * receipt number so it can never be mistaken for a sale.
 */
export function buildRefundBytes(sale, opts = {}) {
  const {
    storeName = '58:12 Global Connect', currency = 'UGX', columns = 48,
    voidedBy = '', reason = '', showQr = true, trackingUrl = '',
  } = opts;
  const items = sale.items || sale.line_items || [];
  const parts = [bytes(
    INIT, ALIGN_CENTER, BOLD_ON, DOUBLE_ON, 'REFUND\n', DOUBLE_OFF,
    `${storeName}\n`, BOLD_OFF,
  )];
  const push = (...p) => parts.push(bytes(...p));

  push(ALIGN_LEFT, '='.repeat(columns) + '\n');
  if (sale.receipt_number) push(row('Original receipt', sale.receipt_number, columns));
  if (sale.created_at) push(row('Sold on', String(sale.created_at).slice(0, 16).replace('T', ' '), columns));
  push(row('Refunded', new Date().toISOString().slice(0, 16).replace('T', ' '), columns));
  if (voidedBy) push(row('Authorised by', String(voidedBy).slice(0, 22), columns));
  if (sale.customer_name) push(row('Customer', String(sale.customer_name).slice(0, 22), columns));
  push('='.repeat(columns) + '\n', 'ITEMS RETURNED\n');

  items.forEach(it => {
    const qty = it.qty ?? it.quantity ?? 1;
    const line = it.line_total ?? (Number(it.price || 0) * qty);
    push(`${String(it.product_name || it.name || 'Item').slice(0, columns)}\n`);
    push(row(`  ${qty} x ${Number(it.price || 0).toLocaleString()}`, Number(line).toLocaleString(), columns));
  });

  push('-'.repeat(columns) + '\n');
  push(BOLD_ON, DOUBLE_ON, row('REFUNDED', money(sale.total, currency), Math.floor(columns / 2)), DOUBLE_OFF, BOLD_OFF);
  if (sale.payment_method) push(row('Paid originally by', String(sale.payment_method).toUpperCase(), columns));
  if (reason) push(`\nReason: ${reason}\n`);
  push('\n', ALIGN_CENTER);
  if (showQr && trackingUrl) { parts.push(qrBytes(trackingUrl)); push('Scan to verify\n'); }
  push('Stock returned. No further payment is due.\n', '\n\n\n', CUT);
  return bytes(...parts);
}

/** End-of-day takings slip for one till. */
export function buildZReportBytes(report, opts = {}) {
  const { storeName = '58:12 Global Connect', currency = 'UGX', columns = 48 } = opts;
  const parts = [bytes(
    INIT, ALIGN_CENTER, BOLD_ON, DOUBLE_ON, 'Z-REPORT\n', DOUBLE_OFF,
    `${storeName}\n`, BOLD_OFF,
  )];
  const push = (...p) => parts.push(bytes(...p));
  push(`${report.store_name || ''}\n`, ALIGN_LEFT, '='.repeat(columns) + '\n');
  push(row('Date', report.date, columns));
  push(row('Printed', new Date().toLocaleString(), columns));
  if (report.generated_by) push(row('By', String(report.generated_by).slice(0, 22), columns));
  push('='.repeat(columns) + '\n');
  push(row('Sales', String(report.sales_count), columns));
  push(row('Items sold', String(report.items_sold), columns));
  push(row('Gross takings', money(report.gross, currency), columns));
  if (report.discounts) push(row('Discounts', `-${money(report.discounts, currency)}`, columns));
  if (report.tax) push(row('Tax', money(report.tax, currency), columns));
  push(BOLD_ON, row('NET TAKINGS', money(report.net, currency), columns), BOLD_OFF);
  push(row('Average sale', money(report.average_sale, currency), columns));
  push('-'.repeat(columns) + '\n', 'BY PAYMENT METHOD\n');
  (report.by_method || []).forEach(m => push(row(`  ${m.method} (${m.count})`, money(m.total, currency), columns)));
  if ((report.by_cashier || []).length) {
    push('-'.repeat(columns) + '\n', 'BY CASHIER\n');
    report.by_cashier.forEach(c => push(row(`  ${String(c.cashier).slice(0, 20)} (${c.count})`, money(c.total, currency), columns)));
  }
  if (report.voided_count) {
    push('-'.repeat(columns) + '\n');
    push(row(`Voided / refunded (${report.voided_count})`, money(report.voided_total, currency), columns));
  }
  const d = report.drawer || {};
  if (d.shifts) {
    push('-'.repeat(columns) + '\n', 'CASH DRAWER\n');
    push(row('  Opening float', money(d.opening_cash, currency), columns));
    push(row('  Cash drops', money(d.cash_drops, currency), columns));
    push(row('  Expected', money(d.expected_cash, currency), columns));
    push(row('  Counted', money(d.counted_cash, currency), columns));
    push(BOLD_ON, row('  Over / short', money(d.variance, currency), columns), BOLD_OFF);
  }
  push('-'.repeat(columns) + '\n');
  if (report.first_receipt) push(row('First receipt', report.first_receipt, columns));
  if (report.last_receipt) push(row('Last receipt', report.last_receipt, columns));
  push('\n', ALIGN_CENTER, 'End of day\n', '\n\n\n', CUT);
  return bytes(...parts);
}

export async function printRefundSlip(sale, storeSettings = {}, extra = {}) {
  const cfg = getTillConfig();
  if (cfg.connection === 'none') return { printed: false, transport: 'none', reason: 'No till printer set up' };
  return sendBytes(buildRefundBytes(sale, {
    storeName: storeSettings.store_name || '58:12 Global Connect',
    currency: storeSettings.currency || 'UGX',
    columns: columnsFor(cfg.paper),
    showQr: storeSettings.receipt_show_qr !== false,
    trackingUrl: extra.trackingUrl || (sale.receipt_number ? `${window.location.origin}/receipt/${sale.receipt_number}` : ''),
    voidedBy: extra.voidedBy || '',
    reason: extra.reason || '',
  }));
}

export async function printZReport(report, storeSettings = {}) {
  const cfg = getTillConfig();
  if (cfg.connection === 'none') return { printed: false, transport: 'none', reason: 'No till printer set up' };
  return sendBytes(buildZReportBytes(report, {
    storeName: storeSettings.store_name || '58:12 Global Connect',
    currency: storeSettings.currency || 'UGX',
    columns: columnsFor(cfg.paper),
  }));
}

/**
 * No thermal printer on this device (or it refused): put the same slip through
 * the browser's print dialog so the customer still gets paper.
 */
export function printSlipFallback(title, textLines) {
  const esc = (s) => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  printHtmlDocument(`<!doctype html><html><head><meta charset="utf-8"/><title>${esc(title)}</title>
    <style>
      @page { size: 80mm auto; margin: 4mm; }
      body { font-family: monospace, 'Courier New', Courier; font-size: 11px; width: 80mm; margin: 0; padding: 2mm; color: #000; }
      pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
    </style></head>
    <body><pre>${esc(textLines.join('\n'))}</pre></body></html>`);
}

/** The same two slips as plain text, for the fallback above. */
export function refundSlipText(sale, opts = {}) {
  return _decode(buildRefundBytes(sale, { ...opts, showQr: false }));
}
export function zReportText(report, opts = {}) {
  return _decode(buildZReportBytes(report, opts));
}

/** Strip the ESC/POS control bytes back out so the text can be shown or printed. */
function _decode(payload) {
  const text = new TextDecoder().decode(payload);
  /* eslint-disable no-control-regex */
  return text
    .replace(/\x1b@/g, '')
    .replace(/\x1b[aE!][\s\S]/g, '')     // ESC a n / ESC E n / ESC ! n
    .replace(/\x1d[!V][\s\S]/g, '')      // GS ! n / GS V n
    .replace(/\x1bp[\s\S]{3}/g, '')      // drawer kick
    .replace(/[\x00-\x09\x0b-\x1f]/g, '')
    .split('\n');
  /* eslint-enable no-control-regex */
}

export async function testPrint() {
  const cfg = getTillConfig();
  const cols = columnsFor(cfg.paper);
  const payload = bytes(
    INIT, ALIGN_CENTER, BOLD_ON, DOUBLE_ON, 'TEST RECEIPT\n', DOUBLE_OFF, BOLD_OFF,
    '58:12 Global Connect\n', ALIGN_LEFT, '-'.repeat(cols) + '\n',
    row('Paper', cfg.paper, cols), row('Connection', cfg.connection, cols),
    row('Printed', new Date().toLocaleString(), cols),
    '-'.repeat(cols) + '\n', ALIGN_CENTER, 'If you can read this,\nthe till printer works.\n',
    '\n\n\n', CUT,
  );
  return sendBytes(payload);
}
