import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Users } from 'lucide-react';
import { kitchenApi } from '../../services/api';

/** Who served what: tables, takings and tips per waiter (iter420). */
export const ServersReportDialog = ({ open, onOpenChange, locationId, currency = 'UGX' }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    kitchenApi.servers({ location_id: locationId || undefined, date_from: from, date_to: to })
      .then(r => setReport(r.data))
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [open, locationId, from, to]);

  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;
  const rows = report?.servers || [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="servers-report-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <Users size={16} className="text-primary" /> Who served what
          </DialogTitle>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <Input type="date" value={from} onChange={e => setFrom(e.target.value)} className="h-8 text-xs"
                 data-testid="servers-from" />
          <span className="text-xs text-muted-foreground">to</span>
          <Input type="date" value={to} onChange={e => setTo(e.target.value)} className="h-8 text-xs"
                 data-testid="servers-to" />
        </div>
        {loading ? (
          <p className="text-sm text-muted-foreground">Counting…</p>
        ) : !rows.length ? (
          <p className="text-sm text-muted-foreground" data-testid="servers-empty">
            No tables served in that window.
          </p>
        ) : (
          <>
            <div className="rounded-lg border border-border divide-y divide-border">
              {rows.map(s => (
                <div key={s.server_id} className="flex items-center justify-between gap-3 px-3 py-2"
                     data-testid={`server-row-${s.server_id}`}>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">{s.server_name}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {s.tables} table(s) · {s.dishes} dish(es)
                      {s.open_tabs ? ` · ${s.open_tabs} still open` : ''}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-bold tabular-nums">{money(s.takings)}</p>
                    {!!s.tips && <p className="text-[11px] text-emerald-600 tabular-nums">{money(s.tips)} in tips</p>}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Tips are recorded against the waiter who served the table, not added to the sale total.
            </p>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
