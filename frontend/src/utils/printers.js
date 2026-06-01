/**
 * printers.js — convenience helpers around the device-role registry for
 * actually sending bytes to a paired receipt / label printer.
 *
 * Two surfaces:
 *   • printReceiptText(lines) — sends plain-text + cut to a paired
 *     ESC/POS receipt printer. Falls back to `window.print()` if no device.
 *   • printLabelZpl(zpl) — sends a raw ZPL payload to a paired USB label
 *     printer (e.g. Zebra). Returns a `{ printed: true|false, transport }`.
 *
 * Both return without throwing if the device disappears mid-call — the caller
 * gets a friendly false and can choose to toast / log.
 */
import { getDeviceForRole } from './deviceRoles';

// ESC/POS control codes — covers 90% of cheap thermal printers.
const ESC = '\x1b';
const GS = '\x1d';
const INIT = `${ESC}@`;          // initialize printer
const CUT_PARTIAL = `${GS}V\x01`; // partial cut (leave 1mm tab)
const ALIGN_LEFT = `${ESC}a\x00`;
const ALIGN_CENTER = `${ESC}a\x01`;
const BOLD_ON = `${ESC}E\x01`;
const BOLD_OFF = `${ESC}E\x00`;
const FEED_3 = '\n\n\n';

function _encode(s) {
  return new TextEncoder().encode(s);
}

/**
 * Print a plain-text receipt over a paired Serial printer.
 *
 * @param {Array<{text:string, align?:'left'|'center', bold?:boolean}>} lines
 * @returns {Promise<{printed:boolean, transport:string, fallback?:boolean}>}
 */
export async function printReceiptText(lines) {
  const device = await getDeviceForRole('receipt_printer');
  if (!device) {
    // No paired printer — caller should fall back to window.print()
    return { printed: false, transport: 'none', fallback: true };
  }
  try {
    // Serial transport: open at 9600/8N1 (the common default for thermal printers)
    if ('open' in device) {
      // Already-opened ports throw "InvalidStateError" — ignore that
      try {
        await device.open({ baudRate: 9600, dataBits: 8, stopBits: 1, parity: 'none', flowControl: 'none' });
      } catch (e) {
        if (!/already open/i.test(String(e?.message || e))) throw e;
      }
      const writer = device.writable.getWriter();
      try {
        await writer.write(_encode(INIT));
        for (const ln of lines) {
          if (ln.align === 'center') await writer.write(_encode(ALIGN_CENTER));
          else await writer.write(_encode(ALIGN_LEFT));
          if (ln.bold) await writer.write(_encode(BOLD_ON));
          await writer.write(_encode((ln.text ?? '') + '\n'));
          if (ln.bold) await writer.write(_encode(BOLD_OFF));
        }
        await writer.write(_encode(FEED_3));
        await writer.write(_encode(CUT_PARTIAL));
      } finally {
        writer.releaseLock();
      }
      return { printed: true, transport: 'serial' };
    }
    // (HID / USB transports for printers are vendor-specific and out of scope.)
    return { printed: false, transport: 'unsupported', fallback: true };
  } catch (e) {
    console.warn('[printers] receipt print failed:', e?.message || e);
    return { printed: false, transport: 'serial-error', fallback: true };
  }
}

/**
 * Send a raw ZPL string to a paired USB label printer (e.g. Zebra).
 * @param {string} zpl
 * @returns {Promise<{printed:boolean, transport:string, fallback?:boolean}>}
 */
export async function printLabelZpl(zpl) {
  const device = await getDeviceForRole('label_printer');
  if (!device) return { printed: false, transport: 'none', fallback: true };
  try {
    if ('open' in device && 'transferOut' in device) {
      // Web USB path
      await device.open();
      if (device.configuration === null) await device.selectConfiguration(1);
      const iface = device.configuration.interfaces[0];
      await device.claimInterface(iface.interfaceNumber);
      const epOut = iface.alternate.endpoints.find(e => e.direction === 'out');
      await device.transferOut(epOut.endpointNumber, _encode(zpl));
      try { await device.releaseInterface(iface.interfaceNumber); } catch { /* ignore */ }
      return { printed: true, transport: 'usb' };
    }
    return { printed: false, transport: 'unsupported', fallback: true };
  } catch (e) {
    console.warn('[printers] label print failed:', e?.message || e);
    return { printed: false, transport: 'usb-error', fallback: true };
  }
}

/**
 * Build a simple receipt-line array from a sale doc — kept generic so any
 * page (POS, Sales Portal, Marketplace) can call it the same way.
 */
export function buildReceiptLines(sale, opts = {}) {
  const { storeName = '58:12 Sales', currency = 'UGX' } = opts;
  const lines = [];
  lines.push({ text: storeName, align: 'center', bold: true });
  lines.push({ text: '---------------------', align: 'center' });
  if (sale.receipt_number) lines.push({ text: `Receipt #${sale.receipt_number}`, align: 'center' });
  if (sale.created_at) lines.push({ text: (sale.created_at || '').slice(0, 19).replace('T', ' '), align: 'center' });
  lines.push({ text: '', align: 'left' });
  for (const it of (sale.items || sale.line_items || [])) {
    const name = (it.product_name || it.name || '').slice(0, 22);
    const qty = it.qty ?? it.quantity ?? 1;
    const price = (it.line_total ?? (it.price * qty)) || 0;
    lines.push({ text: `${qty}x ${name}`, align: 'left' });
    lines.push({ text: `   ${currency} ${Number(price).toLocaleString()}`, align: 'left' });
  }
  lines.push({ text: '---------------------', align: 'center' });
  if (sale.subtotal != null) lines.push({ text: `Subtotal: ${currency} ${Number(sale.subtotal).toLocaleString()}`, align: 'left' });
  if (sale.tax) lines.push({ text: `Tax:      ${currency} ${Number(sale.tax).toLocaleString()}`, align: 'left' });
  lines.push({ text: `TOTAL:    ${currency} ${Number(sale.total || 0).toLocaleString()}`, align: 'left', bold: true });
  lines.push({ text: '', align: 'left' });
  lines.push({ text: 'Thank you', align: 'center' });
  return lines;
}
