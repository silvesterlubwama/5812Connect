import { useEffect, useState, useCallback } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Utensils, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { kitchenApi } from '../../services/api';

const mins = (iso) => {
  const t = Date.parse(iso || '');
  return t ? Math.max(0, Math.round((Date.now() - t) / 60000)) : 0;
};

/** Tabs still open on tables — pick one up to add to it or to settle it. */
export const OpenTabsDialog = ({ open, onOpenChange, locationId, currency = 'UGX', onPickUp }) => {
  const [tabs, setTabs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    kitchenApi.orders({ location_id: locationId || undefined, scope: 'tabs' })
      .then(r => setTabs(r.data || []))
      .catch(() => setTabs([]))
      .finally(() => setLoading(false));
  }, [locationId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;

  const cancel = async (tab) => {
    try { await kitchenApi.cancel(tab.id); toast.success('Tab cancelled'); load(); }
    catch (e) { toast.error(e.response?.data?.detail || 'Could not cancel'); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="open-tabs-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <Utensils size={16} className="text-amber-600" /> Open tabs
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground">Looking…</p>
        ) : !tabs.length ? (
          <p className="text-sm text-muted-foreground" data-testid="open-tabs-empty">
            No tables have an open tab. Send a basket to the kitchen to start one.
          </p>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {tabs.map(tab => (
              <div key={tab.id} className="rounded-lg border border-border px-3 py-2" data-testid={`tab-${tab.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-sm">
                      {tab.table_label ? `Table ${tab.table_label}` : 'Takeaway'}
                      <span className="text-xs text-muted-foreground font-normal"> · {tab.ticket_number}</span>
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {(tab.items || []).filter(i => !i.cancelled).map(i => `${i.qty}× ${i.name}`).join(', ')}
                    </p>
                  </div>
                  <Badge variant="secondary" className="gap-1 shrink-0"><Clock size={10} /> {mins(tab.created_at)}m</Badge>
                </div>
                <div className="flex items-center justify-between gap-2 mt-2">
                  <span className="text-sm font-bold text-primary" data-testid={`tab-total-${tab.id}`}>{money(tab.total)}</span>
                  <span className="flex gap-2">
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive"
                      onClick={() => cancel(tab)} data-testid={`tab-cancel-${tab.id}`}>Cancel</Button>
                    <Button size="sm" className="h-7 text-xs" onClick={() => { onPickUp(tab); onOpenChange(false); }}
                      data-testid={`tab-settle-${tab.id}`}>Bring to till</Button>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
