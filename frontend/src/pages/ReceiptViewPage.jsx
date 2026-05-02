import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../services/api';

const fmt = (n, currency = 'UGX') => `${currency} ${(Number(n) || 0).toLocaleString()}`;

/**
 * Public receipt-verification page — shown when someone scans a receipt QR code.
 * No auth required. Routes from /receipt/:receiptNumber.
 */
export default function ReceiptViewPage() {
  const { receiptNumber } = useParams();
  const [sale, setSale] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/sales/by-receipt/${encodeURIComponent(receiptNumber)}`)
      .then(r => setSale(r.data))
      .catch(() => setError('Receipt not found'));
  }, [receiptNumber]);

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="text-center bg-white rounded-xl shadow p-8 max-w-md">
        <p className="text-lg font-bold text-red-600">Receipt Not Found</p>
        <p className="text-sm text-slate-500 mt-2">No record matches "{receiptNumber}".</p>
      </div>
    </div>
  );

  if (!sale) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const currency = sale.items?.[0]?.currency || 'UGX';

  return (
    <div className="min-h-screen bg-slate-100 p-4 flex items-center justify-center" data-testid="receipt-view-page">
      <div className="w-full max-w-md bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="bg-gradient-to-br from-primary to-primary/80 text-primary-foreground p-5">
          <img src="https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1"
               alt="58:12 Global" className="h-10 mb-3 brightness-0 invert" />
          <p className="text-xs opacity-80">Verified Receipt</p>
          <p className="text-2xl font-bold mt-1 font-mono">{sale.receipt_number}</p>
          <p className="text-xs mt-2 opacity-80">{sale.created_at ? new Date(sale.created_at).toLocaleString() : ''}</p>
        </div>
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
            <p className="text-sm font-medium text-green-700">Authentic — sale on record</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 space-y-1 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">Customer</span><span className="font-medium">{sale.customer_name}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Cashier</span><span className="font-medium">{sale.cashier}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Payment</span><span className="font-medium capitalize">{sale.payment_method}</span></div>
          </div>
          <div className="space-y-1 border-t border-slate-200 pt-3">
            {(sale.items || []).map((item, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span>{item.name} <span className="text-slate-400">×{item.qty}</span></span>
                <span>{((item.unit_price || 0) * (item.qty || 0)).toLocaleString()}</span>
              </div>
            ))}
          </div>
          <div className="flex justify-between border-t-2 border-slate-200 pt-3">
            <span className="font-bold">Total</span>
            <span className="font-bold text-primary text-lg">{fmt(sale.total, currency)}</span>
          </div>
          <p className="text-[10px] text-slate-400 text-center pt-2">58:12 Global Connect · This receipt is verified against our central database.</p>
        </div>
      </div>
    </div>
  );
}
