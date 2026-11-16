import React, { useEffect, useRef, useState } from 'react';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';
import { toast } from 'sonner';
import { escapeHtml as e } from '../utils/htmlEscape';
import { printHtmlDocument } from '../utils/printHtml';
import { printSaleReceipt, isReady as isTillReady, getTillConfig } from '../utils/tillPrinter';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

const fmt = (n, currency = 'UGX') => `${currency} ${(Number(n) || 0).toLocaleString()}`;

const PAPER_WIDTHS = {
  '58mm': '58mm',
  '80mm': '80mm',
  'A5': '148mm',
  'A4': '210mm',
};

/**
 * Receipt — printable sales receipt with logo, QR, traceable number.
 * Auto-generates a tracking QR that points to /receipt/{number}.
 * Auto-detects printer paper width on first render if not specified in storeSettings.
 */
export default function Receipt({ sale, storeSettings = {}, storeName = '58:12 Global Connect', autoPrint = false }) {
  const printRef = useRef(null);
  const [autoPaperSize, setAutoPaperSize] = useState(null);
  const [tillReady, setTillReady] = useState(false);
  const autoPrintedRef = useRef(false);

  useEffect(() => { isTillReady().then(setTillReady); }, []);

  // Auto-print once when the store wants it (hook stays above the early return).
  const printFnRef = useRef(null);
  useEffect(() => {
    if (!autoPrint || !sale || autoPrintedRef.current) return;
    autoPrintedRef.current = true;
    const t = setTimeout(() => printFnRef.current?.(), 500);
    return () => clearTimeout(t);
  }, [autoPrint, sale]);

  // Heuristic: try matchMedia for narrow screen / receipt printer detection.
  // Thermal POS printers commonly resolve to <100mm width when used as default.
  useEffect(() => {
    if (storeSettings.receipt_paper_size || autoPaperSize) return;
    try {
      // Browser will treat thermal printers as ~58–80mm; A4 paper is ~210mm
      if (window.matchMedia('(max-width: 60mm)').matches) setAutoPaperSize('58mm');
      else if (window.matchMedia('(max-width: 90mm)').matches) setAutoPaperSize('80mm');
      else if (window.matchMedia('(max-width: 160mm)').matches) setAutoPaperSize('A5');
      else setAutoPaperSize('80mm'); // sensible default
    } catch (e) {
      setAutoPaperSize('80mm');
    }
  }, [storeSettings.receipt_paper_size, autoPaperSize]);

  // A till told it has a 58 or 80mm roll wins over the shop's saved size: the
  // paper in that printer is a fact, the setting is a guess (iter421).
  const tillPaper = getTillConfig().paper;
  const paperSize = (tillPaper === '58mm' || tillPaper === '80mm')
    ? tillPaper
    : (storeSettings.receipt_paper_size || autoPaperSize || '80mm');
  const paperWidth = PAPER_WIDTHS[paperSize] || '80mm';
  const isRoll = paperSize === '58mm' || paperSize === '80mm';
  const showLogo = storeSettings.receipt_show_logo !== false;
  const showQR = storeSettings.receipt_show_qr !== false;

  if (!sale) return null;

  const receiptNumber = sale.receipt_number || sale.id;
  const trackingUrl = `${window.location.origin}/receipt/${encodeURIComponent(receiptNumber)}`;
  const saleTime = sale.created_at ? new Date(sale.created_at).toLocaleString() : '';
  const currency = sale.items?.[0]?.currency || storeSettings.currency || 'UGX';

  // Straight to the thermal roll when this till has a printer set up; the
  // browser dialog is the fallback so a sale is never stuck (iter411).
  const handlePrint = async () => {
    const till = await printSaleReceipt(sale, storeSettings, { trackingUrl });
    if (till.printed) { toast.success('Receipt sent to the printer'); return; }
    if (till.transport !== 'none') toast.error(`${till.reason || 'Printer not available'} — opening the print dialog`);
    printViaBrowser();
  };

  const printViaBrowser = () => {
    if (!printRef.current) return;
    // Print into a hidden iframe in THIS document. The old version opened a
    // popup (window.open + document.write) and printed from its load handler,
    // which gives a blank page whenever the popup is blocked, the app is inside
    // an iframe, or the browser is Safari/iOS — the "print shows nothing" bug.
    const headerHtml = printRef.current.querySelector('.receipt-content')?.innerHTML || '';
    // Reuse the QR already drawn on screen instead of re-fetching a CDN script
    // (no network, no race with window.print).
    let qrImg = '';
    try {
      // The on-screen QR has the logo drawn into it from another domain, which
      // taints the canvas and makes toDataURL throw — hence the missing QR on
      // print. Copy the plain one rendered off-screen instead.
      const canvas = printRef.current.querySelector('.qr-clean canvas') || printRef.current.querySelector('.qr canvas');
      const dataUrl = canvas?.toDataURL('image/png');
      if (dataUrl) qrImg = `<div class="qr-print"><img src="${dataUrl}" width="120" height="120" alt="" /><div style="font-size:8px;margin-top:2px;color:#555">Scan to verify</div></div>`;
    } catch (err) { console.warn('[receipt] QR copy failed', err); }

    const html = `<!doctype html>
      <html>
        <head>
          <meta charset="utf-8" />
          <title>Receipt ${e(receiptNumber)}</title>
          <style>
            /* The roll IS the page: a @page margin on top of the body width
               pushed the right-hand column off the paper, which is why the
               totals printed clipped (iter421). Margin lives on the body now,
               and nothing is given a fixed width. */
            @page { size: ${paperWidth} auto; margin: 0; }
            html, body { margin: 0; padding: 0; }
            body { padding: ${isRoll ? '2mm 3mm' : '8mm'}; font-family: ${isRoll ? "'Courier New', Courier, monospace" : 'Arial, Helvetica, sans-serif'}; font-size: 12px; line-height: 1.35; box-sizing: border-box; color: #000; background: #fff; }
            * { box-sizing: border-box; }
            .center { text-align: center; }
            .bold { font-weight: 700; }
            hr { border: none; border-top: 1px dashed #888; margin: 5px 0; }
            table { width: 100%; border-collapse: collapse; }
            td { padding: 3px 0; font-size: 11px; }
            .num, .amt, .qty { white-space: nowrap; font-variant-numeric: tabular-nums; }
            .item { margin-bottom: 3px; page-break-inside: avoid; }
            .item-name { word-break: break-word; }
            .item-sum { display: flex; justify-content: space-between; gap: 8px; }
            .qty { padding-left: 10px; }
            .logo { max-width: 55%; height: auto; margin: 0 auto 4px; display: block; }
            .qr-print { margin: 6px auto; text-align: center; }
            .total-row { font-size: 15px; font-weight: 700; }
          </style>
        </head>
        <body>
          ${headerHtml}
          ${qrImg}
          <hr/>
          <div class="center" style="font-size: 9px">${e(storeSettings.receipt_footer || 'Thank you for your purchase!')}</div>
          <div class="center" style="font-size: 8px; color: #888; margin-top: 4px">${e(receiptNumber)} · 58:12 Global</div>
        </body>
      </html>`;

    const frame = printHtmlDocument(html, { autoPrint: false });
    // Fire only once the logo has actually arrived, or the page prints empty.
    const start = Date.now();
    const tryPrint = () => {
      const doc = frame.contentWindow?.document;
      const pending = doc ? [...doc.images].some(img => !img.complete) : false;
      if (pending && Date.now() - start < 4000) return setTimeout(tryPrint, 150);
      try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
      } catch (err) {
        console.warn('[receipt] print failed', err);
        toast.error('Could not open the print dialog — check your browser settings');
      }
      setTimeout(() => { try { window.focus(); } catch { /* ignore */ } }, 0);
    };
    setTimeout(tryPrint, 150);
  };
  printFnRef.current = handlePrint;

  return (
    <div className="space-y-3" data-testid="receipt">
      <div ref={printRef} className="receipt-body space-y-2" style={{ fontFamily: 'monospace, Courier New, Courier', fontSize: 12, maxWidth: paperWidth, margin: '0 auto', padding: '4px 6px', background: '#fff', color: '#000' }}>
        <div className="receipt-content">
        {showLogo && (
          <img src={LOGO_URL} alt="58:12 Global" className="logo" style={{ maxWidth: '60%', height: 'auto', margin: '0 auto 4px', display: 'block' }} onError={(e) => { e.target.style.display = 'none'; }} />
        )}
        <div className="center" style={{ textAlign: 'center' }}>
          <div className="bold" style={{ fontWeight: 700, fontSize: 13 }}>{sale.store_name || storeSettings.store_name || storeName}</div>
          {storeSettings.store_address && <div style={{ fontSize: 9 }}>{storeSettings.store_address}</div>}
          {storeSettings.store_phone && <div style={{ fontSize: 9 }}>{storeSettings.store_phone}</div>}
        </div>
        <hr />
        <div style={{ fontSize: 11 }}>
          <div><strong>Receipt:</strong> {receiptNumber}</div>
          <div><strong>Date:</strong> {saleTime}</div>
          <div><strong>Cashier:</strong> {sale.cashier || 'Unknown'}</div>
          <div><strong>Customer:</strong> {sale.customer_name || 'Walk-in'}</div>
          {sale.customer_phone && <div><strong>Phone:</strong> {sale.customer_phone}</div>}
        </div>
        <hr />
        {/* On a 58/80mm roll there is no room for four columns: the name eats
            the width and Qty/Unit/Total wrap into each other or fall off the
            right edge. Each item takes two lines instead — the name on its own,
            then "2 × 15,000" against the line total (iter421). Sheet paper has
            the width for a proper table, so it keeps one. */}
        {isRoll ? (
          <div className="items">
            {(sale.items || []).map((item, i) => {
              const lineSubtotal = (item.unit_price || 0) * (item.qty || 0);
              const lineDiscount = item.discount_amount || 0;
              const linePackaging = item.packaging_applied || 0;
              return (
                <div key={i} className="item" style={{ marginBottom: 3 }}>
                  <div className="item-name" style={{ fontSize: 11, lineHeight: 1.25, wordBreak: 'break-word' }}>
                    {item.name}
                    {item.variant_name && <span style={{ color: '#555' }}> · {item.variant_name}</span>}
                  </div>
                  <div className="item-sum" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11 }}>
                    <span className="qty" style={{ whiteSpace: 'nowrap', color: '#333', paddingLeft: 10 }}>
                      {`${item.qty} × ${(item.unit_price || 0).toLocaleString()}`}
                    </span>
                    <span className="amt" style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                      {lineSubtotal.toLocaleString()}
                    </span>
                  </div>
                  {linePackaging > 0 && (
                    <div className="item-sum" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 10, color: '#555' }}>
                      <span style={{ paddingLeft: 10 }}>+ {item.packaging_label || 'Packaging'}</span>
                      <span style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>+{linePackaging.toLocaleString()}</span>
                    </div>
                  )}
                  {lineDiscount > 0 && (
                    <div className="item-sum" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 10, color: '#047857' }}>
                      <span style={{ paddingLeft: 10 }}>− {item.discount_pct}% bulk discount</span>
                      <span style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>−{lineDiscount.toLocaleString()}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ fontSize: 10, borderBottom: '1px solid #000' }}>
                <td style={{ textAlign: 'left', padding: '3px 0' }}>Item</td>
                <td className="num" style={{ textAlign: 'right', padding: '3px 6px', whiteSpace: 'nowrap' }}>Qty</td>
                <td className="num" style={{ textAlign: 'right', padding: '3px 6px', whiteSpace: 'nowrap' }}>Unit</td>
                <td className="num" style={{ textAlign: 'right', padding: '3px 0', whiteSpace: 'nowrap' }}>Total</td>
              </tr>
            </thead>
            <tbody>
              {(sale.items || []).map((item, i) => {
                const lineSubtotal = (item.unit_price || 0) * (item.qty || 0);
                const lineDiscount = item.discount_amount || 0;
                const linePackaging = item.packaging_applied || 0;
                return (
                  <React.Fragment key={i}>
                    <tr style={{ fontSize: 11 }}>
                      <td style={{ padding: '3px 0' }}>
                        {item.name}
                        {item.variant_name && <div style={{ fontSize: 9, color: '#555' }}>{item.variant_name}</div>}
                      </td>
                      <td className="num" style={{ textAlign: 'right', padding: '3px 6px', whiteSpace: 'nowrap' }}>{item.qty}</td>
                      <td className="num" style={{ textAlign: 'right', padding: '3px 6px', whiteSpace: 'nowrap' }}>{(item.unit_price || 0).toLocaleString()}</td>
                      <td className="num" style={{ textAlign: 'right', padding: '3px 0', whiteSpace: 'nowrap' }}>{lineSubtotal.toLocaleString()}</td>
                    </tr>
                    {linePackaging > 0 && (
                      <tr style={{ fontSize: 10, color: '#555' }}>
                        <td colSpan={3} style={{ paddingLeft: 8 }}>+ {item.packaging_label || 'Packaging'}</td>
                        <td className="num" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>+{linePackaging.toLocaleString()}</td>
                      </tr>
                    )}
                    {lineDiscount > 0 && (
                      <tr style={{ fontSize: 10, color: '#047857' }}>
                        <td colSpan={3} style={{ paddingLeft: 8 }}>− {item.discount_pct}% bulk discount</td>
                        <td className="num" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>−{lineDiscount.toLocaleString()}</td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
        <hr />
        {sale.subtotal != null && sale.subtotal !== sale.total && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span>Subtotal</span>
            <span>{fmt(sale.subtotal, currency)}</span>
          </div>
        )}
        {sale.packaging_total > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span>Packaging</span>
            <span>+{fmt(sale.packaging_total, currency)}</span>
          </div>
        )}
        {sale.tax_amount > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span>Tax</span>
            <span>{fmt(sale.tax_amount, currency)}</span>
          </div>
        )}
        {sale.discount > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#047857' }}>
            <span>Discount</span>
            <span>-{fmt(sale.discount, currency)}</span>
          </div>
        )}
        <div className="total-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 15, fontWeight: 700, borderTop: '1px dashed #000', paddingTop: 4 }}>
          <span>TOTAL</span>
          <span>{fmt(sale.total, currency)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginTop: 4 }}>
          <span>Paid:</span>
          <span style={{ textTransform: 'capitalize' }}>
            {sale.payment_method || 'cash'}
            {sale.payment_status === 'pending' && <strong style={{ marginLeft: 6, color: '#b45309' }}>· UNPAID</strong>}
          </span>
        </div>
        </div>
        {/* /.receipt-content — body that gets duplicated to print window */}
        {showQR && receiptNumber && (
          <div className="qr" style={{ margin: '6px auto', textAlign: 'center' }}>
            <QRCodeLogo value={trackingUrl} size={120} logoImage={LOGO_URL} logoWidth={22} ecLevel="M" quietZone={4} />
            <div style={{ fontSize: 8, marginTop: 2, color: '#555' }}>Scan to verify</div>
          </div>
        )}
        {/* Logo-free twin, off-screen: the printable copy. A canvas with a
            cross-origin logo painted on it cannot be exported. */}
        {showQR && receiptNumber && (
          <div className="qr-clean" aria-hidden="true" style={{ position: 'absolute', left: -9999, top: 0, width: 0, height: 0, overflow: 'hidden' }}>
            <QRCodeLogo value={trackingUrl} size={120} ecLevel="M" quietZone={4} />
          </div>
        )}
        <hr />
        <div className="center" style={{ textAlign: 'center', fontSize: 9 }}>
          {storeSettings.receipt_footer || 'Thank you for your purchase!'}
        </div>
        <div className="center" style={{ textAlign: 'center', fontSize: 8, color: '#888', marginTop: 4 }}>
          {receiptNumber} · 58:12 Global
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t border-border">
        <button
          onClick={handlePrint}
          data-testid="receipt-print-btn"
          className="flex-1 bg-primary text-primary-foreground rounded-md py-2 text-sm font-medium hover:opacity-90 transition"
        >{tillReady ? 'Print Receipt' : 'Print Receipt'}</button>
        {tillReady && (
          <button
            onClick={printViaBrowser}
            data-testid="receipt-print-dialog-btn"
            className="border border-border rounded-md px-3 py-2 text-sm font-medium hover:bg-accent transition"
            title="Use the browser's print window instead of the till printer"
          >Print dialog</button>
        )}
        {sale.customer_phone && (
          <button
            onClick={() => {
              const msg = encodeURIComponent(`Receipt ${receiptNumber}\nTotal: ${fmt(sale.total, currency)}\nView: ${trackingUrl}`);
              window.open(`https://wa.me/${sale.customer_phone.replace(/\D/g, '')}?text=${msg}`, '_blank');
            }}
            className="bg-green-600 text-white rounded-md px-3 py-2 text-sm font-medium hover:bg-green-700 transition"
            data-testid="receipt-whatsapp-btn"
          >WhatsApp</button>
        )}
      </div>
    </div>
  );
}
