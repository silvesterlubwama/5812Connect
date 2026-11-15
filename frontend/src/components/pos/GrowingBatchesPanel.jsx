import { useState, useEffect, useCallback } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { Egg, ArrowRight, Check } from 'lucide-react';
import { toast } from 'sonner';
import { stockApi } from '../../services/api';

/**
 * Livestock growing on: each intake is a dated batch that becomes another
 * product when its weeks are up. The move happens by itself overnight; this
 * panel is where the farm watches it coming and records any deaths.
 */
export const GrowingBatchesPanel = ({ locationId, currency = 'UGX', onChanged, refreshKey }) => {
  const [batches, setBatches] = useState([]);
  const [recent, setRecent] = useState([]);
  const [lostBy, setLostBy] = useState({});
  const [busy, setBusy] = useState('');

  const load = useCallback(() => {
    stockApi.batches({ location_id: locationId || undefined, status: 'growing' })
      .then(r => setBatches(r.data || [])).catch(() => setBatches([]));
    stockApi.transformations({ location_id: locationId || undefined, limit: 10 })
      .then(r => setRecent((r.data || []).filter(t => t.needs_loss_check))).catch(() => setRecent([]));
  }, [locationId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const matureNow = async (batch) => {
    setBusy(batch.id);
    try {
      const lost = Number(lostBy[batch.id] || 0);
      const res = await stockApi.matureBatch(batch.id, lost > 0 ? { lost } : {});
      toast.success(res.data?.message || 'Grown on');
      load(); onChanged?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not grow this batch on');
    } finally { setBusy(''); }
  };

  const acknowledge = async (t) => {
    try {
      await stockApi.acknowledgeTransformation(t.id);
      setRecent(list => list.filter(x => x.id !== t.id));
    } catch { toast.error('Could not mark it checked'); }
  };

  if (!batches.length && !recent.length) return null;
  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;

  return (
    <div className="rounded-xl border border-border p-4 space-y-3" data-testid="growing-batches-panel">
      <div className="flex items-center gap-2">
        <Egg size={16} className="text-amber-600" />
        <h3 className="text-base font-semibold">Growing on</h3>
        <Badge variant="secondary" data-testid="growing-count">{batches.length}</Badge>
      </div>

      {recent.map(t => (
        <div key={t.id} className="flex items-start justify-between gap-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 px-3 py-2"
             data-testid={`grown-notice-${t.id}`}>
          <p className="text-sm">
            <span className="font-semibold">{t.qty} {t.from_product_name}</span> became{' '}
            <span className="font-semibold">{t.to_product_name}</span> on {String(t.created_at).slice(0, 10)} —
            now worth {money(t.to_value)}.
            {t.lost_on_the_way > 0
              ? ` ${t.lost_on_the_way} were lost on the way.`
              : ` Any deaths? Write them off against ${t.to_product_name}.`}
          </p>
          <Button size="sm" variant="ghost" className="h-7 gap-1 shrink-0" onClick={() => acknowledge(t)}
                  data-testid={`grown-ack-${t.id}`}>
            <Check size={13} /> Checked
          </Button>
        </div>
      ))}

      {batches.map(b => (
        <div key={b.id} className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-2 last:border-0"
             data-testid={`batch-${b.id}`}>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium truncate">
              {b.remaining} {b.product_name} <ArrowRight size={12} className="inline mx-1" /> {b.becomes_product_name}
            </p>
            <p className="text-xs text-muted-foreground">
              in since {String(b.received_at).slice(0, 10)} ·{' '}
              {b.due ? <span className="text-amber-600 font-semibold">due now</span> : `${b.days_to_go} day(s) to go`}
              {b.lost > 0 ? ` · ${b.lost} lost so far` : ''}
            </p>
          </div>
          <Input type="number" min="0" placeholder="deaths" className="h-8 w-24"
                 value={lostBy[b.id] || ''} onChange={(e) => setLostBy(m => ({ ...m, [b.id]: e.target.value }))}
                 data-testid={`batch-lost-input-${b.id}`} />
          <Button size="sm" variant="outline" className="h-8" disabled={busy === b.id}
                  onClick={() => matureNow(b)} data-testid={`batch-mature-btn-${b.id}`}>
            {busy === b.id ? 'Working…' : 'Grow on now'}
          </Button>
        </div>
      ))}
    </div>
  );
};
