import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Egg } from 'lucide-react';
import { toast } from 'sonner';
import { stockApi } from '../../services/api';

/**
 * Booking in produce (iter424).
 *
 * A farm takes delivery of birds, not of "stock": 100 day-old chicks from a
 * named hatchery on a given date. That one action books the stock onto the
 * stage AND starts the clock, so nobody has to add stock and then remember to
 * open a batch over it.
 */
export const BatchIntakeDialog = ({ open, onOpenChange, products = [], locationId, onDone }) => {
  const produce = products.filter(p => p.is_produce && (p.variants || []).length);
  const [productId, setProductId] = useState('');
  const [variantId, setVariantId] = useState('');
  const [qty, setQty] = useState('');
  const [supplier, setSupplier] = useState('');
  const [received, setReceived] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);

  const product = produce.find(p => p.id === productId) || null;
  const stages = (product?.variants || []);
  const stage = stages.find(v => v.id === variantId) || null;

  useEffect(() => {
    if (!open) return;
    setProductId(produce.length === 1 ? produce[0].id : '');
    setVariantId(''); setQty(''); setSupplier('');
    setReceived(new Date().toISOString().slice(0, 10));
  }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // The first stage is nearly always the one that arrives.
    const first = (product?.variants || []).find(v => v.grow_after_days);
    setVariantId(first?.id || (product?.variants || [])[0]?.id || '');
  }, [productId]);   // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    const n = Number(qty);
    if (!productId) { toast.error('Pick the produce item'); return; }
    if (!variantId) { toast.error('Pick which stage came in'); return; }
    if (!n || n <= 0) { toast.error('Say how many came in'); return; }
    setBusy(true);
    try {
      const res = await stockApi.createBatch({
        product_id: productId, variant_id: variantId, qty: n,
        location_id: locationId || undefined,
        received_at: `${received}T08:00:00`,
        supplier: supplier.trim(), add_stock: true,
      });
      toast.success(res.data?.message || 'Batch booked in');
      onDone?.(res.data?.batch);
      onOpenChange(false);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not book that batch in');
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="batch-intake-dialog">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2">
            <Egg size={16} className="text-amber-600" /> Book in a batch
          </DialogTitle>
        </DialogHeader>

        {!produce.length ? (
          <p className="text-sm text-muted-foreground" data-testid="no-produce-note">
            No produce items yet. Open a product, tick <strong>produce or livestock</strong> and add
            its stages — Day-old chicks, 4 Week Broilers — each with its own price and days.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">What came in?</Label>
              <Select value={productId} onValueChange={setProductId}>
                <SelectTrigger data-testid="intake-product-select"><SelectValue placeholder="Pick the produce item" /></SelectTrigger>
                <SelectContent>
                  {produce.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {!!stages.length && (
              <div className="space-y-1">
                <Label className="text-xs">At which stage?</Label>
                <Select value={variantId} onValueChange={setVariantId}>
                  <SelectTrigger data-testid="intake-stage-select"><SelectValue placeholder="Pick the stage" /></SelectTrigger>
                  <SelectContent>
                    {stages.map(v => (
                      <SelectItem key={v.id} value={v.id}>
                        {v.name}{v.grow_after_days ? ` — grows on after ${v.grow_after_days} days` : ' — final stage'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">How many</Label>
                <Input type="number" min="1" value={qty} onChange={e => setQty(e.target.value)}
                  placeholder="100" data-testid="intake-qty-input" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Date they came in</Label>
                <Input type="date" value={received} onChange={e => setReceived(e.target.value)}
                  data-testid="intake-date-input" />
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Which hatchery or supplier</Label>
              <Input value={supplier} onChange={e => setSupplier(e.target.value)}
                placeholder="e.g. Kabira Hatchery" data-testid="intake-supplier-input" />
              <p className="text-[11px] text-muted-foreground">
                Worth filling in: it is how one run can later be set against another.
              </p>
            </div>

            {stage?.grow_after_days ? (
              <p className="text-[11px] text-muted-foreground" data-testid="intake-summary">
                This books {qty || '…'} onto {stage.name} and starts its clock. In{' '}
                {stage.grow_after_days} days they become the next stage by themselves, at that
                stage's price. Deaths are recorded against this batch.
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                This stage does not grow on, so the batch simply records what came in and when.
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={busy || !produce.length} data-testid="intake-save-btn">
            {busy ? 'Booking in…' : 'Book in'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
