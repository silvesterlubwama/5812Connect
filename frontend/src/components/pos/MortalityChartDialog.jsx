import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';
import { Activity } from 'lucide-react';
import { stockApi } from '../../services/api';

/**
 * Deaths per batch, week by week — every figure comes from a recorded
 * write-off, which is the only place a death is ever entered (iter419).
 */
export const MortalityChartDialog = ({ open, onOpenChange, locationId, productId }) => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    stockApi.mortality({ location_id: locationId || undefined, product_id: productId || undefined, weeks: 8 })
      .then(r => setReport(r.data))
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [open, locationId, productId]);

  const rows = report?.batches || [];
  const peak = Math.max(1, ...rows.flatMap(b => (b.weeks || []).map(w => w.deaths)));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="mortality-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <Activity size={16} className="text-destructive" /> Deaths by week, batch by batch
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground">Counting…</p>
        ) : !rows.length ? (
          <p className="text-sm text-muted-foreground" data-testid="mortality-empty">
            No batches here yet. Bring in stock of something that grows on and it appears here.
          </p>
        ) : (
          <>
            {report.worst && (
              <p className="text-sm bg-destructive/10 border border-destructive/30 rounded-lg px-3 py-2"
                 data-testid="mortality-worst">
                Weakest run: <span className="font-semibold">{report.worst.product_name}</span> in on{' '}
                {String(report.worst.received_at).slice(0, 10)} — {report.worst.lost} of{' '}
                {report.worst.started_with} lost ({report.worst.mortality_pct}%).
              </p>
            )}

            <div className="space-y-4 max-h-[26rem] overflow-y-auto pr-1">
              {rows.map((b, i) => (
                <div key={b.batch_id} className="border-b border-border/60 pb-3 last:border-0"
                     data-testid={`mortality-batch-${i}`}>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">
                        {b.product_name} <span className="font-normal text-muted-foreground">
                          · in on {String(b.received_at).slice(0, 10)}</span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {b.started_with} in · {b.remaining} left · {b.status === 'matured' ? 'grown on' : 'growing'}
                        {Object.keys(b.by_reason || {}).length
                          ? ` · ${Object.entries(b.by_reason).map(([r, q]) => `${r} ×${q}`).join(', ')}`
                          : ''}
                      </p>
                    </div>
                    <Badge variant={b.mortality_pct >= 10 ? 'destructive' : 'secondary'}
                           data-testid={`mortality-pct-${i}`}>
                      {b.mortality_pct}% lost
                    </Badge>
                  </div>

                  <div className="flex items-end gap-1.5 h-20">
                    {(b.weeks || []).map(w => (
                      <div key={w.week} className="flex-1 flex flex-col items-center gap-1"
                           title={`Week ${w.week}: ${w.deaths} lost`} data-testid={`mortality-bar-${i}-${w.week}`}>
                        <span className="text-[10px] text-muted-foreground tabular-nums">
                          {w.deaths || ''}
                        </span>
                        <div className={`w-full rounded-t transition-all ${w.deaths ? 'bg-destructive/70' : 'bg-muted'}`}
                             style={{ height: `${w.deaths ? Math.max(6, (w.deaths / peak) * 56) : 3}px` }} />
                        <span className="text-[10px] text-muted-foreground">W{w.week}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Counted from write-offs against each batch, oldest batch first — so the week a bird
              was recorded as dead is the week it shows up in.
            </p>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
