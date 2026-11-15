import { useState, useEffect, useCallback } from 'react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Egg, ArrowRight, Check, Activity, GitCompare } from 'lucide-react';
import { MortalityChartDialog } from './MortalityChartDialog';
import { BatchCompareDialog } from './BatchCompareDialog';
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
  const [busy, setBusy] = useState('');
  const [showMortality, setShowMortality] = useState(false);
  const [showCompare, setShowCompare] = useState(false);
  const [namingSupplier, setNamingSupplier] = useState(null);   // batch id
  const [supplierDraft, setSupplierDraft] = useState('');

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
      const res = await stockApi.matureBatch(batch.id, {});
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

  const saveSupplier = async (batch) => {
    try {
      await stockApi.updateBatch(batch.id, { supplier: supplierDraft });
      setBatches(list => list.map(b => b.id === batch.id ? { ...b, supplier: supplierDraft.trim() } : b));
      setNamingSupplier(null);
      toast.success(supplierDraft.trim() ? `Run marked as ${supplierDraft.trim()}` : 'Supplier cleared');
    } catch (e) { toast.error(e.response?.data?.detail || 'Could not save that'); }
  };

  if (!batches.length && !recent.length) return null;
  const money = (n) => `${currency} ${Number(n || 0).toLocaleString()}`;

  return (
    <div className="rounded-xl border border-border p-4 space-y-3" data-testid="growing-batches-panel">
      <div className="flex items-center gap-2 flex-wrap">
        <Egg size={16} className="text-amber-600" />
        <h3 className="text-base font-semibold">Growing on</h3>
        <Badge variant="secondary" data-testid="growing-count">{batches.length}</Badge>
        <Button size="sm" variant="outline" className="ml-auto h-7 gap-1 text-xs"
                onClick={() => setShowCompare(true)} data-testid="batch-compare-btn">
          <GitCompare size={12} /> Compare runs
        </Button>
        <Button size="sm" variant="outline" className="h-7 gap-1 text-xs"
                onClick={() => setShowMortality(true)} data-testid="mortality-chart-btn">
          <Activity size={12} /> Mortality
        </Button>
      </div>
      <MortalityChartDialog open={showMortality} onOpenChange={setShowMortality} locationId={locationId} />
      <BatchCompareDialog open={showCompare} onOpenChange={setShowCompare} locationId={locationId} />

      {recent.map(t => (
        <div key={t.id} className="flex items-start justify-between gap-3 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 px-3 py-2"
             data-testid={`grown-notice-${t.id}`}>
          <p className="text-sm">
            <span className="font-semibold">{t.qty} {t.from_product_name}</span> became{' '}
            <span className="font-semibold">{t.to_product_name}</span> on {String(t.created_at).slice(0, 10)} —
            now worth {money(t.to_value)}.
            {t.lost_on_the_way > 0 ? ` ${t.lost_on_the_way} were lost on the way.` : ''}
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
            {namingSupplier === b.id ? (
              <div className="flex items-center gap-1.5 mt-1">
                <Input autoFocus value={supplierDraft} onChange={e => setSupplierDraft(e.target.value)}
                       onKeyDown={e => { if (e.key === 'Enter') saveSupplier(b); }}
                       placeholder="Which hatchery?" className="h-7 text-xs max-w-[12rem]"
                       data-testid={`batch-supplier-input-${b.id}`} />
                <Button size="sm" variant="outline" className="h-7 text-[11px] px-2" onClick={() => saveSupplier(b)}
                        data-testid={`batch-supplier-save-${b.id}`}>Save</Button>
                <Button size="sm" variant="ghost" className="h-7 text-[11px] px-2"
                        onClick={() => setNamingSupplier(null)}>Cancel</Button>
              </div>
            ) : (
              <button type="button"
                onClick={() => { setNamingSupplier(b.id); setSupplierDraft(b.supplier || ''); }}
                className="text-xs text-primary hover:underline mt-0.5"
                data-testid={`batch-supplier-${b.id}`}>
                {b.supplier ? `from ${b.supplier}` : 'name the hatchery'}
              </button>
            )}
          </div>
          <Button size="sm" variant="outline" className="h-8" disabled={busy === b.id}
                  onClick={() => matureNow(b)} data-testid={`batch-mature-btn-${b.id}`}>
            {busy === b.id ? 'Working…' : 'Grow on now'}
          </Button>
        </div>
      ))}
    </div>
  );
};
