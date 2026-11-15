import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ChefHat, Clock, Monitor, ShoppingCart } from 'lucide-react';
import { screensApi } from '../services/api';

/**
 * A screen on the wall. No sign-in: the link given out by the store IS the
 * credential, so a cook sees the board and a customer sees the till without
 * anybody typing a password (iter420).
 */
const minutesSince = (iso) => {
  const t = Date.parse(iso || '');
  if (!t) return 0;
  return Math.max(0, Math.round((Date.now() - t) / 60000));
};

const money = (n, currency) => `${currency || 'UGX'} ${Number(n || 0).toLocaleString()}`;

export default function ScreenPage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    screensApi.info(token)
      .then(r => setInfo(r.data))
      .catch(e => setError(e.response?.data?.detail || 'This screen link is not valid'));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-200 flex items-center justify-center p-8"
           data-testid="screen-error">
        <div className="text-center space-y-2">
          <Monitor size={40} className="mx-auto text-slate-600" />
          <p className="text-lg font-semibold">{error}</p>
          <p className="text-sm text-slate-400">Ask the shop to pair this screen again.</p>
        </div>
      </div>
    );
  }
  if (!info) {
    return <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-slate-500 border-t-transparent" />
    </div>;
  }
  return info.kind === 'kitchen'
    ? <KitchenScreen token={token} info={info} />
    : <CustomerScreen token={token} info={info} />;
}

/** The cooks' board: tickets as cards, tap a dish as it comes up. */
const KitchenScreen = ({ token, info }) => {
  const [orders, setOrders] = useState([]);
  const [tick, setTick] = useState(0);

  const load = useCallback(() => {
    screensApi.orders(token).then(r => setOrders(r.data || [])).catch(() => {});
  }, [token]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    const m = setInterval(() => setTick(x => x + 1), 30000);   // keeps the clocks honest
    return () => { clearInterval(t); clearInterval(m); };
  }, [load]);

  const advance = async (order, item) => {
    try {
      await screensApi.advanceItem(token, order.id, item.line_id);
      load();
    } catch { /* the board refreshes itself either way */ }
  };
  const allReady = async (order) => {
    try { await screensApi.advanceOrder(token, order.id, 'ready'); load(); } catch { /* as above */ }
  };
  const served = async (order) => {
    try { await screensApi.advanceOrder(token, order.id, 'served'); load(); } catch { /* as above */ }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 sm:p-6" data-testid="kitchen-screen">
      <div className="flex items-center justify-between gap-3 mb-4">
        <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2">
          <ChefHat size={26} className="text-amber-400" /> {info.store_name || 'Kitchen'}
        </h1>
        <p className="text-xs text-slate-400" data-testid="kitchen-screen-name">
          {info.name} · refreshes itself{tick ? '' : ''}
        </p>
      </div>

      {!orders.length ? (
        <div className="h-[70vh] flex items-center justify-center text-slate-500 text-lg"
             data-testid="kitchen-screen-empty">
          Nothing waiting. Tickets land here the moment the till sends them.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {orders.map(order => {
            const mins = minutesSince(order.created_at);
            return (
              <div key={order.id}
                   className={`rounded-xl border-2 bg-slate-900/80 p-4 space-y-3 ${
                     order.status === 'ready' ? 'border-emerald-500'
                       : order.status === 'cooking' ? 'border-amber-400' : 'border-slate-700'}`}
                   data-testid={`screen-order-${order.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xl font-bold leading-tight">
                      {order.table_label ? `Table ${order.table_label}` : 'Takeaway'}
                    </p>
                    <p className="text-xs text-slate-400">
                      {order.ticket_number} · {order.server_name || '—'}
                    </p>
                  </div>
                  <span className={`text-sm font-bold tabular-nums px-2 py-0.5 rounded-full flex items-center gap-1 ${
                    mins > 20 ? 'bg-rose-500/20 text-rose-300' : 'bg-slate-700/60 text-slate-300'}`}
                        data-testid={`screen-age-${order.id}`}>
                    <Clock size={12} /> {mins}m
                  </span>
                </div>
                <div className="space-y-1.5">
                  {(order.items || []).filter(i => !i.cancelled).map(item => (
                    <button key={item.line_id} onClick={() => advance(order, item)}
                      className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                        item.status === 'ready' ? 'border-emerald-500/60 bg-emerald-500/10'
                          : item.status === 'cooking' ? 'border-amber-400/60 bg-amber-400/10'
                          : item.status === 'served' ? 'border-slate-700 opacity-50' : 'border-slate-700 hover:bg-slate-800'}`}
                      data-testid={`screen-item-${item.line_id}`}>
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-semibold">{item.qty} × {item.name}</span>
                        <span className="text-[10px] uppercase tracking-wide text-slate-400">{item.status}</span>
                      </span>
                      {item.notes && <span className="block text-sm text-amber-300 font-medium">» {item.notes}</span>}
                      {item.station && <span className="block text-[10px] text-slate-500">{item.station}</span>}
                    </button>
                  ))}
                </div>
                {order.note && <p className="text-xs text-slate-400">Note: {order.note}</p>}
                <div className="flex gap-2">
                  <button onClick={() => allReady(order)}
                          className="flex-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-semibold"
                          data-testid={`screen-ready-${order.id}`}>All ready</button>
                  <button onClick={() => served(order)}
                          className="rounded-lg border border-slate-700 hover:bg-slate-800 px-3 py-2 text-sm"
                          data-testid={`screen-served-${order.id}`}>Served</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

/** The customer's side of the counter: what has been rung up, and the total. */
const CustomerScreen = ({ token, info }) => {
  const [sale, setSale] = useState({ state: 'idle', lines: [], total: 0 });

  useEffect(() => {
    let alive = true;
    const load = () => screensApi.sale(token)
      .then(r => { if (alive) setSale(r.data || { state: 'idle', lines: [], total: 0 }); })
      .catch(() => {});
    load();
    const t = setInterval(load, 2500);         // a till moves fast
    return () => { alive = false; clearInterval(t); };
  }, [token]);

  const currency = sale.currency || info.currency || 'UGX';
  const lines = sale.lines || [];
  const paid = sale.state === 'paid';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col" data-testid="customer-screen">
      <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
        <p className="text-lg font-semibold">{sale.store_name || info.store_name || 'Welcome'}</p>
        <p className="text-xs text-slate-500" data-testid="customer-screen-name">{info.name}</p>
      </div>

      {paid ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8 text-center"
             data-testid="customer-screen-paid">
          <p className="text-3xl sm:text-5xl font-bold text-emerald-400">Thank you</p>
          <p className="text-xl tabular-nums">Paid {money(sale.total, currency)}</p>
          {sale.change_due != null && Number(sale.change_due) > 0 && (
            <p className="text-2xl font-semibold" data-testid="customer-change-due">
              Your change: {money(sale.change_due, currency)}
            </p>
          )}
          {sale.receipt_number && <p className="text-sm text-slate-400">Receipt {sale.receipt_number}</p>}
        </div>
      ) : !lines.length ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-500"
             data-testid="customer-screen-idle">
          <ShoppingCart size={44} />
          <p className="text-xl">Ready when you are</p>
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto divide-y divide-slate-800" data-testid="customer-screen-lines">
            {lines.map((l, i) => (
              <div key={i} className="flex items-baseline justify-between gap-4 px-6 py-3"
                   data-testid={`customer-line-${i}`}>
                <span className="text-lg sm:text-xl">
                  <span className="tabular-nums text-slate-400 mr-2">{l.qty} ×</span>{l.name}
                </span>
                <span className="text-lg sm:text-xl tabular-nums">{money(l.line_total ?? (l.price * l.qty), currency)}</span>
              </div>
            ))}
          </div>
          <div className="border-t border-slate-800 px-6 py-5 space-y-1">
            {!!Number(sale.discount) && (
              <div className="flex justify-between text-sm text-emerald-400">
                <span>Discount</span><span className="tabular-nums">− {money(sale.discount, currency)}</span>
              </div>
            )}
            <div className="flex items-baseline justify-between">
              <span className="text-xl text-slate-400">Total</span>
              <span className="text-4xl sm:text-6xl font-bold tabular-nums" data-testid="customer-total">
                {money(sale.total, currency)}
              </span>
            </div>
            {sale.cashier && <p className="text-xs text-slate-500">Served by {sale.cashier}</p>}
          </div>
        </>
      )}
    </div>
  );
};
