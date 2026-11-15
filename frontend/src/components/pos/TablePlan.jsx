import { useEffect, useState, useCallback } from 'react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Utensils, Clock, RefreshCw } from 'lucide-react';
import { kitchenApi } from '../../services/api';

const mins = (iso) => {
  const t = Date.parse(iso || '');
  return t ? Math.max(0, Math.round((Date.now() - t) / 60000)) : 0;
};

const STAGE_TEXT = { new: 'ordered', cooking: 'cooking', ready: 'food up', served: 'eating' };

/**
 * The room at a glance: every table, what it owes and how long it has waited.
 * Tables come from the labels in use plus the list set in Store Settings, so a
 * waiter sees the empty tables too and knows where to seat the next party.
 */
export const TablePlan = ({ locationId, tableLabels = [], currency = 'UGX', onPickUp }) => {
  const [tabs, setTabs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    kitchenApi.orders({ location_id: locationId || undefined, scope: 'tabs' })
      .then(r => setTabs(r.data || []))
      .catch(() => setTabs([]))
      .finally(() => setLoading(false));
  }, [locationId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;
  const taken = tabs.filter(t => t.table_label);
  const takeaways = tabs.filter(t => !t.table_label);
  const labels = Array.from(new Set([
    ...tableLabels.map(String),
    ...taken.map(t => String(t.table_label)),
  ])).sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));

  const tabFor = (label) => taken.find(t => String(t.table_label) === String(label));
  const waited = (tab) => mins(tab.status === 'ready' ? (tab.status_at?.ready || tab.created_at) : tab.created_at);

  return (
    <div className="rounded-xl border border-border p-4 space-y-3" data-testid="table-plan">
      <div className="flex items-center gap-2">
        <Utensils size={16} className="text-amber-600" />
        <h3 className="text-base font-semibold">The room</h3>
        <Badge variant="secondary" data-testid="tables-busy">{taken.length} busy</Badge>
        <Button size="icon" variant="ghost" className="h-7 w-7 ml-auto" onClick={load}
                data-testid="table-plan-refresh"><RefreshCw size={13} /></Button>
      </div>

      {loading ? (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))' }}>
          {[1, 2, 3, 4].map(i => <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />)}
        </div>
      ) : !labels.length ? (
        <p className="text-sm text-muted-foreground" data-testid="table-plan-empty">
          No tables set up yet. Put a table number on an order, or list your tables in
          Store&nbsp;→&nbsp;Restaurant service, and the room appears here.
        </p>
      ) : (
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))' }}>
          {labels.map(label => {
            const tab = tabFor(label);
            const m = tab ? waited(tab) : 0;
            const late = tab && m > 20 && tab.status !== 'served';
            return (
              <button
                key={label}
                onClick={() => tab && onPickUp?.(tab)}
                disabled={!tab}
                data-testid={`table-${label}`}
                className={`rounded-lg border-2 p-2 text-left transition-colors
                  ${!tab ? 'border-dashed border-border text-muted-foreground'
                    : late ? 'border-destructive bg-destructive/10 hover:bg-destructive/15'
                    : tab.status === 'ready' ? 'border-emerald-500 bg-emerald-50/70 dark:bg-emerald-950/20 hover:bg-emerald-100/70'
                    : 'border-amber-400 bg-amber-50/70 dark:bg-amber-950/20 hover:bg-amber-100/70'}`}
              >
                <span className="flex items-center justify-between">
                  {/* "T4" reads naturally for a numbered table; a named one
                      ("Terrace") must not become "TTerrace". */}
                  <span className="text-sm font-bold">{/^\d+$/.test(label) ? `T${label}` : label}</span>
                  {tab && (
                    <span className={`text-[10px] flex items-center gap-0.5 ${late ? 'text-destructive font-semibold' : 'text-muted-foreground'}`}>
                      <Clock size={9} /> {m}m
                    </span>
                  )}
                </span>
                {tab ? (
                  <>
                    <span className="block text-xs font-semibold text-primary" data-testid={`table-total-${label}`}>
                      {money(tab.total)}
                    </span>
                    <span className="block text-[10px] text-muted-foreground truncate">
                      {STAGE_TEXT[tab.status] || tab.status}
                      {tab.server_name ? ` · ${tab.server_name.split(' ')[0]}` : ''}
                    </span>
                  </>
                ) : (
                  <span className="block text-[10px]">free</span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {!!takeaways.length && (
        <div className="pt-1">
          <p className="text-xs text-muted-foreground mb-1">Takeaway waiting</p>
          <div className="flex flex-wrap gap-2">
            {takeaways.map(t => (
              <button key={t.id} onClick={() => onPickUp?.(t)} data-testid={`takeaway-${t.id}`}
                className="rounded-lg border border-border px-2.5 py-1.5 text-xs hover:bg-muted">
                {t.ticket_number} · {money(t.total)} · {mins(t.created_at)}m
              </button>
            ))}
          </div>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        Tap a table to bring its tab to the till. Red means it has been waiting over 20 minutes.
      </p>
    </div>
  );
};
