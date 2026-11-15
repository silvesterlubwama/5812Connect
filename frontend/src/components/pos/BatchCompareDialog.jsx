import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { GitCompare } from 'lucide-react';
import { stockApi } from '../../services/api';

/**
 * Two hatchery runs side by side. Same birds, same feed, different supplier —
 * the one that loses you birds shows itself (iter420).
 */
export const BatchCompareDialog = ({ open, onOpenChange, locationId }) => {
  const [batches, setBatches] = useState([]);
  const [left, setLeft] = useState('');
  const [right, setRight] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    stockApi.batches({ location_id: locationId || undefined, status: 'all', limit: 50 })
      .then(r => {
        const rows = r.data || [];
        setBatches(rows);
        if (rows[0]) setLeft(v => v || rows[0].id);
        if (rows[1]) setRight(v => v || rows[1].id);
      })
      .catch(() => setBatches([]));
  }, [open, locationId]);

  const run = async () => {
    if (!left || !right || left === right) { setError('Pick two different runs'); return; }
    setError(''); setLoading(true);
    try {
      const r = await stockApi.compareBatches([left, right], 8);
      setReport(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not compare those runs');
      setReport(null);
    } finally { setLoading(false); }
  };

  const label = (b) => `${b.product_name} · ${String(b.received_at).slice(0, 10)}`
    + (b.supplier ? ` · ${b.supplier}` : '');
  const rows = report?.batches || [];
  const peak = Math.max(1, ...rows.flatMap(b => (b.weeks || []).map(w => w.deaths)));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="batch-compare-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <GitCompare size={16} className="text-primary" /> Two runs, side by side
          </DialogTitle>
        </DialogHeader>

        {batches.length < 2 ? (
          <p className="text-sm text-muted-foreground" data-testid="compare-not-enough">
            There is only one run on record here. Once a second intake is booked in, the two can be
            set against each other.
          </p>
        ) : (
          <>
            <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
              <div className="space-y-1">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">First run</p>
                <Select value={left} onValueChange={setLeft}>
                  <SelectTrigger className="h-9 text-xs" data-testid="compare-left-select"><SelectValue placeholder="Pick a run" /></SelectTrigger>
                  <SelectContent>
                    {batches.map(b => <SelectItem key={b.id} value={b.id}>{label(b)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Against</p>
                <Select value={right} onValueChange={setRight}>
                  <SelectTrigger className="h-9 text-xs" data-testid="compare-right-select"><SelectValue placeholder="Pick a run" /></SelectTrigger>
                  <SelectContent>
                    {batches.map(b => <SelectItem key={b.id} value={b.id}>{label(b)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" className="h-9" onClick={run} disabled={loading} data-testid="compare-run-btn">
                {loading ? 'Counting…' : 'Compare'}
              </Button>
            </div>
            {error && <p className="text-xs text-destructive" data-testid="compare-error">{error}</p>}

            {!!rows.length && (
              <>
                {report.verdict && (
                  <p className="text-sm bg-muted rounded-lg px-3 py-2" data-testid="compare-verdict">
                    {report.verdict}
                  </p>
                )}
                <div className="grid sm:grid-cols-2 gap-3">
                  {rows.map((b, i) => (
                    <div key={b.batch_id} className="rounded-lg border border-border p-3 space-y-2"
                         data-testid={`compare-col-${i}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold truncate">{b.supplier || 'Supplier not recorded'}</p>
                          <p className="text-xs text-muted-foreground">
                            {b.product_name} · in on {String(b.received_at).slice(0, 10)}
                          </p>
                        </div>
                        <Badge variant={b.mortality_pct >= 10 ? 'destructive' : 'secondary'}
                               data-testid={`compare-pct-${i}`}>{b.mortality_pct}% lost</Badge>
                      </div>
                      <div className="grid grid-cols-3 gap-1 text-center">
                        <div><p className="text-base font-bold tabular-nums">{b.started_with}</p><p className="text-[10px] text-muted-foreground">came in</p></div>
                        <div><p className="text-base font-bold tabular-nums text-destructive">{b.lost}</p><p className="text-[10px] text-muted-foreground">lost</p></div>
                        <div><p className="text-base font-bold tabular-nums text-emerald-600">{b.survival_pct}%</p><p className="text-[10px] text-muted-foreground">survived</p></div>
                      </div>
                      <div className="flex items-end gap-1 h-16">
                        {(b.weeks || []).map(w => (
                          <div key={w.week} className="flex-1 flex flex-col items-center gap-0.5"
                               title={`Week ${w.week}: ${w.deaths} lost`} data-testid={`compare-bar-${i}-${w.week}`}>
                            <span className="text-[9px] text-muted-foreground tabular-nums">{w.deaths || ''}</span>
                            <div className={`w-full rounded-t ${w.deaths ? 'bg-destructive/70' : 'bg-muted'}`}
                                 style={{ height: `${w.deaths ? Math.max(5, (w.deaths / peak) * 40) : 3}px` }} />
                            <span className="text-[9px] text-muted-foreground">W{w.week}</span>
                          </div>
                        ))}
                      </div>
                      {!!Object.keys(b.by_reason || {}).length && (
                        <p className="text-[11px] text-muted-foreground">
                          {Object.entries(b.by_reason).map(([r, q]) => `${r} ×${q}`).join(', ')}
                        </p>
                      )}
                    </div>
                  ))}
                </div>

                {report.by_supplier?.length > 1 && (
                  <div className="rounded-lg border border-border divide-y divide-border" data-testid="compare-by-supplier">
                    {report.by_supplier.map(s => (
                      <div key={s.supplier} className="flex items-center justify-between px-3 py-1.5 text-xs">
                        <span className="font-medium truncate">{s.supplier}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {s.lost} of {s.started_with} lost · <span className={s.mortality_pct >= 10 ? 'text-destructive font-semibold' : ''}>{s.mortality_pct}%</span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-[11px] text-muted-foreground">
                  Weeks are counted from the day each run was booked in, so week 3 means week 3 of that
                  run's own life — not the same calendar week.
                </p>
              </>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};
