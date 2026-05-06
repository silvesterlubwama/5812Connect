import React, { useEffect, useRef, useState } from 'react';
import { QRCode as QRCodeLogo } from 'react-qrcode-logo';

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
export default function Receipt({ sale, storeSettings = {}, storeName = '58:12 Global Connect' }) {
  const printRef = useRef(null);
  const [autoPaperSize, setAutoPaperSize] = useState(null);

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

  const paperSize = storeSettings.receipt_paper_size || autoPaperSize || '80mm';
  const paperWidth = PAPER_WIDTHS[paperSize] || '80mm';
  const showLogo = storeSettings.receipt_show_logo !== false;
  const showQR = storeSettings.receipt_show_qr !== false;

  if (!sale) return null;

  const receiptNumber = sale.receipt_number || sale.id;
  const trackingUrl = `${window.location.origin}/receipt/${encodeURIComponent(receiptNumber)}`;
  const saleTime = sale.created_at ? new Date(sale.created_at).toLocaleString() : '';
  const currency = sale.items?.[0]?.currency || storeSettings.currency || 'UGX';

  const handlePrint = () => {
    if (!printRef.current) return;
    // Build the print HTML manually so we can re-generate the QR via a CDN script
    // (canvas/SVG inside printRef won't transfer reliably to a new window)
    const w = window.open('', '_blank', 'width=400,height=700');
    const headerHtml = printRef.current.querySelector('.receipt-content')?.innerHTML || '';
    w.document.write(`
      <html>
        <head>
          <title>Receipt ${receiptNumber}</title>
          <script src="https://cdn.jsdelivr.net/npm/qrcode/build/qrcode.min.js"></script>
          <style>
            @page { size: ${paperWidth} auto; margin: 4mm; }
            body { margin: 0; padding: 2mm; font-family: monospace, 'Courier New', Courier; font-size: 11px; width: ${paperWidth}; box-sizing: border-box; }
            .center { text-align: center; }
            .bold { font-weight: 700; }
            hr { border: none; border-top: 1px dashed #888; margin: 4px 0; }
            table { width: 100%; border-collapse: collapse; }
            td { padding: 2px 0; font-size: 10px; }
            .logo { max-width: 60%; height: auto; margin: 0 auto 4px; display: block; }
            .qr-print { margin: 6px auto; text-align: center; }
            #qrCanvas { display: block; margin: 0 auto; }
            .total-row { font-size: 13px; font-weight: 700; }
          </style>
        </head>
        <body>
          ${headerHtml}
          ${showQR ? `<div class="qr-print"><canvas id="qrCanvas"></canvas><div style="font-size:8px;margin-top:2px;color:#555">Scan to verify</div></div>` : ''}
          <hr/>
          <div class="center" style="font-size: 9px">${(storeSettings.receipt_footer || 'Thank you for your purchase!').replace(/[<>&]/g, '')}</div>
          <div class="center" style="font-size: 8px; color: #888; margin-top: 4px">${receiptNumber} · 58:12 Global</div>
          <script>
            window.addEventListener('load', () => {
              if (window.QRCode && document.getElementById('qrCanvas')) {
                QRCode.toCanvas(document.getElementById('qrCanvas'), ${JSON.stringify(trackingUrl)}, { width: 120, margin: 1 }, function(err){ if(!err) setTimeout(()=>{window.focus(); window.print();}, 200); else setTimeout(()=>{window.focus(); window.print();}, 100); });
              } else {
                setTimeout(() => { window.focus(); window.print(); }, 200);
              }
            });
          </script>
        </body>
      </html>
    `);
    w.document.close();
  };

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
        <div style={{ fontSize: 10 }}>
          <div><strong>Receipt:</strong> {receiptNumber}</div>
          <div><strong>Date:</strong> {saleTime}</div>
          <div><strong>Cashier:</strong> {sale.cashier || 'Unknown'}</div>
          <div><strong>Customer:</strong> {sale.customer_name || 'Walk-in'}</div>
          {sale.customer_phone && <div><strong>Phone:</strong> {sale.customer_phone}</div>}
        </div>
        <hr />
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ fontSize: 9, borderBottom: '1px solid #000' }}>
              <td style={{ textAlign: 'left', padding: '2px 0' }}>Item</td>
              <td style={{ textAlign: 'right', padding: '2px 0' }}>Qty</td>
              <td style={{ textAlign: 'right', padding: '2px 0' }}>Unit</td>
              <td style={{ textAlign: 'right', padding: '2px 0' }}>Total</td>
            </tr>
          </thead>
          <tbody>
            {(sale.items || []).map((item, i) => {
              const lineSubtotal = (item.unit_price || 0) * (item.qty || 0);
              const lineDiscount = item.discount_amount || 0;
              const linePackaging = item.packaging_applied || 0;
              const lineTotal = item.line_total != null ? item.line_total : lineSubtotal;
              return (
                <React.Fragment key={i}>
                  <tr style={{ fontSize: 10 }}>
                    <td style={{ padding: '2px 0' }}>
                      {item.name}
                      {item.variant_name && <div style={{ fontSize: 8, color: '#555' }}>{item.variant_name}</div>}
                    </td>
                    <td style={{ textAlign: 'right', padding: '2px 0' }}>{item.qty}</td>
                    <td style={{ textAlign: 'right', padding: '2px 0' }}>{(item.unit_price || 0).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '2px 0' }}>{lineSubtotal.toLocaleString()}</td>
                  </tr>
                  {linePackaging > 0 && (
                    <tr style={{ fontSize: 9, color: '#555' }}>
                      <td colSpan={3} style={{ paddingLeft: 8 }}>+ {item.packaging_label || 'Packaging'}</td>
                      <td style={{ textAlign: 'right' }}>+{linePackaging.toLocaleString()}</td>
                    </tr>
                  )}
                  {lineDiscount > 0 && (
                    <tr style={{ fontSize: 9, color: '#047857' }}>
                      <td colSpan={3} style={{ paddingLeft: 8 }}>− {item.discount_pct}% bulk discount</td>
                      <td style={{ textAlign: 'right' }}>−{lineDiscount.toLocaleString()}</td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        <hr />
        {sale.subtotal != null && sale.subtotal !== sale.total && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
            <span>Subtotal</span>
            <span>{fmt(sale.subtotal, currency)}</span>
          </div>
        )}
        {sale.packaging_total > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
            <span>Packaging</span>
            <span>+{fmt(sale.packaging_total, currency)}</span>
          </div>
        )}
        {sale.tax_amount > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
            <span>Tax</span>
            <span>{fmt(sale.tax_amount, currency)}</span>
          </div>
        )}
        {sale.discount > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#047857' }}>
            <span>Discount</span>
            <span>-{fmt(sale.discount, currency)}</span>
          </div>
        )}
        <div className="total-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, fontWeight: 700, borderTop: '1px dashed #000', paddingTop: 4 }}>
          <span>TOTAL</span>
          <span>{fmt(sale.total, currency)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 4 }}>
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
        >Print Receipt</button>
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
