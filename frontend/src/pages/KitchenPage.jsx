import { useEffect, useState, useCallback } from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ChefHat, Clock, Check, RefreshCw, Printer, X } from 'lucide-react';
import { toast } from 'sonner';
import { kitchenApi, storeSettingsApi, locationsApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { printKitchenTicket, kitchenTicketText, printSlipFallback } from '../utils/tillPrinter';

const STAGES = [
  { key: 'new', label: 'In the queue', tone: 'border-slate-300' },
  { key: 'cooking', label: 'On the stove', tone: 'border-amber-400' },
  { key: 'ready', label: 'Ready to carry', tone: 'border-emerald-500' },
];

const minutesSince = (iso) => {
  const t = Date.parse(iso || '');
  if (!t) return 0;
  return Math.max(0, Math.round((Date.now() - t) / 60000));
};

/** The kitchen screen: tickets as cards, tap a dish as it comes up. */
export default function KitchenPage() {
  const { user } = useAuth();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState({});
  const storeId = user?.active_campus_id || localStorage.getItem('5812_pos_store_id') || user?.location_id || '';

  const load = useCallback(async () => {
    try {
      const r = await kitchenApi.orders({ location_id: storeId || undefined, scope: 'open' });
      setOrders(r.data || []);
    } catch { /* the screen keeps the last tickets rather than going blank */ }
    setLoading(false);
  }, [storeId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);     // a kitchen screen refreshes itself
    return () => clearInterval(t);
  }, [load]);

  const [storeName, setStoreName] = useState('');
  useEffect(() => {
    if (!storeId) return;
    storeSettingsApi.get(storeId).then(r => setSettings(r.data || {})).catch(() => {});
    // The location's own name, not the trading name in Store Settings — those
    // can be anything, and a cook needs to know which kitchen this is.
    locationsApi.list().then(r => {
      setStoreName((r.data || []).find(l => l.id === storeId)?.name || '');
    }).catch(() => {});
  }, [storeId]);

  const advanceItem = async (order, item) => {
    try {
      const r = await kitchenApi.setItemStatus(order.id, item.line_id);
      toast.success(r.data?.message || 'Updated');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not update'); }
  };

  const advanceOrder = async (order, status) => {
    try {
      const r = await kitchenApi.setOrderStatus(order.id, status);
      toast.success(r.data?.message || 'Updated');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not update'); }
  };

  const reprint = async (order) => {
    const res = await printKitchenTicket(order, settings, { reprint: true });
    if (res.printed) { toast.success('Ticket reprinted'); return; }
    printSlipFallback(order.ticket_number, kitchenTicketText(order, { columns: 48, reprint: true }));
  };

  const cancel = async (order) => {
    try {
      await kitchenApi.cancel(order.id);
      toast.success('Ticket cancelled');
      load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not cancel'); }
  };

  return (
    <div className="p-4 sm:p-6 space-y-4" data-testid="kitchen-page">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2">
            <ChefHat size={24} className="text-amber-600" /> Kitchen
          </h1>
          <p className="text-sm text-muted-foreground">
            {storeName || settings.store_name || 'This store'} · tickets refresh by themselves
          </p>
        </div>
        <Button variant="outline" size="sm" className="gap-1" onClick={load} data-testid="kitchen-refresh-btn">
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      {loading ? (
        <div className="grid md:grid-cols-3 gap-4">{[1, 2, 3].map(i => <div key={i} className="h-40 bg-muted animate-pulse rounded-xl" />)}</div>
      ) : !orders.length ? (
        <Card className="rounded-xl"><CardContent className="p-10 text-center text-muted-foreground" data-testid="kitchen-empty">
          Nothing waiting. Tickets land here the moment the till sends them.
        </CardContent></Card>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {orders.map(order => {
            const stage = STAGES.find(s => s.key === order.status) || STAGES[0];
            const mins = minutesSince(order.created_at);
            return (
              <Card key={order.id} className={`rounded-xl border-2 ${stage.tone}`} data-testid={`kitchen-order-${order.id}`}>
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-lg font-bold leading-tight">
                        {order.table_label ? `Table ${order.table_label}` : 'Takeaway'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {order.ticket_number} · {order.server_name || '—'}
                      </p>
                    </div>
                    <Badge variant={mins > 20 ? 'destructive' : 'secondary'} className="gap-1 shrink-0"
                           data-testid={`kitchen-age-${order.id}`}>
                      <Clock size={11} /> {mins}m
                    </Badge>
                  </div>

                  <div className="space-y-1.5">
                    {(order.items || []).filter(i => !i.cancelled).map(item => (
                      <button key={item.line_id} onClick={() => advanceItem(order, item)}
                        className={`w-full text-left rounded-lg border px-3 py-2 transition-colors hover:bg-muted/60
                          ${item.status === 'ready' ? 'border-emerald-500/60 bg-emerald-50/60 dark:bg-emerald-950/20'
                            : item.status === 'cooking' ? 'border-amber-400/60 bg-amber-50/60 dark:bg-amber-950/20'
                            : item.status === 'served' ? 'border-border opacity-60' : 'border-border'}`}
                        data-testid={`kitchen-item-${item.line_id}`}>
                        <span className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-sm">{item.qty} × {item.name}</span>
                          <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{item.status}</span>
                        </span>
                        {item.notes && <span className="block text-xs text-amber-700 dark:text-amber-400 font-medium">» {item.notes}</span>}
                        {item.station && <span className="block text-[10px] text-muted-foreground">{item.station}</span>}
                      </button>
                    ))}
                  </div>

                  {order.note && <p className="text-xs text-muted-foreground">Note: {order.note}</p>}

                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" className="flex-1" onClick={() => advanceOrder(order, 'cooking')}
                      data-testid={`kitchen-cooking-${order.id}`}>Start cooking</Button>
                    <Button size="sm" variant="outline" className="flex-1 gap-1" onClick={() => advanceOrder(order, 'ready')}
                      data-testid={`kitchen-ready-${order.id}`}><Check size={13} /> All ready</Button>
                    <Button size="sm" variant="ghost" onClick={() => advanceOrder(order, 'served')}
                      data-testid={`kitchen-served-${order.id}`}>Served</Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => reprint(order)}
                      data-testid={`kitchen-reprint-${order.id}`} title="Reprint ticket"><Printer size={13} /></Button>
                    {!order.paid && (
                      <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive" onClick={() => cancel(order)}
                        data-testid={`kitchen-cancel-${order.id}`} title="Cancel ticket"><X size={13} /></Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
