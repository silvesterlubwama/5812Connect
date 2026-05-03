import React, { useRef } from 'react';

const LOGO_URL = 'https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1';

const fmt = (n, c = 'UGX') => `${c} ${(Number(n) || 0).toLocaleString()}`;

/**
 * InvoicePrintable — printable invoice with 58:12 logo header.
 * Supports A4 (default) and 80mm thermal modes.
 */
export default function InvoicePrintable({ invoice, mode = 'a4', orgName = '58:12 Global Connect' }) {
  const printRef = useRef(null);

  if (!invoice) return null;
  const total = invoice.total || 0;
  const subtotal = invoice.subtotal != null ? invoice.subtotal : (invoice.items || []).reduce((s, i) => s + (i.qty || 0) * (i.unit_price || 0), 0);
  const isDraft = invoice.status === 'draft';
  const isSent = invoice.status === 'sent';
  const isConverted = invoice.status === 'converted';
  const currency = invoice.items?.[0]?.currency || 'UGX';

  const handlePrint = () => {
    const area = printRef.current?.innerHTML;
    if (!area) return;
    const isThermal = mode === 'thermal';
    const w = window.open('', '_blank', `width=${isThermal ? 400 : 900},height=900`);
    w.document.write(`
      <html>
        <head>
          <title>Invoice ${invoice.invoice_number}</title>
          <style>
            @page { size: ${isThermal ? '80mm auto' : 'A4'}; margin: ${isThermal ? '4mm' : '15mm'}; }
            body { font-family: ${isThermal ? 'monospace, Courier' : 'Arial, sans-serif'}; margin: 0; padding: 0; color: #1a1a2e; }
            .invoice-body { ${isThermal ? 'width: 72mm; font-size: 11px;' : 'max-width: 180mm; font-size: 13px;'} }
            h1 { color: #1a1a2e; margin: 0; font-size: ${isThermal ? '14px' : '24px'}; }
            .logo { max-width: ${isThermal ? '60%' : '180px'}; height: auto; }
            table { width: 100%; border-collapse: collapse; margin-top: 12px; }
            th, td { padding: 6px 8px; text-align: left; }
            th { border-bottom: 2px solid #1a1a2e; font-size: ${isThermal ? '10px' : '12px'}; }
            tbody tr { border-bottom: 1px dotted #ccc; }
            .right { text-align: right; }
            .totals { margin-top: 12px; }
            .totals tr td { padding: 4px 8px; }
            .grand { font-weight: 700; border-top: 2px solid #1a1a2e; font-size: ${isThermal ? '14px' : '18px'}; color: #48a9c5; }
            .stamp { display: inline-block; padding: 4px 12px; border: 2px solid; border-radius: 4px; font-weight: 700; text-transform: uppercase; }
            .stamp.draft { color: #b45309; border-color: #b45309; }
            .stamp.sent { color: #2563eb; border-color: #2563eb; }
            .stamp.converted { color: #047857; border-color: #047857; }
          </style>
        </head>
        <body>${area}</body>
      </html>
    `);
    w.document.close();
    setTimeout(() => { w.focus(); w.print(); }, 400);
  };

  return (
    <div className="space-y-3" data-testid="invoice-printable">
      <div ref={printRef} className="invoice-body bg-white p-6 rounded-md border border-border" style={{ color: '#1a1a2e' }}>
        {/* Header */}
        <div className="flex justify-between items-start gap-4 pb-4 border-b-2" style={{ borderColor: '#1a1a2e' }}>
          <div>
            <img src={LOGO_URL} alt="58:12 Global" className="logo" style={{ maxWidth: 180 }} onError={(e) => { e.target.style.display = 'none'; }} />
            <p className="text-xs mt-2 text-muted-foreground">{orgName}</p>
          </div>
          <div className="text-right">
            <h1 className="m-0">INVOICE</h1>
            <p className="font-mono text-sm mt-1" style={{ color: '#48a9c5' }}>{invoice.invoice_number}</p>
            <span className={`stamp ${invoice.status}`}>{invoice.status}</span>
            {invoice.receipt_number && <p className="text-xs mt-2">→ Receipt {invoice.receipt_number}</p>}
          </div>
        </div>

        {/* Customer + meta */}
        <div className="grid grid-cols-2 gap-4 mt-4">
          <div>
            <p className="text-xs uppercase tracking-wider opacity-60">Bill To</p>
            <p className="font-semibold mt-1">{invoice.customer_name || 'Walk-in Customer'}</p>
            {invoice.customer_phone && <p className="text-xs">{invoice.customer_phone}</p>}
            {invoice.customer_email && <p className="text-xs">{invoice.customer_email}</p>}
          </div>
          <div className="text-right text-xs space-y-0.5">
            <div><span className="opacity-60">Issued:</span> {invoice.created_at?.slice(0, 10)}</div>
            {invoice.due_date && <div><span className="opacity-60">Due:</span> {invoice.due_date}</div>}
            <div><span className="opacity-60">Issued by:</span> {invoice.issued_by_name}</div>
            <div><span className="opacity-60">Payment:</span> <span className="capitalize">{invoice.payment_method}</span></div>
          </div>
        </div>

        {/* Items */}
        <table className="w-full mt-4">
          <thead>
            <tr>
              <th>Item</th>
              <th className="right">Qty</th>
              <th className="right">Unit</th>
              <th className="right">Total</th>
            </tr>
          </thead>
          <tbody>
            {(invoice.items || []).map((item, i) => (
              <tr key={i}>
                <td>
                  {item.name}
                  {item.variant_name && <div className="text-xs opacity-60">{item.variant_name}</div>}
                </td>
                <td className="right">{item.qty}</td>
                <td className="right">{(item.unit_price || 0).toLocaleString()}</td>
                <td className="right">{((item.unit_price || 0) * (item.qty || 0)).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Totals */}
        <table className="totals" style={{ marginLeft: 'auto', maxWidth: 280 }}>
          <tbody>
            <tr><td>Subtotal</td><td className="right">{fmt(subtotal, currency)}</td></tr>
            {invoice.discount > 0 && <tr><td>Discount</td><td className="right">-{fmt(invoice.discount, currency)}</td></tr>}
            {invoice.tax_amount > 0 && <tr><td>Tax</td><td className="right">{fmt(invoice.tax_amount, currency)}</td></tr>}
            <tr className="grand"><td>TOTAL</td><td className="right">{fmt(total, currency)}</td></tr>
          </tbody>
        </table>

        {invoice.notes && (
          <div className="mt-4 p-3 rounded-md" style={{ background: '#f8f9fa' }}>
            <p className="text-xs uppercase tracking-wider opacity-60">Notes</p>
            <p className="text-sm mt-1 whitespace-pre-wrap">{invoice.notes}</p>
          </div>
        )}

        <div className="mt-6 pt-3 border-t text-center text-xs opacity-60">
          Thank you for your business · {orgName}
        </div>
      </div>

      <div className="flex gap-2 pt-2 border-t border-border">
        <button onClick={handlePrint} data-testid="invoice-print-btn"
          className="flex-1 bg-primary text-primary-foreground rounded-md py-2 text-sm font-medium hover:opacity-90 transition">
          Print Invoice ({mode === 'thermal' ? '80mm' : 'A4'})
        </button>
        {invoice.customer_phone && !isConverted && (
          <button onClick={() => {
            const url = `${window.location.origin}/invoices/${invoice.invoice_number}`;
            const msg = encodeURIComponent(`Invoice ${invoice.invoice_number}\nTotal: ${fmt(total, currency)}\nDue: ${invoice.due_date || 'on receipt'}\n${url}`);
            window.open(`https://wa.me/${invoice.customer_phone.replace(/\D/g, '')}?text=${msg}`, '_blank');
          }} className="bg-green-600 text-white rounded-md px-3 py-2 text-sm font-medium hover:bg-green-700 transition" data-testid="invoice-whatsapp-btn">
            Send WhatsApp
          </button>
        )}
      </div>
    </div>
  );
}
